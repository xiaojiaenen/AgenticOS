"""智能体启用范围（all / selected / none）与对话入口拦截 回归。

产品语义（用户明确要求）：

- **指定人使用** → 别人在智能体商店里看不到；就算通过手改请求体塞了
  profile_id，对话入口也直接拦截（模型不会被唤醒）。
- **暂不开放**（none）→ "先不让任何人使用"，等价于上一种的极端情况：
  商店不可见 + 对话被拦，只有所有者本人和管理员能用。

三态的落点是 ``agent_profiles.audience_mode`` + ``agent_profile_audiences``
（名单）。老语义"名单为空 = 全体"被显式的 ``all`` 取代，老数据按
audience 表反推兼容。

注意：测试直连真实数据库，slug/邮箱必须带唯一后缀避免跨用例污染。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AgentProfileModel, UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def create_token(email: str, role: str) -> str:
    """直接建用户并签发 token（与 test_agent_profiles 同口径）。"""
    from app.core.config import get_settings
    from app.core.security import create_access_token, hash_password

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


def _cleanup(slug: str, *emails: str) -> None:
    with create_db_session() as db:
        db.query(AgentProfileModel).filter(AgentProfileModel.slug == slug).delete()
        for email in emails:
            db.query(UserModel).filter(UserModel.email == email).delete()
        db.commit()


def _create_profile(client, token, slug, **extra):
    payload = {
        "name": "Scoped Agent",
        "slug": slug,
        "description": "scoped",
        "system_prompt": "You are a scoped helper.",
        "response_mode": "general",
        "enabled": True,
        "listed": True,
        "tools": [{"tool_name": "calc", "enabled": True, "requires_approval": False}],
    }
    payload.update(extra)
    return client.post(
        "/api/v1/agent-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )


def test_audience_none_hides_agent_from_store_and_blocks_chat(client) -> None:
    """暂不开放：商店里看不到 + 对话入口 403。"""
    suffix = uuid4().hex
    slug = f"none-scope-{suffix}"
    admin_email = f"none-admin-{suffix}@example.com"
    user_email = f"none-user-{suffix}@example.com"

    admin_token = create_token(admin_email, "admin")
    user_token = create_token(user_email, "user")

    try:
        created = _create_profile(client, admin_token, slug, audience_mode="none")
        assert created.status_code == 201, created.text
        profile_id = created.json()["id"]
        assert created.json()["audience_mode"] == "none"

        # 商店里看不到
        store = client.get("/api/v1/agent-store", headers={"Authorization": f"Bearer {user_token}"})
        assert store.status_code == 200
        assert all(item["id"] != profile_id for item in store.json()["items"])

        # 对话入口直接拦截（不启动模型）
        resp = client.post(
            "/api/v1/agent/stream",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"message": "hi", "agent_profile_id": profile_id},
        )
        assert resp.status_code == 403, resp.text
    finally:
        _cleanup(slug, admin_email, user_email)


def test_audience_selected_blocks_non_listed_user_chat(client) -> None:
    """指定用户：名单外的人在商店看不到，对话也被拦。"""
    suffix = uuid4().hex
    slug = f"sel-scope-{suffix}"
    admin_email = f"sel-admin-{suffix}@example.com"
    allowed_email = f"sel-ok-{suffix}@example.com"
    blocked_email = f"sel-no-{suffix}@example.com"

    admin_token = create_token(admin_email, "admin")
    allowed_token = create_token(allowed_email, "user")
    blocked_token = create_token(blocked_email, "user")

    try:
        with create_db_session() as db:
            allowed_user = db.scalar(select(UserModel).where(UserModel.email == allowed_email))
            assert allowed_user is not None
            allowed_user_id = allowed_user.id

        created = _create_profile(
            client, admin_token, slug,
            audience_mode="selected",
            audience_user_ids=[allowed_user_id],
        )
        assert created.status_code == 201, created.text
        profile_id = created.json()["id"]

        blocked_store = client.get(
            "/api/v1/agent-store", headers={"Authorization": f"Bearer {blocked_token}"}
        )
        assert all(item["id"] != profile_id for item in blocked_store.json()["items"])

        blocked_chat = client.post(
            "/api/v1/agent/stream",
            headers={"Authorization": f"Bearer {blocked_token}"},
            json={"message": "hi", "agent_profile_id": profile_id},
        )
        assert blocked_chat.status_code == 403, blocked_chat.text

        # 名单内用户能看到
        allowed_store = client.get(
            "/api/v1/agent-store", headers={"Authorization": f"Bearer {allowed_token}"}
        )
        assert any(item["id"] == profile_id for item in allowed_store.json()["items"])
    finally:
        _cleanup(slug, admin_email, allowed_email, blocked_email)


def test_website_builtin_agent_is_not_listed_by_default() -> None:
    """网站工程师默认不上架（噪声大、审核成本高）。"""
    from app.services.agent_profile_service import AgentProfileService

    with create_db_session() as db:
        AgentProfileService().ensure_defaults(db)
        website = db.scalar(
            select(AgentProfileModel).where(AgentProfileModel.slug == "website")
        )
        assert website is not None
        assert website.listed is False
