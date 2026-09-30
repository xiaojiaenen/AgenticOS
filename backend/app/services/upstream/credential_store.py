"""上游凭据/cookie 存取（唯一上游 agents.gree.com）。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_safe, encrypt
from app.core.timezone import app_now
from app.db.models import UpstreamCredentialModel
from app.db.session import create_db_session

logger = logging.getLogger("agenticos.upstream.credentials")

UPSTREAM_KEY = "agents.gree.com"


def get_upstream_login_url() -> str:
    from app.core.config import get_settings

    s = get_settings()
    url = (s.upstream_login_url or "").strip()
    if url:
        return url.rstrip("/")
    base = (s.upstream_base_url or "https://agents.gree.com").rstrip("/")
    # 默认登录页：与 sesame 常见配置一致，可被 UPSTREAM_LOGIN_URL 覆盖
    return f"{base}/login"


def get_upstream_base_url() -> str:
    from app.core.config import get_settings

    return (get_settings().upstream_base_url or "https://agents.gree.com").rstrip("/")


def _serialize(row: UpstreamCredentialModel) -> dict[str, Any]:
    now = app_now()
    expire = row.expire_at
    if expire is not None and expire.tzinfo is None:
        # stored naive app timezone
        from app.core.timezone import APP_TIMEZONE

        expire = expire.replace(tzinfo=APP_TIMEZONE)
    healthy = (
        row.status == "active"
        and bool(row.cookie_encrypted)
        and (expire is None or expire > now)
    )
    return {
        "id": row.id,
        "user_id": row.user_id,
        "username": row.username,
        "upstream": UPSTREAM_KEY,
        "base_url": get_upstream_base_url(),
        "login_url": row.login_url,
        "status": row.status,
        "auto_refresh": bool(row.auto_refresh),
        "expire_at": expire.isoformat() if expire else None,
        "healthy": healthy,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
        "last_error": row.last_error,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_credential_for_user(user_id: int, db: Session | None = None) -> UpstreamCredentialModel | None:
    def _q(session: Session) -> UpstreamCredentialModel | None:
        return session.scalar(
            select(UpstreamCredentialModel).where(
                UpstreamCredentialModel.user_id == user_id,
                UpstreamCredentialModel.upstream_key == UPSTREAM_KEY,
            )
        )

    if db is not None:
        return _q(db)
    with create_db_session() as session:
        return _q(session)


def upsert_credentials(
    *,
    user_id: int,
    username: str,
    password: str,
    display_name: str | None = None,
    login_url: str | None = None,
    auto_refresh: bool = True,
) -> dict[str, Any]:
    """写入/更新用户的上游账号密码（cookie 由后台自动登录填充）。"""
    url = login_url or get_upstream_login_url()
    now = app_now()
    pwd_enc = encrypt(password)

    with create_db_session() as db:
        row = db.scalar(
            select(UpstreamCredentialModel).where(
                UpstreamCredentialModel.user_id == user_id,
                UpstreamCredentialModel.upstream_key == UPSTREAM_KEY,
            )
        )
        if row is None:
            row = UpstreamCredentialModel(
                user_id=user_id,
                upstream_key=UPSTREAM_KEY,
                username=username,
                password_encrypted=pwd_enc,
                login_url=url,
                display_name=display_name,
                cookie_encrypted="",
                status="pending",
                auto_refresh=auto_refresh,
                expire_at=now + timedelta(days=7),
            )
            db.add(row)
        else:
            row.username = username
            row.password_encrypted = pwd_enc
            row.login_url = url
            if display_name:
                row.display_name = display_name
            row.auto_refresh = auto_refresh
            row.updated_at = now
        db.commit()
        db.refresh(row)
        return _serialize(row)


def apply_login_result(
    user_id: int,
    *,
    success: bool,
    cookie: str | None,
    expire_at: datetime | None,
    error: str | None = None,
) -> None:
    """把自动登录结果写回凭据表。"""
    now = app_now()
    with create_db_session() as db:
        row = db.scalar(
            select(UpstreamCredentialModel).where(
                UpstreamCredentialModel.user_id == user_id,
                UpstreamCredentialModel.upstream_key == UPSTREAM_KEY,
            )
        )
        if row is None:
            return
        if success and cookie:
            row.cookie_encrypted = encrypt(cookie)
            row.status = "active"
            row.expire_at = expire_at or (now + timedelta(days=7))
            row.last_login_at = now
            row.last_error = None
        else:
            row.status = "failed" if row.status != "active" else "expired"
            row.last_error = (error or "auto login failed")[:500]
            row.last_login_at = now
        row.updated_at = now
        db.commit()


def get_active_cookie(user_id: int) -> str | None:
    """返回当前用户可用的上游 Cookie 字符串；不可用时返回 None。"""
    row = get_credential_for_user(user_id)
    if row is None or row.status != "active" or not row.cookie_encrypted:
        return None
    expire = row.expire_at
    if expire is not None:
        from app.core.timezone import APP_TIMEZONE

        exp = expire.replace(tzinfo=APP_TIMEZONE) if expire.tzinfo is None else expire
        if exp <= app_now():
            return None
    return decrypt_safe(row.cookie_encrypted, default="") or None


def list_credentials_status(user_id: int | None = None) -> list[dict[str, Any]]:
    with create_db_session() as db:
        stmt = select(UpstreamCredentialModel).where(UpstreamCredentialModel.upstream_key == UPSTREAM_KEY)
        if user_id is not None:
            stmt = stmt.where(UpstreamCredentialModel.user_id == user_id)
        rows = db.scalars(stmt.order_by(UpstreamCredentialModel.updated_at.desc())).all()
        return [_serialize(r) for r in rows]
