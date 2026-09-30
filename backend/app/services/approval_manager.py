from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select
from wuwei.runtime import ApprovalDecision, ApprovalRequest

from app.core.redis import get_redis, is_redis_memory
from app.core.timezone import app_now, isoformat_app_timezone
from app.db.models import ApprovalModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json


# Redis 频道前缀
_APPROVAL_CHANNEL_PREFIX = "approval:"
_logger = logging.getLogger("approval")


class ApprovalManager:
    """审批管理器，使用 Redis pub/sub 实现跨 worker 通信。"""

    def __init__(self, *, timeout_seconds: int = 300, session_factory=create_db_session) -> None:
        self.timeout_seconds = timeout_seconds
        self.session_factory = session_factory
        # 本地会话事件队列：agent_service 通过 subscribe() 取到后 approval_queue.get()
        self._queues: dict[str, asyncio.Queue] = {}
        # 跨进程 listener：外部 Redis 模式下把频道消息转发进本地队列
        self._listeners: dict[str, asyncio.Task] = {}
        # 审批决策本地等待队列（兼容 MemoryRedis 与 redis.asyncio）
        self._decision_waiters: dict[str, asyncio.Queue] = {}

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

        # 同时直投本进程本地队列：agent_service 通过 subscribe() 拿到的
        # approval_queue 依赖此路径（内存 Redis 的 publish 不会进入 _queues）。
        # 若该会话已启动跨进程 listener（外部 Redis），由 listener 转发即可，
        # 跳过本地直投以避免重复投递。
        local_q = self._queues.get(request.session_id)
        listener = self._listeners.get(request.session_id)
        if local_q is not None and (listener is None or listener.done()):
            await local_q.put(event)

        # 决策等待：统一走本地 asyncio.Queue。
        # decide() 在本进程会直接 put；跨 worker 时由 Redis listener 转发。
        # 不能对 redis.asyncio 客户端调用 MemoryRedis 风格的 subscribe()。
        decision_channel = f"{_APPROVAL_CHANNEL_PREFIX}decision:{request.id}"
        decision_queue: asyncio.Queue = asyncio.Queue()
        self._decision_waiters[request.id] = decision_queue

        redis_listener: asyncio.Task | None = None
        if not is_redis_memory():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                redis_listener = loop.create_task(
                    self._forward_decision_events(decision_channel, decision_queue)
                )

        try:
            message = await asyncio.wait_for(decision_queue.get(), timeout=self.timeout_seconds)
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8", errors="replace")
            if isinstance(message, str):
                decision_data = json.loads(message)
            else:
                decision_data = message
            return ApprovalDecision(
                status=decision_data["status"],
                reason=decision_data.get("reason"),
            )
        except asyncio.TimeoutError:
            decision = ApprovalDecision(status="rejected", reason="approval timed out")
            try:
                await self.decide(request.id, status="rejected", reason=decision.reason)
            except Exception:  # noqa: BLE001
                _logger.warning("failed to persist approval timeout decision: approval_id=%s", request.id)
            return decision
        finally:
            self._decision_waiters.pop(request.id, None)
            if redis_listener is not None and not redis_listener.done():
                redis_listener.cancel()

    async def _forward_decision_events(self, channel: str, queue: asyncio.Queue) -> None:
        """把外部 Redis 决策频道消息转发进本地等待队列。"""
        redis = get_redis()
        pubsub = None
        try:
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if not isinstance(message, dict) or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8", errors="replace")
                await queue.put(data)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("approval decision listener failed: channel=%s", channel)
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:  # noqa: BLE001
                    pass
                for closer in ("aclose", "close"):
                    fn = getattr(pubsub, closer, None)
                    if fn is not None:
                        try:
                            result = fn()
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:  # noqa: BLE001
                            pass
                        break

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
        payload = json.dumps(decision_data)
        await redis.publish(decision_channel, payload)

        # 本进程等待方直接投递（不依赖 Redis 客户端是否实现 subscribe）
        waiter = self._decision_waiters.get(approval_id)
        if waiter is not None:
            await waiter.put(payload)

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
        """订阅审批事件队列（兼容 UserInputBlocker/ApprovalBlocker 接口）。

        - 内存 Redis（单进程）：事件由 request_approval 直投本地队列；
        - 外部 Redis（跨进程）：启动 listener 订阅 `approval:{session_id}`
          频道，把 publish 的消息写入本地队列。
        """
        q: asyncio.Queue = asyncio.Queue()
        self._queues[session_id] = q

        # 重新订阅时替换旧 listener
        old = self._listeners.pop(session_id, None)
        if old is not None and not old.done():
            old.cancel()

        if not is_redis_memory():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                self._listeners[session_id] = loop.create_task(
                    self._forward_events(session_id, q)
                )
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue | None = None) -> None:
        """取消订阅审批事件队列。"""
        self._queues.pop(session_id, None)
        task = self._listeners.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _forward_events(self, session_id: str, queue: asyncio.Queue) -> None:
        """跨进程 listener：把 Redis 频道消息转发到本地会话队列。"""
        channel = f"{_APPROVAL_CHANNEL_PREFIX}{session_id}"
        redis = get_redis()
        pubsub = None
        try:
            pubsub = redis.pubsub()
            await pubsub.subscribe(channel)
            async for message in pubsub.listen():
                if not isinstance(message, dict) or message.get("type") != "message":
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="replace")
                try:
                    event = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception(
                "approval event listener failed: session=%s channel=%s", session_id, channel
            )
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(channel)
                except Exception:  # noqa: BLE001
                    pass
                for closer in ("aclose", "close"):
                    fn = getattr(pubsub, closer, None)
                    if fn is not None:
                        try:
                            result = fn()
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:  # noqa: BLE001
                            pass
                        break

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
