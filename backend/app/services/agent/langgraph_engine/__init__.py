"""LangGraph 新引擎适配层（docs/design/wuwei迁移LangChain方案.md 阶段 1-2）。

绞杀者模式（Strangler Fig）：新引擎**插在深缝**——orchestrator 的
``produce_events()`` 只消费 ``agent.stream_events(user_message, session)``
吐出的 wuwei 兼容 ``AgentEvent`` 流。本包用 LangGraph 实现**同一个接口**：

- ``LangGraphAgent``：复刻 wuwei ``Agent`` 的三个被消费面（``_sessions`` /
  ``create_or_get_session`` / ``stream_events``），编排走 LangGraph
  ``create_react_agent``（底层 LangGraph 1.2 Stable）；
- ``GatewayChatModel``：把项目自研的多提供商 ``LLMGateway``（企业 Cookie
  账号池 / 重试 / usage 收尾帧容错）挂到 LangChain ``BaseChatModel`` 接口
  —— 网关资产原样保留，这是迁移方案「网关适配层」的落点；
- ``EngineApprovalPolicy``：把 ``LenientHitlMiddleware`` 的三档审批语义
  （ask/auto/full、拒绝转消息、改参执行、超时按拒绝）移植到工具节点，
  复用同一个 ``ApprovalManager``（Redis pub/sub + DB + SSE 泵不变）；
- 事件直接复用 wuwei ``AgentEvent`` 类型 —— 双轨期与 orchestrator 的
  SSE mapper / trace recorder 逐字节兼容（阶段 5 退役 wuwei 时再换）。

特性开关：``AGENT_ENGINE=langgraph`` 启用（默认 ``wuwei``，秒级可回退）。
"""

from __future__ import annotations

from app.services.agent.langgraph_engine.engine import LangGraphAgent

__all__ = ["LangGraphAgent"]
