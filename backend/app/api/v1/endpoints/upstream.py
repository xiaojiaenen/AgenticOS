"""唯一上游 agents.gree.com：自动登录 / Cookie / 健康检查。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_admin
from app.core.config import get_settings
from app.db.models import UserModel

logger = logging.getLogger("agenticos.upstream.api")

router = APIRouter(prefix="/upstream", tags=["Upstream"])


@router.get("/status")
async def get_upstream_status(current_user: UserModel = Depends(get_current_user)) -> dict:
    """当前用户上游凭据/Cookie 状态（不含明文）。"""
    from app.services.upstream import credential_store
    from app.services.upstream.upstream_client import get_upstream_client

    settings = get_settings()
    items = credential_store.list_credentials_status(
        user_id=None if current_user.role == "admin" else current_user.id
    )
    mine = next((i for i in items if i["user_id"] == current_user.id), None)
    health = await get_upstream_client().health(current_user.id if mine else None)
    return {
        "upstream": credential_store.UPSTREAM_KEY,
        "base_url": credential_store.get_upstream_base_url(),
        "login_url": credential_store.get_upstream_login_url(),
        "auto_login_enabled": settings.upstream_auto_login_enabled,
        "use_cookie_llm": settings.upstream_use_cookie_llm,
        "mine": mine,
        "health": health,
        "items": items if current_user.role == "admin" else ([mine] if mine else []),
    }


@router.post("/relogin")
async def relogin_upstream(current_user: UserModel = Depends(get_current_user)) -> dict:
    """内部/调试：立即重新自动登录。正常场景由登录钩子与预续期循环自动完成。"""
    from app.services.upstream.credential_store import get_credential_for_user
    from app.services.upstream.login_orchestrator import perform_auto_login

    row = get_credential_for_user(current_user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="尚未配置上游凭据，请先完成 LDAP 登录或联系管理员",
        )
    try:
        result = await perform_auto_login(current_user.id)
    except Exception as e:
        logger.exception("upstream relogin failed user=%s", current_user.id)
        raise HTTPException(status_code=500, detail=f"自动登录失败: {e}") from e
    return result


@router.get("/api-keys")
async def list_my_api_keys(current_user: UserModel = Depends(get_current_user)) -> dict:
    from app.services.upstream import api_key_service

    return {
        "items": api_key_service.list_api_keys(current_user.id, is_admin=current_user.role == "admin"),
    }


@router.post("/api-keys")
async def create_api_key(
    body: dict | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """创建 API Key（明文仅返回一次）。供外部软件调用 /v1/chat/completions。"""
    from app.services.upstream import api_key_service

    name = ((body or {}).get("name") or "default") if isinstance(body, dict) else "default"
    return api_key_service.create_api_key(current_user.id, name=name)


@router.delete("/api-keys/{key_id}")
async def delete_api_key(key_id: int, current_user: UserModel = Depends(get_current_user)) -> dict:
    from app.services.upstream import api_key_service

    ok = api_key_service.revoke_api_key(current_user.id, key_id, is_admin=current_user.role == "admin")
    if not ok:
        raise HTTPException(status_code=404, detail="API Key 不存在或无权删除")
    return {"success": True}


@router.post("/api-keys/{key_id}/enabled")
async def toggle_api_key(
    key_id: int,
    body: dict,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    from app.services.upstream import api_key_service

    enabled = bool(body.get("enabled", True))
    item = api_key_service.set_api_key_enabled(
        current_user.id, key_id, enabled, is_admin=current_user.role == "admin"
    )
    if item is None:
        raise HTTPException(status_code=404, detail="API Key 不存在或无权修改")
    return item


@router.get("/admin/credentials")
async def admin_list_credentials(admin: UserModel = Depends(require_admin)) -> dict:
    from app.services.upstream import credential_store

    return {
        "upstream": credential_store.UPSTREAM_KEY,
        "items": credential_store.list_credentials_status(),
    }


@router.post("/admin/users/{user_id}/relogin")
async def admin_relogin_user(user_id: int, admin: UserModel = Depends(require_admin)) -> dict:
    from app.services.upstream.credential_store import get_credential_for_user
    from app.services.upstream.login_orchestrator import perform_auto_login

    if get_credential_for_user(user_id) is None:
        raise HTTPException(status_code=404, detail="该用户尚未配置上游凭据")
    return await perform_auto_login(user_id)
