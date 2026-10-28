"""内网爬虫能力测试（策略 / 占位符 / 工具薄壳）。

重点是**安全策略** —— 内网爬虫的本质是「让服务器访问任意地址」，
策略一旦漏了就是 SSRF。
"""

from __future__ import annotations

import pytest

from app.services.intranet_policy import check_url
from app.services import intranet_client as client


# ---------------------------------------------------------------------------
# SSRF 防护
# ---------------------------------------------------------------------------


class TestIntranetPolicy:
    PRIVATE = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    def test_default_deny_when_no_cidr_configured(self):
        """没配网段 → 拒绝一切（默认拒绝，不是默认允许）。"""
        d = check_url("http://10.1.2.3/")
        assert d.allowed is False
        assert "INTRANET_ALLOWED_CIDRS" in d.reason

    def test_private_ip_allowed_when_in_cidr(self):
        d = check_url("http://10.1.2.3/x", allowed_cidrs=self.PRIVATE)
        assert d.allowed is True

    def test_public_ip_denied(self):
        """公网地址在私网网段配置下必须被拒。"""
        d = check_url("http://93.184.216.34/", allowed_cidrs=self.PRIVATE)
        assert d.allowed is False

    def test_metadata_address_always_denied(self):
        """云元数据地址无条件拒绝 —— 即使网段写得很宽。"""
        d = check_url(
            "http://169.254.169.254/latest/meta-data/",
            allowed_cidrs="0.0.0.0/0",
        )
        assert d.allowed is False

    def test_metadata_hostname_denied(self):
        d = check_url(
            "http://metadata.google.internal/",
            allowed_cidrs="0.0.0.0/0",
        )
        assert d.allowed is False

    def test_non_http_scheme_denied(self):
        for url in ("file:///etc/passwd", "gopher://x/", "ftp://x/"):
            d = check_url(url, allowed_cidrs=self.PRIVATE)
            assert d.allowed is False, url

    def test_missing_host_denied(self):
        d = check_url("http:///path", allowed_cidrs=self.PRIVATE)
        assert d.allowed is False

    def test_egress_allowlist_host_passes(self):
        d = check_url(
            "http://example.com/",
            allowed_cidrs=self.PRIVATE,
            egress_allowlist="example.com",
        )
        assert d.allowed is True

    def test_unresolvable_host_denied(self):
        d = check_url(
            "http://this-host-does-not-exist-xyzzy.invalid/",
            allowed_cidrs=self.PRIVATE,
        )
        assert d.allowed is False


# ---------------------------------------------------------------------------
# 占位符解析
# ---------------------------------------------------------------------------


class TestPlaceholders:
    def test_credential_placeholder_resolved(self):
        resolved, missing = client.resolve_placeholders(
            {"username": "$CREDENTIAL.username"},
            credentials={"username": "alice"},
        )
        assert resolved["username"] == "alice"
        assert missing == []

    def test_input_placeholder_resolved(self):
        resolved, missing = client.resolve_placeholders(
            {"code": "$INPUT.captcha"},
            inputs={"captcha": "123456"},
        )
        assert resolved["code"] == "123456"
        assert missing == []

    def test_missing_credential_reported(self):
        resolved, missing = client.resolve_placeholders(
            {"password": "$CREDENTIAL.password"}, credentials={}
        )
        assert missing == ["CREDENTIAL.password"]
        assert resolved["password"] == "$CREDENTIAL.password"

    def test_missing_input_reported(self):
        resolved, missing = client.resolve_placeholders(
            {"code": "$INPUT.captcha"}, inputs={}
        )
        assert missing == ["INPUT.captcha"]

    def test_plain_values_untouched(self):
        resolved, missing = client.resolve_placeholders(
            {"ticket": "T-123", "url": "http://x/"}
        )
        assert resolved == {"ticket": "T-123", "url": "http://x/"}
        assert missing == []

    def test_non_string_values_untouched(self):
        resolved, _ = client.resolve_placeholders({"count": 5, "flag": True})
        assert resolved["count"] == 5
        assert resolved["flag"] is True

    def test_multiple_placeholders_in_one_value(self):
        resolved, missing = client.resolve_placeholders(
            {"q": "$CREDENTIAL.a-$CREDENTIAL.b"},
            credentials={"a": "1", "b": "2"},
        )
        assert resolved["q"] == "1-2"
        assert missing == []


# ---------------------------------------------------------------------------
# 工具薄壳
# ---------------------------------------------------------------------------


class TestIntranetTools:
    def _tools(self):
        from app.tools.intranet_tools import register_intranet_tools
        from wuwei.tools.registry import ToolRegistry

        reg = ToolRegistry()
        register_intranet_tools(reg)
        return {t.name: t for t in reg.list_tools()}

    def test_tools_registered(self):
        names = set(self._tools())
        assert {
            "intranet_probe",
            "intranet_fetch",
            "intranet_browse",
            "intranet_extract",
            "intranet_submit",
        } <= names

    @pytest.mark.anyio
    async def test_disabled_service_returns_message(self, monkeypatch):
        """没启用内网服务时，工具返回明确提示而不是抛异常。

        这是「不影响外网部署」的关键：外网环境下调用这些工具不会 500。
        """
        monkeypatch.setattr(client, "is_enabled", lambda: False)
        tools = self._tools()
        result = await tools["intranet_fetch"].handler(url="http://10.0.0.1/")
        assert result["ok"] is False
        assert "未启用" in result["error"]

    @pytest.mark.anyio
    async def test_blocked_url_rejected_before_call(self, monkeypatch):
        """策略不通过时**不发起 HTTP 调用**（避免探测行为本身成为漏洞）。"""
        monkeypatch.setattr(client, "is_enabled", lambda: True)
        called = False

        async def _never(*a, **kw):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(client, "call_service", _never)
        tools = self._tools()
        result = await tools["intranet_fetch"].handler(url="http://169.254.169.254/")
        assert result["ok"] is False
        assert called is False

    @pytest.mark.anyio
    async def test_missing_credential_reported_before_call(self, monkeypatch):
        monkeypatch.setattr(client, "is_enabled", lambda: True)
        monkeypatch.setattr(
            client, "guard_url", lambda url: None
        )
        called = False

        async def _never(*a, **kw):
            nonlocal called
            called = True
            return {}

        monkeypatch.setattr(client, "call_service", _never)
        tools = self._tools()
        result = await tools["intranet_fetch"].handler(
            url="http://10.0.0.1/",
            headers={"Authorization": "$CREDENTIAL.token"},
        )
        assert result["ok"] is False
        assert "缺少参数" in result["error"]
        assert called is False

    @pytest.mark.anyio
    async def test_submit_tool_requires_approval(self):
        """写操作必须走审批。"""
        tools = self._tools()
        assert tools["intranet_submit"].execution.requires_approval is True
        assert tools["intranet_browse"].execution.requires_approval is True
        assert tools["intranet_submit"].execution.side_effect is True
