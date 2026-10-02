"""AgentFactory：Agent 实例 / 中间件栈 / 工具注册表的构建。

从原 ``app/services/agent_service.py`` 整段搬移（TECH-DEBT-2026-09 拆分）：
- AgentRunner.stream_events 并发工具执行 monkey-patch（模块导入时应用，时机不变）
- LenientHitlMiddleware / SkillInstructionMiddleware / ThinkingHistoryCompatibilityMiddleware
- _build_tool_registry / _build_middleware_stack / _get_agent / _build_async_sub_agents

本类为 Mixin：由 ``service.AgentService`` 组合继承，依赖宿主提供的属性
（self.settings / self.approval_manager / self._agents Agent 缓存）。
"""

import asyncio
import json
import logging

from wuwei import Agent, FileSystemSkillProvider, SkillManager
from wuwei.llm import LLMGateway
from app.services.approval_policy import (
    is_read_only_tool,
    normalize_approval_mode,
)
from wuwei.middleware import (
    Middleware,
    MiddlewareContext,
    MiddlewareStack,
    ContextCompressionMiddleware,
    HitlMiddleware,
    LoggingMiddleware,
)
from wuwei.tools import ToolRegistry
from wuwei.plugin import PluginContext
from wuwei.plugin.builtin.skill import setup as setup_skill_plugin
from wuwei.core.message import ToolCall
from wuwei.agent.async_sub_agent import AsyncSubAgent, AsyncSubAgentMiddleware
from wuwei.runtime.agent_runner import AgentRunner

from app.services.agent_profile_service import RuntimeAgentProfile
from app.services.tool_config_service import TOOL_CATALOG

_logger = logging.getLogger("agent")

# 特殊工具名：用户拒绝时替换原工具调用，让 LLM 收到明确的拒绝消息
_REJECTED_TOOL_NAME = "__tool_rejected__"

# 工具结果截断：超过此字符数的结果在送入 LLM 上下文时会被截断（约 25000 tokens）
_TOOL_RESULT_CONTEXT_LIMIT = 100000
_CHART_MARKER = "__ECHART_JSON__"

MAX_STEPS_LIMIT_MESSAGE = "任务未完成，已达到最大步骤限制。"

SKILL_INSTRUCTION = (
    "你有可用的 Skill（专门技能），它们是处理特定领域任务的增强能力。\n"
    "遇到可能匹配的请求时，调用 `list_skills` 查看可用技能摘要。\n"
    "如果某个技能描述与用户任务相关，调用 `load_skill` 加载其完整指令并遵循执行。\n"
    "技能正文已包含核心知识，**不要逐个读取 references 文件**，除非正文明确要求读取某个具体文件。\n"
    "references 是补充资料，不是必须全部加载的。"
)


def _truncate_for_context(content: str) -> str:
    """截断工具结果用于 LLM 上下文，保留图表标记，添加截断提示。"""
    if not content:
        return content

    # 保留图表标记完整
    if _CHART_MARKER in content:
        return content

    if len(content) <= _TOOL_RESULT_CONTEXT_LIMIT:
        return content

    # 截断并添加提示
    truncated = content[:_TOOL_RESULT_CONTEXT_LIMIT]
    return f"{truncated}\n\n[结果已截断，原始数据共 {len(content)} 字符，仅展示前 {_TOOL_RESULT_CONTEXT_LIMIT} 字符]"

# ── 并发工具执行补丁 ──────────────────────────────────────────────────
# wuwei 的 AgentRunner 默认逐个执行工具调用。
# 本补丁将安全工具（is_concurrency_safe=True）分批并发执行，
# 非安全工具仍保持顺序串行。对前端 SSE 事件流完全透明。

_original_stream_events = AgentRunner.stream_events


