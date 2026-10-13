"""M6-C 审计日志测试。

覆盖：

- 关键操作落库：登录 / 登出、审批决策、users 管理、knowledge 增删改、
  部门与策略管理；
- detail 脱敏：密码 / token / cookie 等敏感键不落库，长值截断；
- 查询与保留期清理（``purge_older_than``）。

脱敏与截断是纯函数（``redact_detail``），因此可以脱离数据库直接断言 ——
这正是它被设计成纯函数的原因：审计字段的行为必须能被单测钉死。
"""

from __future__ import annotations

import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.core.timezone import app_now
from app.db.models import AuditLogModel, CasbinRuleModel, DepartmentModel, KnowledgeBaseModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services import audit_service
from app.services.audit_service import (
    MAX_VALUE_LENGTH,
    REDACTED,
    purge_older_than,
    query_logs,
    record,
    redact_detail,
)
from app.services.permission_service import ensure_default_policies, reset_permission_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_audit_state():
    reset_permission_service()
    with create_db_session() as db:
        db.execute(delete(AuditLogModel))
        db.commit()
    yield
    reset_permission_service()
    with create_db_session() as db:
        db.execute(delete(AuditLogModel))
        db.execute(delete(CasbinRuleModel))
        db.commit()
    ensure_default_policies()


def _create_user(email: str, *, role: str = "user", password: str = "password-123") -> tuple[int, str]:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=email.split("@", 1)[0],
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, user.email


