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
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.core.data_path import DATA_DIR, is_external_api_call
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
            # 非管理员选 full 时不静默降为 ask（那会让用户以为档位没生效、
            # 反而每次都问）。统一降为 auto —— 与系统默认值一致：只读放行、
            # 写操作仍需审批，既不越权也不骚扰。
            approval_mode = "auto" if approval_mode == "full" else approval_mode
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

        # 预算断路（保留差异化资产：DeepAgents 无等价计费语义）
        budget = self._build_run_budget()

        # ── DeepAgents 内置能力（backend / skills / subagents / summarization）──
        # 绑定它自己的 FilesystemBackend：skills 从磁盘 SKILL.md 读，
        # summarization 把裁剪的历史落盘，subagents 走内置 task() 工具。
        from deepagents.backends import FilesystemBackend
        from deepagents.middleware.filesystem import FilesystemPermission

        # DeepAgents backend 指向项目 data 目录。virtual_mode=True 是安全底线：
        # False 模式下绝对路径（如 /etc/passwd）会绕过 root_dir 直接读取宿主
        # 文件系统（已实测可越权读 root 外任意文件）。True 模式下所有路径都是
        # 以 / 开头的虚拟路径，映射到 root_dir 内部，越界会被拒绝。
        deep_backend = FilesystemBackend(root_dir=str(DATA_DIR), virtual_mode=True)

        # 安全底线：DeepAgents 0.7.41 默认注入 write_file / edit_file / delete 等
        # 内置写工具，它们不经过我们的 EngineApprovalPolicy，且 backend 是全局
        # data/ —— 模型可越权改写其它会话/用户的文件。这里用 DeepAgents 原生
        # permissions 把模型可调用的内置写/删工具收敛为只读：
        #   - 读（ls/read_file/glob/grep）放行，SkillsMiddleware 才能读 SKILL.md；
        #   - 写/删（write_file/edit_file/delete）一律 deny，返回权限拒绝错误。
        # 真正需要落盘时走我们自己的 file 系列工具（有 HITL 审批 + 会话级
        # workspace 隔离）；summarization 直接调 backend，不受此规则影响。
        deep_permissions: list[FilesystemPermission] = [
            FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
        ]

        # 精细控制内置工具：write_file/edit_file/delete 已被 permissions 拒绝，
        # execute 在非 sandbox backend 下不可用 —— 从模型可见工具列表里彻底移除，
        # 省 token 且避免模型反复误调用。同时开启大输出 offload：
        # 超过 20k token 的读取结果 evict 到 backend 文件、二进制内容落盘，
        # 防止大文件把上下文撑爆（DeepAgents 0.7.41 原生能力）。
        from deepagents.middleware.filesystem import FilesystemMiddleware

        deep_fs_middleware = FilesystemMiddleware(
            backend=deep_backend,
            permissions=deep_permissions,
            tools=["ls", "read_file", "glob", "grep"],
            tool_token_limit_before_evict=20_000,
            offload_binary_content=True,
            # 中文描述：明确只读边界，引导模型把写操作交给自研 file 工具
            # （有 HITL 审批 + 会话级 workspace 隔离），避免误调用内置写工具。
            custom_tool_descriptions={
                "ls": "列出会话数据目录中的文件和目录（只读）。路径须以 / 开头，如 /skills/。",
                "read_file": "读取会话数据目录中的文本文件（只读）。路径为虚拟路径，如 /skills/xxx/SKILL.md。需要写文件时请改用 write_text_file 工具（有审批保护）。",
                "glob": "按通配符模式查找会话数据目录中的文件（只读），如 /skills/**/SKILL.md。",
                "grep": "在会话数据目录中搜索文本内容（只读）。用于检索 SKILL.md 等文档内容。",
            },
        )

        # skills: profile 绑定的 skill 目录（SKILL.md 所在目录）。
        # virtual_mode=True 下必须用虚拟路径（/skills/xxx → root_dir/skills/xxx），
        # 传宿主绝对路径会被映射成 root_dir/<绝对路径> 而找不到文件。
        deep_skills: list[str] = []
        if "skill" in profile.builtin_tools and profile.skills:
            for skill in profile.skills:
                root = getattr(skill, "root_dir", None)
                if root:
                    try:
                        rel = Path(root).resolve().relative_to(DATA_DIR.resolve())
                        deep_skills.append("/" + rel.as_posix())
                    except ValueError:
                        # 不在 data/ 下的历史 skill：跳过，避免越权读宿主路径
                        _logger.warning("skill 目录不在 data/ 内，跳过 DeepAgents 绑定: %s", root)

        # subagents: 用 DeepAgents SubAgent TypedDict（tools 是 LC tool 列表）
        deep_subagents: list[dict] = []
        if self.settings.async_sub_agents_enabled:
            deep_subagents = self._build_deepagents_subagents()

        # 可选：DeepAgents RubricMiddleware（在线自评估达标循环）。默认关闭，
        # 开启后 grader 用同一网关独立评估，不达标则让 agent 再迭代一轮。
        deep_middleware: list[Any] = [deep_fs_middleware]
        if getattr(self.settings, "deepagents_rubric_enabled", False):
            try:
                from deepagents.middleware.rubric import RubricMiddleware
                from app.services.agent.langgraph_engine.chat_model import GatewayChatModel

                grader_model = GatewayChatModel(gateway=llm, model_name=effective_model)
                deep_middleware.append(
                    RubricMiddleware(
                        model=grader_model,
                        system_prompt=(
                            "你是交付质量评审员。检查助手的最终回答是否完整、准确、"
                            "满足用户请求。若有明显遗漏或错误，指出具体问题。"
                        ),
                        max_iterations=int(
                            getattr(self.settings, "deepagents_rubric_max_iterations", 2)
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - 可选能力失败不应阻断 agent
                _logger.warning("RubricMiddleware 加载失败，已跳过：%s", exc)

        agent = LangGraphAgent(
            llm=llm,
            tools=tools,
            default_system_prompt=system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            approval_policy=policy,
            model_name=effective_model,
            budget=budget,
            deepagents_backend=deep_backend,
            deepagents_skills=deep_skills or None,
            deepagents_subagents=deep_subagents or None,
            deepagents_permissions=deep_permissions,
            deepagents_middleware=deep_middleware,
        )
        self._agents[cache_key] = agent
        return agent

    def _build_deepagents_subagents(self) -> list[dict]:
        """用 DeepAgents 的 SubAgent TypedDict 构建声明式子代理。

        DeepAgents 自带 ``task()`` 工具按 description 自动分派，子代理用它自己
        的 middleware 栈执行（不再需要我们的 run_fn 回调和 4 个管理工具）。
        """
        subs: list[dict] = []

        code_tools = self._native_tools_for(["calc", "python", "git"])
        subs.append({
            "name": "code_analyst",
            "description": "代码分析与执行：运行 Python 脚本、数学计算、Git 操作。适合需要后台运行代码或分析的场景。",
            "system_prompt": (
                "你是一个代码分析助手。执行 Python 脚本、进行数学计算、查看 Git 状态。"
                "直接运行代码并返回结果，用简洁格式说明执行结果。"
            ),
            "tools": code_tools,
        })

        file_tools = self._native_tools_for(["read_file", "search_files", "text"])
        subs.append({
            "name": "file_processor",
            "description": "文件处理：读取、搜索、整理文件内容。适合需要在后台批量处理文件的场景。",
            "system_prompt": (
                "你是一个文件处理助手。读取文件、搜索文本、整理内容。"
                "保持高效，直接返回处理结果。"
            ),
            "tools": file_tools,
        })
        return subs

    def _native_tools_for(self, plugin_names: list[str]) -> list[Any]:
        """把 native builtin 插件的**只读**工具转成 DeepAgents 接受的 LC tool。

        安全边界：DeepAgents SubAgentMiddleware 在**独立 middleware 栈**里执行
        子代理，不共享主 agent 的 ``EngineApprovalPolicy``，也没有前端审批通道。
        因此子代理工具必须本身无副作用 —— 只暴露 ``is_read_only`` 的工具，
        彻底移除脚本执行 / 文件写入 / git 写操作。否则提示注入可让 ``task()``
        把 ``run_python_script(workspace=<绝对路径>)`` 派给子代理，以服务进程
        权限零审批执行任意脚本（已实测该绕过路径）。
        """
        from app.services.agent.native.plugins import PluginContext
        from app.services.agent.native.tool_registry import ToolRegistry
        from app.services.agent.langgraph_engine.tools_adapter import registry_to_langchain_tools

        reg = ToolRegistry()
        ctx = PluginContext(tool_registry=reg)
        for name in plugin_names:
            try:
                mod = __import__(f"app.services.agent.native.builtin.{name}", fromlist=["setup"])
                mod.setup(ctx)
            except Exception as e:  # noqa: BLE001
                _logger.warning("Sub-agent plugin setup failed: %s: %s", name, e)

        # 只保留只读工具（python/git_add/git_commit/file 写类全部被排除）。
        # 判定用 execution 策略：无副作用 + 不需审批；单靠 concurrency_safe
        # 不够（它在显式 is_concurrency_safe=True 时会覆盖副作用语义）。
        # 用新建 registry 过滤，避免修改原注册表的共享状态。
        read_only = ToolRegistry()
        for tool in reg.list_tools():
            execution = getattr(tool, "execution", None)
            side_effect = bool(getattr(execution, "side_effect", False)) if execution else False
            needs_approval = bool(getattr(execution, "requires_approval", False)) if execution else False
            if not side_effect and not needs_approval:
                read_only.register(tool)
        return registry_to_langchain_tools(read_only)

    def _credential_rotation_bucket(self) -> int:
        """账号池轮换窗口编号（与 DeepAgents 无关，保留）。"""
        try:
            window = int(getattr(self.settings, "llm_credential_rotation_seconds", 300))
        except (AttributeError, TypeError, ValueError):
            window = 300
        if window <= 0:
            return 0
        import time as _time

        return int(_time.time() // window)

    def _build_run_budget(self) -> "Budget | None":
        """run 级预算断路（差异化资产，DeepAgents 无等价计费语义）。"""
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
        except Exception as exc:  # noqa: BLE001
            _logger.warning("AGENT_BUDGET_* 配置非法，run 级预算断路未启用: %s", exc)
            return None

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

        from app.tools.dataframe_tools import register_dataframe_tools as _register_dataframe

        _register_dataframe(registry)

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

        # 计划模式兜底：所有工具注册完后，按「只读白名单」再过滤一遍注册表。
        # 前面的 blocked 只作用于 builtin 插件循环，app/tools/*.py（发邮件/部署/
        # 生图/写文档）与 MCP 工具仍会注册 —— 必须从注册表统一移除，否则计划模式
        # 的「只做只读调研」承诺形同虚设。
        if getattr(profile, "plan_mode", False):
            from app.services.approval_policy import is_read_only_tool

            plan_removed: list[str] = []
            for tool_name, tool in list(registry._tools.items()):
                args = {}
                if tool_name == "file":
                    args = {"action": "list_files"}  # file 组的只读子操作放行
                if not is_read_only_tool(tool_name, args):
                    _unregister_if_exists(registry, tool_name)
                    plan_removed.append(tool_name)
            if plan_removed:
                _logger.info(
                    "plan mode: 从注册表移除 %d 个非只读工具（%s）",
                    len(plan_removed), "、".join(sorted(plan_removed)[:10]),
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
