from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import AgentSessionModel, AgentUsageEventModel, UserModel
from app.schemas.admin_stats import (
    DashboardDistributionItem,
    DashboardStatsResponse,
    DashboardSummary,
    DashboardTrendPoint,
    DashboardUserUsage,
)
from app.services.session_storage import load_json

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _day_key(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date().isoformat()


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    users = db.scalars(select(UserModel).order_by(UserModel.created_at.asc())).all()
    sessions = db.scalars(select(AgentSessionModel)).all()
    events = db.scalars(select(AgentUsageEventModel).order_by(AgentUsageEventModel.created_at.asc())).all()

    session_count_by_user: dict[int, int] = defaultdict(int)
    for session in sessions:
        if session.user_id is not None:
            session_count_by_user[session.user_id] += 1

    usage_by_user: dict[int, dict[str, int]] = defaultdict(lambda: {
        "runs": 0,
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "latency_ms": 0,
    })
    model_counter: Counter[str] = Counter()
    tool_counter: Counter[str] = Counter()

    start_day = datetime.now(timezone.utc).date() - timedelta(days=13)
    trend_map: dict[str, dict[str, int]] = {
        (start_day + timedelta(days=index)).isoformat(): {"runs": 0, "tokens": 0, "tool_calls": 0}
        for index in range(14)
    }

    for event in events:
        if event.user_id is not None:
            item = usage_by_user[event.user_id]
            item["runs"] += 1
            item["total_tokens"] += event.total_tokens
            item["input_tokens"] += event.input_tokens
            item["output_tokens"] += event.output_tokens
            item["llm_calls"] += event.llm_calls
            item["tool_calls"] += event.tool_calls
            item["latency_ms"] += event.latency_ms

        if event.model_name:
            model_counter[event.model_name] += 1

        for tool_name in load_json(event.tool_names_json, []):
            if isinstance(tool_name, str) and tool_name:
                tool_counter[tool_name] += 1

        key = _day_key(event.created_at)
        if key in trend_map:
            trend_map[key]["runs"] += 1
            trend_map[key]["tokens"] += event.total_tokens
            trend_map[key]["tool_calls"] += event.tool_calls

    total_runs = len(events)
    total_latency = sum(event.latency_ms for event in events)
    summary = DashboardSummary(
        total_users=len(users),
        active_users=sum(1 for user in users if user.is_active),
        total_sessions=len(sessions),
        total_runs=total_runs,
        total_tokens=sum(event.total_tokens for event in events),
        input_tokens=sum(event.input_tokens for event in events),
        output_tokens=sum(event.output_tokens for event in events),
        llm_calls=sum(event.llm_calls for event in events),
        tool_calls=sum(event.tool_calls for event in events),
        avg_latency_ms=round(total_latency / total_runs) if total_runs else 0,
    )

    user_usage = [
        DashboardUserUsage(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            sessions=session_count_by_user[user.id],
            runs=usage_by_user[user.id]["runs"],
            total_tokens=usage_by_user[user.id]["total_tokens"],
            input_tokens=usage_by_user[user.id]["input_tokens"],
            output_tokens=usage_by_user[user.id]["output_tokens"],
            llm_calls=usage_by_user[user.id]["llm_calls"],
            tool_calls=usage_by_user[user.id]["tool_calls"],
            avg_latency_ms=round(usage_by_user[user.id]["latency_ms"] / usage_by_user[user.id]["runs"])
            if usage_by_user[user.id]["runs"]
            else 0,
        )
        for user in users
    ]
    user_usage.sort(key=lambda item: item.total_tokens, reverse=True)

    return DashboardStatsResponse(
        summary=summary,
        trend=[
            DashboardTrendPoint(
                date=date,
                runs=values["runs"],
                tokens=values["tokens"],
                tool_calls=values["tool_calls"],
            )
            for date, values in trend_map.items()
        ],
        model_distribution=[
            DashboardDistributionItem(name=name, value=value)
            for name, value in model_counter.most_common(8)
        ],
        tool_distribution=[
            DashboardDistributionItem(name=name, value=value)
            for name, value in tool_counter.most_common(8)
        ],
        user_usage=user_usage,
    )
