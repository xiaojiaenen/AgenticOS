"""MCP 作为爬虫插件形态的回归测试。

覆盖 2026-10-28 的 MCP 通道改造：

1. **依赖**：MCP SDK 是生产依赖（wuwei 把 MCP 放在 optional extra，
   不显式声明会导致管理面板能配但连不上）。
2. **profile 级授权**（dsh 的「按需挂载」）：MCP 工具不再全局注册到
   每个 Agent，必须在 profile 上显式授权。
3. **凭据注入**：``$CREDENTIAL.<字段>`` 从用户自己的集成凭据注入，
   值不进模型上下文、不进审计。
4. **用户临时输入**：``$INPUT.<字段>`` 缺失时走 UserInputBlocker
   阻塞等用户在前端表单里填。
5. **自签证书**：内网自签 CA 必须能连上（官方 SDK 的
   ``create_mcp_http_client`` 没有 verify 参数）。
6. **出网网段限制**：平台连 MCP 服务这一跳的地址可限制在网段内。
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    AgentProfileMCPServerModel,
    AgentProfileModel,
    ExternalSystemModel,
    ExternalUserCredentialModel,
    MCPServerModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app
from app.services.mcp_service import (
    apply_profile_servers,
    delete_server,
    get_mcp_service,
    list_profile_servers,
    list_servers,
    upsert_server,
)
from app.services.mcp_tool_bridge import (
    _resolve_placeholders,
    credential_scope,
    set_credential_scope,
    wrap_mcp_tool,
)


@pytest.fixture
def admin_headers():
    with create_db_session() as db:
        user = db.query(UserModel).filter(
            UserModel.email == "mcp-plugin-admin@example.com"
        ).first()
        if user is None:
            user = UserModel(
                email="mcp-plugin-admin@example.com",
                name="MCP 插件管理员",
                password_hash=hash_password("mcp-plugin-123"),
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        settings = get_settings()
        token = create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role},
            secret=settings.auth_secret_key,
            expires_in_seconds=3600,
        )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def profile_id():
    with create_db_session() as db:
        row = db.query(AgentProfileModel).filter(
            AgentProfileModel.slug == "mcp-plugin-profile"
        ).first()
        if row is None:
            row = AgentProfileModel(
                name="MCP 插件测试智能体",
                slug="mcp-plugin-profile",
                system_prompt="测试",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row.id


class _FakeTool:
    """模拟 wuwei 的 Tool（pydantic model 的最小替身）。"""

    def __init__(self, name: str, handler, description: str = "") -> None:
        self.name = name
        self.handler = handler
        self.description = description
        self.parameters = None

    def model_copy(self, *, update: dict):
        new = _FakeTool(self.name, self.handler, self.description)
        new.handler = update.get("handler", self.handler)
        return new


class TestMcpSdkDependency:
    def test_mcp_sdk_is_importable(self):
        """MCP SDK 必须是可导入的生产依赖。

        wuwei 把 MCP 放在 optional extra（``wuwei[mcp]``）。项目在管理后台
        直接暴露 MCP 接入能力，若不显式声明依赖，管理面板能配服务器但
        连接时 ModuleNotFoundError —— 通道形同虚设。
        """
        import mcp  # noqa: F401
        from mcp.client.streamable_http import streamable_http_client  # noqa: F401

        assert "mcp" in sys.modules

    def test_mcp_declared_in_pyproject(self):
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert '"mcp>=' in content, "mcp SDK 必须声明为生产依赖"


class TestProfileAuthorization:
    """profile 级授权 —— MCP 工具不再全局注册到每个 Agent。"""

    def test_tool_filter_respects_profile_grant(self, profile_id):
        service = get_mcp_service()

        class _Tool:
            def __init__(self, name):
                self.name = name

        service._tools = [
            _Tool("mcp__intranet_crawler__fetch"),
            _Tool("mcp__public_api__search"),
        ]
        try:
            # 该服务器 user_accessible=False（内网爬虫默认），且 profile 已授权
            with create_db_session() as db:
                server = db.query(MCPServerModel).filter(
                    MCPServerModel.name == "intranet_crawler"
                ).first()
                if server is None:
                    server = MCPServerModel(name="intranet_crawler")
                    db.add(server)
                server.enabled = True
                server.user_accessible = False
                db.commit()

                pub = db.query(MCPServerModel).filter(
                    MCPServerModel.name == "public_api"
                ).first()
                if pub is None:
                    pub = MCPServerModel(name="public_api")
                    db.add(pub)
                pub.enabled = True
                pub.user_accessible = True
                db.commit()

            apply_profile_servers(
                profile_id, [{"server_name": "intranet_crawler", "enabled": True}]
            )

            names = {t.name for t in service.get_tools_for_profile(profile_id)}
            # 已授权的内网爬虫可见
            assert "mcp__intranet_crawler__fetch" in names
            # user_accessible=True 的公开服务对所有 profile 可见
            assert "mcp__public_api__search" in names
        finally:
            service._tools = []

    def test_ungranted_server_is_hidden(self, profile_id):
        """未授权的内网爬虫工具对该 profile 不可见。"""
        service = get_mcp_service()

        class _Tool:
            def __init__(self, name):
                self.name = name

        service._tools = [_Tool("mcp__secret_crawler__fetch")]
        try:
            with create_db_session() as db:
                server = db.query(MCPServerModel).filter(
                    MCPServerModel.name == "secret_crawler"
                ).first()
                if server is None:
                    server = MCPServerModel(name="secret_crawler")
                    db.add(server)
                server.enabled = True
                server.user_accessible = False
                db.commit()

            # 清掉该 profile 上可能残留的授权
            apply_profile_servers(profile_id, [])

            names = {t.name for t in service.get_tools_for_profile(profile_id)}
            assert "mcp__secret_crawler__fetch" not in names
        finally:
            service._tools = []

    def test_apply_profile_servers_replaces(self, profile_id):
        """覆盖式设置 —— 提交什么就是什么，不留陈旧授权。"""
        apply_profile_servers(
            profile_id,
            [
                {"server_name": "a", "enabled": True},
                {"server_name": "b", "enabled": True},
            ],
        )
        assert {r["server_name"] for r in list_profile_servers(profile_id)} == {"a", "b"}

        apply_profile_servers(profile_id, [{"server_name": "a", "enabled": True}])
        assert {r["server_name"] for r in list_profile_servers(profile_id)} == {"a"}

    def test_profile_auth_api(self, client, admin_headers, profile_id):
        resp = client.put(
            f"/api/v1/admin/mcp/profiles/{profile_id}/servers",
            json={"servers": [{"server_name": "api_crawler", "enabled": True}]},
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["server_name"] == "api_crawler"

        got = client.get(
            f"/api/v1/admin/mcp/profiles/{profile_id}/servers",
            headers=admin_headers,
        )
        assert got.status_code == 200
        assert got.json()["items"][0]["server_name"] == "api_crawler"


class TestCredentialInjection:
    """``$CREDENTIAL.<字段>`` 注入 —— 值不进模型上下文。"""

    def test_placeholder_regex_excludes_hyphen(self):
        """字段名不含连字符。

        否则 ``"$CREDENTIAL.a-$CREDENTIAL.b"`` 会把第一个解析成字段 ``a-``。
        """
        resolved, missing = _resolve_placeholders(
            {"v": "$CREDENTIAL.a-$CREDENTIAL.b"},
            server_name="s",
            user_id=0,
        )
        # 没配凭据 → 两个都算缺失，且字段名是 a / b 而不是 a-
        assert sorted(missing) == ["CREDENTIAL.a", "CREDENTIAL.b"]

    def test_missing_credential_is_reported(self):
        resolved, missing = _resolve_placeholders(
            {"token": "$CREDENTIAL.session_token"},
            server_name="s",
            user_id=0,
        )
        assert missing == ["CREDENTIAL.session_token"]
        # 未替换时保留原样，不吞掉
        assert resolved["token"] == "$CREDENTIAL.session_token"

    def test_credential_resolved_from_user_credential(self):
        """从用户自己的集成凭据里取。"""
        from app.core.encryption import encrypt

        with create_db_session() as db:
            user = db.query(UserModel).filter(
                UserModel.email == "mcp-cred-user@example.com"
            ).first()
            if user is None:
                user = UserModel(
                    email="mcp-cred-user@example.com",
                    name="凭据用户",
                    password_hash=hash_password("cred-123"),
                    role="user",
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            system = db.query(ExternalSystemModel).filter(
                ExternalSystemModel.name == "mcp_crawler_ext"
            ).first()
            if system is None:
                system = ExternalSystemModel(
                    name="mcp_crawler_ext",
                    base_url="http://intranet",
                    auth_type="custom",
                )
                db.add(system)
                db.commit()
                db.refresh(system)

            existing = db.query(ExternalUserCredentialModel).filter_by(
                user_id=user.id, system_id=system.id
            ).first()
            payload = json.dumps({"username": "alice", "password": "s3cret"})
            if existing:
                existing.credential_data_encrypted = encrypt(payload)
                existing.connection_status = "connected"
            else:
                db.add(
                    ExternalUserCredentialModel(
                        user_id=user.id,
                        system_id=system.id,
                        credential_data_encrypted=encrypt(payload),
                        connection_status="connected",
                    )
                )
            db.commit()
            user_id = user.id
            system_id = system.id

        set_credential_scope("cred_srv", system_id)
        try:
            assert credential_scope("cred_srv") == system_id
            resolved, missing = _resolve_placeholders(
                {"user": "$CREDENTIAL.username", "pwd": "$CREDENTIAL.password"},
                server_name="cred_srv",
                user_id=user_id,
            )
            assert missing == []
            assert resolved["user"] == "alice"
            assert resolved["pwd"] == "s3cret"
        finally:
            set_credential_scope("cred_srv", None)

    def test_tool_wrapper_reports_missing_credential(self):
        """凭据缺失时给出「去集成页配置」的可执行提示，而不是抛异常。"""
        captured = {}

        async def handler(**kwargs):
            captured.update(kwargs)
            return "ok"

        tool = _FakeTool("mcp__nosrv__fetch", handler)
        wrapped = wrap_mcp_tool(tool)
        result = asyncio.run(wrapped.handler(url="$CREDENTIAL.session_token"))

        payload = json.loads(result)
        assert "error" in payload
        assert payload["missing_credentials"] == ["session_token"]
        # 凭据缺失时不该真的调下游
        assert captured == {}


class TestUserInputBridge:
    """``$INPUT.<字段>`` → UserInputBlocker 阻塞等用户填。"""

    def test_missing_input_is_reported_without_session(self):
        """没有会话上下文时给出明确提示，不能静默挂死。"""
        captured = {}

        async def handler(**kwargs):
            captured.update(kwargs)
            return "ok"

        tool = _FakeTool("mcp__srv__submit", handler)
        wrapped = wrap_mcp_tool(tool)
        result = asyncio.run(wrapped.handler(code="$INPUT.sms_code"))

        payload = json.loads(result)
        assert "error" in payload
        assert payload["missing_inputs"] == ["sms_code"]
        assert captured == {}

    def test_user_input_blocks_and_resumes(self):
        """会话内缺失 → 阻塞等用户 → 带着真实值继续调用。"""
        from app.services.external_systems.coordinators import UserInputBlocker
        from app.services.external_systems.context import _current_session_id

        captured = {}

        async def handler(**kwargs):
            captured.update(kwargs)
            return "ok"

        tool = _FakeTool("mcp__srv__submit", handler)
        wrapped = wrap_mcp_tool(tool)

        session_id = "mcp-user-input-session"

        async def _scenario():
            _current_session_id.set(session_id)
            queue = UserInputBlocker.subscribe(session_id)
            task = asyncio.create_task(
                wrapped.handler(code="$INPUT.sms_code", url="http://x")
            )
            # 等阻塞发生
            payload = await asyncio.wait_for(queue.get(), timeout=5)
            assert payload["type"] == "user_input_required"
            assert payload["fields"][0]["key"] == "sms_code"
            UserInputBlocker.resolve(session_id, {"sms_code": "123456"})
            return await asyncio.wait_for(task, timeout=5)

        result = asyncio.run(_scenario())
        assert result == "ok"
        # 真实值带进了下游调用
        assert captured["code"] == "123456"
        # 占位符不再残留
        assert "$INPUT." not in str(captured.values())


class TestIntranetTls:
    """内网自签证书 + 出网网段限制。"""

    def test_verify_tls_field_roundtrip(self):
        payload = {
            "name": "tls-srv",
            "transport": "http",
            "url": "https://intranet.local/mcp",
            "verify_tls": False,
            "allowed_cidrs": "10.0.0.0/8",
            "user_accessible": False,
        }
        result = upsert_server(payload)
        try:
            assert result["verify_tls"] is False
            assert result["allowed_cidrs"] == "10.0.0.0/8"
            assert result["user_accessible"] is False
        finally:
            delete_server("tls-srv")

    def test_verify_tls_not_reset_when_absent(self):
        """前端没带这个字段时不能把「已放行自签证书」重置回校验。"""
        upsert_server(
            {
                "name": "tls-keep",
                "transport": "http",
                "url": "https://intranet.local/mcp",
                "verify_tls": False,
            }
        )
        try:
            result = upsert_server(
                {
                    "name": "tls-keep",
                    "transport": "http",
                    "url": "https://intranet.local/mcp",
                    "description": "改个描述",
                }
            )
            assert result["verify_tls"] is False
        finally:
            delete_server("tls-keep")

    def test_server_url_cidr_guard(self):
        """平台连 MCP 服务这一跳的地址受网段限制。"""
        from app.services.mcp_service import McpService

        with create_db_session() as db:
            row = db.query(MCPServerModel).filter(
                MCPServerModel.name == "cidr-srv"
            ).first()
            if row is None:
                row = MCPServerModel(name="cidr-srv")
                db.add(row)
            row.allowed_cidrs = "10.0.0.0/8"
            row.verify_tls = True
            db.commit()
            db.refresh(row)

        # 10.x 在允许网段内
        McpService._check_server_url("http://10.1.2.3/mcp", row)
        # 公网地址不在网段内 → 拒绝
        with pytest.raises(PermissionError):
            McpService._check_server_url("http://93.184.216.34/mcp", row)

    def test_empty_cidr_means_no_restriction(self):
        """未配置网段时不限制 —— 保持既有公网 MCP 用法不变。"""
        from app.services.mcp_service import McpService

        with create_db_session() as db:
            row = db.query(MCPServerModel).filter(
                MCPServerModel.name == "cidr-free"
            ).first()
            if row is None:
                row = MCPServerModel(name="cidr-free")
                db.add(row)
            row.allowed_cidrs = ""
            db.commit()
            db.refresh(row)

        McpService._check_server_url("http://93.184.216.34/mcp", row)


class TestToolCatalogue:
    def test_server_list_includes_new_fields(self):
        upsert_server(
            {
                "name": "cat-srv",
                "transport": "http",
                "url": "http://127.0.0.1:9/mcp",
                "verify_tls": False,
                "user_accessible": False,
                "external_system_id": None,
            }
        )
        try:
            items = list_servers()
            item = next(i for i in items if i["name"] == "cat-srv")
            assert "verify_tls" in item
            assert "allowed_cidrs" in item
            assert "user_accessible" in item
            assert "external_system_id" in item
        finally:
            delete_server("cat-srv")


class TestConnectionLifecycle:
    """连接生命周期：重连不能泄漏旧连接。

    ``McpService.disconnect()`` 此前只关 ``_session_manager``，而我们走的是
    自己的 ``_connect_servers``（从不给 ``_session_manager`` 赋值）——
    于是「连接并发现工具」每点一次就泄漏一批旧连接：socket 还占着，
    anyio task group 也没退出。
    """

    def test_disconnect_closes_all_clients(self):
        from app.services.mcp_service import McpService

        service = McpService()
        closed = []

        class _FakeClient:
            def __init__(self, name):
                self.name = name

            async def disconnect(self):
                closed.append(self.name)

        service._clients = {"a": _FakeClient("a"), "b": _FakeClient("b")}
        service._tools = ["x"]

        asyncio.run(service.disconnect())

        assert sorted(closed) == ["a", "b"]
        assert service._clients == {}
        assert service._tools == []

    def test_disconnect_survives_client_failure(self):
        """单个连接断开失败不影响其他连接。"""
        from app.services.mcp_service import McpService

        service = McpService()
        closed = []

        class _BadClient:
            async def disconnect(self):
                raise RuntimeError("boom")

        class _GoodClient:
            async def disconnect(self):
                closed.append("good")

        service._clients = {"bad": _BadClient(), "good": _GoodClient()}

        asyncio.run(service.disconnect())

        assert closed == ["good"]
        assert service._clients == {}