async def _patched_stream_events(self, user_input: str, *, task=None):
    """并发版 stream_events：安全工具用 asyncio.gather 并行，其余与原版相同。

    与原始实现的唯一区别：工具执行阶段按 is_concurrency_safe 分批并发。
    LLM 调用、中间件生命周期、事件格式完全不变。

    TECH-DEBT: 等待 wuwei 上游支持并发工具批处理后移除。
    """
    import time
    from collections.abc import AsyncIterator
    from uuid import uuid4
    from wuwei.core.message import AIMessage as AIMsg, ToolMessage as TMsg
    from wuwei.llm import LLMResponseChunk, Message
    from wuwei.middleware.base import MiddlewareContext

    step_count = 0
    llm_calls = 0
    total_latency_ms = 0
    total_usage = self._empty_usage()
    run_id = uuid4().hex
    context = self.session.context
    context.add_user_message(user_input)
    yield self._build_event("run_start", step=0, run_id=run_id, data={"input": user_input})

    ctx = None  # Pre-initialize for exception handler
    try:
        while step_count < self.session.max_steps:
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            full_tool_calls = None
            messages = self._copy_messages()
            tools = list(self.tools)

            # --- before_llm 中间件 ---
            ctx = MiddlewareContext(state=None, config={}, step=step_count)
            ctx.state = type('State', (), {'messages': messages, 'metadata': {}})()
            ctx = await self.middleware.execute_before_llm(ctx)
            messages = ctx.state.messages

            llm_start = time.monotonic()
            yield self._build_event(
                "llm_start", step=step_count, run_id=run_id,
                data={"tools": [tool.name for tool in tools]},
            )

            stream: AsyncIterator[LLMResponseChunk] = await self.llm.generate(
                messages, tools=tools, stream=True,
            )
            llm_calls += 1

            async for chunk in stream:
                if chunk.reasoning_content:
                    reasoning_parts.append(chunk.reasoning_content)
                    yield self._build_event(
                        "reasoning_delta", step=step_count, run_id=run_id,
                        data={"content": chunk.reasoning_content},
                    )
                if chunk.content:
                    content_parts.append(chunk.content)
                    yield self._build_event(
                        "text_delta", step=step_count, run_id=run_id,
                        data={"content": chunk.content},
                    )
                self._merge_usage(total_usage, chunk.usage)
                if chunk.tool_calls_complete:
                    full_tool_calls = chunk.tool_calls_complete

            total_latency_ms += int((time.monotonic() - llm_start) * 1000)
            yield self._build_event(
                "llm_end", step=step_count, run_id=run_id,
                data={"latency_ms": total_latency_ms, "usage": dict(total_usage), "has_tool_calls": bool(full_tool_calls)},
            )

            # 构建 AIMessage 并调用 after_llm 中间件
            ai_msg = AIMsg(
                content="".join(content_parts),
                tool_calls=full_tool_calls or [],
                reasoning_content="".join(reasoning_parts) or None,
            )
            ctx = await self.middleware.execute_after_llm(ctx, ai_msg)
            context.add_ai_message(
                "".join(content_parts),
                tool_calls=full_tool_calls,
                reasoning_content="".join(reasoning_parts) or None,
            )

            if full_tool_calls:
                # ── 并发工具执行 ──
                # 按 is_concurrency_safe 分组：连续安全工具并发，非安全工具串行
                batches: list[list] = []
                current_batch: list = []
                current_safe = True

                for tc in full_tool_calls:
                    tool_obj = self.tool_executor.registry.get(tc.function.name)
                    is_safe = tool_obj.is_concurrency_safe if tool_obj else True

                    if not current_batch:
                        current_batch = [tc]
                        current_safe = is_safe
                    elif is_safe == current_safe:
                        current_batch.append(tc)
                    else:
                        batches.append(current_batch)
                        current_batch = [tc]
                        current_safe = is_safe
                if current_batch:
                    batches.append(current_batch)

                for batch in batches:
                    tool_obj = self.tool_executor.registry.get(batch[0].function.name)
                    is_safe = tool_obj.is_concurrency_safe if tool_obj else True

                    if is_safe and len(batch) > 1:
                        # ── 并发执行安全工具 ──
                        async def _exec_safe(tc):
                            modified = await self.middleware.execute_before_tool(ctx, tc)
                            if modified is None:
                                return None
                            t = self.tool_executor.registry.get(modified.function.name)
                            start_evt = self._build_event(
                                "tool_start", step=step_count, run_id=run_id,
                                data={
                                    "tool_name": modified.function.name,
                                    "display_name": t.display_name if t else None,
                                    "args": modified.function.arguments,
                                    "tool_call_id": modified.id,
                                },
                            )
                            msg = await self._execute_one_tool_call(modified, step=step_count, task=task, run_id=run_id)
                            tmsg = TMsg(content=msg.content or "", tool_call_id=msg.tool_call_id or "", name=msg.name or "")
                            modified_msg = await self.middleware.execute_after_tool(ctx, tmsg)
                            final_msg = Message(role="tool", content=modified_msg.content or "", tool_call_id=modified_msg.tool_call_id, name=modified_msg.name)
                            end_evt = self._build_event(
                                "tool_end", step=step_count, run_id=run_id,
                                data={"tool_name": modified.function.name, "tool_call_id": modified.id, "output": final_msg.content},
                            )
                            return (modified, final_msg, start_evt, end_evt)

                        results = await asyncio.gather(
                            *(_exec_safe(tc) for tc in batch),
                            return_exceptions=True,
                        )
                        for result in results:
                            if isinstance(result, Exception):
                                _logger.error(f"Concurrent tool error: {result}")
                                continue
                            if result is None:
                                continue
                            tc, final_msg, start_evt, end_evt = result
                            yield start_evt
                            self.session.context.add_tool_message(_truncate_for_context(final_msg.content or ""), final_msg.tool_call_id)
                            yield end_evt
                            err = self.tool_executor.extract_error_message(final_msg.content)
                            if err:
                                yield self._build_event(
                                    "error", step=step_count, run_id=run_id,
                                    data={"message": err, "tool_name": tc.function.name, "tool_call_id": tc.id},
                                )
                    else:
                        # ── 串行执行非安全工具或单个工具 ──
                        for tc in batch:
                            modified = await self.middleware.execute_before_tool(ctx, tc)
                            if modified is None:
                                continue
                            t = self.tool_executor.registry.get(modified.function.name)
                            yield self._build_event(
                                "tool_start", step=step_count, run_id=run_id,
                                data={
                                    "tool_name": modified.function.name,
                                    "display_name": t.display_name if t else None,
                                    "args": modified.function.arguments,
                                    "tool_call_id": modified.id,
                                },
                            )
                            tool_message = await self._execute_one_tool_call(modified, step=step_count, task=task, run_id=run_id)
                            tmsg = TMsg(content=tool_message.content or "", tool_call_id=tool_message.tool_call_id or "", name=tool_message.name or "")
                            modified_msg = await self.middleware.execute_after_tool(ctx, tmsg)
                            tool_message = Message(role="tool", content=modified_msg.content or "", tool_call_id=modified_msg.tool_call_id, name=modified_msg.name)
                            self.session.context.add_tool_message(_truncate_for_context(tool_message.content or ""), tool_message.tool_call_id)
                            yield self._build_event(
                                "tool_end", step=step_count, run_id=run_id,
                                data={"tool_name": modified.function.name, "tool_call_id": modified.id, "output": tool_message.content},
                            )
                            err = self.tool_executor.extract_error_message(tool_message.content)
                            if err:
                                yield self._build_event(
                                    "error", step=step_count, run_id=run_id,
                                    data={"message": err, "tool_name": modified.function.name, "tool_call_id": modified.id},
                                )

                step_count += 1
                continue

            # 无工具调用 → 结束
            done_event = self._build_event(
                "done", step=step_count, run_id=run_id,
                data={"usage": dict(total_usage), "latency_ms": total_latency_ms, "llm_calls": llm_calls},
            )
            yield done_event
            yield self._build_event("run_end", step=step_count, run_id=run_id, data=dict(done_event.data))
            self._set_session_run_stats(usage=total_usage, latency_ms=total_latency_ms, llm_calls=llm_calls)
            return

        # 达到最大步数
        context.add_ai_message("任务未完成，已达到最大步骤限制。")
        yield self._build_event(
            "done", step=step_count, run_id=run_id,
            data={"reason": "max_steps", "usage": dict(total_usage), "latency_ms": total_latency_ms, "llm_calls": llm_calls},
        )
        self._set_session_run_stats(usage=total_usage, latency_ms=total_latency_ms, llm_calls=llm_calls)

    except Exception as exc:
        await self.middleware.execute_on_error(ctx if ctx is not None else MiddlewareContext(state=None, config={}, step=step_count), exc)
        yield self._build_event(
            "error", step=step_count, run_id=run_id,
            data={"message": str(exc), "error_type": type(exc).__name__, "latency_ms": total_latency_ms},
        )


