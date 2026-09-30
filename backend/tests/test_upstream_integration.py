"""Upstream integration unit tests (no live Playwright/network)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.upstream.auto_login_service import (
    MAX_RETRIES,
    MIN_COOKIE_EXPIRE_HOURS,
    _AUTH_COOKIE_KEYWORDS,
    _TRACKING_COOKIE_KEYWORDS,
    _friendly_error,
)
from app.services.upstream.credential_store import UPSTREAM_KEY, get_upstream_base_url, get_upstream_login_url


def test_auto_login_constants_match_sesame():
    """与 sesame auto_login_service 保持一致的关键常量。"""
    assert MAX_RETRIES == 2
    assert MIN_COOKIE_EXPIRE_HOURS == 24
    assert "session" in _AUTH_COOKIE_KEYWORDS
    assert "phpsessid" in _AUTH_COOKIE_KEYWORDS
    assert "_ga" in _TRACKING_COOKIE_KEYWORDS
    assert "utm_" in _TRACKING_COOKIE_KEYWORDS


def test_friendly_error_messages():
    assert "超时" in _friendly_error(Exception("Timeout exceeded"))
    assert "无法访问" in _friendly_error(Exception("net::ERR_NAME_NOT_RESOLVED"))
    assert "连接被拒绝" in _friendly_error(Exception("net::ERR_CONNECTION_REFUSED"))
    assert "浏览器启动失败" in _friendly_error(Exception("browser launch failed"))


def test_upstream_single_target_config():
    from app.core.config import get_settings

    s = get_settings()
    assert UPSTREAM_KEY == "agents.gree.com"
    assert "agents.gree.com" in get_upstream_base_url() or "gree.com" in get_upstream_base_url()
    login = get_upstream_login_url()
    assert login.startswith("http")
    assert s.upstream_base_url.rstrip("/").endswith("gree.com") or "agents" in s.upstream_base_url


def test_upsert_and_active_cookie_roundtrip():
    from uuid import uuid4

    from sqlalchemy import delete, text

    from app.db.models import UserModel
    from app.db.session import create_db_session
    from app.services.upstream import credential_store

    email = f"up-test-{uuid4().hex[:8]}@example.com"
    with create_db_session() as db:
        user = UserModel(email=email, name="U", password_hash="x", role="user", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id

    try:
        record = credential_store.upsert_credentials(
            user_id=uid,
            username="10001",
            password="secret-pwd",
            display_name="Test",
        )
        assert record["username"] == "10001"
        assert record["status"] == "pending"
        assert record["upstream"] == UPSTREAM_KEY
        assert credential_store.get_active_cookie(uid) is None

        from app.core.timezone import app_now
        from datetime import timedelta

        credential_store.apply_login_result(
            uid,
            success=True,
            cookie="SESSION=abc; other=1",
            expire_at=app_now() + timedelta(hours=48),
        )
        cookie = credential_store.get_active_cookie(uid)
        assert cookie == "SESSION=abc; other=1"

        status_items = credential_store.list_credentials_status(user_id=uid)
        assert status_items and status_items[0]["healthy"] is True
    finally:
        with create_db_session() as db:
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            db.execute(
                delete(__import__("app.db.models", fromlist=["UpstreamCredentialModel"]).UpstreamCredentialModel).where(
                    __import__("app.db.models", fromlist=["UpstreamCredentialModel"]).UpstreamCredentialModel.user_id == uid
                )
            )
            db.execute(delete(UserModel).where(UserModel.id == uid))
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            db.commit()


def test_api_key_create_and_auth():
    from uuid import uuid4

    from sqlalchemy import delete, text

    from app.db.models import UpstreamApiKeyModel, UserModel
    from app.db.session import create_db_session
    from app.services.upstream import api_key_service

    email = f"key-test-{uuid4().hex[:8]}@example.com"
    with create_db_session() as db:
        user = UserModel(email=email, name="K", password_hash="x", role="user", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id

    try:
        created = api_key_service.create_api_key(uid, name="unit")
        assert created["key"].startswith(api_key_service.KEY_PREFIX)
        raw = created["key"]
        found = api_key_service.authenticate_api_key(raw)
        assert found is not None and found.id == uid
        assert api_key_service.authenticate_api_key("sk-agenticos-invalid") is None
        items = api_key_service.list_api_keys(uid)
        assert any(i["id"] == created["id"] for i in items)
        assert api_key_service.revoke_api_key(uid, created["id"])
        assert api_key_service.authenticate_api_key(raw) is None
    finally:
        with create_db_session() as db:
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            db.execute(delete(UpstreamApiKeyModel).where(UpstreamApiKeyModel.user_id == uid))
            db.execute(delete(UserModel).where(UserModel.id == uid))
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            db.commit()


@pytest.mark.anyio
async def test_perform_auto_login_missing_credential():
    from app.services.upstream.login_orchestrator import perform_auto_login

    result = await perform_auto_login(user_id=99999999)
    assert result["success"] is False
    assert "未配置" in result["message"]


@pytest.mark.anyio
async def test_upstream_client_health_shape():
    from app.services.upstream.upstream_client import UpstreamClient

    client = UpstreamClient(base_url="https://agents.gree.com")
    with patch.object(client, "list_models", new=AsyncMock(return_value={"data": []})):
        with patch("app.services.upstream.upstream_client.credential_store.get_active_cookie", return_value="c=1"):
            info = await client.health(user_id=1)
    assert "base_url" in info
    assert "login_url" in info
    assert info["base_url"].startswith("https://")
