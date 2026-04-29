from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.timezone import APP_TIMEZONE, app_today, to_app_timezone
from app.db.models import AgentMessageModel, AgentSessionModel, AgentUsageEventModel, ApprovalModel, PptArtifactModel, UserModel
from app.schemas.admin_stats import (
    DashboardDistributionItem,
    DashboardStatsResponse,
    DashboardSummary,
    DashboardTrendPoint,
    DashboardUserUsage,
)
from app.schemas.conversations import (
    ConversationDetailMessage,
    ConversationDetailResponse,
    ConversationToolCall,
    ConversationToolResult,
    ConversationListItem,
    ConversationListResponse,
)
from app.services.session_storage import dump_json, load_json

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _day_key(value: datetime) -> str:
    converted = to_app_timezone(value)
    return converted.date().isoformat() if converted else ""


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    users = db.scalars(select(UserModel).order_by(UserModel.created_at.asc())).all()
    session_count_by_user = {
        int(user_id): int(count)
        for user_id, count in db.execute(
            select(AgentSessionModel.user_id, func.count(AgentSessionModel.session_id))
            .where(AgentSessionModel.user_id.is_not(None))
            .group_by(AgentSessionModel.user_id)
        ).all()
        if user_id is not None
    }

    usage_by_user: dict[int, dict[str, int]] = {}
    for row in db.execute(
        select(
            AgentUsageEventModel.user_id,
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.tool_calls), 0).label("tool_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.latency_ms), 0).label("latency_ms"),
        )
        .where(AgentUsageEventModel.user_id.is_not(None))
        .group_by(AgentUsageEventModel.user_id)
    ).all():
        if row.user_id is None:
            continue
        usage_by_user[int(row.user_id)] = {
            "runs": int(row.runs or 0),
            "total_tokens": int(row.total_tokens or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "llm_calls": int(row.llm_calls or 0),
            "tool_calls": int(row.tool_calls or 0),
            "latency_ms": int(row.latency_ms or 0),
        }

    start_day = app_today() - timedelta(days=13)
    start_boundary = datetime.combine(start_day, time.min, tzinfo=APP_TIMEZONE)
    trend_map: dict[str, dict[str, int]] = {
        (start_day + timedelta(days=index)).isoformat(): {"runs": 0, "tokens": 0, "tool_calls": 0}
        for index in range(14)
    }

    for row in db.execute(
        select(
            AgentUsageEventModel.created_at,
            AgentUsageEventModel.total_tokens,
            AgentUsageEventModel.tool_calls,
        )
        .where(AgentUsageEventModel.created_at >= start_boundary)
        .order_by(AgentUsageEventModel.created_at.asc())
    ).all():
        key = _day_key(row.created_at)
        if key in trend_map:
            trend_map[key]["runs"] += 1
            trend_map[key]["tokens"] += int(row.total_tokens or 0)
            trend_map[key]["tool_calls"] += int(row.tool_calls or 0)

    summary_row = db.execute(
        select(
            func.count(AgentUsageEventModel.id).label("total_runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.tool_calls), 0).label("tool_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.latency_ms), 0).label("latency_ms"),
        )
    ).one()
    total_runs = int(summary_row.total_runs or 0)
    total_latency = int(summary_row.latency_ms or 0)

    model_distribution_rows = db.execute(
        select(
            AgentUsageEventModel.model_name.label("name"),
            func.count(AgentUsageEventModel.id).label("value"),
        )
        .where(AgentUsageEventModel.model_name.is_not(None))
        .group_by(AgentUsageEventModel.model_name)
        .order_by(func.count(AgentUsageEventModel.id).desc(), AgentUsageEventModel.model_name.asc())
        .limit(8)
    ).all()

    tool_distribution_rows: list[tuple[str, int]] = []
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        tool_distribution_rows = [
            (str(row.name), int(row.value))
            for row in db.execute(
                text(
                    """
                    SELECT json_each.value AS name, COUNT(*) AS value
                    FROM agent_usage_events, json_each(agent_usage_events.tool_names_json)
                    WHERE json_each.value IS NOT NULL AND TRIM(json_each.value) <> ''
                    GROUP BY json_each.value
                    ORDER BY COUNT(*) DESC, json_each.value ASC
                    LIMIT 8
                    """
                )
            ).all()
        ]
    else:
        tool_counter: Counter[str] = Counter()
        for raw_tool_names in db.scalars(select(AgentUsageEventModel.tool_names_json)).all():
            for tool_name in load_json(raw_tool_names, []):
                if isinstance(tool_name, str) and tool_name:
                    tool_counter[tool_name] += 1
        tool_distribution_rows = tool_counter.most_common(8)

    summary = DashboardSummary(
        total_users=len(users),
        active_users=sum(1 for user in users if user.is_active),
        total_sessions=db.scalar(select(func.count(AgentSessionModel.session_id))) or 0,
        total_runs=total_runs,
        total_tokens=int(summary_row.total_tokens or 0),
        input_tokens=int(summary_row.input_tokens or 0),
        output_tokens=int(summary_row.output_tokens or 0),
        llm_calls=int(summary_row.llm_calls or 0),
        tool_calls=int(summary_row.tool_calls or 0),
        avg_latency_ms=round(total_latency / total_runs) if total_runs else 0,
    )

    user_usage = [
        DashboardUserUsage(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            sessions=session_count_by_user.get(user.id, 0),
            runs=usage_by_user.get(user.id, {}).get("runs", 0),
            total_tokens=usage_by_user.get(user.id, {}).get("total_tokens", 0),
            input_tokens=usage_by_user.get(user.id, {}).get("input_tokens", 0),
            output_tokens=usage_by_user.get(user.id, {}).get("output_tokens", 0),
            llm_calls=usage_by_user.get(user.id, {}).get("llm_calls", 0),
            tool_calls=usage_by_user.get(user.id, {}).get("tool_calls", 0),
            avg_latency_ms=round(usage_by_user.get(user.id, {}).get("latency_ms", 0) / usage_by_user.get(user.id, {}).get("runs", 0))
            if usage_by_user.get(user.id, {}).get("runs", 0)
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
            DashboardDistributionItem(name=str(row.name), value=int(row.value))
            for row in model_distribution_rows
        ],
        tool_distribution=[
            DashboardDistributionItem(name=name, value=value)
            for name, value in tool_distribution_rows
        ],
        user_usage=user_usage,
    )


