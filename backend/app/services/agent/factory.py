"""AgentFactory：Agent 实例 / 中间件栈 / 工具注册表的构建。

从原 ``app/services/agent_service.py`` 整段搬移（TECH-DEBT-2026-09 拆分）：
- LenientHitlMiddleware / SkillInstructionMiddleware / ThinkingHistoryCompatibilityMiddleware
- _build_tool_registry / _build_middleware_stack / _get_agent / _build_async_sub_agents

本类为 Mixin：由 ``service.AgentService`` 组合继承，依赖宿主提供的属性
（self.settings / self.approval_manager / self._agents Agent 缓存）。

**并发工具执行不再需要 monkey-patch。**
这里曾有一份 230 行的 ``AgentRunner.stream_events`` 整体重写（TECH-DEBT），
目的是让安全工具（``is_concurrency_safe=True``）并发执行、非安全工具串行。
wuwei 3.2.1 的 ``ToolExecutor.execute(tool_calls, concurrent=True)`` 已原生
实现同样的分批并发逻辑（``_execute_batched``，注释里明说是借鉴 AgentScope 的
``_batch_tool_calls`` 设计），上游 runner 默认就是 ``concurrent=True``。

实测（两个各耗时 0.5s 的安全工具）：补丁版 0.504s，上游原生 0.505s，
事件序列与数据字段完全一致 —— 所以补丁已删除。

**不要再写这个补丁。** 原因：它整段复制了上游的执行循环（LLM 调用、中间件
生命周期、事件产出格式），上游一改签名或加特性，这份拷贝就会静默落后 ——
本轮升级时上游新增的 ``side_effect`` / ``requires_approval`` 事件字段、
审批决策绑定、interrupt 挂起能力，补丁版本统统拿不到。
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

from app.services.agent_profile_service import RuntimeAgentProfile
from app.services.tool_config_service import TOOL_CATALOG
from app.services.agent.wuwei_patches import BatchSafeMiddlewareProxy, PatchedAgent

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


class LenientHitlMiddleware(HitlMiddleware):
    """宽松的 HITL 中间件：用户拒绝时不抛异常，替换为拒绝消息让 LLM 继续。

    在此基础上支持会话级三档审批模式（ask / auto / full）：

    - ``auto``：只读工具（含 file 的读类子操作）自动放行，写/执行仍逐次确认
    - ``full``：``auto_approve_tools`` 含 ``*`` 哨兵时全部放行（仅管理员可用）
    """

    def __init__(self, *args, approval_mode: str = "auto", approval_timeout: float = 300.0, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.approval_mode = normalize_approval_mode(approval_mode)
        # R-15：审批等待必须有上限。上游 ``HitlMiddleware.before_tool`` 直接
        # ``await self.approval_provider(tool_call)``，没有超时也没有取消通道；
        # 审批期间还持有 session.lock，用户关掉审批页面就会把整个会话卡住。
        self.approval_timeout = float(approval_timeout)

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
        try:
            approved = await asyncio.wait_for(
                self.approval_provider(tool_call), timeout=self.approval_timeout
            )
        except asyncio.TimeoutError:
            # 审批超时按「拒绝」处理：宁可让模型换方案，也不要把会话永久卡住。
            _logger.warning(
                "审批等待超过 %.0f 秒，按拒绝处理：tool=%s",
                self.approval_timeout,
                tool_name,
            )
            approved = False
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

    def _ensure_llm_configured(self) -> None:
        """校验「至少有某条路能拿到凭据」。

        不能再看 ``OPENAI_API_KEY``：提供商可以自带 API Key，企业网关类
        提供商则用 Cookie 登录态，两者都与环境变量无关。
        """
        from app.services.llm_providers.spec import resolve_active_provider

        spec = resolve_active_provider()
        if spec.api_key or spec.needs_cookie:
            return
        raise RuntimeError(
            "未配置任何可用的 AI 提供商，也没有 OPENAI_API_KEY。"
            "请先到「管理后台 → 系统设置 → AI 提供商」配置后再调用 /agent/stream。"
        )

    def _get_agent(self, profile: RuntimeAgentProfile) -> Agent:
        injected = getattr(self, "_agent", None)
        if injected is not None:
            return injected
        self._ensure_llm_configured()
        import hashlib
        from app.services.llm_providers.spec import (
            resolve_active_provider,
            resolve_model_for_role,
        )

        provider = resolve_active_provider()
        # 用途绑定会改变实际模型，而 provider.model 不反映这个映射 ——
        # 不把它算进缓存键的话，管理员改完「对话用哪个模型」后会一直复用
        # 旧 agent（界面上显示已改，实际没生效）。
        effective_model = resolve_model_for_role(provider, "chat")
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
            # 提供商决定 LLM 实例本身。不参与缓存键的话，管理员切换提供商后
            # 旧 agent（连同旧网关）会被一直复用，界面显示已切换但实际没生效。
            provider.slug,
            effective_model,
        )
        cached = self._agents.get(cache_key)
        if cached is not None:
            return cached

        from app.services.llm_factory import build_llm_for_user

        # role="chat"：主对话用「对话」用途绑定的模型，没有绑定时退回
        # 提供商配置的模型。model 传 None 以避免用全局默认覆盖提供商配置。
        llm = build_llm_for_user(
            None,
            max_tokens=self.settings.agent_max_tokens,
            timeout=self.settings.llm_timeout,
            model=None,
            role="chat",
        )
        tools, ext_instruction = self._build_tool_registry(profile)
        middleware_stack = self._build_middleware_stack(profile, llm, tool_registry=tools)

        # 追加外部系统指引到 system prompt
        system_prompt = profile.system_prompt
        if ext_instruction:
            system_prompt = f"{system_prompt}{ext_instruction}"

        agent = PatchedAgent(
            llm=llm,
            tools=tools,
            default_system_prompt=system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            # BatchSafeMiddlewareProxy：上游的并发判定要求中间件栈里没有任何
            # before_tool / after_tool 钩子，本项目默认就装了审批中间件，
            # 于是「打开并行开关 → 并发被静默关闭，用户毫无感知」。
            # 代理只对上游的判定隐藏钩子，实际执行由 BoundedToolExecutor
            # 在批处理路径上补齐（审批语义不丢）。
            middleware=BatchSafeMiddlewareProxy(middleware_stack),
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

        if profile.response_mode == "office":
            from app.tools.sheet_tools import register_sheet_tools as _register_sheet_tools
            _register_sheet_tools(registry)
            from app.tools.doc_tools import register_doc_tools as _register_doc_tools
            _register_doc_tools(registry)

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
        import inspect
        for tool_name, tool in list(registry._tools.items()):
            if not inspect.iscoroutinefunction(tool.handler):
                # 同步 handler → 用 to_thread 包装
                original_handler = tool.handler
                async def _async_wrapper(*args, _orig=original_handler, **kwargs):
                    return await asyncio.to_thread(_orig, *args, **kwargs)
                tool.handler = _async_wrapper

        return registry, ext_instruction
