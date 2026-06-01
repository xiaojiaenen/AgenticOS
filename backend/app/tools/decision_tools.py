"""决策工具

LLM 调用工具提供问题和选项，让用户做决策。
每个决策都有一个"自定义输入"选项，用户可以输入自己的答案。

工作原理：
1. LLM 调用 ask_user_decision(question, options)
2. 工具通过 contextvars 获取当前 session_id
3. 构建 user_decision 事件，推送到 approval_queue
4. 前端收到 user_decision 事件，显示 DecisionPanel
5. 用户选择后，答案通过新的 user message 发回 LLM
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from wuwei.tools import ToolRegistry

# 决策队列：session_id -> list[decision_event]
_decision_queues: dict[str, list[dict[str, Any]]] = {}


def register_decision_tools(registry: ToolRegistry) -> None:
    """注册决策工具"""

    @registry.tool(
        name="ask_user_decision",
        display_name="请求用户决策",
        description="向用户提出一个决策问题，提供选项让用户选择。用于需要用户确认或选择的场景。每个选项都会展示给用户，用户也可以输入自定义答案。",
    )
    async def ask_user_decision(
        question: str,
        options: list[str],
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
        if len(options) < 2:
            return {"error": "至少需要 2 个选项"}

        decision_id = str(uuid.uuid4())[:8]

        # 通过 contextvars 获取当前 session_id
        from app.services.agent_service import _current_session_id
        session_id = _current_session_id.get() or "default"

        # 构建决策事件
        decision_event = {
            "decision_id": decision_id,
            "session_id": session_id,
            "type": "user_decision",
            "question": question,
            "options": options,
            "context": context,
            "allow_custom": True,
            "status": "pending",
        }

        # 推送到决策队列，由 agent_service 的 stream_chat 消费
        if session_id not in _decision_queues:
            _decision_queues[session_id] = []
        _decision_queues[session_id].append(decision_event)

        return {
            "ok": True,
            "decision_id": decision_id,
            "message": f"已向用户提出决策问题：{question}，等待用户选择。",
            "options": options,
        }


def get_decision_queue(session_id: str) -> list[dict[str, Any]]:
    """获取指定 session 的待处理决策列表"""
    return _decision_queues.pop(session_id, [])