def _message_text(message_json: str) -> str:
    payload = load_json(message_json, {})
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content") or payload.get("text") or payload.get("message") or ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _compact_text(value: str | None, limit: int = 120) -> str | None:
    if not value:
        return None
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[:limit]}..."


def _message_role(message_json: str) -> str | None:
    payload = load_json(message_json, {})
    if not isinstance(payload, dict):
        return None

    role = payload.get("role")
    if isinstance(role, str) and role:
        return role

    author = payload.get("author")
    if isinstance(author, dict):
        author_role = author.get("role")
        if isinstance(author_role, str) and author_role:
            return author_role

    return None


def _message_payload(message_json: str) -> dict[str, Any]:
    payload = load_json(message_json, {})
    return payload if isinstance(payload, dict) else {}


def _message_reasoning_text(payload: dict[str, Any]) -> str | None:
    reasoning = payload.get("reasoning_content") or payload.get("reasoningText") or payload.get("reasoning")
    return reasoning if isinstance(reasoning, str) and reasoning.strip() else None


def _message_tool_calls(payload: dict[str, Any]) -> list[ConversationToolCall]:
    raw_calls = payload.get("tool_calls") or payload.get("toolCalls") or []
    if not isinstance(raw_calls, list):
        return []

    calls: list[ConversationToolCall] = []
    for item in raw_calls:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = function.get("name") or item.get("name") or item.get("tool_name") or "工具调用"
        arguments = function.get("arguments") or item.get("arguments") or item.get("args")
        calls.append(
            ConversationToolCall(
                id=item.get("id") or item.get("tool_call_id"),
                name=str(name),
                arguments=arguments if isinstance(arguments, dict) else None,
            )
        )
    return calls


