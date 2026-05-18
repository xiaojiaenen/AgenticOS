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
from app.services.ppt_artifact_service import PptArtifactService, strip_html_block_from_text
from app.services.session_storage import DatabaseAgentStorage, dump_json
from app.services.tool_config_service import ToolConfigService
from app.schemas.agent import AgentStreamRequest
from app.tools.email_tools import register_email_tools, set_current_session_id


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
        """Build a compact catalog of all 31 single-page layout HTML samples.

        Reads each layout file from templates/single-page/, extracts the
        <style> block (layout-specific CSS) and <section> block (slide HTML),
        and formats them for LLM copy-paste.
        """
        if cls._layout_catalog_cache is not None:
            return cls._layout_catalog_cache

        from pathlib import Path
        import re as _re

        layouts_dir = Path(__file__).resolve().parent / "ppt" / "html-ppt" / "templates" / "single-page"
        if not layouts_dir.exists():
            cls._layout_catalog_cache = ""
            return ""

        parts: list[str] = []
        for fpath in sorted(layouts_dir.glob("*.html")):
            name = fpath.stem
            raw = fpath.read_text(encoding="utf-8")

            # Extract <style> block(s)
            style_blocks = _re.findall(r"<style[^>]*>(.*?)</style>", raw, _re.DOTALL)
            styles = "\n".join(s.strip() for s in style_blocks).strip()

            # Extract <section class="slide"> block
            sec_m = _re.search(r'<section class="slide[^"]*"[^>]*>.*?</section>', raw, _re.DOTALL)
            if sec_m is None:
                continue
            section_html = sec_m.group()

            # Compact: remove excessive whitespace but keep structure readable
            section_html = _re.sub(r"\n\s*\n", "\n", section_html)
            section_html = _re.sub(r" {2,}", " ", section_html)

            parts.append(f"<!-- layout: {name} -->")
            if styles:
                parts.append(f"<style>\n{styles}\n</style>")
            parts.append(section_html)
            parts.append("")

        cls._layout_catalog_cache = "\n".join(parts)
        return cls._layout_catalog_cache

    def _get_edit_hint(self, session_id: str) -> str | None:
        """If the session has existing PPT artifacts, add a brief edit hint."""
        try:
            artifact = self.ppt_artifacts.get_latest_for_session(session_id)
            if artifact is None:
                return None
            title = artifact.get("title", "未命名")
            slide_count = artifact.get("slide_count", 0)
            return (
                f"\n\n---\n"
                f"## 注意：当前对话已有一个 PPT（{title}，{slide_count} 页）\n"
                f"用户可能要修改它。从对话历史中找到上次的 HTML，在此基础上修改后输出**完整的修改后 HTML**（包裹在 ```html 中）。\n"
                f"如果是新建 PPT 要求，忽略此提示。\n"
            )
        except Exception:
            return None

    @classmethod
    def _inject_design_catalog(cls, message: str) -> str:
        layout_catalog = cls._build_layout_catalog()

        lines = [
            "",
            "---",
            "## html-ppt 真实 Layout 样本（从 templates/single-page/ 提取，共 31 个）",
            "",
            "**工作流：为每页选择一个 layout → 复制其 <section> 块 → 替换 demo 数据 → 保留 class 结构和 <style> 不变。**",
            "",
            "部分 layout 自带 <style> 块（timeline 的 .tl、comparison 的 .vs、flow-diagram 的 .flow 等），**必须原样保留**在 slide 前面，它们定义了该 layout 的专属视觉。",
            "",
            layout_catalog,
            "",
            "---",
            "## 完整 Deck 模板速查（15 套，可用作设计参考）",
            "",
            "**真实提取**: xhs-white-editorial(白底杂志) · graphify-dark-graph(暗底知识图谱) · knowledge-arch-blueprint(奶油蓝图) · hermes-cyber-terminal(暗终端) · obsidian-claude-gradient(GitHub暗紫) · testing-safety-alert(红琥珀安全) · xhs-pastel-card(马卡龙) · dir-key-nav-minimal(极简Keynote)",
            "**场景脚手架**: pitch-deck(VC融资10页) · product-launch(产品发布8页) · tech-sharing(技术分享8页) · weekly-report(周报7页) · xhs-post(小红书3:4竖版) · course-module(教学7页) · presenter-mode-reveal(演讲者模式·S键提词器)",
            "",
            "---",
            "## 动画速查",
            "",
            "### CSS 入场动画（data-anim=\"名称\"）",
            "**常用**: fade-up(段落/卡片) · fade-down(标题) · fade-left/right(左右栏) · blur-in(封面) · rise-in(hero标题) · zoom-pop(数字/CTA) · counter-up(数字滚动) · stagger-list(列表逐项出现,加在容器class) · perspective-zoom(章节分隔) · cube-rotate-3d(章节分隔) · confetti-burst(致谢页)",
            "**更多**: drop-in · glitch-in · typewriter · neon-glow · shimmer-sweep · gradient-flow · path-draw · morph-shape · parallax-tilt · card-flip-3d · page-turn-3d · marquee-scroll · kenburns · spotlight · ripple-reveal",
            "",
            "### Canvas FX 特效（需引入 `<script src=\"assets/animations/fx-runtime.js\"></script>`，用 `<div data-fx=\"名称\" style=\"width:100%;height:360px\"></div>` 放置）",
            "particle-burst(粒子爆发) · confetti-cannon(彩纸炮) · firework(烟花) · starfield(星空) · matrix-rain(矩阵雨) · knowledge-graph(知识图谱) · neural-net(神经网络) · constellation(星座连线) · orbit-ring(轨道环) · galaxy-swirl(银河漩涡) · word-cascade(词坠落) · letter-explode(字母飞入) · chain-react(链式反应) · magnetic-field(磁场) · data-stream(数据流) · gradient-blob(渐变泡) · sparkle-trail(闪光轨迹) · shockwave(冲击波) · typewriter-multi(多行打字) · counter-explosion(数字爆炸)",
            "",
            "**每页只用 1-2 种动画。Canvas FX 每页只放一个。**",
            "",
            "---",
            "## 快速参考",
            "",
            "### 主题选择（直接选最合适的，不用问用户）",
            "- 技术分享 / 开发者 → tokyo-night, dracula, nord, catppuccin-mocha, terminal-green",
            "- 商业 / 管理层汇报 → corporate-clean, minimal-white, pitch-deck-vc, swiss-grid",
            "- 创意提案 / 发布会 → neo-brutalism, aurora, glassmorphism, cyberpunk-neon, magazine-bold",
            "- 学术 / 研究报告 → academic-paper, editorial-serif, solarized-light",
            "- 小红书 / 社交媒体 → xiaohongshu-white, soft-pastel, rainbow-gradient, memphis-pop",
            "",
            "### 关键规则",
            "1. 推荐 1 个最匹配主题写入 `<html data-theme=\"xxx\">`，body data-themes 列 3-5 个备选",
            "2. 每页从上面的 layout 样本中**复制粘贴**，替换内容但保留结构",
            "3. 带 <style> 的 layout：把 <style> 块复制到 slide 前面，一起放进 deck",
            "4. 所有颜色用 var(--xxx) 令牌",
            "5. deck head 中必须引入: assets/base.css + assets/fonts.css + assets/themes/<name>.css + assets/animations/animations.css",
            "6. deck body 末尾引入: assets/runtime.js",
            "7. 如果用了 Canvas FX: head 中额外引入 assets/animations/fx-runtime.js",
            "",
            "**CURRENT TIME:** " + __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        ]
        return message + "\n".join(lines)

    def _normalize_session_limits(
        self,
        session,
        *,
        response_mode: str,
        requested_max_steps: int | None,
    ) -> None:
        if response_mode != "ppt" or requested_max_steps is not None:
            return
        current_max_steps = getattr(session, "max_steps", self.settings.agent_max_steps)
        if current_max_steps < self.settings.agent_max_steps:
            session.max_steps = self.settings.agent_max_steps

    def _build_user_message(self, request: AgentStreamRequest) -> str:
        """Build the user message, optionally prepending attached file contents."""
        if not request.files:
            return request.message

        file_blocks: list[str] = []
        for f in request.files:
            header = f"### 📎 {f.filename} ({len(f.text_content)} chars)"
            file_blocks.append(f"{header}\n{f.text_content}")

        return "\n\n".join(file_blocks) + f"\n\n---\n{request.message}"

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
    ) -> None:
        usage = event_data.get("usage") or getattr(session, "last_usage", None)
        input_tokens, output_tokens, total_tokens = self._extract_usage_numbers(usage)
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
            # If there's an existing artifact, add a lightweight edit hint
            edit_hint = self._get_edit_hint(request.session_id)
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
                        artifact = await self.ppt_artifacts.create_from_text(session.session_id, collected_text)
                        visible_text = strip_html_block_from_text(collected_text) if artifact else collected_text
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
