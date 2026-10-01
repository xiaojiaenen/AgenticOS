"""阻塞协调器：UserInputBlocker（用户输入）/ ApprovalBlocker（API 级审批）。

均为 per-session 的 Future + Queue 模式，供 SSE 层 resolve。"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


# ── UserInput 阻塞机制（类似审批的 queue+Future 模式）────────────────────

class UserInputBlocker:
    """per-session 的 Future + Queue，让 handler 在需要用户输入时阻塞等待。"""
    _queues: dict[str, asyncio.Queue] = {}
    _futures: dict[str, asyncio.Future] = {}

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        cls._queues[session_id] = q
        return q

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        cls._queues.pop(session_id, None)
        cls._futures.pop(session_id, None)

    @classmethod
    async def request_input(cls, session_id: str, payload: dict) -> dict:
        """阻塞等待用户输入。返回用户提交的 values dict。"""
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        cls._futures[session_id] = fut
        q = cls._queues.get(session_id)
        if q is not None:
            q.put_nowait(payload)
        return await fut

    @classmethod
    def resolve(cls, session_id: str, values: dict) -> None:
        fut = cls._futures.pop(session_id, None)
        if fut and not fut.done():
            fut.set_result(values)


class ApprovalBlocker:
    """API 级别审批：per-session 的 Future + Queue，让 handler 在需要审批时阻塞等待。"""
    _queues: dict[str, asyncio.Queue] = {}
    _futures: dict[str, asyncio.Future] = {}
    # 会话级"全部允许"记录：{(session_id, system_name): True}
    _session_allowed: dict[tuple[str, str], bool] = {}

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        cls._queues[session_id] = q
        return q

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        cls._queues.pop(session_id, None)
        cls._futures.pop(session_id, None)
        # 清理该会话的全部允许记录
        keys_to_remove = [k for k in cls._session_allowed if k[0] == session_id]
        for k in keys_to_remove:
            del cls._session_allowed[k]

    @classmethod
    def is_allowed(cls, session_id: str, system_name: str) -> bool:
        """检查该会话是否已对该系统全部允许。"""
        return cls._session_allowed.get((session_id, system_name), False)

    @classmethod
    def allow_all(cls, session_id: str, system_name: str) -> None:
        """标记该会话对该系统全部允许。"""
        cls._session_allowed[(session_id, system_name)] = True

    @classmethod
    async def request_approval(cls, session_id: str, payload: dict) -> bool:
        """阻塞等待用户审批。返回 True=批准, False=拒绝。"""
        # 检查是否已全部允许
        system_name = payload.get("system_name", "")
        if cls.is_allowed(session_id, system_name):
            logger.info("ApprovalBlocker: session=%s system=%s already allowed, skipping", session_id, system_name)
            return True

        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        cls._futures[session_id] = fut
        q = cls._queues.get(session_id)
        if q is not None:
            q.put_nowait(payload)
        logger.info("ApprovalBlocker: waiting session=%s, futures_keys=%s", session_id, list(cls._futures.keys()))
        result = await fut
        decision = result if isinstance(result, dict) else {"approved": bool(result)}
        logger.info("ApprovalBlocker: resolved session=%s decision=%s", session_id, decision)
        # 如果用户选择了"全部允许"
        if decision.get("allow_all"):
            cls.allow_all(session_id, system_name)
        return bool(decision.get("approved", False))

    @classmethod
    def resolve(cls, session_id: str, decision: dict) -> None:
        logger.info("ApprovalBlocker.resolve: session=%s decision=%s, futures_keys=%s", session_id, decision, list(cls._futures.keys()))
        fut = cls._futures.pop(session_id, None)
        if fut and not fut.done():
            fut.set_result(decision)
            logger.info("ApprovalBlocker.resolve: future resolved for session=%s", session_id)
        else:
            logger.warning("ApprovalBlocker.resolve: no future found for session=%s", session_id)
