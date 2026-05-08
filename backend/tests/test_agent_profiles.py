from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentProfileAudienceModel, AgentProfileModel, AgentProfileToolModel, SkillModel, UserInstalledAgentModel, UserModel
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
            db.execute(delete(AgentProfileAudienceModel).where(AgentProfileAudienceModel.profile_id == profile.id))
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


def test_binding_skill_keeps_project_from_forcing_duplicate_skill_approval() -> None:
    suffix = uuid4().hex
    slug = f"skill-agent-{suffix}"
    admin_email = f"skill-agent-admin-{suffix}@example.com"
    cleanup(slug, admin_email)

    try:
        admin_token = create_token(admin_email, "admin")
        with create_db_session() as db:
            skill = SkillModel(
                name="Reference Skill",
                slug=f"reference-skill-{suffix}",
                description="Has references",
                root_dir=str(get_settings().get_skill_storage_dir()),
                enabled=True,
                created_by=None,
            )
            db.add(skill)
            db.commit()
            db.refresh(skill)
            skill_id = skill.id

        create_response = client.post(
            "/api/v1/agent-profiles",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Skill Agent",
                "slug": slug,
                "description": "Skill-aware helper",
                "system_prompt": "Use skills when they are relevant.",
                "response_mode": "general",
                "enabled": True,
                "listed": False,
                "tools": [
                    {"tool_name": "skill", "enabled": False, "requires_approval": False},
                ],
                "skill_ids": [skill_id],
            },
        )
        assert create_response.status_code == 201
        payload = create_response.json()
        skill_tool = next(tool for tool in payload["tools"] if tool["tool_name"] == "skill")
        # 新行为：管理员显式设置 enabled=False 时，绑定 Skill 不会自动启用 skill 工具
        assert skill_tool["enabled"] is False
        assert skill_tool["requires_approval"] is False
    finally:
        with create_db_session() as db:
            db.execute(delete(SkillModel).where(SkillModel.slug == f"reference-skill-{suffix}"))
            db.commit()
        cleanup(slug, admin_email)


def test_disabled_agent_disappears_from_store_and_runtime() -> None:
    suffix = uuid4().hex
    slug = f"disabled-agent-{suffix}"
    admin_email = f"disabled-agent-admin-{suffix}@example.com"
    user_email = f"disabled-agent-user-{suffix}@example.com"
    cleanup(slug, admin_email, user_email)

    try:
        admin_token = create_token(admin_email, "admin")
        user_token = create_token(user_email, "user")

        create_response = client.post(
            "/api/v1/agent-profiles",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Disabled Agent",
                "slug": slug,
                "description": "Will be disabled",
                "system_prompt": "You are a helper.",
                "response_mode": "general",
                "enabled": True,
                "listed": True,
                "tools": [{"tool_name": "calc", "enabled": True, "requires_approval": False}],
            },
        )
        assert create_response.status_code == 201
        profile_id = create_response.json()["id"]

        install_response = client.post(
            f"/api/v1/agent-store/{profile_id}/install",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert install_response.status_code == 200

        disable_response = client.patch(
            f"/api/v1/agent-profiles/{profile_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"enabled": False},
        )
        assert disable_response.status_code == 200
        assert disable_response.json()["enabled"] is False

        store_response = client.get("/api/v1/agent-store", headers={"Authorization": f"Bearer {user_token}"})
        assert store_response.status_code == 200
        assert all(item["id"] != profile_id for item in store_response.json()["items"])

        my_response = client.get("/api/v1/my/agents", headers={"Authorization": f"Bearer {user_token}"})
        assert my_response.status_code == 200
        assert all(item["id"] != profile_id for item in my_response.json()["items"])
    finally:
        cleanup(slug, admin_email, user_email)


def test_selected_audience_agent_only_visible_to_configured_users() -> None:
    suffix = uuid4().hex
    slug = f"audience-agent-{suffix}"
    admin_email = f"audience-admin-{suffix}@example.com"
    allowed_email = f"audience-allowed-{suffix}@example.com"
    blocked_email = f"audience-blocked-{suffix}@example.com"
    cleanup(slug, admin_email, allowed_email, blocked_email)

    try:
        admin_token = create_token(admin_email, "admin")
        allowed_token = create_token(allowed_email, "user")
        blocked_token = create_token(blocked_email, "user")

        with create_db_session() as db:
            allowed_user = db.scalar(select(UserModel).where(UserModel.email == allowed_email))
            assert allowed_user is not None
            allowed_user_id = allowed_user.id

        create_response = client.post(
            "/api/v1/agent-profiles",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Audience Agent",
                "slug": slug,
                "description": "Only for selected users",
                "system_prompt": "You are a scoped helper.",
                "response_mode": "general",
                "enabled": True,
                "listed": True,
                "audience_mode": "selected",
                "audience_user_ids": [allowed_user_id],
                "tools": [{"tool_name": "calc", "enabled": True, "requires_approval": False}],
            },
        )
        assert create_response.status_code == 201
        payload = create_response.json()
        profile_id = payload["id"]
        assert payload["audience_mode"] == "selected"
        assert [user["id"] for user in payload["audience_users"]] == [allowed_user_id]

        allowed_store = client.get("/api/v1/agent-store", headers={"Authorization": f"Bearer {allowed_token}"})
        assert allowed_store.status_code == 200
        assert any(item["id"] == profile_id for item in allowed_store.json()["items"])

        blocked_store = client.get("/api/v1/agent-store", headers={"Authorization": f"Bearer {blocked_token}"})
        assert blocked_store.status_code == 200
        assert all(item["id"] != profile_id for item in blocked_store.json()["items"])
    finally:
        cleanup(slug, admin_email, allowed_email, blocked_email)