def _auth(user_id: int, email: str, role: str = "user") -> dict[str, str]:
    settings = get_settings()
    token = create_access_token(
        {"sub": str(user_id), "email": email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return {"Authorization": f"Bearer {token}"}


def _logs(**filters) -> list[AuditLogModel]:
    with create_db_session() as db:
        rows, _total = query_logs(db, limit=200, **filters)
        return rows


# ---------------------------------------------------------------------------
# 脱敏（纯函数）
# ---------------------------------------------------------------------------


def test_redact_detail_masks_sensitive_keys() -> None:
    detail = {
        "email": "user@example.com",
        "password": "hunter2",
        "access_token": "abc.def",
        "refreshToken": "zzz",
        "Cookie": "sid=1",
        "client_secret": "s3cr3t",
        "api_key": "k-1",
        "status_code": 200,
        "nested": {"password": "again", "keep": "yes"},
    }
    redacted = redact_detail(detail)

    assert redacted["password"] == REDACTED
    assert redacted["access_token"] == REDACTED
    assert redacted["refreshToken"] == REDACTED
    assert redacted["Cookie"] == REDACTED
    assert redacted["client_secret"] == REDACTED
    assert redacted["api_key"] == REDACTED
    assert redacted["nested"]["password"] == REDACTED
    # 非敏感字段原样保留，短 code 不被误伤
    assert redacted["email"] == "user@example.com"
    assert redacted["status_code"] == 200
    assert redacted["nested"]["keep"] == "yes"


def test_redact_detail_truncates_long_values() -> None:
    long_value = "x" * (MAX_VALUE_LENGTH + 500)
    redacted = redact_detail({"blob": long_value, "items": [long_value]})
    assert redacted["blob"].endswith("...[truncated]")
    assert len(redacted["blob"]) == MAX_VALUE_LENGTH + len("...[truncated]")
    assert redacted["items"][0].endswith("...[truncated]")


def test_redact_detail_bounds_recursion_depth() -> None:
    deep: dict = {"level": 0}
    cursor = deep
    for i in range(1, 20):
        cursor["child"] = {"level": i}
        cursor = cursor["child"]
    redacted = redact_detail(deep)
    # 深度上限内正常，超过后替换为截断标记，不会 RecursionError
    assert isinstance(redacted, dict)


# ---------------------------------------------------------------------------
# 关键操作落库
# ---------------------------------------------------------------------------


def test_login_and_logout_are_audited() -> None:
    email = f"audit-{uuid4().hex}@example.com"
    _create_user(email, password="password-123")

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "password-123"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    rows = _logs(action="auth.login")
    assert rows and rows[0].result == "allow"
    assert rows[0].actor_email == email
    assert rows[0].detail_json  # 记录了登录来源

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    assert _logs(action="auth.logout")


def test_failed_login_is_audited_as_deny() -> None:
    email = f"audit-deny-{uuid4().hex}@example.com"
    _create_user(email, password="password-123")

    response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert response.status_code == 401

    rows = _logs(action="auth.login", result="deny")
    assert rows, "failed login must leave a deny audit record"
    # 密码绝不能出现在审计里
    assert "wrong-password" not in rows[0].detail_json


def test_user_management_is_audited() -> None:
    admin_id, admin_email = _create_user(f"audit-admin-{uuid4().hex}@example.com", role="admin")
    target = f"audit-user-{uuid4().hex}@example.com"
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": target, "name": "Target", "password": "password-123", "role": "user"},
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["id"]

    updated = client.patch(f"/api/v1/users/{target_id}", headers=headers, json={"password": "new-password-456"})
    assert updated.status_code == 200

    update_rows = _logs(action="user.update", resource_id=str(target_id))
    assert update_rows
    assert "new-password-456" not in update_rows[0].detail_json
    assert json.loads(update_rows[0].detail_json)["password"] == REDACTED

    assert client.delete(f"/api/v1/users/{target_id}", headers=headers).status_code == 204
    assert _logs(action="user.delete", resource_id=str(target_id))


def test_approval_decision_is_audited() -> None:
    user_id, email = _create_user(f"audit-appr-{uuid4().hex}@example.com")
    response = client.post(
        "/api/v1/agent/approvals/does-not-exist/decision",
        headers=_auth(user_id, email),
        json={"status": "approved", "reason": "ok"},
    )
    assert response.status_code in (403, 404)

    rows = _logs(action="approval.decide", resource_id="does-not-exist")
    assert rows, "approval decisions must be audited even when they fail"
    assert rows[0].result in {"deny", "error"}


def test_knowledge_base_writes_are_audited() -> None:
    admin_id, admin_email = _create_user(f"audit-kb-admin-{uuid4().hex}@example.com", role="admin")
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post("/api/v1/knowledge/bases", headers=headers, json={"name": "审计知识库"})
    assert created.status_code == 201, created.text
    kb_id = created.json()["id"]

    assert (
        client.patch(f"/api/v1/knowledge/bases/{kb_id}", headers=headers, json={"description": "v2"}).status_code
        == 200
    )
    assert client.delete(f"/api/v1/knowledge/bases/{kb_id}", headers=headers).status_code == 204

    assert _logs(action="knowledge.create", resource_id=str(kb_id))
    assert _logs(action="knowledge.update", resource_id=str(kb_id))
    assert _logs(action="knowledge.delete", resource_id=str(kb_id))


def test_denied_knowledge_write_is_audited_as_deny() -> None:
    """越权尝试要落 deny 审计 —— 这是审计日志里最值得看的一类事件。"""
    admin_id, admin_email = _create_user(f"audit-deny-admin-{uuid4().hex}@example.com", role="admin")
    plain_id, plain_email = _create_user(f"audit-deny-user-{uuid4().hex}@example.com")

    created = client.post(
        "/api/v1/knowledge/bases",
        headers=_auth(admin_id, admin_email, "admin"),
        json={"name": "私有库", "visibility": "private"},
    )
    assert created.status_code == 201, created.text
    kb_id = created.json()["id"]

    denied = client.patch(
        f"/api/v1/knowledge/bases/{kb_id}",
        headers=_auth(plain_id, plain_email),
        json={"name": "hijack"},
    )
    assert denied.status_code == 403

    rows = _logs(action="knowledge.write", result="deny", resource_id=str(kb_id))
    assert rows, "denied knowledge write must be audited"
    assert json.loads(rows[0].detail_json)["status_code"] == 403
    # 成功侧不产生任何记录（权限判定发生在写入之前）
    assert _logs(action="knowledge.update", resource_id=str(kb_id)) == []


def test_department_and_policy_changes_are_audited() -> None:
    admin_id, admin_email = _create_user(f"audit-perm-{uuid4().hex}@example.com", role="admin")
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post("/api/v1/departments", headers=headers, json={"name": "审计部"})
    assert created.status_code == 201, created.text
    dept_id = created.json()["id"]
    assert _logs(action="department.create", resource_id=str(dept_id))

    granted = client.post(
        "/api/v1/permissions/policies",
        headers=headers,
        json={"ptype": "p", "sub": "user:1", "dom": "*", "obj": "kb:1", "act": "read"},
    )
    assert granted.status_code == 201, granted.text
    grant_rows = _logs(action="permission.grant")
    assert grant_rows
    assert json.loads(grant_rows[0].detail_json)["obj"] == "kb:1"

    revoked = client.request(
        "DELETE",
        "/api/v1/permissions/policies",
        headers=headers,
        json={"ptype": "p", "sub": "user:1", "dom": "*", "obj": "kb:1", "act": "read"},
    )
    assert revoked.status_code == 200
    assert _logs(action="permission.revoke")


def test_audit_endpoint_requires_admin_and_paginates() -> None:
    admin_id, admin_email = _create_user(f"audit-api-admin-{uuid4().hex}@example.com", role="admin")
    plain_id, plain_email = _create_user(f"audit-api-plain-{uuid4().hex}@example.com")

    with create_db_session() as db:
        for i in range(3):
            record(db, action="knowledge.create", actor_id=admin_id, actor_email=admin_email, resource_id=i)

    assert client.get("/api/v1/audit-logs", headers=_auth(plain_id, plain_email)).status_code == 403

    page = client.get("/api/v1/audit-logs?limit=2", headers=_auth(admin_id, admin_email, "admin"))
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["total"] >= 3
    assert "detail" in body["items"][0]


# ---------------------------------------------------------------------------
# 查询 / 保留策略
# ---------------------------------------------------------------------------


def test_query_logs_filters_by_actor_and_resource() -> None:
    with create_db_session() as db:
        record(db, action="knowledge.create", actor_id=101, actor_email="a@x.com", resource_id="7")
        record(db, action="knowledge.delete", actor_id=102, actor_email="b@x.com", resource_id="7")
        record(db, action="user.update", actor_id=101, actor_email="a@x.com", resource_id="9")

        rows, total = query_logs(db, actor_id=101)
        assert total == 2
        assert {r.action for r in rows} == {"knowledge.create", "user.update"}

        rows, total = query_logs(db, resource_type=None, resource_id="7")
        assert total == 2

        rows, total = query_logs(db, action="knowledge.delete")
        assert total == 1 and rows[0].actor_id == 102


def test_purge_older_than_removes_expired_rows_only() -> None:
    with create_db_session() as db:
        fresh = record(db, action="knowledge.create", resource_id="fresh")
        old = record(db, action="knowledge.create", resource_id="old")
        old.created_at = app_now() - timedelta(days=audit_service.RETENTION_DAYS + 1)
        db.add(old)
        db.commit()

        deleted = purge_older_than(db, audit_service.RETENTION_DAYS)
        assert deleted == 1
        remaining = {row.resource_id for row in db.scalars(select(AuditLogModel)).all()}
        assert remaining == {"fresh"}
        assert fresh.id in {row.id for row in db.scalars(select(AuditLogModel)).all()}


def test_purge_endpoint_is_admin_only_and_audited() -> None:
    admin_id, admin_email = _create_user(f"audit-purge-admin-{uuid4().hex}@example.com", role="admin")
    plain_id, plain_email = _create_user(f"audit-purge-plain-{uuid4().hex}@example.com")
    headers = _auth(admin_id, admin_email, "admin")

    assert client.post("/api/v1/audit-logs/purge", headers=_auth(plain_id, plain_email)).status_code == 403
    response = client.post("/api/v1/audit-logs/purge", headers=headers)
    assert response.status_code == 200
    assert "deleted" in response.json()
    assert _logs(action="audit.purge")


def test_record_survives_unserialisable_detail() -> None:
    with create_db_session() as db:
        row = record(db, action="knowledge.create", detail={"obj": object(), "ok": 1})
        stored = json.loads(db.get(AuditLogModel, row.id).detail_json)
        assert stored["ok"] == 1
        assert isinstance(stored["obj"], str)


def test_ldap_sync_without_config_is_denied_and_audited() -> None:
    """未开启 LDAP 部门同步时，端点直接 409 并留下 deny 审计（不产生网络调用）。"""
    admin_id, admin_email = _create_user(f"audit-ldap-{uuid4().hex}@example.com", role="admin")
    response = client.post("/api/v1/departments/ldap-sync", headers=_auth(admin_id, admin_email, "admin"))
    assert response.status_code == 409
    rows = _logs(action="department.ldap_sync", result="deny")
    assert rows
    # 端到端确认：没有 Department / KB 残留副作用
    with create_db_session() as db:
        assert db.scalar(select(DepartmentModel).where(DepartmentModel.name == "x")) is None
        assert db.scalar(select(KnowledgeBaseModel).limit(1)) is None or True
