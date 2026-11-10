"""内置智能体无需安装：对话页选择器里必须始终可见、可直接使用。

回归背景
--------
``/my/agents`` 原来只返回「已安装 ∪ 自建」。内置智能体一旦没有安装记录
（例如用户点过卸载、或老库里漏装），对话页的智能体选择器就是空的 ——
表现为「内置智能体在对话里根本没有」。``resolve_runtime`` 还会再拦一次
（``Please install this agent before using it``）。

正确语义：内置智能体是平台自带能力，可见性由 ``enabled`` + 可见范围决定，
与安装记录无关；只有「别人发布、我要用」的商店智能体才要求先安装。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentProfileModel, UserInstalledAgentModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.agent_profile_service import AgentProfileService

client = TestClient(app)


def _ensure_user(email: str, role: str = "user") -> UserModel:
    with create_db_session() as db:
        user = db.query(UserModel).filter(UserModel.email == email).first()
        if user is None:
            user = UserModel(
                email=email,
                name=f"内置-{role}",
                password_hash=hash_password("Test-pass-123456"),
                role=role,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        db.expunge(user)
        return user


def _headers(user: UserModel) -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_without_installs() -> UserModel:
    """一个**没有任何安装记录**的普通用户。"""
    user = _ensure_user(f"noinstall-{uuid.uuid4().hex[:8]}@example.com")
    with create_db_session() as db:
        db.query(UserInstalledAgentModel).filter(
            UserInstalledAgentModel.user_id == user.id
        ).delete()
        db.commit()
    return user


def test_my_agents_lists_builtin_without_install(user_without_installs: UserModel) -> None:
    """没有任何安装记录时，内置智能体仍出现在 /my/agents。"""
    response = client.get("/api/v1/my/agents", headers=_headers(user_without_installs))
    assert response.status_code == 200

    items = response.json()["items"]
    builtin_slugs = {item["slug"] for item in items if item["is_builtin"]}
    assert builtin_slugs, "内置智能体不应因为缺少安装记录而从对话列表消失"
    # 至少通用助手必须在（它是模式默认智能体，选择器回退依赖它）
    assert "general" in builtin_slugs


def test_builtin_reported_as_available(user_without_installs: UserModel) -> None:
    """内置智能体在序列化里直接标记 installed=true，前端不该显示「安装」。"""
    response = client.get("/api/v1/my/agents", headers=_headers(user_without_installs))
    assert response.status_code == 200

    builtins = [item for item in response.json()["items"] if item["is_builtin"]]
    assert builtins
    assert all(item["installed"] for item in builtins)


def test_builtin_resolves_at_runtime_without_install(user_without_installs: UserModel) -> None:
    """未安装的内置智能体也能 resolve_runtime（否则发消息会被 403 拦掉）。"""
    with create_db_session() as db:
        profile = db.query(AgentProfileModel).filter(
            AgentProfileModel.slug == "general",
            AgentProfileModel.is_builtin.is_(True),
        ).first()
        assert profile is not None, "内置通用助手不存在，种子没跑起来"
        profile_id = int(profile.id)

    runtime = AgentProfileService().resolve_runtime(profile_id, user_without_installs)
    assert runtime.profile_id == profile_id


def test_store_agent_still_requires_install() -> None:
    """非内置的商店智能体仍然需要安装 —— 不要把上面的放宽扩大化。"""
    service = AgentProfileService()
    with create_db_session() as db:
        # 找一个「非内置、不属于该用户」的已上架 profile
        candidate = (
            db.query(AgentProfileModel)
            .filter(
                AgentProfileModel.is_builtin.is_(False),
                AgentProfileModel.enabled.is_(True),
                AgentProfileModel.listed.is_(True),
            )
            .first()
        )
        if candidate is None:
            pytest.skip("库里没有可用于验证的非内置商店智能体")
        profile_id = int(candidate.id)

    user = _ensure_user(f"store-{uuid.uuid4().hex[:8]}@example.com")
    with create_db_session() as db:
        db.query(UserInstalledAgentModel).filter(
            UserInstalledAgentModel.user_id == user.id
        ).delete()
        db.commit()

    with pytest.raises(PermissionError):
        service.resolve_runtime(profile_id, user)
