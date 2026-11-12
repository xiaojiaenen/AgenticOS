"""阻塞协调器：UserInputBlocker（用户输入）/ ApprovalBlocker（API 级审批）。

两类交互的阻塞/订阅/清理统一委托给 ``InteractionBroker``
（``app/services/interactions.py``）—— 与决策问答共用同一套 Future 登记表、
Redis pub/sub 转发、超时与会话清理纪律。本文件只保留：

- 两类交互的**语义适配**（超时后 API 审批按拒绝处理、表单按超时错误抛出）；
- ``ApprovalBlocker`` 的会话级"全部允许"记忆（纯会话内状态，与阻塞无关）。

类方法 API（subscribe/request_input/request_approval/resolve/…）与旧实现
兼容，调用方（tool_builder / mcp_tool_bridge / service.py / 端点）无需改动；
仅 ``resolve`` 由同步改异步（统一协调器后 resolve 需要写 Redis 并可能跨
worker 转发）。
"""

from __future__ import annotations

import asyncio
import logging

from app.services.interactions import (
    InteractionBroker,
    InteractionKind,
    InteractionTimeout,
    get_interaction_broker,
)

logger = logging.getLogger(__name__)


def _broker() -> InteractionBroker:
    return get_interaction_broker()


# ── UserInput 阻塞（缺参表单）────────────────────────────────────────────

class UserInputBlocker:
    """让 handler 在需要用户输入时阻塞等待，resolve 后拿到 values dict。

    超时（``hitl_timeout_seconds``，默认 300s）抛 :class:`InteractionTimeout`
    —— 旧行为是永远挂起，依赖流取消兜底；统一到协调器后工具能收到结构化
    超时错误，模型可以据此向用户说明。
    """

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        return _broker().subscribe(session_id)

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        _broker().unsubscribe(session_id)

    @classmethod
    async def request_input(cls, session_id: str, payload: dict) -> dict:
        """阻塞等待用户输入。返回用户提交的 values dict；超时抛 InteractionTimeout。"""
        return await _broker().request(session_id, InteractionKind.USER_INPUT, payload)

    @classmethod
    async def resolve(cls, session_id: str, values: dict) -> bool:
        """resolve 该会话最早挂起的表单交互。返回 False = 无挂起交互。"""
        return await _broker().resolve_by_session(session_id, InteractionKind.USER_INPUT, values)


# ── API 级审批 ────────────────────────────────────────────────────────────

class ApprovalBlocker:
    """API 级别审批：阻塞等待用户决定，返回 True=批准 / False=拒绝。

    保留会话级"全部允许"记忆：同一会话第二次调用同一系统的 API 时不再询问。
    """

    # 会话级"全部允许"记录：{(session_id, system_name): True}
    _session_allowed: dict[tuple[str, str], bool] = {}

    @classmethod
    def subscribe(cls, session_id: str) -> asyncio.Queue:
        return _broker().subscribe(session_id)

    @classmethod
    def unsubscribe(cls, session_id: str) -> None:
        broker = _broker()
        broker.unsubscribe(session_id)
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
        """阻塞等待用户审批。返回 True=批准, False=拒绝（超时按拒绝处理）。"""
        # 检查是否已全部允许
        system_name = payload.get("system_name", "")
        if cls.is_allowed(session_id, system_name):
            logger.info("ApprovalBlocker: session=%s system=%s already allowed, skipping", session_id, system_name)
            return True

        try:
            result = await _broker().request(session_id, InteractionKind.API_APPROVAL, payload)
        except InteractionTimeout:
            logger.warning(
                "ApprovalBlocker: session=%s system=%s approval timed out, treating as rejected",
                session_id, system_name,
            )
            return False
        decision = result if isinstance(result, dict) else {"approved": bool(result)}
        logger.info("ApprovalBlocker: resolved session=%s decision=%s", session_id, decision)
        # 如果用户选择了"全部允许"
        if decision.get("allow_all"):
            cls.allow_all(session_id, system_name)
        return bool(decision.get("approved", False))

    @classmethod
    async def resolve(cls, session_id: str, decision: dict) -> bool:
        """resolve 该会话最早挂起的审批交互。返回 False = 无挂起交互。"""
        return await _broker().resolve_by_session(session_id, InteractionKind.API_APPROVAL, decision)
