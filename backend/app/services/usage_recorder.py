"""直通路径（对外 API Key 网关）的用量记账。

## 为什么需要这个模块

``agent_usage_events`` 的唯一写入点原本在 ``orchestrator._record_usage_event``，
只被 agent 路径（``AgentService.stream_chat``）调用。而对外网关有**三条**
不经过 agent 编排的直通路径：

- ``POST /v1/chat/completions`` 的 ``llm:`` 纯模型分支
- ``POST /v1/messages``（Anthropic 协议）
- ``POST /v1/responses``（OpenAI Responses 协议）

它们的 token **完全不进用量表**，而 ``check_daily_quota`` 读的就是这张表
—— 也就是说这些请求的消耗**不计入日配额**，配额形同虚设。
（``direct.py`` 的模块注释写着"用量仍记账"，那个承诺一直没实现。）

## 归属口径（与 orchestrator 完全一致）

- ``user_id`` = **发起请求的用户**（API Key 所属用户），不是凭据主人。
  用量、额度、聊天记录都归他。
- ``credential_id`` / ``account_label`` = 实际借出的那个账号（审计列）。
  对外接口强制走共享池，所以这里记的是共享号 —— 但这**不参与**统计聚合。

## 与 orchestrator 的字段对齐

两处写入必须长得一样，否则统计口径会出现"网页端算得出、网关算不出"
的窟窿。所以这里刻意复用 ``route.describe_route`` 与
``direct.extract_usage``，而不是另写一套解析。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

_logger = logging.getLogger("usage.recorder")

#: 直通调用没有会话，用这个前缀合成一个稳定的 session_id。
#: ``agent_usage_events.session_id`` 是非空列，不能留 None。
#: 用 ``api:`` 前缀让统计里一眼能分出"这是网关直通的量"。
DIRECT_SESSION_PREFIX = "api:direct"


def _estimate_tokens_from_text(text: str) -> int:
    """按字符数粗估 token（与 orchestrator 的口径保持一致）。

    直通路径拿不到 usage 时用它兜底，但**必须**配合 ``tokens_estimated=True``
    落库 —— 估算值和实际计费混在一张图里，统计就没人敢用了。
    """
    if not text:
        return 0
    # 中英文混排的粗略比例：约 1.5 字符 / token
    return max(1, len(text) // 3)


async def record_direct_usage(
    *,
    user_id: int | None,
    gateway: Any,
    usage: dict[str, int] | None = None,
    model_name: str | None = None,
    response_mode: str = "general",
    session_id: str | None = None,
    latency_ms: int = 0,
    output_text: str = "",
    tool_calls: int = 0,
    tool_names: list[str] | None = None,
) -> bool:
    """记一行直通用量。返回是否真的写进库。

    **记账失败不能影响响应** —— 一次已经成功的对话不该因为统计写不进去
    而对客户端报错。所以这里吞掉异常，只记 WARNING。
    """
    try:
        return await asyncio.to_thread(
            _record_sync,
            user_id=user_id,
            gateway=gateway,
            usage=usage or {},
            model_name=model_name,
            response_mode=response_mode,
            session_id=session_id,
            latency_ms=latency_ms,
            output_text=output_text,
            tool_calls=tool_calls,
            tool_names=tool_names or [],
        )
    except Exception:  # noqa: BLE001 —— 统计失败不该打挂主链路
        _logger.warning("直通用量记账失败", exc_info=True)
        return False


def _record_sync(
    *,
    user_id: int | None,
    gateway: Any,
    usage: dict[str, int],
    model_name: str | None,
    response_mode: str,
    session_id: str | None,
    latency_ms: int,
    output_text: str,
    tool_calls: int,
    tool_names: list[str],
) -> bool:
    from app.db.models import AgentUsageEventModel
    from app.db.session import create_db_session
    from app.services.llm_providers.route import describe_route, resolve_model_name

    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or 0)
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    estimated = total_tokens <= 0
    if estimated:
        estimated_output = _estimate_tokens_from_text(output_text)
        output_tokens = estimated_output
        total_tokens = estimated_output

    route = describe_route(gateway)
    audit_fields = route.audit_fields()
    resolved_model = (
        resolve_model_name(gateway, fallback=model_name) or model_name or "unknown"
    )

    with create_db_session() as db:
        db.add(
            AgentUsageEventModel(
                user_id=user_id,
                agent_profile_id=None,
                session_id=session_id or DIRECT_SESSION_PREFIX,
                model_name=str(resolved_model)[:128],
                response_mode=response_mode,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                llm_calls=1,
                tool_calls=tool_calls,
                tool_names_json="[]" if not tool_names else _dump_json(tool_names),
                latency_ms=max(0, int(latency_ms or 0)),
                tokens_estimated=estimated,
                **audit_fields,
            )
        )
        db.commit()
    return True


def _dump_json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"
