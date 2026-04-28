import asyncio
import contextlib
import json
from functools import lru_cache
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
from wuwei.tools import ToolRegistry
from wuwei.tools.builtin import register_skill_tools

from app.core.config import Settings, get_settings
from app.db.models import AgentUsageEventModel, UserModel
from app.services.approval_manager import ApprovalManager
from app.services.agent_profile_service import AgentProfileService, RuntimeAgentProfile
from app.services.ppt_artifact_service import PptArtifactService, strip_ppt_deck_from_text
from app.services.session_storage import DatabaseAgentStorage, dump_json
from app.services.tool_config_service import ToolConfigService
from app.schemas.agent import AgentStreamRequest


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
        if profile.approval_tools and self.settings.hitl_enabled:
            hooks.append(
                HitlHook(
                    provider=self.approval_manager,
                    policy=ApprovalPolicy(
                        require_approval_tools=set(profile.approval_tools)
                    ),
                )
            )
        if "skill" in profile.builtin_tools:
            hooks.append(SkillHook())

        agent = Agent(
            llm=LLMGateway.from_env(),
            tools=self._build_tool_registry(profile),
            default_system_prompt=profile.system_prompt,
            default_max_steps=1 if profile.response_mode == "ppt" else self.settings.agent_max_steps,
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
        return registry

    @staticmethod
    def _build_tool_call_payload(event: AgentEvent) -> dict[str, Any]:
        return {
            "id": event.data.get("tool_call_id"),
            "function": {
                "name": event.data.get("tool_name") or "工具调用",
                "arguments": event.data.get("args") or {},
            },
        }

    @staticmethod
    def _build_tool_result_payload(
        event: AgentEvent,
        *,
        status: str,
        result: str | None,
    ) -> dict[str, Any]:
        return {
            "tool_call_id": event.data.get("tool_call_id"),
            "name": event.data.get("tool_name") or "工具调用",
            "status": status,
            "result": result,
        }

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
        ppt_mode = response_mode == "ppt"
        agent = self._get_agent(runtime_profile)
        if user is not None:
            await self.ensure_session_access(request, user)
        await self._load_session_if_needed(agent, request)
        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=runtime_profile.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
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
        approval_queue = self.approval_manager.subscribe(session.session_id)

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
                async for event in agent.stream_events(request.message, session=session):
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
                        visible_text = strip_ppt_deck_from_text(collected_text) if artifact else collected_text
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
    ) -> dict[str, Any]:
        return await self.approval_manager.decide(approval_id, status=status, reason=reason)

    async def get_session_state(self, session_id: str) -> dict[str, Any]:
        stored = await self.storage.describe(session_id)
        if stored is None:
            stored = {"session_id": session_id, "storage": "sqlalchemy", "message_count": 0}
        stored["pending_approvals"] = await self.approval_manager.get_pending(session_id)
        return stored

    async def get_ppt_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        return await self.ppt_artifacts.get(artifact_id)


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(get_settings())
