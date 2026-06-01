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
from wuwei.tools.builtin import register_skill_tools

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
    "在对话开始时或遇到可能匹配的请求时，先调用 `list_skills` 查看可用技能摘要。\n"
    "如果某个技能的描述与用户当前任务相关，调用 `load_skill` 加载其完整指令并遵循执行。\n"
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
            self.settings.context_compression_enabled,
        )
        cached = self._agents.get(cache_key)
        if cached is not None:
            return cached

        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        middleware_stack = self._build_middleware_stack(profile, llm)

        agent = Agent(
            llm=llm,
            tools=self._build_tool_registry(profile),
            default_system_prompt=profile.system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            middleware=middleware_stack,
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
            all_tool_names = [t.name for t in self._build_tool_registry(profile).list_tools()]
            auto_approve = [name for name in all_tool_names if name not in approval_tools]
            stack.add(HitlMiddleware(
                approval_provider=self.approval_manager.request_approval_bool,
                auto_approve_tools=auto_approve,
                auto_reject_tools=[],
            ))

        # 2. 上下文压缩：ContextCompressionMiddleware 压缩时无法保证
        #    tool_call/tool_response 消息配对完整性，导致 OpenAI API 400 错误。
        #    暂时禁用，待 wuwei 修复 _compress_context 的配对保护后重新启用。

        # 3. 日志中间件（开发环境启用，生产环境可关闭）
        if self.settings.environment == "development":
            stack.add(LoggingMiddleware())

        # 4. Skill 指令中间件
        if "skill" in profile.builtin_tools:
            stack.add(SkillInstructionMiddleware())

        # 4. 思考历史兼容中间件
        stack.add(ThinkingHistoryCompatibilityMiddleware())

        return stack

    @staticmethod
    def _build_tool_registry(profile: RuntimeAgentProfile) -> ToolRegistry:
        # Exclude "skill", "email", and "file" (file is handled per-mode below)
        _exclude = {"skill", "email"}
        if profile.response_mode == "website":
            _exclude.add("file")
        builtin_tools = [name for name in profile.builtin_tools if name not in _exclude]
        registry = ToolRegistry.from_builtin(builtin_tools)
        if "skill" in profile.builtin_tools:
            skill_manager = SkillManager(
                [FileSystemSkillProvider(skill.root_dir) for skill in profile.skills]
            )
            register_skill_tools(registry, skill_manager)
        if "email" in profile.builtin_tools:
            register_email_tools(registry)

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

        return registry

    @staticmethod
    def _build_tool_call_payload(event: AgentEvent) -> dict[str, Any]:
        payload = {
            "id": event.data.get("tool_call_id"),
            "function": {
                "name": event.data.get("display_name") or event.data.get("tool_name") or "工具调用",
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

    @staticmethod
    def _build_tool_result_payload(
        event: AgentEvent,
        *,
        status: str,
        result: str | None,
    ) -> dict[str, Any]:
        payload = {
            "tool_call_id": event.data.get("tool_call_id"),
            "name": event.data.get("display_name") or event.data.get("tool_name") or "工具调用",
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

    def _inject_design_catalog(cls, message: str) -> str:
        """Inject minimal context: theme selection + token reference + skill loading instructions.

        Design rules, SVG constraints, layout templates, and chart templates
        are now delivered via two skills (ppt-design-guide and ppt-template-library)
        that the LLM loads once at conversation start. This reduces per-message
        injection from ~119K chars to ~5K chars.
        """
        token_ref = build_token_quick_ref()
        theme_count = len(list_available_themes())
        theme_list = ", ".join(sorted(list_available_themes()))

        lines = [
            "",
            "---",
            "## ⚠️ 生成 SVG 前必须加载两个技能",
            "",
            "在生成任何 SVG 之前，**必须按顺序加载以下两个技能**：",
            "",
            "1. `load_skill(\"ppt-design-guide\")` — 设计规范全集（SVG 约束、排版铁律、颜色纪律、动画系统、套装风格）",
            "2. `load_skill(\"ppt-template-library\")` — 模板库（15 个核心布局 + 71 个数据图表，均为 var(--token) 格式）",
            "",
            "**技能加载后，按需用 `read_file` 读取具体的 SVG 模板文件。**",
            "",
            "---",
            "## ⭐ 主题选择（必须先选主题，再写 SVG）",
            "",
            f"**共 {theme_count} 个品牌设计主题可用。data-theme 只能从下方列表选，禁止自创或编造主题名。**",
            "",
            "**快速决策（按场景匹配）：**",
            "- 商业 / 管理层汇报 → apple, stripe, ibm, corporate, professional, enterprise, mastercard",
            "- 技术分享 / 开发者 → github, vercel, cursor, linear-app, expo, warp, mongodb, hashicorp, dracula, monokai",
            "- 创意 / 发布会 → nike, spotify, playstation, ferrari, brutalism, neobrutalism, glassmorphism, cyberpunk, sunset",
            "- AI / 前沿科技 → openai, claude, nvidia, huggingface, spacex, hud, mission-control, aurora, tokyo-night",
            "- 学术 / 研究报告 → kami, paper, editorial, atelier-zero, publication, solarized, everforest",
            "- 社交媒体 / 小红书 → airbnb, pinterest, duolingo, xiaohongshu, framer, rose-pine",
            "- 简约 / 纯净 → minimal, clean, mono, refined, simple, sleek, nord, catppuccin-latte",
            "- 活泼 / 年轻化 → discord, colorful, energetic, tetris, pacman, vibrant, catppuccin",
            "- 暗色系 → spotify, dracula, cyberpunk, tokyo-night, monokai, trading-terminal, hud, mission-control",
            "- 金融 / 支付 → stripe, revolut, binance, coinbase, kraken, wise",
            "- 编辑排版（zhangzara 衬线风）→ zhangzara-editorial-tri-tone, zhangzara-soft-editorial, zhangzara-broadside, zhangzara-mat, zhangzara-vellum, zhangzara-pin-and-paper",
            "- 现代海报/粗野风（zhangzara）→ zhangzara-bold-poster, zhangzara-neo-grid-bold, zhangzara-raw-grid, zhangzara-capsule, zhangzara-signal, zhangzara-block-frame",
            "- 温暖/活泼（zhangzara）→ zhangzara-coral, zhangzara-daisy-days, zhangzara-pink-script, zhangzara-sakura-chroma, zhangzara-scatterbrain, zhangzara-playful",
            "- 创意/艺术（zhangzara）→ zhangzara-studio, zhangzara-grove, zhangzara-cartesian, zhangzara-creative-mode, zhangzara-biennale-yellow, zhangzara-monochrome",
            "- 复古（zhangzara）→ zhangzara-retro-windows, zhangzara-retro-zine, zhangzara-8-bit-orbit",
            "- 专业/商务（zhangzara）→ zhangzara-blue-professional, zhangzara-long-table, zhangzara-peoples-platform, zhangzara-cobalt-grid, zhangzara-stencil-tablet",
            "",
            f"**完整 {theme_count} 主题名列表：**",
            theme_list,
            "",
            "**关键规则：**",
            "1. 从上面选 1 个主题，写入 `<svg data-theme=\"xxx\">`",
            "2. 所有颜色用 var(--xxx) 令牌，非颜色属性（圆角、字号、字体）直接写值",
            "3. 每页调用 save_slide(slide_num=N, svg=\"...\") 写入，共 8-14 页",
            "",
            "---",
            "## Token 语义速查（颜色用 var(--xxx) 引用，具体色值由主题决定，后端自动解析）",
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
        except Exception:
            _logger.exception("ppt artifact creation failed: session=%s", session_id)
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

    def _normalize_session_limits(
        self,
        session,
        *,
        response_mode: str,
        requested_max_steps: int | None,
    ) -> None:
        if response_mode != "ppt" or requested_max_steps is not None:
            return
        ppt_max_steps = 50
        current_max_steps = getattr(session, "max_steps", self.settings.agent_max_steps)
        if current_max_steps < ppt_max_steps:
            session.max_steps = ppt_max_steps

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

        # Inject design system catalog for PPT mode
        message = request.message
        if ppt_mode:
            message = self._inject_design_catalog(message)
            edit_hint = await self._get_edit_hint(request.session_id)
            if edit_hint:
                message = message + edit_hint

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
        if user is not None: set_current_user_id(user.id)
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

        async def produce_events() -> None:
            try:
                user_message = self._build_user_message(request)
                # 注入后的 message 包含主题列表等设计系统信息，需要覆盖原始消息
                if ppt_mode or website_mode:
                    user_message = message
                async for event in agent.stream_events(user_message, session=session):
                    await runtime_queue.put(event)
            finally:
                try:
                    if hasattr(session, "system_prompt"):
                        # Shield to ensure DB write completes even when the
                        # producer task is cancelled by client disconnecting
                        # the SSE stream, so connections are returned to the pool.
                        await asyncio.shield(self.storage.save_meta(session))
                except asyncio.CancelledError:
                    pass
                finally:
                    await runtime_queue.put(None)

        producer = asyncio.create_task(produce_events())
        runtime_task = asyncio.create_task(runtime_queue.get())
        approval_task = asyncio.create_task(approval_queue.get())

        try:
            while True:
                done, _ = await asyncio.wait(
                    {runtime_task, approval_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

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
                        _logger.info("ppt done: session=%s, creating artifact...", session.session_id)
                        artifact = await self._create_ppt_artifact(session.session_id)
                        _logger.info("ppt artifact result: session=%s, artifact=%s", session.session_id, "OK" if artifact else "None")
                        if artifact is not None:
                            visible_text = f"已生成 {artifact['slide_count']} 页 PPT：{artifact['title']}"
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
                            # Artifact 创建失败，尝试 Multi-Agent 重新生成
                            _logger.warning("ppt artifact creation failed: session=%s, trying multi-agent fallback", session.session_id)
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "regenerating_ppt",
                                    "label": "正在用多 Agent 重新生成 PPT",
                                },
                            }
                            try:
                                # 优先使用 StateGraph Pipeline
                                from app.services.ppt_pipeline import PptPipeline
                                pipeline = PptPipeline()
                                pipeline_result = await pipeline.run(
                                    user_message=request.message,
                                    session_id=session.session_id,
                                )
                                if pipeline_result.get("success") and pipeline_result.get("artifact"):
                                    artifact = await self._create_ppt_artifact(session.session_id)
                                    if artifact is not None:
                                        visible_text = f"已生成 {artifact['slide_count']} 页 PPT：{artifact['title']}"
                                        yield {"event": "run_status", "data": {"session_id": session.session_id, "phase": "rendering_ppt", "label": "正在渲染 PPT 预览"}}
                                        yield {"event": "artifact_ready", "data": artifact}
                                    else:
                                        visible_text = collected_text or "PPT 预览生成失败：SVG 页数不足或格式不正确。"
                                        yield {"event": "run_status", "data": {"session_id": session.session_id, "phase": "error", "label": "PPT 预览生成失败"}}
                                else:
                                    # Pipeline 失败，回退到 Multi-Agent
                                    from app.services.multi_agent_ppt_service import MultiAgentPptService
                                    multi_svc = MultiAgentPptService(self.settings)
                                    async for _event in multi_svc.generate_ppt(
                                        user_message=request.message,
                                        session_id=session.session_id,
                                    ):
                                        if _event.get("event") == "done":
                                            artifact = await self._create_ppt_artifact(session.session_id)
                                            if artifact is not None:
                                                visible_text = f"已生成 {artifact['slide_count']} 页 PPT：{artifact['title']}"
                                                yield {"event": "run_status", "data": {"session_id": session.session_id, "phase": "rendering_ppt", "label": "正在渲染 PPT 预览"}}
                                                yield {"event": "artifact_ready", "data": artifact}
                                            else:
                                                visible_text = collected_text or "PPT 预览生成失败：SVG 页数不足或格式不正确。"
                                                yield {"event": "run_status", "data": {"session_id": session.session_id, "phase": "error", "label": "PPT 预览生成失败"}}
                            except Exception as e:
                                _logger.error(f"Multi-agent PPT fallback failed: {e}")
                                visible_text = collected_text or f"PPT 生成失败：{e}"
                                yield {"event": "run_status", "data": {"session_id": session.session_id, "phase": "error", "label": "PPT 生成失败"}}
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
                        yield {
                            "event": "run_status",
                            "data": {
                                "session_id": session.session_id,
                                "phase": "done",
                                "label": "本轮回复已完成",
                            },
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