def _message_tool_results(payload: dict[str, Any]) -> list[ConversationToolResult]:
    raw_results = payload.get("tool_results") or payload.get("toolResults")
    results: list[ConversationToolResult] = []
    if isinstance(raw_results, list):
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            result = item.get("result") or item.get("output") or item.get("content") or ""
            results.append(
                ConversationToolResult(
                    tool_call_id=item.get("tool_call_id") or item.get("id"),
                    name=item.get("name") or item.get("tool_name"),
                    status=str(item.get("status") or "success"),
                    result=result if isinstance(result, str) else dump_json(result),
                )
            )
    if payload.get("role") == "tool":
        result = payload.get("content") or payload.get("result") or ""
        results.append(
            ConversationToolResult(
                tool_call_id=payload.get("tool_call_id"),
                name=payload.get("name") or payload.get("tool_name"),
                status=str(payload.get("status") or "success"),
                result=result if isinstance(result, str) else dump_json(result),
            )
        )
    return results


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    search: str = Query(default="", max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    query = search.strip().lower()
    statement = (
        select(
            AgentSessionModel.session_id,
            AgentSessionModel.user_id,
            AgentSessionModel.summary,
            AgentSessionModel.created_at,
            AgentSessionModel.updated_at,
            UserModel.name.label("user_name"),
            UserModel.email.label("user_email"),
        )
        .select_from(AgentSessionModel)
        .outerjoin(UserModel, UserModel.id == AgentSessionModel.user_id)
    )
    if query:
        like_query = f"%{query}%"
        message_matches = exists(
            select(AgentMessageModel.id).where(
                AgentMessageModel.session_id == AgentSessionModel.session_id,
                func.lower(AgentMessageModel.message_json).like(like_query),
            )
        )
        statement = statement.where(
            or_(
                func.lower(AgentSessionModel.session_id).like(like_query),
                func.lower(func.coalesce(AgentSessionModel.summary, "")).like(like_query),
                func.lower(func.coalesce(UserModel.name, "")).like(like_query),
                func.lower(func.coalesce(UserModel.email, "")).like(like_query),
                message_matches,
            )
        )

    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    session_rows = db.execute(
        statement.order_by(AgentSessionModel.updated_at.desc()).offset(offset).limit(limit)
    ).all()
    session_ids = [str(row.session_id) for row in session_rows]
    if not session_ids:
        return ConversationListResponse(items=[], total=int(total))

    message_meta_subquery = (
        select(
            AgentMessageModel.session_id.label("session_id"),
            func.min(AgentMessageModel.id).label("first_id"),
            func.max(AgentMessageModel.id).label("last_id"),
            func.count(AgentMessageModel.id).label("message_count"),
        )
        .where(AgentMessageModel.session_id.in_(session_ids))
        .group_by(AgentMessageModel.session_id)
        .subquery()
    )
    message_meta_rows = db.execute(select(message_meta_subquery)).all()
    message_ids = {
        int(message_id)
        for row in message_meta_rows
        for message_id in (row.first_id, row.last_id)
        if message_id is not None
    }
    messages_by_id = {
        message.id: message
        for message in db.scalars(select(AgentMessageModel).where(AgentMessageModel.id.in_(message_ids))).all()
    } if message_ids else {}
    message_meta_by_session = {str(row.session_id): row for row in message_meta_rows}

    usage_by_session: dict[str, dict[str, int]] = {}
    for row in db.execute(
        select(
            AgentUsageEventModel.session_id,
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.tool_calls), 0).label("tool_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.latency_ms), 0).label("latency_ms"),
        )
        .where(AgentUsageEventModel.session_id.in_(session_ids))
        .group_by(AgentUsageEventModel.session_id)
    ).all():
        usage_by_session[str(row.session_id)] = {
            "runs": int(row.runs or 0),
            "total_tokens": int(row.total_tokens or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "llm_calls": int(row.llm_calls or 0),
            "tool_calls": int(row.tool_calls or 0),
            "latency_ms": int(row.latency_ms or 0),
        }

    model_names_by_session: dict[str, list[str]] = defaultdict(list)
    for row in db.execute(
        select(
            AgentUsageEventModel.session_id,
            AgentUsageEventModel.model_name,
            func.count(AgentUsageEventModel.id).label("model_runs"),
        )
        .where(
            AgentUsageEventModel.session_id.in_(session_ids),
            AgentUsageEventModel.model_name.is_not(None),
        )
        .group_by(AgentUsageEventModel.session_id, AgentUsageEventModel.model_name)
        .order_by(
            AgentUsageEventModel.session_id.asc(),
            func.count(AgentUsageEventModel.id).desc(),
            AgentUsageEventModel.model_name.asc(),
        )
    ).all():
        model_names_by_session[str(row.session_id)].append(str(row.model_name))

    items = []
    for row in session_rows:
        session_id = str(row.session_id)
        message_meta = message_meta_by_session.get(session_id)
        first_message = messages_by_id.get(message_meta.first_id) if message_meta and message_meta.first_id else None
        last_message = messages_by_id.get(message_meta.last_id) if message_meta and message_meta.last_id else None
        usage = usage_by_session.get(
            session_id,
            {
                "runs": 0,
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "llm_calls": 0,
                "tool_calls": 0,
                "latency_ms": 0,
            },
        )
        runs = usage["runs"]
        items.append(
            ConversationListItem(
                session_id=session_id,
                user_id=row.user_id,
                user_name=row.user_name,
                user_email=row.user_email,
                summary=_compact_text(row.summary),
                first_message=_compact_text(_message_text(first_message.message_json) if first_message else None),
                last_message=_compact_text(_message_text(last_message.message_json) if last_message else None),
                message_count=int(message_meta.message_count) if message_meta else 0,
                model_names=model_names_by_session.get(session_id, []),
                total_tokens=usage["total_tokens"],
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                llm_calls=usage["llm_calls"],
                tool_calls=usage["tool_calls"],
                avg_latency_ms=round(usage["latency_ms"] / runs) if runs else 0,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )

    return ConversationListResponse(items=items, total=int(total))


@router.get("/conversations/{session_id}", response_model=ConversationDetailResponse)
def get_conversation_detail(
    session_id: str,
    messages_offset: int = Query(default=0, ge=0),
    messages_limit: int = Query(default=20, ge=1, le=100),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    session = db.get(AgentSessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user = db.get(UserModel, session.user_id) if session.user_id is not None else None
    message_count = db.scalar(
        select(func.count(AgentMessageModel.id)).where(AgentMessageModel.session_id == session_id)
    ) or 0
    messages = db.scalars(
        select(AgentMessageModel)
        .where(AgentMessageModel.session_id == session_id)
        .order_by(AgentMessageModel.id.asc())
        .offset(messages_offset)
        .limit(messages_limit)
    ).all()
    usage_summary = db.execute(
        select(
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.tool_calls), 0).label("tool_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.latency_ms), 0).label("latency_ms"),
        )
        .where(AgentUsageEventModel.session_id == session_id)
    ).one()
    model_names = [
        str(row.model_name)
        for row in db.execute(
            select(
                AgentUsageEventModel.model_name,
                func.count(AgentUsageEventModel.id).label("model_runs"),
            )
            .where(
                AgentUsageEventModel.session_id == session_id,
                AgentUsageEventModel.model_name.is_not(None),
            )
            .group_by(AgentUsageEventModel.model_name)
            .order_by(func.count(AgentUsageEventModel.id).desc(), AgentUsageEventModel.model_name.asc())
        ).all()
    ]

    return ConversationDetailResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        user_name=user.name if user else None,
        user_email=user.email if user else None,
        summary=_compact_text(session.summary, limit=240),
        message_count=message_count,
        model_names=model_names,
        total_tokens=int(usage_summary.total_tokens or 0),
        input_tokens=int(usage_summary.input_tokens or 0),
        output_tokens=int(usage_summary.output_tokens or 0),
        llm_calls=int(usage_summary.llm_calls or 0),
        tool_calls=int(usage_summary.tool_calls or 0),
        avg_latency_ms=round(int(usage_summary.latency_ms or 0) / int(usage_summary.runs or 0))
        if usage_summary.runs
        else 0,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages_offset=messages_offset,
        messages_limit=messages_limit,
        messages=[
            ConversationDetailMessage(
                id=message.id,
                role=_message_role(message.message_json),
                text=_message_text(message.message_json),
                reasoning_text=_message_reasoning_text(payload),
                tool_calls=_message_tool_calls(payload),
                tool_results=_message_tool_results(payload),
                created_at=message.created_at,
            )
            for message in messages
            for payload in [_message_payload(message.message_json)]
        ],
    )


@router.delete("/conversations/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    session_id: str,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    session = db.get(AgentSessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id == session_id))
    db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.session_id == session_id))
    db.execute(delete(ApprovalModel).where(ApprovalModel.session_id == session_id))
    db.execute(delete(PptArtifactModel).where(PptArtifactModel.session_id == session_id))
    db.delete(session)
    db.commit()
