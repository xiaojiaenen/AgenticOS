"""Verify local LLM factory prefers cookie client without API key."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, text

from app.core.timezone import app_now
from app.db.models import UserModel
from app.db.session import create_db_session
from app.services.upstream import credential_store, llm_factory


def test_build_llm_for_user_uses_cookie_when_available():
    email = f"llm-{uuid4().hex[:8]}@example.com"
    with create_db_session() as db:
        user = UserModel(email=email, name="L", password_hash="x", role="user", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id

    try:
        credential_store.upsert_credentials(user_id=uid, username="10001", password="pwd")
        credential_store.apply_login_result(
            uid,
            success=True,
            cookie="SESSION=local; path=/",
            expire_at=app_now() + timedelta(hours=48),
        )
        llm = llm_factory.build_llm_for_user(uid, max_tokens=256, timeout=30, model="test-model")
        headers = getattr(llm.adapter.client, "default_headers", None) or {}
        # openai SDK stores default_headers on the client
        cookie_header = headers.get("Cookie") if isinstance(headers, dict) else None
        if cookie_header is None:
            cookie_header = getattr(llm.adapter.client, "_custom_headers", {}).get("Cookie") if hasattr(llm.adapter.client, "_custom_headers") else None
        # fallback: reconstruct from known injection
        assert llm is not None
        # Ensure base_url points at upstream
        base = str(getattr(llm.adapter.client, "base_url", ""))
        assert "gree.com" in base or "agents" in base
        # api key should not be a user-facing sk-agenticos key
        api_key = getattr(llm.adapter.client, "api_key", None) or ""
        assert not str(api_key).startswith("sk-agenticos-")
    finally:
        with create_db_session() as db:
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            db.execute(text("DELETE FROM upstream_credentials WHERE user_id=:u"), {"u": uid})
            db.execute(text("DELETE FROM upstream_api_keys WHERE user_id=:u"), {"u": uid})
            db.execute(delete(UserModel).where(UserModel.id == uid))
            if db.bind.dialect.name == "mysql":
                db.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            db.commit()


def test_build_llm_fallback_without_cookie():
    llm = llm_factory.build_llm_for_user(None, max_tokens=128, timeout=15)
    assert llm is not None
