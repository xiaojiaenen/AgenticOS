"""External system integration — CRUD, user credentials, one-tool-per-system design."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import hmac
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt, decrypt_safe, encrypt
from app.core.redis import get_redis
from app.db.models import (
    AgentProfileExternalSystemModel,
    ExternalApiModel,
    ExternalApiParamModel,
    ExternalSystemModel,
    ExternalUserCredentialModel,
)
from app.schemas.external_systems import (
    ExternalApiCreateRequest,
    ExternalApiTestResponse,
    ExternalApiUpdateRequest,
    ExternalSystemCreateRequest,
    ExternalSystemUpdateRequest,
)

logger = logging.getLogger(__name__)

# ── 集成分类常量（预设，不提供管理 API） ────────────────────────────────────
INTEGRATION_CATEGORIES: list[dict[str, str]] = [
    {"key": "collaboration",  "label": "协作办公",  "icon": "💬"},
    {"key": "devops",         "label": "研发效能",  "icon": "🔧"},
    {"key": "compute",        "label": "计算引擎",  "icon": "⚡"},
    {"key": "scheduler",      "label": "任务调度",  "icon": "📋"},
    {"key": "storage",        "label": "数据存储",  "icon": "💾"},
    {"key": "resource",       "label": "资源管理",  "icon": "🖥️"},
    {"key": "integration",    "label": "数据集成",  "icon": "🔄"},
    {"key": "governance",     "label": "数据治理",  "icon": "🔍"},
    {"key": "bi",             "label": "BI 监控",   "icon": "📊"},
    {"key": "other",          "label": "其他",      "icon": "📦"},
]

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


# ── context vars for current user (like email_tools pattern) ────────────────

_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("ext_current_user_id", default=0)
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("ext_current_session_id", default="")


def set_ext_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)


def get_ext_user_id() -> int:
    return _current_user_id.get()


# ── UserInput 阻塞机制（类似审批的 queue+Future 模式）────────────────────

class UserInputBlocker:
    """per-session 的 Future + Queue，让 handler 在需要用户输入时阻塞等待。"""
    _queues: dict[str, asyncio.Queue] = {}
    _futures: dict[str, asyncio.Future] = {}

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        cls._queues[session_id] = q
        return q

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        cls._queues.pop(session_id, None)
        cls._futures.pop(session_id, None)

    @classmethod
    async def request_input(cls, session_id: str, payload: dict) -> dict:
        """阻塞等待用户输入。返回用户提交的 values dict。"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        cls._futures[session_id] = fut
        q = cls._queues.get(session_id)
        if q is not None:
            q.put_nowait(payload)
        return await fut

    @classmethod
    def resolve(cls, session_id: str, values: dict) -> None:
        fut = cls._futures.pop(session_id, None)
        if fut and not fut.done():
            fut.set_result(values)


class ApprovalBlocker:
    """API 级别审批：per-session 的 Future + Queue，让 handler 在需要审批时阻塞等待。"""
    _queues: dict[str, asyncio.Queue] = {}
    _futures: dict[str, asyncio.Future] = {}

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        cls._queues[session_id] = q
        return q

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        cls._queues.pop(session_id, None)
        cls._futures.pop(session_id, None)

    @classmethod
    async def request_approval(cls, session_id: str, payload: dict) -> bool:
        """阻塞等待用户审批。返回 True=批准, False=拒绝。"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        cls._futures[session_id] = fut
        q = cls._queues.get(session_id)
        if q is not None:
            q.put_nowait(payload)
        result = await fut
        return bool(result.get("approved", False)) if isinstance(result, dict) else bool(result)

    @classmethod
    def resolve(cls, session_id: str, decision: dict) -> None:
        fut = cls._futures.pop(session_id, None)
        if fut and not fut.done():
            fut.set_result(decision)


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


# ── AuthInjector ────────────────────────────────────────────────────────────


class AuthInjector:
    """Inject authentication info from user credentials into outgoing requests."""

    @staticmethod
    async def inject(
        system: ExternalSystemModel,
        cred: ExternalUserCredentialModel,
        request: httpx.Request,
    ) -> None:
        if not cred:
            raise ValueError(f"请先连接 {system.name} 集成")
        if cred.connection_status == "expired":
            raise ValueError(f"{system.name} 连接已过期，请重新连接")
        if cred.connection_status == "auth_error":
            raise ValueError(f"{system.name} 凭据无效，请重新连接")

        auth_type = system.auth_type

        if auth_type == "oauth2":
            token = await AuthInjector._ensure_valid_token(system, cred)
            request.headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "jwt_login":
            token = await AuthInjector._ensure_jwt(system, cred)
            # Determine inject mode: explicit login_inject_mode > legacy jwt_response_token_header > default bearer
            inject_mode = system.login_inject_mode or ("header" if system.jwt_response_token_header else "bearer")
            if inject_mode == "header":
                header_name = system.login_inject_header_name or system.jwt_response_token_header or "X-Auth-Token"
                request.headers[header_name] = token
            else:
                request.headers["Authorization"] = f"Bearer {token}"
        else:
            config_raw = decrypt_safe(cred.credential_data_encrypted, "{}")
            try:
                config: dict = json.loads(config_raw) if config_raw else {}
            except (json.JSONDecodeError, TypeError):
                config = {}

            if auth_type == "api_key":
                key = config.get("key", "")
                inject_in = config.get("inject_in", "header")
                header_name = config.get("header_name", "X-API-Key")
                param_name = config.get("param_name", "api_key")
                if inject_in == "query":
                    request.url = request.url.copy_merge_params({param_name: key})
                else:
                    request.headers[header_name] = key

            elif auth_type == "bearer":
                token = config.get("token", "")
                request.headers["Authorization"] = f"Bearer {token}"

            elif auth_type == "basic":
                username = config.get("username", "")
                password = config.get("password", "")
                encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
                request.headers["Authorization"] = f"Basic {encoded}"

            elif auth_type == "custom":
                for k, v in config.get("headers", {}).items():
                    request.headers[k] = str(v)

        # Inject extra fixed headers from the system config
        for k, v in _serialize_headers(system.headers_json).items():
            request.headers[k] = v

    @staticmethod
    async def _ensure_valid_token(system: ExternalSystemModel, cred: ExternalUserCredentialModel) -> str:
        # Check if current token is still valid (with 60s buffer)
        if (
            cred.oauth_expires_at
            and cred.oauth_access_token_encrypted
            and _make_naive(cred.oauth_expires_at) > _naive_utc_now() - timedelta(seconds=60)
        ):
            return decrypt_safe(cred.oauth_access_token_encrypted)

        # Need to refresh
        refresh_token = decrypt_safe(cred.oauth_refresh_token_encrypted or "")
        if not refresh_token:
            cred.connection_status = "expired"
            raise ValueError(f"{system.name} 连接已过期，请重新连接")

        token_url = system.oauth_token_url
        if not token_url:
            raise ValueError("OAuth2 token_url is not configured on this system")

        client_id = decrypt_safe(system.oauth_client_id_encrypted or "")
        client_secret = decrypt_safe(system.oauth_client_secret_encrypted or "")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        new_access = token_data["access_token"]
        new_refresh = token_data.get("refresh_token", refresh_token)
        expires_in = token_data.get("expires_in", 3600)

        # Persist updated tokens
        from app.db.session import create_db_session

        db = create_db_session()
        try:
            db_cred = db.get(ExternalUserCredentialModel, cred.id)
            if db_cred:
                db_cred.oauth_access_token_encrypted = encrypt(new_access)
                db_cred.oauth_refresh_token_encrypted = encrypt(new_refresh)
                db_cred.oauth_expires_at = _naive_utc_now() + timedelta(seconds=expires_in)
                db_cred.connection_status = "connected"
                db.commit()
        finally:
            db.close()

        return new_access

    @staticmethod
    async def _ensure_jwt(system: ExternalSystemModel, cred: ExternalUserCredentialModel) -> str:
        """Return a valid JWT — try refresh_token first, fall back to login."""
        # Check cached JWT (with 60s buffer)
        if (
            cred.jwt_expires_at
            and cred.cached_jwt_encrypted
            and _make_naive(cred.jwt_expires_at) > _naive_utc_now() - timedelta(seconds=60)
        ):
            return decrypt_safe(cred.cached_jwt_encrypted)

        # ── Try refresh_token first ──────────────────────────────────────
        refresh_token = decrypt_safe(cred.oauth_refresh_token_encrypted or "")
        if refresh_token and system.jwt_refresh_url:
            try:
                # Build refresh request body from template
                refresh_body: dict = {"refresh_token": refresh_token}
                if system.jwt_refresh_body_template:
                    try:
                        body_str = system.jwt_refresh_body_template.replace("{refresh_token}", refresh_token)
                        refresh_body = json.loads(body_str)
                    except (json.JSONDecodeError, TypeError):
                        pass

                base = system.base_url.rstrip("/")
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.post(base + system.jwt_refresh_url, json=refresh_body)
                    resp.raise_for_status()

                # Determine token source
                token_source = system.login_token_source
                if not token_source:
                    token_source = "header" if system.jwt_response_token_header else "body"

                # Extract token from configured source
                new_token = None
                resp_data = None
                if token_source == "header":
                    header_name = system.jwt_response_token_header or "Authorization"
                    new_token = resp.headers.get(header_name)
                else:
                    resp_data = resp.json()
                    token_path = system.jwt_response_token_path or "token"
                    new_token = _extract_nested(resp_data, token_path)
                if new_token:
                    expires_at = None
                    if system.jwt_response_expires_path:
                        if resp_data is None:
                            resp_data = resp.json()
                        expires_in = _extract_nested(resp_data, system.jwt_response_expires_path)
                        if isinstance(expires_in, (int, float)):
                            expires_at = _naive_utc_now() + timedelta(seconds=int(expires_in))
                    if not expires_at:
                        expires_at = _naive_utc_now() + timedelta(hours=1)

                    # Extract new refresh token from response
                    rt_path = system.jwt_refresh_token_path or "refresh_token"
                    new_refresh = _extract_nested(resp_data, rt_path) or refresh_token

                    from app.db.session import create_db_session
                    db = create_db_session()
                    try:
                        db_cred = db.get(ExternalUserCredentialModel, cred.id)
                        if db_cred:
                            db_cred.cached_jwt_encrypted = encrypt(str(new_token))
                            db_cred.jwt_expires_at = expires_at
                            db_cred.oauth_refresh_token_encrypted = encrypt(str(new_refresh))
                            db_cred.connection_status = "connected"
                            db.commit()
                    finally:
                        db.close()
                    return str(new_token)
            except Exception:
                pass  # refresh failed, fall through to login

        # ── Login with username/password ─────────────────────────────────
        config_raw = decrypt_safe(cred.credential_data_encrypted, "{}")
        try:
            config: dict = json.loads(config_raw) if config_raw else {}
        except (json.JSONDecodeError, TypeError):
            config = {}

        login_url = system.jwt_login_url
        if not login_url:
            raise ValueError("JWT 登录地址未配置")

        # Build request body from template
        body_template = system.jwt_request_body_template or '{"username":"{username}","password":"{password}"}'
        try:
            body_str = body_template
            for key, value in config.items():
                body_str = body_str.replace(f"{{{key}}}", str(value))
            body = json.loads(body_str)
        except (json.JSONDecodeError, TypeError):
            body = {"username": config.get("username", ""), "password": config.get("password", "")}

        base = system.base_url.rstrip("/")
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(base + login_url, json=body)
            resp.raise_for_status()

        # Determine token source: explicit login_token_source > auto-detect
        token_source = system.login_token_source
        if not token_source:
            token_source = "header" if system.jwt_response_token_header else "body"

        # Extract token from configured source
        token = None
        resp_data = None
        if token_source == "header":
            header_name = system.jwt_response_token_header or "Authorization"
            token = resp.headers.get(header_name)
            # For Set-Cookie, extract the value
            if not token and header_name.lower() == "set-cookie":
                cookie = resp.headers.get("set-cookie", "")
                token = cookie.split(";")[0] if cookie else None
        else:
            resp_data = resp.json()
            token_path = system.jwt_response_token_path or "token"
            token = _extract_nested(resp_data, token_path)
        if not token:
            raise ValueError(f"登录响应中未找到 token（来源: {token_source}）")

        # Extract expiry if configured
        expires_at = None
        if system.jwt_response_expires_path:
            if resp_data is None:
                resp_data = resp.json()
            expires_in = _extract_nested(resp_data, system.jwt_response_expires_path)
            if isinstance(expires_in, (int, float)):
                expires_at = _naive_utc_now() + timedelta(seconds=int(expires_in))

        # If no expiry from response, default to 1 hour
        if not expires_at:
            expires_at = _naive_utc_now() + timedelta(hours=1)

        # Persist cached JWT
        from app.db.session import create_db_session

        db = create_db_session()
        try:
            db_cred = db.get(ExternalUserCredentialModel, cred.id)
            if db_cred:
                db_cred.cached_jwt_encrypted = encrypt(str(token))
                db_cred.jwt_expires_at = expires_at
                db_cred.connection_status = "connected"
                db.commit()
        finally:
            db.close()

        return str(token)


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


# ── Security Processor (signing / encryption) ──────────────────────────────


class SecurityProcessor:
    """Handle request signing, request encryption, and response decryption."""

    @staticmethod
    def sign_hmac(data: str, secret: str, algorithm: str) -> str:
        """HMAC signing: hmac_sha256, hmac_sha512, hmac_md5."""
        algo_map = {"hmac_sha256": "sha256", "hmac_sha512": "sha512", "hmac_md5": "md5"}
        hash_name = algo_map.get(algorithm, "sha256")
        sig = hmac.new(secret.encode("utf-8"), data.encode("utf-8"), getattr(__import__("hashlib", fromlist=[hash_name]), hash_name)).digest()
        return sig

    @staticmethod
    def sign_rsa(data: str, private_key_pem: str, algorithm: str) -> bytes:
        """RSA signing: sha256_with_rsa, sha1_with_rsa, md5_with_rsa."""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        hash_algo_map = {
            "sha256_with_rsa": hashes.SHA256(),
            "sha1_with_rsa": hashes.SHA1(),
            "md5_with_rsa": hashes.MD5(),
        }
        hash_algo = hash_algo_map.get(algorithm, hashes.SHA256())

        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
        sig = key.sign(data.encode("utf-8"), padding.PKCS1v15(), hash_algo)
        return sig

    @staticmethod
    def encrypt_aes(plaintext: str, key: str, iv: str, algorithm: str) -> bytes:
        """AES encryption: aes_128_cbc, aes_256_cbc, aes_256_gcm, aes_ecb."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding

        key_bytes = key.encode("utf-8")
        data = plaintext.encode("utf-8")

        if algorithm == "aes_ecb" or algorithm == "aes_128_ecb":
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            padder = sym_padding.PKCS7(128).padder()
            data = padder.update(data) + padder.finalize()
        elif algorithm == "aes_256_gcm":
            iv_bytes = iv.encode("utf-8")[:12]
            cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv_bytes))
            encryptor = cipher.encryptor()
            return encryptor.update(data) + encryptor.finalize() + encryptor.tag
        else:
            iv_bytes = iv.encode("utf-8")[:16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
            padder = sym_padding.PKCS7(128).padder()
            data = padder.update(data) + padder.finalize()

        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()

    @staticmethod
    def decrypt_aes(ciphertext: bytes, key: str, iv: str, algorithm: str) -> str:
        """AES decryption."""
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding

        key_bytes = key.encode("utf-8")

        if algorithm == "aes_ecb" or algorithm == "aes_128_ecb":
            cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
            decryptor = cipher.decryptor()
            data = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            data = unpadder.update(data) + unpadder.finalize()
            return data.decode("utf-8")
        elif algorithm == "aes_256_gcm":
            iv_bytes = iv.encode("utf-8")[:12]
            tag = ciphertext[-16:]
            ct = ciphertext[:-16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv_bytes, tag))
            decryptor = cipher.decryptor()
            return (decryptor.update(ct) + decryptor.finalize()).decode("utf-8")
        else:
            iv_bytes = iv.encode("utf-8")[:16]
            cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
            decryptor = cipher.decryptor()
            data = decryptor.update(ciphertext) + decryptor.finalize()
            unpadder = sym_padding.PKCS7(128).unpadder()
            data = unpadder.update(data) + unpadder.finalize()
            return data.decode("utf-8")

    @classmethod
    async def process_request(cls, system: ExternalSystemModel, request: httpx.Request) -> None:
        """Apply signing and encryption to the outgoing request."""
        try:
            aa = json.loads(system.advanced_auth_json) if system.advanced_auth_json else {}
        except (json.JSONDecodeError, TypeError):
            return

        sign_cfg = aa.get("sign", {})
        enc_cfg = aa.get("request_encrypt", {})
        common_cfg = aa.get("common", {})

        algorithm = sign_cfg.get("algorithm", "none")
        if algorithm == "none" and enc_cfg.get("algorithm", "none") == "none":
            return

        # Generate timestamp + nonce
        now = _naive_utc_now()
        timestamp = ""
        nonce = ""
        ts_field = common_cfg.get("timestamp_field", "")
        nonce_field = common_cfg.get("nonce_field", "")

        if ts_field:
            if common_cfg.get("timestamp_format") == "iso8601":
                timestamp = now.isoformat()
            else:
                timestamp = str(int(now.timestamp()))

        if nonce_field:
            import secrets
            length = common_cfg.get("nonce_length", 16)
            nonce = secrets.token_hex(length // 2)

        # ── Signing ──
        if algorithm != "none":
            secret = decrypt_safe(sign_cfg.get("secret", ""))
            placement = sign_cfg.get("placement", "header")
            field_name = sign_cfg.get("field_name", "X-Signature")
            content_template = sign_cfg.get("content_template", "{body}")
            encoding = sign_cfg.get("encoding", "base64")

            body_text = ""
            if request.content:
                body_text = request.content.decode("utf-8", errors="replace")

            sign_content = content_template.replace("{timestamp}", timestamp).replace("{nonce}", nonce).replace("{body}", body_text)

            if algorithm.startswith("hmac"):
                raw_sig = cls.sign_hmac(sign_content, secret, algorithm)
            else:
                raw_sig = cls.sign_rsa(sign_content, secret, algorithm)

            if encoding == "hex":
                sig_str = raw_sig.hex()
            else:
                sig_str = base64.b64encode(raw_sig).decode("ascii")

            if placement == "header":
                request.headers[field_name] = sig_str
            elif placement == "query":
                url = str(request.url)
                sep = "&" if "?" in url else "?"
                request.url = httpx.URL(f"{url}{sep}{field_name}={sig_str}")
            elif placement == "body":
                # For body placement, we'd need to modify the body — skip for now
                pass

        # ── Request Encryption ──
        enc_algorithm = enc_cfg.get("algorithm", "none")
        if enc_algorithm != "none" and request.content:
            enc_key = decrypt_safe(enc_cfg.get("key", ""))
            enc_iv = decrypt_safe(enc_cfg.get("iv", ""))
            encoding = enc_cfg.get("encoding", "base64")

            plaintext = request.content.decode("utf-8", errors="replace")
            encrypted = cls.encrypt_aes(plaintext, enc_key, enc_iv, enc_algorithm)

            if encoding == "hex":
                result = encrypted.hex()
            else:
                result = base64.b64encode(encrypted).decode("ascii")

            scope = enc_cfg.get("scope", "body")
            if scope == "body":
                request.content = json.dumps({"encrypted": result}).encode("utf-8")
                request.headers["Content-Type"] = "application/json"

        # Add common fields to headers
        if ts_field and timestamp:
            request.headers[ts_field] = timestamp
        if nonce_field and nonce:
            request.headers[nonce_field] = nonce

    @classmethod
    async def process_response(cls, system: ExternalSystemModel, response_text: str) -> str:
        """Decrypt response if configured."""
        try:
            aa = json.loads(system.advanced_auth_json) if system.advanced_auth_json else {}
        except (json.JSONDecodeError, TypeError):
            return response_text

        dec_cfg = aa.get("response_decrypt", {})
        dec_algorithm = dec_cfg.get("algorithm", "none")
        if dec_algorithm == "none":
            return response_text

        try:
            resp_json = json.loads(response_text)
        except (json.JSONDecodeError, TypeError):
            return response_text

        path = dec_cfg.get("path", "")
        if not path:
            return response_text

        ciphertext_b64 = _extract_nested(resp_json, path)
        if not ciphertext_b64:
            return response_text

        dec_key = decrypt_safe(dec_cfg.get("key", ""))
        dec_iv = decrypt_safe(dec_cfg.get("iv", ""))
        encoding = dec_cfg.get("encoding", "base64")

        try:
            if encoding == "hex":
                ct_bytes = bytes.fromhex(str(ciphertext_b64))
            else:
                ct_bytes = base64.b64decode(str(ciphertext_b64))

            plaintext = cls.decrypt_aes(ct_bytes, dec_key, dec_iv, dec_algorithm)

            # Replace the encrypted field with decrypted content
            keys = path.split(".")
            current = resp_json
            for key in keys[:-1]:
                current = current.get(key, {})
            current[keys[-1]] = json.loads(plaintext) if plaintext.startswith(("{", "[")) else plaintext
            return json.dumps(resp_json, ensure_ascii=False)
        except Exception:
            return response_text


# ── helpers for tool building ───────────────────────────────────────────────


def _resolve_path(template: str, params: dict[str, Any]) -> str:
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        return str(params.get(key, match.group(0)))
    return re.sub(r"\{(\w+)\}", replacer, template)


def _cast_value(value: Any, data_type: str) -> Any:
    if value is None:
        return None
    if data_type == "integer":
        return int(value)
    if data_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes")
    if data_type == "object":
        if isinstance(value, str):
            return json.loads(value)
        return value
    return str(value)


# ── One tool per system ─────────────────────────────────────────────────────


def _build_system_tool_handler(
    system: ExternalSystemModel,
    api_map: dict[str, tuple[ExternalApiModel, list[ExternalApiParamModel]]],
    user_id: int,
):
    """Build one handler that dispatches to the correct API based on api_name."""
    available_names = list(api_map.keys())

    async def handler(api_name: str, params: dict = {}) -> str:
        # 运行时动态获取 user_id（agent 可能被不同用户共享）
        from app.services.external_system_service import get_ext_user_id as _get_uid
        effective_user_id = _get_uid() or user_id

        entry = api_map.get(api_name)
        if not entry:
            return json.dumps({
                "error": f"未知操作 '{api_name}'。可用操作: {', '.join(available_names)}",
            }, ensure_ascii=False)

        api, param_rows = entry

        # 实时刷新参数（避免闭包缓存旧数据）
        from app.db.session import create_db_session
        _db = create_db_session()
        try:
            param_rows = list(_db.execute(
                select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api.id)
            ).scalars().all())
            # 同步刷新 api 上的动态字段（闭包缓存的 api 对象可能过期）
            fresh = _db.get(ExternalApiModel, api.id)
            if fresh:
                api.body_wrapper_key = fresh.body_wrapper_key
        finally:
            _db.close()

        # API 级别审批：检查该 API 是否需要审批
        if api.requires_approval:
            session_id = _current_session_id.get()
            if session_id:
                logger.warning("ApprovalRequired: session=%s api=%s", session_id, api_name)
                payload = {
                    "type": "api_approval_required",
                    "api_name": api_name,
                    "api_display_name": api.display_name,
                    "system_name": system.name,
                    "method": api.method,
                    "path": api.path,
                    "message": f"调用 {system.name} → {api.display_name}（{api.method} {api.path}）需要审批",
                }
                approved = await ApprovalBlocker.request_approval(session_id, payload)
                if not approved:
                    return json.dumps({
                        "error": f"操作 {api.display_name} 已被用户拒绝",
                    }, ensure_ascii=False)

        # 检查是否有需要用户输入的参数
        user_input_params = [
            p for p in param_rows
            if p.param_source in ('user_input', 'user_credential')
        ]

        # 如果有需要用户输入的参数，且调用时没有提供这些参数
        if user_input_params:
            missing_params = []
            for p in user_input_params:
                if p.name not in params:
                    missing_params.append({
                        "key": p.name,
                        "label": p.label or p.name,
                        "type": "password" if p.param_source == "user_credential" else "text",
                        "required": p.required,
                        "description": p.description or "",
                    })

            if missing_params:
                # 阻塞等待用户输入（类似审批的 Future 模式）
                session_id = _current_session_id.get()
                logger.warning("UserInput: session=%s missing=%s", session_id, [m['key'] for m in missing_params])
                if session_id:
                    payload = {
                        "type": "user_input_required",
                        "api_name": api_name,
                        "api_display_name": api.display_name,
                        "system_name": system.name,
                        "fields": missing_params,
                        "message": f"需要输入以下参数才能调用 {api.display_name}：",
                    }
                    user_input = await UserInputBlocker.request_input(session_id, payload)
                    logger.warning("UserInput: resolved values=%s", {k:v for k,v in (user_input or {}).items() if k!='password'})
                    if user_input:
                        params = dict(params)
                        params.update(user_input)
                        logger.warning("UserInput received: %s", {k: v for k, v in user_input.items() if k != 'password'})
                else:
                    return json.dumps({
                        "error": "内部错误：无法获取会话 ID",
                    }, ensure_ascii=False)

        # Look up user credential
        from app.db.session import create_db_session

        db = create_db_session()
        try:
            # 从 Redis 缓存获取最新配置；miss 则用注册时的 system 对象
            cached = await _cache_get(system.id)
            fresh_system = cached if cached else system

            cred = db.query(ExternalUserCredentialModel).filter_by(
                user_id=effective_user_id, system_id=system.id
            ).first()
            if not cred or cred.connection_status != "connected":
                # 回退到管理员设置的默认凭据
                if fresh_system.default_credential_data_encrypted:
                    cred = _build_default_credential(fresh_system)
                else:
                    return json.dumps({
                        "error": f"请先在集成市场连接 {fresh_system.name}",
                    }, ensure_ascii=False)

            # Separate params by type
            path_params: dict[str, Any] = {}
            query_params: dict[str, Any] = {}
            body_params: dict[str, Any] = {}

            param_defs = {p.name: p for p in param_rows}
            for name, value in params.items():
                pdef = param_defs.get(name)
                if pdef is None:
                    continue
                casted = _cast_value(value, pdef.data_type)
                if pdef.param_type == "path":
                    path_params[name] = casted
                elif pdef.param_type == "query":
                    query_params[name] = casted
                elif pdef.param_type == "body":
                    body_params[name] = casted

            # 路径参数兜底：未提供时用 default_value 填充
            for p in param_rows:
                if p.param_type == "path" and p.name not in path_params and p.default_value:
                    path_params[p.name] = p.default_value

            # 解析 base_url（支持逗号分隔的多地址 HA）
            base_urls = [u.strip().rstrip("/") for u in fresh_system.base_url.split(",") if u.strip()]

            body: Any = None
            if body_params:
                if len(body_params) == 1 and "body" in body_params and isinstance(body_params["body"], (dict, list)):
                    body = body_params["body"]
                elif api.body_wrapper_key:
                    body = {api.body_wrapper_key: body_params}
                else:
                    body = body_params

            headers = _serialize_headers(fresh_system.headers_json)

            # HA 故障转移：依次尝试每个地址
            response = None
            last_error = None
            for base in base_urls:
                url = base + _resolve_path(api.path, path_params)
                logger.warning("API call: %s %s, params=%s, body=%s", api.method, url,
                             {k: v for k, v in params.items() if k != 'password'},
                             {k: v for k, v in (body_params if isinstance(body_params, dict) else {}).items() if k != 'password'})
                try:
                    async with httpx.AsyncClient(timeout=api.timeout_seconds, follow_redirects=True) as client:
                        request = client.build_request(
                            method=api.method,
                            url=url,
                            params=query_params or None,
                            json=body,
                            headers=headers,
                        )
                        await AuthInjector.inject(fresh_system, cred, request)
                        await SecurityProcessor.process_request(system, request)
                        response = await client.send(request)

                    # 检查是否 Standby 节点（HDFS/YARN 常见）
                    if response.status_code == 503 or (
                        response.status_code == 403 and "standby" in response.text.lower()
                    ):
                        logger.info("HA failover: %s is standby, trying next", base)
                        last_error = f"{base} 是 Standby 节点"
                        response = None
                        continue
                    break  # 成功，跳出循环
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                    logger.info("HA failover: %s unreachable (%s), trying next", base, exc)
                    last_error = f"{base} 不可达: {exc}"
                    response = None
                    continue

            if response is None:
                return json.dumps({
                    "error": f"所有地址均不可用: {last_error}",
                    "tried": base_urls,
                }, ensure_ascii=False)

            # Mark auth errors
            if response.status_code in (401, 403):
                cred.connection_status = "auth_error"
                db.commit()
                return json.dumps({
                    "error": f"{fresh_system.name} 凭据无效（HTTP {response.status_code}），请重新连接",
                    "status_code": response.status_code,
                }, ensure_ascii=False)

            # Decrypt response if configured
            body_text = await SecurityProcessor.process_response(fresh_system, response.text)
            result: dict[str, Any] = {
                "status_code": response.status_code,
                "body": body_text,
            }
            return json.dumps(result, ensure_ascii=False)

        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"请求失败: {e}"}, ensure_ascii=False)
        finally:
            db.close()

    return handler


