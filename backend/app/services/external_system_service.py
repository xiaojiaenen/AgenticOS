"""External system integration — CRUD, user credentials, one-tool-per-system design."""

from __future__ import annotations

import base64
import contextvars
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
        "jwt_login_url": sys.jwt_login_url,
        "jwt_request_body_template": sys.jwt_request_body_template,
        "jwt_response_token_path": sys.jwt_response_token_path,
        "jwt_response_expires_path": sys.jwt_response_expires_path,
        "published": sys.published,
        "headers": _serialize_headers(sys.headers_json),
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
            and cred.oauth_expires_at > datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
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
                db_cred.oauth_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=expires_in)
                db_cred.connection_status = "connected"
                db.commit()
        finally:
            db.close()

        return new_access

    @staticmethod
    async def _ensure_jwt(system: ExternalSystemModel, cred: ExternalUserCredentialModel) -> str:
        """Return a valid JWT by logging in with username/password, caching the result."""
        # Check cached JWT (with 60s buffer)
        if (
            cred.jwt_expires_at
            and cred.cached_jwt_encrypted
            and cred.jwt_expires_at > datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=60)
        ):
            return decrypt_safe(cred.cached_jwt_encrypted)

        # Need to login
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
                expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=int(expires_in))

        # If no expiry from response, default to 1 hour
        if not expires_at:
            expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

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
                user_id=user_id, system_id=system.id
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
                response = await client.send(request)

            # Mark auth errors
            if response.status_code in (401, 403):
                cred.connection_status = "auth_error"
                db.commit()
                return json.dumps({
                    "error": f"{system.name} 凭据无效（HTTP {response.status_code}），请重新连接",
                    "status_code": response.status_code,
                }, ensure_ascii=False)

            result: dict[str, Any] = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result, ensure_ascii=False)

        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"请求失败: {e}"}, ensure_ascii=False)
        finally:
            db.close()

    return handler


def register_external_tools(registry, system_ids: list[int], db: Session) -> None:
    """Register one wuwei tool per external system.

    Each tool's description lists available APIs. The handler dispatches by api_name.
    """
    user_id = get_ext_user_id()
    if not user_id:
        return

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

        logger.info("Registered system tool: %s (%d APIs)", tool_name, len(api_map))


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
            jwt_login_url=data.jwt_login_url,
            jwt_request_body_template=data.jwt_request_body_template,
            jwt_response_token_path=data.jwt_response_token_path,
            jwt_response_expires_path=data.jwt_response_expires_path,
            published=data.published,
            headers_json=json.dumps(data.headers) if data.headers else "{}",
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
        if data.jwt_login_url is not None:
            sys.jwt_login_url = data.jwt_login_url
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

                response = await client.send(request)

            elapsed = int((time.monotonic() - start) * 1000)
            return ExternalApiTestResponse(
                success=200 <= response.status_code < 300,
                status_code=response.status_code,
                body=response.text,
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
