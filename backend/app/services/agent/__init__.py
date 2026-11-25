"""Agent 服务包（自原 app/services/agent_service.py 拆分，TECH-DEBT-2026-09）。

模块划分：
- factory       AgentFactory：Agent/中间件栈/工具注册表构建 + 并发工具执行补丁
- orchestrator  StreamOrchestrator：stream_chat SSE 编排主循环与队列 fan-out
- artifacts     ArtifactFactory：PPT/website 工件创建与 PPTX 导出
- prompts       PPT/website 目录注入文案（模板存放于 app/resources/prompt_catalogs）
- service       AgentService 门面（组合上述 Mixin，保持公共 API 零变更）

兼容入口：``app.services.agent_service`` 继续 re-export 全部既有公共符号；
``_current_session_id`` 等 contextvar 定义保留在该兼容层模块中。
"""

from typing import Any

__all__ = [
    "AgentService",
    "get_agent_service",
    "clear_agent_service_cache",
]


def __getattr__(name: str) -> Any:
    """惰性导出：避免包初始化时拉起 factory → agent_profile_service →
    tool_config_service 的循环（tool_config_service 模块级代码会反向
    import 本包的 native.tool_registry）。"""
    if name in ("AgentService", "get_agent_service", "clear_agent_service_cache"):
        from app.services.agent import service as _service

        return getattr(_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
