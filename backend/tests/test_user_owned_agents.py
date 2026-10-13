"""用户自建智能体：所有权、可见性与工具配置测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.models import AgentProfileModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.core.config import get_settings


def _ensure_user(email: str, role: str = "user") -> int:
    with create_db_session() as db:
        user = db.query(UserModel).filter(UserModel.email == email).first()
        if user is None:
            user = UserModel(
                email=email,
                name=f"测试-{role}",
                password_hash=hash_password("owner-test-123"),
                role=role,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return int(user.id)


def _token(user_id: int, email: str, role: str) -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user_id), "email": email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=3600,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def owner():
    email = "agent-owner@example.com"
    uid = _ensure_user(email)
    return uid, _token(uid, email, "user")


@pytest.fixture
def other():
    email = "agent-other@example.com"
    uid = _ensure_user(email)
    return uid, _token(uid, email, "user")


@pytest.fixture
def admin():
    email = "agent-admin@example.com"
    uid = _ensure_user(email, role="admin")
    return uid, _token(uid, email, "admin")


@pytest.fixture
def client():
    return TestClient(app)


def _create_payload(name: str, **overrides) -> dict:
    payload = {
        "name": name,
        "system_prompt": "你是一个只服务于 A 部门的助手，回答要简短。",
        "response_mode": "general",
        "description": "自建智能体",
    }
    payload.update(overrides)
    return payload


class TestCreateOwnAgent:
    def test_user_can_create_agent(self, client, owner):
        _, headers = owner
        resp = client.post(
            "/api/v1/agent-profiles",
            json=_create_payload("部门小助手"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["owner_id"] is not None
        assert data["is_owner"] is True
        assert data["visibility"] == "private"
        assert data["installed"] is True  # 自己创建的天然可用

    def test_create_with_tools(self, client, owner):
        _, headers = owner
        resp = client.post(
            "/api/v1/agent-profiles",
            json=_create_payload(
                "带工具的助手",
                tools=[
                    {"tool_name": "calc", "enabled": True, "requires_approval": False},
                    {"tool_name": "time", "enabled": True, "requires_approval": False},
                    {"tool_name": "file", "enabled": False, "requires_approval": False},
                ],
            ),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        tools = {t["tool_name"]: t for t in resp.json()["tools"]}
        assert tools["calc"]["enabled"] is True
        assert tools["time"]["enabled"] is True
        assert tools["file"]["enabled"] is False

    def test_create_with_unknown_tool_rejected(self, client, owner):
        _, headers = owner
        resp = client.post(
            "/api/v1/agent-profiles",
            json=_create_payload(
                "坏助手",
                tools=[{"tool_name": "not_a_real_tool", "enabled": True, "requires_approval": False}],
            ),
            headers=headers,
        )
        assert resp.status_code == 400

    def test_requires_login(self, client):
        resp = client.post("/api/v1/agent-profiles", json=_create_payload("x"))
        assert resp.status_code in (401, 403)


class TestOwnership:
    def test_owner_can_update(self, client, owner):
        _, headers = owner
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("可改的"), headers=headers
        ).json()
        resp = client.patch(
            f"/api/v1/agent-profiles/{created['id']}",
            json={"description": "改过了"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "改过了"

    def test_other_user_cannot_update(self, client, owner, other):
        _, oh = owner
        _, th = other
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("别人的"), headers=oh
        ).json()
        resp = client.patch(
            f"/api/v1/agent-profiles/{created['id']}",
            json={"description": "我要改"},
            headers=th,
        )
        assert resp.status_code == 403

    def test_other_user_cannot_delete(self, client, owner, other):
        _, oh = owner
        _, th = other
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("别删"), headers=oh
        ).json()
        resp = client.delete(f"/api/v1/agent-profiles/{created['id']}", headers=th)
        assert resp.status_code == 403

    def test_admin_can_update_any(self, client, owner, admin):
        _, oh = owner
        _, ah = admin
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("管理员要改"), headers=oh
        ).json()
        resp = client.patch(
            f"/api/v1/agent-profiles/{created['id']}",
            json={"description": "管理员改的"},
            headers=ah,
        )
        assert resp.status_code == 200

    def test_builtin_not_deletable_even_by_owner(self, client, admin):
        _, ah = admin
        with create_db_session() as db:
            builtin = db.query(AgentProfileModel).filter(
                AgentProfileModel.is_builtin.is_(True)
            ).first()
            assert builtin is not None
            builtin_id = builtin.id
        resp = client.delete(f"/api/v1/agent-profiles/{builtin_id}", headers=ah)
        assert resp.status_code in (400, 403)


class TestStoreVisibility:
    def test_private_agent_visible_to_owner_in_my_agents(self, client, owner):
        _, headers = owner
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("私密助手"), headers=headers
        ).json()
        mine = client.get("/api/v1/my/agents", headers=headers).json()
        assert any(item["id"] == created["id"] for item in mine["items"])

    def test_private_agent_not_in_other_store(self, client, owner, other):
        _, oh = owner
        _, th = other
        created = client.post(
            "/api/v1/agent-profiles", json=_create_payload("只给自己"), headers=oh
        ).json()
        store = client.get("/api/v1/agent-store", headers=th).json()
        assert not any(item["id"] == created["id"] for item in store["items"])

    def test_public_agent_appears_in_store(self, client, owner, other):
        _, oh = owner
        _, th = other
        created = client.post(
            "/api/v1/agent-profiles",
            json=_create_payload("公开助手", visibility="public"),
            headers=oh,
        ).json()
        assert created["visibility"] == "public"
        store = client.get("/api/v1/agent-store", headers=th).json()
        assert any(item["id"] == created["id"] for item in store["items"])

    def test_other_user_sees_is_owner_false(self, client, owner, other):
        _, oh = owner
        _, th = other
        created = client.post(
            "/api/v1/agent-profiles",
            json=_create_payload("别人的公开助手", visibility="public"),
            headers=oh,
        ).json()
        store = client.get("/api/v1/agent-store", headers=th).json()
        item = next(i for i in store["items"] if i["id"] == created["id"])
        assert item["is_owner"] is False
        assert item["installed"] is False