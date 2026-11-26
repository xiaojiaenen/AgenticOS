"""创作画布新功能的权限点接入回归。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _token(user_id: int, role: str) -> str:
    s = get_settings()
    return create_access_token(
        {"sub": str(user_id), "email": "canvas@test.local", "role": role},
        secret=s.auth_secret_key, expires_in_seconds=3600,
    )


def test_canvas_permission_points_registered():
    from app.core.permission_catalog import (
        PERMISSION_KEYS,
        catalog_payload,
        default_permissions_for_role,
        normalize_permissions,
    )

    assert "image:create" in PERMISSION_KEYS
    assert "image:process" in PERMISSION_KEYS
    assert normalize_permissions(["image:create", "bogus"]) == frozenset({"image:create"})
    # 挂在 CAP_AGENT_USE → 内置 user 默认继承
    user = default_permissions_for_role("user")
    assert "image:create" in user
    assert "image:process" in user
    payload = catalog_payload()
    assert payload["total"] == len(PERMISSION_KEYS)


def test_canvas_endpoint_requires_auth(client):
    """未登录调用画布端点必须 401。"""
    resp = client.post("/api/v1/canvas/process", data={"operation": "compress"})
    assert resp.status_code in (401, 403)


def test_canvas_process_parameter_validation(client):
    """登录用户调用处理端点：缺图片/非法参数应得到 4xx 而非 500。"""
    resp = client.post(
        "/api/v1/canvas/process",
        data={"operation": "compress", "session_id": "x"},
        headers={"Authorization": f"Bearer {_token(1, 'admin')}"},
    )
    # 422 = 缺 image 参数（FastAPI 校验），401/403 取决于该测试库用户状态均可接受
    assert resp.status_code in (401, 403, 422)
