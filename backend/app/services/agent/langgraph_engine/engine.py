"""DeepAgents 编排引擎（全新系统核心，wuwei 已退役）。

``LangGraphAgent`` 是唯一的 Agent 引擎，保留被消费面：

1. ``_sessions: dict[session_id, AgentSession]``（orchestrator 做会话加载）；
2. ``create_or_get_session(...)``（自有 ``AgentSession``）；
3. ``stream_events(user_message, session)`` —— 异步生成器，吐出 ``AgentEvent``。

编排走 DeepAgents ``create_deep_agent``（底层 LangGraph）。差异化语义内建：

- **工具配对修复**：残缺历史补失败结果、删孤立结果；
- **思考历史兼容**：剔除步数上限合成回复，适配 provider 思考模式；
- **HITL 审批**（EngineApprovalPolicy，工具包装层）：ask/auto/full 三档 +
  四决策，真实 tool_call_id 由 ToolRuntime 注入；
- **预算断路**（自研 Budget，DeepAgents 无等价计费语义）；
- **工具输出截断**（MAX_TOOL_OUTPUT_CHARS）；
- **max_steps 步数上限**：截断时写入合成回复（下一轮被 thinking-compat 剔除）。

文件 / Skill / 上下文压缩 / 子代理已由 DeepAgents 内置 middleware 接管
（FilesystemBackend，bound 到 data/），本模块只做适配与差异化语义。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from app.services.agent.native.async_sub_agent import MAX_STEPS_LIMIT_MESSAGE
from app.services.agent.native.budget import Budget, check_budget, estimate_cost
from app.services.agent.native.context_compression import ContextCompressor
from app.services.agent.native.tool_registry import ToolRegistry

from app.services.agent.langgraph_engine.chat_model import GatewayChatModel
from app.services.agent.langgraph_engine.tools_adapter import (
    MAX_TOOL_OUTPUT_CHARS,
    registry_to_langchain_tools,
)

_logger = logging.getLogger("agenticos.langgraph.engine")


def _agent_event(event_type: str, session_id: str, step: int, data: dict[str, Any]) -> Any:
    from app.services.agent.native.types import AgentEvent

    return AgentEvent(type=event_type, session_id=session_id, step=step, data=data)


class _UsageTracker:
    """单次 run 的用量/延迟/调用数收集（done 事件 + 预算断路）。"""

    def __init__(self) -> None:
        self.llm_calls = 0
        self.latency_ms = 0
        self.usage: dict[str, int] = {}
        self.usage_available = True
        # 软阈值告警每 run 只打一次（原 self._budget_warned 从未回写，导致刷屏）
        self.budget_warned = False

    def record_llm_call(self, *, latency_ms: int, usage_emitted: bool) -> None:
        self.llm_calls += 1
        self.latency_ms += latency_ms
        if not usage_emitted:
            self.usage_available = False

    def add_usage(self, usage: dict[str, Any] | None) -> None:
        if not isinstance(usage, dict):
            return
        for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                self.usage[key] = self.usage.get(key, 0) + int(value)

    def snapshot(self) -> dict[str, int]:
        total = self.usage.get(
            "total_tokens",
            self.usage.get("input_tokens", 0) + self.usage.get("output_tokens", 0),
        )
        input_tokens = self.usage.get("input_tokens", self.usage.get("prompt_tokens", 0))
        output_tokens = self.usage.get("output_tokens", self.usage.get("completion_tokens", 0))
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            # LLM 网关原生键名：budget.estimate_cost 与部分 provider 都读这一组
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total,
        }


class LangGraphAgent:
    """唯一的 Agent 引擎（DeepAgents create_deep_agent / 底层 LangGraph）。"""

    def __init__(
        self,
        *,
        llm: Any,
        tools: ToolRegistry,
        default_system_prompt: str = "你是一个有用的助手",
        default_max_steps: int = 10,
        default_parallel_tool_calls: bool = False,
        approval_policy: Any = None,
        model_name: str = "",
        skill_toolbox: Any | None = None,  # deprecated: DeepAgents SkillsMiddleware 替代
        async_sub_agents: Any | None = None,  # deprecated: DeepAgents SubAgentMiddleware 替代
        budget: Budget | None = None,  # 保留：DeepAgents 无计费语义
        compressor: ContextCompressor | None = None,  # deprecated: DeepAgents summarization 替代
        max_output_chars: int = MAX_TOOL_OUTPUT_CHARS,
        # DeepAgents 内置能力（backend / skills / subagents / summarization）
        deepagents_backend: Any | None = None,
        deepagents_skills: list[str] | None = None,
        deepagents_subagents: list[dict] | None = None,
        deepagents_memory: list[str] | None = None,
        deepagents_permissions: list[Any] | None = None,
        deepagents_middleware: list[Any] | None = None,
    ) -> None:
        self.llm = llm
        self.tool_registry = tools
        self.default_system_prompt = default_system_prompt
        self.default_max_steps = int(default_max_steps)
        self.default_parallel_tool_calls = bool(default_parallel_tool_calls)
        self.approval_policy = approval_policy
        self.model_name = model_name
        self.skill_toolbox = skill_toolbox
        self.async_sub_agents = async_sub_agents
        self.budget = budget
        self.compressor = compressor
        self.max_output_chars = int(max_output_chars)
        self._deepagents_backend = deepagents_backend
        self._deepagents_skills = deepagents_skills
        self._deepagents_subagents = deepagents_subagents
        self._deepagents_memory = deepagents_memory
        self._deepagents_permissions = deepagents_permissions
        self._deepagents_middleware = deepagents_middleware
        self._sessions: dict[str, Any] = {}
        self._skill_injected: set[str] = set()

        self._lc_tools = registry_to_langchain_tools(tools, approval_policy)
        self._chat_model = GatewayChatModel(gateway=llm, model_name=model_name)
        # 图延迟到首次 stream 时构建：AsyncSqliteSaver 必须在事件循环里创建，
        # 且 checkpointer 绑定 loop —— 每个事件循环一个 (graph, checkpointer)。
        self._graphs: dict[Any, Any] = {}
        self._checkpointers: dict[Any, Any] = {}

    def _build_graph(self, checkpointer: Any | None) -> Any:
        """用给定 checkpointer 构建 DeepAgents 图（每 loop 一次）。"""
        from deepagents import create_deep_agent

        graph_kwargs: dict[str, Any] = {
            "model": self._chat_model,
            "tools": self._lc_tools,
            "interrupt_on": None,  # 审批仍走 EngineApprovalPolicy（工具包装层），保留真实 tool_call_id
        }
        if self._deepagents_backend is not None:
            graph_kwargs["backend"] = self._deepagents_backend
        if self._deepagents_skills:
            graph_kwargs["skills"] = self._deepagents_skills
        if self._deepagents_subagents:
            graph_kwargs["subagents"] = self._deepagents_subagents
        if self._deepagents_memory:
            graph_kwargs["memory"] = self._deepagents_memory
        if self._deepagents_permissions:
            graph_kwargs["permissions"] = self._deepagents_permissions
        if self._deepagents_middleware:
            graph_kwargs["middleware"] = self._deepagents_middleware
        if checkpointer is not None:
            graph_kwargs["checkpointer"] = checkpointer
        return create_deep_agent(**graph_kwargs)

    async def _graph_for_current_loop(self) -> tuple[Any, Any | None]:
        """当前事件循环的 (graph, checkpointer)，首次调用时惰性构建。"""
        import asyncio

        loop = asyncio.get_running_loop()
        graph = self._graphs.get(loop)
        if graph is not None:
            return graph, self._checkpointers.get(loop)
        from app.services.agent.checkpointer import get_async_checkpointer

        cp = await get_async_checkpointer()
        graph = self._build_graph(cp)
        self._graphs[loop] = graph
        self._checkpointers[loop] = cp
        return graph, cp

    # ── 会话管理（被消费面）────────────────────────────────────────────

    def create_session(
        self,
        session_id: str | None = None,
        system_prompt: str | None = None,
        max_steps: int | None = None,
        parallel_tool_calls: bool | None = None,
    ) -> Any:
        from app.services.agent.native.types import AgentSession

        session = AgentSession(
            session_id=session_id or str(uuid.uuid4()),
            system_prompt=system_prompt or self.default_system_prompt,
            max_steps=max_steps or self.default_max_steps,
            parallel_tool_calls=(
                self.default_parallel_tool_calls if parallel_tool_calls is None else bool(parallel_tool_calls)
            ),
        )
        self._sessions[session.session_id] = session
        return session

    def create_or_get_session(
        self,
        session_id: str | None = None,
        system_prompt: str | None = None,
        max_steps: int | None = None,
        parallel_tool_calls: bool | None = None,
    ) -> Any:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create_session(session_id, system_prompt, max_steps, parallel_tool_calls)

    def stream_events(
        self,
        user_input: str,
        session: Any = None,
        session_id: str | None = None,
    ) -> AsyncIterator[Any]:
        """sync def 返回 async generator（消费面契约）。"""
        return self._stream_events(user_input, session, session_id)

    async def _stream_events(
        self,
        user_input: str,
        session: Any = None,
        session_id: str | None = None,
    ) -> AsyncIterator[Any]:
        if session is None:
            session = self.create_or_get_session(session_id)
        sid = session.session_id
        step = 0
        tracker = _UsageTracker()
        run_started = time.monotonic()

        yield _agent_event("run_start", sid, 0, {})

        # ── 预处理管线（作用于自有消息历史）────────────────────────────
        history = self._repair_tool_pairs(list(session.context.get_messages()))

        # 思考历史兼容：剔除上一轮截断时写入的步数上限合成回复
        step_limit_msg = MAX_STEPS_LIMIT_MESSAGE.format(max_steps=session.max_steps)
        history = [
            m
            for m in history
            if not (
                m.role == "assistant"
                and m.content.strip() == step_limit_msg
                and not m.reasoning_content
                and not m.tool_calls
            )
        ]
        session.context.replace_messages(history)

        # Skill 指令注入（每会话一次，并入首条 system 保持唯一性）
        if self.skill_toolbox is not None:
            instruction = self.skill_toolbox.instruction_text()
            if instruction and sid not in self._skill_injected:
                if not any(m.role == "system" for m in history):
                    history.insert(0, session.context.get_messages()[0] if session.context.get_messages() else None)
                    if history[0] is None:
                        history.pop(0)
                head = next((m for m in history if m.role == "system"), None)
                if head is not None:
                    head.content = f"{head.content}\n\n{instruction}" if head.content else instruction
                else:
                    from app.services.agent.native.types import SystemMessage

                    history.insert(0, SystemMessage(content=instruction))
                session.context.replace_messages(history)
                self._skill_injected.add(sid)

        # 上下文压缩（原 ContextCompressionMiddleware，压缩后再取历史）
        if self.compressor is not None:
            compressed = await self.compressor.compress_if_needed_full(
                list(session.context.get_messages()), session, self.llm
            )
            session.context.replace_messages(compressed)

        # 压缩后重建 lc 历史（含本轮用户输入）
        lc_history = self._to_lc(list(session.context.get_messages()))
        if not any(m.type == "system" for m in lc_history):
            lc_history.insert(0, SystemMessage(content=session.system_prompt or self.default_system_prompt))
        lc_history.append(HumanMessage(content=user_input))
        # 本轮用户输入进会话上下文（持久化契约；压缩后的历史不含它）
        self._append_user_message(session, user_input)

        graph, cp = await self._graph_for_current_loop()
        recursion_limit = max(8, int(getattr(session, "max_steps", self.default_max_steps)) * 2 + 4)
        config = {"recursion_limit": recursion_limit}
        # 阶段 2A：checkpointer 用 thread_id 做会话隔离（官方约定）。
        if cp is not None:
            config["configurable"] = {"thread_id": session.session_id}
        max_steps = int(getattr(session, "max_steps", self.default_max_steps))
        truncated = False
        had_error = False
        produced: list[Any] = []

        self._chat_model._usage_tracker = tracker  # noqa: SLF001 —— 每 run 挂 tracker

        try:
            async for mode, payload in graph.astream(
                {"messages": lc_history}, config=config, stream_mode=["updates", "messages"]
            ):
                if mode == "messages":
                    chunk, _meta = payload
                    if isinstance(chunk, AIMessageChunk):
                        content = chunk.content
                        if isinstance(content, str) and content:
                            yield _agent_event("text_delta", sid, step, {"content": content})
                        reasoning = (chunk.additional_kwargs or {}).get("reasoning_content")
                        if reasoning:
                            tracker.add_usage((chunk.additional_kwargs or {}).get("usage"))
                            yield _agent_event("reasoning_delta", sid, step, {"content": reasoning})
                    continue

                # updates 模式：节点完成 → AIMessage（工具调用）/ ToolMessage（结果）
                for _node, update in (payload or {}).items():
                    messages = update.get("messages") if isinstance(update, dict) else update
                    if not isinstance(messages, list):
                        messages = [messages]
                    for message in messages:
                        if isinstance(message, (AIMessage, ToolMessage)):
                            produced.append(message)
                        if isinstance(message, AIMessage):
                            usage = (message.additional_kwargs or {}).get("usage") or (
                                message.response_metadata or {}
                            ).get("usage")
                            tracker.add_usage(usage)
                            # 预算检查放在每次 AIMessage 产出后（无论是否带
                            # tool_calls）：纯文本回答同样累计 usage，此前只在
                            # 工具调用分支检查会让单次长回答绕过 token/cost 上限。
                            if self.budget is not None:
                                check_budget(
                                    self.budget,
                                    tracker.snapshot(),
                                    tracker.llm_calls,
                                    self._spend(tracker),
                                    usage_available=tracker.usage_available,
                                )
                            if message.tool_calls:
                                step += 1
                                for call in message.tool_calls:
                                    tool = self.tool_registry.get(str(call.get("name") or ""))
                                    metadata = (
                                        {
                                            "side_effect": bool(getattr(tool.execution, "side_effect", False)),
                                            "requires_approval": bool(getattr(tool.execution, "requires_approval", False)),
                                        }
                                        if getattr(tool, "execution", None)
                                        else {}
                                    )
                                    yield _agent_event(
                                        "tool_start",
                                        sid,
                                        step,
                                        {
                                            "tool_call_id": str(call.get("id") or ""),
                                            "tool_name": str(call.get("name") or ""),
                                            "args": call.get("args") or {},
                                            "display_name": (
                                                (getattr(tool, "display_name", None) or str(call.get("name") or ""))
                                                if tool
                                                else str(call.get("name") or "")
                                            ),
                                            **metadata,
                                        },
                                    )
                        elif isinstance(message, ToolMessage):
                            ok_payload = self._parse_tool_status(message.content)
                            data = {
                                "tool_call_id": str(message.tool_call_id or ""),
                                "tool_name": str(message.name or ""),
                                "output": message.content,
                            }
                            if ok_payload == "error":
                                yield _agent_event(
                                    "tool_error",
                                    sid,
                                    step,
                                    {
                                        **data,
                                        "message": self._error_message(message.content),
                                        "error_type": "tool_error",
                                    },
                                )
                            else:
                                yield _agent_event("tool_end", sid, step, data)
        except GraphRecursionError:
            truncated = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 异常翻成 error 事件
            had_error = True
            yield _agent_event(
                "error",
                sid,
                step,
                {"message": str(exc), "error_type": type(exc).__name__},
            )

        # graph 产生的消息同步回自有会话上下文（持久化契约）
        self._sync_context(session, produced)

        # max_steps 截断：写入合成回复（下一轮被 thinking-compat 剔除）
        if truncated:
            final_content = MAX_STEPS_LIMIT_MESSAGE.format(max_steps=max_steps)
            session.context.add_ai_message(final_content)
            yield _agent_event("text_delta", sid, step, {"content": final_content})

        if not had_error:
            yield _agent_event(
                "done",
                sid,
                step,
                {
                    "reason": "length" if truncated else "stop",
                    "usage": tracker.snapshot(),
                    "latency_ms": int((time.monotonic() - run_started) * 1000),
                    "llm_calls": tracker.llm_calls,
                    "model": self.model_name,
                },
            )

        # 最后用量写回会话（orchestrator session_payload 读取）
        session.last_usage = tracker.snapshot()
        session.last_latency_ms = int((time.monotonic() - run_started) * 1000)
        session.last_llm_calls = tracker.llm_calls

    # ── 会话上下文同步 ───────────────────────────────────────────────────

    def _to_lc(self, messages: list) -> list[Any]:
        """自有消息 → LangChain 消息。"""
        out: list[Any] = []
        for msg in messages:
            if msg.role == "assistant":
                tool_calls = [
                    {
                        "name": call.function.name,
                        "args": call.function.arguments if isinstance(call.function.arguments, dict) else {},
                        "id": call.id,
                    }
                    for call in msg.tool_calls
                ]
                ai = AIMessage(content=msg.content)
                if tool_calls:
                    ai.tool_calls = tool_calls
                if msg.reasoning_content:
                    ai.additional_kwargs["reasoning_content"] = msg.reasoning_content
                out.append(ai)
            elif msg.role == "tool":
                out.append(
                    ToolMessage(content=msg.content, tool_call_id=msg.tool_call_id or "", name=msg.name or "")
                )
            elif msg.role == "system":
                out.append(SystemMessage(content=msg.content))
            else:
                out.append(HumanMessage(content=msg.content))
        return out

    def _sync_context(self, session: Any, produced: list[Any]) -> None:
        """graph 产生的 LC 消息转回自有消息追加进 session.context。

        ``produced`` 只含 graph 新生成的 AIMessage / ToolMessage —— 用户消息
        已在 stream 开头追加，历史段本来就在上下文里，都不重复。
        """
        from app.services.agent.native.types import (
            AIMessage as NativeAIMessage,
            FunctionCall,
            ToolCall as NativeToolCall,
            ToolMessage as NativeToolMessage,
        )

        context = getattr(session, "context", None)
        if context is None or not produced:
            return
        for msg in produced:
            if isinstance(msg, AIMessage):
                ai = NativeAIMessage(content=msg.content if isinstance(msg.content, str) else str(msg.content))
                # 思考内容必须同步进 session.context，否则 model_dump_json(
                # exclude_none=True) 落库时 reasoning_content 为 null —— 用户
                # 刷新后思考永久消失（实时 SSE 正常，掩盖了这个写入端回归）。
                # 与 chat_model.lc_to_native_messages 保持同一取法。
                reasoning = (msg.additional_kwargs or {}).get("reasoning_content")
                if reasoning:
                    ai.reasoning_content = reasoning
                for call in msg.tool_calls or []:
                    ai.tool_calls.append(
                        NativeToolCall(
                            id=str(call.get("id") or ""),
                            function=FunctionCall(
                                name=str(call.get("name") or ""),
                                arguments=call.get("args") if isinstance(call.get("args"), dict) else {},
                            ),
                        )
                    )
                context._messages.append(ai)
            elif isinstance(msg, ToolMessage):
                # 落库工具结果的成功/失败态：前端 mapper 按 metadata.tool_outcome
                # 还原刷新后的工具状态。不带的话一律显示 success，刷新后红色
                # 失败工具会"变绿"（实时 SSE 正常，掩盖了这个写入端遗漏）。
                outcome = self._parse_tool_status(msg.content)
                context._messages.append(
                    NativeToolMessage(
                        content=msg.content if isinstance(msg.content, str) else str(msg.content),
                        tool_call_id=str(msg.tool_call_id or ""),
                        name=str(msg.name or ""),
                        # status 列单独落库（append_messages_batch 取 msg.status），
                        # 不设的话默认是 "success" —— 刷新后 metadata.tool_outcome
                        # 会被读回端的 status 列无条件覆盖成 success（失败工具"变绿"）。
                        status=outcome,
                        metadata={"tool_outcome": {"status": outcome}},
                    )
                )
        _logger.debug("langgraph: synced %d produced messages to session %s", len(produced), session.session_id)

    def _append_user_message(self, session: Any, content: str) -> None:
        context = getattr(session, "context", None)
        if context is None:
            return
        context.add_user_message(content)

    # ── 预算 ────────────────────────────────────────────────────────────

    def _spend(self, tracker: _UsageTracker) -> Any:
        from app.services.agent.native.budget import RunSpend

        # 每个 run 复用同一个 RunSpend：check_budget 会把软阈值告警标记写到
        # spend.warned 上，若每次新建就永远读不到，导致 80% 告警重复刷屏。
        if getattr(tracker, "_spend", None) is None:
            tracker._spend = RunSpend(model=self.model_name, warned=False, cost_usd=0.0)
        tracker._spend.cost_usd = estimate_cost(tracker.snapshot(), self.model_name)
        return tracker._spend

    # ── 工具结果解析 ────────────────────────────────────────────────────

    # LangGraph / ToolNode 在工具参数 schema 校验失败、handler 抛异常时，
    # 给出的不是 JSON，而是形如
    #   "Error invoking tool 'ls' with kwargs {} with error:\n path: Field required"
    # 的纯文本。此前只认 `ok:false` → 这类失败被判成 success 落库，
    # 刷新后前端把失败工具显示成绿色「已完成」（用户实测遇到）。
    _TOOL_ERROR_TEXT_MARKERS = (
        "error invoking tool",
        "tool invocation error",
        "field required",
        "validation error",
        "tool not found",
    )

    @staticmethod
    def _parse_tool_status(content: Any) -> str:
        """ok:false / 纯文本工具错误 → error（orchestrator 同口径）。"""
        if isinstance(content, str):
            lowered = content.strip().lower()
            # LangGraph ToolNode 的校验/调用失败文本
            if any(marker in lowered for marker in LangGraphAgent._TOOL_ERROR_TEXT_MARKERS):
                return "error"
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return "success"
        else:
            payload = content
        if isinstance(payload, dict) and payload.get("ok") is False:
            return "error"
        return "success"

    @staticmethod
    def _error_message(content: Any) -> str:
        if isinstance(content, str):
            try:
                payload = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                return content[:500]
        else:
            payload = content
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)
            return str(payload.get("message") or payload)[:500]
        return str(payload)[:500]

    # ── 历史修复（原 ToolPairRepairMiddleware）──────────────────────────

    _MISSING_RESULT = (
        "该工具调用没有返回结果（可能被取消、超时、等待审批未通过，"
        "或达到步数上限）。请根据已有信息判断下一步，不要假设它成功。"
    )

    def _repair_tool_pairs(self, messages: list) -> list:
        """补齐/清理 tool_calls 与 tool 消息配对（DeepSeek 等端点硬约束）。"""
        if not messages:
            return messages

        answered = {str(m.tool_call_id) for m in messages if m.role == "tool" and m.tool_call_id}
        declared: list[str] = []
        missing_names: dict[str, str] = {}
        for message in messages:
            if message.role != "assistant":
                continue
            for call in message.tool_calls or []:
                if not call.id:
                    continue
                declared.append(str(call.id))
                missing_names[str(call.id)] = call.function.name or "unknown"

        declared_set = set(declared)
        missing = [cid for cid in declared if cid not in answered]
        orphans = [cid for cid in answered if cid not in declared_set]
        if not missing and not orphans:
            return messages

        _logger.warning("修复历史配对：补 %d 条缺失工具结果，删 %d 条孤立结果", len(missing), len(orphans))

        repaired: list = []
        for message in messages:
            if message.role == "tool" and message.tool_call_id and str(message.tool_call_id) in orphans:
                continue
            repaired.append(message)
            if message.role != "assistant":
                continue
            pending_ids = [str(c.id) for c in message.tool_calls or [] if str(c.id) in missing]
            for call_id in pending_ids:
                from app.services.agent.native.types import ToolMessage

                repaired.append(
                    ToolMessage(
                        content=self._MISSING_RESULT,
                        tool_call_id=call_id,
                        name=missing_names.get(call_id, "unknown"),
                    )
                )
        return repaired
