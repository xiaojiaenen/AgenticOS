from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.timezone import app_today, to_app_timezone
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

    start_day = app_today() - timedelta(days=13)
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
    sessions = db.scalars(select(AgentSessionModel).order_by(AgentSessionModel.updated_at.desc())).all()
    user_ids = {session.user_id for session in sessions if session.user_id is not None}
    users_by_id = {
        user.id: user
        for user in db.scalars(select(UserModel).where(UserModel.id.in_(user_ids))).all()
    } if user_ids else {}

    messages_by_session: dict[str, list[AgentMessageModel]] = defaultdict(list)
    for message in db.scalars(
        select(AgentMessageModel).order_by(AgentMessageModel.session_id.asc(), AgentMessageModel.id.asc())
    ).all():
        messages_by_session[message.session_id].append(message)

    usage_by_session: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "model_names": Counter(),
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "latency_ms": 0,
        "runs": 0,
    })
    for event in db.scalars(select(AgentUsageEventModel)).all():
        item = usage_by_session[event.session_id]
        item["model_names"][event.model_name] += 1
        item["total_tokens"] += event.total_tokens
        item["input_tokens"] += event.input_tokens
        item["output_tokens"] += event.output_tokens
        item["llm_calls"] += event.llm_calls
        item["tool_calls"] += event.tool_calls
        item["latency_ms"] += event.latency_ms
        item["runs"] += 1

    items: list[ConversationListItem] = []
    query = search.strip().lower()
    for session in sessions:
        user = users_by_id.get(session.user_id) if session.user_id is not None else None
        messages = messages_by_session.get(session.session_id, [])
        texts = [_message_text(message.message_json) for message in messages]
        texts = [text for text in texts if text]
        first_message = _compact_text(texts[0] if texts else None)
        last_message = _compact_text(texts[-1] if texts else None)
        usage = usage_by_session[session.session_id]
        model_names = [name for name, _ in usage["model_names"].most_common()]
        haystack = " ".join(
            [
                session.session_id,
                session.summary or "",
                user.name if user else "",
                user.email if user else "",
                first_message or "",
                last_message or "",
            ]
        ).lower()
        if query and query not in haystack:
            continue

        runs = usage["runs"]
        items.append(
            ConversationListItem(
                session_id=session.session_id,
                user_id=session.user_id,
                user_name=user.name if user else None,
                user_email=user.email if user else None,
                summary=_compact_text(session.summary),
                first_message=first_message,
                last_message=last_message,
                message_count=len(messages),
                model_names=model_names,
                total_tokens=usage["total_tokens"],
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                llm_calls=usage["llm_calls"],
                tool_calls=usage["tool_calls"],
                avg_latency_ms=round(usage["latency_ms"] / runs) if runs else 0,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
        )

    total = len(items)
    return ConversationListResponse(items=items[offset:offset + limit], total=total)


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
    events = db.scalars(
        select(AgentUsageEventModel)
        .where(AgentUsageEventModel.session_id == session_id)
        .order_by(AgentUsageEventModel.created_at.asc())
    ).all()

    model_counter: Counter[str] = Counter()
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    llm_calls = 0
    tool_calls = 0
    latency_ms = 0
    for event in events:
        if event.model_name:
            model_counter[event.model_name] += 1
        total_tokens += event.total_tokens
        input_tokens += event.input_tokens
        output_tokens += event.output_tokens
        llm_calls += event.llm_calls
        tool_calls += event.tool_calls
        latency_ms += event.latency_ms

    return ConversationDetailResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        user_name=user.name if user else None,
        user_email=user.email if user else None,
        summary=_compact_text(session.summary, limit=240),
        message_count=message_count,
        model_names=[name for name, _ in model_counter.most_common()],
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
        avg_latency_ms=round(latency_ms / len(events)) if events else 0,
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
