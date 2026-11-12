"""统一「等人」交互协调器（InteractionBroker）。

**为什么需要这一层。** 同一件事 ——「agent 停下来等人」—— 此前有四套实现：
工具审批走 ``ApprovalManager``（Redis pub/sub + DB 审计），而外部 API 审批
（``ApprovalBlocker``）、缺参表单（``UserInputBlocker``）、决策问答
（``decision_tools``）各自维护一份模块级 Future dict。它们行为不一致：

- 决策有 300s 超时；API 审批与表单**没有超时**，用户不响应时工具永远挂着；
- 只有 ApprovalManager 支持 Redis pub/sub —— 多 worker 部署
  （``UVICORN_WORKERS>1``）下另外三类的 resolve 端点打到别的 worker 时
  **静默失效**（Future 在另一个进程里）；
- 各自的清理纪律不同（决策按归属过滤、blocker 直接 pop 不 cancel）。

本协调器把三类交互统一到与 ApprovalManager 同构的机制上：per-session 订阅
队列（SSE pump 消费）+ Redis pub/sub（跨 worker）+ 统一超时 + 归属登记 +
流结束时 cancel 所有挂起 Future。工具审批**不走这里** —— 它的 DB 审计、
modified_arguments、跨 worker 语义已经由 ApprovalManager 完整承担。

事件 payload 在原有字段之外统一附加 ``interaction_id`` 与 ``kind``，SSE 层按
``kind`` 映射回各自的事件名（``user_input_required`` / ``api_approval_required``
/ ``user_decision``），前端契约不变。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from app.core.redis import get_redis, is_redis_memory
from app.services.redis_relay import forward_channel_to_queue

_CHANNEL_PREFIX = "interaction:"
_pending_key_prefix = f"{_CHANNEL_PREFIX}pending:"
_logger = logging.getLogger("interactions")


class InteractionKind:
    """交互类别常量 —— 也决定 SSE 事件名与决策载荷的形状。"""

    API_APPROVAL = "api_approval"
    USER_INPUT = "user_input"
    DECISION = "decision"


# kind → SSE 事件名（orchestrator 的 pump 按 src 映射；工具审批不经 broker）
KIND_EVENTS: dict[str, str] = {
    InteractionKind.API_APPROVAL: "api_approval_required",
    InteractionKind.USER_INPUT: "user_input_required",
    InteractionKind.DECISION: "user_decision",
}


class InteractionTimeout(RuntimeError):
    """等待人工响应超时。

    继承 RuntimeError 使其在工具执行路径上表现为普通的工具失败
    （wuwei 会把它转成结构化 tool_error，模型可以据此换做法）。
    """

    def __init__(self, interaction_id: str, kind: str, timeout_seconds: float) -> None:
        super().__init__(
            f"interaction {kind}({interaction_id}) timed out after {timeout_seconds}s"
        )
        self.interaction_id = interaction_id
        self.kind = kind
        self.timeout_seconds = timeout_seconds


class InteractionBroker:
    """一个进程一份；会话级订阅队列 + per-interaction 决策等待队列。"""

    def __init__(self, *, default_timeout_seconds: int = 300) -> None:
        self.default_timeout_seconds = default_timeout_seconds
        # SSE pump 订阅的会话事件队列
        self._queues: dict[str, asyncio.Queue] = {}
        # 外部 Redis 模式下的会话频道 listener
        self._listeners: dict[str, asyncio.Task] = {}
        # per-interaction 决策等待队列（本进程等待方）
        self._decision_waiters: dict[str, asyncio.Queue] = {}
        # 归属登记：interaction_id -> {"session_id", "kind"}（快速路径；
        # 跨 worker 时以 Redis pending key 为准）
        self._pending: dict[str, dict[str, str]] = {}

    # ── 订阅（SSE pump）─────────────────────────────────────────────

    def subscribe(self, session_id: str) -> asyncio.Queue:
        """订阅会话交互队列（幂等：重复订阅返回同一队列）。

        外部 Redis 模式下同时启动频道 listener。多个入口（工具审批门面、
        表单门面、orchestrator）对同一会话重复 subscribe 是正常路径 ——
        它们必须拿到**同一个**队列，事件才不会因为后一次订阅覆盖前一次而丢失。
        """
        existing = self._queues.get(session_id)
        listener = self._listeners.get(session_id)
        if existing is not None and listener is not None and not listener.done():
            return existing
        # 队列本身始终复用（内存模式没有 listener；外部 Redis 模式 listener
        # 挂掉时下面会重建），保证重复订阅拿到同一个队列
        q = existing if existing is not None else asyncio.Queue()
        self._queues[session_id] = q

        old = self._listeners.pop(session_id, None)
        if old is not None and not old.done():
            old.cancel()

        if not is_redis_memory():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                redis = get_redis()
                channel = f"{_CHANNEL_PREFIX}{session_id}"
                self._listeners[session_id] = loop.create_task(
                    forward_channel_to_queue(redis, channel, q, parse_json=True)
                )
        return q

    def unsubscribe(self, session_id: str, queue: asyncio.Queue | None = None) -> None:
        """取消订阅，并 cancel 该会话所有挂起 Future（流结束清理，防泄漏）。"""
        self._queues.pop(session_id, None)
        task = self._listeners.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()
        self.cancel_session(session_id)

    # ── 本地投递 ──────────────────────────────────────────────────────

    def _deliver_local_if_no_listener(self, session_id: str, event: dict[str, Any]) -> None:
        """无活跃 Redis listener 时直投本地队列。

        内存 Redis 模式的 publish 不会进 _queues，必须直投；外部 Redis 模式
        下 listener 已在转发，直投会重复。
        """
        local_q = self._queues.get(session_id)
        listener = self._listeners.get(session_id)
        if local_q is not None and (listener is None or listener.done()):
            local_q.put_nowait(event)

    def _deliver_local(self, session_id: str, event: dict[str, Any]) -> None:
        """强制直投本地队列（Redis publish 失败后的降级路径）。"""
        local_q = self._queues.get(session_id)
        if local_q is not None:
            local_q.put_nowait(event)

    # ── 请求（工具侧阻塞等待）───────────────────────────────────────

    async def request(
        self,
        session_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
        interaction_id: str | None = None,
    ) -> dict[str, Any]:
        """发起一次交互：推送事件给前端（SSE），阻塞等待决策，超时抛
        :class:`InteractionTimeout`。

        返回值是 resolve 端点提交的决策 dict（形状由 kind 决定，见模块 docstring）。
        ``payload`` 会被原地补上 ``interaction_id`` / ``kind`` / ``session_id``。
        """
        if kind not in KIND_EVENTS:
            raise ValueError(f"unknown interaction kind: {kind}")
        timeout = self.default_timeout_seconds if timeout_seconds is None else timeout_seconds
        interaction_id = interaction_id or uuid.uuid4().hex

        payload["interaction_id"] = interaction_id
        payload["kind"] = kind
        payload.setdefault("session_id", session_id)

        event = dict(payload)
        self._pending[interaction_id] = {"session_id": session_id, "kind": kind}
        await self._save_pending(interaction_id, session_id, kind, timeout)

        redis = get_redis()
        channel = f"{_CHANNEL_PREFIX}{session_id}"
        try:
            await redis.publish(channel, json.dumps(event))
        except Exception:  # noqa: BLE001
            # Redis 故障不得打断进程内等待：回退本地直投（跨 worker 转发暂时
            # 不可用属降级，本地 pump 仍能收到事件）
            _logger.warning(
                "interaction event publish failed, falling back to local delivery: "
                "session=%s id=%s", session_id, interaction_id, exc_info=True,
            )
            await self._deliver_local(session_id, event)
        else:
            self._deliver_local_if_no_listener(session_id, event)

        # 决策等待：统一走本地 asyncio.Queue，跨 worker 由 Redis listener 转发
        decision_channel = f"{_CHANNEL_PREFIX}decision:{interaction_id}"
        decision_queue: asyncio.Queue = asyncio.Queue()
        self._decision_waiters[interaction_id] = decision_queue

        redis_listener: asyncio.Task | None = None
        if not is_redis_memory():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                redis_listener = loop.create_task(
                    forward_channel_to_queue(redis, decision_channel, decision_queue, parse_json=False)
                )

        try:
            message = await asyncio.wait_for(decision_queue.get(), timeout=timeout)
            if isinstance(message, (bytes, bytearray)):
                message = message.decode("utf-8", errors="replace")
            if isinstance(message, str):
                message = json.loads(message)
            if isinstance(message, dict) and message.get("__cancelled__"):
                # cancel_session 的哨兵：会话流已结束，交互作废（等同超时语义）
                raise InteractionTimeout(interaction_id, kind, timeout) from None
            return message
        except asyncio.TimeoutError:
            raise InteractionTimeout(interaction_id, kind, timeout) from None
        finally:
            self._decision_waiters.pop(interaction_id, None)
            self._pending.pop(interaction_id, None)
            await self._clear_pending(interaction_id)
            if redis_listener is not None and not redis_listener.done():
                redis_listener.cancel()

    # ── 决策（端点侧 resolve）───────────────────────────────────────

    async def resolve(self, interaction_id: str, decision: dict[str, Any]) -> bool:
        """按 interaction_id 提交决策。返回 False 表示交互不存在或已超时。"""
        info = self._pending.get(interaction_id)
        if info is None:
            # 跨 worker：登记在本进程没有，回源 Redis pending key
            info = await self._load_pending(interaction_id)
        if info is None:
            return False

        # Redis publish 是跨 worker 转发通道；进程内等待方靠 _decision_waiters
        # 直投，publish 失败只降级不致命（与 request 的事件发布同一纪律）。
        try:
            redis = get_redis()
            await redis.publish(
                f"{_CHANNEL_PREFIX}decision:{interaction_id}", json.dumps(decision)
            )
        except Exception:  # noqa: BLE001
            _logger.warning(
                "interaction decision publish failed (local waiter still resolves): id=%s",
                interaction_id, exc_info=True,
            )

        waiter = self._decision_waiters.get(interaction_id)
        if waiter is not None:
            await waiter.put(decision)
        # 本进程等待方已收到 / 跨 worker 时决策已经频道送达对方进程
        return True

    async def resolve_by_session(
        self, session_id: str, kind: str, decision: dict[str, Any]
    ) -> bool:
        """按会话+类别提交决策（兼容旧的 session-keyed 端点契约）。

        命中该会话该类别**最早挂起**的交互 —— 同类交互串行等待，历史上
        blocker 的 per-session 单 Future 也是这个语义。_pending 是插入序
        dict，登记序即请求序。
        """
        for interaction_id, info in list(self._pending.items()):
            if info["session_id"] == session_id and info["kind"] == kind:
                if await self.resolve(interaction_id, decision):
                    return True
        return False

    def pending_session(self, interaction_id: str) -> str | None:
        """peek 归属会话（不弹出），供端点做归属校验。"""
        info = self._pending.get(interaction_id)
        if info is not None:
            return info["session_id"]
        return None

    async def pending_session_async(self, interaction_id: str) -> str | None:
        """归属校验的完整版：本地登记 miss 时回源 Redis（跨 worker resolve）。"""
        info = self._pending.get(interaction_id)
        if info is not None:
            return info["session_id"]
        loaded = await self._load_pending(interaction_id)
        if loaded:
            return loaded.get("session_id")
        return None

    def cancel_session(self, session_id: str) -> None:
        """cancel 该会话全部挂起交互（流结束 / 会话删除时调用）。

        不直接 cancel Future —— 向等待队列投取消哨兵，让 ``request()`` 以
        InteractionTimeout 返回，工具可以优雅地给出「用户未响应」类消息，
        而不是让 CancelledError 从工具里炸出去。
        """
        orphaned = [
            iid for iid, info in self._pending.items() if info["session_id"] == session_id
        ]
        for iid in orphaned:
            waiter = self._decision_waiters.get(iid)
            if waiter is not None:
                waiter.put_nowait({"__cancelled__": True})
            self._pending.pop(iid, None)

    def pending_count(self, session_id: str | None = None) -> int:
        if session_id is None:
            return len(self._pending)
        return sum(1 for info in self._pending.values() if info["session_id"] == session_id)

    # ── Redis pending 登记（跨 worker 归属与 resolve 判定）──────────

    async def _save_pending(self, interaction_id: str, session_id: str, kind: str, timeout: float) -> None:
        try:
            redis = get_redis()
            await redis.set(
                f"{_pending_key_prefix}{interaction_id}",
                json.dumps({"session_id": session_id, "kind": kind}),
                ex=int(timeout) + 60,
            )
        except Exception:  # noqa: BLE001
            _logger.warning("failed to persist interaction pending key: id=%s", interaction_id)

    async def _load_pending(self, interaction_id: str) -> dict[str, str] | None:
        try:
            redis = get_redis()
            raw = await redis.get(f"{_pending_key_prefix}{interaction_id}")
            if not raw:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            data = json.loads(raw)
            self._pending[interaction_id] = data
            return data
        except Exception:  # noqa: BLE001
            return None

    async def _clear_pending(self, interaction_id: str) -> None:
        try:
            redis = get_redis()
            await redis.delete(f"{_pending_key_prefix}{interaction_id}")
        except Exception:  # noqa: BLE001
            pass


_broker: InteractionBroker | None = None


def get_interaction_broker() -> InteractionBroker:
    """进程级单例（并发工具可能在多个 task 里发起交互，共享同一份登记）。"""
    global _broker
    if _broker is None:
        from app.core.config import get_settings

        settings = get_settings()
        timeout = getattr(settings, "hitl_timeout_seconds", 300)
        _broker = InteractionBroker(default_timeout_seconds=timeout)
    return _broker


def reset_interaction_broker() -> None:
    """测试专用：重置单例（conftest 的 _reset_global_singletons 会调用）。"""
    global _broker
    _broker = None
