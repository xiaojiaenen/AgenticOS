"""API Key 自助端点：创建 / 列表 / 启停 / 删除，以及跨用户隔离。

这些端点此前完全没有测试覆盖，而它们既是对外发凭证的入口，
也是最容易写出「管理员能看到所有人 Key」这类越权的地方。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.api_key_service import authenticate_api_key
from tests.conftest import safe_delete_users


@pytest.fixture
def client():
    return TestClient(app)


def _user_by_id(user_id: int) -> UserModel:
    with create_db_session() as db:
        user = db.get(UserModel, user_id)
        assert user is not None
        db.expunge(user)
        return user


def _make_user(role: str) -> tuple[UserModel, dict[str, str]]:
    email = f"apikey-{uuid4().hex[:8]}@example.com"
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=f"API Key 测试({role})",
            password_hash=hash_password("apikey-test-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = int(user.id)

    token = create_access_token(
        {"sub": str(uid)},
        secret=get_settings().auth_secret_key,
        expires_in_seconds=3600,
    )
    return _user_by_id(uid), {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_user():
    user, headers = _make_user("admin")
    yield user, headers
    safe_delete_users(user.email)


@pytest.fixture
def normal_user():
    user, headers = _make_user("user")
    yield user, headers
    safe_delete_users(user.email)


class TestApiKeyLifecycle:
    def test_create_returns_plaintext_only_once(self, client, admin_user):
        _user, headers = admin_user

        resp = client.post("/api/v1/api-keys", json={"name": "本地 Cursor"}, headers=headers)
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["key"].startswith("sk-agenticos-")
        assert "…" in created["key_masked"]
        assert created["enabled"] is True

        listed = client.get("/api/v1/api-keys", headers=headers).json()["items"]
        assert len(listed) == 1
        # 列表绝不能再吐出明文
        assert "key" not in listed[0]
        assert listed[0]["key_masked"] != created["key"]

    def test_list_carries_owner_identity(self, client, admin_user):
        """管理员看全部 Key 时需要归属人，否则列表只有一串 user_id 无法辨认。"""
        user, headers = admin_user
        client.post("/api/v1/api-keys", json={"name": "owner-check"}, headers=headers)

        item = client.get("/api/v1/api-keys", headers=headers).json()["items"][0]
        assert item["owner_name"] == user.name
        assert item["owner_email"] == user.email

    def test_plaintext_authenticates_and_disable_revokes(self, client, admin_user):
        _user, headers = admin_user
        created = client.post(
            "/api/v1/api-keys", json={"name": "auth-check"}, headers=headers
        ).json()
        assert authenticate_api_key(created["key"]) is not None

        resp = client.post(
            f"/api/v1/api-keys/{created['id']}/enabled",
            json={"enabled": False},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        # 停用必须立即让网关鉴权失败
        assert authenticate_api_key(created["key"]) is None

    def test_delete_then_second_delete_returns_404(self, client, admin_user):
        _user, headers = admin_user
        created = client.post("/api/v1/api-keys", json={"name": "del"}, headers=headers).json()

        assert client.delete(f"/api/v1/api-keys/{created['id']}", headers=headers).status_code == 200
        assert client.delete(f"/api/v1/api-keys/{created['id']}", headers=headers).status_code == 404
        assert client.get("/api/v1/api-keys", headers=headers).json()["items"] == []


class TestApiKeyIsolation:
    def test_requires_authentication(self, client):
        assert client.get("/api/v1/api-keys").status_code == 401

    def test_user_cannot_see_others_keys(self, client, admin_user, normal_user):
        _admin, admin_headers = admin_user
        _user, user_headers = normal_user
        client.post("/api/v1/api-keys", json={"name": "admin-only"}, headers=admin_headers)

        assert client.get("/api/v1/api-keys", headers=user_headers).json()["items"] == []

    def test_user_cannot_delete_others_key(self, client, admin_user, normal_user):
        _admin, admin_headers = admin_user
        _user, user_headers = normal_user
        created = client.post(
            "/api/v1/api-keys", json={"name": "protected"}, headers=admin_headers
        ).json()

        resp = client.delete(f"/api/v1/api-keys/{created['id']}", headers=user_headers)
        assert resp.status_code == 404
        # 越权删除必须没有副作用
        assert len(client.get("/api/v1/api-keys", headers=admin_headers).json()["items"]) == 1

    def test_user_cannot_toggle_others_key(self, client, admin_user, normal_user):
        _admin, admin_headers = admin_user
        _user, user_headers = normal_user
        created = client.post(
            "/api/v1/api-keys", json={"name": "protected-toggle"}, headers=admin_headers
        ).json()

        resp = client.post(
            f"/api/v1/api-keys/{created['id']}/enabled",
            json={"enabled": False},
            headers=user_headers,
        )
        assert resp.status_code == 404
        still_enabled = client.get("/api/v1/api-keys", headers=admin_headers).json()["items"][0]
        assert still_enabled["enabled"] is True
