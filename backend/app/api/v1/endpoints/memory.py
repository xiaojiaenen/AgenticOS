"""记忆 API 端点"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.services.memory_service import get_memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("")
def list_memories(current_user: UserModel = Depends(get_current_user)) -> dict:
    """获取当前用户的所有记忆"""
    memories = get_memory_service().get_all_memories(current_user.id)
    return {"items": memories, "count": len(memories)}


@router.get("/search")
def search_memories(
    q: str,
    limit: int = 5,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """搜索当前用户的记忆"""
    if not q.strip():
        return {"items": [], "count": 0}
    memories = get_memory_service().search_memory(current_user.id, q, limit=limit)
    return {"items": memories, "count": len(memories)}


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """删除当前用户的一条记忆"""
    success = get_memory_service().delete_memory(current_user.id, memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True}
