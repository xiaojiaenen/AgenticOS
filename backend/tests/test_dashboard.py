from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentMessageModel, AgentSessionModel, AgentUsageEventModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.session_storage import dump_json

client = TestClient(app)


def cleanup_records(*emails: str) -> None:
    with create_db_session() as db:
        users = db.scalars(select(UserModel).where(UserModel.email.in_(emails))).all()
        user_ids = [user.id for user in users]
        if user_ids:
            session_ids = db.scalars(select(AgentSessionModel.session_id).where(AgentSessionModel.user_id.in_(user_ids))).all()
            if session_ids:
                db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id.in_(session_ids)))
            db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id.in_(user_ids)))
            db.execute(delete(AgentSessionModel).where(AgentSessionModel.user_id.in_(user_ids)))
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_admin_and_user(admin_email: str, user_email: str) -> tuple[str, int]:
    with create_db_session() as db:
        admin = UserModel(
            email=admin_email,
            name="Stats Admin",
            password_hash=hash_password("password-123"),
            role="admin",
            is_active=True,
        )
        user = UserModel(
            email=user_email,
            name="Stats User",
            password_hash=hash_password("password-123"),
            role="user",
            is_active=True,
        )
        db.add_all([admin, user])
        db.commit()
        db.refresh(admin)
        db.refresh(user)

    settings = get_settings()
    token = create_access_token(
        {"sub": str(admin.id), "email": admin.email, "role": admin.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return token, user.id


def test_dashboard_stats_aggregate_usage() -> None:
    admin_email = f"stats-admin-{uuid4().hex}@example.com"
    user_email = f"stats-user-{uuid4().hex}@example.com"

    try:
        with TestClient(app):
            token, user_id = create_admin_and_user(admin_email, user_email)
            with create_db_session() as db:
                db.add(
                    AgentSessionModel(
                        session_id="stats-session",
                        user_id=user_id,
                        system_prompt="test",
                        metadata_json=dump_json({"user_id": user_id}),
                    )
                )
                db.add(
                    AgentUsageEventModel(
                        user_id=user_id,
                        session_id="stats-session",
                        model_name="gpt-test",
                        response_mode="general",
                        input_tokens=120,
                        output_tokens=80,
                        total_tokens=200,
                        llm_calls=2,
                        tool_calls=1,
                        tool_names_json=dump_json(["time"]),
                        latency_ms=900,
                    )
                )
                db.add(
                    AgentMessageModel(
                        session_id="stats-session",
                        message_json=dump_json({"role": "user", "content": "请帮我做一个统计图"}),
                    )
                )
                db.commit()

            response = client.get("/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["total_tokens"] >= 200
        assert payload["summary"]["llm_calls"] >= 2
        assert any(item["name"] == "gpt-test" for item in payload["model_distribution"])
        assert any(item["name"] == "time" for item in payload["tool_distribution"])
        assert any(item["user_id"] == user_id and item["total_tokens"] >= 200 for item in payload["user_usage"])

        conversations_response = client.get(
            "/api/v1/dashboard/conversations",
            headers={"Authorization": f"Bearer {token}"},
            params={"search": "统计图"},
        )
        assert conversations_response.status_code == 200
        conversations_payload = conversations_response.json()
        assert conversations_payload["total"] >= 1
        assert conversations_payload["items"][0]["session_id"] == "stats-session"
        assert conversations_payload["items"][0]["total_tokens"] == 200
    finally:
        cleanup_records(admin_email, user_email)
