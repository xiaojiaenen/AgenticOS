"""上游 API Key 管理：供外部软件与 AgenticOS 调用 /v1 网关。"""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any

from sqlalchemy import select

from app.core.timezone import app_now
from app.db.models import UpstreamApiKeyModel, UserModel
from app.db.session import create_db_session

logger = logging.getLogger("agenticos.upstream.apikey")

KEY_PREFIX = "sk-agenticos-"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _serialize(row: UpstreamApiKeyModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "prefix": row.prefix,
        "enabled": bool(row.enabled),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create_api_key(user_id: int, name: str = "default") -> dict[str, Any]:
    """创建 Key；明文仅在创建时返回一次。"""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    prefix = raw[:16]
    row = UpstreamApiKeyModel(
        user_id=user_id,
        name=(name or "default").strip()[:128] or "default",
        prefix=prefix,
        key_hash=_hash_key(raw),
        enabled=True,
    )
    with create_db_session() as db:
        db.add(row)
        db.commit()
        db.refresh(row)
        payload = _serialize(row)
    payload["key"] = raw
    payload["key_masked"] = f"{prefix}…{raw[-4:]}"
    logger.info(f"API key created user={user_id} prefix={prefix}")
    return payload


def list_api_keys(user_id: int, *, is_admin: bool = False) -> list[dict[str, Any]]:
    with create_db_session() as db:
        stmt = select(UpstreamApiKeyModel)
        if not is_admin:
            stmt = stmt.where(UpstreamApiKeyModel.user_id == user_id)
        rows = db.scalars(stmt.order_by(UpstreamApiKeyModel.created_at.desc())).all()
        items = []
        for r in rows:
            item = _serialize(r)
            item["key_masked"] = f"{r.prefix}…"
            items.append(item)
        return items


def revoke_api_key(user_id: int, key_id: int, *, is_admin: bool = False) -> bool:
    with create_db_session() as db:
        row = db.get(UpstreamApiKeyModel, key_id)
        if row is None:
            return False
        if not is_admin and row.user_id != user_id:
            return False
        db.delete(row)
        db.commit()
        return True


def set_api_key_enabled(user_id: int, key_id: int, enabled: bool, *, is_admin: bool = False) -> dict[str, Any] | None:
    with create_db_session() as db:
        row = db.get(UpstreamApiKeyModel, key_id)
        if row is None or (not is_admin and row.user_id != user_id):
            return None
        row.enabled = enabled
        row.updated_at = app_now()
        db.commit()
        db.refresh(row)
        item = _serialize(row)
        item["key_masked"] = f"{row.prefix}…"
        return item


def authenticate_api_key(raw_key: str) -> UserModel | None:
    """校验 Bearer sk-agenticos-*，返回所属用户。"""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None
    key_hash = _hash_key(raw_key)
    with create_db_session() as db:
        row = db.scalar(
            select(UpstreamApiKeyModel).where(
                UpstreamApiKeyModel.key_hash == key_hash,
                UpstreamApiKeyModel.enabled.is_(True),
            )
        )
        if row is None:
            return None
        user = db.get(UserModel, row.user_id)
        if user is None or not user.is_active:
            return None
        row.last_used_at = app_now()
        db.add(row)
        db.commit()
        # detach
        db.refresh(user)
        return user


def mark_used(raw_key: str) -> None:
    key_hash = _hash_key(raw_key)
    with create_db_session() as db:
        row = db.scalar(select(UpstreamApiKeyModel).where(UpstreamApiKeyModel.key_hash == key_hash))
        if row:
            row.last_used_at = app_now()
            db.add(row)
            db.commit()
