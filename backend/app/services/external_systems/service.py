"""ExternalSystemService：外部系统/API/凭据/档案关联的 CRUD 与测试调用。"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_safe, encrypt
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
from app.services.external_systems.auth_injector import AuthInjector
from app.services.external_systems.cache import refresh_system_cache
from app.services.external_systems.context import get_ext_user_id
from app.services.external_systems.security_processor import SecurityProcessor
from app.services.external_systems.tool_builder import _cast_value, _resolve_path
from app.services.external_systems.serializers import (
    _serialize_api,
    _serialize_connection,
    _serialize_headers,
    _serialize_system,
)

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
