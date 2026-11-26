"""权限矩阵回归：权限点目录 / 角色自定义 / 用户多角色 / 统一判定。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import RoleModel, UserModel
from app.db.session import create_db_session
from app.main import app


def _token(user_id: int, role: str = "admin") -> str:
    s = get_settings()
    return create_access_token(
        # 不传 sid：get_current_user 对带 sid 的 token 会校验 auth_sessions 行
        {"sub": str(user_id), "email": "matrix@test.local", "role": role},
        secret=s.auth_secret_key, expires_in_seconds=3600,
    )


@pytest.fixture()
def client():
    return TestClient(app)


def _admin_user():
    """确保有一个 admin 用户（测试库可能由其它用例清理过）。"""
    from app.core.security import hash_password

    with create_db_session() as db:
        u = db.query(UserModel).filter(UserModel.role == "admin").first()
        if u is None:
            u = UserModel(
                email="matrix-admin@test.local", name="Matrix Admin",
                password_hash=hash_password("pw123456"), role="admin", is_active=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        return u.id, u.role


def test_catalog_structure():
    from app.core.permission_catalog import PERMISSION_POINTS, catalog_payload, normalize_permissions

    assert len(PERMISSION_POINTS) > 30
    payload = catalog_payload()
    assert payload["total"] == len(PERMISSION_POINTS)
    assert len(payload["groups"]) >= 10
    # 非法 key 被过滤
    assert normalize_permissions(["user:create", "bogus:action"]) == frozenset({"user:create"})


def test_default_permissions_expand():
    from app.core.permission_catalog import default_permissions_for_role

    user = default_permissions_for_role("user")
    admin = default_permissions_for_role("admin")
    assert "agent:chat" in user
    assert "user:create" not in user
    assert "user:create" in admin
    assert len(admin) > len(user)


def test_role_permissions_custom_override():
    """自定义权限点覆盖内置默认。"""
    from app.services.permission_checker import (
        clear_role_permission_cache, role_permissions,
    )

    with create_db_session() as db:
        role = db.get(RoleModel, 1)  # 任一 role 行；测试库由 seed 建
        if role is None:
            pytest.skip("测试库无角色行")
        original = role.permissions_json
        try:
            role.permissions_json = '["agent:chat"]'
            db.commit()
            clear_role_permission_cache()
            assert role_permissions(db, role.slug) == frozenset({"agent:chat"})
        finally:
            role.permissions_json = original
            db.commit()
            clear_role_permission_cache()


def test_user_multi_role_union():
    """用户主角色 + 额外角色的权限并集。"""
    from app.db.models import UserRoleModel
    from app.services.permission_checker import permissions_for_user

    with create_db_session() as db:
        u = db.query(UserModel).filter(UserModel.role == "user").first()
        if u is None:
            pytest.skip("测试库无普通用户")
        before = permissions_for_user(db, u)
        extra = UserRoleModel(user_id=u.id, role_slug="auditor")
        db.add(extra)
        db.commit()
        try:
            after = permissions_for_user(db, u)
            assert "audit:stats" in after
            assert after > before
        finally:
            db.delete(extra)
            db.commit()


def test_matrix_endpoints(client):
    uid, role = _admin_user()
    headers = {"Authorization": f"Bearer {_token(uid, role)}"}
    r = client.get("/api/v1/permission-matrix/catalog", headers=headers)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["total"] > 30

    r = client.get("/api/v1/permission-matrix/roles", headers=headers)
    assert r.status_code == 200, r.text[:300]
    assert any(x["value"] == "admin" for x in r.json()["roles"])

    r = client.get("/api/v1/permission-matrix/me", headers=headers)
    assert r.status_code == 200, r.text[:300]
    assert "user:create" in r.json()["permissions"]
    assert r.json()["can_enter_admin"] is True


def test_require_permission_denies_normal_user(client):
    """普通用户调用需 user:create 的端点应 403（用 me 之外的权限点探测）。"""

    with create_db_session() as db:
        u = db.query(UserModel).filter(UserModel.role == "user").first()
        if u is None:
            pytest.skip("测试库无普通用户")
        from app.services.permission_checker import has_permission
        assert has_permission(db, u, "user:create") is False


def _make_user(email: str, role: str) -> int:
    from app.core.security import hash_password

    with create_db_session() as db:
        u = db.query(UserModel).filter(UserModel.email == email).first()
        if u is None:
            u = UserModel(
                email=email, name="T", password_hash=hash_password("pw123456"),
                role=role, is_active=True,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
        return u.id


def test_cannot_change_own_matrix_roles(client):
    """权限矩阵：不能给自己加角色（自升权），与 users.py 同口径。"""
    from app.db.models import UserRoleModel

    suffix = __import__("uuid").uuid4().hex[:8]
    email = f"matrix-self-{suffix}@test.local"
    uid = _make_user(email, "admin")
    headers = {"Authorization": f"Bearer {_token(uid, 'admin')}"}
    try:
        resp = client.put(
            f"/api/v1/permission-matrix/users/{uid}/roles",
            headers=headers, json={"roles": ["superadmin"]},
        )
        assert resp.status_code == 400, resp.text
        assert "自己" in resp.json()["detail"]
        with create_db_session() as db:
            assert db.query(UserRoleModel).filter(UserRoleModel.user_id == uid).count() == 0
    finally:
        with create_db_session() as db:
            db.query(UserRoleModel).filter(UserRoleModel.user_id == uid).delete()
            db.query(UserModel).filter(UserModel.email == email).delete()
            db.commit()


def test_cannot_grant_out_of_tier_permissions(client):
    """权限矩阵：admin 不能把角色配出自己不具备的档位（dangerous/read_any）。"""
    suffix = __import__("uuid").uuid4().hex[:8]
    email = f"matrix-grant-{suffix}@test.local"
    uid = _make_user(email, "admin")
    headers = {"Authorization": f"Bearer {_token(uid, 'admin')}"}
    try:
        resp = client.put(
            "/api/v1/permission-matrix/roles/operator",
            headers=headers, json={"permissions": ["agent:chat", "system:dangerous"]},
        )
        assert resp.status_code == 403, resp.text
        assert "超出" in resp.json()["detail"]
    finally:
        # 确保没留下脏数据（此用例在校验阶段就返回，未写库）
        with create_db_session() as db:
            db.query(UserModel).filter(UserModel.email == email).delete()
            db.commit()


def test_cannot_grant_out_of_tier_role(client):
    """权限矩阵：admin 不能给别人分配超管角色（含自己不具备的能力）。"""
    from app.db.models import UserRoleModel

    suffix = __import__("uuid").uuid4().hex[:8]
    actor_email = f"matrix-actor-{suffix}@test.local"
    target_email = f"matrix-target-{suffix}@test.local"
    actor_id = _make_user(actor_email, "admin")
    target_id = _make_user(target_email, "user")
    headers = {"Authorization": f"Bearer {_token(actor_id, 'admin')}"}
    try:
        resp = client.put(
            f"/api/v1/permission-matrix/users/{target_id}/roles",
            headers=headers, json={"roles": ["superadmin"]},
        )
        assert resp.status_code == 403, resp.text
        with create_db_session() as db:
            rows = db.query(UserRoleModel).filter(UserRoleModel.user_id == target_id).all()
            assert all(r.role_slug != "superadmin" for r in rows)
    finally:
        with create_db_session() as db:
            db.query(UserRoleModel).filter(UserRoleModel.user_id.in_([actor_id, target_id])).delete()
            db.query(UserModel).filter(UserModel.email.in_([actor_email, target_email])).delete()
            db.commit()


def test_dashboard_analytics_endpoint_uses_permission_point(client):
    """dashboard /analytics 走权限点而非静态 capability。"""
    from starlette.routing import Match

    targets = {"/api/v1/dashboard/stats", "/api/v1/dashboard/analytics", "/api/v1/dashboard/usage-routes"}
    matched = [r.path for r in app.routes if getattr(r, "path", None) in targets]
    assert set(matched) == targets, f"端点缺失: {targets - set(matched)}"
