import asyncio
import contextlib
import contextvars
import json
import logging
from typing import Any, AsyncIterator

# 当前会话 ID，供 ApprovalManager 使用
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)

from wuwei import Agent, AgentEvent, FileSystemSkillProvider, SkillManager
from wuwei.llm import LLMGateway
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
from wuwei.agent.multi_agent import MultiAgentGraph, TeamMember
from wuwei.runtime.agent_runner import AgentRunner

# 特殊工具名：用户拒绝时替换原工具调用，让 LLM 收到明确的拒绝消息
_REJECTED_TOOL_NAME = "__tool_rejected__"

# ── 并发工具执行补丁 ──────────────────────────────────────────────────
# wuwei 的 AgentRunner 默认逐个执行工具调用。
# 本补丁将安全工具（is_concurrency_safe=True）分批并发执行，
# 非安全工具仍保持顺序串行。对前端 SSE 事件流完全透明。

_original_stream_events = AgentRunner.stream_events


async def _patched_stream_events(self, user_input: str, *, task=None):
    """并发版 stream_events：安全工具用 asyncio.gather 并行，其余与原版相同。

    与原始实现的唯一区别：工具执行阶段按 is_concurrency_safe 分批并发。
    LLM 调用、中间件生命周期、事件格式完全不变。
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
                            self.session.context.add_tool_message(final_msg.content or "", final_msg.tool_call_id)
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
                            self.session.context.add_tool_message(tool_message.content or "", tool_message.tool_call_id)
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


# 应用补丁（启用并发工具执行）
AgentRunner.stream_events = _patched_stream_events


class LenientHitlMiddleware(HitlMiddleware):
    """宽松的 HITL 中间件：用户拒绝时不抛异常，替换为拒绝消息让 LLM 继续。"""

    async def before_tool(
        self,
        ctx: MiddlewareContext,
        tool_call: ToolCall,
    ) -> ToolCall | None:
        """工具执行前进行审批，用户拒绝时替换为拒绝工具。"""
        tool_name = tool_call.function.name

        # 自动批准
        if tool_name in self.auto_approve_tools:
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

from app.core.config import Settings, get_settings
from app.db.models import AgentUsageEventModel, ApprovalModel, PptArtifactModel, UserModel
from app.db.session import create_db_session
from app.services.approval_manager import ApprovalManager
from app.services.agent_profile_service import AgentProfileService, RuntimeAgentProfile
from app.services.ppt_artifact_service import PptArtifactService
from app.services.ppt.theme_token_resolver import build_token_quick_ref, list_available_themes
from app.services.session_storage import DatabaseAgentStorage, dump_json
from app.services.tool_config_service import ToolConfigService
from app.schemas.agent import AgentStreamRequest
from app.tools.email_tools import register_email_tools, set_current_session_id as set_email_session_id
from app.core.data_path import set_current_session_id as set_data_session_id, set_current_user_id, restore_website_dir_for_session, DATA_DIR, PPT_SESSIONS_DIR, PPT_OUTPUT_DIR, WEBSITES_DIR, WEBSITE_TEMPLATES_DIR, DESIGN_THEMES_DIR, _parse_dir_name
from app.services.external_system_service import set_ext_user_id
# pptx_reverse_session_id removed — now uses data_path contextvars directly


MAX_STEPS_LIMIT_MESSAGE = "任务未完成，已达到最大步骤限制。"


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


SKILL_INSTRUCTION = (
    "你有可用的 Skill（专门技能），它们是处理特定领域任务的增强能力。\n"
    "遇到可能匹配的请求时，调用 `list_skills` 查看可用技能摘要。\n"
    "如果某个技能描述与用户任务相关，调用 `load_skill` 加载其完整指令并遵循执行。\n"
    "技能正文已包含核心知识，**不要逐个读取 references 文件**，除非正文明确要求读取某个具体文件。\n"
    "references 是补充资料，不是必须全部加载的。"
)


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


_logger = logging.getLogger("agent")


def _unregister_if_exists(registry: ToolRegistry, name: str) -> None:
    """wuwei 2.1 的 ToolRegistry.register() 拒绝重名，注册前先移除旧工具。"""
    if registry.get(name) is not None:
        registry.unregister(registry.get(name))

class AgentService:
    def __init__(
        self,
        settings: Settings,
        storage: DatabaseAgentStorage | None = None,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or DatabaseAgentStorage()
        self.approval_manager = approval_manager or ApprovalManager(
            timeout_seconds=settings.hitl_timeout_seconds
        )
        self.ppt_artifacts = PptArtifactService()
        self.agent_profiles = AgentProfileService()
        self.tool_configs = ToolConfigService()
        self._agents: dict[tuple[object, ...], Agent] = {}
        self._cached_display_name_map: dict[str, str] | None = None

    def _get_display_name_map(self) -> dict[str, str]:
        if self._cached_display_name_map is None:
            self._cached_display_name_map = self.tool_configs.build_display_name_map()
        return self._cached_display_name_map

    def ensure_ready(self) -> None:
        self._ensure_openai_key()

    def clear_agent_cache(self) -> None:
        self._agents.clear()

    def _ensure_openai_key(self) -> None:
        if not self.settings.openai_api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请先在环境变量或 .env 中配置后再调用 /agent/stream。")

    def _runtime_from_mode(self, response_mode: str, system_prompt: str | None = None) -> RuntimeAgentProfile:
        profile = self.tool_configs.get_runtime_profile(response_mode)
        return RuntimeAgentProfile(
            profile_id=None,
            name=response_mode,
            slug=response_mode,
            response_mode=profile.mode,
            system_prompt=system_prompt or self.settings.agent_system_prompt,
            builtin_tools=profile.builtin_tools,
            approval_tools=profile.approval_tools,
            signature=profile.signature,
            skills=(),
        )

    def _resolve_runtime_profile(self, request: AgentStreamRequest, user: UserModel | None) -> RuntimeAgentProfile:
        if request.agent_profile_id is not None:
            if user is None:
                raise PermissionError("Agent profile requires an authenticated user")
            return self.agent_profiles.resolve_runtime(request.agent_profile_id, user)
        if user is not None:
            return self.agent_profiles.resolve_runtime_by_mode(request.response_mode, user)
        return self._runtime_from_mode(request.response_mode, request.system_prompt)

    def _get_agent(self, profile: RuntimeAgentProfile) -> Agent:
        injected = getattr(self, "_agent", None)
        if injected is not None:
            return injected
        self._ensure_openai_key()
        cache_key = (
            profile.profile_id,
            profile.slug,
            profile.response_mode,
            profile.system_prompt,
            profile.builtin_tools,
            tuple(sorted(profile.approval_tools)),
            profile.signature,
            profile.skills,
            profile.external_system_ids,
            self.settings.context_compression_enabled,
        )
        cached = self._agents.get(cache_key)
        if cached is not None:
            return cached

        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        tools, ext_instruction = self._build_tool_registry(profile)
        middleware_stack = self._build_middleware_stack(profile, llm)

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

    def _build_middleware_stack(self, profile: RuntimeAgentProfile, llm: LLMGateway) -> MiddlewareStack:
        """构建中间件栈，替代旧版 Hook 注册。"""
        stack = MiddlewareStack()

        # 1. HITL 审批中间件
        # approval_tools 是需要审批的工具列表，不在列表中的工具自动批准
        approval_tools = set(profile.approval_tools)
        if approval_tools and self.settings.hitl_enabled:
            from wuwei.tools import ToolRegistry as _TR
            _reg, _ = self._build_tool_registry(profile)
            all_tool_names = [t.name for t in _reg.list_tools()]
            auto_approve = [name for name in all_tool_names if name not in approval_tools]
            stack.add(LenientHitlMiddleware(
                approval_provider=self.approval_manager.request_approval_bool,
                auto_approve_tools=auto_approve,
                auto_reject_tools=[],
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
        except Exception:
            pass

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
        except Exception:
            pass

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
            register_email_tools(registry)

        # 外部系统工具：根据 agent profile 关联的外部系统动态注册
        ext_instruction = ""
        if profile.external_system_ids:
            from app.services.external_system_service import register_external_tools
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

        # 决策工具：所有模式都可用
        from app.tools.decision_tools import register_decision_tools
        register_decision_tools(registry)

        # 记忆工具：所有模式都可用
        from app.tools.memory_tools import register_memory_tools
        register_memory_tools(registry)

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
        except Exception:
            pass  # MCP 未配置或未连接时静默跳过

        return registry, ext_instruction

    def _build_tool_call_payload(self, event: AgentEvent) -> dict[str, Any]:
        # 优先使用事件中的 display_name，否则从 TOOL_CATALOG 查找中文名
        tool_name = event.data.get("tool_name") or ""
        # 拒绝工具显示原始工具名 + "已拒绝"
        if tool_name == _REJECTED_TOOL_NAME:
            original = event.data.get("args", {}).get("original_tool", "") if isinstance(event.data.get("args"), dict) else ""
            display_name = f"{self._get_display_name_map().get(original, original) or '工具'}（已拒绝）"
        else:
            display_name = (
                event.data.get("display_name")
                or self._get_display_name_map().get(tool_name)
                or tool_name
                or "工具调用"
            )
        payload = {
            "id": event.data.get("tool_call_id"),
            "function": {
                "name": display_name,
                "arguments": event.data.get("args") or {},
            },
        }
        for source_key, target_key in (
            ("side_effect", "side_effect"),
            ("requires_approval", "requires_approval"),
        ):
            value = event.data.get(source_key)
            if isinstance(value, bool):
                payload[target_key] = value
        return payload

    def _build_tool_result_payload(
        self,
        event: AgentEvent,
        *,
        status: str,
        result: str | None,
    ) -> dict[str, Any]:
        tool_name = event.data.get("tool_name") or ""
        display_name = (
            event.data.get("display_name")
            or self._get_display_name_map().get(tool_name)
            or tool_name
            or "工具调用"
        )
        payload = {
            "tool_call_id": event.data.get("tool_call_id"),
            "name": display_name,
            "status": status,
            "result": result,
        }
        error_type = event.data.get("error_type")
        if isinstance(error_type, str) and error_type:
            payload["error_type"] = error_type
        payload.update(AgentService._extract_tool_output_metadata(result))
        return payload

    @staticmethod
    def _extract_tool_output_metadata(output: str | None) -> dict[str, Any]:
        if not output:
            return {}
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}

        metadata: dict[str, Any] = {}
        error = payload.get("error")
        if isinstance(error, dict):
            error_type = error.get("type")
            if isinstance(error_type, str) and error_type:
                metadata["error_type"] = error_type

        for key in ("tool_executed", "retryable", "instruction"):
            value = payload.get(key)
            if value is not None:
                metadata[key] = value

        attempts = payload.get("attempts")
        if isinstance(attempts, int):
            metadata["attempts"] = attempts

        return metadata

    @staticmethod
    def _status_from_tool_output(output: str | None) -> str:
        if not output:
            return "success"
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return "success"
        if isinstance(payload, dict) and payload.get("ok") is False:
            return "error"
        return "success"

    async def _load_session_if_needed(self, agent: Agent, request: AgentStreamRequest) -> None:
        if not request.session_id or not hasattr(agent, "_sessions"):
            return
        sessions = getattr(agent, "_sessions")
        if request.session_id in sessions:
            return
        loaded = await self.storage.load(request.session_id)
        if loaded is not None:
            sessions[request.session_id] = loaded

    @staticmethod
    def _inject_design_catalog(message: str) -> str:
        """Inject design catalog: phased skill loading + theme selection + token reference.

        分阶段加载策略：LLM 按工作流阶段依次加载技能，避免一次性注入过多规则。
        """
        token_ref = build_token_quick_ref()
        theme_count = len(list_available_themes())
        theme_list = ", ".join(sorted(list_available_themes()))

        lines = [
            "",
            "---",
            "## ⚠️ 分阶段技能加载（严格遵守）",
            "",
            "**不要一次加载所有技能。** 按以下阶段依次加载：",
            "",
            "### 阶段 1：开始创作（立即执行）",
            "1. `load_skill(\"ppt-design-guide\")` — SVG 技术约束 + 排版铁律 + 颜色纪律",
            "2. `load_skill(\"ppt-template-library\")` — 15 个布局 + 71 个图表模板",
            "",
            "### 阶段 2：规划完成后",
            "3. `load_skill(\"ppt-workflow\")` — 7 步工作流 + spec_lock 格式 + 修改流程",
            "",
            "### 阶段 3：每次 save_slide 前",
            "4. `load_skill(\"ppt-quality-budgets\")` — 颜色预算 + 字号预算 + 自检清单",
            "",
            "**懒加载纪律**：加载技能后不要预读所有模板。每页只读 1 个模板 SVG，读完立即生成。",
            "",
            "示例正确流程：",
            "  load_skill(\"ppt-design-guide\")",
            "  load_skill(\"ppt-template-library\")",
            "  → 确认需求 + 选择主题",
            "  load_skill(\"ppt-workflow\")",
            "  → 生成 spec_lock + 规划页面",
            "  submit_slide_plan(slides='[{...}]')  ← 提交结构化页面计划",
            "  → 等待用户确认",
            "  load_skill(\"ppt-quality-budgets\")",
            "  load_skill_reference(\"references/core-layouts/cover.svg\")",
            "  → save_slide(1, svg=\"...\")",
            "  load_skill_reference(\"references/core-layouts/toc.svg\")",
            "  → save_slide(2, svg=\"...\")",
            "",
            "---",
            "## ⭐ 主题选择",
            "",
            f"**共 {theme_count} 个主题可用。data-theme 只能从下方列表选。**",
            "",
            "**快速决策：**",
            "- 商业汇报 → apple, stripe, ibm, corporate",
            "- 技术分享 → github, vercel, cursor, linear-app",
            "- 创意发布 → nike, spotify, cyberpunk, sunset",
            "- AI 科技 → openai, claude, nvidia, huggingface",
            "- 学术报告 → kami, paper, editorial, solarized",
            "- 社交媒体 → airbnb, xiaohongshu, framer, rose-pine",
            "- 简约纯净 → minimal, clean, mono, nord, catppuccin-latte",
            "- 活泼年轻 → vibrant, colorful, catppuccin, zhangzara-sakura-chroma",
            "- 暗色系 → dracula, tokyo-night, monokai, trading-terminal",
            "- 金融支付 → stripe, revolut, binance, kraken",
            "",
            f"**全部 {theme_count} 个主题：**",
            theme_list,
            "",
            "---",
            "## Token 语义速查",
            "",
            token_ref,
            "",
            "**CURRENT TIME:** " + __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        ]
        return message + "\n".join(lines)

    @staticmethod
    def _inject_website_catalog(message: str) -> str:
        """Inject template structure overview and theme guide for website mode."""
        from pathlib import Path

        templates_dir = WEBSITE_TEMPLATES_DIR
        template_info: list[str] = []
        for stack in ("vanilla", "vue", "react"):
            pkg = templates_dir / stack / "package.json"
            if not pkg.exists():
                continue
            import json
            deps = json.loads(pkg.read_text("utf-8")).get("dependencies", {})
            dep_list = ", ".join(deps.keys()) if deps else "无"
            template_info.append(f"  **{stack}** — 依赖: {dep_list}")

        theme_dir = DESIGN_THEMES_DIR
        theme_count = len(list(theme_dir.glob("*.css"))) if theme_dir.exists() else 0

        lines = [
            "",
            "---",
            "## Website 模式资源速查",
            "",
            "### 致命错误警告",
            "",
            "**在调用 `copy_template` 之前，项目目录根本不存在！**",
            "直接 `read_text_file` 一个尚不存在的路径必然报错 FileNotFoundError。",
            "正确流程永远是：先 `check_website_project()` → 再 `copy_template(stack)` → 然后才能操作文件。目录名自动生成，格式为 u<用户ID>_s<会话ID>_v<版本号>。",
            "",
            "### 可用模板",
            "",
            *template_info,
            "",
            "### 工作流程（必须严格按顺序）",
            "",
            "1. 分析需求 → 选择 vanilla/vue/react",
            "2. `check_website_project()` 检查项目是否已存在",
            f"3. `copy_template(stack)` 复制模板（目录名自动生成）← 绝对不能跳过！",
            "4. 用文件工具（write_text_file / replace_text_in_file）修改已存在的模板文件",
            "5. 调用 `build_website(slug)` 验证构建",
            "6. 告知用户项目路径和构建结果",
            "",
            "### 依赖约束",
            "",
            "- 模板 package.json 已包含所有必需依赖，**禁止调用 npm_install_package**",
            "- **禁止 `npm_run_script` 和 `npm_list_scripts`** — 构建验证只用 `build_website(slug)`，不要直接调用 npm 工具",
            "- 如需额外依赖，必须先告知用户获得同意",
            "- 禁止安装 UI 组件库和 CSS 框架",
            "",
            f"### 设计主题（{theme_count} 套可用）",
            "",
            "所有模板 CSS 使用 var(--bg) / var(--accent) / var(--text-1) 等 CSS 变量。",
            "设置 :root 中的变量值即可切换主题。已内置 apple 主题作为默认。",
            f"完整主题列表见 data/design-themes/ 目录下的 {theme_count} 个 CSS 文件。",
            "",
            "### 项目目录结构",
            "",
            "```",
            "data/websites/u<用户ID>_s<会话ID>_v<版本号>/",
            "  ├── index.html       # 入口 HTML",
            "  ├── package.json     # 依赖配置（不要修改）",
            "  ├── vite.config.js   # 构建配置（不要修改）",
            "  ├── src/             # 源码目录（vue/react）",
            "  ├── css/             # 样式目录（vanilla）",
            "  ├── js/              # 脚本目录（vanilla）",
            "  └── dist/            # 构建产物（build_website 后生成）",
            "```",
            "",
            "### 文件路径规则（极其重要）",
            "",
            "文件工具已自动绑定到当前项目目录，**只需提供相对路径**：",
            "",
            "```",
            "✅ 正确：write_text_file(path=\"index.html\", ...)",
            "✅ 正确：write_text_file(path=\"src/main.js\", ...)",
            "✅ 正确：replace_text_in_file(path=\"css/style.css\", ...)",
            "❌ 错误：write_text_file(path=\"data/websites/u1_xxx_v1/index.html\", ...)",
            "❌ 错误：write_text_file(path=\"D:/code/AgenticOS/data/websites/...\", ...)",
            "```",
            "",
            "**绝对不要在文件路径中包含 `data/websites/` 前缀或完整目录名！**",
            "",
            "---",
        ]
        return message + "\n".join(lines)

    async def _create_ppt_artifact(self, session_id: str) -> dict[str, Any] | None:
        """Create a PPT artifact from saved slides in the session work directory."""
        from app.core.data_path import _parse_dir_name
        # Find the latest versioned directory for this session.
        # Directory naming: u{user_id}_s{session_id}_v{version}
        _slides_dir = None
        max_ver = 0
        if PPT_SESSIONS_DIR.exists():
            for child in PPT_SESSIONS_DIR.iterdir():
                if not child.is_dir():
                    continue
                parsed = _parse_dir_name(child.name)
                if parsed and str(parsed[1]) == session_id:
                    if parsed[2] > max_ver:
                        max_ver = parsed[2]
                        _slides_dir = child
        if _slides_dir is None:
            _slides_dir = PPT_SESSIONS_DIR / session_id
        try:
            artifact = await self.ppt_artifacts.create_from_slides_dir(session_id, _slides_dir)
            if artifact is not None:
                _logger.info("ppt artifact created: session=%s slides=%d", session_id, artifact.get("slide_count", 0))
            else:
                _logger.info("ppt artifact skipped: session=%s (no slides found)", session_id)
            return artifact
        except Exception as exc:
            _logger.exception("ppt artifact creation failed: session=%s", session_id)
            self.ppt_artifacts._last_quality_errors = [f"artifact 创建异常: {type(exc).__name__}: {exc}"]
            self.ppt_artifacts._last_quality_warnings = []
            return None

    @staticmethod
    def _infer_project_slug_from_tools(tool_names: list[str], messages: list | None = None) -> str | None:
        """Try to find the project slug from recent tool calls.

        We can't directly access tool call arguments here, so we scan
        data/websites/ for directories with recent dist/ folders.
        """
        from pathlib import Path as _Path
        _websites_dir = WEBSITES_DIR
        if not _websites_dir.exists():
            return None

        # Find directories with dist/ that have been modified recently
        candidates: list[tuple[str, float]] = []
        for proj in _websites_dir.iterdir():
            if not proj.is_dir() or proj.name.startswith("."):
                continue
            dist = proj / "dist"
            if dist.exists() and dist.is_dir():
                index_html = dist / "index.html"
                if index_html.exists():
                    candidates.append((proj.name, index_html.stat().st_mtime))

        if not candidates:
            return None

        # Return the most recently modified one
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    @staticmethod
    def _inline_dist_assets(dist_dir: "Path", html: str) -> str:
        """Inline CSS and JS assets from dist/ into a self-contained HTML document.

        Vite-built index.html references /assets/... paths which can't resolve
        inside an iframe srcdoc. This reads each local asset and inlines it.
        """
        import re as _re

        def _read_asset(href: str) -> str | None:
            path = href.lstrip("/")
            file_path = dist_dir / path
            if not file_path.exists():
                return None
            try:
                return file_path.read_text(encoding="utf-8")
            except Exception:
                return None

        # Inline CSS: <link rel="stylesheet" href="/assets/xxx.css" /> → <style>
        link_re = _re.compile(
            r'<link\b[^>]*\brel\s*=\s*["\']stylesheet["\'][^>]*\bhref\s*=\s*["\']([^"\']+\.css)["\'][^>]*/?>',
            _re.IGNORECASE,
        )
        def _replace_link(match: _re.Match) -> str:
            href = match.group(1)
            content = _read_asset(href)
            if content is None:
                return match.group(0)
            return f"<style>{content}</style>"

        html = link_re.sub(_replace_link, html)

        # Inline JS: <script src="/assets/xxx.js"></script> → <script>...</script>
        script_re = _re.compile(
            r'<script\b([^>]*)\bsrc\s*=\s*["\']([^"\']+)["\']([^>]*)>\s*</script>',
            _re.IGNORECASE,
        )
        def _replace_script(match: _re.Match) -> str:
            src = match.group(2)
            if src.startswith(("http://", "https://", "data:")):
                return match.group(0)
            content = _read_asset(src)
            if content is None:
                return match.group(0)
            before = match.group(1)
            after = match.group(3)
            return f"<script{before}{after}>{content}</script>"

        html = script_re.sub(_replace_script, html)

        return html

    async def _create_website_artifact(
        self, session_id: str, tool_names: list[str]
    ) -> dict[str, Any] | None:
        """Create a website artifact from the built dist/ directory."""
        _websites_dir = WEBSITES_DIR

        try:
            slug = self._infer_project_slug_from_tools(tool_names)
            if not slug:
                _logger.info("website artifact skipped: could not infer project slug")
                return None

            project_dir = _websites_dir / slug
            dist_dir = project_dir / "dist"
            index_html = dist_dir / "index.html"
            if not index_html.exists():
                _logger.info("website artifact skipped: dist/index.html not found in %s", dist_dir)
                return None

            raw_html = index_html.read_text(encoding="utf-8")
            preview_html = self._inline_dist_assets(dist_dir, raw_html)

            # Count files in dist
            file_count = len([f for f in dist_dir.rglob("*") if f.is_file()])

            # Detect stack
            has_vue = any(f.suffix == ".vue" for f in project_dir.rglob("*"))
            has_jsx = any(f.suffix == ".jsx" for f in project_dir.rglob("*"))
            if has_vue:
                stack = "vue"
            elif has_jsx:
                stack = "react"
            else:
                stack = "vanilla"

            artifact = {
                "type": "website",
                "artifact_id": session_id,  # use session_id as artifact_id for now
                "session_id": session_id,
                "title": slug.replace("-", " ").title(),
                "project_slug": slug,
                "stack": stack,
                "file_count": file_count,
                "preview_html": preview_html,
            }

            _logger.info(
                "website artifact created: session=%s slug=%s stack=%s files=%d",
                session_id, slug, stack, file_count,
            )
            return artifact
        except Exception:
            _logger.exception("website artifact creation failed: session=%s", session_id)
            return None

    async def _get_edit_hint(self, session_id: str) -> str | None:
        """If the session has existing PPT artifacts, add an edit hint for save_slide."""
        from pathlib import Path as _Path
        try:
            artifact = await self.ppt_artifacts.get_latest_for_session(session_id)
            if artifact is None:
                return None
            title = artifact.get("title", "未命名")
            slide_count = artifact.get("slide_count", 0)
            slides_dir = PPT_SESSIONS_DIR / session_id
            svg_files = sorted(slides_dir.glob("slide_*.svg"),
                                key=lambda p: int(p.stem.replace("slide_", ""))) if slides_dir.exists() else []
            file_list = "\n".join(
                f"  read_slide({f.stem.replace('slide_', '')})" for f in svg_files
            ) if svg_files else "  （无已保存文件）"
            return (
                f"\n\n---\n"
                f"## 注意：当前对话已有 PPT「{title}」（{slide_count} 页）\n"
                f"用户可能要修改它。用 read_slide(N) 读取后，save_slide 覆盖修改的页：\n"
                f"{file_list}\n"
                f"如果是新建 PPT 要求，忽略此提示。\n"
            )
        except Exception:
            _logger.warning("_get_edit_hint failed for session=%s", session_id, exc_info=True)
            return None

    async def _persist_session_messages(self, session) -> None:
        """将 session.context 中的消息持久化到数据库。

        wuwei 的 AgentSession 只在内存中存储消息，需要手动持久化。
        """
        try:
            context = getattr(session, "context", None)
            if context is None:
                _logger.warning(f"No context found for session {session.session_id}")
                return

            messages = getattr(context, "_messages", [])
            _logger.info(f"Persist check: session={session.session_id}, context_messages={len(messages)}")

            if not messages:
                return

            # 检查数据库中已有的消息数量，避免重复插入
            existing_count = await self.storage.get_message_count(session.session_id)
            _logger.info(f"Persist check: existing_count={existing_count}")

            if existing_count >= len(messages):
                return

            # 只保存新增的消息
            new_messages = messages[existing_count:]
            for msg in new_messages:
                try:
                    await self.storage.append_message(session.session_id, msg)
                except Exception as e:
                    _logger.warning(f"Failed to append message: {e}, type={type(msg)}")

            _logger.info(f"Persisted {len(new_messages)} messages for session {session.session_id}")
        except Exception as e:
            _logger.warning(f"Failed to persist messages for session {session.session_id}: {e}", exc_info=True)

    def _normalize_session_limits(
        self,
        session,
        *,
        response_mode: str,
        requested_max_steps: int | None,
        profile_max_steps: int | None = None,
    ) -> None:
        if requested_max_steps is not None:
            return
        effective = profile_max_steps or self.settings.agent_max_steps
        current_max_steps = getattr(session, "max_steps", self.settings.agent_max_steps)
        if current_max_steps < effective:
            session.max_steps = effective

    def _build_user_message(self, request: AgentStreamRequest) -> str:
        """Build the user message, describing attached files so the Agent can use tools to process them."""
        if not request.files:
            return request.message

        file_descriptions: list[str] = []
        for f in request.files:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext in ("pptx", "ppt"):
                hint = f"PPTX 文件，用 convert_pptx_to_svg(file_path=\"{f.file_path}\") 转换为 SVG 后编辑"
            else:
                hint = f"文档文件，用 file_to_md(path=\"{f.file_path}\") 读取内容"
            file_descriptions.append(f"- **{f.filename}** → 路径 `{f.file_path}` → {hint}")

        return (
            "## 📎 用户上传了以下文件\n\n"
            + "\n".join(file_descriptions)
            + f"\n\n---\n\n{request.message}"
        )

    def _session_payload(self, session) -> dict[str, Any]:
        metadata = getattr(session, "metadata", {}) or {}
        return {
            "session_id": session.session_id,
            "user_id": metadata.get("user_id"),
            "summary": getattr(session, "summary", None),
            "metadata": metadata,
            "context_compressed": bool(getattr(session, "summary", None)),
            "storage": "sqlalchemy",
            "last_usage": getattr(session, "last_usage", None),
            "last_latency_ms": getattr(session, "last_latency_ms", None),
            "last_llm_calls": getattr(session, "last_llm_calls", None),
        }

    def _map_agent_event(self, event: AgentEvent, session) -> dict[str, Any] | None:
        if event.type == "text_delta":
            return {
                "event": "delta",
                "data": {
                    "session_id": session.session_id,
                    "content": event.data.get("content", ""),
                },
            }

        if event.type == "reasoning_delta":
            return {
                "event": "reasoning_delta",
                "data": {
                    "session_id": session.session_id,
                    "content": event.data.get("content", ""),
                },
            }

        if event.type == "tool_start":
            return {
                "event": "tool_calls",
                "data": {
                    "session_id": session.session_id,
                    "tool_calls": [self._build_tool_call_payload(event)],
                },
            }

        if event.type == "tool_end":
            output = event.data.get("output")
            return {
                "event": "tool_results",
                "data": {
                    "session_id": session.session_id,
                    "tool_calls": [
                        self._build_tool_result_payload(
                            event,
                            status=self._status_from_tool_output(output),
                            result=output,
                        )
                    ],
                },
            }

        if event.type == "tool_error":
            return {
                "event": "tool_error",
                "data": {
                    "session_id": session.session_id,
                    "tool_call_id": event.data.get("tool_call_id"),
                    "tool_name": event.data.get("display_name") or event.data.get("tool_name") or "工具调用",
                    "message": event.data.get("message"),
                    "error_type": event.data.get("error_type"),
                },
            }

        if event.type == "done":
            return {
                "event": "done",
                "data": {
                    **self._session_payload(session),
                    "finish_reason": event.data.get("reason", "stop"),
                    "usage": event.data.get("usage"),
                    "latency_ms": event.data.get("latency_ms"),
                    "llm_calls": event.data.get("llm_calls"),
                },
            }

        if event.type == "error":
            if event.data.get("tool_call_id") or event.data.get("tool_name"):
                return {
                    "event": "tool_results",
                    "data": {
                        "session_id": session.session_id,
                        "tool_calls": [
                            self._build_tool_result_payload(
                                event,
                                status="error",
                                result=event.data.get("message"),
                            )
                        ],
                    },
                }

            return {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "message": event.data.get("message", "智能体执行失败。"),
                    "error_type": event.data.get("error_type"),
                    "usage": event.data.get("usage"),
                    "latency_ms": event.data.get("latency_ms"),
                    "llm_calls": event.data.get("llm_calls"),
                },
            }

        return None

    async def ensure_session_access(self, request: AgentStreamRequest, user: UserModel) -> None:
        if not request.session_id:
            return
        owner_id = await self.storage.get_owner_id(request.session_id)
        if owner_id is not None:
            if owner_id != user.id and user.role != "admin":
                raise PermissionError("当前用户无权访问该会话。")
        else:
            # Session is unowned — allow access but verify it's empty or new.
            # If the session already has messages with a different user context,
            # it's likely a stale unowned session, deny access.
            msg_count = await self.storage.get_message_count(request.session_id)
            if msg_count > 0 and user.role != "admin":
                raise PermissionError("会话未绑定用户且已有消息记录，当前用户无权访问。")

    async def _ensure_record_owner(
        self,
        record_id: str,
        model_type: type[ApprovalModel | PptArtifactModel],
        user: UserModel,
    ) -> None:
        def _run():
            with create_db_session() as db:
                row = db.get(model_type, record_id)
                if row is None:
                    return None
                return row.session_id
        session_id = await asyncio.to_thread(_run)
        if not session_id:
            return
        owner_id = await self.storage.get_owner_id(session_id)
        if owner_id is not None and owner_id != user.id and user.role != "admin":
            raise PermissionError("当前用户无权访问此资源。")
        # Reject access when session owner is unset but the artifact exists
        if owner_id is None and user.role != "admin":
            raise PermissionError("资源所属会话未绑定用户，当前用户无权访问。")

    @staticmethod
    def _extract_usage_numbers(usage: Any) -> tuple[int, int, int]:
        if not isinstance(usage, dict):
            return 0, 0, 0

        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
        return input_tokens, output_tokens, total_tokens

    @staticmethod
    def _estimate_tokens_from_text(text: str) -> int:
        """Rough token estimation when the LLM provider doesn't return usage in streaming mode."""
        if not text:
            return 0
        # ~4 chars per token for Latin, ~1.5 for CJK; use 3 as a balanced average
        return max(1, round(len(text) / 3))

    async def _record_usage_event(
        self,
        *,
        session,
        request: AgentStreamRequest,
        user: UserModel | None,
        event_data: dict[str, Any],
        tool_names: list[str],
        response_mode: str,
        agent_profile_id: int | None,
        collected_text: str = "",
    ) -> None:
        usage = event_data.get("usage") or getattr(session, "last_usage", None)
        input_tokens, output_tokens, total_tokens = self._extract_usage_numbers(usage)
        if total_tokens <= 0:
            estimated_output = self._estimate_tokens_from_text(collected_text)
            total_tokens = estimated_output
            output_tokens = estimated_output
        latency_ms = int(event_data.get("latency_ms") or getattr(session, "last_latency_ms", 0) or 0)
        llm_calls = int(event_data.get("llm_calls") or getattr(session, "last_llm_calls", 0) or 0)

        def _run():
            import time
            for attempt in range(3):
                try:
                    with self.storage.session_factory() as db:
                        db.add(
                            AgentUsageEventModel(
                                user_id=user.id if user is not None else None,
                                agent_profile_id=agent_profile_id,
                                session_id=session.session_id,
                                model_name=str(event_data.get("model") or self.settings.openai_model),
                                response_mode=response_mode,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                total_tokens=total_tokens,
                                llm_calls=llm_calls,
                                tool_calls=len(tool_names),
                                tool_names_json=dump_json(tool_names),
                                latency_ms=latency_ms,
                            )
                        )
                        db.commit()
                    return
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise
        await asyncio.to_thread(_run)

    async def stream_chat(self, request: AgentStreamRequest, user: UserModel | None = None) -> AsyncIterator[dict[str, Any]]:
        # Restore agent_profile_id and response_mode from stored session metadata
        # so that page-refreshed sessions correctly resolve the right tools.
        if request.session_id and user is not None:
            stored = await self.storage.describe(request.session_id)
            if stored:
                meta = stored.get("metadata") or {}
                if request.agent_profile_id is None:
                    stored_id = meta.get("agent_profile_id")
                    if isinstance(stored_id, int) and stored_id > 0:
                        request.agent_profile_id = stored_id
                stored_mode = meta.get("response_mode")
                if isinstance(stored_mode, str) and stored_mode in ("general", "ppt", "website"):
                    request.response_mode = stored_mode

        runtime_profile = self._resolve_runtime_profile(request, user)
        response_mode = runtime_profile.response_mode
        ppt_mode = response_mode == "ppt"

        # 提前设置 user context，确保 register_external_tools 能获取 user_id
        if user is not None:
            set_current_user_id(user.id)
            set_ext_user_id(user.id)

        agent = self._get_agent(runtime_profile)

        _logger.info(
            "stream_chat start: session=%s mode=%s profile=%s msg_len=%d files=%d",
            request.session_id or "(new)",
            response_mode,
            runtime_profile.slug,
            len(request.message),
            len(request.files or ()),
        )
        if user is not None:
            await self.ensure_session_access(request, user)
        await self._load_session_if_needed(agent, request)

        # 记录用户输入到补全缓存
        if user is not None and request.message:
            try:
                from app.services.cache_service import get_cache_service
                await get_cache_service().add_user_input(user.id, request.message)
                await get_cache_service().add_global_input(request.message)
            except Exception:
                pass

        # Inject design system catalog for PPT mode
        message = request.message
        if ppt_mode:
            message = self._inject_design_catalog(message)
            edit_hint = await self._get_edit_hint(request.session_id)
            if edit_hint:
                message = message + edit_hint
            # Phase-specific injection — deferred to after session creation (see below)

        website_mode = response_mode == "website"
        if website_mode:
            message = self._inject_website_catalog(message)

        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=runtime_profile.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
        )
        self._normalize_session_limits(
            session,
            response_mode=response_mode,
            requested_max_steps=request.max_steps,
            profile_max_steps=runtime_profile.max_steps,
        )
        metadata = getattr(session, "metadata", {}) or {}
        metadata.update(
            {
                "user_id": user.id if user is not None else None,
                "user_email": user.email if user is not None else None,
                "user_name": user.name if user is not None else None,
                "response_mode": response_mode,
                "agent_profile_id": runtime_profile.profile_id,
                "agent_profile_name": runtime_profile.name,
                "agent_profile_slug": runtime_profile.slug,
            }
        )
        session.metadata = metadata
        if user is not None:
            await self.storage.assign_owner(session.session_id, user.id)
        await self.storage.assign_agent_profile(session.session_id, runtime_profile.profile_id)
        await self.storage.save_meta(session)
        approval_queue = self.approval_manager.subscribe(session.session_id)
        set_email_session_id(session.session_id)
        set_data_session_id(session.session_id)
        restore_website_dir_for_session(session.session_id)
        if user is not None:
            set_current_user_id(user.id)
            set_ext_user_id(user.id)
        _current_session_id.set(session.session_id)

        yield {
            "event": "session",
            "data": self._session_payload(session),
        }
        yield {
            "event": "run_status",
            "data": {
                "session_id": session.session_id,
                "phase": "thinking",
                "label": "大模型正在思考",
            },
        }

        runtime_queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        collected_text = ""
        saw_text_delta = False
        tool_names: list[str] = []
        usage_recorded = False

        # 注入用户记忆上下文（异步调用）
        if user is not None and not ppt_mode and not website_mode:
            try:
                from app.services.memory_service import get_memory_service
                memory_context = await get_memory_service().get_memory_context(user.id, request.message)
                if memory_context:
                    _logger.info(f"Injecting memory context for user {user.id}: {memory_context[:100]}...")
                    message = memory_context + "\n\n---\n\n" + message
                else:
                    _logger.info(f"No memory context found for user {user.id}")
            except Exception as e:
                _logger.warning(f"Memory context injection failed: {e}")

        async def produce_events() -> None:
            nonlocal message
            try:
                # message 变量已经包含记忆注入或设计目录注入
                # 如果有文件附件，追加文件描述
                if request.files:
                    file_desc = self._build_user_message(request)
                    if file_desc != request.message:
                        message = message + "\n\n" + file_desc
                user_message = message
                _logger.info(f"produce_events: starting, user_msg_len={len(user_message)}, context_msgs={len(getattr(session.context, '_messages', []))}")
                event_count = 0
                async for event in agent.stream_events(user_message, session=session):
                    event_count += 1
                    await runtime_queue.put(event)
                _logger.info(f"produce_events: done, events={event_count}, context_msgs={len(getattr(session.context, '_messages', []))}")
            except Exception as e:
                _logger.error(f"produce_events: exception: {e}", exc_info=True)
                raise
            finally:
                try:
                    if hasattr(session, "system_prompt"):
                        # Shield to ensure DB write completes even when the
                        # producer task is cancelled by client disconnecting
                        # the SSE stream, so connections are returned to the pool.
                        _logger.info(f"produce_events finally: saving meta for session {session.session_id}")
                        await asyncio.shield(self.storage.save_meta(session))
                        # 保存消息到数据库（wuwei 的 AgentSession 只在内存中存储消息）
                        _logger.info(f"produce_events finally: persisting messages for session {session.session_id}")
                        await asyncio.shield(self._persist_session_messages(session))
                        _logger.info(f"produce_events finally: done for session {session.session_id}")
                except asyncio.CancelledError:
                    _logger.warning(f"produce_events finally: cancelled for session {session.session_id}")
                except Exception as e:
                    _logger.warning(f"produce_events finally: error for session {session.session_id}: {e}", exc_info=True)
                finally:
                    await runtime_queue.put(None)

        producer = asyncio.create_task(produce_events())
        runtime_task = asyncio.create_task(runtime_queue.get())
        approval_task = asyncio.create_task(approval_queue.get())

        # Keepalive: 每 15 秒发送一次注释防止连接超时
        KEEPALIVE_INTERVAL = 15
        loop = asyncio.get_running_loop()
        last_event_time = loop.time()

        try:
            while True:
                # 使用 timeout 避免无限等待，以便发送 keepalive
                done, _ = await asyncio.wait(
                    {runtime_task, approval_task},
                    timeout=KEEPALIVE_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # 如果没有事件且距上次事件超过 keepalive 间隔，发送 keepalive
                current_time = loop.time()
                if not done and (current_time - last_event_time) >= KEEPALIVE_INTERVAL:
                    yield {"event": "keepalive", "data": {"timestamp": int(current_time)}}
                    last_event_time = current_time
                    continue

                if done:
                    last_event_time = current_time

                if runtime_task in done:
                    event = runtime_task.result()
                    if event is None:
                        break

                    if event.type == "text_delta":
                        first_text_delta = not saw_text_delta
                        saw_text_delta = True
                        collected_text += event.data.get("content", "")
                        if ppt_mode:
                            if first_text_delta:
                                yield {
                                    "event": "run_status",
                                    "data": {
                                        "session_id": session.session_id,
                                        "phase": "generating_ppt",
                                        "label": "正在生成 PPT 内容与版式",
                                    },
                                }
                            runtime_task = asyncio.create_task(runtime_queue.get())
                            continue
                        if first_text_delta:
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "streaming",
                                    "label": "大模型正在输出",
                                },
                            }

                    if event.type == "tool_start":
                        tool_name = event.data.get("tool_name")
                        if isinstance(tool_name, str) and tool_name:
                            tool_names.append(tool_name)

                    if ppt_mode and event.type == "done":
                        visible_text = ""

                        _logger.info("ppt done: session=%s, creating artifact...", session.session_id)

                        artifact = await self._create_ppt_artifact(session.session_id)
                        _logger.info("ppt artifact result: session=%s, artifact=%s", session.session_id, "OK" if artifact else "None")
                        if artifact is not None:
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "rendering_ppt",
                                    "label": "正在渲染 PPT 预览",
                                },
                            }
                            yield {
                                "event": "artifact_ready",
                                "data": artifact,
                            }
                        else:
                            # 质量门失败，返回错误信息给用户
                            quality_errors = getattr(self.ppt_artifacts, '_last_quality_errors', [])
                            quality_warnings = getattr(self.ppt_artifacts, '_last_quality_warnings', [])
                            error_detail = "; ".join(quality_errors[:3]) if quality_errors else "未知原因"
                            _logger.warning(
                                "ppt artifact creation failed: session=%s, errors=%s",
                                session.session_id, quality_errors,
                            )
                            visible_text = f"PPT 预览生成失败：{error_detail}"
                        if visible_text:
                            yield {
                                "event": "delta",
                                "data": {
                                    "session_id": session.session_id,
                                    "content": visible_text,
                                },
                            }
                        yield {
                            "event": "run_status",
                            "data": {
                                "session_id": session.session_id,
                                "phase": "done",
                                "label": "本轮回复已完成",
                            },
                        }
                        mapped = self._map_agent_event(event, session)
                        if not usage_recorded:
                            await self._record_usage_event(
                                session=session,
                                request=request,
                                user=user,
                                event_data=event.data,
                                tool_names=tool_names,
                                response_mode=response_mode,
                                agent_profile_id=runtime_profile.profile_id,
                                collected_text=collected_text,
                            )
                            usage_recorded = True
                        if mapped is not None:
                            yield mapped
                        runtime_task = asyncio.create_task(runtime_queue.get())
                        continue

                    if website_mode and event.type == "done":
                        artifact = await self._create_website_artifact(
                            session.session_id, tool_names
                        )
                        if artifact is not None:
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "rendering_website",
                                    "label": "正在渲染网站预览",
                                },
                            }
                            yield {
                                "event": "artifact_ready",
                                "data": artifact,
                            }
                        if not usage_recorded:
                            await self._record_usage_event(
                                session=session,
                                request=request,
                                user=user,
                                event_data=event.data,
                                tool_names=tool_names,
                                response_mode=response_mode,
                                agent_profile_id=runtime_profile.profile_id,
                                collected_text=collected_text,
                            )
                            usage_recorded = True
                        yield {
                            "event": "run_status",
                            "data": {
                                "session_id": session.session_id,
                                "phase": "done",
                                "label": "本轮回复已完成",
                            },
                        }
                        mapped = self._map_agent_event(event, session)
                        if mapped is not None:
                            yield mapped
                        runtime_task = asyncio.create_task(runtime_queue.get())
                        continue

                    if event.type == "done":
                        reason = event.data.get("reason", "stop")
                        yield {
                            "event": "run_status",
                            "data": {
                                "session_id": session.session_id,
                                "phase": "done",
                                "label": "本轮回复已完成",
                            },
                        }
                        # 输出被截断时追加提示
                        if reason == "length":
                            yield {
                                "event": "delta",
                                "data": {
                                    "session_id": session.session_id,
                                    "content": (
                                        "\n\n---\n⚠️ **回复被截断**：模型输出已达到 token 上限，内容不完整。"
                                        "你可以发送「继续」让模型接着输出，或精简需求后重新提问。"
                                    ),
                                },
                            }
                            _logger.warning(
                                "Output truncated (finish_reason=length): session=%s tokens_used=%s",
                                session.session_id,
                                event.data.get("usage"),
                            )
                        if not usage_recorded:
                            await self._record_usage_event(
                                session=session,
                                request=request,
                                user=user,
                                event_data=event.data,
                                tool_names=tool_names,
                                response_mode=response_mode,
                                agent_profile_id=runtime_profile.profile_id,
                                collected_text=collected_text,
                            )
                            usage_recorded = True

                    if event.type == "error" and not usage_recorded:
                        _logger.warning(
                            "agent error event: session=%s error=%s tools=%s",
                            session.session_id,
                            event.data.get("message", "")[:200],
                            tool_names,
                        )
                        await self._record_usage_event(
                            session=session,
                            request=request,
                            user=user,
                            event_data=event.data,
                            tool_names=tool_names,
                            response_mode=response_mode,
                            agent_profile_id=runtime_profile.profile_id,
                            collected_text=collected_text,
                        )
                        usage_recorded = True

                    mapped = self._map_agent_event(event, session)
                    if mapped is not None:
                        yield mapped
                    runtime_task = asyncio.create_task(runtime_queue.get())

                # 检查决策工具队列（工具在 agent 内部执行时可能产生决策事件）
                from app.tools.decision_tools import get_decision_queue
                pending_decisions = get_decision_queue(session.session_id)
                for decision in pending_decisions:
                    yield {
                        "event": "user_decision",
                        "data": decision,
                    }

                if approval_task in done:
                    approval = approval_task.result()
                    func_name = approval.get("tool_name", "")
                    display_name_map = self._get_display_name_map()
                    approval["tool_name"] = display_name_map.get(func_name, func_name)
                    yield {
                        "event": "approval_required",
                        "data": approval,
                    }
                    approval_task = asyncio.create_task(approval_queue.get())
            # 对话结束时用 LLM 提取记忆（仅通用模式）
            _logger.info(f"Memory extraction conditions: user={user is not None}, collected_text_len={len(collected_text) if collected_text else 0}, ppt_mode={ppt_mode}, website_mode={website_mode}, message={request.message[:50] if request.message else ''}")
            if user is not None and request.message and not ppt_mode and not website_mode:
                try:
                    from app.services.memory_service import get_memory_service
                    # 使用用户消息和 AI 回复进行记忆提取（异步非阻塞）
                    ai_response = collected_text[:500] if collected_text else ""
                    asyncio.create_task(
                        get_memory_service().extract_and_save_memories(
                            user.id,
                            request.message,
                            ai_response,
                        )
                    )
                    _logger.info(f"Memory extraction task created for user {user.id}")
                except Exception as e:
                    _logger.warning(f"Memory extraction task creation failed: {e}")

        finally:
            _logger.info(
                "stream_chat end: session=%s mode=%s tools=%s text_len=%d",
                session.session_id,
                response_mode,
                tool_names,
                len(collected_text),
            )
            self.approval_manager.unsubscribe(session.session_id, approval_queue)
            for task in (runtime_task, approval_task):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            if not producer.done():
                producer.cancel()
                # Shield to keep the producer's DB cleanup (save_meta) from
                # being cancelled alongside the SSE stream — prevents leaked
                # connections when the client disconnects mid-stream.
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(producer)
            else:
                with contextlib.suppress(Exception):
                    producer.result()

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        reason: str | None = None,
        current_user: UserModel | None = None,
    ) -> dict[str, Any]:
        if current_user is not None:
            await self._ensure_record_owner(approval_id, ApprovalModel, current_user)
        return await self.approval_manager.decide(approval_id, status=status, reason=reason)

    async def get_session_state(self, session_id: str) -> dict[str, Any]:
        stored = await self.storage.describe(session_id)
        if stored is None:
            stored = {"session_id": session_id, "storage": "sqlalchemy", "message_count": 0}
        stored["pending_approvals"] = await self.approval_manager.get_pending(session_id)
        return stored

    async def get_ppt_artifact(self, artifact_id: str, current_user: UserModel | None = None) -> dict[str, Any] | None:
        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, current_user)
        return await self.ppt_artifacts.get(artifact_id)

    async def export_pptx(
        self,
        artifact_id: str,
        *,
        canvas_format: str | None = None,
        theme: str | None = None,
        use_native_shapes: bool = True,
        use_compat_mode: bool = False,
        transition: str | None = None,
        animation: str | None = None,
        enable_notes: bool = True,
        current_user: UserModel | None = None,
    ) -> bytes:
        """Export a PPT artifact as a native .pptx file.

        Converts the SVG pages stored in the artifact into DrawingML shapes
        and assembles a complete PowerPoint file.
        """
        import logging
        import tempfile
        from pathlib import Path
        from app.services.ppt.svg_to_pptx import create_pptx_with_native_svg
        from app.services.ppt.svg_finalize.embed_icons import process_svg_file as _embed_icons
        from app.services.ppt.svg_finalize.align_embed_images import align_and_embed_images_in_svg as _align_images
        from app.services.ppt.svg_finalize.flatten_tspan import flatten_text_with_tspans as _flatten_tspan_text
        from app.services.ppt.svg_finalize.svg_rect_to_path import process_svg as _fix_rounded
        from xml.etree import ElementTree as ET

        _logger = logging.getLogger("ppt_export")

        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, current_user)

        artifact = await self.ppt_artifacts.get(artifact_id)
        if artifact is None:
            raise FileNotFoundError(f"PPT artifact '{artifact_id}' not found")

        svgs = self.ppt_artifacts.extract_svgs_from_artifact(artifact)
        if not svgs:
            raise ValueError("Artifact contains no SVG slides to export")

        _logger.info(f"Exporting artifact {artifact_id}: {len(svgs)} slides, "
                     f"native_shapes={use_native_shapes}, compat={use_compat_mode}")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            svg_paths: list[Path] = []
            for i, svg_content in enumerate(svgs):
                svg_path = tmpdir_path / f"slide{i + 1}.svg"
                # Sanitize: escape raw < and & in text content
                from app.services.ppt_artifact_service import sanitize_svg_xml
                svg_content = sanitize_svg_xml(svg_content)
                svg_path.write_text(svg_content, encoding="utf-8")
                svg_paths.append(svg_path)

            # SVG post-processing (icon embedding + image alignment + text flatten + rounded rect fix)
            _icons_dir = DATA_DIR / "icons"
            _processed = 0
            for svg_path in svg_paths:
                _processed += _embed_icons(svg_path, _icons_dir, dry_run=False, verbose=False)
                _processed += _align_images(svg_path, dry_run=False, verbose=False)[0]
                try:
                    tree = ET.parse(str(svg_path))
                    if _flatten_tspan_text(tree):
                        tree.write(str(svg_path), encoding="unicode", xml_declaration=False)
                        _processed += 1
                except Exception:
                    _logger.warning("tspan flatten failed for %s", svg_path.name, exc_info=True)
                try:
                    raw = svg_path.read_text(encoding="utf-8")
                    new_content, count = _fix_rounded(raw, verbose=False)
                    if count:
                        svg_path.write_text(new_content, encoding="utf-8")
                        _processed += count
                except Exception:
                    _logger.warning("rounded rect fix failed for %s", svg_path.name, exc_info=True)
            _logger.info(f"SVG post-processing: {_processed} changes across {len(svg_paths)} slides")

            output_path = tmpdir_path / "output.pptx"
            create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format=canvas_format or "ppt169",
                verbose=False,
                transition=transition or "fade",
                use_native_shapes=use_native_shapes,
                use_compat_mode=use_compat_mode,
                animation=animation or "mixed",
                enable_notes=enable_notes,
                notes={},
            )

            return output_path.read_bytes()

    async def list_user_sessions(self, user_id: int) -> list[dict[str, Any]]:
        return await self.storage.list_user_sessions(user_id)

    async def delete_session(self, session_id: str, current_user: UserModel) -> None:
        owner_id = await self.storage.get_owner_id(session_id)
        if owner_id is not None and owner_id != current_user.id and current_user.role != "admin":
            raise PermissionError("当前用户无权删除该会话。")
        await self.storage.delete(session_id)


_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService(get_settings())
    return _agent_service


def clear_agent_service_cache() -> None:
    global _agent_service
    _agent_service = None




