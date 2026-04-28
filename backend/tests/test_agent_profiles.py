from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentProfileModel, AgentProfileToolModel, UserInstalledAgentModel, UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)


def create_token(email: str, role: str) -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=f"{role.title()} User",
            password_hash=hash_password("password-123"),
            role=role,
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


def cleanup(slug: str, *emails: str) -> None:
    with create_db_session() as db:
        profile = db.scalar(select(AgentProfileModel).where(AgentProfileModel.slug == slug))
        if profile is not None:
            db.execute(delete(UserInstalledAgentModel).where(UserInstalledAgentModel.profile_id == profile.id))
            db.execute(delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id))
            db.delete(profile)
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def test_admin_can_publish_agent_and_user_can_install_it() -> None:
    suffix = uuid4().hex
    slug = f"research-agent-{suffix}"
    admin_email = f"agent-admin-{suffix}@example.com"
    user_email = f"agent-user-{suffix}@example.com"
    cleanup(slug, admin_email, user_email)

    try:
        admin_token = create_token(admin_email, "admin")
        user_token = create_token(user_email, "user")

        create_response = client.post(
            "/api/v1/agent-profiles",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Research Agent",
                "slug": slug,
                "description": "Research helper",
                "system_prompt": "You are a careful research helper.",
                "response_mode": "general",
                "enabled": True,
                "listed": True,
                "tools": [
                    {"tool_name": "calc", "enabled": True, "requires_approval": False},
                    {"tool_name": "skill", "enabled": True, "requires_approval": False},
                ],
            },
        )
        assert create_response.status_code == 201
        profile_id = create_response.json()["id"]

        store_response = client.get("/api/v1/agent-store", headers={"Authorization": f"Bearer {user_token}"})
        assert store_response.status_code == 200
        store_agent = next(item for item in store_response.json()["items"] if item["id"] == profile_id)
        assert store_agent["installed"] is False

        install_response = client.post(
            f"/api/v1/agent-store/{profile_id}/install",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert install_response.status_code == 200
        assert install_response.json()["installed"] is True

        my_response = client.get("/api/v1/my/agents", headers={"Authorization": f"Bearer {user_token}"})
        assert my_response.status_code == 200
        assert any(item["id"] == profile_id for item in my_response.json()["items"])
    finally:
        cleanup(slug, admin_email, user_email)
