from functools import lru_cache
from typing import Any, AsyncIterator

from wuwei import Agent, AgentEvent

from app.core.config import Settings, get_settings
from app.schemas.agent import AgentStreamRequest


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._agent: Agent | None = None

    def ensure_ready(self) -> None:
        self._get_agent()

    def _get_agent(self) -> Agent:
        if self._agent is not None:
            return self._agent

        if not self.settings.openai_api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请先在环境变量或 .env 中配置后再调用 /agent/stream。")

        self._agent = Agent.from_env(
            builtin_tools=["time", "file"],
            system_prompt=self.settings.agent_system_prompt,
            max_steps=self.settings.agent_max_steps,
            parallel_tool_calls=self.settings.agent_parallel_tool_calls,
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

    async def stream_chat(self, request: AgentStreamRequest) -> AsyncIterator[dict[str, Any]]:
        agent = self._get_agent()
        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=request.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
        )

        yield {
            "event": "session",
            "data": {
                "session_id": session.session_id,
            },
        }

        async for event in agent.stream_events(request.message, session=session):
            if event.type == "text_delta":
                yield {
                    "event": "delta",
                    "data": {
                        "session_id": session.session_id,
                        "content": event.data.get("content", ""),
                    },
                }
                continue

            if event.type == "tool_start":
                yield {
                    "event": "tool_calls",
                    "data": {
                        "session_id": session.session_id,
                        "tool_calls": [self._build_tool_call_payload(event)],
                    },
                }
                continue

            if event.type == "tool_end":
                yield {
                    "event": "tool_results",
                    "data": {
                        "session_id": session.session_id,
                        "tool_calls": [
                            self._build_tool_result_payload(
                                event,
                                status="success",
                                result=event.data.get("output"),
                            )
                        ],
                    },
                }
                continue

            if event.type == "done":
                yield {
                    "event": "done",
                    "data": {
                        "session_id": session.session_id,
                        "finish_reason": event.data.get("reason", "stop"),
                        "usage": event.data.get("usage"),
                        "latency_ms": event.data.get("latency_ms"),
                        "llm_calls": event.data.get("llm_calls"),
                    },
                }
                continue

            if event.type == "error":
                if event.data.get("tool_call_id") or event.data.get("tool_name"):
                    yield {
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
                    continue

                yield {
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


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(get_settings())
