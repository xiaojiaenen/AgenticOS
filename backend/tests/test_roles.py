"""角色与能力（RBAC）回归。

这套设计的核心目的是**让权限边界可读、可测、不用满仓库改字符串比较**。
测试锁住三件事：

1. 能力矩阵本身（新增角色/改能力会在这里撞红）
2. 失败即收紧：未知角色绝不意外升权
3. 越权保护：admin 不能把人提成 superadmin（否则绕过 superadmin 独有能力）
"""

from __future__ import annotations

import pytest

from app.core.roles import (
    BASE_USER_CAPS,
    CAP_AGENT_MANAGE,
    CAP_ANNOUNCEMENT_MANAGE,
    CAP_APIKEY_MANAGE,
    CAP_AUDIT_VIEW,
    CAP_CONVERSATION_READ_ANY,
    CAP_DANGEROUS,
    CAP_PROVIDER_MANAGE,
    CAP_SYSTEM_SETTINGS,
    CAP_USER_MANAGE,
    ROLE_CAPABILITIES,
    VALID_ROLES,
    can_enter_admin,
    capabilities_for,
    has_capability,
    is_admin_like,
    normalize_role,
    role_meta_payload,
)


class TestCapabilityMatrix:
    def test_every_role_has_base_user_caps(self):
        for role in ROLE_CAPABILITIES:
            caps = capabilities_for(role)
            assert BASE_USER_CAPS <= caps, f"{role} 缺少基础能力，用户会无法对话"

    def test_privilege_is_monotonic(self):
        """权限档位逐级包含：user ⊂ auditor ⊂ operator ⊂ admin ⊂ superadmin。

        这不是形式要求 —— 若 operator 有而 admin 没有某项能力，
        「升成 admin 反而丢权限」会让管理员莫名其妙。
        """
        order = ["user", "auditor", "operator", "admin", "superadmin"]
        for lower, higher in zip(order, order[1:]):
            assert capabilities_for(lower) <= capabilities_for(higher), (
                f"{higher} 没有包含 {lower} 的全部能力"
            )


class TestConversationPrivacy:
    def test_only_superadmin_can_read_any_conversation(self):
        """对话正文是个人通信：连 admin 都不该能代查。"""
        for role in ("user", "auditor", "operator", "admin"):
            assert not has_capability(role, CAP_CONVERSATION_READ_ANY), (
                f"{role} 不该有读他人对话的能力"
            )
        assert has_capability("superadmin", CAP_CONVERSATION_READ_ANY)

    def test_dangerous_ops_are_superadmin_only(self):
        for role in ("user", "auditor", "operator", "admin"):
            assert not has_capability(role, CAP_DANGEROUS)
        assert has_capability("superadmin", CAP_DANGEROUS)


class TestRoleSeparation:
    def test_auditor_is_read_only(self):
        """审计员能看统计，但任何"改"的能力都没有。"""
        assert has_capability("auditor", CAP_AUDIT_VIEW)
        for write_cap in (
            CAP_AGENT_MANAGE,
            CAP_ANNOUNCEMENT_MANAGE,
            CAP_USER_MANAGE,
            CAP_APIKEY_MANAGE,
            CAP_PROVIDER_MANAGE,
            CAP_SYSTEM_SETTINGS,
        ):
            assert not has_capability("auditor", write_cap), (
                f"审计员不该有 {write_cap}（只读角色）"
            )

    def test_operator_manages_content_not_secrets(self):
        """运营能管内容，但碰不到用户、密钥、提供商与系统设置。"""
        assert has_capability("operator", CAP_AGENT_MANAGE)
        assert has_capability("operator", CAP_ANNOUNCEMENT_MANAGE)
        for forbidden in (
            CAP_USER_MANAGE,
            CAP_APIKEY_MANAGE,
            CAP_PROVIDER_MANAGE,
            CAP_SYSTEM_SETTINGS,
        ):
            assert not has_capability("operator", forbidden), (
                f"运营不该有 {forbidden}"
            )

    def test_admin_has_platform_config(self):
        for cap in (CAP_USER_MANAGE, CAP_PROVIDER_MANAGE, CAP_SYSTEM_SETTINGS):
            assert has_capability("admin", cap)

    def test_enter_admin_scope(self):
        """能进后台 = 有任一项管理能力；普通用户进不去。"""
        assert not can_enter_admin("user")
        assert can_enter_admin("auditor")
        assert can_enter_admin("operator")
        assert can_enter_admin("admin")
        assert can_enter_admin("superadmin")

    def test_admin_like_is_stricter_than_enter_admin(self):
        """运营/审计能进后台，但不算 admin（不能拿到全部管理端点）。"""
        assert can_enter_admin("operator") and not is_admin_like("operator")
        assert can_enter_admin("auditor") and not is_admin_like("auditor")
        assert is_admin_like("admin") and is_admin_like("superadmin")


