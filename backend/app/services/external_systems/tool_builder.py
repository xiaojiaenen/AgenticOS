"""一系统一工具：动态构建 wuwei 工具 handler 并注册。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ExternalApiModel,
    ExternalApiParamModel,
    ExternalSystemModel,
    ExternalUserCredentialModel,
)
from app.services.external_systems.auth_injector import AuthInjector
from app.services.external_systems.cache import _cache_get, _cache_put
from app.services.external_systems.coordinators import ApprovalBlocker, UserInputBlocker
from app.services.external_systems.context import _current_session_id, get_ext_user_id
from app.services.external_systems.security_processor import SecurityProcessor
from app.services.external_systems.serializers import (
    _build_default_credential,
    _safe_name,
    _serialize_headers,
)

logger = logging.getLogger(__name__)

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
            logger.info("API approval check: session_id='%s', system=%s, api=%s", session_id, system.name, api_name)
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
