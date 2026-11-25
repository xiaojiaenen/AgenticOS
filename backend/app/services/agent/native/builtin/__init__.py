"""内置插件（自 wuwei builtin 逐字移植，仅替换注册上下文）。"""

from app.services.agent.native.builtin import (
    calc,
    decision,
    file,
    git,
    http,
    json_tools,
    npm,
    python,
    text,
    time,
)

PLUGIN_MAP = {
    "calc": calc,
    "time": time,
    "file": file,
    "git": git,
    "npm": npm,
    "python": python,
    "decision": decision,
    "json": json_tools,
    "http": http,
    "text": text,
}

__all__ = ["PLUGIN_MAP"]
