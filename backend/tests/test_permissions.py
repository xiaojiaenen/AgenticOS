"""M6-C 企业权限体系测试。

覆盖设计稿第四节的权限矩阵：

- admin / dept_admin / user × kb read/write/delete × 跨部门
- 策略 CRUD 与角色绑定（管理端点 + service）
- 知识库行级过滤（``require_kb_access`` / ``filter_readable_kb_ids``）
- 部门树物化路径（创建 / 移动 / 子树查询 / 成员）
- OIDC claims → 本地用户 upsert（纯函数）
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
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    AuditLogModel,
    CasbinRuleModel,
    DepartmentModel,
    KnowledgeBaseModel,
    RoleModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app
from app.services.department_service import (
    DepartmentError,
    create_department,
    delete_department,
    members_of_department,
    move_department,
)
from app.services.permission_service import (
    GLOBAL_DOMAIN,
    ensure_default_policies,
    get_permission_service,
    knowledge_base_domains,
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
    """每个用例前后清空策略表、部门树与审计表，并重置 enforcer 单例。

    清空后立刻重新种下内置策略 —— 否则新 enforcer 加载到的是空策略集，
    dept_admin 这类**靠角色 + 内置 p 规则**放行的判定会假阴性。
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


def _create_user(email: str, *, role: str = "user", department_id: int | None = None) -> tuple[int, str]:
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=email.split("@", 1)[0],
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
            department_id=department_id,
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


def _create_department(name: str, parent_id: int | None = None) -> int:
    with create_db_session() as db:
        return create_department(db, name=name, parent_id=parent_id).id


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


def _grant_dept_admin(user_id: int, department_id: int) -> None:
    get_permission_service().add_role_for_user(
        f"user:{user_id}", "dept_admin", f"dept:{department_id}"
    )


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


def test_dept_admin_scoped_to_own_department() -> None:
    dept_a = _create_department("Dept A")
    dept_b = _create_department("Dept B")
    bob_id, bob_email = _create_user(f"perm-bob-{uuid4().hex}@example.com", department_id=dept_a)
    _grant_dept_admin(bob_id, dept_a)

    with create_db_session() as db:
        bob = db.get(UserModel, bob_id)
        service = get_permission_service()
        # 本部门域：读/写/删都放行
        for act in ("read", "write", "delete"):
            assert service.enforce_for_user(bob, act, "kb", 1) is True
        # 切到别的部门域后（dept_admin 的 g 关系不在该域）——拒绝
        assert service.enforce(bob_email and subject_for_user(bob), [f"dept:{dept_b}"], "kb:1", "read") is False
        assert service.enforce_for_user(bob, "read", "user", bob_id) is True  # 自身资源
        assert service.enforce_for_user(bob, "read", "user", bob_id + 1000) is False
    del bob_email


def test_dept_admin_cannot_reach_other_department_knowledge_base() -> None:
    """跨部门隔离：判定的域取自**知识库归属部门**，不是请求者所在部门。

    早期实现用请求者的部门域判定，导致 bob（dept_admin of A）能读写挂在
    dept B 名下的知识库 —— 因为他的请求域永远是 dept:A。
    """
    dept_a = _create_department("Dept X")
    dept_b = _create_department("Dept Y")
    bob_id, _ = _create_user(f"perm-scope-{uuid4().hex}@example.com", department_id=dept_a)
    amy_id, _ = _create_user(f"perm-scope-b-{uuid4().hex}@example.com", department_id=dept_b)
    _grant_dept_admin(bob_id, dept_a)
    _grant_dept_admin(amy_id, dept_b)

    owner_id, _ = _create_user(f"perm-scope-owner-{uuid4().hex}@example.com", role="admin")
    kb_b = _create_kb(owner_id, slug=f"scope-b-{uuid4().hex}", team_id=dept_b)
    kb_a = _create_kb(owner_id, slug=f"scope-a-{uuid4().hex}", team_id=dept_a)
    kb_free = _create_kb(owner_id, slug=f"scope-free-{uuid4().hex}")

    with create_db_session() as db:
        bob = db.get(UserModel, bob_id)
        amy = db.get(UserModel, amy_id)
        assert get_permission_service().enforce_for_user(
            bob, "write", "kb", kb_a, domains=knowledge_base_domains(db.get(KnowledgeBaseModel, kb_a))
        )
        assert not get_permission_service().enforce_for_user(
            bob, "write", "kb", kb_b, domains=knowledge_base_domains(db.get(KnowledgeBaseModel, kb_b))
        )
        assert not get_permission_service().enforce_for_user(
            bob, "write", "kb", kb_free, domains=knowledge_base_domains(db.get(KnowledgeBaseModel, kb_free))
        )
        # dept B 的管理员拿得到自己的库
        assert get_permission_service().enforce_for_user(
            amy, "read", "kb", kb_b, domains=knowledge_base_domains(db.get(KnowledgeBaseModel, kb_b))
        )


