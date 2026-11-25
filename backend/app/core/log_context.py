"""结构化日志上下文（横切优化 2.4：统一结构化日志字段）。

提供 request 级别的上下文字段（request_id / user_id / session_id / path），
通过 logging Filter 把字段注入每条日志记录 —— 业务代码用普通
``logger.info("...")`` 即可，排障时 ``grep request_id=<id>`` 能把一次请求
产生的所有日志（含 Agent 引擎、审批、DB 层）串起来。

用法：
    - 中间件：进入请求时 ``bind_request_context(request_id=..., path=...)``；
    - 业务深处（如 Agent 会话）：``bind_request_context(session_id=sid)``
      增量补字段（同一 contextvar dict，不影响已绑定的 key）；
    - 任何 logger 输出自动携带这些字段（JSON 序列化时是 log_record 上的属性，
      文本格式下以 ``key=value`` 后缀追加）。
"""

from __future__ import annotations

import contextvars
import logging
import uuid
from typing import Any

#: 请求级日志上下文（值是 dict；跨 async 安全，每次请求独立）
_log_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "agenticos_log_context", default=None
)

#: 允许进入日志记录的字段白名单（防任意 key 注入日志管道）
_ALLOWED_KEYS = frozenset({"request_id", "user_id", "session_id", "path", "provider", "model"})


def bind_request_context(**fields: Any) -> dict[str, Any]:
    """增量绑定日志上下文字段（不覆盖既有请求的 request_id）。

    返回当前上下文 dict（通常无需使用）。字段名必须在白名单内。
    """
    ctx = _log_context.get()
    if ctx is None:
        ctx = {}
        _log_context.set(ctx)
    for key, value in fields.items():
        if key in _ALLOWED_KEYS and value is not None:
            ctx[key] = value
    return ctx


def clear_request_context() -> None:
    """请求结束时清理（中间件 finally 调用；contextvar 复用线程时防串号）。"""
    _log_context.set(None)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class RequestContextFilter(logging.Filter):
    """把上下文字段注入 LogRecord：record.request_id 等可直接被 formatter 使用。

    文本格式建议：``%(asctime)s %(levelname)s [%(request_id)s] %(name)s %(message)s``
    未绑定时显示 ``-``，不产生空字段噪声。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _log_context.get() or {}
        for key in _ALLOWED_KEYS:
            setattr(record, key, ctx.get(key, "-"))
        return True


def context_fields() -> dict[str, Any]:
    """当前上下文字段快照（供 OTel span attribute / 审计 detail 复用）。"""
    return dict(_log_context.get() or {})
