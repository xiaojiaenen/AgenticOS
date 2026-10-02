"""记忆 API 端点

扩展端点：
- GET /memory/scenarios   L2 场景列表
- GET /memory/persona      L3 用户画像
- GET /memory/conversations  L0 原始对话回溯
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.models import (
    MemoryConversationModel,
    MemoryModel,
    MemoryPersonaModel,
    MemoryScenarioModel,
    UserModel,
)
from app.db.session import create_db_session
from app.services.memory_service import get_memory_service

router = APIRouter(prefix="/memory", tags=["Memory"])


class CreateMemoryRequest(BaseModel):
    """POST /memory JSON body（修复无 Body 注解导致的 422）。"""

    content: str = Field(..., min_length=1)
    memory_type: str = Field(default="fact")
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: Optional[Union[list[str], str]] = None


def _parse_tags(tags: Optional[Union[list[str], str]]) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(t) for t in tags if str(t).strip()]
    text = tags.strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            pass
        return [text]
    return [t.strip() for t in text.split(",") if t.strip()]


@router.get("")
async def list_memories(
    user_id: int | None = Query(default=None, description="管理员可指定用户 ID"),
    limit: int = Query(default=200, ge=1, le=1000, description="分页大小上限"),
    offset: int = Query(default=0, ge=0, description="分页偏移"),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """获取当前用户的记忆，管理员可查看所有用户的记忆。"""
    if user_id is not None and current_user.role == "admin":
        memories = await get_memory_service().get_all_memories(user_id, limit=limit, offset=offset)
    elif current_user.role == "admin":
        memories = await get_memory_service().get_all_memories_admin(limit=limit, offset=offset)
    else:
        memories = await get_memory_service().get_all_memories(current_user.id, limit=limit, offset=offset)
    return {"items": memories, "count": len(memories)}


@router.post("")
async def create_memory(
    payload: Optional[CreateMemoryRequest] = None,
    content: Optional[str] = Query(default=None),
    memory_type: str = Query(default="fact"),
    importance: float = Query(default=0.5),
    tags: Optional[str] = Query(default=None),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """创建新记忆。

    优先接受 JSON body（CreateMemoryRequest），同时兼容 query 参数，
    避免仅传标量导致的 422。
    """
    if payload is not None:
        final_content = payload.content
        final_type = payload.memory_type
        final_importance = payload.importance
        tag_list = _parse_tags(payload.tags)
    else:
        final_content = content
        final_type = memory_type
        final_importance = importance
        tag_list = _parse_tags(tags)

    if not final_content or not str(final_content).strip():
        raise HTTPException(status_code=422, detail="内容不能为空")

    memory_id = await get_memory_service().add_memory(
        current_user.id,
        str(final_content).strip(),
        memory_type=final_type,
        importance=max(0.1, min(1.0, float(final_importance))),
        tags=tag_list or None,
        source="manual",
    )
    return {"id": memory_id, "success": True}


@router.get("/search")
async def search_memories(
    q: str,
    limit: int = 5,
    user_id: int | None = Query(default=None),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """搜索记忆（BM25 + 向量混合检索）。管理员可搜索指定用户的记忆。"""
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
        raise HTTPException(status_code=404, detail="记忆记录不存在")
    return {"success": True}


# ─── 分层蒸馏扩展端点 ───


@router.get("/scenarios")
async def list_scenarios(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """L2 场景列表（当前用户的场景块）"""
    def _run():
        with create_db_session() as db:
            return db.scalars(
                select(MemoryScenarioModel)
                .where(MemoryScenarioModel.user_id == current_user.id)
                .order_by(MemoryScenarioModel.updated_at.desc())
                .limit(limit)
            ).all()

    rows = await asyncio.to_thread(_run)
    items = [
        {
            "id": r.id,
            "title": r.title,
            "summary": r.summary,
            "tags": json.loads(r.tags_json) if r.tags_json else [],
            "atom_ids": json.loads(r.atom_ids_json) if r.atom_ids_json else [],
            "access_count": r.access_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "last_accessed_at": r.last_accessed_at.isoformat() if r.last_accessed_at else None,
        }
        for r in rows
    ]
    return {"items": items, "count": len(items)}


@router.get("/persona")
async def get_persona(
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """L3 用户画像"""
    def _run():
        with create_db_session() as db:
            return db.scalars(
                select(MemoryPersonaModel)
                .where(MemoryPersonaModel.user_id == current_user.id)
            ).first()

    persona = await asyncio.to_thread(_run)
    if not persona:
        return {"exists": False}

    return {
        "exists": True,
        "identity": json.loads(persona.identity_json or "{}"),
        "preferences": json.loads(persona.preferences_json or "{}"),
        "tech_stack": json.loads(persona.tech_stack_json or "[]"),
        "goals": json.loads(persona.goals_json or "[]"),
        "projects": json.loads(persona.projects_json or "[]"),
        "version": persona.version,
        "updated_at": persona.updated_at.isoformat() if persona.updated_at else None,
    }


@router.get("/conversations")
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """L0 原始对话回溯"""
    def _run():
        with create_db_session() as db:
            return db.scalars(
                select(MemoryConversationModel)
                .where(MemoryConversationModel.user_id == current_user.id)
                .order_by(MemoryConversationModel.created_at.desc())
                .limit(limit)
            ).all()

    rows = await asyncio.to_thread(_run)
    items = [
        {
            "id": r.id,
            "session_id": r.session_id,
            "user_message": r.user_message[:300],
            "assistant_message": r.assistant_message[:300],
            "tokens_used": r.tokens_used,
            "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    return {"items": items, "count": len(items)}


@router.get("/stats")
async def memory_stats(
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """记忆统计：各层数量"""
    from sqlalchemy import func

    def _run():
        with create_db_session() as db:
            atom_count = db.scalar(
                select(func.count(MemoryModel.id))
                .where(MemoryModel.user_id == current_user.id)
                .where(MemoryModel.layer == "L1")
            ) or 0
            scenario_count = db.scalar(
                select(func.count(MemoryScenarioModel.id))
                .where(MemoryScenarioModel.user_id == current_user.id)
            ) or 0
            conversation_count = db.scalar(
                select(func.count(MemoryConversationModel.id))
                .where(MemoryConversationModel.user_id == current_user.id)
            ) or 0
            has_persona = db.scalar(
                select(func.count(MemoryPersonaModel.id))
                .where(MemoryPersonaModel.user_id == current_user.id)
            ) or 0
            return atom_count, scenario_count, conversation_count, has_persona

    atom_count, scenario_count, conversation_count, has_persona = await asyncio.to_thread(_run)
    return {
        "l0_conversations": conversation_count,
        "l1_atoms": atom_count,
        "l2_scenarios": scenario_count,
        "l3_persona_exists": bool(has_persona),
    }
