"""记忆 API 端点"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user, require_admin
from app.db.models import UserModel
from app.services.memory_service import get_memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("")
async def list_memories(
    user_id: int | None = Query(default=None, description="管理员可指定用户 ID"),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """获取当前用户的记忆，管理员可查看所有用户的记忆。"""
    if user_id is not None and current_user.role == "admin":
        # 管理员查看指定用户的记忆
        memories = await get_memory_service().get_all_memories(user_id)
    elif current_user.role == "admin":
        # 管理员查看所有用户的记忆
        memories = await get_memory_service().get_all_memories_admin()
    else:
        # 普通用户只能查看自己的记忆
        memories = await get_memory_service().get_all_memories(current_user.id)
    return {"items": memories, "count": len(memories)}


@router.get("/search")
async def search_memories(
    q: str,
    limit: int = 5,
    user_id: int | None = Query(default=None),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """搜索记忆。管理员可搜索指定用户的记忆。"""
    if not q.strip():
        return {"items": [], "count": 0}

    target_user_id = user_id if (user_id and current_user.role == "admin") else current_user.id
    memories = await get_memory_service().search_memory(target_user_id, q, limit=limit)
    return {"items": memories, "count": len(memories)}


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: int,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """删除记忆。普通用户只能删除自己的，管理员可删除任意记忆。"""
    user_id = None if current_user.role == "admin" else current_user.id
    success = await get_memory_service().delete_memory(memory_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}