# 应用补丁（启用并发工具执行）。与拆分前一致：仍在模块导入时应用，时机不变。
AgentRunner.stream_events = _patched_stream_events


class LenientHitlMiddleware(HitlMiddleware):
    """宽松的 HITL 中间件：用户拒绝时不抛异常，替换为拒绝消息让 LLM 继续。

    在此基础上支持会话级三档审批模式（ask / auto / full）：

    - ``auto``：只读工具（含 file 的读类子操作）自动放行，写/执行仍逐次确认
    - ``full``：``auto_approve_tools`` 含 ``*`` 哨兵时全部放行（仅管理员可用）
    """

    def __init__(self, *args, approval_mode: str = "ask", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.approval_mode = normalize_approval_mode(approval_mode)

    @staticmethod
    def _tool_arguments(tool_call: ToolCall) -> dict:
        arguments = getattr(tool_call.function, "arguments", None)
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = None
        return arguments if isinstance(arguments, dict) else {}

    async def before_tool(
        self,
        ctx: MiddlewareContext,
        tool_call: ToolCall,
    ) -> ToolCall | None:
        """工具执行前进行审批，用户拒绝时替换为拒绝工具。"""
        tool_name = tool_call.function.name

        # 自动批准：显式名单 / 全放行哨兵
        if "*" in self.auto_approve_tools or tool_name in self.auto_approve_tools:
            return tool_call

        # auto 档：只读工具（含细粒度工具的只读子操作）自动放行
        if self.approval_mode == "auto" and is_read_only_tool(
            tool_name, self._tool_arguments(tool_call)
        ):
            return tool_call

        # 自动拒绝 - 替换为拒绝工具
        if tool_name in self.auto_reject_tools:
            tool_call.function.name = _REJECTED_TOOL_NAME
            tool_call.function.arguments = {"original_tool": tool_name, "reason": "自动拒绝"}
            return tool_call

        # 请求用户审批
        approved = await self.approval_provider(tool_call)
        if not approved:
            # 用户拒绝，替换为拒绝工具（LLM 会收到明确的拒绝消息）
            tool_call.function.name = _REJECTED_TOOL_NAME
            tool_call.function.arguments = {"original_tool": tool_name, "reason": "用户拒绝了此工具的执行"}
            return tool_call

        return tool_call


class ThinkingHistoryCompatibilityMiddleware(Middleware):
    """Keep provider thinking-mode histories free of local synthetic replies."""

    async def before_llm(self, ctx: MiddlewareContext) -> MiddlewareContext:
        ctx.state.messages = [
            message
            for message in ctx.state.messages
            if not (
                message.role == "assistant"
                and message.content == MAX_STEPS_LIMIT_MESSAGE
                and not getattr(message, "reasoning_content", None)
                and not getattr(message, "tool_calls", None)
            )
        ]
        return ctx


class SkillInstructionMiddleware(Middleware):
    """将 Skill 使用指引注入系统提示词。

    与 wuwei 内置 SkillMiddleware 不同，本中间件保留了项目自定义的指令文本，
    并匹配 register_skill_tools() 注册的 list_skills/load_skill 工具名。
    """

    def __init__(self, instruction: str = SKILL_INSTRUCTION) -> None:
        self.instruction = instruction.strip()
        self._injected = False

    async def before_llm(self, ctx: MiddlewareContext) -> MiddlewareContext:
        if self._injected:
            return ctx
        if not self.instruction:
            return ctx

        for msg in ctx.state.messages:
            if msg.role == "system":
                base_prompt = (msg.content or "").rstrip()
                msg.content = (
                    f"{base_prompt}\n\n{self.instruction}" if base_prompt else self.instruction
                )
                break
        else:
            from wuwei.core.message import SystemMessage
            ctx.state.messages.insert(0, SystemMessage(content=self.instruction))

        self._injected = True
        return ctx


def _unregister_if_exists(registry: ToolRegistry, name: str) -> None:
    """wuwei 2.1 的 ToolRegistry.register() 拒绝重名，注册前先移除旧工具。"""
    if registry.get(name) is not None:
        registry.unregister(registry.get(name))


def _unregister_tool_group(registry: ToolRegistry, group_name: str) -> None:
    """按工具组名注销：组名本身 + TOOL_CATALOG 中该组的全部 sub_tools。

    signature 中的键是组名（如 "knowledge"/"memory"/"decision"），而注册表里的
    实际工具名是 sub_tools（如 search_knowledge_base）。只按组名精确匹配会漏注销。
    """
    _unregister_if_exists(registry, group_name)
    catalog_item = TOOL_CATALOG.get(group_name) or {}
    for sub_name in (catalog_item.get("sub_tools") or {}):
        _unregister_if_exists(registry, sub_name)


def _signature_group_enabled(
    signature: tuple[tuple[str, bool, bool], ...] | list[tuple[str, bool, bool]],
    group_name: str,
    default: bool = True,
) -> bool:
    """从 profile.signature 判断工具组是否启用；未配置时返回 default。"""
    for tool_name, enabled, _ in signature:
        if tool_name == group_name:
            return bool(enabled)
    return default


class AgentFactory:
    """Agent 构建工厂（Mixin，由 AgentService 组合继承）。

    依赖宿主（AgentService）提供的属性：
    - ``self.settings``: 应用配置
    - ``self.approval_manager``: HITL 审批管理器
    - ``self._agents``: Agent 实例 TTLCache
    """

    def _ensure_openai_key(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请先在环境变量或 .env 中配置后再调用 /agent/stream。")

    def _get_agent(self, profile: RuntimeAgentProfile) -> Agent:
        injected = getattr(self, "_agent", None)
        if injected is not None:
            return injected
        self._ensure_openai_key()
        import hashlib
        # 用 hash 替代完整文本，减少缓存键内存占用
        prompt_hash = hashlib.md5((profile.system_prompt or "").encode()).hexdigest()[:8]
        skills_hash = hashlib.md5(str(profile.skills).encode()).hexdigest()[:8]
        cache_key = (
            profile.profile_id,
            profile.slug,
            profile.response_mode,
            prompt_hash,
            profile.builtin_tools,
            tuple(sorted(profile.approval_tools)),
            profile.signature,
            skills_hash,
            profile.external_system_ids,
            self.settings.context_compression_enabled,
            # 计划模式会改变工具集合，必须参与缓存键，否则会复用普通模式的 agent
            bool(getattr(profile, "plan_mode", False)),
        )
        cached = self._agents.get(cache_key)
        if cached is not None:
            return cached

        # 本机 AgenticOS：默认用当前用户 Cookie 直连 agents.gree.com，无需 API Key。
        from app.core.data_path import get_current_user_id
        from app.services.upstream.llm_factory import build_llm_for_user

        uid = get_current_user_id() or None
        llm = build_llm_for_user(
            uid,
            max_tokens=self.settings.agent_max_tokens,
            timeout=self.settings.llm_timeout,
            model=self.settings.openai_model,
            prefer_cookie=True,
        )
        tools, ext_instruction = self._build_tool_registry(profile)
        middleware_stack = self._build_middleware_stack(profile, llm, tool_registry=tools)

        # 追加外部系统指引到 system prompt
        system_prompt = profile.system_prompt
        if ext_instruction:
            system_prompt = f"{system_prompt}{ext_instruction}"

        agent = Agent(
            llm=llm,
            tools=tools,
            default_system_prompt=system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            middleware=middleware_stack,
            load_builtins=False,
        )
        self._agents[cache_key] = agent
        return agent

    def _build_middleware_stack(
        self,
        profile: RuntimeAgentProfile,
        llm: LLMGateway,
        tool_registry: ToolRegistry | None = None,
    ) -> MiddlewareStack:
        """构建中间件栈，替代旧版 Hook 注册。

        tool_registry：调用方已构建的注册表（避免重复构建，含同步 DB 会话）。
        """
        stack = MiddlewareStack()

        # 1. HITL 审批中间件
        # approval_tools 是需要审批的工具列表，不在列表中的工具自动批准
        approval_tools = set(profile.approval_tools)
        if approval_tools and self.settings.hitl_enabled:
            if tool_registry is None:
                tool_registry, _ = self._build_tool_registry(profile)
            all_tool_names = [t.name for t in tool_registry.list_tools()]
            # 审批模式：full 档用 "*" 哨兵表示全放行（非管理员自动降级为原行为）
            approval_mode = normalize_approval_mode(
                getattr(profile, "approval_mode", None)
            )
            if approval_mode == "full" and getattr(profile, "is_admin_actor", False):
                auto_approve = ["*"]
            else:
                approval_mode = "ask" if approval_mode == "full" else approval_mode
                auto_approve = [name for name in all_tool_names if name not in approval_tools]
            stack.add(LenientHitlMiddleware(
                approval_provider=self.approval_manager.request_approval_bool,
                auto_approve_tools=auto_approve,
                auto_reject_tools=[],
                approval_mode=approval_mode,
            ))

        # 2. 异步子代理中间件（后台任务能力）
        if self.settings.async_sub_agents_enabled:
            sub_agents = self._build_async_sub_agents()
            if sub_agents:
                stack.add(AsyncSubAgentMiddleware(
                    sub_agents=sub_agents,
                    parent_llm=llm,
                ))

        # 5. 上下文压缩中间件
        if self.settings.context_compression_enabled:
            stack.add(ContextCompressionMiddleware(
                llm=llm,
                trigger_tokens=self.settings.context_compress_after_turns * 500,
                keep_recent_turns=self.settings.context_keep_recent_turns,
            ))

        # 3. 日志中间件（开发环境启用，生产环境可关闭）
        if self.settings.environment == "development":
            stack.add(LoggingMiddleware())

        # 4. 追踪中间件（开发环境启用，输出 OpenTelemetry span）
        if self.settings.environment == "development":
            try:
                from wuwei.observability import TracingMiddleware
                stack.add(TracingMiddleware(service_name="agenticos"))
            except ImportError:
                pass  # opentelemetry 未安装时跳过

        # 4. Skill 指令中间件
        if "skill" in profile.builtin_tools:
            stack.add(SkillInstructionMiddleware())

        # 4. 思考历史兼容中间件
        stack.add(ThinkingHistoryCompatibilityMiddleware())

        return stack

    def _build_async_sub_agents(self) -> list[AsyncSubAgent]:
        """构建异步子代理列表。

        子代理在后台运行，不阻塞主对话。LLM 通过 start/check/cancel/list 操作管理。
        """
        from wuwei.tools import ToolRegistry as _TR

        sub_agents: list[AsyncSubAgent] = []

        # 1. 代码分析子代理
        code_registry = _TR()
        code_ctx = PluginContext(tool_registry=code_registry)
        try:
            from wuwei.plugin.builtin import calc as calc_mod, python as python_mod, git as git_mod
            calc_mod.setup(code_ctx)
            python_mod.setup(code_ctx)
            git_mod.setup(code_ctx)
        except Exception as e:
            _logger.warning("Sub-agent code_analyst plugin setup failed: %s", e)

        sub_agents.append(AsyncSubAgent(
            name="code_analyst",
            description="代码分析与执行：运行 Python 脚本、数学计算、Git 操作。适合需要后台运行代码或分析的场景。",
            system_prompt=(
                "你是一个代码分析助手。你可以执行 Python 脚本、进行数学计算、查看 Git 状态。"
                "请直接运行代码并返回结果，不要解释代码本身。"
                "返回时用简洁的格式说明执行结果。"
            ),
            tools=list(code_registry.list_tools()),
            max_steps=5,
            inherit_context=False,
        ))

        # 2. 文件处理子代理
        file_registry = _TR()
        file_ctx = PluginContext(tool_registry=file_registry)
        try:
            from wuwei.plugin.builtin import file as file_mod, text as text_mod
            file_mod.setup(file_ctx)
            text_mod.setup(file_ctx)
        except Exception as e:
            _logger.warning("Sub-agent file_processor plugin setup failed: %s", e)

        sub_agents.append(AsyncSubAgent(
            name="file_processor",
            description="文件处理：读取、搜索、整理文件内容。适合需要在后台批量处理文件的场景。",
            system_prompt=(
                "你是一个文件处理助手。你可以读取文件、搜索文本、整理内容。"
                "工作时保持高效，直接返回处理结果。"
            ),
            tools=list(file_registry.list_tools()),
            max_steps=8,
            inherit_context=False,
        ))

        return sub_agents

    @staticmethod
    def _build_tool_registry(profile: RuntimeAgentProfile) -> tuple[ToolRegistry, str]:
        # Exclude "skill", "email", and "file" (file is handled per-mode below)
        _exclude = {"skill", "email"}
        if profile.response_mode == "website":
            _exclude.add("file")
        builtin_tools = [name for name in profile.builtin_tools if name not in _exclude]

        registry = ToolRegistry()
        ctx = PluginContext(tool_registry=registry)

        # 按需加载内置插件
        from wuwei.plugin.builtin import (
            calc as calc_mod,
            time_plugin as time_mod,
            file as file_mod,
            git as git_mod,
            npm as npm_mod,
            python as python_mod,
            decision as decision_mod,
            json_tools as json_mod,
            http as http_mod,
            text as text_mod,
        )
        # 计划模式：只保留只读工具，从源头杜绝误操作（而非事后拦截）
        if getattr(profile, "plan_mode", False):
            from app.services.approval_policy import plan_mode_blocked_tools

            blocked = set(plan_mode_blocked_tools(list(profile.builtin_tools)))
            if blocked:
                _logger.info("plan mode: blocking %d tools: %s", len(blocked), sorted(blocked))
            builtin_tools = [name for name in builtin_tools if name not in blocked]
            _exclude |= blocked

        _PLUGIN_MAP = {
            "calc": calc_mod,
            "time": time_mod,
            "file": file_mod,
            "git": git_mod,
            "npm": npm_mod,
            "python": python_mod,
            "decision": decision_mod,
            "json": json_mod,
            "http": http_mod,
            "text": text_mod,
        }
        for name in builtin_tools:
            mod = _PLUGIN_MAP.get(name)
            if mod is not None:
                mod.setup(ctx)

        if "skill" in profile.builtin_tools:
            skill_manager = SkillManager(
                [FileSystemSkillProvider(skill.root_dir) for skill in profile.skills]
            )
            skill_ctx = PluginContext(
                tool_registry=registry,
                skill_manager=skill_manager,
                middleware_stack=None,  # middleware 在 Agent 层处理
            )
            setup_skill_plugin(skill_ctx)
        if "email" in profile.builtin_tools:
            from app.tools.email_tools import register_email_tools
            register_email_tools(registry)

        # 外部系统工具：根据 agent profile 关联的外部系统动态注册
        ext_instruction = ""
        if profile.external_system_ids:
            from app.services.external_system_service import register_external_tools
            from app.db.session import create_db_session
            _db = create_db_session()
            try:
                registered_names = register_external_tools(registry, list(profile.external_system_ids), _db)
            finally:
                _db.close()
            if registered_names:
                ext_instruction = (
                    f"\n\n你已连接以下外部集成系统：{', '.join(registered_names)}。"
                    "当用户的需求涉及这些系统时，优先调用对应的集成工具完成操作。"
                    "例如：查询数据、创建记录、调用接口等。"
                )

        # 决策工具：检查配置是否启用
        decision_enabled = _signature_group_enabled(profile.signature, "decision", default=True)
        if decision_enabled:
            from app.tools.decision_tools import register_decision_tools
            register_decision_tools(registry)

        # 记忆工具：检查配置是否启用
        memory_enabled = _signature_group_enabled(profile.signature, "memory", default=True)
        if memory_enabled:
            from app.tools.memory_tools import register_memory_tools
            register_memory_tools(registry)

        # 知识库工具：尊重 tool config（组名 "knowledge"），禁用则不注册
        knowledge_enabled = _signature_group_enabled(profile.signature, "knowledge", default=True)
        if knowledge_enabled:
            from app.tools.knowledge_tools import register_knowledge_tools
            register_knowledge_tools(registry)

        # 注册拒绝工具：用户拒绝工具执行时，替换原工具调用，让 LLM 收到明确的拒绝消息
        @registry.tool(
            name=_REJECTED_TOOL_NAME,
            display_name="工具被拒绝",
            description="用户拒绝了工具的执行。此工具由系统自动调用，不需要手动使用。",
        )
        async def _tool_rejected(original_tool: str = "", reason: str = "用户拒绝了此工具的执行") -> dict:
            return {"rejected": True, "original_tool": original_tool, "message": reason}

        # 独立 file_to_md 工具：当 file 工具组未启用时单独注册
        if "file" not in profile.builtin_tools:
            _unregister_if_exists(registry, "file_to_md")
            from app.tools.file_to_md_tool import register_file_to_md_tool as _register_file_to_md
            _register_file_to_md(registry)

        # 数据可视化工具（所有模式可用）
        from app.tools.chart_render_tools import register_chart_render_tools as _register_chart_render
        _register_chart_render(registry)

        # 数据分析工具（所有模式可用）
        from app.tools.data_analysis_tools import register_data_analysis_tools as _register_data_analysis
        _register_data_analysis(registry)

        if profile.response_mode == "ppt":
            from app.tools.icon_tools import register_icon_tools as _register_icon_tools
            _register_icon_tools(registry)
            from app.tools.ppt_tools import register_ppt_tools as _register_ppt_tools
            _register_ppt_tools(registry)
            from app.tools.chart_tools import register_chart_tools as _register_chart_tools
            _register_chart_tools(registry)
            from app.tools.quality_checker_tools import register_quality_checker_tools as _register_qc_tools
            _register_qc_tools(registry)
            from app.tools.pptx_reverse_tools import register_pptx_reverse_tools as _register_pptx_reverse
            _register_pptx_reverse(registry)
            from app.tools.template_tools import register_template_tools as _register_template_tools
            _register_template_tools(registry)
            from app.tools.image_tools import register_image_tools as _register_image_tools
            _register_image_tools(registry)

        if profile.response_mode == "website":
            from app.tools.website_tools import register_website_tools as _register_website_tools
            _register_website_tools(registry)
            from app.tools.website_file_tools import register_website_file_tools as _register_website_file_tools
            _register_website_file_tools(registry)

        # MCP 工具集成：如果 MCP 服务已连接，将 MCP 工具添加到注册表
        try:
            from app.services.mcp_service import get_mcp_service
            mcp_svc = get_mcp_service()
            mcp_tools = mcp_svc.get_tools()
            if mcp_tools:
                for tool in mcp_tools:
                    if registry.get(tool.name) is None:
                        registry.register(tool)
        except Exception as e:
            _logger.debug("MCP tool registration skipped: %s", e)

        # 移除 profile 中禁用的工具（覆盖 PPT/website 等模式无条件注册的工具）
        # 组名工具（knowledge/memory/decision 等）需按 sub_tools 一并注销
        for tool_name, enabled, _ in profile.signature:
            if not enabled:
                _unregister_tool_group(registry, tool_name)

        # 统一工具执行层：对同步 handler 包装成异步版本，防止 wuwei Tool.invoke
        # 直接在事件循环上跑同步代码导致阻塞。这是解决"一个接口阻塞全站"的关键修复。
        import asyncio
        import inspect
        for tool_name, tool in list(registry._tools.items()):
            if not inspect.iscoroutinefunction(tool.handler):
                # 同步 handler → 用 to_thread 包装
                original_handler = tool.handler
                async def _async_wrapper(*args, _orig=original_handler, **kwargs):
                    return await asyncio.to_thread(_orig, *args, **kwargs)
                tool.handler = _async_wrapper

        return registry, ext_instruction
