"""AgentFactory：Agent 实例与工具注册表的构建（全新系统，wuwei 已退役）。

原 wuwei 路径（PatchedAgent / 中间件栈 / wuwei_patches.py）已整体删除；
唯一的引擎是 ``langgraph_engine.LangGraphAgent``，原先挂在中间件栈上的
语义（审批 / 配对修复 / 思考历史兼容 / Skill 注入 / 压缩 / 预算 / 子代理）
全部移植进引擎本身（见 ``langgraph_engine/engine.py`` 与 ``native/``）。

本类为 Mixin：由 ``service.AgentService`` 组合继承，依赖宿主提供的属性
（self.settings / self.approval_manager / self._agents Agent 缓存）。
"""

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from app.core.data_path import is_external_api_call
from app.services.agent.native.async_sub_agent import AsyncSubAgent, AsyncSubAgentManager
from app.services.agent.native.plugins import PluginContext
from app.services.agent.native.tool_registry import ToolRegistry
from app.services.agent_profile_service import RuntimeAgentProfile
from app.services.tool_config_service import TOOL_CATALOG

if TYPE_CHECKING:
    from app.services.agent.native.budget import Budget

_logger = logging.getLogger("agent")

#: 企业 Cookie 型提供商（provider_type）。这类提供商走账号池，取号逻辑在
#: ``credentials.acquire``。
_ENTERPRISE_COOKIE = "enterprise_cookie"

# 特殊工具名：用户拒绝时替换原工具调用，让 LLM 收到明确的拒绝消息
_REJECTED_TOOL_NAME = "__tool_rejected__"

# 上游 runner 达到步骤上限时写进上下文的原文。引擎在截断时写入这条合成回复，
# 下一轮由 thinking-compat 剔除 —— 面向用户的说法在序列化层（agent.py）替换。
MAX_STEPS_LIMIT_MESSAGE = "任务未完成，已达到最大步骤限制。"

SKILL_INSTRUCTION = (
    "你有可用的 Skill（专门技能），它们是处理特定领域任务的增强能力。\n"
    "遇到可能匹配的请求时，调用 `list_skills` 查看可用技能摘要。\n"
    "如果某个技能描述与用户任务相关，调用 `load_skill` 加载其完整指令并遵循执行。\n"
    "技能正文已包含核心知识，**不要逐个读取 references 文件**，除非正文明确要求读取某个具体文件。\n"
    "references 是补充资料，不是必须全部加载的。"
)


def _unregister_if_exists(registry: ToolRegistry, name: str) -> None:
    """注册表拒绝重名，注册前先移除旧工具。"""
    existing = registry.get(name)
    if existing is not None:
        registry.unregister(existing)


def _unregister_tool_group(registry: ToolRegistry, group_name: str) -> None:
    """按 TOOL_CATALOG 的组名注销工具（含 sub_tools）。"""
    catalog = TOOL_CATALOG.get(group_name)
    if catalog is None:
        return
    for tool_name in catalog.get("sub_tools", {}) or [group_name]:
        _unregister_if_exists(registry, tool_name)


