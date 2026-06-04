"""输入补全 API"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.services.cache_service import get_cache_service

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.get("/suggest", summary="输入补全建议")
async def get_suggestions(
    q: str = Query(..., min_length=2, max_length=200, description="用户输入的前缀"),
    limit: int = Query(default=5, ge=1, le=10, description="返回数量"),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    """根据用户输入前缀，返回历史输入建议。

    优先匹配当前用户的输入，不足时补充全局热门输入。
    """
    cache = get_cache_service()

    # 先搜当前用户的
    user_suggestions = await cache.suggest_input(current_user.id, q, limit=limit)

    # 不足时补充全局的
    remaining = limit - len(user_suggestions)
    global_suggestions = []
    if remaining > 0:
        global_suggestions = await cache.suggest_global(q, limit=remaining)

    # 合并去重
    seen = set()
    suggestions = []
    for s in user_suggestions + global_suggestions:
        if s not in seen:
            seen.add(s)
            suggestions.append(s)

    return {"suggestions": suggestions[:limit]}
