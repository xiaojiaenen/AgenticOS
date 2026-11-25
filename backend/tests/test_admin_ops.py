"""后台运维 API 回归（docs/design/系统改造总方案.md 战线 E-P1）。

- 批量用户启停/删除（删除叠加 system:dangerous 能力、保护自身与 superadmin）；
- 批量 API Key 吊销/启停（吊销语义与 api_key_service 一致 = 删除记录）；
- 配额管理：system_settings DB 配置优先、check_daily_quota 读到后台调整值；
- 统一审批中心聚合端点（三类待办计数）；
- /health/components 依赖级探针（DB/Redis/配置档位）。
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.db.models import ApiKeyModel, SystemSettingModel, UserModel
from app.db.session import create_db_session
from app.main import app


def _admin_token(email: str, role: str = "superadmin") -> str:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name="Admin Ops",
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        from app.core.config import get_settings

        settings = get_settings()
        token = create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role},
            secret=settings.auth_secret_key,
            expires_in_seconds=3600,
        )
        return token, user.id


def _cleanup(*emails: str) -> None:
    with create_db_session() as db:
        for email in emails:
            db.query(UserModel).filter(UserModel.email == email).delete()
        db.query(SystemSettingModel).filter(SystemSettingModel.key == "quota.daily_token_quota").delete()
        db.commit()


def _client() -> TestClient:
    return TestClient(app)


def test_batch_users_disable_and_enable():
    suffix = uuid4().hex[:8]
    admin_email = f"ops-admin-{suffix}@t.local"
    target_a, target_b = f"op-a-{suffix}@t.local", f"op-b-{suffix}@t.local"
    token, admin_id = _admin_token(admin_email)
    with create_db_session() as db:
        for email in (target_a, target_b):
            db.add(
                UserModel(
                    email=email,
                    name="Target",
                    password_hash=hash_password("password-123"),
                    role="user",
                    is_active=True,
                )
            )
        db.commit()
    client = _client()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with create_db_session() as db:
            ids = [u.id for u in db.query(UserModel).filter(UserModel.email.in_([target_a, target_b])).all()]

        resp = client.post(
            "/api/v1/admin/users/batch",
            headers=headers,
            json={"action": "disable", "user_ids": ids},
        )
        assert resp.status_code == 200, resp.text
        assert sorted(resp.json()["succeeded"]) == sorted(ids)
        with create_db_session() as db:
            assert all(u.is_active is False for u in db.query(UserModel).filter(UserModel.id.in_(ids)).all())

        resp = client.post(
            "/api/v1/admin/users/batch",
            headers=headers,
            json={"action": "enable", "user_ids": ids + [99999999]},
        )
        assert resp.status_code == 200
        assert len(resp.json()["succeeded"]) == 2
        assert resp.json()["failed"][0]["user_id"] == 99999999
    finally:
        _cleanup(admin_email, target_a, target_b)


def test_batch_users_delete_requires_dangerous_capability():
    suffix = uuid4().hex[:8]
    admin_email = f"ops-admin-{suffix}@t.local"
    token, admin_id = _admin_token(admin_email, role="admin")  # admin 无 system:dangerous
    target = f"op-del-{suffix}@t.local"
    with create_db_session() as db:
        db.add(
            UserModel(
                email=target,
                name="Del",
                password_hash=hash_password("password-123"),
                role="user",
                is_active=True,
            )
        )
        db.commit()
        target_id = db.query(UserModel).filter(UserModel.email == target).one().id
    client = _client()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.post(
            "/api/v1/admin/users/batch",
            headers=headers,
            json={"action": "delete", "user_ids": [target_id]},
        )
        assert resp.status_code == 403  # admin 无 dangerous → 拒绝（8.6 红线）

        # self-delete 保护
        resp = client.post(
            "/api/v1/admin/users/batch",
            headers=headers,
            json={"action": "delete", "user_ids": [admin_id]},
        )
        assert resp.status_code == 400
    finally:
        _cleanup(admin_email, target)


def test_batch_api_keys_revoke_and_disable():
    suffix = uuid4().hex[:8]
    admin_email = f"ops-admin-{suffix}@t.local"
    token, admin_id = _admin_token(admin_email)
    with create_db_session() as db:
        keys = [
            ApiKeyModel(user_id=admin_id, name=f"k{i}", prefix=f"sk-agenticos-{suffix}{i}", key_hash=f"hash-{suffix}-{i}")
            for i in range(2)
        ]
        db.add_all(keys)
        db.commit()
        key_ids = [k.id for k in keys]
    client = _client()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.post(
            "/api/v1/admin/api-keys/batch",
            headers=headers,
            json={"action": "disable", "key_ids": key_ids},
        )
        assert resp.status_code == 200
        with create_db_session() as db:
            assert all(k.enabled is False for k in db.query(ApiKeyModel).filter(ApiKeyModel.id.in_(key_ids)).all())

        resp = client.post(
            "/api/v1/admin/api-keys/batch",
            headers=headers,
            json={"action": "revoke", "key_ids": key_ids},
        )
        assert resp.status_code == 200
        with create_db_session() as db:
            assert db.query(ApiKeyModel).filter(ApiKeyModel.id.in_(key_ids)).count() == 0
    finally:
        _cleanup(admin_email)


def test_quota_config_roundtrip_and_check_daily_quota_reads_db():
    suffix = uuid4().hex[:8]
    admin_email = f"ops-admin-{suffix}@t.local"
    token, admin_id = _admin_token(admin_email)
    client = _client()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = client.put(
            "/api/v1/admin/quota",
            headers=headers,
            json={"daily_token_quota": 500000},
        )
        assert resp.status_code == 200, resp.text

        # 普通用户视角的配额检查读到 DB 配置
        from app.services.quota_service import check_daily_quota

        info = check_daily_quota(999999, role="user")
        assert info["quota"] == 500000

        # 管理员豁免不变
        info = check_daily_quota(admin_id, role="superadmin")
        assert info["used"] is None

        # 读端点
        resp = client.get("/api/v1/admin/quota", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["daily_token_quota"] == 500000
        assert resp.json()["source"] == "database"
    finally:
        _cleanup(admin_email)


def test_unified_pending_approvals_endpoint():
    suffix = uuid4().hex[:8]
    admin_email = f"ops-admin-{suffix}@t.local"
    token, _ = _admin_token(admin_email)
    client = _client()
    try:
        resp = client.get(
            "/api/v1/admin/approvals/pending",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body["counts"]) == {"website_deploys", "published_items", "tool_approvals", "total"}
        assert isinstance(body["tool_approvals"], list)
    finally:
        _cleanup(admin_email)


def test_health_components_endpoint():
    client = _client()
    resp = client.get("/api/v1/health/components")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["components"]["database"]["ok"] is True
    assert "agent_engine" in body["components"]["config"]
