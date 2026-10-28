"""兼容层：原单文件 agent_service.py 已拆分为 ``app/services/agent`` 包。

本模块保持既有导入路径与公共 API 零变更：
- ``AgentService`` / ``get_agent_service`` / ``clear_agent_service_cache``
- ``MAX_STEPS_LIMIT_MESSAGE`` / ``ThinkingHistoryCompatibilityMiddleware`` 等符号
- ``_current_session_id`` contextvar（approval_manager、decision_tools、
  knowledge_tools、memory_tools、ppt_tools 等跨模块直接 import 读取，
  定义保留在此处；包内模块通过显式参数/函数级导入使用，不互相读取私有变量）

并发工具执行曾由 agent.factory 里的 AgentRunner.stream_events monkey-patch
实现。wuwei 3.2.1 起上游 ToolExecutor 已原生按 is_concurrency_safe 分批并发
（``execute(tool_calls, concurrent=True)``），补丁已删除 —— 见 factory.py 顶部说明。
"""

import contextvars

# 当前会话 ID，供 ApprovalManager 使用
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)

# 必须先于包导入定义完成（见上），随后导入包以装配 re-export
from app.services.agent.factory import (  # noqa: E402,F401  （re-export）
    MAX_STEPS_LIMIT_MESSAGE,
    SKILL_INSTRUCTION,
    LenientHitlMiddleware,
    SkillInstructionMiddleware,
    ThinkingHistoryCompatibilityMiddleware,
    _CHART_MARKER,
    _REJECTED_TOOL_NAME,
    _TOOL_RESULT_CONTEXT_LIMIT,
    _truncate_for_context,
)
from app.services.agent.service import (  # noqa: E402,F401  （re-export）
    AgentService,
    clear_agent_service_cache,
    get_agent_service,
)

__all__ = [
    # 门面与单例
    "AgentService",
    "get_agent_service",
    "clear_agent_service_cache",
    # 中间件与常量
    "LenientHitlMiddleware",
    "SkillInstructionMiddleware",
    "ThinkingHistoryCompatibilityMiddleware",
    "MAX_STEPS_LIMIT_MESSAGE",
    "SKILL_INSTRUCTION",
    # contextvar（跨模块读取）
    "_current_session_id",
    # 辅助（向后兼容）
    "_truncate_for_context",
    "_REJECTED_TOOL_NAME",
    "_TOOL_RESULT_CONTEXT_LIMIT",
    "_CHART_MARKER",
]
