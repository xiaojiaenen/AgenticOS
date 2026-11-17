"""LDAP 按关键词查人（邮箱助手解析收件人用）。

`lookup_people` 与 `authenticate` 是两条独立路径：前者**只读**、不带密码，
用服务账号搜目录。这里用假 ldap3 连接验证：
- 精确 → 前缀 → 子串 三级收窄，前级命中就不再往下一级跑（省目录查询）
- 空关键词直接返回空（不发请求）
- 结果把属性名映射成 name/email/username
- 连接失败转成 LdapAuthError（上层据此给可读提示）
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from app.services.ldap_auth_service import LdapAuthError, LdapConfig, lookup_people


def make_config(**overrides) -> LdapConfig:
    base = dict(
        enabled=True,
        server_url="ldap://127.0.0.1:389",
        base_dn="dc=corp,dc=com",
        bind_dn="cn=svc,dc=corp,dc=com",
        bind_password="pw",
        user_filter="(sAMAccountName={username})",
        attr_username="sAMAccountName",
        attr_email="mail",
        attr_name="displayName",
    )
    base.update(overrides)
    return LdapConfig(**base)


class FakeEntry:
    def __init__(self, mapping: dict[str, object]):
        self._m = mapping

    def __getitem__(self, name: str):
        class _Attr:
            def __init__(self, value):
                self.value = value

        return _Attr(self._m.get(name))


def make_conn(rounds: list[list[FakeEntry]]):
    """按调用顺序返回每一轮搜索结果。"""
    conn = MagicMock()
    conn.entries = []
    state = {"i": 0}

    def search(**kwargs):
        idx = state["i"]
        state["i"] += 1
        conn.entries = rounds[idx] if idx < len(rounds) else []
        return True

    conn.search.side_effect = search
    return conn


@pytest.fixture(autouse=True)
def fake_ldap3():
    """lookup_people 内部 from ldap3 import SUBTREE，提供一个最小替身。"""
    module = types.ModuleType("ldap3")
    module.SUBTREE = "SUBTREE"
    util = types.ModuleType("ldap3.utils")
    conv = types.ModuleType("ldap3.utils.conv")
    conv.escape_filter_chars = lambda s: s.replace("(", r"\(").replace(")", r"\)")
    sys.modules.setdefault("ldap3", module)
    sys.modules.setdefault("ldap3.utils", util)
    sys.modules.setdefault("ldap3.utils.conv", conv)
    yield


class TestLookupPeople:
    def test_empty_keyword_returns_nothing_without_query(self):
        conn = make_conn([])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            assert lookup_people(make_config(), "   ") == []
        conn.search.assert_not_called()

    def test_exact_match_short_circuits(self):
        """精确命中后不再做前缀/子串搜索（省目录查询）。"""
        entry = FakeEntry({"displayName": "张伟", "mail": "zhangwei@corp.com", "sAMAccountName": "zhangwei"})
        conn = make_conn([[entry]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            people = lookup_people(make_config(), "zhangwei@corp.com")

        assert people == [
            {"name": "张伟", "email": "zhangwei@corp.com", "username": "zhangwei"}
        ]
        assert conn.search.call_count == 1, "精确命中后不该继续搜前缀/子串"

    def test_falls_through_to_substring(self):
        """精确和前缀都空 → 才做子串搜索。"""
        entry = FakeEntry({"displayName": "李张三", "mail": "lzs@corp.com", "sAMAccountName": "lzs"})
        conn = make_conn([[], [], [entry]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            people = lookup_people(make_config(), "张三")
        assert len(people) == 1
        assert conn.search.call_count == 3

    def test_multiple_results_mapped(self):
        entries = [
            FakeEntry({"displayName": "张伟", "mail": "zw1@corp.com", "sAMAccountName": "zw1"}),
            FakeEntry({"displayName": "张伟", "mail": "zw2@corp.com", "sAMAccountName": "zw2"}),
        ]
        conn = make_conn([entries])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            people = lookup_people(make_config(), "张伟")
        assert [p["email"] for p in people] == ["zw1@corp.com", "zw2@corp.com"]

    def test_missing_attributes_are_empty_strings(self):
        """目录里缺 mail（只有账号）时不能抛异常。"""
        entry = FakeEntry({"sAMAccountName": "svc"})
        conn = make_conn([[entry]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            people = lookup_people(make_config(), "svc")
        assert people == [{"name": "", "email": "", "username": "svc"}]

    def test_list_valued_attribute_takes_first(self):
        entry = FakeEntry({"displayName": ["张伟", "Zhang Wei"], "mail": "zw@corp.com", "sAMAccountName": "zw"})
        conn = make_conn([[entry]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            people = lookup_people(make_config(), "张伟")
        assert people[0]["name"] == "张伟"

    def test_connection_failure_raises_readable_error(self):
        with patch("app.services.ldap_auth_service._connect", side_effect=RuntimeError("refused")):
            with pytest.raises(LdapAuthError):
                lookup_people(make_config(), "张伟")

    def test_respects_limit(self):
        conn = make_conn([[]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            lookup_people(make_config(), "张", limit=3)
        # size_limit 被夹在 1..50
        assert conn.search.call_args.kwargs["size_limit"] == 3

    def test_huge_limit_clamped(self):
        conn = make_conn([[]])
        with patch("app.services.ldap_auth_service._connect", return_value=conn):
            lookup_people(make_config(), "张", limit=9999)
        assert conn.search.call_args.kwargs["size_limit"] == 50


class TestLookupToolRegistered:
    def test_tool_present_in_email_registrar(self):
        """工具要真的注册进 registry，否则模型看不到。"""
        import inspect

        from app.tools import email_tools

        assert "lookup_contact" in inspect.getsource(email_tools.register_email_tools)