class TestFailSafeNormalization:
    @pytest.mark.parametrize("raw", [None, "", "   ", "weird", "ADMINISTRATOR", "root"])
    def test_unknown_roles_degrade_to_user(self, raw):
        """未知/空角色一律按普通用户处理 —— 拼错不该意外升权。"""
        assert normalize_role(raw) == "user"
        assert capabilities_for(raw) == BASE_USER_CAPS

    def test_legacy_member_alias(self):
        assert normalize_role("member") == "user"

    def test_case_and_space_insensitive(self):
        assert normalize_role("  ADMIN  ") == "admin"

    def test_valid_roles_matches_matrix(self):
        assert VALID_ROLES == frozenset(ROLE_CAPABILITIES)


class TestRoleMetaPayload:
    def test_covers_all_roles_with_labels(self):
        payload = role_meta_payload()
        assert {item["value"] for item in payload} == set(ROLE_CAPABILITIES)
        for item in payload:
            assert item["label"], f"{item['value']} 缺少中文名"
            assert item["hint"], f"{item['value']} 缺少说明"
            assert isinstance(item["capabilities"], list)
            assert item["capabilities"] == sorted(item["capabilities"])


class TestApiIntegration:
    """端点层：能力随 /auth/me 下发，且改角色不做提权。"""

    def test_me_returns_capabilities(self):
        from fastapi.testclient import TestClient
        from uuid import uuid4

        from app.core.config import get_settings
        from app.core.security import create_access_token, hash_password
        from app.db.models import UserModel
        from app.db.session import create_db_session
        from app.main import app

        email = f"caps-{uuid4().hex}@example.com"
        try:
            with create_db_session() as db:
                user = UserModel(
                    email=email,
                    name="Caps User",
                    password_hash=hash_password("password-123"),
                    role="operator",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                user_id = user.id

            settings = get_settings()
            token = create_access_token(
                {"sub": str(user_id), "email": email, "role": "operator"},
                secret=settings.auth_secret_key,
                expires_in_seconds=600,
            )
            with TestClient(app) as client:
                payload = client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                ).json()

            assert payload["role"] == "operator"
            assert CAP_AGENT_MANAGE in payload["capabilities"]
            assert CAP_USER_MANAGE not in payload["capabilities"]
        finally:
            from sqlalchemy import delete

            with create_db_session() as db:
                db.execute(delete(UserModel).where(UserModel.email == email))
                db.commit()

    def test_operator_cannot_use_admin_endpoints(self):
        """运营能进后台看，但 /users 这类平台管理端点仍然 403。"""
        from fastapi.testclient import TestClient
        from uuid import uuid4

        from app.core.config import get_settings
        from app.core.security import create_access_token, hash_password
        from app.db.models import UserModel
        from app.db.session import create_db_session
        from app.main import app

        email = f"op-{uuid4().hex}@example.com"
        try:
            with create_db_session() as db:
                user = UserModel(
                    email=email,
                    name="Op",
                    password_hash=hash_password("password-123"),
                    role="operator",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                user_id = user.id

            settings = get_settings()
            token = create_access_token(
                {"sub": str(user_id), "email": email, "role": "operator"},
                secret=settings.auth_secret_key,
                expires_in_seconds=600,
            )
            with TestClient(app) as client:
                response = client.get(
                    "/api/v1/users",
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert response.status_code == 403, "运营不该能访问用户管理"
        finally:
            from sqlalchemy import delete

            with create_db_session() as db:
                db.execute(delete(UserModel).where(UserModel.email == email))
                db.commit()


class TestRoleChangeGuards:
    """改角色的越权保护（端点层）。

    这三条是最容易被绕过的权限漏洞，必须钉死：
    - 不能把自己改掉（否则可以自降自升，绕过审计与边界）
    - 不能授予超出自己权限的角色（admin 不能把人提成 superadmin）
    - 未知角色字符串不能进库（拼错会让人莫名丢权限）
    """

    @staticmethod
    def _make_user(email: str, role: str):
        from app.core.security import hash_password
        from app.db.models import UserModel
        from app.db.session import create_db_session

        with create_db_session() as db:
            user = UserModel(
                email=email,
                name="U",
                password_hash=hash_password("password-123"),
                role=role,
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user.id

    @staticmethod
    def _token(user_id: int, email: str, role: str) -> str:
        from app.core.config import get_settings
        from app.core.security import create_access_token

        settings = get_settings()
        return create_access_token(
            {"sub": str(user_id), "email": email, "role": role},
            secret=settings.auth_secret_key,
            expires_in_seconds=600,
        )

    @staticmethod
    def _cleanup(*emails: str):
        from sqlalchemy import delete

        from app.db.models import UserModel
        from app.db.session import create_db_session

        with create_db_session() as db:
            db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
            db.commit()

    def test_admin_cannot_promote_to_superadmin(self):
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from app.main import app

        admin_email = f"g-admin-{uuid4().hex}@example.com"
        target_email = f"g-target-{uuid4().hex}@example.com"
        try:
            admin_id = self._make_user(admin_email, "admin")
            target_id = self._make_user(target_email, "user")
            token = self._token(admin_id, admin_email, "admin")

            with TestClient(app) as client:
                response = client.patch(
                    f"/api/v1/users/{target_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"role": "superadmin"},
                )
            assert response.status_code == 403, "admin 不该能把人提成 superadmin"
            assert "超出自己权限" in response.json().get("detail", "")
        finally:
            self._cleanup(admin_email, target_email)

    def test_cannot_change_own_role(self):
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from app.main import app

        admin_email = f"self-{uuid4().hex}@example.com"
        try:
            admin_id = self._make_user(admin_email, "admin")
            token = self._token(admin_id, admin_email, "admin")
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/v1/users/{admin_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"role": "user"},
                )
            assert response.status_code == 400
            assert "自己的角色" in response.json().get("detail", "")
        finally:
            self._cleanup(admin_email)

    def test_unknown_role_rejected(self):
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from app.main import app

        admin_email = f"unk-{uuid4().hex}@example.com"
        target_email = f"unk-t-{uuid4().hex}@example.com"
        try:
            admin_id = self._make_user(admin_email, "admin")
            target_id = self._make_user(target_email, "user")
            token = self._token(admin_id, admin_email, "admin")
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/v1/users/{target_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"role": "superuser"},  # 不是合法角色
                )
            assert response.status_code == 400
            assert "未知角色" in response.json().get("detail", "")
        finally:
            self._cleanup(admin_email, target_email)

    def test_superadmin_can_promote_to_admin(self):
        """superadmin 能授予 admin（它的能力确实包含 admin 的全部）。"""
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from app.main import app

        su_email = f"su-{uuid4().hex}@example.com"
        target_email = f"su-t-{uuid4().hex}@example.com"
        try:
            su_id = self._make_user(su_email, "superadmin")
            target_id = self._make_user(target_email, "user")
            token = self._token(su_id, su_email, "superadmin")
            with TestClient(app) as client:
                response = client.patch(
                    f"/api/v1/users/{target_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"role": "admin"},
                )
            assert response.status_code == 200
            assert response.json()["role"] == "admin"
        finally:
            self._cleanup(su_email, target_email)

    def test_admin_can_set_operator_and_auditor(self):
        """operator/auditor 的能力是 admin 的子集，admin 有权授予。"""
        from uuid import uuid4

        from fastapi.testclient import TestClient

        from app.main import app

        admin_email = f"set-{uuid4().hex}@example.com"
        op_email = f"set-op-{uuid4().hex}@example.com"
        try:
            admin_id = self._make_user(admin_email, "admin")
            op_id = self._make_user(op_email, "user")
            token = self._token(admin_id, admin_email, "admin")
            with TestClient(app) as client:
                for role in ("operator", "auditor", "user"):
                    response = client.patch(
                        f"/api/v1/users/{op_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"role": role},
                    )
                    assert response.status_code == 200, f"{role} 应该可以授予"
                    assert response.json()["role"] == role
        finally:
            self._cleanup(admin_email, op_email)
