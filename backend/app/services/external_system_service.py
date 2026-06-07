"""External system integration — CRUD, user credentials, one-tool-per-system design."""

from __future__ import annotations

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

# ── context vars for current user (like email_tools pattern) ────────────────

_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("ext_current_user_id", default=0)


def set_ext_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)


def get_ext_user_id() -> int:
    return _current_user_id.get()


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
        "published": sys.published,
        "headers": _serialize_headers(sys.headers_json),
        "advanced_auth": json.loads(sys.advanced_auth_json) if sys.advanced_auth_json else {},
        "enabled": sys.enabled,
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
        "enabled": api.enabled,
        "params": [
            {
                "name": p.name,
                "param_type": p.param_type,
                "data_type": p.data_type,
                "required": p.required,
                "description": p.description,
                "default_value": p.default_value,
            }
            for p in params
        ],
        "created_at": api.created_at,
        "updated_at": api.updated_at,
    }


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

                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.post(system.jwt_refresh_url, json=refresh_body)
                    resp.raise_for_status()
                    resp_data = resp.json()

                token_path = system.jwt_response_token_path or "token"
                new_token = _extract_nested(resp_data, token_path)
                if new_token:
                    expires_at = None
                    if system.jwt_response_expires_path:
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

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(login_url, json=body)
            resp.raise_for_status()
            resp_data = resp.json()

        # Extract token from response using configured path
        token_path = system.jwt_response_token_path or "token"
        token = _extract_nested(resp_data, token_path)
        if not token:
            raise ValueError(f"登录响应中未找到 token（路径: {token_path}）")

        # Extract expiry if configured
        expires_at = None
        if system.jwt_response_expires_path:
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

        # Look up user credential
        from app.db.session import create_db_session

        db = create_db_session()
        try:
            cred = db.query(ExternalUserCredentialModel).filter_by(
                user_id=effective_user_id, system_id=system.id
            ).first()
            if not cred or cred.connection_status != "connected":
                return json.dumps({
                    "error": f"请先在集成市场连接 {system.name}",
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

            url = system.base_url + _resolve_path(api.path, path_params)

            body: Any = None
            if body_params:
                if len(body_params) == 1 and "body" in body_params and isinstance(body_params["body"], (dict, list)):
                    body = body_params["body"]
                else:
                    body = body_params

            headers = _serialize_headers(system.headers_json)

            async with httpx.AsyncClient(timeout=api.timeout_seconds, follow_redirects=True) as client:
                request = client.build_request(
                    method=api.method,
                    url=url,
                    params=query_params or None,
                    json=body,
                    headers=headers,
                )
                await AuthInjector.inject(system, cred, request)
                await SecurityProcessor.process_request(system, request)
                response = await client.send(request)

            # Mark auth errors
            if response.status_code in (401, 403):
                cred.connection_status = "auth_error"
                db.commit()
                return json.dumps({
                    "error": f"{system.name} 凭据无效（HTTP {response.status_code}），请重新连接",
                    "status_code": response.status_code,
                }, ensure_ascii=False)

            # Decrypt response if configured
            body_text = await SecurityProcessor.process_response(system, response.text)
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

            # Build param description
            param_descs = []
            for p in param_rows:
                req = "*" if p.required else ""
                param_descs.append(f"{p.name}{req}({p.data_type})")
            param_str = ", ".join(param_descs) if param_descs else "无参数"
            description_lines.append(f"- {api.name}({param_str}) — {api.display_name}: {api.description}")
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
            timeout_seconds=30,
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

    def list_published_systems(self) -> list[dict]:
        systems = list(self.db.execute(
            select(ExternalSystemModel).where(
                ExternalSystemModel.published.is_(True),
                ExternalSystemModel.enabled.is_(True),
            )
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
            headers_json=json.dumps(data.headers) if data.headers else "{}",
            advanced_auth_json=json.dumps(data.advanced_auth) if data.advanced_auth else "{}",
            created_by=user_id,
        )
        self.db.add(sys)
        self.db.commit()
        self.db.refresh(sys)
        return _serialize_system(sys)

    def update_system(self, system_id: int, data: ExternalSystemUpdateRequest) -> dict:
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
        if data.published is not None:
            sys.published = data.published
        if data.headers is not None:
            sys.headers_json = json.dumps(data.headers)
        if data.advanced_auth is not None:
            sys.advanced_auth_json = json.dumps(data.advanced_auth)
        if data.enabled is not None:
            sys.enabled = data.enabled

        self.db.commit()
        self.db.refresh(sys)
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
                self.db.add(ExternalApiParamModel(api_id=api.id, name=p["name"], param_type=p["param_type"], data_type=p.get("data_type", "string"), required=p.get("required", False), description=p.get("description", ""), default_value=p.get("default_value")))
            created.append(api)
        self.db.commit()
        self.db.refresh(system)
        return _serialize_system(system, len(created))


def seed_preset_external_systems() -> None:
    """Seed preset external systems on startup (idempotent)."""
    from app.db.session import create_db_session

    PRESETS = [
        {
            "name": "GitHub",
            "description": "GitHub 代码托管平台 - 仓库管理、Issues、Pull Requests",
            "base_url": "https://api.github.com",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Personal Access Token", "type": "password", "required": True, "help_text": "在 GitHub Settings > Developer settings > Personal access tokens 中生成", "help_url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token"}]},
            "apis": [
                {"name": "list_repos", "display_name": "获取仓库列表", "method": "GET", "path": "/user/repos", "description": "获取当前用户的仓库列表"},
                {"name": "get_repo", "display_name": "获取仓库详情", "method": "GET", "path": "/repos/{owner}/{repo}", "description": "获取指定仓库的详细信息"},
                {"name": "list_issues", "display_name": "获取 Issues 列表", "method": "GET", "path": "/repos/{owner}/{repo}/issues", "description": "获取仓库的 Issues 列表"},
                {"name": "create_issue", "display_name": "创建 Issue", "method": "POST", "path": "/repos/{owner}/{repo}/issues", "description": "在仓库中创建新 Issue"},
                {"name": "list_pull_requests", "display_name": "获取 PR 列表", "method": "GET", "path": "/repos/{owner}/{repo}/pulls", "description": "获取仓库的 Pull Request 列表"},
                {"name": "get_pull_request", "display_name": "获取 PR 详情", "method": "GET", "path": "/repos/{owner}/{repo}/pulls/{pull_number}", "description": "获取指定 PR 的详细信息"},
                {"name": "list_commits", "display_name": "获取提交记录", "method": "GET", "path": "/repos/{owner}/{repo}/commits", "description": "获取仓库的提交历史"},
            ],
        },
        {
            "name": "GitLab",
            "description": "GitLab 代码托管平台 - 仓库管理、Issues、Merge Requests",
            "base_url": "https://gitlab.com/api/v4",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Personal Access Token", "type": "password", "required": True, "help_text": "在 GitLab User Settings > Access Tokens 中生成", "help_url": "https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html"}]},
            "apis": [
                {"name": "list_projects", "display_name": "获取项目列表", "method": "GET", "path": "/projects", "description": "获取当前用户的项目列表"},
                {"name": "get_project", "display_name": "获取项目详情", "method": "GET", "path": "/projects/{id}", "description": "获取指定项目的详细信息"},
                {"name": "list_issues", "display_name": "获取 Issues 列表", "method": "GET", "path": "/projects/{id}/issues", "description": "获取项目的 Issues 列表"},
                {"name": "create_issue", "display_name": "创建 Issue", "method": "POST", "path": "/projects/{id}/issues", "description": "在项目中创建新 Issue"},
                {"name": "list_merge_requests", "display_name": "获取 MR 列表", "method": "GET", "path": "/projects/{id}/merge_requests", "description": "获取项目的 Merge Request 列表"},
                {"name": "get_merge_request", "display_name": "获取 MR 详情", "method": "GET", "path": "/projects/{id}/merge_requests/{merge_request_iid}", "description": "获取指定 MR 的详细信息"},
            ],
        },
        {
            "name": "Slack",
            "description": "Slack 团队协作平台 - 消息发送、频道管理",
            "base_url": "https://slack.com/api",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Bot Token / User Token", "type": "password", "required": True, "help_text": "在 Slack API > Your Apps > OAuth & Permissions 中获取", "help_url": "https://api.slack.com/authentication/token-types"}]},
            "apis": [
                {"name": "post_message", "display_name": "发送消息", "method": "POST", "path": "/chat.postMessage", "description": "向指定频道发送消息"},
                {"name": "list_channels", "display_name": "获取频道列表", "method": "GET", "path": "/conversations.list", "description": "获取可用频道列表"},
                {"name": "get_channel_info", "display_name": "获取频道信息", "method": "GET", "path": "/conversations.info", "description": "获取指定频道的详细信息"},
                {"name": "list_users", "display_name": "获取用户列表", "method": "GET", "path": "users.list", "description": "获取工作区用户列表"},
            ],
        },
        {
            "name": "Notion",
            "description": "Notion 知识管理平台 - 页面、数据库操作",
            "base_url": "https://api.notion.com/v1",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Integration Token", "type": "password", "required": True, "help_text": "在 Notion Settings > Connections > Develop or manage integrations 中创建", "help_url": "https://developers.notion.com/docs/getting-started"}]},
            "apis": [
                {"name": "search", "display_name": "搜索页面", "method": "POST", "path": "/search", "description": "搜索 Notion 中的页面和数据库"},
                {"name": "get_page", "display_name": "获取页面", "method": "GET", "path": "/pages/{page_id}", "description": "获取指定页面的内容"},
                {"name": "create_page", "display_name": "创建页面", "method": "POST", "path": "/pages", "description": "创建新页面"},
                {"name": "update_page", "display_name": "更新页面", "method": "PATCH", "path": "/pages/{page_id}", "description": "更新页面内容"},
                {"name": "query_database", "display_name": "查询数据库", "method": "POST", "path": "/databases/{database_id}/query", "description": "查询 Notion 数据库"},
            ],
        },
        {
            "name": "Jira",
            "description": "Jira 项目管理平台 - Issues、项目、Sprint 管理",
            "base_url": "https://your-domain.atlassian.net",
            "auth_type": "basic",
            "credential_template": {"fields": [
                {"key": "username", "label": "邮箱地址", "type": "text", "required": True, "help_text": "你的 Atlassian 账户邮箱"},
                {"key": "password", "label": "API Token", "type": "password", "required": True, "help_text": "在 https://id.atlassian.com/manage-profile/security/api-tokens 中生成", "help_url": "https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/"},
            ]},
            "apis": [
                {"name": "list_projects", "display_name": "获取项目列表", "method": "GET", "path": "/rest/api/3/project", "description": "获取所有可访问的项目"},
                {"name": "get_issue", "display_name": "获取 Issue", "method": "GET", "path": "/rest/api/3/issue/{issueIdOrKey}", "description": "获取指定 Issue 的详细信息"},
                {"name": "create_issue", "display_name": "创建 Issue", "method": "POST", "path": "/rest/api/3/issue", "description": "创建新 Issue"},
                {"name": "search_issues", "display_name": "搜索 Issues", "method": "GET", "path": "/rest/api/3/search", "description": "使用 JQL 搜索 Issues"},
                {"name": "update_issue", "display_name": "更新 Issue", "method": "PUT", "path": "/rest/api/3/issue/{issueIdOrKey}", "description": "更新 Issue 状态或字段"},
            ],
        },
        {
            "name": "Feishu",
            "description": "飞书企业协作平台 - 消息、文档、日历",
            "base_url": "https://open.feishu.cn/open-apis",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Tenant Access Token", "type": "password", "required": True, "help_text": "在飞书开放平台 > 应用管理 > 凭证与基础信息 中获取", "help_url": "https://open.feishu.cn/document/home/introduction-to-permissions-and-authentication/access-token/tenant-access-token"}]},
            "apis": [
                {"name": "send_message", "display_name": "发送消息", "method": "POST", "path": "/im/v1/messages", "description": "向用户或群组发送消息"},
                {"name": "list_contacts", "display_name": "获取通讯录", "method": "GET", "path": "/contact/v3/users", "description": "获取企业通讯录用户列表"},
                {"name": "create_document", "display_name": "创建文档", "method": "POST", "path": "/docx/v1/documents", "description": "创建飞书文档"},
                {"name": "get_calendar_events", "display_name": "获取日程", "method": "GET", "path": "/calendar/v4/calendars/{calendar_id}/events", "description": "获取日历日程列表"},
            ],
        },
        {
            "name": "DingTalk",
            "description": "钉钉企业协作平台 - 消息、审批、日程",
            "base_url": "https://oapi.dingtalk.com",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "Access Token", "type": "password", "required": True, "help_text": "在钉钉开放平台 > 应用开发 > 企业内部应用 > 凭证与基础信息 中获取", "help_url": "https://open.dingtalk.com/document/isvapp/isv-obtain-configuration-parameters"}]},
            "apis": [
                {"name": "send_work_notification", "display_name": "发送工作通知", "method": "POST", "path": "/topapi/message/corpconversation/asyncsend_v2", "description": "向员工发送工作通知"},
                {"name": "get_user_info", "display_name": "获取用户信息", "method": "GET", "path": "/topapi/v2/user/get", "description": "获取员工详细信息"},
                {"name": "list_users", "display_name": "获取员工列表", "method": "GET", "path": "/topapi/v2/user/listbypage", "description": "分页获取员工列表"},
                {"name": "create_approval", "display_name": "创建审批", "method": "POST", "path": "/topapi/processinstance/create", "description": "发起审批流程"},
            ],
        },
        {
            "name": "Linear",
            "description": "Linear 项目管理工具 - Issues、Projects、Teams",
            "base_url": "https://api.linear.app/graphql",
            "auth_type": "bearer",
            "credential_template": {"fields": [{"key": "token", "label": "API Key", "type": "password", "required": True, "help_text": "在 Linear Settings > API > Personal API keys 中生成", "help_url": "https://linear.app/docs/api-reference"}]},
            "apis": [
                {"name": "list_teams", "display_name": "获取团队列表", "method": "POST", "path": "/", "description": "获取所有团队"},
                {"name": "list_issues", "display_name": "获取 Issue 列表", "method": "POST", "path": "/", "description": "获取 Issues 列表"},
                {"name": "create_issue", "display_name": "创建 Issue", "method": "POST", "path": "/", "description": "创建新 Issue"},
                {"name": "update_issue", "display_name": "更新 Issue", "method": "POST", "path": "/", "description": "更新 Issue 状态或字段"},
                {"name": "list_projects", "display_name": "获取项目列表", "method": "POST", "path": "/", "description": "获取所有项目"},
            ],
        },
    ]

    with create_db_session() as db:
        existing = {s.name for s in db.execute(select(ExternalSystemModel)).scalars().all()}
        created_count = 0
        for preset in PRESETS:
            if preset["name"] in existing:
                continue
            system = ExternalSystemModel(
                name=preset["name"],
                description=preset["description"],
                base_url=preset["base_url"],
                auth_type=preset["auth_type"],
                credential_template_json=json.dumps(preset.get("credential_template", {})),
                published=True,
                headers_json="{}",
                created_by=1,
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
            created_count += 1
        if created_count > 0:
            db.commit()
            logger.info("Seeded %d preset external systems", created_count)