def _signature_group_enabled(
    signature: list[tuple[str, bool, Any]],
    group_name: str,
    *,
    default: bool = True,
) -> bool:
    """signature 里某工具组的启用状态；未配置按 default。"""
    for name, enabled, _ in signature:
        if name == group_name:
            return enabled
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

    def _get_agent(self, profile: RuntimeAgentProfile) -> Any:
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

        # 企业网关：按轮换窗口让缓存失效，账号才会轮换（换号必须重建网关）
        rotation_bucket: int | None = None
        if provider.provider_type == _ENTERPRISE_COOKIE:
            rotation_bucket = self._credential_rotation_bucket()
        # 工作流签名：启停/编辑工作流会改变工具集，必须进缓存键
        workflows_sig = None  # workflow 已下线（签名机制保留给未来的动态工具源）
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
            bool(getattr(profile, "plan_mode", False)),
            getattr(profile, "approval_mode", "auto"),
            bool(getattr(profile, "is_admin_actor", False)),
            provider.slug,
            effective_model,
            workflows_sig,
            rotation_bucket,
            is_external_api_call(),
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
        self._sub_agent_llm = llm  # 子代理复用主对话网关

        # 追加外部系统指引到 system prompt
        system_prompt = profile.system_prompt
        if ext_instruction:
            system_prompt = f"{system_prompt}{ext_instruction}"

        from app.services.agent.langgraph_engine import LangGraphAgent
        from app.services.agent.langgraph_engine.tools_adapter import (
            EngineApprovalPolicy,
            InterruptOnConfig,
        )
        from app.services.approval_policy import normalize_approval_mode

        # 声明式 interrupt_on —— profile 审批名单里的每个工具一份
        # InterruptOnConfig（决策集含人工代答），其余工具自动放行。
        approval_mode = normalize_approval_mode(getattr(profile, "approval_mode", None))
        if approval_mode == "full" and getattr(profile, "is_admin_actor", False):
            approval_mode = "auto"
            interrupt_on: dict[str, bool | InterruptOnConfig] = {}
            auto_approve: set[str] = {"*"}
        else:
            approval_mode = "ask" if approval_mode == "full" else approval_mode
            approval_tools = set(profile.approval_tools)
            auto_approve = set()
            interrupt_on = {
                t.name: InterruptOnConfig() for t in tools.list_tools() if t.name in approval_tools
            }
        policy = EngineApprovalPolicy(
            approval_manager=self.approval_manager,
            auto_approve_tools=auto_approve or None,
            approval_mode=approval_mode,
            approval_timeout=float(self.settings.hitl_timeout_seconds),
            interrupt_on=interrupt_on or None,
        )

        # 预算断路（原 BudgetMiddleware 语义，移植进引擎）
        budget = self._build_run_budget()

        # 上下文压缩（原 ContextCompressionMiddleware，移植进引擎）
        compressor = None
        if self.settings.context_compression_enabled:
            from app.services.agent.native.context_compression import ContextCompressor

            window = max(1, self.settings.context_window_tokens)
            per_turn = max(1, self.settings.context_tokens_per_turn)
            trigger = min(
                self.settings.context_compress_after_turns * per_turn,
                max(1, window // 2),
            )
            compressor = ContextCompressor(
                llm=llm,
                trigger_tokens=trigger,
                keep_recent_turns=self.settings.context_keep_recent_turns,
                max_tokens=window,
            )

        # 异步子代理（原 AsyncSubAgentMiddleware，移植进引擎并自执行）
        sub_agent_manager = None
        if self.settings.async_sub_agents_enabled:
            sub_agents = self._build_async_sub_agents()
            if sub_agents:
                sub_agent_manager = AsyncSubAgentManager(sub_agents, run_fn=self._run_sub_agent)
                # 注册 4 个管理工具（start/check/cancel/list）
                from app.services.agent.native.tool_registry import ToolParameters, Tool as _Tool

                for schema in sub_agent_manager.tool_schemas():
                    # tool_schemas 返回 {"type":"function","function":{...}}（OpenAI 格式）
                    fn_spec = schema["function"]
                    tool = _Tool(
                        name=fn_spec["name"],
                        description=fn_spec.get("description", ""),
                        parameters=ToolParameters.model_validate(fn_spec.get("parameters") or {"type": "object"}),
                        handler=self._make_sub_agent_handler(sub_agent_manager, fn_spec["name"]),
                        side_effect=fn_spec["name"] == "start_async_task",
                        requires_approval=False,
                    )
                    try:
                        tools.register(tool)
                    except ValueError:
                        pass  # 重名（不应发生）

        # Skill 工具（原 wuwei skill 插件，移植为 SkillToolBox）
        skill_toolbox = None
        if "skill" in profile.builtin_tools and profile.skills:
            from app.services.agent.native.fs_provider import FileSystemSkillProvider
            from app.services.agent.native.skill import SkillManager
            from app.services.agent.native.builtin.skill_tools import SkillToolBox

            skill_manager = SkillManager(
                [FileSystemSkillProvider(skill.root_dir) for skill in profile.skills]
            )
            skill_toolbox = SkillToolBox(skill_manager)
            skill_toolbox.register(tools)

        agent = LangGraphAgent(
            llm=llm,
            tools=tools,
            default_system_prompt=system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            approval_policy=policy,
            model_name=effective_model,
            skill_toolbox=skill_toolbox,
            async_sub_agents=sub_agent_manager,
            budget=budget,
            compressor=compressor,
        )
        self._agents[cache_key] = agent
        return agent

    @staticmethod
    def _make_sub_agent_handler(manager: Any, name: str):
        """子代理管理工具的 handler（闭包绑定 manager 与工具名）。"""

        async def _handler(**kwargs: Any) -> dict:
            from app.core.data_path import _current_session_id

            import json as _json

            result = await manager.handle_tool(
                name, kwargs, _current_session_id.get()
            )
            return _json.loads(result)

        return _handler

    async def _run_sub_agent(self, sub_agent: Any, task: str) -> dict:
        """用本引擎执行子代理（AsyncSubAgentManager 的 run_fn 回调）。"""
        from app.services.agent.langgraph_engine import LangGraphAgent
        from app.services.agent.native.tool_registry import ToolRegistry
        from app.services.agent.native.plugins import PluginContext

        registry = ToolRegistry()
        ctx = PluginContext(tool_registry=registry)
        for plugin in (sub_agent.tools or []):
            # 子代理工具已由 factory 在构建时注入（list[Tool]）
            registry.register(plugin)

        # 子代理用同一个网关（会话独立、无审批中间件，直接执行）
        agent = LangGraphAgent(
            llm=self._sub_agent_llm,
            tools=registry,
            default_system_prompt=sub_agent.system_prompt,
            default_max_steps=sub_agent.max_steps,
        )
        session = agent.create_session(system_prompt=sub_agent.system_prompt)
        usage_total: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        llm_calls = 0
        steps = 0
        final_text = ""
        async for event in agent.stream_events(task, session=session):
            if event.type == "done":
                usage_total = event.data.get("usage") or usage_total
                llm_calls = event.data.get("llm_calls", 0)
            elif event.type == "tool_start":
                steps += 1
            elif event.type == "text_delta":
                final_text += event.data.get("content", "")
        usage_total["steps"] = steps
        return {
            "result": final_text.strip() or "(子代理无文本输出)",
            "status": "completed",
            "usage": usage_total,
            "llm_calls": llm_calls,
            "steps": steps,
        }

    def _credential_rotation_bucket(self) -> int:
        """账号池轮换窗口的编号。

        返回「当前时间落在第几个窗口」。把这个值放进 Agent 缓存键，
        跨窗口后缓存自动失效 → 重建 Agent 时会借到另一个账号 → 配额被
        摊到多个号上。窗口长度取 ``LLM_CREDENTIAL_ROTATION_SECONDS``。
        """
        try:
            window = int(getattr(self.settings, "llm_credential_rotation_seconds", 300))
        except (AttributeError, TypeError, ValueError):
            window = 300
        if window <= 0:
            return 0
        import time as _time

        return int(_time.time() // window)

    def _build_run_budget(self) -> "Budget | None":
        """按配置组装 run 级 Budget；未启用 / 配置非法时返回 None。

        刻意**不设 max_steps**：session.max_steps 的步数超限由引擎循环优雅收尾
        （done 事件 + 步数上限合成回复），放进 Budget 会让超限从「优雅收尾」
        变成 BudgetExhausted 错误，语义不对。
        """
        max_tokens = self.settings.agent_budget_max_tokens
        max_cost = self.settings.agent_budget_max_cost_usd
        if max_tokens is None and max_cost is None:
            return None
        try:
            from app.services.agent.native.budget import Budget

            return Budget(
                max_tokens=max_tokens,
                max_cost_usd=max_cost,
                on_exhausted=self.settings.agent_budget_on_exhausted,
            )
        except Exception as exc:  # noqa: BLE001 —— 配置降级
            _logger.warning("AGENT_BUDGET_* 配置非法，run 级预算断路未启用: %s", exc)
            return None

    def _build_async_sub_agents(self) -> list[AsyncSubAgent]:
        """构建异步子代理列表（工具集在构建时由 builtin 插件注入）。"""
        sub_agents: list[AsyncSubAgent] = []

        # 1. 代码分析子代理
        code_registry = ToolRegistry()
        code_ctx = PluginContext(tool_registry=code_registry)
        try:
            from app.services.agent.native.builtin import calc as calc_mod, git as git_mod, python as python_mod

            calc_mod.setup(code_ctx)
            python_mod.setup(code_ctx)
            git_mod.setup(code_ctx)
        except Exception as e:
            _logger.warning("Sub-agent code_analyst plugin setup failed: %s", e)

        sub_agents.append(
            AsyncSubAgent(
                name="code_analyst",
                description="代码分析与执行：运行 Python 脚本、数学计算、Git 操作。适合需要后台运行代码或分析的场景。",
                system_prompt=(
                    "你是一个代码分析助手。你可以执行 Python 脚本、进行数学计算、查看 Git 状态。"
                    "请直接运行代码并返回结果，不要解释代码本身。"
                    "返回时用简洁的格式说明执行结果。"
                ),
                tools=list(code_registry.list_tools()),
                max_steps=10,
                inherit_context=False,
            )
        )

        # 2. 文件处理子代理
        file_registry = ToolRegistry()
        file_ctx = PluginContext(tool_registry=file_registry)
        try:
            from app.services.agent.native.builtin import file as file_mod, text as text_mod

            file_mod.setup(file_ctx)
            text_mod.setup(file_ctx)
        except Exception as e:
            _logger.warning("Sub-agent file_processor plugin setup failed: %s", e)

        sub_agents.append(
            AsyncSubAgent(
                name="file_processor",
                description="文件处理：读取、搜索、整理文件内容。适合需要在后台批量处理文件的场景。",
                system_prompt=(
                    "你是一个文件处理助手。你可以读取文件、搜索文本、整理内容。"
                    "工作时保持高效，直接返回处理结果。"
                ),
                tools=list(file_registry.list_tools()),
                max_steps=8,
                inherit_context=False,
            )
        )

        return sub_agents

    @staticmethod
    def _build_tool_registry(profile: RuntimeAgentProfile) -> tuple[ToolRegistry, str]:
        # "file" 一律排除内置插件：所有模式统一改用「作用域文件工具」
        # （见下方 register_website_file_tools）。内置插件的 workspace 默认是
        # "."，会被解析成进程 cwd（容器里 /app），导致 AI 看到源码与别人的数据。
        _exclude = {"skill", "email", "file"}
        builtin_tools = [name for name in profile.builtin_tools if name not in _exclude]

        registry = ToolRegistry()
        ctx = PluginContext(tool_registry=registry)

        # 计划模式：只保留只读工具，从源头杜绝误操作（而非事后拦截）
        if getattr(profile, "plan_mode", False):
            from app.services.approval_policy import plan_mode_blocked_tools

            blocked = set(plan_mode_blocked_tools(list(profile.builtin_tools)))
            if blocked:
                _logger.info("plan mode: blocking %d tools: %s", len(blocked), sorted(blocked))
            builtin_tools = [name for name in builtin_tools if name not in blocked]
            _exclude |= blocked

        # 按需加载内置插件（自有移植版本）
        from app.services.agent.native.builtin import PLUGIN_MAP

        for name in builtin_tools:
            mod = PLUGIN_MAP.get(name)
            if mod is not None:
                mod.setup(ctx)

        if "email" in profile.builtin_tools:
            from app.tools.email_tools import register_email_tools

            register_email_tools(registry)

        # 外部系统工具：根据 agent profile 关联的外部系统动态注册
        ext_instruction = ""
        if profile.external_system_ids:
            from app.db.session import create_db_session
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

        decision_enabled = _signature_group_enabled(profile.signature, "decision", default=True)
        if decision_enabled:
            from app.tools.decision_tools import register_decision_tools

            register_decision_tools(registry)

        memory_enabled = _signature_group_enabled(profile.signature, "memory", default=True)
        if memory_enabled:
            from app.tools.memory_tools import register_memory_tools

            register_memory_tools(registry)

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

        # 数据可视化 / 数据分析 / A2UI / 文生图（所有模式可用）
        from app.tools.chart_render_tools import register_chart_render_tools as _register_chart_render

        _register_chart_render(registry)

        from app.tools.data_analysis_tools import register_data_analysis_tools as _register_data_analysis

        _register_data_analysis(registry)

        from app.services.a2ui import register_a2ui_tools as _register_a2ui

        _register_a2ui(registry)

        from app.tools.image_gen_tools import register_image_gen_tools as _register_image_gen

        _register_image_gen(registry)

        if profile.response_mode == "ppt":
            from app.tools.chart_tools import register_chart_tools as _register_chart_tools
            from app.tools.icon_tools import register_icon_tools as _register_icon_tools
            from app.tools.image_tools import register_image_tools as _register_image_tools
            from app.tools.ppt_tools import register_ppt_tools as _register_ppt_tools
            from app.tools.pptx_reverse_tools import register_pptx_reverse_tools as _register_pptx_reverse
            from app.tools.quality_checker_tools import register_quality_checker_tools as _register_qc_tools
            from app.tools.template_tools import register_template_tools as _register_template_tools

            _register_icon_tools(registry)
            _register_ppt_tools(registry)
            _register_chart_tools(registry)
            _register_qc_tools(registry)
            _register_pptx_reverse(registry)
            _register_template_tools(registry)
            _register_image_tools(registry)

        if profile.response_mode == "website":
            from app.tools.website_tools import register_website_tools as _register_website_tools

            _register_website_tools(registry)

        # 作用域文件工具：所有模式共用（workspace 解析到会话工作区）
        from app.tools.website_file_tools import register_website_file_tools as _register_scoped_file_tools

        _register_scoped_file_tools(registry)

        if profile.response_mode == "office":
            from app.tools.doc_tools import register_doc_tools as _register_doc_tools
            from app.tools.sheet_tools import register_sheet_tools as _register_sheet_tools

            _register_sheet_tools(registry)
            _register_doc_tools(registry)

        # MCP 工具集成：按 profile 过滤（「按需挂载」）
        try:
            from app.services.mcp_service import get_mcp_service

            mcp_svc = get_mcp_service()
            mcp_tools = mcp_svc.get_tools_for_profile(profile.profile_id)
            if mcp_tools:
                for tool in mcp_tools:
                    if registry.get(tool.name) is None:
                        registry.register(tool)
        except Exception as e:
            _logger.debug("MCP tool registration skipped: %s", e)

        # 移除 profile 中禁用的工具
        for tool_name, enabled, _ in profile.signature:
            if not enabled:
                _unregister_tool_group(registry, tool_name)

        # 越界防线：按 profile 白名单裁剪注册表
        allowed = getattr(profile, "allowed_tools", None)
        if allowed:
            removed = []
            for tool_name in list(registry._tools.keys()):
                if tool_name in allowed:
                    continue
                if tool_name.startswith("mcp_"):
                    continue
                _unregister_if_exists(registry, tool_name)
                removed.append(tool_name)
            if removed:
                _logger.info(
                    "profile %s 白名单裁剪：移除 %d 个未配置的工具（%s）",
                    profile.slug,
                    len(removed),
                    "、".join(sorted(removed)[:8]),
                )

        # 统一工具执行层：同步 handler 包装成异步版本（防止事件循环阻塞）
        import inspect

        for tool_name, tool in list(registry._tools.items()):
            if not inspect.iscoroutinefunction(tool.handler):
                original_handler = tool.handler

                async def _async_wrapper(*args: Any, _orig=original_handler, **kwargs: Any):
                    return await asyncio.to_thread(_orig, *args, **kwargs)

                tool.handler = _async_wrapper

        # 按**最终注册表**生成能力边界说明，拼进 system prompt
        try:
            from app.services.agent.capability_hint import build_capability_hint

            hint = build_capability_hint(
                registry_tool_names={str(n) for n in registry._tools.keys()},
                response_mode=profile.response_mode,
            )
            if hint:
                ext_instruction = f"{ext_instruction}\n\n{hint}" if ext_instruction else f"\n\n{hint}"
        except Exception:  # noqa: BLE001 -- 提示生成失败不该挡住 agent 构建
            _logger.warning("capability hint 生成失败", exc_info=True)

        return registry, ext_instruction
