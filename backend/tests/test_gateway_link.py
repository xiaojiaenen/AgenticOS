"""LDAP ↔ 企业网关账号联动测试。

前提：平台的 LDAP 账号就是百通 SSO 的同一套账号密码。测试覆盖闭环四环：

1. 登录同步：upsert 本人绑定凭据，密码变更时更新加密列
2. 取号偏好：优先本人凭据；本人失效时不借同事账号（审计隔离）；
   无绑定行时回落共享池（灰度）
3. 失效吊销：重登失败且之前有可用 Cookie → 吊销平台会话（强制重新登录）
4. 不误伤：登录时联动失败不吊销；从未成功过的绑定行不吊销
"""
from __future__ import annotations

import pytest

from sqlalchemy import select

from app.core import data_path
from app.core.encryption import decrypt_safe
from app.db.models import (
    AuthSessionModel,
    LlmProviderCredentialModel,
    LlmProviderModel,
    UserModel,
)
from app.db.session import create_db_session
from app.services.llm_providers import credentials, gateway_link


@pytest.fixture()
def enterprise_provider():
    """建一个企业网关提供商，返回 id。"""
    with create_db_session() as db:
        row = LlmProviderModel(
            name="gw-link-test",
            slug=f"gw-link-{gateway_link.__name__[-4:]}",
            provider_type="enterprise_cookie",
            base_url="https://gw.test/v1",
            enabled=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        pid = row.id
    yield pid
    with create_db_session() as db:
        # 先删凭据再删提供商：避免孤儿凭据行 —— SQLite 会复用被删提供商的
        # 自增 id，孤儿行会被后续测试的「同名 provider」错误继承，
        # 触发审计隔离逻辑（这正是要测的行为，脏数据会让它误伤其他用例）。
        for cred in db.scalars(
            select(LlmProviderCredentialModel).where(
                LlmProviderCredentialModel.provider_id == pid
            )
        ).all():
            db.delete(cred)
        obj = db.get(LlmProviderModel, pid)
        if obj:
            db.delete(obj)
        db.commit()


@pytest.fixture()
def user_id():
    """取或建一个用户（测试库可能为空）。"""
    import secrets

    from app.db.models import UserModel

    with create_db_session() as db:
        user = db.execute(select(UserModel).order_by(UserModel.id).limit(1)).scalar_one_or_none()
        if user is None:
            user = UserModel(
                email="gw-link@example.test",
                name="GW Link Test",
                password_hash=secrets.token_hex(32),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user.id


def _make_session(uid: int, sid: str) -> None:
    from datetime import timedelta

    from app.core.timezone import app_now

    with create_db_session() as db:
        db.add(AuthSessionModel(
            session_id=sid, user_id=uid,
            expires_at=app_now() + timedelta(hours=1),
        ))
        db.commit()


def _cleanup(sid: str) -> None:
    with create_db_session() as db:
        row = db.get(AuthSessionModel, sid)
        if row:
            db.delete(row)
            db.commit()


# ---------------------------------------------------------------------------
# 1. 登录同步
# ---------------------------------------------------------------------------


def test_sync_creates_bound_credential(enterprise_provider, user_id) -> None:
    pairs = gateway_link.sync_ldap_enterprise_credentials(
        user_id, "zhangsan", "Secret!2026"
    )
    assert any(pid == enterprise_provider for pid, _ in pairs), (
        f"应为企业提供商建绑定凭据，实际 {pairs}"
    )
    with create_db_session() as db:
        row = db.scalar(
            select(LlmProviderCredentialModel).where(
                LlmProviderCredentialModel.provider_id == enterprise_provider,
                LlmProviderCredentialModel.user_id == user_id,
            )
        )
    assert row is not None
    assert row.username == "zhangsan"
    assert decrypt_safe(row.password_encrypted, "") == "Secret!2026"
    assert "LDAP 绑定" in row.label


def test_sync_updates_password_on_change(enterprise_provider, user_id) -> None:
    """密码变更后再次登录 → 加密列必须更新为新密码。"""
    gateway_link.sync_ldap_enterprise_credentials(user_id, "zhangsan", "Old!123")
    gateway_link.sync_ldap_enterprise_credentials(user_id, "zhangsan", "New!456")

    with create_db_session() as db:
        row = db.scalar(
            select(LlmProviderCredentialModel).where(
                LlmProviderCredentialModel.provider_id == enterprise_provider,
                LlmProviderCredentialModel.user_id == user_id,
            )
        )
    assert decrypt_safe(row.password_encrypted, "") == "New!456", (
        "旧密码会导致后续自动登录每次都失败 —— 这是本功能的核心"
    )


def test_sync_only_targets_entercookie_providers() -> None:
    """openai_compatible 提供商不该被建绑定凭据。"""
    from sqlalchemy import select

    with create_db_session() as db:
        openai_provider = LlmProviderModel(
            name="gw-link-openai", slug="gw-link-openai-t",
            provider_type="openai_compatible",
            base_url="https://x.test/v1", enabled=True,
        )
        db.add(openai_provider)
        db.commit()
        db.refresh(openai_provider)
        pid = openai_provider.id

    try:
        from sqlalchemy import func

        with create_db_session() as db:
            uid = db.execute(select(UserModel.id).limit(1)).scalar_one()
        gateway_link.sync_ldap_enterprise_credentials(uid, "t", "p")
        with create_db_session() as db:
            n = db.scalar(
                select(func.count(LlmProviderCredentialModel.id)).where(
                    LlmProviderCredentialModel.provider_id == pid
                )
            )
        assert n == 0, "非 enterprise_cookie 提供商不该有绑定凭据"
    finally:
        with create_db_session() as db:
            obj = db.get(LlmProviderModel, pid)
            if obj:
                db.delete(obj)
                db.commit()


# ---------------------------------------------------------------------------
# 2. 取号偏好
# ---------------------------------------------------------------------------


def _add_cred(provider_id: int, *, user_id: int | None, username: str,
              cookie: str = "SESSION=ok", status: str = "active") -> int:
    with create_db_session() as db:
        row = LlmProviderCredentialModel(
            provider_id=provider_id, user_id=user_id, username=username,
            password_encrypted=credentials.encrypt("p"),
            cookie_encrypted=credentials.encrypt(cookie),
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _drop_cred(cred_id: int) -> None:
    with create_db_session() as db:
        obj = db.get(LlmProviderCredentialModel, cred_id)
        if obj:
            db.delete(obj)
            db.commit()


def test_acquire_prefers_own_credential(enterprise_provider, user_id, monkeypatch) -> None:
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    own_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    try:
        token = data_path._current_user_id.set(user_id)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._current_user_id.reset(token)
        assert lease is not None
        assert lease.credential_id == own_id, "应优先取本人绑定的凭据"
    finally:
        _drop_cred(shared_id)
        _drop_cred(own_id)


def test_acquire_dead_own_credential_never_borrows(
    enterprise_provider, user_id, monkeypatch
) -> None:
    """本人凭据失效时**绝不**借同事账号 —— 上游审计身份会变成别人。"""
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    own_dead = _add_cred(
        enterprise_provider, user_id=user_id, username="zhangsan",
        cookie="", status="expired",
    )
    try:
        token = data_path._current_user_id.set(user_id)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._current_user_id.reset(token)
        assert lease is None, "本人凭据失效时不得回落共享池"
    finally:
        _drop_cred(shared_id)
        _drop_cred(own_dead)


def test_acquire_falls_back_to_shared_when_unbound(
    enterprise_provider, user_id, monkeypatch
) -> None:
    """没有绑定行（灰度期老用户）→ 回落共享池，不断供。"""
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    try:
        # [DBG] 现场
        with create_db_session() as db:
            rows = db.scalars(
                select(LlmProviderCredentialModel).where(
                    LlmProviderCredentialModel.provider_id == enterprise_provider
                )
            ).all()
            print(f"\n[DBG] provider={enterprise_provider} user={user_id} rows="
                  f"{[(r.id, r.user_id, r.status, r.disabled, r.failure_count, bool(r.cookie_encrypted)) for r in rows]}")
        token = data_path._current_user_id.set(user_id)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._current_user_id.reset(token)
        print(f"[DBG] lease={lease}")
        assert lease is not None
        assert lease.credential_id == shared_id
    finally:
        _drop_cred(shared_id)


def test_acquire_shared_for_anonymous(enterprise_provider, monkeypatch) -> None:
    """匿名上下文（如定时任务）走共享池。"""
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    try:
        lease = credentials.acquire(enterprise_provider)
        assert lease is not None
    finally:
        _drop_cred(shared_id)


# ---------------------------------------------------------------------------
# 3. 失效吊销
# ---------------------------------------------------------------------------


def test_auth_failure_revokes_platform_sessions(
    enterprise_provider, user_id
) -> None:
    """密码改了 → 自动重登失败 → 平台会话被吊销（强制重新登录）。"""
    cred_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    sid = f"rev-{cred_id}"
    _make_session(user_id, sid)
    try:
        gateway_link.handle_credential_auth_failure(
            cred_id, "登录后缺少会话 Cookie：可能是账号密码错误或登录流程已变更",
            allow_revoke=True,
        )
        with create_db_session() as db:
            row = db.get(AuthSessionModel, sid)
        assert row.revoked_at is not None, "应吊销平台会话强制重新登录"
    finally:
        _cleanup(sid)
        _drop_cred(cred_id)


def test_no_revoke_when_never_had_cookie(enterprise_provider, user_id) -> None:
    """从未成功过 Cookie 的绑定行失败（可能是 SSO 改版）→ 不该踢人。"""
    from app.core.encryption import encrypt

    with create_db_session() as db:
        row = LlmProviderCredentialModel(
            provider_id=enterprise_provider, user_id=user_id,
            username="zhangsan", password_encrypted=encrypt("p"),
            cookie_encrypted="",  # 从未登录成功
            status="failed",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        cred_id = row.id

    sid = f"norev-{cred_id}"
    _make_session(user_id, sid)
    try:
        gateway_link.handle_credential_auth_failure(
            cred_id, "可能是账号密码错误", allow_revoke=True
        )
        with create_db_session() as db:
            sess = db.get(AuthSessionModel, sid)
        assert sess.revoked_at is None, "从未成功过 → 不该吊销（可能是上游改版）"
    finally:
        _cleanup(sid)
        _drop_cred(cred_id)


def test_no_revoke_at_login_time(enterprise_provider, user_id) -> None:
    """登录时联动失败不吊销 —— 密码刚被 LDAP 验证过，踢人毫无意义。"""
    cred_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    sid = f"logint-{cred_id}"
    _make_session(user_id, sid)
    try:
        gateway_link.handle_credential_auth_failure(
            cred_id, "可能是账号密码错误", allow_revoke=False
        )
        with create_db_session() as db:
            sess = db.get(AuthSessionModel, sid)
        assert sess.revoked_at is None
    finally:
        _cleanup(sid)
        _drop_cred(cred_id)


def test_shared_credential_failure_never_revokes_anyone(
    enterprise_provider, user_id
) -> None:
    """共享凭据失败不该吊销任何用户 —— 它不属于任何个人。"""
    cred_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    sid = f"shr-{cred_id}"
    _make_session(user_id, sid)
    try:
        gateway_link.handle_credential_auth_failure(
            cred_id, "可能是账号密码错误", allow_revoke=True
        )
        with create_db_session() as db:
            sess = db.get(AuthSessionModel, sid)
        assert sess.revoked_at is None
    finally:
        _cleanup(sid)
        _drop_cred(cred_id)


def test_auth_failure_keyword_detection() -> None:
    assert gateway_link.looks_like_auth_failure("可能是账号密码错误或登录流程已变更")
    assert gateway_link.looks_like_auth_failure("Invalid credentials")
    assert not gateway_link.looks_like_auth_failure("登录超时，请检查网络")
