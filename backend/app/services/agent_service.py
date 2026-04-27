import asyncio
import contextlib
import json
from functools import lru_cache
from typing import Any, AsyncIterator

from wuwei import Agent, AgentEvent, ContextCompressionHook, HitlHook, StorageHook
from wuwei.memory.context_compressor import LLMContextCompressor
from wuwei.runtime import ApprovalPolicy

from app.core.config import Settings, get_settings
from app.services.approval_manager import ApprovalManager
from app.services.ppt_artifact_service import PptArtifactService, strip_ppt_deck_from_text
from app.services.session_storage import DatabaseAgentStorage
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
        self._agent: Agent | None = None

    def ensure_ready(self) -> None:
        self._get_agent()

    def _get_agent(self) -> Agent:
        if self._agent is not None:
            return self._agent

        if not self.settings.openai_api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请先在环境变量或 .env 中配置后再调用 /agent/stream。")

        hooks = [StorageHook(self.storage)]
        if self.settings.hitl_enabled:
            hooks.append(
                HitlHook(
                    provider=self.approval_manager,
                    policy=ApprovalPolicy(
                        require_approval_tools=self.settings.get_hitl_require_approval_tools()
                    ),
                )
            )

        self._agent = Agent.from_env(
            builtin_tools=["time", "file"],
            system_prompt=self.settings.agent_system_prompt,
            max_steps=self.settings.agent_max_steps,
            parallel_tool_calls=self.settings.agent_parallel_tool_calls,
            hooks=hooks,
        )
        if self.settings.context_compression_enabled:
            self._agent.hooks.register(
                ContextCompressionHook(
                    compressor=LLMContextCompressor(self._agent.llm),
                    compress_after_turns=self.settings.context_compress_after_turns,
                    keep_recent_turns=self.settings.context_keep_recent_turns,
                )
            )
        return self._agent

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

    async def stream_chat(self, request: AgentStreamRequest) -> AsyncIterator[dict[str, Any]]:
        agent = self._get_agent()
        await self._load_session_if_needed(agent, request)
        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=request.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
        )
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
        ppt_mode = request.response_mode == "ppt"

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
