"""Agent 引擎适配层（唯一引擎：DeepAgents + LangGraph）。

orchestrator 的 ``produce_events()`` 只消费 ``agent.stream_events(user_message,
session)`` 吐出的 ``AgentEvent`` 流；本包负责把 DeepAgents harness 的输出
转换成同一套事件契约，SSE mapper / trace recorder 无需改动：

- ``LangGraphAgent``：用 ``deepagents.create_deep_agent`` 构建编排图（底层
  LangGraph 1.2 Stable），内置 filesystem / skills / subagents / summarization
  middleware 由 DeepAgents 自身提供；同时保留消费面（``_sessions`` /
  ``create_or_get_session`` / ``stream_events``）；
- ``GatewayChatModel``：把项目自研的多提供商 ``NativeLLMGateway``（企业 Cookie
  账号池 / 重试 / usage 收尾帧容错）挂到 LangChain ``BaseChatModel`` 接口；
- ``EngineApprovalPolicy``：三档审批语义（ask/auto/full、拒绝转消息、改参执行、
  人工代答、超时按拒绝）在工具包装层实现，复用同一个 ``ApprovalManager``；
- 事件类型 ``AgentEvent`` 与 ``agent_messages.message_json`` wire 格式兼容。

历史说明：wuwei 已整体退役（2026-11），AGENT_ENGINE 兼容开关已移除；
本包名保留 ``langgraph_engine`` 仅为兼容历史 import 路径。
"""

from __future__ import annotations

from app.services.agent.langgraph_engine.engine import LangGraphAgent

__all__ = ["LangGraphAgent"]