def test_dept_admin_knowledge_base_access_via_require_kb_access() -> None:
    from fastapi import HTTPException

    from app.api.deps import require_kb_access

    dept_a = _create_department("Access A")
    dept_b = _create_department("Access B")
    bob_id, _ = _create_user(f"perm-acc-{uuid4().hex}@example.com", department_id=dept_a)
    _grant_dept_admin(bob_id, dept_a)
    owner_id, _ = _create_user(f"perm-acc-owner-{uuid4().hex}@example.com", role="admin")
    kb_b = _create_kb(owner_id, slug=f"acc-b-{uuid4().hex}", team_id=dept_b)
    kb_a = _create_kb(owner_id, slug=f"acc-a-{uuid4().hex}", team_id=dept_a)

    with create_db_session() as db:
        bob = db.get(UserModel, bob_id)
        # 本部门的库：可写
        assert require_kb_access(db, bob, kb_a, "write").id == kb_a
        # 别的部门的库：拒写
        with pytest.raises(HTTPException) as exc:
            require_kb_access(db, bob, kb_b, "write")
        assert exc.value.status_code == 403
        # 别的部门的 org 级公开库仍可读（既有 visibility 语义未被破坏）
        assert require_kb_access(db, bob, kb_b, "read").id == kb_b


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
    assert len(first) == 4  # admin 全权 + dept_admin read/write/delete


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
# 管理端点：策略 / 角色 / 部门
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
    assert {"admin", "dept_admin", "user", "auditor"} <= slugs

    assert client.delete(f"/api/v1/roles/{role_id}", headers=headers).status_code == 200

    # 内置角色不允许删除
    builtin = next(row for row in client.get("/api/v1/roles", headers=headers).json() if row["slug"] == "admin")
    assert client.delete(f"/api/v1/roles/{builtin['id']}", headers=headers).status_code == 400


def test_department_tree_crud_and_member_queries() -> None:
    with create_db_session() as db:
        root = create_department(db, name="总部")
        child = create_department(db, name="研发部", parent_id=root.id)
        grandchild = create_department(db, name="平台组", parent_id=child.id)
        assert root.path == str(root.id)
        assert child.path == f"{root.id}/{child.id}"
        assert grandchild.path == f"{root.id}/{child.id}/{grandchild.id}"

        # 兄弟重名被拒
        with pytest.raises(DepartmentError):
            create_department(db, name="研发部", parent_id=root.id)

        # 成环被拒
        with pytest.raises(DepartmentError):
            move_department(db, root, grandchild.id)

    # 子树成员查询
    member_root, _ = _create_user(f"perm-dept-root-{uuid4().hex}@example.com", department_id=root.id)
    member_leaf, _ = _create_user(f"perm-dept-leaf-{uuid4().hex}@example.com", department_id=grandchild.id)
    outsider, _ = _create_user(f"perm-dept-out-{uuid4().hex}@example.com")
    with create_db_session() as db:
        ids = {u.id for u in members_of_department(db, root.id)}
        assert ids == {member_root, member_leaf}
        assert outsider not in ids
        direct = {u.id for u in members_of_department(db, root.id, include_subdepartments=False)}
        assert direct == {member_root}

    # 软删除：子树停用 + 成员解绑
    with create_db_session() as db:
        stats = delete_department(db, db.get(DepartmentModel, root.id))
        assert stats["deactivated"] == 3
        assert stats["unlinked_users"] == 2
        assert db.get(UserModel, member_root).department_id is None


def test_department_endpoints_and_member_assignment() -> None:
    admin_id, admin_email = _create_user(f"perm-dept-admin-{uuid4().hex}@example.com", role="admin")
    member_id, member_email = _create_user(f"perm-dept-member-{uuid4().hex}@example.com")
    headers = _auth(admin_id, admin_email, "admin")

    created = client.post("/api/v1/departments", headers=headers, json={"name": "财务部"})
    assert created.status_code == 201, created.text
    dept_id = created.json()["id"]
    assert created.json()["path"] == str(dept_id)

    assigned = client.post(
        f"/api/v1/departments/{dept_id}/members",
        headers=headers,
        json={"user_id": member_id, "department_id": dept_id, "dept_admin": True},
    )
    assert assigned.status_code == 200, assigned.text

    members = client.get(f"/api/v1/departments/{dept_id}/members", headers=headers)
    assert [item["id"] for item in members.json()["items"]] == [member_id]

    # 授权后该用户确实拿到了本部门的部门管理员权限
    with create_db_session() as db:
        member = db.get(UserModel, member_id)
        assert get_permission_service().enforce_for_user(member, "write", "kb", 5) is True

    tree = client.get("/api/v1/departments/tree", headers=headers)
    assert tree.status_code == 200
    assert any(node["id"] == dept_id for node in tree.json()["items"])

    roles = client.get(f"/api/v1/permissions/roles/{member_id}", headers=headers)
    assert roles.status_code == 200
    assert "dept_admin" in roles.json()["roles"]

    # 非 admin 不能建部门
    assert (
        client.post("/api/v1/departments", headers=_auth(member_id, member_email), json={"name": "X"}).status_code
        == 403
    )


def test_moving_user_between_departments_revokes_old_dept_admin() -> None:
    dept_a = _create_department("Move A")
    dept_b = _create_department("Move B")
    user_id, _ = _create_user(f"perm-move-{uuid4().hex}@example.com", department_id=dept_a)
    _grant_dept_admin(user_id, dept_a)

    with create_db_session() as db:
        from app.services.department_service import assign_user_department

        user = db.get(UserModel, user_id)
        assert get_permission_service().enforce_for_user(user, "write", "kb", 5) is True
        assign_user_department(db, user, dept_b)
        assert get_permission_service().enforce_for_user(db.get(UserModel, user_id), "write", "kb", 5) is False


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


def test_oidc_department_claim_never_creates_departments() -> None:
    from app.services.oidc_service import claims_to_profile, upsert_oidc_user

    settings = get_settings()
    email = f"oidc-dept-{uuid4().hex}@example.com"
    profile = claims_to_profile({"email": email, "department": "不存在的部门"}, settings)
    with create_db_session() as db:
        user, _ = upsert_oidc_user(db, profile)
        assert user.department_id is None
        assert db.scalar(select(DepartmentModel).where(DepartmentModel.name == "不存在的部门")) is None
