"""MCP 服务器管理 API（管理员）。

MCP（Model Context Protocol）是让 Agent 接入外部工具的事实标准协议。
这里提供服务器配置的增删改查与连接测试；发现的工具会以
``mcp__<server>__<tool>`` 命名进入工具目录，供智能体勾选使用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import UserModel
from app.services import audit_service
from app.services.mcp_service import (
    apply_profile_servers,
    delete_server,
    get_mcp_service,
    list_profile_servers,
    list_servers,
    upsert_server,
)

logger = logging.getLogger("mcp.api")

router = APIRouter(prefix="/admin/mcp", tags=["MCP"])


class MCPServerPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    transport: str = Field(default="http", pattern="^(stdio|http|sse)$")
    url: str | None = Field(default=None, max_length=512)
    command: str | None = Field(default=None, max_length=256)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = Field(default=60.0, gt=0, le=600)
    enabled: bool = True
    # ── 内网接入选项 ──
    verify_tls: bool | None = Field(
        default=None,
        description="是否校验 TLS 证书。内网自签证书需置 false；不传 = 保持原值。",
    )
    allowed_cidrs: str | None = Field(
        default=None,
        description="平台连接本服务时允许的网段（逗号分隔 CIDR）。留空 = 不限制。",
    )
    user_accessible: bool | None = Field(
        default=None,
        description="是否允许被普通智能体使用。false 时须在 profile 上显式授权。",
    )
    external_system_id: int | None = Field(
        default=None,
        description="凭据来源集成 id。$CREDENTIAL.<字段> 从该集成的用户凭据中注入。",
    )


class ProfileMCPRef(BaseModel):
    server_name: str = Field(..., min_length=1, max_length=120)
    enabled: bool = True


class ProfileMCPAuthPayload(BaseModel):
    servers: list[ProfileMCPRef] = Field(default_factory=list)


@router.get("/servers", summary="列出 MCP 服务器")
def get_mcp_servers(_: UserModel = Depends(require_admin)):
    return {"items": list_servers()}


@router.post("/servers", summary="新增/更新 MCP 服务器")
def create_mcp_server(
    payload: MCPServerPayload,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    try:
        result = upsert_server(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    # env / headers 可能含凭据，只记非敏感字段
    audit_service.record_request(
        db, http_request, action="mcp.upsert", actor=current_user,
        resource_type="mcp_server", resource_id=payload.name,
        detail={"name": payload.name, "transport": payload.transport, "enabled": payload.enabled},
    )
    return result


@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_mcp_server(
    name: str,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> None:
    try:
        delete_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP 服务器不存在") from exc
    audit_service.record_request(
        db, http_request, action="mcp.delete", actor=current_user,
        resource_type="mcp_server", resource_id=name,
    )


@router.post("/connect", summary="连接 MCP 服务器并刷新工具列表")
async def connect_mcp(
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    service = get_mcp_service()
    ok = await service.connect()
    audit_service.record_request(
        db, http_request, action="mcp.connect", actor=current_user,
        resource_type="mcp_server",
        result=audit_service.RESULT_ALLOW if ok else audit_service.RESULT_ERROR,
        detail={"connected": ok, "error": service.last_error, "tool_count": len(service.tool_catalogue())},
    )
    return {
        "connected": ok,
        "error": service.last_error,
        "tools": service.tool_catalogue(),
    }


@router.get("/tools", summary="查看已发现的 MCP 工具")
async def list_mcp_tools(_: UserModel = Depends(require_admin)):
    service = get_mcp_service()
    return {
        "connected": service._session_manager is not None,
        "error": service.last_error,
        "tools": service.tool_catalogue(),
    }


# ── profile 级授权（按需挂载）──────────────────────────────────────────


@router.get("/profiles/{profile_id}/servers", summary="查看智能体授权的 MCP 服务器")
def get_profile_mcp_servers(
    profile_id: int,
    _: UserModel = Depends(require_admin),
):
    return {"items": list_profile_servers(profile_id)}


@router.put("/profiles/{profile_id}/servers", summary="设置智能体授权的 MCP 服务器")
def set_profile_mcp_servers(
    profile_id: int,
    payload: ProfileMCPAuthPayload,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    apply_profile_servers(profile_id, [r.model_dump() for r in payload.servers])
    audit_service.record_request(
        db, http_request, action="mcp.profile_auth", actor=current_user,
        resource_type="agent_profile", resource_id=str(profile_id),
        detail={
            "servers": [r.server_name for r in payload.servers],
            "count": len(payload.servers),
        },
    )
    return {"items": list_profile_servers(profile_id)}