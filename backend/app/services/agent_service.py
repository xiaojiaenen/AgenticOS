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
from app.services.ppt.theme_token_resolver import build_color_token_table, build_token_quick_ref, list_available_themes
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

        # 合并审批工具：原始审批工具 + 邮件发送工具（如果包含邮件 skill）
        approval_tools = set(profile.approval_tools)
        skill_names = [skill.name.lower() for skill in profile.skills]
        skill_slugs = [skill.slug.lower() for skill in profile.skills]
        has_email_skill = any(
            "email" in name or "邮件" in name or "email" in slug
            for name, slug in zip(skill_names, skill_slugs)
        )
        if has_email_skill:
            approval_tools.add("send_email")

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
        builtin_tools = [name for name in profile.builtin_tools if name != "skill"]
        registry = ToolRegistry.from_builtin(builtin_tools)
        if "skill" in profile.builtin_tools:
            skill_manager = SkillManager(
                [FileSystemSkillProvider(skill.root_dir) for skill in profile.skills]
            )
            register_skill_tools(registry, skill_manager)

        # 检查是否包含邮件 skill，如果有则注册邮件工具
        skill_names = [skill.name.lower() for skill in profile.skills]
        skill_slugs = [skill.slug.lower() for skill in profile.skills]
        has_email_skill = any(
            "email" in name or "邮件" in name or "email" in slug
            for name, slug in zip(skill_names, skill_slugs)
        )
        if has_email_skill:
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
    @classmethod
    def _build_layout_catalog(cls) -> str:
        """Build a compact catalog of all 31 SVG layout structural templates."""
        parts: list[str] = []
        for name, svg in SVG_LAYOUTS.items():
            parts.append(svg)
            parts.append("")
        return "\n".join(parts)

    @classmethod
    def _inject_design_catalog(cls, message: str, theme_name: str = "tokyo-night") -> str:
        """Inject SVG layout templates + color token table + token reference."""
        layout_catalog = cls._build_svg_layout_catalog()
        color_table = build_color_token_table(theme_name)
        token_ref = build_token_quick_ref()

        lines = [
            "",
            "---",
            "## SVG Layout 结构模板（31 个，可直接复制替换内容）",
            "",
            "**工作流：为每页选择一个 layout → 复制其 SVG 结构 → 替换占位内容 → 保留 var(--token) 和 data-theme 不变。**",
            "",
            layout_catalog,
            "",
            "---",
            "## 当前主题颜色令牌表",
            "",
            color_table,
            "",
            token_ref,
            "",
            "**主题选择快速决策:**",
            "- 技术分享 / 开发者 → tokyo-night, dracula, nord, catppuccin-mocha, terminal-green",
            "- 商业 / 管理层汇报 → corporate-clean, minimal-white, pitch-deck-vc, swiss-grid",
            "- 创意提案 / 发布会 → neo-brutalism, aurora, glassmorphism, cyberpunk-neon, magazine-bold",
            "- 学术 / 研究报告 → academic-paper, editorial-serif, solarized-light",
            "- 小红书 / 社交媒体 → xiaohongshu-white, soft-pastel, rainbow-gradient, memphis-pop",
            "",
            "### 关键规则",
            "1. 推荐 1 个最匹配主题写入 `<svg data-theme=\"xxx\">`",
            "2. 每页从上面的 SVG layout 样本中**复制粘贴**，替换内容但保留结构和 var(--token) 引用",
            "3. 所有颜色用 var(--xxx) 令牌，非颜色属性（圆角、字号、字体）直接写值",
            "4. 每页一个 ```svg 代码块，共 8-14 页",
            "5. 演讲者备注：在 SVG 开头附近添加 `<!-- notes: ... -->`",
            "",
            "**CURRENT TIME:** " + __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        ]
        return message + "\n".join(lines)

    def _get_edit_hint(self, session_id: str) -> str | None:
        """If the session has existing PPT artifacts, add an edit hint with file paths."""
        import os as _os
        try:
            artifact = self.ppt_artifacts.get_latest_for_session(session_id)
            if artifact is None:
                return None
            title = artifact.get("title", "未命名")
            slide_count = artifact.get("slide_count", 0)
            artifact_id = artifact.get("artifact_id", "")
            project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
            svg_dir = _os.path.join(project_root, "data", "ppt-output", artifact_id)
            svg_files = sorted(
                [f for f in _os.listdir(svg_dir) if f.startswith("source_slide_") and f.endswith(".svg")]
            ) if _os.path.isdir(svg_dir) else []
            file_list = "\n".join(f"  - {_os.path.join(svg_dir, f)}" for f in svg_files) if svg_files else "  （文件列表读取失败，请从对话历史中找到上次的 SVG）"
            return (
                f"\n\n---\n"
                f"## 注意：当前对话已有一个 PPT（{title}，{slide_count} 页）\n"
                f"用户可能要修改它。请先用文件工具读取以下 SVG 源文件，在此基础上修改后输出**完整的修改后 SVG**（每页一个 ```svg 代码块）：\n"
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
        if response_mode != "ppt-svg" or requested_max_steps is not None:
            return
        current_max_steps = getattr(session, "max_steps", self.settings.agent_max_steps)
        if current_max_steps < self.settings.agent_max_steps:
            session.max_steps = self.settings.agent_max_steps

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
        id_column: str,
        user: UserModel,
    ) -> None:
        with create_db_session() as db:
            row = db.get(model_type, record_id)
            if row is None:
                return
            session_id = row.session_id
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

    def _record_usage_event(
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

    async def stream_chat(self, request: AgentStreamRequest, user: UserModel | None = None) -> AsyncIterator[dict[str, Any]]:
        runtime_profile = self._resolve_runtime_profile(request, user)
        response_mode = runtime_profile.response_mode
        ppt_mode = response_mode == "ppt-svg"
        agent = self._get_agent(runtime_profile)
        if user is not None:
            await self.ensure_session_access(request, user)
        await self._load_session_if_needed(agent, request)

        # Inject design system catalog for PPT mode
        message = request.message
        if ppt_mode:
            message = self._inject_design_catalog(message)
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
                async for event in agent.stream_events(message, session=session):
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
                        artifact = await self.ppt_artifacts.create_from_text(
                            session.session_id, collected_text,
                            mode="ppt-svg",
                        )
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
                            self._record_usage_event(
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
                            self._record_usage_event(
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
                        self._record_usage_event(
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
            await self._ensure_record_owner(approval_id, ApprovalModel, "approval_id", current_user)
        return await self.approval_manager.decide(approval_id, status=status, reason=reason)

    async def get_session_state(self, session_id: str) -> dict[str, Any]:
        stored = await self.storage.describe(session_id)
        if stored is None:
            stored = {"session_id": session_id, "storage": "sqlalchemy", "message_count": 0}
        stored["pending_approvals"] = await self.approval_manager.get_pending(session_id)
        return stored

    async def get_ppt_artifact(self, artifact_id: str, current_user: UserModel | None = None) -> dict[str, Any] | None:
        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, "artifact_id", current_user)
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

        _logger = logging.getLogger("ppt_export")

        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, "artifact_id", current_user)

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
                svg_path.write_text(svg_content, encoding="utf-8")
                svg_paths.append(svg_path)

            output_path = tmpdir_path / "output.pptx"
            create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format=canvas_format or "ppt169",
                verbose=False,
                transition=transition,
                use_native_shapes=use_native_shapes,
                use_compat_mode=use_compat_mode,
                animation=animation,
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
