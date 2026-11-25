"""上下文压缩（自 wuwei/middleware/context_compression.py 移植，wuwei 退役 A5-5）。

从 Middleware 形态改为**直接操作消息列表**的纯函数式类（引擎在构建
模型输入前调用），行为语义逐条保留：

1. 触发条件：绝对阈值 + 相对阈值（占窗口比例）
2. 保护头部：系统消息 + 前 N 条
3. 保护尾部：按 keep_recent_turns 保留最近轮次，且不在 tool_call 配对中间切断
4. 旧轮次 → LLM 结构化摘要
5. 反抖动：上次压缩节省 <10% 跳过
6. 摘要失败冷却 600s
7. 工具结果去重
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.agent.native.types import BaseMessage, LLMError

logger = logging.getLogger("agenticos.context_compression")

# 同类异常的日志节流
_FAIL_LOG_INTERVAL_S = 600.0

SUMMARY_TEMPLATE = """# Conversation Summary
*This is an automatically generated summary of earlier conversation turns.*
*Use it for context; the original messages have been removed to save tokens.*

## Resolved Questions
{resolved}

## Pending Questions
{pending}

## Active Task
{active_task}

## Key Findings
{key_findings}
"""


class ContextCompressor:
    """上下文压缩器（引擎在每轮 LLM 调用前调用 compress_if_needed）。"""

    def __init__(
        self,
        llm: Any,
        trigger_tokens: int = 6000,
        keep_recent_turns: int = 3,
        max_tokens: int = 128000,
        trigger_ratio: float = 0.75,
        min_savings_ratio: float = 0.10,
        failure_cooldown_s: int = 600,
    ) -> None:
        self.llm = llm
        self.trigger_tokens = trigger_tokens
        self.keep_recent_turns = keep_recent_turns
        self.max_tokens = max_tokens
        self.trigger_ratio = trigger_ratio
        self.min_savings_ratio = min_savings_ratio
        self.failure_cooldown_s = failure_cooldown_s

    # ── 状态（挂在 session.metadata 上，跨 run 存活）────────────────────

    def _state(self, session: Any) -> dict:
        owner = session.metadata.setdefault("middleware_state", {}) if session is not None else {}
        key = f"context_compression:{self.trigger_tokens}:{self.keep_recent_turns}:{self.max_tokens}"
        return owner.setdefault(key, {})

    def _estimate_tokens(self, messages: list[BaseMessage]) -> int:
        """CJK×1.5 + 其他×0.3 的字符启发式（无 tiktoken 依赖）。"""
        cjk = 0
        non_cjk = 0
        for msg in messages:
            for ch in msg.content or "":
                if "\u4e00" <= ch <= "\u9fff":
                    cjk += 1
                else:
                    non_cjk += 1
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    non_cjk_count = len(str(tc))
                    non_cjk += non_cjk_count
        return int(cjk * 1.5 + non_cjk * 0.3)

    # ── 入口 ────────────────────────────────────────────────────────────

    async def compress_if_needed_full(
        self, messages: list[BaseMessage], session: Any, llm: Any
    ) -> list[BaseMessage]:
        """完整压缩入口（引擎使用；把触发检查与压缩合在一起）。"""
        state = self._state(session)
        estimated = self._estimate_tokens(messages)
        trigger = min(self.trigger_tokens, int(self.max_tokens * self.trigger_ratio))
        if estimated <= trigger:
            return messages
        if state.get("last_summary_time", 0) > 0 and state.get("last_summary_saved_tokens", 0) > 0:
            if (estimated - trigger) / state["last_summary_saved_tokens"] < self.min_savings_ratio:
                return messages

        compressed = await self._compress_full(messages, session, llm)
        new_estimate = self._estimate_tokens(compressed)
        state["last_summary_saved_tokens"] = estimated - new_estimate
        state["last_summary_time"] = time.time()
        if len(compressed) < len(messages):
            logger.info(
                "上下文已压缩：%d → %d 条（估算 %d → %d tokens）",
                len(messages), len(compressed), estimated, new_estimate,
            )
        return compressed

    async def _compress_full(
        self, messages: list[BaseMessage], session: Any, llm: Any
    ) -> list[BaseMessage]:
        """压缩实现：切分 + 保护 + 摘要 + 配对回补（原逻辑逐条保留）。"""
        if len(messages) <= 2:
            return messages

        system_messages = [m for m in messages if m.role == "system"]
        non_system = [m for m in messages if m.role != "system"]
        if len(non_system) <= self.keep_recent_turns * 2:
            return messages

        protect_head = min(2, len(non_system) // 3)
        protect_tail = self.keep_recent_turns * 2
        cut = max(len(non_system) - protect_tail, protect_head)
        # 不在 tool_call 配对中间切断
        while cut > protect_head:
            msg = non_system[cut]
            if msg.role == "tool" and msg.tool_call_id:
                found = False
                for j in range(cut - 1, protect_head - 1, -1):
                    prev = non_system[j]
                    if prev.role == "assistant" and prev.tool_calls and any(
                        tc.id == msg.tool_call_id for tc in prev.tool_calls
                    ):
                        cut = j
                        found = True
                        break
                if not found:
                    break
            else:
                break

        old_messages = non_system[protect_head:cut]
        recent_messages = non_system[cut:]
        if not old_messages:
            return messages

        old_messages = self._deduplicate_tool_results(old_messages)
        existing_summary = self._state(session).get("last_summary")
        summary = await self._generate_summary(old_messages, existing_summary, self._state(session), llm)
        if not summary:
            return messages

        self._state(session)["last_summary"] = summary
        summary_msg = BaseMessage(role="system", content=summary)

        # recent 开头的孤立 tool response 回补
        recovered: list[BaseMessage] = []
        while recent_messages and recent_messages[0].role == "tool":
            tc_id = recent_messages[0].tool_call_id
            if tc_id:
                for j in range(len(old_messages) - 1, -1, -1):
                    prev = old_messages[j]
                    if prev.role == "assistant" and prev.tool_calls and any(
                        tc.id == tc_id for tc in prev.tool_calls
                    ):
                        recovered.insert(0, old_messages.pop(j))
                        break
            recent_messages = recent_messages[1:]

        # recent 开头的 assistant(tool_calls) 确保对应 tool response 也在
        if recent_messages and recent_messages[0].role == "assistant" and recent_messages[0].tool_calls:
            assistant_msg = recent_messages[0]
            tc_ids = {tc.id for tc in assistant_msg.tool_calls}
            tool_msgs: list[BaseMessage] = []
            rest = list(recent_messages[1:])
            while rest and rest[0].role == "tool":
                if rest[0].tool_call_id in tc_ids:
                    tool_msgs.append(rest.pop(0))
                else:
                    break
            found_ids = {m.tool_call_id for m in tool_msgs}
            for tc_id in tc_ids - found_ids:
                for j in range(len(old_messages) - 1, -1, -1):
                    prev = old_messages[j]
                    if prev.role == "tool" and prev.tool_call_id == tc_id:
                        tool_msgs.append(old_messages.pop(j))
                        break
            recent_messages = [assistant_msg] + tool_msgs + rest

        return (
            system_messages
            + non_system[:protect_head]
            + [summary_msg]
            + recovered
            + recent_messages
        )

    def _deduplicate_tool_results(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        seen: dict[str, int] = {}
        result: list[BaseMessage] = []
        for msg in messages:
            if msg.role == "tool":
                key = msg.content or ""
                if key in seen:
                    seen[key] += 1
                    result.append(
                        BaseMessage(
                            role="tool",
                            content=f"[同上，结果与消息 #{seen[key]} 相同]",
                            tool_call_id=msg.tool_call_id,
                            name=msg.name,
                        )
                    )
                    continue
                seen[key] = 1
            result.append(msg)
        return result

    async def _generate_summary(
        self,
        messages: list[BaseMessage],
        existing_summary: str | None,
        state: dict,
        llm: Any,
    ) -> str | None:
        if state.get("last_failure_time", 0) > 0 and time.time() - state["last_failure_time"] < self.failure_cooldown_s:
            return None

        parts: list[str] = []
        for msg in messages:
            content = msg.content or ""
            if not content:
                continue
            role = msg.role
            if role == "tool" and len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"[{role}]: {content}")
        conversation_text = "\n".join(parts)
        if not conversation_text.strip():
            return None

        existing_note = f"\n\nPrevious summary (iteratively update it):\n{existing_summary}" if existing_summary else ""
        prompt = (
            "Summarize the following conversation into a structured summary.\n"
            "Focus on: user's goals, decisions made, tool results, current progress, and blockers.\n\n"
            f"{conversation_text}{existing_note}\n\n"
            "Return ONLY the summary, no extra text. Use this format:\n"
            "## Resolved\n- item 1\n## Pending\n- item 1\n## Active Task\ncurrent task\n## Key Findings\n- finding 1"
        )
        try:
            from app.services.agent.native.types import HumanMessage

            response = await llm.generate(messages=[HumanMessage(content=prompt)])
            return response.message.content if hasattr(response, "message") else str(response)
        except LLMError as exc:
            # BudgetExhausted 语义：预算断路必须继续向上传播
            if exc.kind == "budget_exhausted" or "预算耗尽" in str(exc):
                raise
            state["last_failure_time"] = time.time()
            logger.warning(
                "上下文摘要生成失败（%s: %s），%ds 冷却期内不再尝试",
                type(exc).__name__, str(exc)[:200], self.failure_cooldown_s,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            state["last_failure_time"] = time.time()
            logger.warning("上下文摘要生成失败（%s）", exc)
            return None
