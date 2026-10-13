"""ORM → dict 序列化助手与轻量凭据/缓存对象。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.db.models import (
    ExternalApiModel,
    ExternalApiParamModel,
    ExternalSystemModel,
    ExternalUserCredentialModel,
)

# ── helpers ─────────────────────────────────────────────────────────────────


def _serialize_headers(headers_json: str) -> dict[str, str]:
    try:
        return json.loads(headers_json) if headers_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _safe_name(name: str) -> str:
    """Convert system name to a safe tool name: lowercase, underscores."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _naive_utc_now() -> datetime:
    """Return a naive UTC datetime (no tzinfo) for safe DB comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_naive(dt: datetime) -> datetime:
    """Strip tzinfo so comparisons never fail across naive/aware boundaries."""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _serialize_system(sys: ExternalSystemModel, api_count: int = 0) -> dict:
    try:
        tpl = json.loads(sys.credential_template_json) if sys.credential_template_json else {}
    except (json.JSONDecodeError, TypeError):
        tpl = {}
    return {
        "id": sys.id,
        "name": sys.name,
        "description": sys.description,
        "category": getattr(sys, "category", "other") or "other",
        "base_url": sys.base_url,
        "auth_type": sys.auth_type,
        "credential_template": tpl,
        "oauth_auth_url": sys.oauth_auth_url,
        "oauth_token_url": sys.oauth_token_url,
        "oauth_scope": sys.oauth_scope,
        "oauth_refresh_token_url": sys.oauth_refresh_token_url,
        "jwt_login_url": sys.jwt_login_url,
        "jwt_refresh_url": sys.jwt_refresh_url,
        "jwt_refresh_body_template": sys.jwt_refresh_body_template,
        "jwt_refresh_token_path": sys.jwt_refresh_token_path,
        "jwt_request_body_template": sys.jwt_request_body_template,
        "jwt_response_token_path": sys.jwt_response_token_path,
        "jwt_response_expires_path": sys.jwt_response_expires_path,
        "jwt_response_token_header": sys.jwt_response_token_header,
        "login_token_source": sys.login_token_source,
        "login_inject_mode": sys.login_inject_mode,
        "login_inject_header_name": sys.login_inject_header_name,
        "published": sys.published,
        "headers": _serialize_headers(sys.headers_json),
        "advanced_auth": json.loads(sys.advanced_auth_json) if sys.advanced_auth_json else {},
        "enabled": sys.enabled,
        "has_default_credential": bool(sys.default_credential_data_encrypted),
        "api_count": api_count,
        "created_by": sys.created_by,
        "created_at": sys.created_at,
        "updated_at": sys.updated_at,
    }


def _serialize_api(api: ExternalApiModel, params: list[ExternalApiParamModel]) -> dict:
    return {
        "id": api.id,
        "name": api.name,
        "display_name": api.display_name,
        "description": api.description,
        "method": api.method,
        "path": api.path,
        "request_body_schema": api.request_body_schema,
        "response_example": api.response_example,
        "requires_approval": api.requires_approval,
        "timeout_seconds": api.timeout_seconds,
        "body_wrapper_key": api.body_wrapper_key,
        "enabled": api.enabled,
        "params": [
            {
                "name": p.name,
                "param_type": p.param_type,
                "data_type": p.data_type,
                "required": p.required,
                "description": p.description,
                "default_value": p.default_value,
                "param_source": p.param_source,
                "label": p.label,
            }
            for p in params
        ],
        "created_at": api.created_at,
        "updated_at": api.updated_at,
    }


class _DefaultCredential:
    """从系统默认凭据构建的轻量凭据对象，兼容 AuthInjector 接口。"""
    def __init__(self, system: ExternalSystemModel):
        self.id = 0
        self.user_id = 0
        self.system_id = system.id
        self.credential_data_encrypted = system.default_credential_data_encrypted
        self.oauth_access_token_encrypted = None
        self.oauth_refresh_token_encrypted = None
        self.oauth_expires_at = None
        self.cached_jwt_encrypted = None
        self.jwt_expires_at = None
        self.connection_status = "connected"


def _build_default_credential(system: ExternalSystemModel) -> _DefaultCredential:
    """从系统的 default_credential_data_encrypted 构建伪凭据对象。"""
    return _DefaultCredential(system)


def _serialize_connection(cred: ExternalUserCredentialModel, system_name: str) -> dict:
    return {
        "id": cred.id,
        "system_id": cred.system_id,
        "system_name": system_name,
        "connection_status": cred.connection_status,
        "connected_at": cred.created_at,
        "last_checked_at": cred.last_checked_at,
    }


def _extract_nested(data: dict, path: str) -> Any:
    """Extract a value from nested dict using dot-separated path, e.g. 'data.access_token'."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current
