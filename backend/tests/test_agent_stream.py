from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_service import get_agent_service


class FakeAgentService:
    def ensure_ready(self) -> None:
        return None

    async def stream_chat(self, request):
        yield {
            "event": "session",
            "data": {
                "session_id": request.session_id or "test-session",
            },
        }
        yield {
            "event": "delta",
            "data": {
                "session_id": request.session_id or "test-session",
                "content": "hello",
            },
        }
        yield {
            "event": "done",
            "data": {
                "session_id": request.session_id or "test-session",
                "finish_reason": "stop",
                "usage": None,
            },
        }

    async def decide_approval(self, approval_id: str, *, status: str, reason: str | None = None):
        return {
            "approval_id": approval_id,
            "status": status,
            "reason": reason,
        }

    async def get_session_state(self, session_id: str):
        return {
            "session_id": session_id,
            "storage": "sqlalchemy",
            "pending_approvals": [],
        }


def test_agent_stream_endpoint() -> None:
    app.dependency_overrides[get_agent_service] = lambda: FakeAgentService()

    try:
        with TestClient(app) as client:
            with client.stream(
                "POST",
                "/api/v1/agent/stream",
                json={"message": "hi", "session_id": "demo-session"},
            ) as response:
                body = "".join(response.iter_text())

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "event: session" in body
        assert '"session_id": "demo-session"' in body
        assert "event: delta" in body
        assert '"content": "hello"' in body
        assert "event: done" in body
    finally:
        app.dependency_overrides.clear()


def test_agent_approval_decision_endpoint() -> None:
    app.dependency_overrides[get_agent_service] = lambda: FakeAgentService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/approvals/approval-1/decision",
                json={"status": "approved", "reason": "ok"},
            )

        assert response.status_code == 200
        assert response.json() == {
            "approval_id": "approval-1",
            "status": "approved",
            "reason": "ok",
        }
    finally:
        app.dependency_overrides.clear()
