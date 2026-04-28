from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from wuwei.runtime import ApprovalDecision, ApprovalRequest

from app.core.timezone import app_now, isoformat_app_timezone
from app.db.models import ApprovalModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json


class ApprovalManager:
    def __init__(self, *, timeout_seconds: int = 300, session_factory=create_db_session) -> None:
        self.timeout_seconds = timeout_seconds
        self.session_factory = session_factory
        self._futures: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(session_id, set()).add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(session_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(session_id, None)

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        await self._save_pending(request)
        event = self._event_from_request(request)
        for queue in list(self._subscribers.get(request.session_id, set())):
            await queue.put(event)

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._futures[request.id] = future
        try:
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            decision = ApprovalDecision(status="rejected", reason="approval timed out")
            await self.decide(request.id, status="rejected", reason=decision.reason)
            return decision
        finally:
            self._futures.pop(request.id, None)

    async def decide(self, approval_id: str, *, status: str, reason: str | None = None) -> dict[str, Any]:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")

        with self.session_factory() as db:
            row = db.get(ApprovalModel, approval_id)
            if row is None:
                raise KeyError(f"approval not found: {approval_id}")
            row.status = status
            row.reason = reason
            row.decided_at = app_now()
            db.commit()
            db.refresh(row)
            record = self._serialize_row(row)

        future = self._futures.get(approval_id)
        if future is not None and not future.done():
            future.set_result(ApprovalDecision(status=status, reason=reason))

        return record

    async def get_pending(self, session_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = db.scalars(
                select(ApprovalModel)
                .where(ApprovalModel.session_id == session_id, ApprovalModel.status == "pending")
                .order_by(ApprovalModel.created_at.asc())
            ).all()
            return [self._serialize_row(row) for row in rows]

    async def _save_pending(self, request: ApprovalRequest) -> None:
        payload = request.payload or {}
        with self.session_factory() as db:
            row = db.get(ApprovalModel, request.id)
            if row is None:
                row = ApprovalModel(
                    approval_id=request.id,
                    session_id=request.session_id,
                    tool_call_id=payload.get("tool_call_id"),
                    tool_name=payload.get("tool_name", request.action_type),
                )
                db.add(row)

            row.arguments_json = dump_json(payload.get("arguments", {}))
            row.status = "pending"
            row.reason = None
            row.metadata_json = dump_json(request.metadata or {})
            db.commit()

    def _event_from_request(self, request: ApprovalRequest) -> dict[str, Any]:
        payload = request.payload or {}
        return {
            "approval_id": request.id,
            "session_id": request.session_id,
            "tool_call_id": payload.get("tool_call_id"),
            "tool_name": payload.get("tool_name", request.action_type),
            "arguments": payload.get("arguments", {}),
            "status": "pending",
            "metadata": request.metadata,
        }

    def _serialize_row(self, row: ApprovalModel) -> dict[str, Any]:
        return {
            "approval_id": row.approval_id,
            "session_id": row.session_id,
            "tool_call_id": row.tool_call_id,
            "tool_name": row.tool_name,
            "arguments": load_json(row.arguments_json, {}),
            "status": row.status,
            "reason": row.reason,
            "metadata": load_json(row.metadata_json, {}),
            "created_at": isoformat_app_timezone(row.created_at),
            "decided_at": isoformat_app_timezone(row.decided_at),
        }
