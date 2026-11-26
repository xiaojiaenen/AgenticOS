"""出网 SSRF 防护回归：统一 check_url + 不跟随重定向 + 图片工具审批。

所有用例不发真实网络请求：check_url / httpx.AsyncClient 均被 monkeypatch。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.services.intranet_policy import check_url


def test_check_url_blocks_cloud_metadata():
    """云元数据地址任何情况下都拒绝（不依赖 CIDR 配置）。"""
    decision = check_url("http://169.254.169.254/latest/meta-data/")
    assert decision.allowed is False
    assert "元数据" in decision.reason

    decision2 = check_url("https://metadata.google.internal/computeMetadata/v1/")
    assert decision2.allowed is False


def test_check_url_blocks_non_http_scheme():
    assert check_url("file:///etc/passwd").allowed is False


def test_get_image_info_calls_check_url_and_blocks_metadata(monkeypatch):
    """get_image_info 出网前经 check_url；元数据地址被拒且不发起 HTTP。"""
    from app.services.agent.native.tool_registry import ToolRegistry
    from app.tools.image_tools import register_image_tools

    calls: list[str] = []

    def _fake_check_url(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            allowed=False, reason="禁止访问元数据地址：169.254.169.254", resolved_ip="",
        )

    monkeypatch.setattr("app.services.intranet_policy.check_url", _fake_check_url)

    http_calls: list[str] = []

    class _FakeClient:
        def __init__(self, **kw):
            http_calls.append(f" init:{kw}")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def head(self, url, **kw):
            http_calls.append(f" head:{url} kw={kw}")
            raise AssertionError("不应发起 HTTP 请求")

        async def get(self, url, **kw):
            http_calls.append(f" get:{url} kw={kw}")
            raise AssertionError("不应发起 HTTP 请求")

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    registry = ToolRegistry()
    register_image_tools(registry)
    tool = registry.get("get_image_info")
    assert tool is not None
    assert tool.execution.requires_approval is True

    result = asyncio.run(tool.invoke({"url": "http://169.254.169.254/"}))
    assert "不在允许访问范围" in result or "失败" in result
    assert any("169.254.169.254" in c for c in calls), calls
    assert not any(c.startswith(" head") or c.startswith(" get") for c in http_calls)


def test_get_image_info_no_follow_redirects(monkeypatch):
    """合法 URL 通过校验后，HEAD/GET 均不带 follow_redirects=True。"""
    from app.services.agent.native.tool_registry import ToolRegistry
    from app.tools.image_tools import register_image_tools

    monkeypatch.setattr(
        "app.services.intranet_policy.check_url",
        lambda url, **kw: SimpleNamespace(allowed=True, reason="", resolved_ip="1.2.3.4"),
    )

    seen: list[dict] = []

    class _Resp:
        status_code = 200
        headers = {"content-type": "image/png", "content-length": "2048"}

    class _FakeClient:
        def __init__(self, **kw):
            seen.append(kw)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def head(self, url, **kw):
            seen.append(kw)
            return _Resp()

        async def get(self, url, **kw):
            seen.append(kw)
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    registry = ToolRegistry()
    register_image_tools(registry)
    tool = registry.get("get_image_info")
    result = asyncio.run(tool.invoke({"url": "https://images.example.com/a.png"}))
    assert "图片信息" in result, result
    assert all(kw.get("follow_redirects") is not True for kw in seen if isinstance(kw, dict))


def test_external_tool_builder_calls_check_url(monkeypatch):
    """外部系统集成工具调用逐跳过 check_url，元数据地址被拒。"""
    from app.services.external_systems import tool_builder as tb

    calls: list[str] = []

    def _fake_check_url(url, **kwargs):
        calls.append(url)
        # 只拒绝元数据地址，其余放行
        if "169.254.169.254" in url:
            return SimpleNamespace(allowed=False, reason="禁止访问元数据地址", resolved_ip="")
        return SimpleNamespace(allowed=True, reason="", resolved_ip="1.2.3.4")

    monkeypatch.setattr("app.services.intranet_policy.check_url", _fake_check_url)

    api = SimpleNamespace(
        id=7, name="probe", path="/x", method="GET", timeout_seconds=5,
        requires_approval=False, body_wrapper_key="",
        params_json="[]",
    )
    system = SimpleNamespace(
        id=99, name="S", base_url="http://169.254.169.254",
        auth_type="none", headers_json="{}", advanced_auth_json="",
        default_credential_data_encrypted="", oauth_token_url=None,
        oauth_client_id_encrypted=None, oauth_client_secret_encrypted=None,
        jwt_refresh_url=None, jwt_login_url=None, jwt_request_body_template=None,
        jwt_refresh_body_template=None, jwt_response_token_path=None,
        jwt_response_expires_path=None, jwt_response_token_header=None,
        jwt_refresh_token_path=None, login_token_source=None,
        login_inject_mode=None, login_inject_header_name=None,
    )
    param_rows = []

    class _FakeSession:
        def execute(self, _stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: param_rows))

        def get(self, _model, _id):
            return None

        def query(self, _model):
            return SimpleNamespace(filter_by=lambda **_kw: SimpleNamespace(first=lambda: None))

        def close(self):
            pass

    async def _fake_cache_get(_system_id):
        return None

    monkeypatch.setattr("app.db.session.create_db_session", lambda: _FakeSession())
    monkeypatch.setattr(tb, "_cache_get", _fake_cache_get)

    handler = tb._build_system_tool_handler(system, {"probe": (api, param_rows)}, user_id=1)
    result = asyncio.run(handler("probe", {}))
    assert "169.254.169.254" in str(calls), calls
    assert "不可用" in result or "error" in result, result


def test_get_image_info_approval_in_catalog():
    """图片信息工具在 TOOL_CATALOG / PPT 默认配置里 requires_approval=True。"""
    from app.services.tool_config_service import DEFAULT_MODE_TOOLS, TOOL_CATALOG

    entry = TOOL_CATALOG["get_image_info"]
    assert "get_image_info" in entry["approval_scope"]
    assert entry["sub_tools"]

    ppt = DEFAULT_MODE_TOOLS["ppt"]
    assert ppt["get_image_info"]["requires_approval"] is True


def test_parse_openapi_calls_check_url(monkeypatch):
    """OpenAPI URL 导入经 check_url；元数据地址被拒且不发起 HTTP。"""
    from app.services.external_systems.service import ExternalSystemService

    calls: list[str] = []

    def _fake_check_url(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(allowed=False, reason="禁止访问元数据地址", resolved_ip="")

    monkeypatch.setattr("app.services.intranet_policy.check_url", _fake_check_url)

    class _BoomClient:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, url):
            raise AssertionError("不应发起 HTTP 请求")

    monkeypatch.setattr(httpx, "AsyncClient", _BoomClient)

    with pytest.raises(PermissionError) as exc:
        asyncio.run(ExternalSystemService.parse_openapi(
            openapi_url="http://169.254.169.254/openapi.json"
        ))
    assert "元数据" in str(exc.value)
    assert any("169.254.169.254" in c for c in calls)


def test_oauth_token_refresh_calls_check_url(monkeypatch):
    """OAuth 令牌刷新 URL 经 check_url；无 refresh token 时先短路（测不到网络）。"""
    from app.services.external_systems.auth_injector import AuthInjector

    calls: list[str] = []
    monkeypatch.setattr(
        "app.services.intranet_policy.check_url",
        lambda url, **kw: (calls.append(url) or SimpleNamespace(allowed=False, reason="blocked")),
    )

    system = SimpleNamespace(
        name="S", oauth_token_url="http://169.254.169.254/token",
        oauth_client_id_encrypted="", oauth_client_secret_encrypted="",
    )
    cred = SimpleNamespace(
        oauth_expires_at=None, oauth_access_token_encrypted=None,
        oauth_refresh_token_encrypted=None, connection_status="connected",
        id=1,
    )
    with pytest.raises(ValueError, match="过期"):
        asyncio.run(AuthInjector._ensure_valid_token(system, cred))
    # 无 refresh token 时提前返回，check_url 不该被调用（说明短路顺序正确）
    assert calls == []
