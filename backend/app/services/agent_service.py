import asyncio
import contextlib
import json
from typing import Any, AsyncIterator

from wuwei import (
    Agent,
    AgentEvent,
    ContextCompressionHook,
    FileSystemSkillProvider,
    HitlHook,
    SkillHook,
    SkillManager,
    StorageHook,
)
from wuwei.llm import LLMGateway
from wuwei.memory.context_compressor import LLMContextCompressor
from wuwei.runtime import ApprovalPolicy
from wuwei.runtime.hooks import RuntimeHook
from wuwei.tools import ToolRegistry
from wuwei.tools.builtin import register_skill_tools

from app.core.config import Settings, get_settings
from app.db.models import AgentUsageEventModel, ApprovalModel, PptArtifactModel, UserModel
from app.db.session import create_db_session
from app.services.approval_manager import ApprovalManager
from app.services.agent_profile_service import AgentProfileService, RuntimeAgentProfile
from app.services.ppt_artifact_service import PptArtifactService
from app.services.ppt.svg_layouts import SVG_LAYOUTS
from app.services.ppt.svg_to_pptx.config import SVG_CONSTRAINTS
from app.services.ppt.theme_token_resolver import build_token_quick_ref, list_available_themes
from app.services.session_storage import DatabaseAgentStorage, dump_json
from app.services.tool_config_service import ToolConfigService
from app.schemas.agent import AgentStreamRequest
from app.tools.email_tools import register_email_tools, set_current_session_id
from app.tools.ppt_tools import set_current_session_id as set_ppt_session_id
from app.tools.pptx_reverse_tools import set_current_session_id as set_pptx_reverse_session_id


MAX_STEPS_LIMIT_MESSAGE = "任务未完成，已达到最大步骤限制。"


