"""记忆工具

LLM 可主动搜索和保存用户记忆：
- search_memory: 搜索用户的历史记忆
- save_memory: 保存新的用户记忆

这让 LLM 可以自主决定何时查询/保存记忆，比自动注入更灵活。
"""

from __future__ import annotations

from typing import Any

from wuwei.tools import ToolRegistry


def register_memory_tools(registry: ToolRegistry) -> None:
    """注册记忆工具"""

    @registry.tool(
        name="search_memory",
        display_name="搜索记忆",
        description="搜索当前用户的历史记忆。用于了解用户的偏好、身份、技术栈等信息。在回答用户问题前，如果需要了解用户背景，可以调用此工具。",
    )
    async def search_memory(query: str, limit: int = 5) -> dict[str, Any]:
        """搜索用户记忆。

        参数:
            query: 搜索关键词（如用户名、技术栈、项目名等）
            limit: 返回结果数量（默认 5）

        返回:
            匹配的记忆列表
        """
        from app.services.agent_service import _current_session_id
        from app.services.session_storage import DatabaseAgentStorage

        session_id = _current_session_id.get()
        if not session_id:
            return {"error": "无法获取当前会话", "memories": []}

        # 获取用户 ID
        storage = DatabaseAgentStorage()
        owner_id = await storage.get_owner_id(session_id)
        if not owner_id:
            return {"error": "无法获取用户信息", "memories": []}

        from app.services.memory_service import get_memory_service
        memories = await get_memory_service().search_memory(owner_id, query, limit=limit)

        return {
            "memories": memories,
            "count": len(memories),
        }

    @registry.tool(
        name="save_memory",
        display_name="保存记忆",
        description="保存一条关于用户的重要信息到记忆库。当用户提到自己的偏好、身份、技术栈等值得记住的信息时，主动调用此工具保存。",
    )
    async def save_memory(
        content: str,
        memory_type: str = "fact",
        importance: float = 0.7,
    ) -> dict[str, Any]:
        """保存用户记忆。

        参数:
            content: 记忆内容（简短明确，如"用户叫张三"、"用户喜欢 Vue"）
            memory_type: 记忆类型（fact=事实, preference=偏好, tech=技术栈, project=项目）
            importance: 重要性（0.1-1.0，默认 0.7）

        返回:
            保存结果
        """
        from app.services.agent_service import _current_session_id
        from app.services.session_storage import DatabaseAgentStorage

        session_id = _current_session_id.get()
        if not session_id:
            return {"error": "无法获取当前会话"}

        storage = DatabaseAgentStorage()
        owner_id = await storage.get_owner_id(session_id)
        if not owner_id:
            return {"error": "无法获取用户信息"}

        from app.services.memory_service import get_memory_service
        memory_id = await get_memory_service().add_memory(
            owner_id,
            content,
            memory_type=memory_type,
            importance=max(0.1, min(1.0, importance)),
            source="tool",
        )

        return {
            "ok": True,
            "memory_id": memory_id,
            "message": f"已保存记忆：{content}",
        }
