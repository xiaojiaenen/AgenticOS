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

from app.services.agent.service import (
    AgentService,
    clear_agent_service_cache,
    get_agent_service,
)

__all__ = [
    "AgentService",
    "get_agent_service",
    "clear_agent_service_cache",
]
