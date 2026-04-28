from __future__ import annotations

import shutil
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import SkillModel, UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)


def create_admin_token(email: str) -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name="Skill Admin",
            password_hash=hash_password("password-123"),
            role="admin",
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


def cleanup(skill_slug: str, admin_email: str) -> None:
    with create_db_session() as db:
        skill = db.scalar(select(SkillModel).where(SkillModel.slug == skill_slug))
        if skill is not None:
            shutil.rmtree(get_settings().get_skill_storage_dir() / skill.slug, ignore_errors=True)
            db.delete(skill)
        db.execute(delete(UserModel).where(UserModel.email == admin_email))
        db.commit()


def test_admin_can_create_update_and_delete_skill() -> None:
    suffix = uuid4().hex
    slug = f"skill-{suffix}"
    admin_email = f"skill-admin-{suffix}@example.com"
    cleanup(slug, admin_email)

    try:
        token = create_admin_token(admin_email)
        create_response = client.post(
            "/api/v1/skills",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Research Playbook",
                "slug": slug,
                "description": "Collects structured research notes.",
                "enabled": True,
                "instruction": "Use this skill for research-heavy tasks.",
            },
        )
        assert create_response.status_code == 201
        skill_id = create_response.json()["id"]

        list_response = client.get(
            "/api/v1/skills",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_response.status_code == 200
        assert any(item["id"] == skill_id for item in list_response.json()["items"])

        update_response = client.patch(
            f"/api/v1/skills/{skill_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "description": "Updated description",
                "instruction": "Updated instruction",
            },
        )
        assert update_response.status_code == 200
        assert update_response.json()["description"] == "Updated description"

        delete_response = client.delete(
            f"/api/v1/skills/{skill_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_response.status_code == 204
    finally:
        cleanup(slug, admin_email)