class ThinkingHistoryCompatibilityHook(RuntimeHook):
    """Keep provider thinking-mode histories free of local synthetic replies."""

    async def before_llm(self, session, messages, tools, *, step: int, task=None):
        filtered_messages = [
            message
            for message in messages
            if not (
                message.role == "assistant"
                and message.content == MAX_STEPS_LIMIT_MESSAGE
                and not message.reasoning_content
                and not message.tool_calls
            )
        ]
        return filtered_messages, tools


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

    def _register_runtime_hooks(self, agent: Agent, *, approval_tools: set[str] | frozenset[str]) -> None:
        if approval_tools and self.settings.hitl_enabled:
            agent.hooks.register(
                HitlHook(
                    provider=self.approval_manager,
                    policy=ApprovalPolicy(
                        require_approval_tools=set(approval_tools)
                    ),
                )
            )
        if self.settings.context_compression_enabled:
            agent.hooks.register(
                ContextCompressionHook(
                    compressor=LLMContextCompressor(agent.llm),
                    compress_after_turns=self.settings.context_compress_after_turns,
                    keep_recent_turns=self.settings.context_keep_recent_turns,
                )
            )

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

        hooks = [StorageHook(self.storage)]

        approval_tools = set(profile.approval_tools)

        if approval_tools and self.settings.hitl_enabled:
            hooks.append(
                HitlHook(
                    provider=self.approval_manager,
                    policy=ApprovalPolicy(
                        require_approval_tools=approval_tools
                    ),
                )
            )
        if "skill" in profile.builtin_tools:
            hooks.append(
                SkillHook(
                    instruction=(
                        "你有可用的 Skill（专门技能），它们是处理特定领域任务的增强能力。\n"
                        "在对话开始时或遇到可能匹配的请求时，先调用 `list_skills` 查看可用技能摘要。\n"
                        "如果某个技能的描述与用户当前任务相关，调用 `load_skill` 加载其完整指令并遵循执行。\n"
                        "技能声明的 references 和 Python scripts 是宝贵资源，按正文指引使用。"
                    ),
                )
            )

        agent = Agent(
            llm=LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens),
            tools=self._build_tool_registry(profile),
            default_system_prompt=profile.system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            hooks=hooks,
        )
        if self.settings.context_compression_enabled:
            agent.hooks.register(
                ContextCompressionHook(
                    compressor=LLMContextCompressor(agent.llm),
                    compress_after_turns=self.settings.context_compress_after_turns,
                    keep_recent_turns=self.settings.context_keep_recent_turns,
                )
            )
        agent.hooks.register(ThinkingHistoryCompatibilityHook())
        self._agents[cache_key] = agent
        return agent

    @staticmethod
    def _build_tool_registry(profile: RuntimeAgentProfile) -> ToolRegistry:
        builtin_tools = [name for name in profile.builtin_tools if name not in ("skill", "email")]
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

    _layout_catalog_cache: str | None = None

    @classmethod
    def _build_layout_catalog(cls) -> str:
        """Build a compact catalog of all 31 SVG layout structural templates."""
        parts: list[str] = []
        for name, svg in SVG_LAYOUTS.items():
            parts.append(svg)
            parts.append("")
        return "\n".join(parts)

    @staticmethod
    def _build_svg_constraints_text() -> str:
        """从 SVG_CONSTRAINTS 动态生成 SVG 禁止清单文本。"""
        fc = SVG_CONSTRAINTS
        elements = ", ".join(f"`<{e}>`" for e in fc["forbidden_elements"])
        attributes = ", ".join(f"`{a}`" for a in fc["forbidden_attributes"])
        patterns = ", ".join(f"`{p}`" for p in fc["forbidden_patterns"])
        return (
            f"**禁止元素**：{elements}\n"
            f"**禁止属性**：{attributes}\n"
            f"**禁止模式**：{patterns}\n"
            f"→ 透明度用 `fill-opacity` / `stroke-opacity`"
        )

    def _inject_design_catalog(cls, message: str) -> str:
        """Inject SVG layout templates + token reference + icon rules + theme selection guide."""
        layout_catalog = cls._build_layout_catalog()
        token_ref = build_token_quick_ref()

        lines = [
            "",
            "---",
            "## ⚠️ 第一步：调用 `list_skills` 加载 ppt-svg-reference 技能",
            "",
            "在生成任何 SVG 之前，**必须先调用 `list_skills` 查看可用技能，然后 `load_skill(\"ppt-svg-reference\")` 加载 SVG 技术规范**。",
            "技能中包含图标嵌入语法、tspan 铁律、阴影模板、分组动画规则等关键约束，不加载将导致导出失败。",
            "",
            "---",
            "## SVG Layout 结构模板（31 个，可直接复制替换内容）",
            "",
            "**工作流：list_skills → load_skill(\"ppt-svg-reference\") → search_icons 搜索图标 → 为每页选择 layout → 调用 save_slide(slide_num=N, svg=\"...\") 写入每页 → 不再调工具即完成。**",
            "",
            layout_catalog,
            "",
            "---",
            "## Token 语义速查（颜色用 var(--xxx) 引用，具体色值由主题决定，后端自动解析）",
            "",
            token_ref,
            "",
            "---",
            "## 图标引用（使用 `search_icons` 工具按关键词搜索，再通过 `<use data-icon=\"库名/图标名\" fill=\"var(--accent)\" x=\"..\" y=\"..\" width=\"..\" height=\"..\"/>` 引用）",
            "",
            "**图标使用规则：**",
            "- 先用 search_icons 工具搜索需要的图标名",
            "- 一页内只能用**一个**图标库的图标，不要混用",
            "- 图标名严格从搜索结果中复制",
            "",
            "---",
            "## SVG 技术速查（详细规范见 data/skills/ppt-svg-reference/SKILL.md）",
            "",
            cls._build_svg_constraints_text(),
            "",
            "**tspan 合并**：同一行文字（含混色/混粗）必须合并到一个 `<text><tspan>...</tspan></text>`。数值结果用 `<tspan fill=\"var(--accent)\" font-weight=\"bold\">` 加粗高亮。",
            "",
            "**图标**：先用 `search_icons` 搜，再用 `<use data-icon=\"库名/图标名\" x=\"..\" y=\"..\" width=\"..\" height=\"..\" fill=\"var(--accent)\"/>` 嵌入。一页一种库。",
            "",
            "**阴影模板（克制使用，每页 ≤3 个）**：",
            "```svg",
            "<filter id=\"softShadow\" x=\"-15%\" y=\"-15%\" width=\"140%\" height=\"140%\">",
            "  <feDropShadow dx=\"0\" dy=\"4\" stdDeviation=\"8\" flood-color=\"#000000\" flood-opacity=\"0.08\"/>",
            "</filter>",
            "```",
            "",
            "**图表**：柱状=`<rect>` + `<text>` / 折线=`<polyline>` + `<circle>` / 饼图=`<path>` 扇形 / 雷达=`<polygon>`",
            "**表格**：`<rect>` 行背景交替 + `<text>` / **虚线**：`stroke-dasharray=\"4,4\"`",
            "**图片**：`<image href=\"../images/photo.jpg\" ... preserveAspectRatio=\"xMidYMid slice\"/>`（后处理自动内嵌）",
            "",
            "---",
            "**主题选择快速决策（data-theme 只能从下方完整列表或分类推荐中选，禁止自创）：**",
            "- 商业 / 管理层汇报 → apple, stripe, ibm, corporate, professional, enterprise, mastercard",
            "- 技术分享 / 开发者 → github, vercel, cursor, linear-app, expo, warp, mongodb, hashicorp, dracula, monokai",
            "- 创意 / 发布会 → nike, spotify, playstation, ferrari, brutalism, neobrutalism, glassmorphism, cyberpunk, sunset",
            "- AI / 前沿科技 → openai, claude, nvidia, huggingface, spacex, hud, mission-control, aurora, tokyo-night",
            "- 学术 / 研究报告 → kami, paper, editorial, atelier-zero, publication, solarized, everforest",
            "- 社交媒体 / 小红书 → airbnb, pinterest, duolingo, xiaohongshu, framer, rose-pine",
            "- 简约 / 纯净 → minimal, clean, mono, refined, simple, sleek, nord, catppuccin-latte",
            "- 活泼 / 年轻化 → discord, colorful, energetic, tetris, pacman, vibrant, catppuccin",
            "- 暗色系 → spotify, github, dracula, cyberpunk, tokyo-night, monokai, trading-terminal, hud, mission-control",
            "- 金融 / 支付 → stripe, revolut, binance, coinbase, kraken, wise",
            "",
            "**完整 161 主题名列表（data-theme 只能从下面选）：**",
            ", ".join(sorted(list_available_themes())),
            "",
            "### 关键规则",
            "1. 推荐 1 个最匹配主题写入 `<svg data-theme=\"xxx\">`",
            "2. 每页从上面的 SVG layout 样本中**复制粘贴**，替换内容但保留结构和 var(--token) 引用",
            "3. 所有颜色用 var(--xxx) 令牌，非颜色属性（圆角、字号、字体）直接写值",
            "4. 每页调用一次 save_slide(slide_num=N, svg=\"...\")，共 8-14 页",
            "5. 演讲者备注：在 SVG 开头附近添加 `<!-- notes: ... -->`",
            "",
            "**CURRENT TIME:** " + __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        ]
        return message + "\n".join(lines)

    async def _get_edit_hint(self, session_id: str) -> str | None:
        """If the session has existing PPT artifacts, add an edit hint for save_slide."""
        from pathlib import Path as _Path
        try:
            artifact = await self.ppt_artifacts.get_latest_for_session(session_id)
            if artifact is None:
                return None
            title = artifact.get("title", "未命名")
            slide_count = artifact.get("slide_count", 0)
            project_root = _Path(__file__).resolve().parent.parent.parent.parent
            slides_dir = project_root / "data" / "ppt-sessions" / session_id
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
        if owner_id is not None and owner_id != user.id and user.role != "admin":
            raise PermissionError("当前用户无权访问该会话。")

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
        set_current_session_id(session.session_id)
        set_ppt_session_id(session.session_id)
        set_pptx_reverse_session_id(session.session_id)

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
                async for event in agent.stream_events(user_message, session=session):
                    await runtime_queue.put(event)
            finally:
                try:
                    if hasattr(session, "system_prompt"):
                        await self.storage.save_meta(session)
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
                        # 从 session 工作目录收集 save_slide 写入的文件
                        from pathlib import Path as _Path
                        _slides_dir = _Path(__file__).resolve().parent.parent.parent.parent / "data" / "ppt-sessions" / session.session_id
                        artifact = await self.ppt_artifacts.create_from_slides_dir(
                            session.session_id, _slides_dir,
                        )
                        # 构建简短的文字摘要给前端展示
                        if artifact is not None:
                            visible_text = f"已生成 {artifact['slide_count']} 页 PPT：{artifact['title']}"
                        else:
                            visible_text = collected_text
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
            self.approval_manager.unsubscribe(session.session_id, approval_queue)
            for task in (runtime_task, approval_task):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            if not producer.done():
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
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
            _icons_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "icons"
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
                    pass
                try:
                    raw = svg_path.read_text(encoding="utf-8")
                    new_content, count = _fix_rounded(raw, verbose=False)
                    if count:
                        svg_path.write_text(new_content, encoding="utf-8")
                        _processed += count
                except Exception:
                    pass
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