def register_external_tools(registry, system_ids: list[int], db: Session) -> list[str]:
    """Register one wuwei tool per external system.

    Each tool's description lists available APIs. The handler dispatches by api_name.
    Returns list of system names that were successfully registered.
    """
    user_id = get_ext_user_id()
    if not user_id:
        return []

    registered_systems: list[str] = []

    systems = db.execute(
        select(ExternalSystemModel).where(
            ExternalSystemModel.id.in_(system_ids),
            ExternalSystemModel.enabled.is_(True),
        )
    ).scalars().all()

    for system in systems:
        # Populate Redis cache so handler uses latest config
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_cache_put(system))
        except RuntimeError:
            pass  # 无运行中事件循环时跳过（首次启动 seed 阶段）

        apis = list(db.execute(
            select(ExternalApiModel).where(
                ExternalApiModel.system_id == system.id,
                ExternalApiModel.enabled.is_(True),
            )
        ).scalars().all())

        if not apis:
            continue

        # Build api_name -> (api, params) map
        api_map: dict[str, tuple[ExternalApiModel, list[ExternalApiParamModel]]] = {}
        description_lines = [f"操作 {system.name}。可用操作:"]
        has_any_approval = False

        for api in apis:
            param_rows = list(db.execute(
                select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api.id)
            ).scalars().all())
            api_map[api.name] = (api, param_rows)

            # Build param description — 只告诉 LLM 需要它提取的参数
            param_descs = []
            for p in param_rows:
                req = "*" if p.required else ""
                if p.param_source == 'llm_extract':
                    param_descs.append(f"{p.name}{req}({p.data_type})")
                elif p.param_source in ('static', 'user_input', 'user_credential'):
                    pass  # LLM 无需关心
                else:
                    param_descs.append(f"{p.name}{req}({p.data_type})")
            param_str = ", ".join(param_descs) if param_descs else "无参数"
            desc_line = f"- {api.name}({param_str}) — {api.display_name}: {api.description}"
            description_lines.append(desc_line)
            if api.requires_approval:
                has_any_approval = True

        tool_name = _safe_name(system.name)
        description = "\n".join(description_lines)

        # Schema: api_name (required) + params (optional object)
        schema = {
            "type": "object",
            "properties": {
                "api_name": {
                    "type": "string",
                    "description": f"要执行的操作名称，可选值: {', '.join(api_map.keys())}",
                },
                "params": {
                    "type": "object",
                    "description": "操作的参数，key-value 形式。具体参数请参考工具描述。",
                },
            },
            "required": ["api_name"],
        }

        handler = _build_system_tool_handler(system, api_map, user_id)

        registry.tool(
            name=tool_name,
            display_name=f"{system.name} 集成",
            description=description,
            parameters=schema,
            requires_approval=has_any_approval,
            timeout_seconds=300,
        )(handler)

        registered_systems.append(system.name)
        logger.info("Registered system tool: %s (%d APIs)", tool_name, len(api_map))

    return registered_systems


# ── CRUD Service ────────────────────────────────────────────────────────────


