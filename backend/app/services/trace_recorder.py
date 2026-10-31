"""LLMOps 运行追踪记录器。

每次 agent run 一个 TraceRecorder：orchestrator 的事件循环里同步调用
``on_event``（纯内存追加，零 IO 开销），run 结束（含失败/客户端断开）
在 finally 里 ``flush`` 落库一行 agent_run_traces。

设计取向：
- 步骤瀑布只保留必要字段，detail 截断（LLM 输出可能几十 KB）；
- 步数上限 200 —— 超长 run 丢弃最老的 10%，保留最近步骤；
- flush 失败只记日志，不影响对话主流程。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

from app.core.timezone import app_now
from app.db.models import AgentRunTraceModel
from app.db.session import create_db_session

_logger = logging.getLogger("llmops.trace")

_MAX_STEPS = 200
_MAX_DETAIL = 600


def _clip(value: Any, limit: int = _MAX_DETAIL) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + f"…({len(text)} chars)"


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class TraceRecorder:
    """一次 run 的内存步骤收集器。所有采集方法非阻塞。"""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: int | None,
        agent_profile_id: int | None,
        mode: str,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.agent_profile_id = agent_profile_id
        self.mode = mode
        self._t0 = time.monotonic()
        self._started_at = app_now()
        self._steps: list[dict[str, Any]] = []
        self.status = "running"
        self.error: str | None = None
        self.text_chars = 0
        self.reasoning_chars = 0
        self.tool_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self._flushed = False

    @property
    def latency_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)

    def _append(self, kind: str, name: str = "", detail: str = "") -> None:
        if len(self._steps) >= _MAX_STEPS:
            del self._steps[: max(1, _MAX_STEPS // 10)]
        self._steps.append({
            "kind": kind,
            "name": name[:120],
            "ts_ms": self.latency_ms,
            "detail": _clip(detail),
        })

    def on_event(self, event: Any) -> None:
        """orchestrator 事件循环里逐事件调用（同步、纯内存）。"""
        et = getattr(event, "type", None)
        data = getattr(event, "data", None) or {}

        if et == "tool_start":
            self.tool_calls += 1
            self._append("tool_start", str(data.get("tool_name") or ""), _clip(data.get("args")))
        elif et == "tool_end":
            self._append("tool_end", str(data.get("tool_name") or ""), _clip(data.get("output")))
        elif et == "tool_error":
            self._append("tool_error", str(data.get("tool_name") or ""), _clip(data.get("message")))
        elif et == "text_delta":
            self.text_chars += len(str(data.get("content") or ""))
        elif et == "reasoning_delta":
            self.reasoning_chars += len(str(data.get("content") or ""))
        elif et == "done":
            usage = data.get("usage") or {}
            self.input_tokens = _as_int(usage.get("input_tokens") or usage.get("prompt_tokens"))
            self.output_tokens = _as_int(usage.get("output_tokens") or usage.get("completion_tokens"))
            self.status = "done"
        elif et == "error":
            if self.status == "running":
                self.status = "error"
                self.error = _clip(data.get("message") or "unknown error", 800)
        elif et == "hitl_requested":
            self._append("hitl", str(data.get("tool_name") or ""), "等待人工审批")
        elif et == "artifact_ready":
            self._append("artifact", str(data.get("type") or ""), _clip(data.get("title")))

    async def flush(self) -> int | None:
        """落库一行 trace。返回行 id；失败返回 None（不影响主流程）。"""
        if self._flushed:
            return None
        self._flushed = True

        def _run() -> int:
            with create_db_session() as db:
                row = AgentRunTraceModel(
                    session_id=self.session_id,
                    user_id=self.user_id,
                    agent_profile_id=self.agent_profile_id,
                    mode=self.mode,
                    status=self.status,
                    steps_json=json.dumps(self._steps, ensure_ascii=False),
                    text_chars=self.text_chars,
                    reasoning_chars=self.reasoning_chars,
                    tool_calls=self.tool_calls,
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    latency_ms=self.latency_ms,
                    error=self.error,
                    started_at=self._started_at,
                    finished_at=app_now(),
                )
                db.add(row)
                db.commit()
                return row.id

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:  # noqa: BLE001 -- 观测失败不影响对话
            _logger.warning(f"trace flush failed: {e}")
            return None


def message_fingerprint(content: str | None) -> str:
    """回复内容指纹：反馈定位用（前 200 字符 sha1）。"""
    if not content:
        return ""
    return hashlib.sha1(content[:200].encode("utf-8")).hexdigest()
