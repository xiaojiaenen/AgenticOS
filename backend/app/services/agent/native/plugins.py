"""插件上下文（自有实现，替代 wuwei.plugin.PluginContext）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.agent.native.tool_registry import ToolRegistry


@dataclass
class PluginContext:
    """builtin 插件 setup(ctx) 的上下文：挂一个工具注册表。"""

    tool_registry: ToolRegistry
    workspace: str = "."
