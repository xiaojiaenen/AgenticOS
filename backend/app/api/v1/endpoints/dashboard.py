from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, exists, func, or_, select, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.core.config import get_settings
from app.core.timezone import APP_TIMEZONE, app_today, to_app_timezone
from app.db.models import AgentMessageModel, AgentProfileModel, AgentSessionModel, AgentUsageEventModel, ApprovalModel, PptArtifactModel, UserModel
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
from app.services.cache_service import get_cache_service
from app.services.session_storage import dump_json, load_json

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _day_key(value: datetime) -> str:
    converted = to_app_timezone(value)
    return converted.date().isoformat() if converted else ""


def _cached_dashboard(
    namespace: str,
    user_id: int,
    params: dict[str, Any],
    producer,
    *,
    model: type | None = None,
):
    """M6-A4：dashboard 统计结果 30s 缓存。

    key 里带 user_id（这两个端点都是 require_admin，但保留用户维度隔离，
    未来放开到普通用户时不必改 key 结构）+ 参数哈希，避免不同 days 参数串数据。
    Redis 不可用时 get_or_set_json_sync 自动旁路直查，不影响正确性。

    ``model`` 给出时把缓存里的 dict 还原成响应模型（缓存经过 JSON 往返，
    直接返回会让 FastAPI 少一层校验）；``/analytics`` 返回裸 dict，不传 model。
    """
    cache = get_cache_service()
    param_hash = hashlib.sha1(
        json.dumps(params, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    key = cache.build_cache_key(f"dashboard:{namespace}", f"u{user_id}", param_hash)
    ttl = get_settings().dashboard_cache_ttl
    cached = cache.get_or_set_json_sync(key, producer, ttl=ttl)
    if model is None or isinstance(cached, model):
        return cached
    if isinstance(cached, dict):
        return model.model_validate(cached)
    return cached


@router.get("/stats", response_model=DashboardStatsResponse)
def get_dashboard_stats(
    days: int = Query(14, ge=1, le=90),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> DashboardStatsResponse:
    return _cached_dashboard(
        "stats",
        _.id,
        {"days": days},
        lambda: _compute_dashboard_stats(days=days, db=db),
        model=DashboardStatsResponse,
    )


def _compute_dashboard_stats(*, days: int, db: Session) -> DashboardStatsResponse:
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

    start_day = app_today() - timedelta(days=days - 1)
    start_boundary = datetime.combine(start_day, time.min, tzinfo=APP_TIMEZONE)
    trend_map: dict[str, dict[str, int]] = {
        (start_day + timedelta(days=index)).isoformat(): {"runs": 0, "tokens": 0, "tool_calls": 0}
        for index in range(days)
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
        # MySQL 8.0+: JSON_TABLE 在库内聚合，避免把全表 JSON 拉到 Python 逐行解析。
        # 5.7 及更早版本不支持 JSON_TABLE（语法错误），自动回退 Python 路径。
        try:
            tool_distribution_rows = [
                (str(row.name), int(row.value))
                for row in db.execute(
                    text(
                        """
                        SELECT jt.tool_name AS name, COUNT(*) AS value
                        FROM agent_usage_events ue
                        JOIN JSON_TABLE(
                            ue.tool_names_json,
                            '$[*]' COLUMNS (tool_name VARCHAR(255) PATH '$')
                        ) jt
                        WHERE jt.tool_name IS NOT NULL AND TRIM(jt.tool_name) <> ''
                        GROUP BY jt.tool_name
                        ORDER BY COUNT(*) DESC, jt.tool_name ASC
                        LIMIT 8
                        """
                    )
                ).all()
            ]
        except (OperationalError, ProgrammingError):
            db.rollback()
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
            AgentSessionModel.agent_profile_id,
            AgentSessionModel.summary,
            AgentSessionModel.created_at,
            AgentSessionModel.updated_at,
            UserModel.name.label("user_name"),
            UserModel.email.label("user_email"),
            AgentProfileModel.name.label("agent_profile_name"),
        )
        .select_from(AgentSessionModel)
        .outerjoin(UserModel, UserModel.id == AgentSessionModel.user_id)
        .outerjoin(AgentProfileModel, AgentProfileModel.id == AgentSessionModel.agent_profile_id)
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
                agent_profile_name=row.agent_profile_name,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    user = db.get(UserModel, session.user_id) if session.user_id is not None else None
    agent_profile = db.get(AgentProfileModel, session.agent_profile_id) if session.agent_profile_id is not None else None
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
        agent_profile_name=agent_profile.name if agent_profile else None,
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



@router.get("/analytics")
def get_analytics(
    days: int = Query(14, ge=1, le=90),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return analytics data for chat history visualizations.

    M6-A4：与 /stats 共享 30s 缓存策略（key 命名空间隔离）。
    """
    return _cached_dashboard(
        "analytics",
        _.id,
        {"days": days},
        lambda: _compute_analytics(days=days, db=db),
    )


def _compute_analytics(*, days: int, db: Session) -> dict[str, Any]:
    start_day = app_today() - timedelta(days=days - 1)
    start_boundary = datetime.combine(start_day, time.min, tzinfo=APP_TIMEZONE)

    # 1. Session timeline: sessions created per day
    session_timeline: dict[str, int] = {
        (start_day + timedelta(days=i)).isoformat(): 0 for i in range(days)
    }
    for row in db.execute(
        select(AgentSessionModel.created_at)
        .where(AgentSessionModel.created_at >= start_boundary)
    ).all():
        key = _day_key(row.created_at)
        if key in session_timeline:
            session_timeline[key] += 1

    # 2. Hourly distribution: messages per hour (0-23)
    hourly_dist: dict[int, int] = {h: 0 for h in range(24)}

    # Fallback: use usage events for hourly distribution
    for row in db.execute(
        select(AgentUsageEventModel.created_at)
        .where(AgentUsageEventModel.created_at >= start_boundary)
    ).all():
        converted = to_app_timezone(row.created_at)
        if converted:
            hourly_dist[converted.hour] = hourly_dist.get(converted.hour, 0) + 1

    # 3. Tool call frequency from usage events
    tool_freq: dict[str, int] = {}
    for row in db.execute(
        select(AgentUsageEventModel.tool_calls)
        .where(AgentUsageEventModel.created_at >= start_boundary)
    ).all():
        count = int(row.tool_calls or 0)
        if count > 0:
            tool_freq["_total"] = tool_freq.get("_total", 0) + count

    # 4. Mode distribution
    mode_dist: dict[str, int] = {}
    mode_rows = [
        row
        for row in db.execute(
            select(AgentSessionModel.agent_profile_id, func.count(AgentSessionModel.session_id))
            .where(AgentSessionModel.created_at >= start_boundary)
            .group_by(AgentSessionModel.agent_profile_id)
        ).all()
        if row[0]
    ]
    # 一次性批量取涉及的 profile，避免循环内逐条 db.get（N+1）
    profile_ids = [row[0] for row in mode_rows]
    profile_names: dict[Any, str] = {}
    if profile_ids:
        profile_names = {
            profile.id: profile.name
            for profile in db.scalars(
                select(AgentProfileModel).where(AgentProfileModel.id.in_(profile_ids))
            ).all()
        }
    for row in mode_rows:
        profile_id = row[0]
        count = int(row[1])
        mode = profile_names.get(profile_id, "unknown")
        mode_dist[mode] = mode_dist.get(mode, 0) + count

    return {
        "session_timeline": [{"date": k, "count": v} for k, v in sorted(session_timeline.items())],
        "hourly_distribution": [{"hour": h, "count": hourly_dist.get(h, 0)} for h in range(24)],
        "tool_frequency": tool_freq,
        "mode_distribution": [{"mode": k, "count": v} for k, v in mode_dist.items()],
    }
@router.delete("/conversations/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    session_id: str,
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    session = db.get(AgentSessionModel, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id == session_id))
    db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.session_id == session_id))
    db.execute(delete(ApprovalModel).where(ApprovalModel.session_id == session_id))
    db.execute(delete(PptArtifactModel).where(PptArtifactModel.session_id == session_id))
    db.delete(session)
    db.commit()


# ---------------------------------------------------------------------------
# 用量统计：口径以「人」为准，凭据只做审计标签
# ---------------------------------------------------------------------------
# 这两张视图刻意分开，因为它们的**统计口径完全不同**，混在一张表里一定会
# 被读成「某个号用了多少 token」——而号是共享的，那个数字对谁都不成立。
#
# - ``/dashboard/my-usage``：用户看自己的用量。归属 = user_id。
# - ``/dashboard/usage-routes``：管理员排障视图。回答「流量实际落在哪条路由上」，
#   token 列只用来判断影响面大小，不是分摊依据。


def _usage_window_start(days: int) -> datetime:
    start_day = app_today() - timedelta(days=days - 1)
    return datetime.combine(start_day, time.min, tzinfo=APP_TIMEZONE)


def _as_iso(value: Any) -> str | None:
    """``func.max(created_at)`` 在 SQLite 上回字符串、MySQL 上回 datetime。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    converted = to_app_timezone(value)
    return converted.isoformat() if converted else None


@router.get("/my-usage")
def get_my_usage(
    days: int = Query(14, ge=1, le=90),
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """当前登录用户自己的 token 用量。

    只按 ``user_id`` 聚合，不暴露提供商/凭据 —— 那些是系统级共享资源，
    与「你用了多少」无关。``estimated_runs`` 单独给出，让页面能提示
    「其中 N 次是估算值」而不是把估算和实际计费混成一个数。
    """
    return _cached_dashboard(
        "my-usage",
        user.id,
        {"days": days},
        lambda: _compute_my_usage(days=days, user_id=user.id, db=db),
    )


def _compute_my_usage(*, days: int, user_id: int, db: Session) -> dict[str, Any]:
    start_boundary = _usage_window_start(days)

    summary = db.execute(
        select(
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.output_tokens), 0).label("output_tokens"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.tool_calls), 0).label("tool_calls"),
        )
        .where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at >= start_boundary,
        )
    ).one()

    estimated_runs = int(
        db.scalar(
            select(func.count(AgentUsageEventModel.id)).where(
                AgentUsageEventModel.user_id == user_id,
                AgentUsageEventModel.created_at >= start_boundary,
                AgentUsageEventModel.tokens_estimated.is_(True),
            )
        )
        or 0
    )

    daily: dict[str, dict[str, int]] = {
        (app_today() - timedelta(days=index)).isoformat(): {"runs": 0, "tokens": 0}
        for index in range(days - 1, -1, -1)
    }
    for row in db.execute(
        select(
            AgentUsageEventModel.created_at,
            AgentUsageEventModel.total_tokens,
        ).where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at >= start_boundary,
        )
    ).all():
        key = _day_key(row.created_at)
        if key in daily:
            daily[key]["runs"] += 1
            daily[key]["tokens"] += int(row.total_tokens or 0)

    model_rows = db.execute(
        select(
            AgentUsageEventModel.model_name.label("name"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("tokens"),
            func.count(AgentUsageEventModel.id).label("runs"),
        )
        .where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at >= start_boundary,
        )
        .group_by(AgentUsageEventModel.model_name)
        .order_by(func.sum(AgentUsageEventModel.total_tokens).desc())
        .limit(8)
    ).all()

    session_rows = db.execute(
        select(
            AgentUsageEventModel.session_id,
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("tokens"),
            func.count(AgentUsageEventModel.id).label("runs"),
            func.max(AgentUsageEventModel.created_at).label("last_at"),
        )
        .where(
            AgentUsageEventModel.user_id == user_id,
            AgentUsageEventModel.created_at >= start_boundary,
        )
        .group_by(AgentUsageEventModel.session_id)
        .order_by(func.sum(AgentUsageEventModel.total_tokens).desc())
        .limit(5)
    ).all()

    return {
        "days": days,
        "runs": int(summary.runs or 0),
        "total_tokens": int(summary.total_tokens or 0),
        "input_tokens": int(summary.input_tokens or 0),
        "output_tokens": int(summary.output_tokens or 0),
        "llm_calls": int(summary.llm_calls or 0),
        "tool_calls": int(summary.tool_calls or 0),
        "estimated_runs": estimated_runs,
        "daily": [{"date": key, **value} for key, value in daily.items()],
        "models": [
            {
                "name": str(row.name or "未知"),
                "tokens": int(row.tokens or 0),
                "runs": int(row.runs or 0),
            }
            for row in model_rows
        ],
        "sessions": [
            {
                "session_id": str(row.session_id),
                "tokens": int(row.tokens or 0),
                "runs": int(row.runs or 0),
                "last_at": _as_iso(row.last_at),
            }
            for row in session_rows
        ],
    }


