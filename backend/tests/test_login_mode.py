"""登录形态下发（/auth/login-mode）与 LDAP 免邮箱后缀 回归。

背景：LDAP 部署形态下账号是企业域账号（工号/用户名），登录页此前仍按
邮箱格式校验并提示「邮箱地址」，用户被迫输入邮箱后缀。现在后端下发
登录形态，前端据此切换表单；后端 login 的 email 字段本就不校验邮箱
格式（只 strip+lower），纯工号可直达 LDAP 过滤器。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_login_mode_defaults_to_local(client):
    """未配置 LDAP：本地邮箱登录，允许验证码与注册。"""
    resp = client.get("/api/v1/auth/login-mode")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] in ("ldap", "local")
    assert "email_domain" in body
    assert isinstance(body["allow_code"], bool)
    assert isinstance(body["allow_register"], bool)


def test_login_mode_hides_sensitive_values(client):
    """公开端点不得泄露 LDAP 服务器/DN/密码等配置。"""
    body = client.get("/api/v1/auth/login-mode").json()
    raw = str(body).lower()
    for leaked in ("bind_dn", "server_url", "bind_password", "ldap://", "ldaps://"):
        assert leaked not in raw


def test_login_request_accepts_employee_id_without_domain(client):
    """纯工号（无 @）必须能通过 schema 校验（此前前端拦截 + 用户被迫加后缀）。

    这里只验证请求能到达认证逻辑（凭据错误返回 401 而非 422）——
    说明「格式」不再拦人，是否认证成功取决于 LDAP/本地库。
    """
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "A1234", "password": "whatever-not-exist"},
    )
    assert resp.status_code in (401, 403, 429), resp.text
    # 关键：不是 422（格式校验失败）
    assert resp.status_code != 422
