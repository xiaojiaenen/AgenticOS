import pytest

from app.core.config import Settings
from app.schemas.agent import AgentStreamRequest
from app.services.agent_service import AgentService
from wuwei import AgentEvent


class FakeSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


class FakeAgent:
    def __init__(self, events: list[AgentEvent]) -> None:
        self._events = events

    def create_or_get_session(
        self,
        session_id: str | None = None,
        system_prompt: str | None = None,
        max_steps: int | None = None,
        parallel_tool_calls: bool | None = None,
    ) -> FakeSession:
        return FakeSession(session_id or "fake-session")

    async def _stream(self):
        for event in self._events:
            yield event

    def stream_events(self, user_input: str, session: FakeSession):
        return self._stream()


@pytest.mark.anyio
async def test_agent_service_maps_wuwei_events_to_sse_payloads() -> None:
    service = AgentService(Settings(openai_api_key="test-key"))
    service._agent = FakeAgent(
        [
            AgentEvent(
                type="text_delta",
                session_id="demo-session",
                step=0,
                data={"content": "你好"},
            ),
            AgentEvent(
                type="tool_start",
                session_id="demo-session",
                step=0,
                data={
                    "tool_name": "get_time",
                    "tool_call_id": "call_1",
                    "args": {"timezone": "Asia/Shanghai"},
                },
            ),
            AgentEvent(
                type="tool_end",
                session_id="demo-session",
                step=0,
                data={
                    "tool_name": "get_time",
                    "tool_call_id": "call_1",
                    "output": "{\"time\": \"10:00\"}",
                },
            ),
            AgentEvent(
                type="error",
                session_id="demo-session",
                step=0,
                data={
                    "tool_name": "get_time",
                    "tool_call_id": "call_1",
                    "message": "tool failed",
                },
            ),
            AgentEvent(
                type="done",
                session_id="demo-session",
                step=0,
                data={
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                    "latency_ms": 120,
                    "llm_calls": 1,
                },
            ),
        ]
    )

    request = AgentStreamRequest(message="现在几点", session_id="demo-session")
    events = [event async for event in service.stream_chat(request)]

    assert events[0] == {
        "event": "session",
        "data": {"session_id": "demo-session"},
    }
    assert events[1] == {
        "event": "delta",
        "data": {
            "session_id": "demo-session",
            "content": "你好",
        },
    }
    assert events[2] == {
        "event": "tool_calls",
        "data": {
            "session_id": "demo-session",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "get_time",
                        "arguments": {"timezone": "Asia/Shanghai"},
                    },
                }
            ],
        },
    }
    assert events[3] == {
        "event": "tool_results",
        "data": {
            "session_id": "demo-session",
            "tool_calls": [
                {
                    "tool_call_id": "call_1",
                    "name": "get_time",
                    "status": "success",
                    "result": "{\"time\": \"10:00\"}",
                }
            ],
        },
    }
    assert events[4] == {
        "event": "tool_results",
        "data": {
            "session_id": "demo-session",
            "tool_calls": [
                {
                    "tool_call_id": "call_1",
                    "name": "get_time",
                    "status": "error",
                    "result": "tool failed",
                }
            ],
        },
    }
    assert events[5] == {
        "event": "done",
        "data": {
            "session_id": "demo-session",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "latency_ms": 120,
            "llm_calls": 1,
        },
    }
