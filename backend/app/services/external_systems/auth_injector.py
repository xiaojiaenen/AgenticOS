"""AuthInjector：把用户凭据注入到出站请求（oauth2/jwt_login/api_key/bearer/basic/custom）。"""

from __future__ import annotations

import base64
import json
from datetime import timedelta

import httpx

from app.core.encryption import decrypt_safe, encrypt
from app.db.models import ExternalSystemModel, ExternalUserCredentialModel
from app.services.external_systems.serializers import (
    _extract_nested,
    _make_naive,
    _naive_utc_now,
    _serialize_headers,
)

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