class ExternalSystemService:
    def __init__(self, db: Session):
        self.db = db

    # ── systems ──

    def list_systems(self) -> list[dict]:
        systems = list(self.db.execute(select(ExternalSystemModel)).scalars().all())
        counts: dict[int, int] = {}
        for row in self.db.execute(select(ExternalApiModel.system_id, ExternalApiModel.id)).all():
            counts[row[0]] = counts.get(row[0], 0) + 1
        return [_serialize_system(s, counts.get(s.id, 0)) for s in systems]

    def list_published_systems(self, user_id: int | None = None) -> list[dict]:
        from app.db.models import UserInstalledAgentModel, AgentProfileExternalSystemModel

        conditions = [
            ExternalSystemModel.published.is_(True),
            ExternalSystemModel.enabled.is_(True),
        ]

        if user_id is not None:
            # 只显示用户安装的智能体关联的集成
            installed_profile_ids = self.db.execute(
                select(UserInstalledAgentModel.profile_id).where(
                    UserInstalledAgentModel.user_id == user_id
                )
            ).scalars().all()

            if installed_profile_ids:
                # 获取这些智能体关联的系统 ID
                linked_system_ids = self.db.execute(
                    select(AgentProfileExternalSystemModel.system_id).where(
                        AgentProfileExternalSystemModel.profile_id.in_(installed_profile_ids),
                        AgentProfileExternalSystemModel.enabled.is_(True),
                    )
                ).scalars().all()

                if linked_system_ids:
                    conditions.append(ExternalSystemModel.id.in_(linked_system_ids))
                else:
                    # 用户安装的智能体没有关联任何系统
                    return []
            else:
                # 用户没有安装任何智能体
                return []

        systems = list(self.db.execute(
            select(ExternalSystemModel).where(*conditions)
        ).scalars().all())
        counts: dict[int, int] = {}
        for row in self.db.execute(select(ExternalApiModel.system_id, ExternalApiModel.id)).all():
            counts[row[0]] = counts.get(row[0], 0) + 1
        return [_serialize_system(s, counts.get(s.id, 0)) for s in systems]

    def get_system(self, system_id: int) -> dict:
        sys = self.db.get(ExternalSystemModel, system_id)
        if not sys:
            raise KeyError(f"External system {system_id} not found")
        api_count = len(self.db.execute(
            select(ExternalApiModel.id).where(ExternalApiModel.system_id == system_id)
        ).all())
        return _serialize_system(sys, api_count)

    def create_system(self, data: ExternalSystemCreateRequest, user_id: int) -> dict:
        sys = ExternalSystemModel(
            name=data.name,
            description=data.description,
            base_url=data.base_url,
            auth_type=data.auth_type,
            credential_template_json=json.dumps(data.credential_template) if data.credential_template else "{}",
            oauth_client_id_encrypted=encrypt(data.oauth_client_id) if data.oauth_client_id else None,
            oauth_client_secret_encrypted=encrypt(data.oauth_client_secret) if data.oauth_client_secret else None,
            oauth_auth_url=data.oauth_auth_url,
            oauth_token_url=data.oauth_token_url,
            oauth_scope=data.oauth_scope,
            oauth_refresh_token_url=data.oauth_refresh_token_url,
            jwt_login_url=data.jwt_login_url,
            jwt_refresh_url=data.jwt_refresh_url,
            jwt_refresh_body_template=data.jwt_refresh_body_template,
            jwt_refresh_token_path=data.jwt_refresh_token_path,
            jwt_request_body_template=data.jwt_request_body_template,
            jwt_response_token_path=data.jwt_response_token_path,
            jwt_response_expires_path=data.jwt_response_expires_path,
            jwt_response_token_header=data.jwt_response_token_header,
            login_token_source=data.login_token_source,
            login_inject_mode=data.login_inject_mode,
            login_inject_header_name=data.login_inject_header_name,
            headers_json=json.dumps(data.headers) if data.headers else "{}",
            advanced_auth_json=json.dumps(data.advanced_auth) if data.advanced_auth else "{}",
            default_credential_data_encrypted=encrypt(json.dumps(data.default_credential_data)) if data.default_credential_data else None,
            created_by=user_id,
        )
        self.db.add(sys)
        self.db.commit()
        self.db.refresh(sys)
        return _serialize_system(sys)

    async def update_system(self, system_id: int, data: ExternalSystemUpdateRequest) -> dict:
        sys = self.db.get(ExternalSystemModel, system_id)
        if not sys:
            raise KeyError(f"External system {system_id} not found")

        if data.name is not None:
            sys.name = data.name
        if data.description is not None:
            sys.description = data.description
        if data.base_url is not None:
            sys.base_url = data.base_url
        if data.auth_type is not None:
            sys.auth_type = data.auth_type
        if data.credential_template is not None:
            sys.credential_template_json = json.dumps(data.credential_template)
        if data.oauth_client_id is not None:
            sys.oauth_client_id_encrypted = encrypt(data.oauth_client_id) if data.oauth_client_id else None
        if data.oauth_client_secret is not None:
            sys.oauth_client_secret_encrypted = encrypt(data.oauth_client_secret) if data.oauth_client_secret else None
        if data.oauth_auth_url is not None:
            sys.oauth_auth_url = data.oauth_auth_url
        if data.oauth_token_url is not None:
            sys.oauth_token_url = data.oauth_token_url
        if data.oauth_scope is not None:
            sys.oauth_scope = data.oauth_scope
        if data.oauth_refresh_token_url is not None:
            sys.oauth_refresh_token_url = data.oauth_refresh_token_url
        if data.jwt_login_url is not None:
            sys.jwt_login_url = data.jwt_login_url
        if data.jwt_refresh_url is not None:
            sys.jwt_refresh_url = data.jwt_refresh_url
        if data.jwt_refresh_body_template is not None:
            sys.jwt_refresh_body_template = data.jwt_refresh_body_template
        if data.jwt_refresh_token_path is not None:
            sys.jwt_refresh_token_path = data.jwt_refresh_token_path
        if data.jwt_request_body_template is not None:
            sys.jwt_request_body_template = data.jwt_request_body_template
        if data.jwt_response_token_path is not None:
            sys.jwt_response_token_path = data.jwt_response_token_path
        if data.jwt_response_expires_path is not None:
            sys.jwt_response_expires_path = data.jwt_response_expires_path
        if data.jwt_response_token_header is not None:
            sys.jwt_response_token_header = data.jwt_response_token_header
        if data.login_token_source is not None:
            sys.login_token_source = data.login_token_source
        if data.login_inject_mode is not None:
            sys.login_inject_mode = data.login_inject_mode
        if data.login_inject_header_name is not None:
            sys.login_inject_header_name = data.login_inject_header_name
        if data.published is not None:
            sys.published = data.published
        if data.headers is not None:
            sys.headers_json = json.dumps(data.headers)
        if data.advanced_auth is not None:
            sys.advanced_auth_json = json.dumps(data.advanced_auth)
        if data.enabled is not None:
            sys.enabled = data.enabled
        if data.default_credential_data is not None:
            sys.default_credential_data_encrypted = encrypt(json.dumps(data.default_credential_data)) if data.default_credential_data else None

        self.db.commit()
        self.db.refresh(sys)
        # 刷新 Redis 缓存，让运行中的 agent 工具立即使用新配置
        await refresh_system_cache(system_id)
        api_count = len(self.db.execute(
            select(ExternalApiModel.id).where(ExternalApiModel.system_id == system_id)
        ).all())
        return _serialize_system(sys, api_count)

    def delete_system(self, system_id: int) -> None:
        sys = self.db.get(ExternalSystemModel, system_id)
        if not sys:
            raise KeyError(f"External system {system_id} not found")
        # Delete APIs and params
        for api in self.db.execute(
            select(ExternalApiModel).where(ExternalApiModel.system_id == system_id)
        ).scalars().all():
            self.db.query(ExternalApiParamModel).filter(ExternalApiParamModel.api_id == api.id).delete()
        self.db.query(ExternalApiModel).filter(ExternalApiModel.system_id == system_id).delete()
        # Delete user credentials
        self.db.query(ExternalUserCredentialModel).filter(
            ExternalUserCredentialModel.system_id == system_id
        ).delete()
        # Delete profile associations
        self.db.query(AgentProfileExternalSystemModel).filter(
            AgentProfileExternalSystemModel.system_id == system_id
        ).delete()
        self.db.delete(sys)
        self.db.commit()

    # ── APIs ──

    def list_apis(self, system_id: int) -> list[dict]:
        apis = list(self.db.execute(
            select(ExternalApiModel).where(ExternalApiModel.system_id == system_id)
        ).scalars().all())
        result = []
        for api in apis:
            params = list(self.db.execute(
                select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api.id)
            ).scalars().all())
            result.append(_serialize_api(api, params))
        return result

    def get_api(self, api_id: int) -> dict:
        api = self.db.get(ExternalApiModel, api_id)
        if not api:
            raise KeyError(f"External API {api_id} not found")
        params = list(self.db.execute(
            select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api_id)
        ).scalars().all())
        return _serialize_api(api, params)

    def create_api(self, system_id: int, data: ExternalApiCreateRequest) -> dict:
        sys = self.db.get(ExternalSystemModel, system_id)
        if not sys:
            raise KeyError(f"External system {system_id} not found")

        api = ExternalApiModel(
            system_id=system_id,
            name=data.name,
            display_name=data.display_name,
            description=data.description,
            method=data.method,
            path=data.path,
            request_body_schema=data.request_body_schema,
            response_example=data.response_example,
            requires_approval=data.requires_approval,
            timeout_seconds=data.timeout_seconds,
            body_wrapper_key=data.body_wrapper_key,
        )
        self.db.add(api)
        self.db.flush()

        param_models = []
        for p in data.params:
            pm = ExternalApiParamModel(
                api_id=api.id,
                name=p.name,
                param_type=p.param_type,
                data_type=p.data_type,
                required=p.required,
                description=p.description,
                default_value=p.default_value,
                param_source=p.param_source,
                label=p.label,
            )
            self.db.add(pm)
            param_models.append(pm)

        self.db.commit()
        self.db.refresh(api)
        return _serialize_api(api, param_models)

    def update_api(self, api_id: int, data: ExternalApiUpdateRequest) -> dict:
        api = self.db.get(ExternalApiModel, api_id)
        if not api:
            raise KeyError(f"External API {api_id} not found")

        if data.name is not None:
            api.name = data.name
        if data.display_name is not None:
            api.display_name = data.display_name
        if data.description is not None:
            api.description = data.description
        if data.method is not None:
            api.method = data.method
        if data.path is not None:
            api.path = data.path
        if data.request_body_schema is not None:
            api.request_body_schema = data.request_body_schema
        if data.response_example is not None:
            api.response_example = data.response_example
        if data.requires_approval is not None:
            api.requires_approval = data.requires_approval
        if data.timeout_seconds is not None:
            api.timeout_seconds = data.timeout_seconds
        if data.body_wrapper_key is not None:
            api.body_wrapper_key = data.body_wrapper_key
        if data.enabled is not None:
            api.enabled = data.enabled

        if data.params is not None:
            self.db.query(ExternalApiParamModel).filter(ExternalApiParamModel.api_id == api_id).delete()
            for p in data.params:
                pm = ExternalApiParamModel(
                    api_id=api_id,
                    name=p.name,
                    param_type=p.param_type,
                    data_type=p.data_type,
                    required=p.required,
                    description=p.description,
                    default_value=p.default_value,
                    param_source=p.param_source,
                    label=p.label,
                )
                self.db.add(pm)

        self.db.commit()
        self.db.refresh(api)
        params = list(self.db.execute(
            select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api_id)
        ).scalars().all())
        return _serialize_api(api, params)

    def delete_api(self, api_id: int) -> None:
        api = self.db.get(ExternalApiModel, api_id)
        if not api:
            raise KeyError(f"External API {api_id} not found")
        self.db.query(ExternalApiParamModel).filter(ExternalApiParamModel.api_id == api_id).delete()
        self.db.delete(api)
        self.db.commit()

    # ── test call ──

    async def test_api_call(self, api_id: int, params: dict, credential_data: dict | None = None) -> ExternalApiTestResponse:
        api = self.db.get(ExternalApiModel, api_id)
        if not api:
            raise KeyError(f"External API {api_id} not found")
        system = self.db.get(ExternalSystemModel, api.system_id)
        if not system:
            raise KeyError(f"External system {api.system_id} not found")

        param_rows = list(self.db.execute(
            select(ExternalApiParamModel).where(ExternalApiParamModel.api_id == api_id)
        ).scalars().all())

        # Build a temporary handler for single-API test
        param_defs = {p.name: p for p in param_rows}
        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}
        body_params: dict[str, Any] = {}

        for name, value in params.items():
            pdef = param_defs.get(name)
            if pdef is None:
                continue
            casted = _cast_value(value, pdef.data_type)
            if pdef.param_type == "path":
                path_params[name] = casted
            elif pdef.param_type == "query":
                query_params[name] = casted
            elif pdef.param_type == "body":
                body_params[name] = casted

        url = system.base_url + _resolve_path(api.path, path_params)
        body: Any = None
        if body_params:
            if len(body_params) == 1 and "body" in body_params and isinstance(body_params["body"], (dict, list)):
                body = body_params["body"]
            else:
                body = body_params

        headers = _serialize_headers(system.headers_json)
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=api.timeout_seconds, follow_redirects=True) as client:
                request = client.build_request(
                    method=api.method, url=url,
                    params=query_params or None, json=body, headers=headers,
                )
                # Inject auth from provided credential_data (admin test mode)
                if credential_data:
                    cred_dict = credential_data
                    if system.auth_type == "api_key":
                        key = cred_dict.get("key", "")
                        inject_in = cred_dict.get("inject_in", "header")
                        header_name = cred_dict.get("header_name", "X-API-Key")
                        if inject_in == "query":
                            request.url = request.url.copy_merge_params({cred_dict.get("param_name", "api_key"): key})
                        else:
                            request.headers[header_name] = key
                    elif system.auth_type == "bearer":
                        request.headers["Authorization"] = f"Bearer {cred_dict.get('token', '')}"
                    elif system.auth_type == "basic":
                        encoded = base64.b64encode(f"{cred_dict.get('username', '')}:{cred_dict.get('password', '')}".encode()).decode()
                        request.headers["Authorization"] = f"Basic {encoded}"
                    elif system.auth_type == "custom":
                        for k, v in cred_dict.get("headers", {}).items():
                            request.headers[k] = str(v)
                elif system.auth_type == "oauth2":
                    # For OAuth2 test, use user connection if available
                    user_id = get_ext_user_id()
                    if user_id:
                        cred = self.db.query(ExternalUserCredentialModel).filter_by(
                            user_id=user_id, system_id=system.id
                        ).first()
                        if cred:
                            await AuthInjector.inject(system, cred, request)
                await SecurityProcessor.process_request(system, request)
                response = await client.send(request)

            elapsed = int((time.monotonic() - start) * 1000)
            body_text = await SecurityProcessor.process_response(system, response.text)
            return ExternalApiTestResponse(
                success=200 <= response.status_code < 300,
                status_code=response.status_code,
                body=body_text,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ExternalApiTestResponse(
                success=False, status_code=0, body=str(e), elapsed_ms=elapsed,
            )

    # ── user connections ──

    def connect_system(self, user_id: int, system_id: int, credential_data: dict) -> dict:
        sys = self.db.get(ExternalSystemModel, system_id)
        if not sys:
            raise KeyError(f"集成 {system_id} 不存在")
        if not sys.published or not sys.enabled:
            raise ValueError("该集成不可用")

        existing = self.db.query(ExternalUserCredentialModel).filter_by(
            user_id=user_id, system_id=system_id
        ).first()

        if existing:
            existing.credential_data_encrypted = encrypt(json.dumps(credential_data)) if credential_data else ""
            existing.connection_status = "connected"
            existing.last_checked_at = None
            self.db.commit()
            self.db.refresh(existing)
            return _serialize_connection(existing, sys.name)

        cred = ExternalUserCredentialModel(
            user_id=user_id,
            system_id=system_id,
            credential_data_encrypted=encrypt(json.dumps(credential_data)) if credential_data else "",
            connection_status="connected",
        )
        self.db.add(cred)
        self.db.commit()
        self.db.refresh(cred)
        return _serialize_connection(cred, sys.name)

    def disconnect_system(self, user_id: int, system_id: int) -> None:
        cred = self.db.query(ExternalUserCredentialModel).filter_by(
            user_id=user_id, system_id=system_id
        ).first()
        if cred:
            self.db.delete(cred)
            self.db.commit()

    def get_user_connection(self, user_id: int, system_id: int) -> dict | None:
        cred = self.db.query(ExternalUserCredentialModel).filter_by(
            user_id=user_id, system_id=system_id
        ).first()
        if not cred:
            return None
        sys = self.db.get(ExternalSystemModel, system_id)
        return _serialize_connection(cred, sys.name if sys else "")

    def list_user_connections(self, user_id: int) -> list[dict]:
        creds = self.db.query(ExternalUserCredentialModel).filter_by(user_id=user_id).all()
        result = []
        for cred in creds:
            sys = self.db.get(ExternalSystemModel, cred.system_id)
            if sys:
                result.append(_serialize_connection(cred, sys.name))
        return result

    def decrypt_credential_data(self, credential: ExternalUserCredentialModel) -> dict:
        """解密凭据数据，返回明文字典。

        用于凭据代理 API，供内部系统（如爬虫平台）安全获取用户凭据。
        """
        config_raw = decrypt_safe(credential.credential_data_encrypted, "{}")
        try:
            return json.loads(config_raw) if config_raw else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    # ── profile ↔ system association ──

    def list_profile_systems(self, profile_id: int) -> list[dict]:
        rows = list(self.db.execute(
            select(AgentProfileExternalSystemModel).where(
                AgentProfileExternalSystemModel.profile_id == profile_id
            )
        ).scalars().all())
        result = []
        for row in rows:
            sys = self.db.get(ExternalSystemModel, row.system_id)
            if sys:
                result.append({
                    "system_id": row.system_id,
                    "system_name": sys.name,
                    "enabled": row.enabled,
                })
        return result

    def apply_profile_systems(self, profile_id: int, system_refs: list[dict]) -> None:
        self.db.query(AgentProfileExternalSystemModel).filter(
            AgentProfileExternalSystemModel.profile_id == profile_id
        ).delete()
        for ref in system_refs:
            row = AgentProfileExternalSystemModel(
                profile_id=profile_id,
                system_id=ref["system_id"],
                enabled=ref.get("enabled", True),
            )
            self.db.add(row)
        self.db.commit()

    def get_enabled_system_ids(self, profile_id: int) -> list[int]:
        return list(self.db.execute(
            select(AgentProfileExternalSystemModel.system_id).where(
                AgentProfileExternalSystemModel.profile_id == profile_id,
                AgentProfileExternalSystemModel.enabled.is_(True),
            )
        ).scalars().all())

    # ── OpenAPI import ──

    @staticmethod
    async def parse_openapi(openapi_json=None, openapi_url=None):
        import re as _re
        if openapi_url:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(openapi_url)
                resp.raise_for_status()
                spec = resp.json()
        elif openapi_json:
            spec = json.loads(openapi_json)
        else:
            raise ValueError("Please provide OpenAPI JSON or URL")
        info = spec.get("info", {})
        system_name = info.get("title", "Imported API")
        system_description = info.get("description", "")
        base_url = ""
        if "servers" in spec and spec["servers"]:
            base_url = spec["servers"][0].get("url", "").rstrip("/")
        elif "host" in spec:
            scheme = (spec.get("schemes") or ["https"])[0]
            base_url = f"{scheme}://{spec['host']}{spec.get('basePath', '')}".rstrip("/")
        auth_type = "api_key"
        security_schemes = {}
        if "components" in spec:
            security_schemes = spec.get("components", {}).get("securitySchemes", {})
        elif "securityDefinitions" in spec:
            security_schemes = spec.get("securityDefinitions", {})
        if security_schemes:
            first_scheme = next(iter(security_schemes.values()), {})
            stype = first_scheme.get("type", "")
            if stype == "http" and first_scheme.get("scheme") == "bearer":
                auth_type = "bearer"
            elif stype == "http" and first_scheme.get("scheme") == "basic":
                auth_type = "basic"
            elif stype == "oauth2":
                auth_type = "oauth2"
        apis_list = []
        for path, path_item in spec.get("paths", {}).items():
            for method in ["get", "post", "put", "delete", "patch"]:
                operation = path_item.get(method)
                if not operation:
                    continue
                op_id = operation.get("operationId", "")
                if not op_id:
                    op_id = f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", "").strip("_")
                op_id = _re.sub(r"[^a-zA-Z0-9_]", "_", op_id).lower().strip("_")
                summary = operation.get("summary", "")
                description = operation.get("description", "")
                display_name = summary or op_id.replace("_", " ").title()
                params = []
                for p in operation.get("parameters", []):
                    param_in = p.get("in", "query")
                    schema = p.get("schema", {})
                    dt = schema.get("type", "string")
                    if dt not in ("string", "integer", "boolean", "object"):
                        dt = "string"
                    params.append({"name": p.get("name", ""), "param_type": "path" if param_in == "path" else "query", "data_type": dt, "required": p.get("required", False), "description": p.get("description", ""), "default_value": None})
                request_body = operation.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    json_content = content.get("application/json", {})
                    body_schema = json_content.get("schema", {})
                    if body_schema:
                        props = body_schema.get("properties", {})
                        req_fields = set(body_schema.get("required", []))
                        if props:
                            for pn, ps in props.items():
                                pt = ps.get("type", "string")
                                if pt not in ("string", "integer", "boolean", "object"):
                                    pt = "string"
                                params.append({"name": pn, "param_type": "body", "data_type": pt, "required": pn in req_fields, "description": ps.get("description", ""), "default_value": None})
                apis_list.append({"name": op_id, "display_name": display_name, "description": description or summary, "method": method.upper(), "path": path, "requires_approval": method in ("post", "put", "delete", "patch"), "timeout_seconds": 30, "params": params})
        return {"system_name": system_name, "system_description": system_description, "base_url": base_url, "auth_type": auth_type, "apis": apis_list}

    def import_from_openapi_preview(self, preview, user_id):
        system = ExternalSystemModel(name=preview["system_name"], description=preview["system_description"], base_url=preview["base_url"], auth_type=preview["auth_type"], credential_template_json="{}", published=True, headers_json="{}", created_by=user_id)
        self.db.add(system)
        self.db.flush()
        created = []
        for ad in preview["apis"]:
            api = ExternalApiModel(system_id=system.id, name=ad["name"], display_name=ad["display_name"], description=ad.get("description", ""), method=ad["method"], path=ad["path"], requires_approval=ad.get("requires_approval", False), timeout_seconds=ad.get("timeout_seconds", 30))
            self.db.add(api)
            self.db.flush()
            for p in ad.get("params", []):
                self.db.add(ExternalApiParamModel(api_id=api.id, name=p["name"], param_type=p["param_type"], data_type=p.get("data_type", "string"), required=p.get("required", False), description=p.get("description", ""), default_value=p.get("default_value"), param_source=p.get("param_source", "static"), label=p.get("label")))
            created.append(api)
        self.db.commit()
        self.db.refresh(system)
        return _serialize_system(system, len(created))


def seed_preset_external_systems() -> None:
    """Seed preset external systems on startup (idempotent).

    每次启动检查并添加缺失的预设，已存在的不会重复添加。
    """
    from app.db.session import create_db_session

    PRESETS = [
        {
            "name": "OpenSpider",
            "description": "OpenSpider 爬虫管理平台 - 爬虫生命周期管理、数据采集、定时调度",
            "category": "devops",
            "base_url": "http://localhost:8000",
            "auth_type": "jwt_login",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "OpenSpider 账户用户名"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "OpenSpider 账户密码"},
            ]},
            "jwt_login_url": "/auth/login/json",
            "jwt_refresh_url": "/auth/refresh",
            "jwt_request_body_template": '{"username": "{username}", "password": "{password}"}',
            "jwt_response_token_path": "access_token",
            "jwt_response_expires_path": "expires_in",
            "jwt_refresh_body_template": '{"refresh_token": "{refresh_token}"}',
            "apis": [
                {"name": "list_spiders", "display_name": "获取爬虫列表", "method": "GET", "path": "/spiders", "description": "列出当前用户可见的爬虫"},
                {"name": "get_spider", "display_name": "获取爬虫详情", "method": "GET", "path": "/spiders/{name}", "description": "获取单个爬虫的详细信息",
                 "params": [{"name": "name", "param_type": "path", "data_type": "string", "required": True, "description": "爬虫名称", "param_source": "llm_extract"}]},
                {"name": "start_spider", "display_name": "启动爬虫", "method": "POST", "path": "/spiders/{spider_id}/start", "description": "启动指定爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "stop_spider", "display_name": "停止爬虫", "method": "POST", "path": "/spiders/{spider_id}/stop", "description": "停止正在运行的爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "pause_spider", "display_name": "暂停爬虫", "method": "POST", "path": "/spiders/{spider_id}/pause", "description": "暂停爬虫，保留断点",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "resume_spider", "display_name": "恢复爬虫", "method": "POST", "path": "/spiders/{spider_id}/resume", "description": "从断点恢复爬虫运行",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "delete_spider", "display_name": "删除爬虫", "method": "DELETE", "path": "/spiders/{spider_id}", "description": "删除爬虫",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "upload_spider", "display_name": "上传爬虫文件", "method": "POST", "path": "/spiders/upload", "description": "上传 .py 爬虫文件，自动注册"},
                {"name": "list_tasks", "display_name": "获取任务列表", "method": "GET", "path": "/tasks", "description": "查询任务列表，支持按爬虫和状态筛选"},
                {"name": "get_task", "display_name": "获取任务详情", "method": "GET", "path": "/tasks/{task_id}", "description": "获取单个任务的详细信息",
                 "params": [{"name": "task_id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_task_logs", "display_name": "获取任务日志", "method": "GET", "path": "/tasks/{task_id}/logs", "description": "获取指定任务的运行日志",
                 "params": [{"name": "task_id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_spider_data", "display_name": "查询爬虫数据", "method": "GET", "path": "/spiders/{spider_id}/data", "description": "分页查询爬虫采集的数据",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "export_spider_data", "display_name": "导出爬虫数据", "method": "GET", "path": "/spiders/{spider_id}/export", "description": "导出爬虫数据，支持 JSON/JSONL/CSV",
                 "params": [{"name": "spider_id", "param_type": "path", "data_type": "integer", "required": True, "description": "爬虫 ID", "param_source": "llm_extract"}]},
                {"name": "list_schedules", "display_name": "获取调度列表", "method": "GET", "path": "/schedules", "description": "列出所有定时调度"},
                {"name": "create_schedule", "display_name": "创建调度", "method": "POST", "path": "/schedules", "description": "创建新的定时调度任务"},
                {"name": "update_schedule", "display_name": "修改调度", "method": "PUT", "path": "/schedules/{schedule_id}", "description": "修改调度的 cron 表达式和参数",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "delete_schedule", "display_name": "删除调度", "method": "DELETE", "path": "/schedules/{schedule_id}", "description": "删除定时调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "enable_schedule", "display_name": "启用调度", "method": "POST", "path": "/schedules/{schedule_id}/enable", "description": "启用已禁用的调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "disable_schedule", "display_name": "禁用调度", "method": "POST", "path": "/schedules/{schedule_id}/disable", "description": "禁用调度",
                 "params": [{"name": "schedule_id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
            ],
        },
        {
            "name": "Dinky",
            "description": "Dinky 实时计算平台 - 基于 Apache Flink 的数据开发、作业管理、运维监控。"
                           "通过 OpenAPI 提供 Flink 作业全生命周期管理能力。",
            "category": "compute",
            "base_url": "http://your-dinky-host:8888",
            "auth_type": "bearer",
            "credential_template": {"fields": [
                {"key": "token", "label": "API Token", "type": "password", "required": True,
                 "help_text": "在 Dinky 系统管理 → 令牌管理 中创建 API Token",
                 "help_url": "https://dinky.org.cn/docs/next/openapi/openapi_overview"},
            ]},
            "apis": [
                # ── 系统 ──
                {"name": "version", "display_name": "获取版本", "method": "GET", "path": "/openapi/version",
                 "description": "获取 Dinky 服务版本号"},
                # ── 任务提交与管理 ──
                {"name": "submit_task", "display_name": "提交任务", "method": "POST", "path": "/openapi/submitTask",
                 "description": "提交 Flink 任务到集群执行（支持 SQL 和 JAR）",
                 "params": [
                     {"name": "id", "param_type": "body", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "isOnline", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否上线（仅允许一个作业运行）", "param_source": "llm_extract"},
                     {"name": "savePointPath", "param_type": "body", "data_type": "string", "required": False, "description": "SavePoint 路径（从检查点恢复）", "param_source": "llm_extract"},
                     {"name": "variables", "param_type": "body", "data_type": "object", "required": False, "description": "变量键值对", "param_source": "llm_extract"},
                 ]},
                {"name": "restart_task", "display_name": "重启任务", "method": "GET", "path": "/openapi/restartTask",
                 "description": "从指定 SavePoint 路径重启 Flink 任务",
                 "params": [
                     {"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"},
                     {"name": "savePointPath", "param_type": "query", "data_type": "string", "required": False, "description": "SavePoint 路径", "param_source": "llm_extract"},
                 ]},
                {"name": "cancel_job", "display_name": "取消 Flink Job", "method": "GET", "path": "/openapi/cancel",
                 "description": "取消正在运行的 Flink 作业",
                 "params": [
                     {"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"},
                     {"name": "withSavePoint", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否携带 SavePoint，默认 false", "param_source": "llm_extract"},
                     {"name": "forceCancel", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否强制取消，默认 true", "param_source": "llm_extract"},
                 ]},
                # ── SQL 分析 ──
                {"name": "explain_sql", "display_name": "解释 SQL", "method": "POST", "path": "/openapi/explainSql",
                 "description": "解释 Flink SQL 语句的执行计划，不实际执行",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "databaseName", "param_type": "body", "data_type": "string", "required": False, "description": "数据库名称", "param_source": "llm_extract"},
                     {"name": "envId", "param_type": "body", "data_type": "integer", "required": False, "description": "环境 ID", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                     {"name": "variables", "param_type": "body", "data_type": "object", "required": False, "description": "变量键值对", "param_source": "llm_extract"},
                 ]},
                {"name": "get_job_plan", "display_name": "获取执行计划", "method": "POST", "path": "/openapi/getJobPlan",
                 "description": "获取 Flink 作业的执行计划（Job Graph）",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "parallelism", "param_type": "body", "data_type": "integer", "required": False, "description": "并行度", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                 ]},
                {"name": "get_stream_graph", "display_name": "获取 Stream Graph", "method": "POST", "path": "/openapi/getStreamGraph",
                 "description": "获取 Flink 作业的 StreamGraph DAG 图",
                 "params": [
                     {"name": "statement", "param_type": "body", "data_type": "string", "required": True, "description": "Flink SQL 语句", "param_source": "llm_extract"},
                     {"name": "clusterName", "param_type": "body", "data_type": "string", "required": False, "description": "集群实例名称", "param_source": "llm_extract"},
                     {"name": "parallelism", "param_type": "body", "data_type": "integer", "required": False, "description": "并行度", "param_source": "llm_extract"},
                     {"name": "fragment", "param_type": "body", "data_type": "boolean", "required": False, "description": "是否为片段模式", "param_source": "llm_extract"},
                 ]},
                {"name": "export_sql", "display_name": "导出 SQL", "method": "GET", "path": "/openapi/exportSql",
                 "description": "导出指定任务的 Flink SQL 语句",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
                # ── SavePoint ──
                {"name": "savepoint", "display_name": "触发 Savepoint", "method": "POST", "path": "/openapi/savepoint",
                 "description": "为运行中的 Flink 作业触发 Savepoint（通过查询参数）",
                 "params": [
                     {"name": "taskId", "param_type": "query", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "savePointType", "param_type": "query", "data_type": "string", "required": True, "description": "SavePoint 类型：TRIGGER/STOP/CANCEL", "param_source": "llm_extract"},
                 ]},
                {"name": "savepoint_task", "display_name": "任务级 Savepoint", "method": "POST", "path": "/openapi/savepointTask",
                 "description": "以任务维度触发 Savepoint（通过请求体）",
                 "params": [
                     {"name": "taskId", "param_type": "body", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"},
                     {"name": "type", "param_type": "body", "data_type": "string", "required": False, "description": "SavePoint 类型：trigger/stop/cancel，默认 trigger", "param_source": "llm_extract"},
                 ]},
                # ── 作业实例 ──
                {"name": "get_job_instance", "display_name": "获取作业实例", "method": "GET", "path": "/openapi/getJobInstance",
                 "description": "根据 Job Instance ID 获取作业实例详情",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "Job Instance ID", "param_source": "llm_extract"}]},
                {"name": "get_job_instance_by_task_id", "display_name": "按任务查实例", "method": "GET", "path": "/openapi/getJobInstanceByTaskId",
                 "description": "根据任务 ID 获取作业实例详情",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "Dinky 任务 ID", "param_source": "llm_extract"}]},
                {"name": "get_job_instance_list", "display_name": "作业实例列表", "method": "POST", "path": "/openapi/getJobInstanceList",
                 "description": "分页查询作业实例列表（ProTable 格式）",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": False, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "current", "param_type": "body", "data_type": "integer", "required": False, "description": "当前页码", "param_source": "llm_extract"},
                 ]},
                # ── 血缘 ──
                {"name": "get_task_lineage", "display_name": "获取任务血缘", "method": "GET", "path": "/openapi/getTaskLineage",
                 "description": "获取指定任务的数据血缘关系",
                 "params": [{"name": "id", "param_type": "query", "data_type": "integer", "required": True, "description": "任务 ID", "param_source": "llm_extract"}]},
            ],
        },
        {
            "name": "DolphinScheduler",
            "category": "scheduler",
            "description": "Apache DolphinScheduler 分布式工作流调度平台。支持可视化 DAG 编排、30+ 任务类型、定时调度、运维监控。",
            "base_url": "http://your-ds-host:12345/dolphinscheduler",
            "auth_type": "api_key",
            "credential_template": {"fields": [
                {"key": "key", "label": "Token", "type": "password", "required": True,
                 "help_text": "在 DolphinScheduler 安全中心 → 令牌管理 中创建 API Token",
                 "help_url": "https://dolphinscheduler.apache.org/zh-cn/docs/latest/user_guide/token"},
                {"key": "header_name", "label": "Header 名称", "type": "text", "required": False, "placeholder": "token"},
            ]},
            "apis": [
                # ── 项目 ──
                {"name": "queryAllProjectList", "display_name": "获取项目列表", "method": "GET", "path": "/v2/projects/list",
                 "description": "获取所有项目列表"},
                {"name": "createProject", "display_name": "创建项目", "method": "POST", "path": "/v2/projects",
                 "description": "创建新项目",
                 "params": [
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": True, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "项目描述", "param_source": "llm_extract"},
                 ]},
                {"name": "queryProjectByCode", "display_name": "获取项目详情", "method": "GET", "path": "/v2/projects/{code}",
                 "description": "根据项目 Code 获取项目详情",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"}]},
                {"name": "updateProject", "display_name": "更新项目", "method": "PUT", "path": "/v2/projects/{code}",
                 "description": "更新项目信息",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": True, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "项目描述", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteProject", "display_name": "删除项目", "method": "DELETE", "path": "/v2/projects/{code}",
                 "description": "删除指定项目",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"}]},
                # ── 工作流 ──
                {"name": "filterWorkflows", "display_name": "搜索工作流", "method": "POST", "path": "/v2/workflows/query",
                 "description": "按条件搜索/过滤工作流定义",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "workflowName", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                 ]},
                {"name": "createWorkflow", "display_name": "创建工作流", "method": "POST", "path": "/v2/workflows",
                 "description": "创建新的工作流定义",
                 "params": [
                     {"name": "name", "param_type": "body", "data_type": "string", "required": True, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "projectCode", "param_type": "body", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "描述", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE，默认 OFFLINE", "param_source": "llm_extract"},
                     {"name": "executionType", "param_type": "body", "data_type": "string", "required": False, "description": "执行类型：PARALLEL/SERIAL_WAIT/SERIAL_DISCARD/SERIAL_PRIORITY", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                 ]},
                {"name": "getWorkflow", "display_name": "获取工作流详情", "method": "GET", "path": "/v2/workflows/{code}",
                 "description": "获取工作流定义详情（含任务节点）",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"}]},
                {"name": "updateWorkflow", "display_name": "更新工作流", "method": "PUT", "path": "/v2/workflows/{code}",
                 "description": "更新工作流定义",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "描述", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                     {"name": "executionType", "param_type": "body", "data_type": "string", "required": False, "description": "执行类型：PARALLEL/SERIAL_WAIT/SERIAL_DISCARD/SERIAL_PRIORITY", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteWorkflow", "display_name": "删除工作流", "method": "DELETE", "path": "/v2/workflows/{code}",
                 "description": "删除工作流定义",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"}]},
                # ── 流程实例 ──
                {"name": "queryWorkflowInstanceListPaging", "display_name": "查询流程实例", "method": "GET", "path": "/v2/workflow-instances",
                 "description": "分页查询工作流执行实例列表",
                 "params": [
                     {"name": "searchVal", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "query", "data_type": "integer", "required": False, "description": "页码，默认 1", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "query", "data_type": "integer", "required": False, "description": "每页大小，默认 10", "param_source": "llm_extract"},
                     {"name": "stateType", "param_type": "query", "data_type": "string", "required": False, "description": "状态类型：SUCCESS/FAILURE/STOP/KILL 等", "param_source": "llm_extract"},
                     {"name": "startDate", "param_type": "query", "data_type": "string", "required": False, "description": "开始日期（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "endDate", "param_type": "query", "data_type": "string", "required": False, "description": "结束日期（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                 ]},
                {"name": "queryWorkflowInstanceById", "display_name": "获取实例详情", "method": "GET", "path": "/v2/workflow-instances/{workflowInstanceId}",
                 "description": "获取工作流实例的详细信息",
                 "params": [{"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"}]},
                {"name": "execute", "display_name": "执行操作", "method": "POST", "path": "/v2/workflow-instances/{workflowInstanceId}/execute/{executeType}",
                 "description": "对流程实例执行操作",
                 "params": [
                     {"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"},
                     {"name": "executeType", "param_type": "path", "data_type": "string", "required": True, "description": "执行类型：NONE/REPEAT_RUNNING/RECOVER_SUSPENDED_PROCESS/START_FAILURE_TASK_PROCESS/STOP/PAUSE/EXECUTE_TASK", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteWorkflowInstance", "display_name": "删除实例", "method": "DELETE", "path": "/v2/workflow-instances/{workflowInstanceId}",
                 "description": "删除工作流执行实例",
                 "params": [{"name": "workflowInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "流程实例 ID", "param_source": "llm_extract"}]},
                # ── 任务定义 ──
                {"name": "filterTaskDefinition", "display_name": "搜索任务定义", "method": "POST", "path": "/v2/tasks/query",
                 "description": "按条件搜索/过滤任务定义",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": False, "description": "任务类型：SHELL/SQL/SPARK/FLINK 等", "param_source": "llm_extract"},
                 ]},
                {"name": "createTaskDefinition", "display_name": "创建任务", "method": "POST", "path": "/v2/tasks",
                 "description": "创建新的任务定义",
                 "params": [
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "所属工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": True, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": True, "description": "任务描述", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": True, "description": "任务类型：SHELL/SQL/SPARK/FLINK 等", "param_source": "llm_extract"},
                     {"name": "taskParams", "param_type": "body", "data_type": "string", "required": True, "description": "任务参数（JSON 字符串）", "param_source": "llm_extract"},
                     {"name": "flag", "param_type": "body", "data_type": "string", "required": False, "description": "是否启用：YES/NO，默认 YES", "param_source": "llm_extract"},
                     {"name": "taskPriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级：HIGHEST/HIGH/MEDIUM/LOW/LOWEST", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组，默认 default", "param_source": "llm_extract"},
                     {"name": "failRetryTimes", "param_type": "body", "data_type": "integer", "required": False, "description": "失败重试次数，默认 0", "param_source": "llm_extract"},
                     {"name": "failRetryInterval", "param_type": "body", "data_type": "integer", "required": False, "description": "重试间隔（分钟）", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                     {"name": "upstreamTasksCodes", "param_type": "body", "data_type": "string", "required": False, "description": "上游任务 Code（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "getTaskDefinition", "display_name": "获取任务详情", "method": "GET", "path": "/v2/tasks/{code}",
                 "description": "获取任务定义详情",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"}]},
                {"name": "updateTaskDefinition", "display_name": "更新任务", "method": "PUT", "path": "/v2/tasks/{code}",
                 "description": "更新任务定义",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"},
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "所属工作流 Code", "param_source": "llm_extract"},
                     {"name": "name", "param_type": "body", "data_type": "string", "required": False, "description": "任务名称", "param_source": "llm_extract"},
                     {"name": "description", "param_type": "body", "data_type": "string", "required": False, "description": "任务描述", "param_source": "llm_extract"},
                     {"name": "taskType", "param_type": "body", "data_type": "string", "required": False, "description": "任务类型", "param_source": "llm_extract"},
                     {"name": "taskParams", "param_type": "body", "data_type": "string", "required": False, "description": "任务参数（JSON 字符串）", "param_source": "llm_extract"},
                     {"name": "flag", "param_type": "body", "data_type": "string", "required": False, "description": "是否启用：YES/NO", "param_source": "llm_extract"},
                     {"name": "taskPriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                     {"name": "failRetryTimes", "param_type": "body", "data_type": "integer", "required": False, "description": "失败重试次数", "param_source": "llm_extract"},
                     {"name": "timeout", "param_type": "body", "data_type": "integer", "required": False, "description": "超时时间（秒）", "param_source": "llm_extract"},
                     {"name": "upstreamTasksCodes", "param_type": "body", "data_type": "string", "required": False, "description": "上游任务 Code（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteTaskDefinition", "display_name": "删除任务", "method": "DELETE", "path": "/v2/tasks/{code}",
                 "description": "删除任务定义",
                 "params": [{"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "任务 Code", "param_source": "llm_extract"}]},
                # ── 任务实例 ──
                {"name": "queryTaskListPaging", "display_name": "查询任务实例", "method": "GET", "path": "/v2/projects/{projectCode}/task-instances",
                 "description": "分页查询任务执行实例列表",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "searchVal", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "query", "data_type": "integer", "required": False, "description": "页码，默认 1", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "query", "data_type": "integer", "required": False, "description": "每页大小，默认 10", "param_source": "llm_extract"},
                     {"name": "stateType", "param_type": "query", "data_type": "string", "required": False, "description": "状态类型：SUCCESS/FAILURE/STOP 等", "param_source": "llm_extract"},
                     {"name": "taskName", "param_type": "query", "data_type": "string", "required": False, "description": "任务实例名", "param_source": "llm_extract"},
                     {"name": "startDate", "param_type": "query", "data_type": "string", "required": False, "description": "开始日期", "param_source": "llm_extract"},
                     {"name": "endDate", "param_type": "query", "data_type": "string", "required": False, "description": "结束日期", "param_source": "llm_extract"},
                 ]},
                {"name": "queryTaskInstanceByCode", "display_name": "获取任务实例详情", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{taskInstanceId}",
                 "description": "获取任务实例的详细信息",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "taskInstanceId", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "stopTask", "display_name": "停止任务实例", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/stop",
                 "description": "停止正在运行的任务实例",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "taskSavePoint", "display_name": "任务 Savepoint", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/savepoint",
                 "description": "为任务实例触发 Savepoint",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "forceTaskSuccess", "display_name": "强制成功", "method": "POST", "path": "/v2/projects/{projectCode}/task-instances/{id}/force-success",
                 "description": "强制将任务实例标记为成功",
                 "params": [
                     {"name": "projectCode", "param_type": "path", "data_type": "integer", "required": True, "description": "项目 Code", "param_source": "llm_extract"},
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "任务实例 ID", "param_source": "llm_extract"},
                 ]},
                # ── 调度 ──
                {"name": "filterSchedule", "display_name": "搜索定时调度", "method": "POST", "path": "/v2/schedules/filter",
                 "description": "按条件搜索定时调度配置",
                 "params": [
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "projectName", "param_type": "body", "data_type": "string", "required": False, "description": "项目名称", "param_source": "llm_extract"},
                     {"name": "processDefinitionName", "param_type": "body", "data_type": "string", "required": False, "description": "工作流名称", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                 ]},
                {"name": "createSchedule", "display_name": "创建调度", "method": "POST", "path": "/v2/schedules",
                 "description": "为工作流创建定时调度",
                 "params": [
                     {"name": "processDefinitionCode", "param_type": "body", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "crontab", "param_type": "body", "data_type": "string", "required": True, "description": "Cron 表达式（如 0 0 * * * ?）", "param_source": "llm_extract"},
                     {"name": "startTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效开始时间（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "endTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效结束时间（yyyy-MM-dd HH:mm:ss）", "param_source": "llm_extract"},
                     {"name": "timezoneId", "param_type": "body", "data_type": "string", "required": True, "description": "时区（如 Asia/Shanghai）", "param_source": "llm_extract"},
                     {"name": "failureStrategy", "param_type": "body", "data_type": "string", "required": False, "description": "失败策略：CONTINUE/END，默认 CONTINUE", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE，默认 OFFLINE", "param_source": "llm_extract"},
                     {"name": "warningType", "param_type": "body", "data_type": "string", "required": False, "description": "告警类型：NONE/SUCCESS/FAILURE/ALL", "param_source": "llm_extract"},
                     {"name": "processInstancePriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级：HIGHEST/HIGH/MEDIUM/LOW/LOWEST", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                     {"name": "tenantCode", "param_type": "body", "data_type": "string", "required": False, "description": "租户编码", "param_source": "llm_extract"},
                 ]},
                {"name": "getSchedule", "display_name": "获取调度详情", "method": "GET", "path": "/v2/schedules/{id}",
                 "description": "获取定时调度的详细配置",
                 "params": [{"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                {"name": "updateSchedule", "display_name": "更新调度", "method": "PUT", "path": "/v2/schedules/{id}",
                 "description": "更新定时调度配置",
                 "params": [
                     {"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"},
                     {"name": "crontab", "param_type": "body", "data_type": "string", "required": True, "description": "Cron 表达式", "param_source": "llm_extract"},
                     {"name": "startTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效开始时间", "param_source": "llm_extract"},
                     {"name": "endTime", "param_type": "body", "data_type": "string", "required": True, "description": "生效结束时间", "param_source": "llm_extract"},
                     {"name": "timezoneId", "param_type": "body", "data_type": "string", "required": True, "description": "时区", "param_source": "llm_extract"},
                     {"name": "failureStrategy", "param_type": "body", "data_type": "string", "required": False, "description": "失败策略：CONTINUE/END", "param_source": "llm_extract"},
                     {"name": "releaseState", "param_type": "body", "data_type": "string", "required": False, "description": "上线状态：ONLINE/OFFLINE", "param_source": "llm_extract"},
                     {"name": "warningType", "param_type": "body", "data_type": "string", "required": False, "description": "告警类型：NONE/SUCCESS/FAILURE/ALL", "param_source": "llm_extract"},
                     {"name": "processInstancePriority", "param_type": "body", "data_type": "string", "required": False, "description": "优先级", "param_source": "llm_extract"},
                     {"name": "workerGroup", "param_type": "body", "data_type": "string", "required": False, "description": "Worker 组", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteSchedule", "display_name": "删除调度", "method": "DELETE", "path": "/v2/schedules/{id}",
                 "description": "删除定时调度",
                 "params": [{"name": "id", "param_type": "path", "data_type": "integer", "required": True, "description": "调度 ID", "param_source": "llm_extract"}]},
                # ── 队列 ──
                {"name": "queryList", "display_name": "获取队列列表", "method": "GET", "path": "/v2/queues/list",
                 "description": "获取所有队列列表"},
                # ── 任务关系 ──
                {"name": "createTaskRelation", "display_name": "创建任务关系", "method": "POST", "path": "/v2/relations",
                 "description": "创建工作流中的任务依赖关系",
                 "params": [
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": True, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "preTaskCode", "param_type": "body", "data_type": "integer", "required": True, "description": "上游任务 Code", "param_source": "llm_extract"},
                     {"name": "postTaskCode", "param_type": "body", "data_type": "integer", "required": True, "description": "下游任务 Code", "param_source": "llm_extract"},
                     {"name": "projectCode", "param_type": "body", "data_type": "integer", "required": False, "description": "项目 Code", "param_source": "llm_extract"},
                 ]},
                {"name": "updateUpstreamTaskDefinition", "display_name": "更新上游依赖", "method": "PUT", "path": "/v2/relations/{code}",
                 "description": "更新任务的上游依赖关系",
                 "params": [
                     {"name": "code", "param_type": "path", "data_type": "integer", "required": True, "description": "下游任务 Code", "param_source": "llm_extract"},
                     {"name": "pageSize", "param_type": "body", "data_type": "integer", "required": True, "description": "每页大小", "param_source": "llm_extract"},
                     {"name": "pageNo", "param_type": "body", "data_type": "integer", "required": True, "description": "页码", "param_source": "llm_extract"},
                     {"name": "workflowCode", "param_type": "body", "data_type": "integer", "required": False, "description": "工作流 Code", "param_source": "llm_extract"},
                     {"name": "upstreams", "param_type": "body", "data_type": "string", "required": True, "description": "上游任务 Code 列表（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "deleteTaskRelation", "display_name": "删除任务关系", "method": "DELETE", "path": "/v2/relations/{code-pair}",
                 "description": "删除任务间的依赖关系",
                 "params": [{"name": "code-pair", "param_type": "path", "data_type": "string", "required": True, "description": "任务关系 Code 对", "param_source": "llm_extract"}]},
                # ── 统计 ──
                {"name": "queryWorkflowStatesCounts", "display_name": "工作流状态统计", "method": "GET", "path": "/v2/statistics/workflows/states/count",
                 "description": "查询所有工作流的状态统计"},
            ],
        },
        {
            "name": "Apache Doris FE",
            "category": "compute",
            "description": "Apache Doris Frontend HTTP API。提供集群管理、SQL 执行、查询分析、节点运维等能力。默认端口 8030。",
            "base_url": "http://your-fe-host:8030",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Doris FE 用户名（需在 fe.conf 中启用 enable_all_http_auth=true）"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Doris FE 密码"},
            ]},
            "apis": [
                # ── 集群概览 ──
                {"name": "health", "display_name": "健康检查", "method": "GET", "path": "/api/health",
                 "description": "检查 FE 健康状态，返回在线 BE 节点数"},
                {"name": "cluster_overview", "display_name": "集群概览", "method": "GET", "path": "/rest/v2/api/cluster_overview",
                 "description": "获取集群统计：数据库数、表数、BE 数、磁盘使用等"},
                {"name": "cluster_conn_info", "display_name": "连接信息", "method": "GET", "path": "/rest/v2/manager/cluster/cluster_info/conn_info",
                 "description": "获取集群 HTTP 和 MySQL 连接地址"},
                {"name": "fe_version", "display_name": "FE 版本", "method": "GET", "path": "/api/fe_version_info",
                 "description": "获取 FE 版本信息（构建版本、Git 哈希、构建时间）"},
                # ── 节点管理 ──
                {"name": "list_backends", "display_name": "BE 节点列表", "method": "GET", "path": "/api/backends",
                 "description": "获取所有 Backend 节点列表（IP、端口、状态）",
                 "params": [{"name": "is_alive", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 仅返回存活节点，默认 false 返回全部", "param_source": "llm_extract"}]},
                {"name": "list_frontends", "display_name": "FE 节点列表", "method": "GET", "path": "/rest/v2/manager/node/frontends",
                 "description": "获取所有 Frontend 节点列表"},
                {"name": "list_brokers", "display_name": "Broker 列表", "method": "GET", "path": "/rest/v2/manager/node/brokers",
                 "description": "获取所有 Broker 节点列表"},
                {"name": "node_list", "display_name": "节点总览", "method": "GET", "path": "/rest/v2/manager/node/node_list",
                 "description": "获取集群所有节点列表"},
                {"name": "operate_be", "display_name": "操作 BE 节点", "method": "POST", "path": "/rest/v2/manager/node/{action}/be",
                 "description": "添加/删除/下线 BE 节点（action: ADD/DROP/DECOMMISSION）",
                 "params": [{"name": "action", "param_type": "path", "data_type": "string", "required": True, "description": "操作类型：ADD/DROP/DECOMMISSION", "param_source": "llm_extract"}]},
                {"name": "operate_fe", "display_name": "操作 FE 节点", "method": "POST", "path": "/rest/v2/manager/node/{action}/fe",
                 "description": "添加/删除 FE 节点（action: ADD/DROP）",
                 "params": [{"name": "action", "param_type": "path", "data_type": "string", "required": True, "description": "操作类型：ADD/DROP", "param_source": "llm_extract"}]},
                # ── SQL 执行 ──
                {"name": "execute_sql", "display_name": "执行 SQL", "method": "POST", "path": "/api/query/{ns_name}/{db_name}",
                 "description": "执行 SQL 语句（SELECT/SHOW/INSERT 等），返回结果集或执行状态。"
                                "ns_name 通常为 default_cluster，db_name 为数据库名。"
                                "如果用户没指定数据库，可以用 information_schema。",
                 "params": [
                     {"name": "ns_name", "param_type": "path", "data_type": "string", "required": False, "description": "命名空间，默认 default_cluster", "param_source": "llm_extract", "default_value": "default_cluster"},
                     {"name": "db_name", "param_type": "path", "data_type": "string", "required": False, "description": "数据库名，默认 information_schema", "param_source": "llm_extract", "default_value": "information_schema"},
                     {"name": "stmt", "param_type": "body", "data_type": "string", "required": True, "description": "要执行的 SQL 语句", "param_source": "llm_extract"},
                 ]},
                # ── 查询分析 ──
                {"name": "current_queries", "display_name": "当前查询", "method": "GET", "path": "/rest/v2/manager/query/current_queries",
                 "description": "获取当前正在运行的查询列表",
                 "params": [{"name": "is_all_node", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否查询所有 FE 节点，默认 true", "param_source": "llm_extract"}]},
                {"name": "query_info", "display_name": "查询详情", "method": "GET", "path": "/rest/v2/manager/query/query_info",
                 "description": "获取查询信息，支持按 query_id 或关键字搜索",
                 "params": [
                     {"name": "query_id", "param_type": "query", "data_type": "string", "required": False, "description": "指定查询 ID", "param_source": "llm_extract"},
                     {"name": "search", "param_type": "query", "data_type": "string", "required": False, "description": "搜索关键字", "param_source": "llm_extract"},
                     {"name": "is_all_node", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否查询所有 FE，默认 true", "param_source": "llm_extract"},
                 ]},
                {"name": "query_sql", "display_name": "查询 SQL", "method": "GET", "path": "/rest/v2/manager/query/sql/{query_id}",
                 "description": "获取指定查询执行的 SQL 语句",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_profile_text", "display_name": "Profile 文本", "method": "GET", "path": "/rest/v2/manager/query/profile/text/{query_id}",
                 "description": "获取查询 Profile 文本格式（用于性能分析）",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_profile_graph", "display_name": "Profile 图", "method": "GET", "path": "/rest/v2/manager/query/profile/graph/{query_id}",
                 "description": "获取查询 Profile 图形化执行树",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "kill_query", "display_name": "取消查询", "method": "POST", "path": "/rest/v2/manager/query/kill/{query_id}",
                 "description": "取消正在执行的查询",
                 "params": [{"name": "query_id", "param_type": "path", "data_type": "string", "required": True, "description": "查询 ID", "param_source": "llm_extract"}]},
                {"name": "query_stats", "display_name": "查询统计", "method": "GET", "path": "/api/query_stats/{catalog_name}",
                 "description": "获取指定 Catalog 的查询统计信息",
                 "params": [
                     {"name": "catalog_name", "param_type": "path", "data_type": "string", "required": True, "description": "Catalog 名（Doris 内表用 default_cluster）", "param_source": "llm_extract"},
                     {"name": "summary", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 仅返回摘要，false 返回详细统计", "param_source": "llm_extract"},
                 ]},
                # ── 表与数据 ──
                {"name": "table_schema", "display_name": "表结构", "method": "GET", "path": "/api/{db}/{table}/_schema",
                 "description": "获取指定表的 Schema 信息（列名、类型等）",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "path", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                 ]},
                {"name": "get_ddl", "display_name": "获取 DDL", "method": "GET", "path": "/api/_get_ddl",
                 "description": "获取表的建表语句（DDL）",
                 "params": [
                     {"name": "db", "param_type": "query", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "query", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                 ]},
                {"name": "show_data", "display_name": "数据量", "method": "GET", "path": "/api/show_data",
                 "description": "获取数据库的数据量（字节）",
                 "params": [{"name": "db", "param_type": "query", "data_type": "string", "required": False, "description": "指定数据库名，不指定返回总量", "param_source": "llm_extract"}]},
                {"name": "show_table_data", "display_name": "表数据量", "method": "GET", "path": "/api/show_table_data",
                 "description": "获取各表的数据量（字节），支持按库/表筛选",
                 "params": [
                     {"name": "db", "param_type": "query", "data_type": "string", "required": False, "description": "指定数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "query", "data_type": "string", "required": False, "description": "指定表名", "param_source": "llm_extract"},
                     {"name": "single_replica", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否返回单副本数据量", "param_source": "llm_extract"},
                 ]},
                {"name": "query_plan", "display_name": "查询计划", "method": "POST", "path": "/api/{db}/{table}/_query_plan",
                 "description": "获取 SQL 语句的查询执行计划",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "table", "param_type": "path", "data_type": "string", "required": True, "description": "表名", "param_source": "llm_extract"},
                     {"name": "sql", "param_type": "body", "data_type": "string", "required": True, "description": "要分析的 SQL 语句", "param_source": "llm_extract"},
                 ]},
                # ── 加载任务 ──
                {"name": "load_info", "display_name": "加载任务详情", "method": "GET", "path": "/api/{db}/_load_info",
                 "description": "获取指定 Label 的数据加载任务详情",
                 "params": [
                     {"name": "db", "param_type": "path", "data_type": "string", "required": True, "description": "数据库名", "param_source": "llm_extract"},
                     {"name": "label", "param_type": "query", "data_type": "string", "required": True, "description": "加载任务 Label", "param_source": "llm_extract"},
                 ]},
                # ── 会话 ──
                {"name": "session_info", "display_name": "当前会话", "method": "GET", "path": "/rest/v1/session",
                 "description": "获取当前 FE 的会话信息"},
                {"name": "all_sessions", "display_name": "所有会话", "method": "GET", "path": "/rest/v1/session/all",
                 "description": "获取所有 FE 的会话信息"},
                {"name": "connection_info", "display_name": "连接详情", "method": "GET", "path": "/api/connection",
                 "description": "根据连接 ID 获取当前执行的查询 ID",
                 "params": [{"name": "connection_id", "param_type": "query", "data_type": "string", "required": True, "description": "连接 ID（通过 MySQL show processlist 获取）", "param_source": "llm_extract"}]},
                # ── 配置 ──
                {"name": "get_fe_config", "display_name": "FE 配置", "method": "GET", "path": "/rest/v1/config/fe/",
                 "description": "获取当前 FE 配置信息"},
                {"name": "set_config", "display_name": "修改配置", "method": "GET", "path": "/api/_set_config",
                 "description": "修改 FE 配置项（通过 query 参数传 key=value）",
                 "params": [
                     {"name": "persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否持久化，默认 false", "param_source": "llm_extract"},
                     {"name": "reset_persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否清除原有持久化配置，默认 true", "param_source": "llm_extract"},
                 ]},
                {"name": "get_config_info", "display_name": "节点配置", "method": "POST", "path": "/rest/v2/manager/node/configuration_info",
                 "description": "获取 FE/BE 节点的配置信息",
                 "params": [
                     {"name": "type", "param_type": "query", "data_type": "string", "required": True, "description": "节点类型：fe/be", "param_source": "llm_extract"},
                     {"name": "conf_name", "param_type": "body", "data_type": "string", "required": False, "description": "指定配置项名称列表", "param_source": "llm_extract"},
                     {"name": "node", "param_type": "body", "data_type": "string", "required": False, "description": "指定节点列表", "param_source": "llm_extract"},
                 ]},
                {"name": "set_fe_config_v2", "display_name": "修改 FE 配置", "method": "POST", "path": "/rest/v2/manager/node/set_config/fe",
                 "description": "批量修改 FE 节点配置（支持指定节点、持久化）"},
                {"name": "set_be_config", "display_name": "修改 BE 配置", "method": "POST", "path": "/rest/v2/manager/node/set_config/be",
                 "description": "批量修改 BE 节点配置"},
                # ── 运维 ──
                {"name": "runtime_info", "display_name": "运行时信息", "method": "GET", "path": "/api/show_runtime_info",
                 "description": "获取 FE JVM 运行时信息（内存、线程）"},
                {"name": "colocate_info", "display_name": "Colocate 信息", "method": "GET", "path": "/api/colocate",
                 "description": "获取 Colocate Group 信息（表亲和性分组）",
                 "params": [
                     {"name": "db_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定数据库 ID", "param_source": "llm_extract"},
                     {"name": "group_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定 Group ID", "param_source": "llm_extract"},
                 ]},
            ],
        },
        {
            "name": "Apache Doris BE",
            "category": "compute",
            "description": "Apache Doris Backend HTTP API。提供 Tablet 管理、Compaction、RPC 诊断、日志查看等运维能力。默认端口 8040。",
            "base_url": "http://your-be-host:8040",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": True, "help_text": "Doris BE 用户名（需在 be.conf 中启用 enable_all_http_auth=true）"},
                {"key": "password", "label": "密码", "type": "password", "required": True, "help_text": "Doris BE 密码"},
            ]},
            "apis": [
                # ── BE 节点管理 ──
                {"name": "be_health", "display_name": "BE 健康检查", "method": "GET", "path": "/api/health",
                 "description": "检查 BE 节点存活状态"},
                {"name": "be_version", "display_name": "BE 版本", "method": "GET", "path": "/api/be_version_info",
                 "description": "获取 BE 版本信息"},
                {"name": "be_config", "display_name": "BE 配置", "method": "GET", "path": "/api/show_config",
                 "description": "获取 BE 配置项列表"},
                {"name": "be_set_config", "display_name": "修改 BE 配置", "method": "POST", "path": "/api/update_config",
                 "description": "修改 BE 配置项（通过 query 参数传 key=value）",
                 "params": [
                     {"name": "persist", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否持久化，默认 false", "param_source": "llm_extract"},
                 ]},
                {"name": "be_metrics", "display_name": "BE 指标", "method": "GET", "path": "/metrics",
                 "description": "获取 BE 指标信息（兼容 Prometheus 格式）",
                 "params": [
                     {"name": "type", "param_type": "query", "data_type": "string", "required": False, "description": "输出格式：core（仅核心项）/json，默认 all", "param_source": "llm_extract"},
                     {"name": "with_tablet", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否输出 Tablet 相关指标，默认 false", "param_source": "llm_extract"},
                 ]},
                # ── Compaction ──
                {"name": "compaction_status", "display_name": "Compaction 状态", "method": "GET", "path": "/api/compaction/run_status",
                 "description": "查看 BE 节点整体 Compaction 状态",
                 "params": [{"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定 Tablet ID 查看单个 Tablet 状态", "param_source": "llm_extract"}]},
                {"name": "compaction_show", "display_name": "Tablet Compaction", "method": "GET", "path": "/api/compaction/show",
                 "description": "查看指定 Tablet 的 Compaction 状态",
                 "params": [{"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"}]},
                {"name": "compaction_run", "display_name": "触发 Compaction", "method": "POST", "path": "/api/compaction/run",
                 "description": "手动触发 Tablet Compaction",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": False, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "table_id", "param_type": "query", "data_type": "integer", "required": False, "description": "Table ID（compact_type=full 时有效）", "param_source": "llm_extract"},
                     {"name": "compact_type", "param_type": "query", "data_type": "string", "required": True, "description": "压缩类型：base/cumulative/full", "param_source": "llm_extract"},
                 ]},
                # ── Tablet 管理 ──
                {"name": "tablet_info", "display_name": "Tablet 信息", "method": "GET", "path": "/tablets_json",
                 "description": "获取 BE 上的 Tablet 列表",
                 "params": [{"name": "limit", "param_type": "query", "data_type": "string", "required": False, "description": "输出数量限制，默认 1000，all 输出全部", "param_source": "llm_extract"}]},
                {"name": "tablet_distribution", "display_name": "Tablet 分布", "method": "GET", "path": "/api/tablets_distribution",
                 "description": "查看 Tablet 在各磁盘间的分布情况",
                 "params": [
                     {"name": "group_by", "param_type": "query", "data_type": "string", "required": True, "description": "分组方式（仅支持 partition）", "param_source": "llm_extract"},
                     {"name": "partition_id", "param_type": "query", "data_type": "integer", "required": False, "description": "指定分区 ID，不指定返回全部", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_meta", "display_name": "Tablet 元数据", "method": "GET", "path": "/api/meta/header/{tablet_id}",
                 "description": "获取指定 Tablet 的元数据头信息",
                 "params": [{"name": "tablet_id", "param_type": "path", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"}]},
                {"name": "tablet_checksum", "display_name": "Tablet 校验", "method": "GET", "path": "/api/checksum",
                 "description": "计算 Tablet 的校验和",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "version", "param_type": "query", "data_type": "integer", "required": True, "description": "版本号", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_snapshot", "display_name": "创建快照", "method": "GET", "path": "/api/snapshot",
                 "description": "为 Tablet 创建快照",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_reload", "display_name": "重载 Tablet", "method": "GET", "path": "/api/reload_tablet",
                 "description": "重新加载 Tablet 数据",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "数据文件路径", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_restore", "display_name": "恢复 Tablet", "method": "POST", "path": "/api/restore_tablet",
                 "description": "从回收站恢复 Tablet 数据",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                 ]},
                {"name": "tablet_migration", "display_name": "Tablet 迁移", "method": "GET", "path": "/api/tablet_migration",
                 "description": "提交或查看 Tablet 迁移任务",
                 "params": [
                     {"name": "goal", "param_type": "query", "data_type": "string", "required": True, "description": "操作：run（提交迁移）/status（查看状态）", "param_source": "llm_extract"},
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "schema_hash", "param_type": "query", "data_type": "integer", "required": True, "description": "Schema Hash", "param_source": "llm_extract"},
                     {"name": "disk", "param_type": "query", "data_type": "string", "required": True, "description": "目标磁盘路径", "param_source": "llm_extract"},
                 ]},
                {"name": "check_segment_lost", "display_name": "Segment 检查", "method": "GET", "path": "/api/check_tablet_segment_lost",
                 "description": "检查所有丢失 Segment 的 Tablet",
                 "params": [{"name": "repair", "param_type": "query", "data_type": "boolean", "required": False, "description": "true 将异常 Tablet 设为 SHUTDOWN 以便 FE 自动修复，false 仅返回列表", "param_source": "llm_extract"}]},
                {"name": "pad_rowset", "display_name": "补齐 Rowset", "method": "POST", "path": "/api/pad_rowset",
                 "description": "为空缺版本补齐空 Rowset（修复副本异常）",
                 "params": [
                     {"name": "tablet_id", "param_type": "query", "data_type": "integer", "required": True, "description": "Tablet ID", "param_source": "llm_extract"},
                     {"name": "start_version", "param_type": "query", "data_type": "integer", "required": True, "description": "起始版本", "param_source": "llm_extract"},
                     {"name": "end_version", "param_type": "query", "data_type": "integer", "required": True, "description": "结束版本", "param_source": "llm_extract"},
                 ]},
                # ── RPC ──
                {"name": "check_rpc", "display_name": "检查 RPC 通道", "method": "GET", "path": "/api/check_rpc_channel/{host}/{port}/{size}",
                 "description": "检查与指定节点的 RPC 连接缓存是否可用",
                 "params": [
                     {"name": "host", "param_type": "path", "data_type": "string", "required": True, "description": "目标主机", "param_source": "llm_extract"},
                     {"name": "port", "param_type": "path", "data_type": "integer", "required": True, "description": "BRPC 端口", "param_source": "llm_extract"},
                     {"name": "size", "param_type": "path", "data_type": "integer", "required": True, "description": "负载大小（字节，1~1024000）", "param_source": "llm_extract"},
                 ]},
                {"name": "reset_rpc", "display_name": "重置 RPC 缓存", "method": "GET", "path": "/api/reset_rpc_channel/{endpoints}",
                 "description": "重置 BRPC 连接缓存（all 或指定 endpoint 列表）",
                 "params": [{"name": "endpoints", "param_type": "path", "data_type": "string", "required": True, "description": "all 或 host1:port1,host2:port2", "param_source": "llm_extract"}]},
                # ── 日志 ──
                {"name": "load_error_log", "display_name": "加载错误日志", "method": "GET", "path": "/api/_load_error_log",
                 "description": "下载数据加载错误日志",
                 "params": [
                     {"name": "file", "param_type": "query", "data_type": "string", "required": True, "description": "日志文件路径", "param_source": "llm_extract"},
                     {"name": "token", "param_type": "query", "data_type": "string", "required": True, "description": "认证令牌", "param_source": "llm_extract"},
                 ]},
                {"name": "adjust_vlog", "display_name": "调整 VLOG 级别", "method": "POST", "path": "/api/glog/adjust",
                 "description": "动态调整 BE 模块的 VLOG 日志级别",
                 "params": [
                     {"name": "module", "param_type": "query", "data_type": "string", "required": True, "description": "模块名（对应 BE 无后缀文件名）", "param_source": "llm_extract"},
                     {"name": "level", "param_type": "query", "data_type": "integer", "required": True, "description": "VLOG 级别（1~10，-1 关闭）", "param_source": "llm_extract"},
                 ]},
            ],
        },
        {
            "name": "HDFS",
            "category": "storage",
            "description": "Hadoop 分布式文件系统。通过 WebHDFS REST API 提供文件的浏览、读取、写入、删除等操作。"
                           "默认端口 9870（NameNode Web UI）。",
            "base_url": "http://your-namenode:9870",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "HDFS 用户", "type": "text", "required": True,
                 "help_text": "HDFS 操作用户名（如 hdfs、hive 等）",
                 "help_url": "https://hadoop.apache.org/docs/r3.4.2/hadoop-project-dist/hadoop-hdfs/WebHDFS.html"},
            ]},
            "apis": [
                # ── 文件读写 ──
                {"name": "open", "display_name": "读取文件", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "读取文件内容（重定向到 DataNode）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：OPEN", "param_source": "static", "default_value": "OPEN"},
                     {"name": "offset", "param_type": "query", "data_type": "integer", "required": False, "description": "起始字节位置", "param_source": "llm_extract"},
                     {"name": "length", "param_type": "query", "data_type": "integer", "required": False, "description": "读取字节数", "param_source": "llm_extract"},
                 ]},
                {"name": "create", "display_name": "创建文件", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "创建并写入文件（两步式：先获取 DataNode 地址，再上传数据）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CREATE", "param_source": "static", "default_value": "CREATE"},
                     {"name": "overwrite", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否覆盖已有文件", "param_source": "llm_extract"},
                     {"name": "replication", "param_type": "query", "data_type": "integer", "required": False, "description": "副本数", "param_source": "llm_extract"},
                     {"name": "blocksize", "param_type": "query", "data_type": "integer", "required": False, "description": "块大小（字节）", "param_source": "llm_extract"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": False, "description": "权限（如 644）", "param_source": "llm_extract"},
                 ]},
                {"name": "append", "display_name": "追加内容", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "向文件追加数据（两步式）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：APPEND", "param_source": "static", "default_value": "APPEND"},
                 ]},
                {"name": "concat", "display_name": "合并文件", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "将多个源文件合并到目标文件",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目标文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CONCAT", "param_source": "static", "default_value": "CONCAT"},
                     {"name": "sources", "param_type": "query", "data_type": "string", "required": True, "description": "源文件路径（逗号分隔）", "param_source": "llm_extract"},
                 ]},
                {"name": "truncate", "display_name": "截断文件", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "将文件截断到指定长度",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：TRUNCATE", "param_source": "static", "default_value": "TRUNCATE"},
                     {"name": "newlength", "param_type": "query", "data_type": "integer", "required": True, "description": "截断后的长度（字节）", "param_source": "llm_extract"},
                 ]},
                # ── 目录操作 ──
                {"name": "mkdirs", "display_name": "创建目录", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "创建目录（支持递归创建）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：MKDIRS", "param_source": "static", "default_value": "MKDIRS"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": False, "description": "权限（默认 755）", "param_source": "llm_extract"},
                 ]},
                {"name": "rename", "display_name": "重命名", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "重命名文件或目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "原路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：RENAME", "param_source": "static", "default_value": "RENAME"},
                     {"name": "destination", "param_type": "query", "data_type": "string", "required": True, "description": "新路径", "param_source": "llm_extract"},
                 ]},
                {"name": "delete", "display_name": "删除", "method": "DELETE", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件或目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DELETE", "param_source": "static", "default_value": "DELETE"},
                     {"name": "recursive", "param_type": "query", "data_type": "boolean", "required": False, "description": "是否递归删除", "param_source": "llm_extract"},
                 ]},
                # ── 文件/目录信息 ──
                {"name": "list_status", "display_name": "列出目录", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "列出目录下的文件和子目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTSTATUS", "param_source": "static", "default_value": "LISTSTATUS"},
                 ]},
                {"name": "file_status", "display_name": "文件状态", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的元信息（类型、大小、副本数、权限等）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILESTATUS", "param_source": "static", "default_value": "GETFILESTATUS"},
                 ]},
                {"name": "content_summary", "display_name": "目录汇总", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录汇总信息（总大小、文件数、目录数）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETCONTENTSUMMARY", "param_source": "static", "default_value": "GETCONTENTSUMMARY"},
                 ]},
                {"name": "file_checksum", "display_name": "文件校验", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件校验和",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILECHECKSUM", "param_source": "static", "default_value": "GETFILECHECKSUM"},
                 ]},
                {"name": "fs_status", "display_name": "文件系统状态", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取文件系统状态（已用/剩余/总容量）",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSTATUS", "param_source": "static", "default_value": "GETSTATUS"},
                 ]},
                {"name": "home_directory", "display_name": "用户主目录", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取当前用户的主目录",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETHOMEDIRECTORY", "param_source": "static", "default_value": "GETHOMEDIRECTORY"},
                 ]},
                # ── 权限管理 ──
                {"name": "set_permission", "display_name": "设置权限", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录权限",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETPERMISSION", "param_source": "static", "default_value": "SETPERMISSION"},
                     {"name": "permission", "param_type": "query", "data_type": "string", "required": True, "description": "权限（如 755、777）", "param_source": "llm_extract"},
                 ]},
                {"name": "set_owner", "display_name": "设置所有者", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的所有者和组",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETOWNER", "param_source": "static", "default_value": "SETOWNER"},
                     {"name": "owner", "param_type": "query", "data_type": "string", "required": False, "description": "新所有者", "param_source": "llm_extract"},
                     {"name": "group", "param_type": "query", "data_type": "string", "required": False, "description": "新组", "param_source": "llm_extract"},
                 ]},
                {"name": "set_replication", "display_name": "设置副本数", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件的副本因子",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETREPLICATION", "param_source": "static", "default_value": "SETREPLICATION"},
                     {"name": "replication", "param_type": "query", "data_type": "integer", "required": True, "description": "副本数", "param_source": "llm_extract"},
                 ]},
                # ── 存储策略 ──
                {"name": "all_storage_policies", "display_name": "所有存储策略", "method": "GET", "path": "/webhdfs/v1",
                 "description": "获取所有存储策略（COLD/WARM/HOT/ONE_SSD/ALL_SSD 等）",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETALLSTORAGEPOLICY", "param_source": "static", "default_value": "GETALLSTORAGEPOLICY"},
                 ]},
                {"name": "set_storage_policy", "display_name": "设置存储策略", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的存储策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETSTORAGEPOLICY", "param_source": "static", "default_value": "SETSTORAGEPOLICY"},
                     {"name": "storagepolicy", "param_type": "query", "data_type": "string", "required": True, "description": "策略名（如 HOT、COLD）", "param_source": "llm_extract"},
                 ]},
                # ── 快照 ──
                {"name": "create_snapshot", "display_name": "创建快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "为目录创建快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CREATESNAPSHOT", "param_source": "static", "default_value": "CREATESNAPSHOT"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": False, "description": "快照名称", "param_source": "llm_extract"},
                 ]},
                {"name": "delete_snapshot", "display_name": "删除快照", "method": "DELETE", "path": "/webhdfs/v1/{path}",
                 "description": "删除目录的指定快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DELETESNAPSHOT", "param_source": "static", "default_value": "DELETESNAPSHOT"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "快照名称", "param_source": "llm_extract"},
                 ]},
                {"name": "snapshot_diff", "display_name": "快照差异", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取两个快照之间的差异",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTDIFF", "param_source": "static", "default_value": "GETSNAPSHOTDIFF"},
                     {"name": "oldsnapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "源快照名", "param_source": "llm_extract"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "目标快照名", "param_source": "llm_extract"},
                 ]},
                {"name": "list_status_batch", "display_name": "分页列目录", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "分页列出目录内容（适合大目录）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTSTATUS_BATCH", "param_source": "static", "default_value": "LISTSTATUS_BATCH"},
                     {"name": "startAfter", "param_type": "query", "data_type": "string", "required": False, "description": "上一批最后一条的 pathSuffix", "param_source": "llm_extract"},
                 ]},
                {"name": "quota_usage", "display_name": "配额使用", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的配额使用情况",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETQUOTAUSAGE", "param_source": "static", "default_value": "GETQUOTAUSAGE"},
                 ]},
                {"name": "set_quota", "display_name": "设置配额", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置目录的命名空间和存储空间配额",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETQUOTA", "param_source": "static", "default_value": "SETQUOTA"},
                     {"name": "namespacequota", "param_type": "query", "data_type": "integer", "required": True, "description": "命名空间配额", "param_source": "llm_extract"},
                     {"name": "storagespacequota", "param_type": "query", "data_type": "integer", "required": False, "description": "存储空间配额", "param_source": "llm_extract"},
                 ]},
                {"name": "trash_root", "display_name": "回收站路径", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取指定路径的回收站根目录",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETTRASHROOT", "param_source": "static", "default_value": "GETTRASHROOT"},
                 ]},
                {"name": "set_times", "display_name": "设置时间", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的访问和修改时间",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETTIMES", "param_source": "static", "default_value": "SETTIMES"},
                     {"name": "modificationtime", "param_type": "query", "data_type": "integer", "required": False, "description": "修改时间（毫秒）", "param_source": "llm_extract"},
                     {"name": "accesstime", "param_type": "query", "data_type": "integer", "required": False, "description": "访问时间（毫秒）", "param_source": "llm_extract"},
                 ]},
                # ── ACL ──
                {"name": "set_acl", "display_name": "设置 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "替换整个 ACL",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETACL", "param_source": "static", "default_value": "SETACL"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "get_acl_status", "display_name": "获取 ACL", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的 ACL 状态",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETACLSTATUS", "param_source": "static", "default_value": "GETACLSTATUS"},
                 ]},
                {"name": "modify_acl", "display_name": "修改 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "修改现有 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：MODIFYACLENTRIES", "param_source": "static", "default_value": "MODIFYACLENTRIES"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "remove_acl_entries", "display_name": "删除 ACL 条目", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除指定的 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEACLENTRIES", "param_source": "static", "default_value": "REMOVEACLENTRIES"},
                     {"name": "aclspec", "param_type": "query", "data_type": "string", "required": True, "description": "ACL 规范字符串", "param_source": "llm_extract"},
                 ]},
                {"name": "remove_default_acl", "display_name": "删除默认 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除目录的所有默认 ACL 条目",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEDEFAULTACL", "param_source": "static", "default_value": "REMOVEDEFAULTACL"},
                 ]},
                {"name": "remove_acl", "display_name": "删除所有 ACL", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件/目录的所有 ACL（访问和默认）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEACL", "param_source": "static", "default_value": "REMOVEACL"},
                 ]},
                {"name": "check_access", "display_name": "检查权限", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "检查当前用户是否有指定的访问权限",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：CHECKACCESS", "param_source": "static", "default_value": "CHECKACCESS"},
                     {"name": "fsaction", "param_type": "query", "data_type": "string", "required": True, "description": "访问动作（如 r、w、x、rw）", "param_source": "llm_extract"},
                 ]},
                # ── XAttr ──
                {"name": "set_xattr", "display_name": "设置扩展属性", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "设置文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETXATTR", "param_source": "static", "default_value": "SETXATTR"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": True, "description": "属性名", "param_source": "llm_extract"},
                     {"name": "xattr.value", "param_type": "query", "data_type": "string", "required": True, "description": "属性值", "param_source": "llm_extract"},
                 ]},
                {"name": "get_xattrs", "display_name": "获取扩展属性", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETXATTRS", "param_source": "static", "default_value": "GETXATTRS"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": False, "description": "属性名（不指定返回全部）", "param_source": "llm_extract"},
                 ]},
                {"name": "list_xattrs", "display_name": "列出扩展属性", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "列出文件/目录的所有扩展属性名",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：LISTXATTRS", "param_source": "static", "default_value": "LISTXATTRS"},
                 ]},
                {"name": "remove_xattr", "display_name": "删除扩展属性", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "删除文件/目录的扩展属性",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：REMOVEXATTR", "param_source": "static", "default_value": "REMOVEXATTR"},
                     {"name": "xattr.name", "param_type": "query", "data_type": "string", "required": True, "description": "属性名", "param_source": "llm_extract"},
                 ]},
                # ── 纠删码 ──
                {"name": "get_ec_policies", "display_name": "EC 策略列表", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取所有纠删码策略及其状态",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETECPOLICIES", "param_source": "static", "default_value": "GETECPOLICIES"},
                 ]},
                {"name": "set_ec_policy", "display_name": "设置 EC 策略", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "为目录设置纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：SETECPOLICY", "param_source": "static", "default_value": "SETECPOLICY"},
                     {"name": "ecpolicy", "param_type": "query", "data_type": "string", "required": True, "description": "EC 策略名（如 RS-6-3-1024k）", "param_source": "llm_extract"},
                 ]},
                {"name": "get_ec_policy", "display_name": "获取 EC 策略", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETECPOLICY", "param_source": "static", "default_value": "GETECPOLICY"},
                 ]},
                {"name": "unset_ec_policy", "display_name": "取消 EC 策略", "method": "POST", "path": "/webhdfs/v1/{path}",
                 "description": "取消目录的纠删码策略",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：UNSETECPOLICY", "param_source": "static", "default_value": "UNSETECPOLICY"},
                 ]},
                # ── 更多快照 ──
                {"name": "allow_snapshot", "display_name": "允许快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "标记目录为可快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：ALLOWSNAPSHOT", "param_source": "static", "default_value": "ALLOWSNAPSHOT"},
                 ]},
                {"name": "disallow_snapshot", "display_name": "禁止快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "取消目录的可快照标记",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：DISALLOWSNAPSHOT", "param_source": "static", "default_value": "DISALLOWSNAPSHOT"},
                 ]},
                {"name": "rename_snapshot", "display_name": "重命名快照", "method": "PUT", "path": "/webhdfs/v1/{path}",
                 "description": "重命名快照",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：RENAMESNAPSHOT", "param_source": "static", "default_value": "RENAMESNAPSHOT"},
                     {"name": "oldsnapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "原快照名", "param_source": "llm_extract"},
                     {"name": "snapshotname", "param_type": "query", "data_type": "string", "required": True, "description": "新快照名", "param_source": "llm_extract"},
                 ]},
                {"name": "snapshot_list", "display_name": "快照列表", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取目录的所有快照列表",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "目录路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTLIST", "param_source": "static", "default_value": "GETSNAPSHOTLIST"},
                 ]},
                {"name": "snapshottable_dirs", "display_name": "可快照目录", "method": "GET", "path": "/webhdfs/v1/",
                 "description": "获取所有可快照的目录列表",
                 "params": [
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSNAPSHOTTABLEDIRECTORYLIST", "param_source": "static", "default_value": "GETSNAPSHOTTABLEDIRECTORYLIST"},
                 ]},
                # ── 其他 ──
                {"name": "server_defaults", "display_name": "服务端默认值", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取服务端默认配置（副本数、块大小、校验类型等）",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETSERVERDEFAULTS", "param_source": "static", "default_value": "GETSERVERDEFAULTS"},
                 ]},
                {"name": "symlink_target", "display_name": "符号链接目标", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取符号链接的目标路径",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "符号链接路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETLINKTARGET", "param_source": "static", "default_value": "GETLINKTARGET"},
                 ]},
                {"name": "block_locations", "display_name": "块位置", "method": "GET", "path": "/webhdfs/v1/{path}",
                 "description": "获取文件的数据块位置信息",
                 "params": [
                     {"name": "path", "param_type": "query", "data_type": "string", "required": True, "description": "文件路径", "param_source": "llm_extract"},
                     {"name": "op", "param_type": "query", "data_type": "string", "required": True, "description": "固定值：GETFILEBLOCKLOCATIONS", "param_source": "static", "default_value": "GETFILEBLOCKLOCATIONS"},
                 ]},
            ],
        },
        {
            "name": "YARN",
            "category": "resource",
            "description": "Hadoop YARN 资源管理器。通过 ResourceManager REST API 监控集群资源、管理应用程序、查看节点状态。"
                           "默认端口 8088。",
            "base_url": "http://your-rm-host:8088",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "用户名", "type": "text", "required": False, "help_text": "YARN 用户名（无认证可留空）"},
                {"key": "password", "label": "密码", "type": "password", "required": False, "help_text": "YARN 密码（无认证可留空）"},
            ]},
            "apis": [
                # ── 集群信息 ──
                {"name": "cluster_info", "display_name": "集群信息", "method": "GET", "path": "/ws/v1/cluster/info",
                 "description": "获取 YARN 集群基本信息：HA 状态、RM 版本、Hadoop 版本"},
                {"name": "cluster_metrics", "display_name": "集群资源指标", "method": "GET", "path": "/ws/v1/cluster/metrics",
                 "description": "获取集群资源使用概况：总/已用内存、VCores、节点数、应用数"},
                {"name": "scheduler_info", "display_name": "调度器信息", "method": "GET", "path": "/ws/v1/cluster/scheduler",
                 "description": "获取调度器配置和队列资源分配情况"},
                # ── 节点管理 ──
                {"name": "list_nodes", "display_name": "节点列表", "method": "GET", "path": "/ws/v1/cluster/nodes",
                 "description": "获取所有 NodeManager 节点状态、资源、健康状况"},
                {"name": "get_node", "display_name": "节点详情", "method": "GET", "path": "/ws/v1/cluster/nodes/{nodeId}",
                 "description": "获取指定节点的详细资源和运行中容器信息",
                 "params": [{"name": "nodeId", "param_type": "path", "data_type": "string", "required": True, "description": "节点 ID", "param_source": "llm_extract"}]},
                # ── 应用管理 ──
                {"name": "list_apps", "display_name": "应用列表", "method": "GET", "path": "/ws/v1/cluster/apps",
                 "description": "获取应用列表，支持按状态、用户、队列筛选",
                 "params": [
                     {"name": "states", "param_type": "query", "data_type": "string", "required": False, "description": "应用状态（逗号分隔：RUNNING,FINISHED,FAILED,KILLED）", "param_source": "llm_extract"},
                     {"name": "user", "param_type": "query", "data_type": "string", "required": False, "description": "用户名筛选", "param_source": "llm_extract"},
                     {"name": "queue", "param_type": "query", "data_type": "string", "required": False, "description": "队列名筛选", "param_source": "llm_extract"},
                     {"name": "limit", "param_type": "query", "data_type": "integer", "required": False, "description": "返回数量限制", "param_source": "llm_extract"},
                 ]},
                {"name": "get_app", "display_name": "应用详情", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}",
                 "description": "获取应用详细信息：状态、资源占用、运行时间、诊断信息",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "kill_app", "display_name": "终止应用", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/state",
                 "description": "终止指定应用（发送 KILL 命令）",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "state", "param_type": "body", "data_type": "string", "required": True, "description": "目标状态：KILLED", "param_source": "llm_extract"},
                 ]},
                {"name": "get_app_attempts", "display_name": "应用尝试列表", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts",
                 "description": "获取应用的所有尝试（重试记录）",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "move_app", "display_name": "移动应用队列", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/queue",
                 "description": "将应用移动到另一个队列",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "queue", "param_type": "body", "data_type": "string", "required": True, "description": "目标队列名", "param_source": "llm_extract"},
                 ]},
                {"name": "update_priority", "display_name": "更新优先级", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/priority",
                 "description": "修改应用的优先级",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "priority", "param_type": "body", "data_type": "integer", "required": True, "description": "新优先级值", "param_source": "llm_extract"},
                 ]},
                # ── 统计 ──
                {"name": "app_statistics", "display_name": "应用统计", "method": "GET", "path": "/ws/v1/cluster/appstatistics",
                 "description": "获取应用统计数据（按状态和类型分组）"},
                # ── 容器 ──
                {"name": "list_containers", "display_name": "容器列表", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers",
                 "description": "获取应用尝试的容器列表",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "get_container", "display_name": "容器详情", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers/{containerId}",
                 "description": "获取容器的详细信息",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                     {"name": "containerId", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"},
                 ]},
                {"name": "signal_container", "display_name": "发送信号", "method": "POST", "path": "/ws/v1/cluster/apps/{appId}/appattempts/{appAttemptId}/containers/{containerId}/signal",
                 "description": "向容器发送信号",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "appAttemptId", "param_type": "path", "data_type": "string", "required": True, "description": "尝试 ID", "param_source": "llm_extract"},
                     {"name": "containerId", "param_type": "path", "data_type": "string", "required": True, "description": "容器 ID", "param_source": "llm_extract"},
                     {"name": "signal", "param_type": "body", "data_type": "string", "required": True, "description": "信号类型（如 OUTPUT_THREAD_DUMP）", "param_source": "llm_extract"},
                 ]},
                # ── 超时管理 ──
                {"name": "get_app_timeouts", "display_name": "应用超时", "method": "GET", "path": "/ws/v1/cluster/apps/{appId}/timeouts",
                 "description": "获取应用的所有超时配置",
                 "params": [{"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"}]},
                {"name": "update_app_timeout", "display_name": "更新超时", "method": "PUT", "path": "/ws/v1/cluster/apps/{appId}/timeouts/{type}",
                 "description": "更新应用的超时值",
                 "params": [
                     {"name": "appId", "param_type": "path", "data_type": "string", "required": True, "description": "应用 ID", "param_source": "llm_extract"},
                     {"name": "type", "param_type": "path", "data_type": "string", "required": True, "description": "超时类型", "param_source": "llm_extract"},
                 ]},
                # ── 应用提交 ──
                {"name": "new_application", "display_name": "创建应用", "method": "POST", "path": "/ws/v1/cluster/apps/new-application",
                 "description": "创建新应用，返回 applicationId"},
                {"name": "submit_application", "display_name": "提交应用", "method": "POST", "path": "/ws/v1/cluster/apps",
                 "description": "提交新应用"},
                # ── 节点资源 ──
                {"name": "update_node_resource", "display_name": "更新节点资源", "method": "POST", "path": "/ws/v1/cluster/nodes/{nodeId}/resource",
                 "description": "更新节点的资源配置",
                 "params": [
                     {"name": "nodeId", "param_type": "path", "data_type": "string", "required": True, "description": "节点 ID", "param_source": "llm_extract"},
                 ]},
                # ── 调度器配置 ──
                {"name": "get_scheduler_conf", "display_name": "调度器配置", "method": "GET", "path": "/ws/v1/cluster/scheduler-conf",
                 "description": "获取调度器配置"},
                {"name": "update_scheduler_conf", "display_name": "修改调度器配置", "method": "PUT", "path": "/ws/v1/cluster/scheduler-conf",
                 "description": "修改调度器配置"},
                {"name": "scheduler_activities", "display_name": "调度活动", "method": "GET", "path": "/ws/v1/cluster/scheduler/activities",
                 "description": "获取调度器活动信息"},
                # ── 预约 ──
                {"name": "list_reservations", "display_name": "预约列表", "method": "GET", "path": "/ws/v1/cluster/reservation/list",
                 "description": "列出所有预约"},
                {"name": "create_reservation", "display_name": "创建预约", "method": "POST", "path": "/ws/v1/cluster/reservation/create",
                 "description": "创建预约定义"},
                {"name": "submit_reservation", "display_name": "提交预约", "method": "POST", "path": "/ws/v1/cluster/reservation/submit",
                 "description": "提交预约"},
                {"name": "update_reservation", "display_name": "更新预约", "method": "PUT", "path": "/ws/v1/cluster/reservation/update",
                 "description": "更新预约"},
                {"name": "delete_reservation", "display_name": "删除预约", "method": "DELETE", "path": "/ws/v1/cluster/reservation/delete",
                 "description": "删除预约"},
                # ── 委托令牌 ──
                {"name": "create_delegation_token", "display_name": "创建令牌", "method": "POST", "path": "/ws/v1/cluster/delegation-token",
                 "description": "创建委托令牌"},
                {"name": "cancel_delegation_token", "display_name": "取消令牌", "method": "POST", "path": "/ws/v1/cluster/delegation-token/cancel",
                 "description": "取消委托令牌"},
            ],
        },
    ]

    with create_db_session() as db:
        existing = {s.name for s in db.execute(select(ExternalSystemModel)).scalars().all()}
        created_count = 0
        updated_count = 0
        for preset in PRESETS:
            if preset["name"] in existing:
                # 更新已有系统的分类和 API 参数
                sys = db.scalar(select(ExternalSystemModel).where(ExternalSystemModel.name == preset["name"]))
                if not sys:
                    continue
                preset_cat = preset.get("category", "other")
                if sys.category == "other" and preset_cat != "other":
                    sys.category = preset_cat
                    updated_count += 1
                # 同步 API 参数：删除旧参数，从预设重建
                preset_apis = {a["name"]: a for a in preset.get("apis", [])}
                for api in db.execute(
                    select(ExternalApiModel).where(ExternalApiModel.system_id == sys.id)
                ).scalars().all():
                    api_def = preset_apis.get(api.name)
                    if api_def:
                        # 更新路径、方法、审批
                        api.path = api_def["path"]
                        api.method = api_def["method"]
                        api.description = api_def.get("description", "")
                        api.display_name = api_def["display_name"]
                        api.requires_approval = api_def["method"] in ("POST", "PUT", "DELETE", "PATCH")
                        # 删除旧参数，重建
                        db.query(ExternalApiParamModel).filter(ExternalApiParamModel.api_id == api.id).delete()
                        for p in api_def.get("params", []):
                            db.add(ExternalApiParamModel(
                                api_id=api.id,
                                name=p["name"],
                                param_type=p["param_type"],
                                data_type=p.get("data_type", "string"),
                                required=p.get("required", False),
                                description=p.get("description", ""),
                                default_value=p.get("default_value"),
                                param_source=p.get("param_source", "static"),
                                label=p.get("label"),
                            ))
                continue
            system = ExternalSystemModel(
                name=preset["name"],
                description=preset["description"],
                category=preset.get("category", "other"),
                base_url=preset["base_url"],
                auth_type=preset["auth_type"],
                credential_template_json=json.dumps(preset.get("credential_template", {})),
                published=True,
                headers_json="{}",
                created_by=1,
                jwt_login_url=preset.get("jwt_login_url"),
                jwt_refresh_url=preset.get("jwt_refresh_url"),
                jwt_request_body_template=preset.get("jwt_request_body_template"),
                jwt_response_token_path=preset.get("jwt_response_token_path"),
                jwt_response_expires_path=preset.get("jwt_response_expires_path"),
                jwt_response_token_header=preset.get("jwt_response_token_header"),
                login_token_source=preset.get("login_token_source"),
                login_inject_mode=preset.get("login_inject_mode"),
                login_inject_header_name=preset.get("login_inject_header_name"),
                jwt_refresh_body_template=preset.get("jwt_refresh_body_template"),
            )
            db.add(system)
            db.flush()
            for api_def in preset.get("apis", []):
                api = ExternalApiModel(
                    system_id=system.id,
                    name=api_def["name"],
                    display_name=api_def["display_name"],
                    description=api_def.get("description", ""),
                    method=api_def["method"],
                    path=api_def["path"],
                    requires_approval=api_def["method"] in ("POST", "PUT", "DELETE", "PATCH"),
                    timeout_seconds=30,
                )
                db.add(api)
                db.flush()
                # 创建 API 参数
                for p in api_def.get("params", []):
                    db.add(ExternalApiParamModel(
                        api_id=api.id,
                        name=p["name"],
                        param_type=p["param_type"],
                        data_type=p.get("data_type", "string"),
                        required=p.get("required", False),
                        description=p.get("description", ""),
                        default_value=p.get("default_value"),
                        param_source=p.get("param_source", "static"),
                        label=p.get("label"),
                    ))
            created_count += 1
        if created_count > 0 or updated_count > 0:
            db.commit()
            if created_count > 0:
                logger.info("Seeded %d preset external systems", created_count)
            if updated_count > 0:
                logger.info("Updated category for %d existing external systems", updated_count)
