"""决策工具

LLM 调用工具提供问题和选项，让用户做决策。
每个决策都有一个"自定义输入"选项，用户可以输入自己的答案。

工作原理：
1. LLM 调用 ask_user_decision(question, options)（或 ppt_tools 的计划确认）
2. 工具通过 contextvars 获取当前 session_id，构建 user_decision 事件
3. ``request_decision`` 把事件交给 :class:`InteractionBroker`（统一"等人"
   协调器）：事件进 SSE pump 队列 → 前端 DecisionPanel 渲染 →
   ``POST /decisions/{id}/decision`` 提交答案
4. 协调器 resolve 等待队列，工具拿到用户的选择
5. 超时（``hitl_timeout_seconds``，默认 300s）返回超时错误；流结束时
   挂起交互由协调器统一 cancel

此前这里是一份模块级 Future dict（重启即丢、无跨 worker 支持），现已并入
协调器 —— 与审批/表单共用同一套登记与清理纪律。
"""

from __future__ import annotations

import json
from typing import Any

from wuwei.tools import ToolRegistry

from app.services.interactions import (
    InteractionKind,
    InteractionTimeout,
    get_interaction_broker,
)

DECISION_TIMEOUT_SECONDS = 300


async def request_decision(
    session_id: str, event: dict[str, Any], *, timeout_seconds: float | None = None
) -> tuple[str, str | None]:
    """发起一次决策并阻塞等待用户回答。

    ``event`` 会原地补上 ``decision_id`` / ``session_id``；返回
    ``(decision_id, answer)``，用户未在超时内回答时 ``answer`` 为 ``None``。
    """
    broker = get_interaction_broker()
    import uuid

    decision_id = str(event.get("decision_id") or uuid.uuid4().hex[:8])
    event["decision_id"] = decision_id
    event["session_id"] = session_id
    event.setdefault("type", "user_decision")
    event.setdefault("status", "pending")

    try:
        result = await broker.request(
            session_id,
            InteractionKind.DECISION,
            event,
            timeout_seconds=timeout_seconds or DECISION_TIMEOUT_SECONDS,
            interaction_id=decision_id,
        )
    except InteractionTimeout:
        return decision_id, None
    answer = result.get("answer") if isinstance(result, dict) else None
    return decision_id, str(answer) if answer is not None else None


def get_decision_session(decision_id: str) -> str | None:
    """peek 决策归属的会话（不弹出），供端点做归属校验。"""
    return get_interaction_broker().pending_session(decision_id)


async def resolve_decision(decision_id: str, answer: str) -> bool:
    """前端调用：resolve 一个决策。

    返回 True 表示成功，False 表示 decision_id 不存在或已超时。
    """
    return await get_interaction_broker().resolve(decision_id, {"answer": answer})


def cleanup_session_decisions(session_id: str) -> None:
    """清理指定 session 的所有挂起决策（stream 结束时调用，防止泄漏）。

    协调器会 cancel 等待方，工具以超时语义返回，而不是让 CancelledError
    从工具里炸出去。
    """
    get_interaction_broker().cancel_session(session_id)


def register_decision_tools(registry: ToolRegistry) -> None:
    """注册决策工具"""

    @registry.tool(
        name="ask_user_decision",
        display_name="请求用户决策",
        description="向用户提出一个决策问题，提供选项让用户选择。用于需要用户确认或选择的场景。每个选项都会展示给用户，用户也可以输入自定义答案。",
    )
    async def ask_user_decision(
        question: str,
        options: list[str] | str,
        context: str = "",
    ) -> dict[str, Any]:
        """向用户提出决策问题。

        参数:
            question: 要问用户的问题
            options: 选项列表（至少 2 个）
            context: 补充上下文信息

        返回:
            包含 decision_id 和选项的字典
        """
        # 处理 options 可能是字符串的情况
        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [s.strip() for s in options.split(',') if s.strip()]
        if not isinstance(options, list):
            return {"error": "options 必须是数组"}
        if len(options) < 2:
            return {"error": "至少需要 2 个选项"}

        # 通过 contextvars 获取当前 session_id
        from app.services.agent_service import _current_session_id
        session_id = _current_session_id.get() or "default"

        decision_event = {
            "type": "user_decision",
            "question": question,
            "options": options,
            "context": context,
            "allow_custom": True,
        }

        decision_id, answer = await request_decision(session_id, decision_event)

        if answer is None:
            return {
                "ok": False,
                "decision_id": decision_id,
                "error": "用户未在规定时间内做出决策",
                "timeout": True,
            }
        return {
            "ok": True,
            "decision_id": decision_id,
            "answer": answer,
            "message": f"用户选择了：{answer}",
        }