@router.get("/usage-routes")
def get_usage_routes(
    days: int = Query(14, ge=1, le=90),
    _: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """管理员排障视图：流量落在哪个提供商 / 哪条凭据 / 哪个模型上。

    **这里的 token 数不是分摊依据。** 企业网关的账号是系统级共享池，一个号
    被多个用户共用，按号聚合出来的 token 数不能回推给任何个体。要看「谁用了
    多少」用 ``/dashboard/stats``（按 user_id）或用户自己的 ``/my-usage``。

    这个端点回答的是另外三个问题：

    - 切了提供商之后流量真的转过去了吗（``legacy_runs`` / ``env_fallback_runs``）
    - 某个号撞 401 时影响面多大（``accounts[].runs``）
    - 用量库里记的模型名对不对（``models[].name`` 取自网关上实际发出的模型）
    """
    return _cached_dashboard(
        "usage-routes",
        _.id,
        {"days": days},
        lambda: _compute_usage_routes(days=days, db=db),
    )


def _compute_usage_routes(*, days: int, db: Session) -> dict[str, Any]:
    from app.services.llm_providers.spec import ENV_PROVIDER_SLUG

    start_boundary = _usage_window_start(days)
    in_window = AgentUsageEventModel.created_at >= start_boundary

    totals = db.execute(
        select(
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
        ).where(in_window)
    ).one()

    # 迁移前的历史行：既没有 provider_id 也没有 slug，只能整体标成「无路由信息」，
    # 不能归到任何提供商头上（归了就等于编数据）。
    legacy_runs = int(
        db.scalar(
            select(func.count(AgentUsageEventModel.id)).where(
                in_window,
                AgentUsageEventModel.provider_id.is_(None),
                AgentUsageEventModel.provider_slug.is_(None),
            )
        )
        or 0
    )
    env_fallback_runs = int(
        db.scalar(
            select(func.count(AgentUsageEventModel.id)).where(
                in_window,
                AgentUsageEventModel.provider_slug == ENV_PROVIDER_SLUG,
            )
        )
        or 0
    )

    provider_rows = db.execute(
        select(
            AgentUsageEventModel.provider_id,
            AgentUsageEventModel.provider_slug,
            AgentUsageEventModel.provider_name,
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.max(AgentUsageEventModel.created_at).label("last_at"),
        )
        .where(in_window, AgentUsageEventModel.provider_slug.is_not(None))
        .group_by(
            AgentUsageEventModel.provider_id,
            AgentUsageEventModel.provider_slug,
            AgentUsageEventModel.provider_name,
        )
        .order_by(func.count(AgentUsageEventModel.id).desc())
    ).all()

    account_rows = db.execute(
        select(
            AgentUsageEventModel.credential_id,
            AgentUsageEventModel.account_label,
            AgentUsageEventModel.provider_slug,
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.llm_calls), 0).label("llm_calls"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
            func.max(AgentUsageEventModel.created_at).label("last_at"),
        )
        .where(in_window, AgentUsageEventModel.credential_id.is_not(None))
        .group_by(
            AgentUsageEventModel.credential_id,
            AgentUsageEventModel.account_label,
            AgentUsageEventModel.provider_slug,
        )
        .order_by(func.count(AgentUsageEventModel.id).desc())
    ).all()

    model_rows = db.execute(
        select(
            AgentUsageEventModel.model_name.label("name"),
            func.count(AgentUsageEventModel.id).label("runs"),
            func.coalesce(func.sum(AgentUsageEventModel.total_tokens), 0).label("total_tokens"),
        )
        .where(in_window, AgentUsageEventModel.model_name.is_not(None))
        .group_by(AgentUsageEventModel.model_name)
        .order_by(func.count(AgentUsageEventModel.id).desc())
        .limit(10)
    ).all()

    estimated_runs = int(
        db.scalar(
            select(func.count(AgentUsageEventModel.id)).where(
                in_window, AgentUsageEventModel.tokens_estimated.is_(True)
            )
        )
        or 0
    )

    return {
        "days": days,
        "totals": {
            "runs": int(totals.runs or 0),
            "total_tokens": int(totals.total_tokens or 0),
            "estimated_runs": estimated_runs,
            # 这两项是「配置没生效」的显式信号，别当噪音删掉
            "legacy_runs": legacy_runs,
            "env_fallback_runs": env_fallback_runs,
        },
        "providers": [
            {
                "provider_id": row.provider_id,
                "provider_slug": row.provider_slug,
                "provider_name": row.provider_name,
                "runs": int(row.runs or 0),
                "llm_calls": int(row.llm_calls or 0),
                "total_tokens": int(row.total_tokens or 0),
                "last_at": _as_iso(row.last_at),
            }
            for row in provider_rows
        ],
        "accounts": [
            {
                "credential_id": row.credential_id,
                "account_label": row.account_label or "",
                "provider_slug": row.provider_slug,
                "runs": int(row.runs or 0),
                "llm_calls": int(row.llm_calls or 0),
                "total_tokens": int(row.total_tokens or 0),
                "last_at": _as_iso(row.last_at),
            }
            for row in account_rows
        ],
        "models": [
            {
                "name": str(row.name),
                "runs": int(row.runs or 0),
                "total_tokens": int(row.total_tokens or 0),
            }
            for row in model_rows
        ],
    }
