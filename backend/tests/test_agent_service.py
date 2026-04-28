import pytest

from app.core.config import Settings
from app.schemas.agent import AgentStreamRequest
from app.services.agent_service import AgentService, MAX_STEPS_LIMIT_MESSAGE, ThinkingHistoryCompatibilityHook
from wuwei import AgentEvent
from wuwei.llm import Message


class FakeSession:
    def __init__(self, session_id: str, max_steps: int = 10) -> None:
        self.session_id = session_id
        self.max_steps = max_steps


class FakeAgent:
    def __init__(self, events: list[AgentEvent], session: FakeSession | None = None) -> None:
        self._events = events
        self.session = session

    def create_or_get_session(
        self,
        session_id: str | None = None,
        system_prompt: str | None = None,
        max_steps: int | None = None,
        parallel_tool_calls: bool | None = None,
    ) -> FakeSession:
        if self.session is not None:
            return self.session
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
                type="reasoning_delta",
                session_id="demo-session",
                step=0,
                data={"content": "先判断是否需要调用工具。"},
            ),
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

    assert events[0]["event"] == "session"
    assert events[0]["data"]["session_id"] == "demo-session"
    assert events[0]["data"]["storage"] == "sqlalchemy"
    assert events[1] == {
        "event": "run_status",
        "data": {
            "session_id": "demo-session",
            "phase": "thinking",
            "label": "大模型正在思考",
        },
    }
    assert events[2] == {
        "event": "reasoning_delta",
        "data": {
            "session_id": "demo-session",
            "content": "先判断是否需要调用工具。",
        },
    }
    assert events[3] == {
        "event": "run_status",
        "data": {
            "session_id": "demo-session",
            "phase": "streaming",
            "label": "大模型正在输出",
        },
    }
    assert events[4] == {
        "event": "delta",
        "data": {
            "session_id": "demo-session",
            "content": "你好",
        },
    }
    assert events[5] == {
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
    assert events[6] == {
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
    assert events[7] == {
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
    assert events[8] == {
        "event": "run_status",
        "data": {
            "session_id": "demo-session",
            "phase": "done",
            "label": "本轮回复已完成",
        },
    }
    assert events[9]["event"] == "done"
    assert events[9]["data"]["session_id"] == "demo-session"
    assert events[9]["data"]["finish_reason"] == "stop"
    assert events[9]["data"]["usage"] == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    assert events[9]["data"]["latency_ms"] == 120
    assert events[9]["data"]["llm_calls"] == 1


@pytest.mark.anyio
async def test_ppt_mode_lifts_legacy_one_step_session_limit() -> None:
    service = AgentService(Settings(openai_api_key="test-key", agent_max_steps=10))
    session = FakeSession("ppt-session", max_steps=1)
    service._agent = FakeAgent(
        [
            AgentEvent(
                type="done",
                session_id="ppt-session",
                step=0,
                data={"usage": {}, "latency_ms": 10, "llm_calls": 1},
            ),
        ],
        session=session,
    )

    request = AgentStreamRequest(
        message="生成一个产品介绍 PPT",
        session_id="ppt-session",
        response_mode="ppt",
    )
    events = [event async for event in service.stream_chat(request)]

    assert session.max_steps == 10
    assert events[-1]["event"] == "done"


@pytest.mark.anyio
async def test_thinking_history_hook_removes_synthetic_step_limit_reply() -> None:
    hook = ThinkingHistoryCompatibilityHook()
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="生成 PPT"),
        Message(role="assistant", content="", reasoning_content="需要先规划结构。"),
        Message(role="assistant", content=MAX_STEPS_LIMIT_MESSAGE),
        Message(role="user", content="继续"),
    ]

    filtered_messages, _ = await hook.before_llm(None, messages, [], step=0)

    assert [message.content for message in filtered_messages] == [
        "system",
        "生成 PPT",
        "",
        "继续",
    ]
    assert filtered_messages[2].reasoning_content == "需要先规划结构。"
