"""凭据代理 API 安全测试（endpoints/credential_proxy.py）。

安全契约：
1. **令牌门卫**：未配置令牌 → 全部拒绝；缺头/错头 → 403；正确令牌（常数时间
   比较）放行；
2. **精确归属**：必须 (system_id, user_id) 精确命中 —— 系统下他人凭据取不到
   （历史 bug：.first() 无 user_id 过滤会返回任意一条）；
3. **解密返回**：credential_data 解密为明文字典；
4. **validate 不解密**：只回连接状态；
5. **批量**：50 上限、逐条 results/errors、坏条目不影响其它条目。
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.encryption import encrypt
from app.db.models import ExternalSystemModel, ExternalUserCredentialModel, UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture
def proxy_env(monkeypatch):
    """配置内部令牌 + 每用例独立后缀避免库污染。"""
    token = "itest-" + __import__("uuid").uuid4().hex[:8]
    monkeypatch.setattr(
        type(get_settings()), "credential_proxy_token",
        property(lambda self: token),
        raising=False,
    )
    return token


def _seed_system_and_credential(suffix: str, owner_user_id: int = 0, *, other_user_id: int | None = None):
    """建系统 + 用户的凭据（secret 明文仅本次返回）。"""
    with create_db_session() as db:
        system = ExternalSystemModel(
            name=f"爬虫平台-{suffix}",
            description="",
            category="crawler",
            auth_type="none",
            base_url="https://crawler.internal",
            enabled=True,
        )
        db.add(system)
        db.flush()

        db.add(ExternalUserCredentialModel(
            user_id=owner_user_id,
            system_id=system.id,
            credential_data_encrypted=encrypt('{"api_key": "sk-secret-123", "endpoint": "https://x"}'),
            connection_status="connected",
        ))
        if other_user_id is not None:
            db.add(ExternalUserCredentialModel(
                user_id=other_user_id,
                system_id=system.id,
                credential_data_encrypted=encrypt('{"api_key": "sk-other-user"}'),
                connection_status="connected",
            ))
        db.commit()
        return system.id, owner_user_id


def _cleanup(suffix: str):
    from sqlalchemy import delete

    with create_db_session() as db:
        systems = db.query(ExternalSystemModel).filter(
            ExternalSystemModel.name == f"爬虫平台-{suffix}"
        ).all()
        for s in systems:
            db.execute(delete(ExternalUserCredentialModel).where(
                ExternalUserCredentialModel.system_id == s.id))
            db.delete(s)
        db.commit()


def _make_second_user(suffix: str) -> int:
    with create_db_session() as db:
        user = UserModel(
            email=f"cp-other-{suffix}@test.local",
            name="cp-other",
            password_hash="test-only",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return int(user.id)


# ── 1. 令牌门卫 ──────────────────────────────────────────────────────────


def test_reject_all_when_token_not_configured(client, monkeypatch):
    """未配置 CREDENTIAL_PROXY_TOKEN → 即使带头也全部拒绝（fail-closed）。"""
    monkeypatch.setattr(
        type(get_settings()), "credential_proxy_token",
        property(lambda self: ""),
        raising=False,
    )
    resp = client.post("/api/v1/credential-proxy/get", json={"system_id": 1, "user_id": 1})
    assert resp.status_code == 403


def test_reject_missing_or_wrong_token(client, proxy_env):
    system_id, owner_id = _seed_system_and_credential("gate", owner_user_id=0)
    try:
        # 缺头
        r1 = client.post("/api/v1/credential-proxy/get", json={"system_id": system_id, "user_id": owner_id})
        assert r1.status_code == 403
        # 错头
        r2 = client.post(
            "/api/v1/credential-proxy/get",
            json={"system_id": system_id, "user_id": owner_id},
            headers={"X-Internal-Token": "wrong-token"},
        )
        assert r2.status_code == 403
    finally:
        _cleanup("gate")


def test_validate_also_gated(client, proxy_env):
    """validate 端点同样被令牌门卫保护。"""
    resp = client.post("/api/v1/credential-proxy/validate", json={"system_id": 1, "user_id": 1})
    assert resp.status_code == 403


def test_batch_also_gated(client, proxy_env):
    resp = client.post("/api/v1/credential-proxy/batch", json={"requests": []})
    assert resp.status_code == 403


# ── 2. 精确归属 + 解密返回 ────────────────────────────────────────────────


def test_get_credential_happy_path_decrypts(client, proxy_env):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    with create_db_session() as db:
        other = UserModel(email=f"cp-x-{suffix}@test.local", name="x", password_hash="t")
        db.add(other)
        db.commit()
        db.refresh(other)
        other_id = int(other.id)

    system_id, owner_id = _seed_system_and_credential(suffix, owner_user_id=0, other_user_id=other_id)
    try:
        resp = client.post(
            "/api/v1/credential-proxy/get",
            json={"system_id": system_id, "user_id": owner_id},
            headers={"X-Internal-Token": proxy_env},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["system_id"] == system_id
        assert body["system_name"].startswith("爬虫平台-")
        assert body["credential_data"] == {"api_key": "sk-secret-123", "endpoint": "https://x"}
        assert body["connection_status"] == "connected"
    finally:
        _cleanup(suffix)


def test_get_credential_rejects_other_users_credential(client, proxy_env):
    """精确归属回归：同一系统下 B 用户的凭据，A 的 (system_id, user_id) 取不到。"""
    import uuid

    suffix = uuid.uuid4().hex[:8]
    with create_db_session() as db:
        other = UserModel(email=f"cp-o2-{suffix}@test.local", name="o2", password_hash="t")
        db.add(other)
        db.commit()
        db.refresh(other)
        other_id = int(other.id)

    system_id, owner_id = _seed_system_and_credential(suffix, owner_user_id=0, other_user_id=other_id)
    try:
        resp = client.post(
            "/api/v1/credential-proxy/get",
            json={"system_id": system_id, "user_id": 99999999},  # 不存在的 user
            headers={"X-Internal-Token": proxy_env},
        )
        assert resp.status_code == 404
        assert "Credential not found" in resp.json()["detail"]
    finally:
        _cleanup(suffix)


def test_get_credential_404_when_system_missing(client, proxy_env):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    _, owner_id = _seed_system_and_credential(suffix, owner_user_id=0)
    try:
        resp = client.post(
            "/api/v1/credential-proxy/get",
            json={"system_id": 99999999, "user_id": owner_id},
            headers={"X-Internal-Token": proxy_env},
        )
        assert resp.status_code == 404
    finally:
        _cleanup(suffix)


# ── 3. validate（不解密）──────────────────────────────────────────────────


def test_validate_returns_status_without_decryption(client, proxy_env):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    system_id, owner_id = _seed_system_and_credential(suffix, owner_user_id=0)
    try:
        resp = client.post(
            "/api/v1/credential-proxy/validate",
            json={"system_id": system_id, "user_id": owner_id},
            headers={"X-Internal-Token": proxy_env},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["status"] == "connected"
        assert "credential_data" not in body  # 不解密、不返回凭据内容
    finally:
        _cleanup(suffix)


# ── 4. 批量 ───────────────────────────────────────────────────────────────


def test_batch_partial_success(client, proxy_env):
    import uuid

    suffix = uuid.uuid4().hex[:8]
    system_id, owner_id = _seed_system_and_credential(suffix, owner_user_id=0)
    try:
        resp = client.post(
            "/api/v1/credential-proxy/batch",
            json={"requests": [
                {"system_id": system_id, "user_id": owner_id},        # 命中
                {"system_id": system_id, "user_id": 99999999},        # 未命中 → error
                {"system_id": 99999999, "user_id": owner_id},         # 系统不存在 → error
            ]},
            headers={"X-Internal-Token": proxy_env},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) == 1
        assert len(body["errors"]) == 2
        assert body["results"][0]["credential_data"]["api_key"] == "sk-secret-123"
    finally:
        _cleanup(suffix)


def test_batch_rejects_over_50(client, proxy_env):
    resp = client.post(
        "/api/v1/credential-proxy/batch",
        json={"requests": [{"system_id": 1, "user_id": 1}] * 51},
        headers={"X-Internal-Token": proxy_env},
    )
    assert resp.status_code == 422  # max_length=50
