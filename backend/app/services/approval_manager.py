from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import select

from app.core.timezone import app_now, isoformat_app_timezone
from app.db.models import ApprovalModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json


class ApprovalManager:
    """Human-in-the-Loop 审批管理器（适配 wuwei 2.1 Middleware）。

    提供两种接口：
    1. request_approval_bool(tool_call) -> bool — 供 HitlMiddleware 使用
    2. subscribe/unsubscribe — 供前端 SSE 推送审批请求
    """

    def __init__(self, *, timeout_seconds: int = 300, session_factory=create_db_session) -> None:
        self.timeout_seconds = timeout_seconds
        self.session_factory = session_factory
        self._futures: dict[str, asyncio.Future[bool]] = {}
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

    def _purge_stale_entries(self) -> None:
        done_futures = [req_id for req_id, fut in self._futures.items() if fut.done()]
        for req_id in done_futures:
            self._futures.pop(req_id, None)

        empty_sessions = [sid for sid, queues in self._subscribers.items() if not queues]
        for sid in empty_sessions:
            self._subscribers.pop(sid, None)

    async def request_approval_bool(self, tool_call) -> bool:
        """适配 HitlMiddleware 的 approval_provider: Callable[[ToolCall], Awaitable[bool]]。

        将工具调用转为内部审批流程，返回 True/False。
        """
        self._purge_stale_entries()

        approval_id = uuid.uuid4().hex
        tool_name = tool_call.function.name
        arguments = tool_call.function.arguments
        tool_call_id = getattr(tool_call, "id", None)

        # 从 tool_call 中提取 session_id（通过 metadata 或默认值）
        session_id = getattr(tool_call, "session_id", None) or "default"

        # 持久化到数据库
        await self._save_pending(approval_id, session_id, tool_name, arguments, tool_call_id)

        # 推送给前端
        event = {
            "approval_id": approval_id,
            "session_id": session_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "status": "pending",
            "metadata": {},
        }
        for queue in list(self._subscribers.get(session_id, set())):
            await queue.put(event)

        # 等待审批决策
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._futures[approval_id] = future
        try:
            return await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            await self.decide(approval_id, status="rejected", reason="approval timed out")
            return False
        finally:
            self._futures.pop(approval_id, None)

    async def decide(self, approval_id: str, *, status: str, reason: str | None = None) -> dict[str, Any]:
        if status not in {"approved", "rejected"}:
            raise ValueError("status must be approved or rejected")

        def _run():
            with self.session_factory() as db:
                row = db.get(ApprovalModel, approval_id)
                if row is None:
                    raise KeyError(f"approval not found: {approval_id}")
                row.status = status
                row.reason = reason
                row.decided_at = app_now()
                db.commit()
                db.refresh(row)
                return self._serialize_row(row)

        record = await asyncio.to_thread(_run)

        future = self._futures.get(approval_id)
        if future is not None and not future.done():
            future.set_result(status == "approved")

        return record

    async def get_pending(self, session_id: str) -> list[dict[str, Any]]:
        def _run():
            with self.session_factory() as db:
                rows = db.scalars(
                    select(ApprovalModel)
                    .where(ApprovalModel.session_id == session_id, ApprovalModel.status == "pending")
                    .order_by(ApprovalModel.created_at.asc())
                ).all()
                return [self._serialize_row(row) for row in rows]
        return await asyncio.to_thread(_run)

    async def _save_pending(
        self,
        approval_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict,
        tool_call_id: str | None,
    ) -> None:
        def _run():
            with self.session_factory() as db:
                row = db.get(ApprovalModel, approval_id)
                if row is None:
                    row = ApprovalModel(
                        approval_id=approval_id,
                        session_id=session_id,
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                    )
                    db.add(row)

                row.arguments_json = dump_json(arguments)
                row.status = "pending"
                row.reason = None
                row.metadata_json = dump_json({})
                db.commit()
        await asyncio.to_thread(_run)

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
