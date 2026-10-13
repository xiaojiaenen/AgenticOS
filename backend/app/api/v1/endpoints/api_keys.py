"""API Key 管理：用户创建/管理自己的 sk-agenticos-*，用于调用 /v1 OpenAI 兼容网关。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get("")
async def list_my_api_keys(current_user: UserModel = Depends(get_current_user)) -> dict:
    return {
        "items": api_key_service.list_api_keys(current_user.id, is_admin=current_user.role == "admin"),
    }


@router.post("")
async def create_api_key(
    body: dict | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """创建 API Key（明文仅返回一次）。供外部软件调用 /v1/chat/completions。"""
    name = ((body or {}).get("name") or "default") if isinstance(body, dict) else "default"
    return api_key_service.create_api_key(current_user.id, name=name)


@router.delete("/{key_id}")
async def delete_api_key(key_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    ok = api_key_service.revoke_api_key(current_user.id, key_id, is_admin=current_user.role == "admin")
    if not ok:
        raise HTTPException(status_code=404, detail="API Key 不存在或无权删除")
    return {"success": True}


@router.post("/{key_id}/enabled")
async def toggle_api_key(
    key_id: int,
    body: dict,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    enabled = bool(body.get("enabled", True))
    item = api_key_service.set_api_key_enabled(
        current_user.id, key_id, enabled, is_admin=current_user.role == "admin"
    )
    if item is None:
        raise HTTPException(status_code=404, detail="API Key 不存在或无权修改")
    return item
