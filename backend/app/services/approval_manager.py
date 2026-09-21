from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select
from wuwei.runtime import ApprovalDecision, ApprovalRequest

from app.core.redis import get_redis
from app.core.timezone import app_now, isoformat_app_timezone
from app.db.models import ApprovalModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json


# Redis 频道前缀
_APPROVAL_CHANNEL_PREFIX = "approval:"


class ApprovalManager:
    """审批管理器，使用 Redis pub/sub 实现跨 worker 通信。"""

    def __init__(self, *, timeout_seconds: int = 300, session_factory=create_db_session) -> None:
        self.timeout_seconds = timeout_seconds
        self.session_factory = session_factory
        # 不再使用内存态的 futures 和 subscribers，改用 Redis pub/sub

    async def request_approval_bool(self, tool_call) -> bool:
        """兼容 wuwei HitlMiddleware 的 approval_provider 接口：接收 ToolCall 返回 bool。"""
        import uuid
        from app.services.agent_service import _current_session_id
        session_id = _current_session_id.get() or "default"

        # 确保 arguments 是字典而不是 JSON 字符串
        arguments = tool_call.function.arguments
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}

        request = ApprovalRequest(
            id=uuid.uuid4().hex,
            session_id=session_id,
            action_type="tool_call",
            payload={
                "tool_call_id": getattr(tool_call, "id", None),
                "tool_name": tool_call.function.name,
                "arguments": arguments,
            },
        )
        decision = await self.request_approval(request)
        return decision.status == "approved"

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """请求审批，通过 Redis pub/sub 等待决策（支持多 worker）。"""
        await self._save_pending(request)
        event = self._event_from_request(request)

        # 通知所有订阅者（前端 SSE）
        redis = get_redis()
        channel = f"{_APPROVAL_CHANNEL_PREFIX}{request.session_id}"
        await redis.publish(channel, json.dumps(event))

        # 订阅决策频道，等待审批结果
        decision_channel = f"{_APPROVAL_CHANNEL_PREFIX}decision:{request.id}"
        queue = redis.subscribe(decision_channel)

        try:
            # 等待决策或超时
            message = await asyncio.wait_for(queue.get(), timeout=self.timeout_seconds)
            decision_data = json.loads(message)
            return ApprovalDecision(
                status=decision_data["status"],
                reason=decision_data.get("reason"),
            )
        except asyncio.TimeoutError:
            decision = ApprovalDecision(status="rejected", reason="approval timed out")
            await self.decide(request.id, status="rejected", reason=decision.reason)
            return decision
        finally:
            redis.unsubscribe(decision_channel, queue)

    async def decide(self, approval_id: str, *, status: str, reason: str | None = None) -> dict[str, Any]:
        """做出审批决策，通过 Redis pub/sub 通知等待方（支持多 worker）。"""
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
                return self._serialize_row(row), row.session_id

        record, session_id = await asyncio.to_thread(_run)

        # 通过 Redis pub/sub 通知等待方
        redis = get_redis()
        decision_channel = f"{_APPROVAL_CHANNEL_PREFIX}decision:{approval_id}"
        decision_data = {"status": status, "reason": reason}
        await redis.publish(decision_channel, json.dumps(decision_data))

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

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """订阅审批事件队列（兼容 UserInputBlocker/ApprovalBlocker 接口）。"""
        q: asyncio.Queue = asyncio.Queue()
        # 可以在这里保存 queue 引用以便后续推送事件
        if not hasattr(self, '_queues'):
            self._queues: dict[str, asyncio.Queue] = {}
        self._queues[session_id] = q
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue | None = None) -> None:
        """取消订阅审批事件队列。"""
        if hasattr(self, '_queues'):
            self._queues.pop(session_id, None)

    async def _save_pending(self, request: ApprovalRequest) -> None:
        payload = request.payload or {}

        def _run():
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
        await asyncio.to_thread(_run)

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
