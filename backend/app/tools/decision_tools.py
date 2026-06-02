"""决策工具

LLM 调用工具提供问题和选项，让用户做决策。
每个决策都有一个"自定义输入"选项，用户可以输入自己的答案。

工作原理：
1. LLM 调用 ask_user_decision(question, options)
2. 工具通过 contextvars 获取当前 session_id
3. 构建 user_decision 事件，推送到前端
4. 创建 Future 阻塞等待用户选择
5. 前端收到 user_decision 事件，显示 DecisionPanel
6. 用户选择后，答案通过 /decisions/{id}/decision API 发回
7. Future 被 resolve，工具返回用户的选择
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from wuwei.tools import ToolRegistry

# 决策管理：session_id -> list[decision_event]（用于 SSE 推送）
_decision_queues: dict[str, list[dict[str, Any]]] = {}

# 决策 Future：decision_id -> Future（用于阻塞等待用户响应）
_decision_futures: dict[str, asyncio.Future[str]] = {}

DECISION_TIMEOUT_SECONDS = 300


async def resolve_decision(decision_id: str, answer: str) -> bool:
    """前端调用：resolve 一个决策的 Future

    返回 True 表示成功，False 表示 decision_id 不存在或已超时。
    """
    future = _decision_futures.pop(decision_id, None)
    if future and not future.done():
        future.set_result(answer)
        return True
    return False


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
            import json
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [s.strip() for s in options.split(',') if s.strip()]
        if not isinstance(options, list):
            return {"error": "options 必须是数组"}
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

        # 推送到决策队列，由 agent_service 的 stream_chat 消费并 SSE 推送给前端
        if session_id not in _decision_queues:
            _decision_queues[session_id] = []
        _decision_queues[session_id].append(decision_event)

        # 创建 Future 并阻塞等待用户响应
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        _decision_futures[decision_id] = future

        try:
            answer = await asyncio.wait_for(future, timeout=DECISION_TIMEOUT_SECONDS)
            return {
                "ok": True,
                "decision_id": decision_id,
                "answer": answer,
                "message": f"用户选择了：{answer}",
            }
        except asyncio.TimeoutError:
            _decision_futures.pop(decision_id, None)
            return {
                "ok": False,
                "decision_id": decision_id,
                "error": "用户未在规定时间内做出决策",
                "timeout": True,
            }


def get_decision_queue(session_id: str) -> list[dict[str, Any]]:
    """获取指定 session 的待处理决策列表（由 agent_service 调用）"""
    return _decision_queues.pop(session_id, [])



