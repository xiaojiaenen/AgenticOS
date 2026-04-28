from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.agent_service import get_agent_service


class FakeAgentService:
    def ensure_ready(self) -> None:
        return None

    async def ensure_session_access(self, request, user) -> None:
        return None

    async def stream_chat(self, request, user):
        yield {
            "event": "session",
            "data": {
                "session_id": request.session_id or "test-session",
                "user_id": user.id,
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


def cleanup_test_users(*emails: str) -> None:
    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_user_token(email: str) -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name="Stream User",
            password_hash=hash_password("password-123"),
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    settings = get_settings()
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


def test_agent_stream_endpoint() -> None:
    app.dependency_overrides[get_agent_service] = lambda: FakeAgentService()
    email = "stream-user@example.com"

    try:
        with TestClient(app) as client:
            cleanup_test_users(email)
            token = create_user_token(email)
            with client.stream(
                "POST",
                "/api/v1/agent/stream",
                headers={"Authorization": f"Bearer {token}"},
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
        cleanup_test_users(email)
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
