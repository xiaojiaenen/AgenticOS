"""个人年度报告（Wrapped）统计。

把 ``agent_usage_events`` 按自然年（APP_TIMEZONE）聚合成一份有温度的回顾：
总量、活跃天数、连续打卡、最忙时段、常用功能/工具/模型，以及一个由数据
推导出的「年度 persona」标签。纯确定性计算，不依赖 LLM，离线也能跑。

供三处复用：用户端 ``GET /wrapped/{year}``、邮件模板、1 月 1 日 cron 群发。
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import APP_TIMEZONE, to_app_timezone
from app.db.models import AgentUsageEventModel, UserModel

# 功能 → 年度称号（取使用最多的 mode）
_MODE_PERSONA = {
    "ppt": "PPT 大师",
    "website": "建站达人",
    "email": "邮件管家",
    "bigdata": "数据极客",
    "office": "办公效率王",
    "general": "全能探索者",
}
_MODE_NAME = {
    "general": "通用", "ppt": "PPT", "website": "网站",
    "email": "邮箱", "bigdata": "大数据", "office": "办公",
}
_WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _parse_tools(raw: str | None) -> list[str]:
    try:
        data = json.loads(raw or "[]")
        return [str(x) for x in data if x] if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []


def _longest_streak(days: set[str]) -> int:
    """连续活跃天数（按 ISO 日期字符串）。"""
    if not days:
        return 0
    from datetime import date, timedelta

    parsed = sorted(date.fromisoformat(d) for d in days)
    best = cur = 1
    for prev, nxt in zip(parsed, parsed[1:]):
        if (nxt - prev).days == 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def compute_wrapped(db: Session, user_id: int, year: int) -> dict:
    user = db.get(UserModel, user_id)
    start = datetime(year, 1, 1, tzinfo=APP_TIMEZONE)
    end = datetime(year + 1, 1, 1, tzinfo=APP_TIMEZONE)
    events = db.scalars(
        select(AgentUsageEventModel)
        .where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at >= start,
            AgentUsageEventModel.created_at < end,
        )
        .order_by(AgentUsageEventModel.created_at.asc())
    ).all()

    total_tokens = input_tokens = output_tokens = tool_calls = llm_calls = latency_ms = 0
    modes: Counter = Counter()
    tools: Counter = Counter()
    models: Counter = Counter()
    hours: Counter = Counter()
    weekdays: Counter = Counter()
    active_days: set[str] = set()
    sessions: set[str] = set()
    first_at = last_at = None

    for e in events:
        total_tokens += e.total_tokens or 0
        input_tokens += e.input_tokens or 0
        output_tokens += e.output_tokens or 0
        tool_calls += e.tool_calls or 0
        llm_calls += e.llm_calls or 0
        latency_ms += e.latency_ms or 0
        modes[e.response_mode or "general"] += 1
        tools.update(_parse_tools(e.tool_names_json))
        if e.model_name:
            models[e.model_name] += 1
        if e.session_id:
            sessions.add(e.session_id)
        dt = to_app_timezone(e.created_at) if e.created_at else None
        if dt:
            active_days.add(dt.date().isoformat())
            hours[dt.hour] += 1
            weekdays[dt.weekday()] += 1
            if first_at is None:
                first_at = dt
            last_at = dt

    top_mode = modes.most_common(1)[0][0] if modes else None
    busiest_hour = hours.most_common(1)[0][0] if hours else None
    busiest_weekday = weekdays.most_common(1)[0][0] if weekdays else None

    return {
        "year": year,
        "user_id": user_id,
        "user_name": user.name if user else "",
        "has_data": bool(events),
        "total_runs": len(events),
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "tool_calls": tool_calls,
        "llm_calls": llm_calls,
        "conversation_count": len(sessions),
        "active_days": len(active_days),
        "longest_streak": _longest_streak(active_days),
        "total_hours": round(latency_ms / 3_600_000, 1),
        "persona": _MODE_PERSONA.get(top_mode, "全能探索者") if top_mode else "蓄势待发",
        "top_mode": top_mode,
        "top_mode_name": _MODE_NAME.get(top_mode, top_mode) if top_mode else None,
        "busiest_hour": busiest_hour,
        "busiest_weekday": _WEEKDAY[busiest_weekday] if busiest_weekday is not None else None,
        "first_activity": first_at.date().isoformat() if first_at else None,
        "last_activity": last_at.date().isoformat() if last_at else None,
        "mode_distribution": [
            {"name": _MODE_NAME.get(n, n), "value": c} for n, c in modes.most_common()
        ],
        "top_tools": [{"name": n, "count": c} for n, c in tools.most_common(8)],
        "top_models": [{"name": n, "count": c} for n, c in models.most_common(5)],
    }


def years_with_data(db: Session, user_id: int) -> list[int]:
    """该用户有用量记录的年份（倒序），供前端年份选择。"""
    rows = db.scalars(
        select(AgentUsageEventModel.created_at).where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at.is_not(None),
        )
    ).all()
    years = {to_app_timezone(d).year for d in rows if d}
    return sorted(years, reverse=True)
