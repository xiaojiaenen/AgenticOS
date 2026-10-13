"""MCP 服务器管理 API（管理员）。

MCP（Model Context Protocol）是让 Agent 接入外部工具的事实标准协议。
这里提供服务器配置的增删改查与连接测试；发现的工具会以
``mcp__<server>__<tool>`` 命名进入工具目录，供智能体勾选使用。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import require_admin
from app.db.models import UserModel
from app.services.mcp_service import (
    delete_server,
    get_mcp_service,
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


@router.get("/servers", summary="列出 MCP 服务器")
def get_mcp_servers(_: UserModel = Depends(require_admin)):
    return {"items": list_servers()}


@router.post("/servers", summary="新增/更新 MCP 服务器")
def create_mcp_server(payload: MCPServerPayload, _: UserModel = Depends(require_admin)):
    try:
        return upsert_server(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/servers/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_mcp_server(name: str, _: UserModel = Depends(require_admin)) -> None:
    try:
        delete_server(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP 服务器不存在") from exc


@router.post("/connect", summary="连接 MCP 服务器并刷新工具列表")
async def connect_mcp(_: UserModel = Depends(require_admin)):
    service = get_mcp_service()
    ok = await service.connect()
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