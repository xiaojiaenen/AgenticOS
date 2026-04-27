from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
    return value.isoformat() if value else None


class DatabaseAgentStorage:
    """Wuwei storage implementation backed by SQLAlchemy.

    The schema is intentionally generic: switching to MySQL later should only
    require changing DATABASE_URL to a MySQL SQLAlchemy URL.
    """

    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def save_meta(self, session) -> None:
        with self.session_factory() as db:
            row = db.get(AgentSessionModel, session.session_id)
            if row is None:
                row = AgentSessionModel(session_id=session.session_id, system_prompt=session.system_prompt)
                db.add(row)

            row.system_prompt = session.system_prompt
            row.max_steps = session.max_steps
            row.parallel_tool_calls = session.parallel_tool_calls
            row.summary = getattr(session, "summary", None)
            row.metadata_json = _dumps(getattr(session, "metadata", {}) or {})
            row.last_usage_json = _dumps(getattr(session, "last_usage", {}) or {})
            row.last_latency_ms = getattr(session, "last_latency_ms", 0) or 0
            row.last_llm_calls = getattr(session, "last_llm_calls", 0) or 0
            db.commit()

    async def append_message(self, session_id: str, message) -> None:
        with self.session_factory() as db:
            db.add(
                AgentMessageModel(
                    session_id=session_id,
                    message_json=message.model_dump_json(exclude_none=True),
                )
            )
            db.commit()

    async def load(self, session_id: str):
        from wuwei.agent.session import AgentSession
        from wuwei.llm import Message

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
            session.last_usage = _loads(row.last_usage_json, {})
            session.last_latency_ms = row.last_latency_ms
            session.last_llm_calls = row.last_llm_calls

            messages = db.scalars(
                select(AgentMessageModel)
                .where(AgentMessageModel.session_id == session_id)
                .order_by(AgentMessageModel.id.asc())
            ).all()
            for message in messages:
                session.context._messages.append(Message.model_validate_json(message.message_json))

            return session

    async def delete(self, session_id: str) -> None:
        with self.session_factory() as db:
            db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id == session_id))
            row = db.get(AgentSessionModel, session_id)
            if row is not None:
                db.delete(row)
            db.commit()

    async def describe(self, session_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.get(AgentSessionModel, session_id)
            if row is None:
                return None

            message_count = len(
                db.scalars(select(AgentMessageModel.id).where(AgentMessageModel.session_id == session_id)).all()
            )
            return {
                "session_id": row.session_id,
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


def dump_json(value: Any) -> str:
    return _dumps(value)


def load_json(value: str | None, default: Any) -> Any:
    return _loads(value, default)
