"""每用户使用数据分析（管理员）。

回答「每个用户用了多少、是否在线、最近何时活跃、常用什么工具/功能」：
- 用量来自 ``agent_usage_events``（runs/tokens/tool_calls，按 user_id + 时间窗）。
- 工具分布来自 ``tool_names_json``（一次 run 的工具名列表），功能分布来自
  ``response_mode``（general/ppt/website/email/bigdata/office）。
- 「当前在线」来自 Redis 心跳（presence），「最近活跃」来自 users.last_active_at。

DB 聚合放线程池，避免阻塞事件循环；在线集合异步读 Redis。
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.timezone import APP_TIMEZONE, app_today, to_app_timezone
from app.db.models import AgentSessionModel, AgentUsageEventModel, UserModel
from app.services.cache_service import get_cache_service

router = APIRouter(prefix="/admin/user-analytics", tags=["admin-user-analytics"])


def _window_start(days: int) -> datetime:
    return datetime.combine(app_today() - timedelta(days=days - 1), time.min, tzinfo=APP_TIMEZONE)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    dt = to_app_timezone(value) if isinstance(value, datetime) else None
    if dt is None:
        return str(value)
    return dt.isoformat()


def _parse_tools(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(x) for x in data if x] if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def _compute_list(db: Session, days: int) -> list[dict]:
    start = _window_start(days)
    users = db.scalars(select(UserModel).order_by(UserModel.id.asc())).all()

    # 按用户聚合用量
    agg: dict[int, dict[str, int]] = defaultdict(lambda: {
        "runs": 0, "total_tokens": 0, "tool_calls": 0, "llm_calls": 0,
    })
    tool_counter: dict[int, Counter] = defaultdict(Counter)
    mode_counter: dict[int, Counter] = defaultdict(Counter)
    last_use: dict[int, Any] = {}
    events = db.scalars(
        select(AgentUsageEventModel).where(
            AgentUsageEventModel.user_id.is_not(None),
            AgentUsageEventModel.created_at >= start,
        )
    ).all()
    for e in events:
        uid = e.user_id
        a = agg[uid]
        a["runs"] += 1
        a["total_tokens"] += e.total_tokens or 0
        a["tool_calls"] += e.tool_calls or 0
        a["llm_calls"] += e.llm_calls or 0
        tool_counter[uid].update(_parse_tools(e.tool_names_json))
        mode_counter[uid][e.response_mode or "general"] += 1
        if uid not in last_use or (e.created_at and e.created_at > last_use[uid]):
            last_use[uid] = e.created_at

    sessions = dict(
        db.execute(
            select(AgentSessionModel.user_id, func.count(AgentSessionModel.session_id))
            .where(AgentSessionModel.user_id.is_not(None))
            .group_by(AgentSessionModel.user_id)
        ).all()
    )

    result = []
    for u in users:
        a = agg.get(u.id, {"runs": 0, "total_tokens": 0, "tool_calls": 0, "llm_calls": 0})
        result.append({
            "user_id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "last_active_at": _iso(u.last_active_at),
            "last_use_at": _iso(last_use.get(u.id)),
            "sessions": int(sessions.get(u.id, 0)),
            "runs": a["runs"],
            "total_tokens": a["total_tokens"],
            "tool_calls": a["tool_calls"],
            "llm_calls": a["llm_calls"],
            "top_tools": [{"name": n, "count": c} for n, c in tool_counter[u.id].most_common(5)],
            "top_modes": [{"name": n, "count": c} for n, c in mode_counter[u.id].most_common(6)],
        })
    result.sort(key=lambda r: r["total_tokens"], reverse=True)
    return result


def _compute_detail(db: Session, user_id: int, days: int) -> dict | None:
    user = db.get(UserModel, user_id)
    if user is None:
        return None
    start = _window_start(days)
    events = db.scalars(
        select(AgentUsageEventModel)
        .where(AgentUsageEventModel.user_id == user_id, AgentUsageEventModel.created_at >= start)
        .order_by(AgentUsageEventModel.created_at.asc())
    ).all()

    daily: dict[str, dict[str, int]] = {
        (start.date() + timedelta(days=i)).isoformat(): {"runs": 0, "tokens": 0, "tool_calls": 0}
        for i in range(days)
    }
    tools: Counter = Counter()
    modes: Counter = Counter()
    models: Counter = Counter()
    total_tokens = tool_calls = llm_calls = 0
    for e in events:
        key = to_app_timezone(e.created_at).date().isoformat() if e.created_at else None
        if key and key in daily:
            daily[key]["runs"] += 1
            daily[key]["tokens"] += e.total_tokens or 0
            daily[key]["tool_calls"] += e.tool_calls or 0
        total_tokens += e.total_tokens or 0
        tool_calls += e.tool_calls or 0
        llm_calls += e.llm_calls or 0
        tools.update(_parse_tools(e.tool_names_json))
        modes[e.response_mode or "general"] += 1
        if e.model_name:
            models[e.model_name] += 1

    recent_sessions = db.scalars(
        select(AgentSessionModel)
        .where(AgentSessionModel.user_id == user_id)
        .order_by(AgentSessionModel.updated_at.desc())
        .limit(10)
    ).all()

    return {
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "last_active_at": _iso(user.last_active_at),
        "summary": {
            "runs": len(events),
            "total_tokens": total_tokens,
            "tool_calls": tool_calls,
            "llm_calls": llm_calls,
        },
        "daily": [{"date": d, **v} for d, v in daily.items()],
        "tool_distribution": [{"name": n, "value": c} for n, c in tools.most_common(12)],
        "mode_distribution": [{"name": n, "value": c} for n, c in modes.most_common()],
        "model_distribution": [{"name": n, "value": c} for n, c in models.most_common(8)],
        "recent_sessions": [
            {"session_id": s.session_id, "updated_at": _iso(s.updated_at)} for s in recent_sessions
        ],
    }


@router.get("")
async def list_user_analytics(
    days: int = Query(default=14, ge=1, le=90),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    rows = await asyncio.to_thread(_compute_list, db, days)
    online = await get_cache_service().get_online_users()
    online_ids = {int(x) for x in online}
    for r in rows:
        r["online"] = r["user_id"] in online_ids
    return {"items": rows, "online_count": len(online_ids), "days": days}


@router.get("/{user_id}")
async def get_user_analytics(
    user_id: int,
    days: int = Query(default=30, ge=1, le=90),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    detail = await asyncio.to_thread(_compute_detail, db, user_id, days)
    if detail is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    online = await get_cache_service().get_online_users()
    detail["online"] = str(user_id) in online
    detail["days"] = days
    return detail
