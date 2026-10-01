"""外部系统配置的 Redis 缓存（key: agenticos:ext_system:{id}，TTL 24h）。"""

from __future__ import annotations

import json

from app.core.redis import get_redis
from app.db.models import ExternalSystemModel

# ── Redis-backed cache for external system config ──────────────────────────
# Key: agenticos:ext_system:{id}  |  TTL: 24h (auto-refresh on access)
_SYSTEM_CACHE_TTL = 86400  # 24 hours


def _system_cache_key(system_id: int) -> str:
    return f"agenticos:ext_system:{system_id}"


# Fields cached from ExternalSystemModel (only what handler + AuthInjector need)
_CACHE_FIELDS = [
    "id", "name", "base_url", "auth_type", "headers_json",
    "jwt_login_url", "jwt_refresh_url", "jwt_request_body_template",
    "jwt_response_token_path", "jwt_response_expires_path",
    "jwt_response_token_header",
    "login_token_source", "login_inject_mode", "login_inject_header_name",
    "jwt_refresh_body_template",
    "oauth_auth_url", "oauth_token_url", "oauth_scope",
    "oauth_refresh_token_url", "oauth_client_id_encrypted",
    "oauth_client_secret_encrypted", "advanced_auth_json",
    "default_credential_data_encrypted",
]


def _serialize_system_for_cache(sys: ExternalSystemModel) -> dict[str, str]:
    """Extract cacheable fields from ORM object → dict of strings."""
    data: dict[str, str] = {}
    for f in _CACHE_FIELDS:
        val = getattr(sys, f, None)
        data[f] = str(val) if val is not None else ""
    return data


class _CachedSystem:
    """Lightweight read-only proxy that mimics ExternalSystemModel attribute access."""

    __slots__ = _CACHE_FIELDS

    def __init__(self, data: dict[str, str]):
        for f in _CACHE_FIELDS:
            raw = data.get(f, "")
            # Restore int for id
            if f == "id":
                setattr(self, f, int(raw) if raw else 0)
            else:
                setattr(self, f, raw if raw else None)


async def _cache_put(system: ExternalSystemModel) -> None:
    """Write system config to Redis."""
    r = get_redis()
    key = _system_cache_key(system.id)
    data = _serialize_system_for_cache(system)
    await r.set(key, json.dumps(data, ensure_ascii=False), ex=_SYSTEM_CACHE_TTL)


async def _cache_get(system_id: int) -> _CachedSystem | None:
    """Read system config from Redis. Returns None on miss."""
    r = get_redis()
    key = _system_cache_key(system_id)
    raw = await r.get(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return _CachedSystem(data)
    except (json.JSONDecodeError, TypeError):
        return None


async def _cache_delete(system_id: int) -> None:
    """Remove system from cache."""
    r = get_redis()
    await r.delete(_system_cache_key(system_id))


async def refresh_system_cache(system_id: int) -> None:
    """Reload system from DB and push to Redis. Called after update_system()."""
    from app.db.session import create_db_session
    db = create_db_session()
    try:
        sys = db.get(ExternalSystemModel, system_id)
        if sys:
            await _cache_put(sys)
    finally:
        db.close()
