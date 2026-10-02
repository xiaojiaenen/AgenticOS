"""MCP 服务器管理测试（配置 CRUD + 校验，不建立真实连接）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.mcp_service import delete_server, list_servers, upsert_server


@pytest.fixture
def admin_headers():
    with create_db_session() as db:
        user = db.query(UserModel).filter(
            UserModel.email == "mcp-admin@example.com"
        ).first()
        if user is None:
            user = UserModel(
                email="mcp-admin@example.com",
                name="MCP 管理员",
                password_hash=hash_password("mcp-test-123"),
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


class TestServerCrud:
    def test_create_and_list(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/mcp/servers",
            json={
                "name": "test-fileserver",
                "transport": "http",
                "url": "http://127.0.0.1:9999/mcp",
                "description": "测试服务器",
                "headers": {"Authorization": "Bearer x"},
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "test-fileserver"
        assert resp.json()["headers"] == {"Authorization": "Bearer x"}

        items = client.get(
            "/api/v1/admin/mcp/servers", headers=admin_headers
        ).json()["items"]
        assert any(i["name"] == "test-fileserver" for i in items)

        assert client.delete(
            "/api/v1/admin/mcp/servers/test-fileserver", headers=admin_headers
        ).status_code == 204

    def test_upsert_same_name_updates(self, client, admin_headers):
        payload = {
            "name": "test-updates",
            "transport": "sse",
            "url": "http://a/sse",
            "description": "第一版",
        }
        client.post("/api/v1/admin/mcp/servers", json=payload, headers=admin_headers)
        payload["description"] = "第二版"
        resp = client.post(
            "/api/v1/admin/mcp/servers", json=payload, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "第二版"
        names = [i["name"] for i in client.get(
            "/api/v1/admin/mcp/servers", headers=admin_headers
        ).json()["items"]]
        assert names.count("test-updates") == 1
        client.delete("/api/v1/admin/mcp/servers/test-updates", headers=admin_headers)

    def test_delete_missing_returns_404(self, client, admin_headers):
        resp = client.delete(
            "/api/v1/admin/mcp/servers/not-exist", headers=admin_headers
        )
        assert resp.status_code == 404


class TestValidation:
    def test_http_requires_url(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/mcp/servers",
            json={"name": "bad-http", "transport": "http"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "服务地址" in resp.json()["detail"]

    def test_stdio_requires_command(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/mcp/servers",
            json={"name": "bad-stdio", "transport": "stdio"},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "启动命令" in resp.json()["detail"]

    def test_invalid_transport_rejected(self, client, admin_headers):
        resp = client.post(
            "/api/v1/admin/mcp/servers",
            json={"name": "bad-transport", "transport": "carrier-pigeon"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    def test_requires_admin(self, client):
        resp = client.get("/api/v1/admin/mcp/servers")
        assert resp.status_code in (401, 403)


class TestServiceLayer:
    def test_upsert_requires_name(self):
        with pytest.raises(ValueError):
            upsert_server({"name": "  "})

    def test_list_after_delete_is_empty(self):
        upsert_server({
            "name": "unit-test-server",
            "transport": "http",
            "url": "http://example/mcp",
        })
        assert any(s["name"] == "unit-test-server" for s in list_servers())
        delete_server("unit-test-server")
        assert not any(s["name"] == "unit-test-server" for s in list_servers())

    def test_tool_catalogue_naming(self):
        from types import SimpleNamespace

        from app.services.mcp_service import McpService

        service = McpService()
        service._tools = [
            SimpleNamespace(name="read_file", description="读取文件"),
            SimpleNamespace(name="write_file", description=""),
        ]
        entries = service.tool_catalogue()
        assert [e["name"] for e in entries] == [
            "mcp__read_file",
            "mcp__write_file",
        ]
        assert entries[0]["description"] == "读取文件"
        assert entries[1]["description"]  # 无描述时给兜底文案
        assert entries[0]["source"] == "mcp"

    def test_disabled_servers_excluded_from_config(self):
        upsert_server({
            "name": "disabled-server",
            "transport": "http",
            "url": "http://example/mcp",
            "enabled": False,
        })
        with create_db_session() as db:
            from app.services.mcp_service import McpService

            config = McpService._to_wuwei_config(db)
            assert "disabled-server" not in config.mcp_servers
        delete_server("disabled-server")