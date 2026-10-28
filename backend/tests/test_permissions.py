"""M6-C 企业权限体系测试。

覆盖设计稿第四节的权限矩阵：

- admin / user × kb read/write/delete
- 策略 CRUD 与角色绑定（管理端点 + service）
- 知识库行级过滤（``require_kb_access`` / ``filter_readable_kb_ids``）
- OIDC claims → 本地用户 upsert（纯函数）

> 部门（departments）与 dept_admin 角色已下线，相关用例随功能一并删除。
- 一次性迁移脚本 ``scripts/migrate_roles_to_policies.py`` 的幂等性

隔离约定
--------
``permission_service`` 是进程内单例（缓存 casbin_rule），每个用例前后都
:func:`_reset_permission_state` 重置，否则策略会跨用例渗透。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    AuditLogModel,
    CasbinRuleModel,
    KnowledgeBaseModel,
    RoleModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app
from app.services.permission_service import (
    GLOBAL_DOMAIN,
    ensure_default_policies,
    get_permission_service,
    reset_permission_service,
    subject_for_user,
)
from app.services.permission_service import assign_default_role_for_user as assign_default_role

client = TestClient(app)


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_permission_state():
    """每个用例前后清空策略表与审计表，并重置 enforcer 单例。

    清空后立刻重新种下内置策略 —— 否则新 enforcer 加载到的是空策略集，
    **靠角色 + 内置 p 规则**放行的判定会假阴性。
    """
    reset_permission_service()
    with create_db_session() as db:
        db.execute(delete(CasbinRuleModel))
        db.execute(delete(AuditLogModel))
        db.commit()
    ensure_default_policies()
    yield
    reset_permission_service()
    with create_db_session() as db:
        db.execute(delete(CasbinRuleModel))
        db.execute(delete(AuditLogModel))
        db.execute(delete(RoleModel).where(RoleModel.is_builtin.is_(False)))
        db.commit()
    ensure_default_policies()


def _create_user(email: str, *, role: str = "user") -> tuple[int, str]:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=email.split("@", 1)[0],
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id, user.email


def _token_for(user_id: int, email: str, role: str = "user") -> str:
    settings = get_settings()
    return create_access_token(
        {"sub": str(user_id), "email": email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


def _auth(user_id: int, email: str, role: str = "user") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token_for(user_id, email, role)}"}


def _create_kb(owner_id: int, *, slug: str, visibility: str = "public", team_id: int | None = None) -> int:
    with create_db_session() as db:
        kb = KnowledgeBaseModel(
            name=slug,
            slug=slug,
            description="",
            purpose="",
            scope="org",
            owner_id=owner_id,
            team_id=team_id,
            visibility=visibility,
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
        return kb.id


# ---------------------------------------------------------------------------
# 权限矩阵
# ---------------------------------------------------------------------------


def test_admin_has_full_access_to_every_resource() -> None:
    admin_id, _ = _create_user(f"perm-admin-{uuid4().hex}@example.com", role="admin")
    with create_db_session() as db:
        user = db.get(UserModel, admin_id)
        service = get_permission_service()
        for act in ("read", "write", "delete"):
            assert service.enforce_for_user(user, act, "kb", 999) is True
            assert service.enforce_for_user(user, act, "user", 12345) is True


def test_plain_user_has_no_kb_access_until_granted() -> None:
    carol_id, _ = _create_user(f"perm-carol-{uuid4().hex}@example.com")
    with create_db_session() as db:
        carol = db.get(UserModel, carol_id)
        service = get_permission_service()
        assert service.enforce_for_user(carol, "read", "kb", 3) is False
        service.add_policy(subject_for_user(carol), "*", "kb:3", "write")
        assert service.enforce_for_user(carol, "write", "kb", 3) is True
        # 直接授权只覆盖被授权的那个资源
        assert service.enforce_for_user(carol, "write", "kb", 4) is False
        assert service.enforce_for_user(carol, "read", "kb", 3) is False


def test_self_resource_access_without_any_policy() -> None:
    """设计稿「user 自身资源」：不需要任何策略就能访问自己的 user 资源。"""
    dave_id, _ = _create_user(f"perm-dave-{uuid4().hex}@example.com")
    with create_db_session() as db:
        dave = db.get(UserModel, dave_id)
        service = get_permission_service()
        assert service.enforce_for_user(dave, "read", "user", dave_id) is True
        assert service.enforce_for_user(dave, "read", "user", dave_id + 1) is False


def test_default_policies_are_idempotent() -> None:
    ensure_default_policies()
    first = get_permission_service().get_policy()
    ensure_default_policies()
    assert get_permission_service().get_policy() == first
    assert len(first) == 1  # 只剩 admin 全权；普通用户靠 self-access 快捷判定


def test_policy_changes_persist_across_reload() -> None:
    erin_id, _ = _create_user(f"perm-erin-{uuid4().hex}@example.com")
    get_permission_service().add_policy(f"user:{erin_id}", "*", "kb:42", "read")
    get_permission_service().reload()
    with create_db_session() as db:
        assert get_permission_service().enforce_for_user(db.get(UserModel, erin_id), "read", "kb", 42) is True


def test_migrate_roles_to_policies_is_idempotent() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        from migrate_roles_to_policies import migrate
    finally:
        sys.path.pop(0)

    admin_id, _ = _create_user(f"perm-mig-admin-{uuid4().hex}@example.com", role="admin")
    plain_id, _ = _create_user(f"perm-mig-user-{uuid4().hex}@example.com", role="user")

    first = migrate(prune=False)
    grouping_after_first = get_permission_service().get_grouping_policy()
    second = migrate(prune=False)
    assert get_permission_service().get_grouping_policy() == grouping_after_first
    assert first["linked"] == second["linked"] >= 2
    assert first["admins"] >= 1

    with create_db_session() as db:
        service = get_permission_service()
        assert "admin" in service.get_roles_for_user(f"user:{admin_id}", "*")
        assert "user" in service.get_roles_for_user(f"user:{plain_id}", GLOBAL_DOMAIN)


# ---------------------------------------------------------------------------
# 知识库行级过滤
# ---------------------------------------------------------------------------


def test_require_kb_access_enforces_row_level_rules() -> None:
    from app.api.deps import require_kb_access
    from fastapi import HTTPException

    owner_id, _ = _create_user(f"perm-kb-owner-{uuid4().hex}@example.com")
    stranger_id, _ = _create_user(f"perm-kb-stranger-{uuid4().hex}@example.com")
    public_kb = _create_kb(owner_id, slug=f"public-{uuid4().hex}")
    private_kb = _create_kb(owner_id, slug=f"private-{uuid4().hex}", visibility="private")

    with create_db_session() as db:
        owner = db.get(UserModel, owner_id)
        stranger = db.get(UserModel, stranger_id)

        # private 库：只有 owner/admin（Casbin 无授权时靠 owner 身份放行）
        assert require_kb_access(db, owner, private_kb, "write").id == private_kb
        with pytest.raises(HTTPException) as exc:
            require_kb_access(db, stranger, private_kb, "read")
        assert exc.value.status_code == 403

        # 写权限：public 库可见但不可写
        assert require_kb_access(db, stranger, public_kb, "read").id == public_kb
        with pytest.raises(HTTPException):
            require_kb_access(db, stranger, public_kb, "write")

        # 直接授权后 stranger 可写
        get_permission_service().add_policy(subject_for_user(stranger), "*", f"kb:{public_kb}", "write")
        assert require_kb_access(db, stranger, public_kb, "write").id == public_kb


def test_filter_readable_kb_ids_row_level() -> None:
    from app.api.deps import filter_readable_kb_ids

    owner_id, _ = _create_user(f"perm-filter-owner-{uuid4().hex}@example.com")
    stranger_id, _ = _create_user(f"perm-filter-other-{uuid4().hex}@example.com")
    public_kb = _create_kb(owner_id, slug=f"f-pub-{uuid4().hex}")
    private_kb = _create_kb(owner_id, slug=f"f-priv-{uuid4().hex}", visibility="private")

    with create_db_session() as db:
        stranger = db.get(UserModel, stranger_id)
        readable = filter_readable_kb_ids(db, stranger, [public_kb, private_kb])
        assert readable == {public_kb}


def test_knowledge_base_endpoints_enforce_permissions() -> None:
    owner_id, owner_email = _create_user(f"perm-ep-owner-{uuid4().hex}@example.com", role="admin")
    stranger_id, stranger_email = _create_user(f"perm-ep-other-{uuid4().hex}@example.com")
    private_kb = _create_kb(owner_id, slug=f"ep-priv-{uuid4().hex}", visibility="private")

    admin_headers = _auth(owner_id, owner_email, "admin")
    user_headers = _auth(stranger_id, stranger_email)

    # 列表只回可见的库
    listing = client.get("/api/v1/knowledge/bases", headers=user_headers)
    assert listing.status_code == 200
    assert private_kb not in [item["id"] for item in listing.json()]

    # 直接访问 private 库 -> 403
    assert client.get(f"/api/v1/knowledge/bases/{private_kb}", headers=user_headers).status_code == 403

    # 写操作 -> 403
    assert (
        client.patch(
            f"/api/v1/knowledge/bases/{private_kb}", headers=user_headers, json={"name": "hacked"}
        ).status_code
        == 403
    )

    # admin 全权
    assert client.get(f"/api/v1/knowledge/bases/{private_kb}", headers=admin_headers).status_code == 200

    # 授权后放行
    with create_db_session() as db:
        get_permission_service().add_policy(f"user:{stranger_id}", "*", f"kb:{private_kb}", "write")
    assert (
        client.patch(
            f"/api/v1/knowledge/bases/{private_kb}", headers=user_headers, json={"name": "renamed"}
        ).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# 管理端点：策略 / 角色
# ---------------------------------------------------------------------------


def test_policy_crud_endpoints() -> None:
    admin_id, admin_email = _create_user(f"perm-pol-admin-{uuid4().hex}@example.com", role="admin")
    target_id, target_email = _create_user(f"perm-pol-target-{uuid4().hex}@example.com")
    admin_headers = _auth(admin_id, admin_email, "admin")
    user_headers = _auth(target_id, target_email)

    # 非 admin 读不了策略
    assert client.get("/api/v1/permissions/policies", headers=user_headers).status_code == 403

    created = client.post(
        "/api/v1/permissions/policies",
        headers=admin_headers,
        json={"ptype": "p", "sub": f"user:{target_id}", "dom": "*", "obj": "kb:88", "act": "read"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["obj"] == "kb:88"

    # 重复添加 -> 400
    assert (
        client.post(
            "/api/v1/permissions/policies",
            headers=admin_headers,
            json={"ptype": "p", "sub": f"user:{target_id}", "dom": "*", "obj": "kb:88", "act": "read"},
        ).status_code
        == 400
    )

    listing = client.get("/api/v1/permissions/policies", headers=admin_headers)
    assert listing.status_code == 200
    assert any(rule["obj"] == "kb:88" for rule in listing.json())

    removed = client.request(
        "DELETE",
        "/api/v1/permissions/policies",
        headers=admin_headers,
        json={"ptype": "p", "sub": f"user:{target_id}", "dom": "*", "obj": "kb:88", "act": "read"},
    )
    assert removed.status_code == 200
    assert (
        client.request(
            "DELETE",
            "/api/v1/permissions/policies",
            headers=admin_headers,
            json={"ptype": "p", "sub": f"user:{target_id}", "dom": "*", "obj": "kb:88", "act": "read"},
        ).status_code
        == 404
    )


def test_role_crud_and_builtin_protection() -> None:
    admin_id, admin_email = _create_user(f"perm-role-admin-{uuid4().hex}@example.com", role="admin")
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post(
        "/api/v1/roles", headers=headers, json={"name": "审计员", "slug": "auditor"}
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["id"]

    listing = client.get("/api/v1/roles", headers=headers)
    slugs = {row["slug"] for row in listing.json()}
    assert {"admin", "user", "auditor"} <= slugs

    assert client.delete(f"/api/v1/roles/{role_id}", headers=headers).status_code == 200

    # 内置角色不允许删除
    builtin = next(row for row in client.get("/api/v1/roles", headers=headers).json() if row["slug"] == "admin")
    assert client.delete(f"/api/v1/roles/{builtin['id']}", headers=headers).status_code == 400


def test_grouping_policy_listing_round_trips_through_delete() -> None:
    """``g`` 列表的 obj 必须是角色名，否则读出来再删会 404。

    旧实现把这个字段写成 "-"，列表与写接口的字段语义不一致。
    """
    admin_id, admin_email = _create_user(f"perm-g-admin-{uuid4().hex}@example.com", role="admin")
    target_id, _ = _create_user(f"perm-g-target-{uuid4().hex}@example.com")
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post(
        "/api/v1/permissions/policies",
        headers=headers,
        json={"ptype": "g", "sub": f"user:{target_id}", "dom": "global", "obj": "user", "act": "-"},
    )
    assert created.status_code == 201, created.text

    listed = client.get("/api/v1/permissions/policies?ptype=g", headers=headers)
    assert listed.status_code == 200
    rule = next(r for r in listed.json() if r["sub"] == f"user:{target_id}")
    assert rule["obj"] == "user"
    assert rule["dom"] == "global"

    # 用列表里拿到的字段原样回传即可删除
    removed = client.request("DELETE", "/api/v1/permissions/policies", headers=headers, json=rule)
    assert removed.status_code == 200, removed.text


def test_department_endpoints_are_gone() -> None:
    """部门整体下线后的回归守护：端点必须 404，不能悄悄复活。

    部门码被重新加回来时，最容易出现的是「界面没了、接口还在」——
    那样等于留了一个没人维护的越权面。
    """
    admin_id, admin_email = _create_user(f"perm-gone-{uuid4().hex}@example.com", role="admin")
    headers = _auth(admin_id, admin_email, "admin")

    for method, path in (
        ("GET", "/api/v1/departments"),
        ("GET", "/api/v1/departments/tree"),
        ("POST", "/api/v1/departments"),
        ("POST", "/api/v1/departments/ldap-sync"),
    ):
        response = client.request(method, path, headers=headers, json={} if method == "POST" else None)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"


def test_new_user_gets_default_role_assignment() -> None:
    admin_id, admin_email = _create_user(f"perm-def-admin-{uuid4().hex}@example.com", role="admin")
    email = f"perm-def-new-{uuid4().hex}@example.com"
    response = client.post(
        "/api/v1/users",
        headers=_auth(admin_id, admin_email, "admin"),
        json={"email": email, "name": "New", "password": "password-123", "role": "user"},
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["id"]

    with create_db_session() as db:
        service = get_permission_service()
        assert "user" in service.get_roles_for_user(f"user:{new_id}", GLOBAL_DOMAIN)
    with create_db_session() as db:
        assign_default_role(db.get(UserModel, new_id))


# ---------------------------------------------------------------------------
# OIDC：claims -> upsert（纯函数）
# ---------------------------------------------------------------------------


def test_oidc_claims_variants_normalize_identically(monkeypatch) -> None:
    from app.services.oidc_service import OidcError, claims_to_profile

    settings = get_settings()
    domain = "example.com"
    # 裸工号补域依赖显式配置；测试里固定下来，不依赖环境变量
    monkeypatch.setattr(settings, "oidc_email_domain", domain)
    expected = {"name": "Zhang San", "role": "user"}
    cases = (
        ({"email": "12345@example.com", "name": "Zhang San"}, "12345@example.com"),
        ({"mail": "12345@example.com", "display_name": "Zhang San"}, "12345@example.com"),
        # 裸工号补域
        ({"preferred_username": "12345", "cn": "Zhang San"}, f"12345@{domain}"),
    )
    for claims, email in cases:
        profile = claims_to_profile(claims, settings)
        assert profile["email"] == email
        assert {k: profile[k] for k in expected} == expected

    with pytest.raises(OidcError):
        claims_to_profile({"sub": "no-email"}, settings)


def test_oidc_role_allowlist_blocks_privilege_escalation() -> None:
    from app.services.oidc_service import claims_to_profile

    settings = get_settings()
    assert claims_to_profile({"email": "a@b.com", "roles": ["root", "superuser"]}, settings)["role"] == "user"
    assert claims_to_profile({"email": "a@b.com", "role": "ADMIN"}, settings)["role"] == "admin"


def test_oidc_upsert_creates_then_updates_without_touching_password() -> None:
    from app.services.oidc_service import claims_to_profile, upsert_oidc_user

    settings = get_settings()
    email = f"oidc-{uuid4().hex}@example.com"
    profile = claims_to_profile({"email": email, "name": "First"}, settings)

    with create_db_session() as db:
        user, created = upsert_oidc_user(db, profile)
        assert created is True
        assert user.auth_source == "oidc"
        first_hash = user.password_hash
        user_id = user.id

        profile["name"] = "Second"
        user2, created2 = upsert_oidc_user(db, profile)
        assert created2 is False
        assert user2.id == user_id
        assert user2.name == "Second"
        assert user2.password_hash == first_hash
