"""通用 LDAP 认证服务测试（不连真实 LDAP 服务器）。

覆盖：

- 配置读写：``save_config`` 加密落库 → ``load_config`` 解密还原；
  未知键被忽略；``config_to_response`` 不回显明文密码；
- ``validate``：缺失字段与过滤器缺 ``{username}`` 占位符时报错；
- ``authenticate``（mock ldap3 连接）：认证成功归一化字段、
  密码错误拒绝、过滤器命中多条记录拒绝、用户不存在拒绝。

> 部门同步（``lookup_user`` / ``apply_department`` / ``department_sync``）随
> 部门功能一并下线，相关用例已删除。

ldap3 是同步 API，服务层已用 ``asyncio.to_thread`` 包裹 —— 这里直接测
同步函数，事件循环行为由 auth 路径的集成测试覆盖。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import SystemSettingModel
from app.db.session import create_db_session
from app.services import ldap_auth_service as svc
from app.services.ldap_auth_service import (
    LdapAuthError,
    LdapConfig,
    LdapConfigError,
    authenticate,
    config_to_response,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# 测试替身：模拟 ldap3 的 Entry / Connection
# ---------------------------------------------------------------------------


class _Attr:
    def __init__(self, value):
        self.value = value


class FakeEntry:
    """模拟 ldap3 Entry：entry[attr].value 取值，缺失抛 KeyError。"""

    def __init__(self, dn: str, attrs: dict):
        self.entry_dn = dn
        self._attrs = attrs

    def __getitem__(self, key: str):
        return _Attr(self._attrs[key])


class FakeServiceConn:
    """模拟服务账号连接：预置搜索结果。"""

    def __init__(self, entries: list[FakeEntry], search_ok: bool = True):
        self.entries = entries
        self._search_ok = search_ok
        self.server = SimpleNamespace(host="fake")
        self.result: dict = {"message": "ok"}

    def search(self, **kwargs):
        self.last_kwargs = kwargs
        return self._search_ok

    def unbind(self):
        pass


class FakeUserConn:
    """模拟用户 DN 二次 bind 的连接。bind_ok 决定 bind() 结果。"""

    bind_ok = True
    opened = True
    result: dict = {"message": "bind failed"}

    def __init__(self, server, user=None, password=None, auto_bind=False):
        assert password, "用户 bind 必须带密码"
        FakeUserConn.last_user_dn = user

    def open(self):
        return FakeUserConn.opened

    def bind(self):
        return FakeUserConn.bind_ok

    def unbind(self):
        pass


def _make_config(**overrides) -> LdapConfig:
    base = dict(
        enabled=True,
        server_url="ldap://dc.corp.com:389",
        bind_dn="cn=svc,dc=corp,dc=com",
        bind_password="svc-secret",
        base_dn="dc=corp,dc=com",
        user_filter="(sAMAccountName={username})",
        email_domain="corp.com",
    )
    base.update(overrides)
    return LdapConfig(**base)


@pytest.fixture
def _clean_ldap_settings():
    """清理 system_settings 里的 ldap.* 键，避免用例间渗透。"""
    db = create_db_session()
    try:
        for row in db.scalars(select(SystemSettingModel).where(SystemSettingModel.key.like("ldap.%"))).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()
    yield
    db = create_db_session()
    try:
        for row in db.scalars(select(SystemSettingModel).where(SystemSettingModel.key.like("ldap.%"))).all():
            db.delete(row)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_missing_required_fields():
    config = LdapConfig(enabled=True, server_url="", bind_dn="", base_dn="", bind_password="")
    with pytest.raises(LdapConfigError) as exc:
        config.validate()
    message = str(exc.value)
    assert "服务器地址" in message
    assert "绑定账号" in message


def test_validate_rejects_filter_without_username_placeholder():
    config = _make_config(user_filter="(uid=*)")
    with pytest.raises(LdapConfigError) as exc:
        config.validate()
    assert "{username}" in str(exc.value)


def test_validate_passes_for_complete_config():
    _make_config().validate()  # 不抛即通过


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_clean_ldap_settings")
def test_config_round_trip_encrypts_password():
    db = create_db_session()
    try:
        payload = {"server_url": "ldaps://dc.corp.com:636", "bind_dn": "cn=svc,dc=corp,dc=com",
                   "bind_password": "plain-secret", "base_dn": "dc=corp,dc=com", "enabled": True,
                   "unknown_key": "should-be-ignored"}
        save_config(db, payload)

        # 库里存的是密文，不是明文
        row = db.scalar(select(SystemSettingModel).where(SystemSettingModel.key == "ldap.bind_password"))
        assert row is not None
        assert "plain-secret" not in row.value

        config = load_config(db)
        assert config.enabled is True
        assert config.server_url == "ldaps://dc.corp.com:636"
        assert config.bind_password == "plain-secret"  # 解密还原

        # 未知键没有落库
        assert db.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == "ldap.unknown_key")
        ) is None

        response = config_to_response(config)
        assert response["bind_password_set"] is True
        assert "bind_password" not in response  # 明文不回显
    finally:
        db.close()


@pytest.mark.usefixtures("_clean_ldap_settings")
def test_save_config_empty_password_keeps_old_value():
    db = create_db_session()
    try:
        save_config(db, {"bind_password": "first"})
        save_config(db, {"bind_password": ""})  # 空串 = 不修改
        assert load_config(db).bind_password == "first"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# authenticate（mock 连接）
# ---------------------------------------------------------------------------


def _patch_ldap(monkeypatch, entries, *, bind_ok=True, search_ok=True):
    """同时替换 _connect（服务账号连接）与 ldap3.Connection（用户二次 bind）。"""
    service_conn = FakeServiceConn(entries, search_ok=search_ok)
    monkeypatch.setattr(svc, "_connect", lambda config, bind=True: service_conn)
    FakeUserConn.bind_ok = bind_ok
    monkeypatch.setattr("ldap3.Connection", FakeUserConn)
    return service_conn


_ENTRY = FakeEntry(
    "cn=10001,ou=people,dc=corp,dc=com",
    {"sAMAccountName": "10001", "mail": "10001@corp.com", "displayName": "张三"},
)


def test_authenticate_success_normalizes_fields(monkeypatch):
    _patch_ldap(monkeypatch, [_ENTRY])
    result = authenticate(_make_config(), "10001", "pw")

    assert result["username"] == "10001"
    assert result["email"] == "10001@corp.com"
    assert result["name"] == "张三"
    # 用户 DN 被用于二次 bind
    assert FakeUserConn.last_user_dn == "cn=10001,ou=people,dc=corp,dc=com"


def test_authenticate_fills_email_from_domain(monkeypatch):
    entry = FakeEntry("cn=10002,ou=people,dc=corp,dc=com", {"sAMAccountName": "10002"})
    _patch_ldap(monkeypatch, [entry])
    result = authenticate(_make_config(), "10002", "pw")
    assert result["email"] == "10002@corp.com"


def test_authenticate_wrong_password_rejected(monkeypatch):
    _patch_ldap(monkeypatch, [_ENTRY], bind_ok=False)
    with pytest.raises(LdapAuthError, match="用户名或密码错误"):
        authenticate(_make_config(), "10001", "wrong")


def test_authenticate_user_bind_failure(monkeypatch):
    _patch_ldap(monkeypatch, [_ENTRY])
    FakeUserConn.opened = False
    try:
        with pytest.raises(LdapAuthError, match="连接失败"):
            authenticate(_make_config(), "10001", "pw")
    finally:
        FakeUserConn.opened = True


def test_authenticate_rejects_ambiguous_filter(monkeypatch):
    _patch_ldap(monkeypatch, [_ENTRY, _ENTRY])
    with pytest.raises(LdapAuthError, match="多条记录"):
        authenticate(_make_config(), "10001", "pw")


def test_authenticate_rejects_unknown_user(monkeypatch):
    _patch_ldap(monkeypatch, [])
    with pytest.raises(LdapAuthError, match="不存在"):
        authenticate(_make_config(), "ghost", "pw")


def test_authenticate_rejects_empty_credentials(monkeypatch):
    with pytest.raises(LdapAuthError, match="为空"):
        authenticate(_make_config(), "10001", "")


def test_authenticate_search_failure(monkeypatch):
    _patch_ldap(monkeypatch, [], search_ok=False)
    with pytest.raises(LdapAuthError, match="搜索失败"):
        authenticate(_make_config(), "10001", "pw")
