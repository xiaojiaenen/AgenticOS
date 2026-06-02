from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.timezone import isoformat_app_timezone
from app.db.models import AgentMessageModel, AgentSessionModel
from app.db.session import create_db_session


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _iso(value: datetime | None) -> str | None:
    return isoformat_app_timezone(value)


class DatabaseAgentStorage:
    """Wuwei storage implementation backed by SQLAlchemy.

    All sync DB operations run via asyncio.to_thread to avoid blocking
    the event loop during long-running SSE stream requests.
    """

    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def save_meta(self, session) -> None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session.session_id)
                if row is None:
                    row = AgentSessionModel(session_id=session.session_id, system_prompt=session.system_prompt)
                    db.add(row)

                metadata = getattr(session, "metadata", {}) or {}
                row.system_prompt = session.system_prompt
                row.user_id = row.user_id or metadata.get("user_id")
                row.agent_profile_id = metadata.get("agent_profile_id") or row.agent_profile_id
                row.max_steps = session.max_steps
                row.parallel_tool_calls = session.parallel_tool_calls
                row.summary = getattr(session, "summary", None)
                row.metadata_json = _dumps(metadata)
                row.last_usage_json = _dumps(getattr(session, "last_usage", {}) or {})
                row.last_latency_ms = getattr(session, "last_latency_ms", 0) or 0
                row.last_llm_calls = getattr(session, "last_llm_calls", 0) or 0
                db.commit()
        await asyncio.to_thread(_run)

    async def append_message(self, session_id: str, message) -> None:
        def _run():
            import time
            for attempt in range(3):
                try:
                    with self.session_factory() as db:
                        db.add(
                            AgentMessageModel(
                                session_id=session_id,
                                message_json=message.model_dump_json(exclude_none=True),
                            )
                        )
                        db.commit()
                    return
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise
        await asyncio.to_thread(_run)

    async def load(self, session_id: str):
        from wuwei.agent.session import AgentSession
        from wuwei.llm import Message

        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None

                session = AgentSession(
                    session_id=row.session_id,
                    system_prompt=row.system_prompt,
                    max_steps=row.max_steps,
                    parallel_tool_calls=row.parallel_tool_calls,
                    summary=row.summary,
                    metadata=_loads(row.metadata_json, {}),
                )
                if row.user_id is not None:
                    session.metadata["user_id"] = row.user_id
                if row.agent_profile_id is not None:
                    session.metadata["agent_profile_id"] = row.agent_profile_id
                session.last_usage = _loads(row.last_usage_json, {})
                session.last_latency_ms = row.last_latency_ms
                session.last_llm_calls = row.last_llm_calls

                messages = db.scalars(
                    select(AgentMessageModel)
                    .where(AgentMessageModel.session_id == session_id)
                    .order_by(AgentMessageModel.id.asc())
                ).all()
                for message in messages:
                    # wuwei 2.1 的 BaseMessage 严格验证 tool_calls 不能为 null，
                    # 但旧数据或 LLM 返回可能存储了 "tool_calls": null，清理后再反序列化。
                    raw = message.message_json
                    if '"tool_calls": null' in raw:
                        raw = raw.replace('"tool_calls": null', '"tool_calls": []')
                    if '"reasoning_content": null' in raw:
                        raw = raw.replace('"reasoning_content": null', '"reasoning_content": ""')
                    try:
                        session.context._messages.append(Message.model_validate_json(raw))
                    except Exception:
                        # 最后兜底：跳过无法解析的消息
                        continue

                return session
        return await asyncio.to_thread(_run)

    async def delete(self, session_id: str) -> None:
        def _run():
            with self.session_factory() as db:
                db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id == session_id))
                row = db.get(AgentSessionModel, session_id)
                if row is not None:
                    db.delete(row)
                db.commit()
        await asyncio.to_thread(_run)

    async def describe(self, session_id: str) -> dict[str, Any] | None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None

                message_count = db.scalar(
                    select(func.count(AgentMessageModel.id)).where(AgentMessageModel.session_id == session_id)
                ) or 0
                return {
                    "session_id": row.session_id,
                    "user_id": row.user_id,
                    "agent_profile_id": row.agent_profile_id,
                    "summary": row.summary,
                    "metadata": _loads(row.metadata_json, {}),
                    "last_usage": _loads(row.last_usage_json, {}),
                    "last_latency_ms": row.last_latency_ms,
                    "last_llm_calls": row.last_llm_calls,
                    "message_count": message_count,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                    "storage": "sqlalchemy",
                }
        return await asyncio.to_thread(_run)

    async def get_owner_id(self, session_id: str) -> int | None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is None:
                    return None
                return row.user_id
        return await asyncio.to_thread(_run)

    async def list_user_sessions(self, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
        def _run():
            with self.session_factory() as db:
                rows = db.scalars(
                    select(AgentSessionModel)
                    .where(AgentSessionModel.user_id == user_id)
                    .order_by(AgentSessionModel.updated_at.desc())
                    .limit(limit)
                ).all()

                session_ids = [row.session_id for row in rows]
                if not session_ids:
                    return []

                message_counts = dict(
                    db.execute(
                        select(
                            AgentMessageModel.session_id,
                            func.count(AgentMessageModel.id),
                        )
                        .where(AgentMessageModel.session_id.in_(session_ids))
                        .group_by(AgentMessageModel.session_id)
                    ).all()
                )

                sessions = []
                for row in rows:
                    sessions.append({
                        "session_id": row.session_id,
                        "summary": row.summary,
                        "metadata": _loads(row.metadata_json, {}),
                        "message_count": message_counts.get(row.session_id, 0),
                        "created_at": _iso(row.created_at),
                        "updated_at": _iso(row.updated_at),
                    })
                return sessions
        return await asyncio.to_thread(_run)

    async def get_message_count(self, session_id: str) -> int:
        """Return the number of messages in a session."""
        def _run():
            with self.session_factory() as db:
                return db.scalar(
                    select(func.count(AgentMessageModel.id)).where(
                        AgentMessageModel.session_id == session_id
                    )
                ) or 0
        return await asyncio.to_thread(_run)

    async def assign_owner(self, session_id: str, user_id: int) -> None:
        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is not None and row.user_id is None:
                    row.user_id = user_id
                    metadata = _loads(row.metadata_json, {})
                    metadata["user_id"] = user_id
                    row.metadata_json = _dumps(metadata)
                    db.commit()
        await asyncio.to_thread(_run)

    async def assign_agent_profile(self, session_id: str, agent_profile_id: int | None) -> None:
        if agent_profile_id is None:
            return

        def _run():
            with self.session_factory() as db:
                row = db.get(AgentSessionModel, session_id)
                if row is not None and row.agent_profile_id is None:
                    row.agent_profile_id = agent_profile_id
                    metadata = _loads(row.metadata_json, {})
                    metadata["agent_profile_id"] = agent_profile_id
                    row.metadata_json = _dumps(metadata)
                    db.commit()
        await asyncio.to_thread(_run)


def dump_json(value: Any) -> str:
    return _dumps(value)


def load_json(value: str | None, default: Any) -> Any:
    return _loads(value, default)


def parse_approval_sub_tools(json_str: str | None) -> list[str]:
    """Parse a JSON array of sub-tool names from a string, returning [] on failure."""
    if not json_str:
        return []
    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def slugify(value: str, *, fallback: str = "agent") -> str:
    """Convert a string to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower().replace("_", "-"))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or fallback
