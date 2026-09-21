"""记忆工具

LLM 可主动搜索和保存用户记忆（多层记忆系统 L0-L3）：
- search_memory: 搜索用户记忆（L1+L2 混合检索）
- save_memory: 保存新的用户记忆（L1 atom）
- get_user_persona: 获取用户长期画像（L3）
- list_memory_scenarios: 列出用户场景块（L2）
"""

from __future__ import annotations

from typing import Any

from wuwei.tools import ToolRegistry

# 模块加载时记录
import os
_debug_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "memory_debug.log")
try:
    with open(_debug_path, "w") as f:
        f.write(f"MEMORY_TOOLS_MODULE_LOADED: {__file__}\n")
except Exception as e:
    pass


def register_memory_tools(registry: ToolRegistry) -> None:
    """注册记忆工具"""

    @registry.tool(
        name="search_memory",
        display_name="搜索记忆",
        description="搜索当前用户的历史记忆（L1+L2 混合检索）。当用户询问自己的身份（如'我是谁'、'我叫什么'）、偏好、技术栈、项目，或需要了解用户背景时，必须调用此工具。即使用户没有明确说'搜索记忆'，只要问题涉及用户自身信息，就应该调用。",
    )
    async def search_memory(query: str, limit: int = 5) -> dict[str, Any]:
        """搜索用户记忆（BM25 + 向量混合检索）。"""
        from app.services.memory_service import get_memory_service
        from app.db.session import SessionLocal
        from app.db.models import AgentSessionModel, AgentMessageModel
        from sqlalchemy import select, func, desc

        # 获取最近有消息的 session 的 user_id
        def _get_recent_user_id():
            with SessionLocal() as db:
                # 查找最近的消息对应的 session
                recent_msg = db.query(AgentMessageModel).order_by(desc(AgentMessageModel.created_at)).first()
                if recent_msg:
                    session = db.get(AgentSessionModel, recent_msg.session_id)
                    if session:
                        return session.user_id
            return None

        user_id = _get_recent_user_id()

        if not user_id:
            return {"error": "无法获取用户信息", "memories": [], "debug": "no_user_id"}

        memories = await get_memory_service().search_memory(user_id, query, limit=limit)
        return {
            "memories": memories,
            "count": len(memories),
            "debug_user_id": user_id,
        }

    @registry.tool(
        name="save_memory",
        display_name="保存记忆",
        description="保存一条关于用户的重要信息到记忆库（L1 atom，自动生成向量索引）。当用户提到自己的偏好、身份、技术栈等值得记住的信息时，主动调用此工具保存。",
    )
    async def save_memory(
        content: str,
        memory_type: str = "fact",
        importance: float = 0.7,
    ) -> dict[str, Any]:
        """保存用户记忆（L1 atom，自动生成向量索引）。"""
        from app.services.memory_service import get_memory_service
        from app.db.session import SessionLocal
        from app.db.models import AgentSessionModel, AgentMessageModel
        from sqlalchemy import select, func, desc

        def _get_recent_user_id():
            with SessionLocal() as db:
                recent_msg = db.query(AgentMessageModel).order_by(desc(AgentMessageModel.created_at)).first()
                if recent_msg:
                    session = db.get(AgentSessionModel, recent_msg.session_id)
                    if session:
                        return session.user_id
            return None

        user_id = _get_recent_user_id()
        if not user_id:
            return {"error": "无法获取用户信息"}

        memory_id = await get_memory_service().add_memory(
            user_id,
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

    @registry.tool(
        name="get_user_persona",
        display_name="获取用户画像",
        description="获取用户的长期画像（L3 Persona），包含身份、偏好、技术栈、目标、项目等综合信息。用于快速了解用户全貌。",
    )
    async def get_user_persona() -> dict[str, Any]:
        """获取用户长期画像（L3 Persona）。"""
        from app.services.memory_service import get_memory_service
        from app.db.session import SessionLocal
        from app.db.models import AgentSessionModel, AgentMessageModel
        from sqlalchemy import select, func, desc

        def _get_recent_user_id():
            with SessionLocal() as db:
                recent_msg = db.query(AgentMessageModel).order_by(desc(AgentMessageModel.created_at)).first()
                if recent_msg:
                    session = db.get(AgentSessionModel, recent_msg.session_id)
                    if session:
                        return session.user_id
            return None

        user_id = _get_recent_user_id()
        if not user_id:
            return {"error": "无法获取用户信息", "exists": False}

        persona = await get_memory_service().get_persona(user_id)
        return {
            "exists": persona is not None,
            "persona": persona,
        }

    @registry.tool(
        name="list_memory_scenarios",
        display_name="列出记忆场景",
        description="列出用户的场景块（L2 Scenario）。场景块是从多个 L1 记忆中聚合而成的主题场景，用于理解用户在特定情境下的偏好和行为。",
    )
    async def list_memory_scenarios(limit: int = 10) -> dict[str, Any]:
        """列出用户场景块（L2 Scenario）。"""
        from app.services.memory_service import get_memory_service
        from app.db.session import SessionLocal
        from app.db.models import AgentSessionModel, AgentMessageModel
        from sqlalchemy import select, func, desc

        def _get_recent_user_id():
            with SessionLocal() as db:
                recent_msg = db.query(AgentMessageModel).order_by(desc(AgentMessageModel.created_at)).first()
                if recent_msg:
                    session = db.get(AgentSessionModel, recent_msg.session_id)
                    if session:
                        return session.user_id
            return None

        user_id = _get_recent_user_id()
        if not user_id:
            return {"error": "无法获取用户信息"}

        scenarios = await get_memory_service().list_scenarios(user_id, limit=limit)
        return {
            "scenarios": scenarios,
            "count": len(scenarios),
        }
