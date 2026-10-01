"""当前用户/会话的 contextvars（供工具 handler 运行时动态读取）。"""

from __future__ import annotations

import contextvars

# ── context vars for current user (like email_tools pattern) ────────────────

_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("ext_current_user_id", default=0)
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("ext_current_session_id", default="")


def set_ext_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)


def get_ext_user_id() -> int:
    return _current_user_id.get()
