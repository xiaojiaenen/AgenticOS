"""决策工具

LLM 调用工具提供问题和选项，让用户做决策。
每个决策都有一个"自定义输入"选项，用户可以输入自己的答案。
"""

from __future__ import annotations

import uuid
from typing import Any

from wuwei.tools import ToolRegistry


def register_decision_tools(registry: ToolRegistry, approval_manager=None) -> None:
    """注册决策工具"""

    @registry.tool(
        name="ask_user_decision",
        display_name="请求用户决策",
        description="向用户提出一个决策问题，提供选项让用户选择。用于需要用户确认或选择的场景。",
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
            包含 decision_id 和选项的字典，等待用户决策
        """
        if len(options) < 2:
            return {"error": "至少需要 2 个选项"}

        decision_id = str(uuid.uuid4())[:8]

        # 构建决策事件
        decision_event = {
            "decision_id": decision_id,
            "type": "user_decision",
            "question": question,
            "options": options,
            "context": context,
            "allow_custom": True,  # 允许用户自定义输入
            "status": "pending",
        }

        # 如果有 approval_manager，通过它推送事件
        if approval_manager is not None:
            # 使用 approval_manager 的订阅机制推送决策事件
            # 这里返回事件数据，由 agent_service 层处理推送
            return {
                "ok": True,
                "decision_id": decision_id,
                "event": decision_event,
                "message": f"已向用户提出决策问题：{question}",
            }

        # 没有 approval_manager 时，返回事件数据
        return {
            "ok": True,
            "decision_id": decision_id,
            "event": decision_event,
            "message": f"已向用户提出决策问题：{question}",
        }
