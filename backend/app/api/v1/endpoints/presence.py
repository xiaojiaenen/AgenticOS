"""在线状态端点。

- ``POST /presence/heartbeat``：前端周期调用（登录态），刷新 Redis 5 分钟心跳。
- ``GET /presence/online``：管理员查看当前在线用户 id 集合 + 计数。

「最近活跃」持久化在 users.last_active_at（get_current_user 节流刷新），
「当前在线」走这里的 Redis 心跳，两者互补。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_admin
from app.db.models import UserModel
from app.services.cache_service import get_cache_service

router = APIRouter(prefix="/presence", tags=["Presence"])


@router.post("/heartbeat")
async def heartbeat(current_user: UserModel = Depends(get_current_user)) -> dict:
    await get_cache_service().user_online(current_user.id)
    return {"online": True}


@router.get("/online")
async def online_users(_: UserModel = Depends(require_admin)) -> dict:
    cache = get_cache_service()
    ids = await cache.get_online_users()
    return {"user_ids": sorted(int(x) for x in ids), "count": len(ids)}
