"""用户记忆服务

数据库持久化存储，支持：
- 跨会话记忆（用户所有会话共享）
- 跨重启持久化（数据库存储）
- LLM 工具调用（search_memory / save_memory）
- 管理后台查看所有用户记忆

存储方式：
- SQLAlchemy + SQLite/MySQL
- 每用户独立（user_id 隔离）
"""

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import func, select, delete
from sqlalchemy.orm import Session

from app.db.models import MemoryModel
from app.db.session import create_db_session

_logger = logging.getLogger("memory_service")


class UserMemoryService:
    """用户记忆服务（数据库持久化）"""

    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory
        self._conversation_counts: dict[int, int] = {}  # user_id -> 对话计数
        self._conversation_buffers: dict[int, list[dict]] = {}  # user_id -> 多轮对话缓冲

    async def add_memory(
        self,
        user_id: int,
        content: str,
        *,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: list[str] | None = None,
        source: str = "auto",
    ) -> int:
        """为用户添加一条记忆，返回记忆 ID。"""

        def _run() -> int:
            with self.session_factory() as db:
                row = MemoryModel(
                    user_id=user_id,
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    tags_json=json.dumps(tags, ensure_ascii=False) if tags else None,
                    source=source,
                )
                db.add(row)
                db.commit()
                return row.id

        memory_id = await asyncio.to_thread(_run)
        _logger.info(f"Added memory for user {user_id}: {content[:50]}...")
        return memory_id

    async def search_memory(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """搜索用户的记忆（关键词匹配）。"""

        def _run() -> list[dict[str, Any]]:
            with self.session_factory() as db:
                rows = db.scalars(
                    select(MemoryModel)
                    .where(MemoryModel.user_id == user_id)
                    .where(MemoryModel.content.contains(query))
                    .order_by(MemoryModel.importance.desc(), MemoryModel.created_at.desc())
                    .limit(limit)
                ).all()
                return [self._row_to_dict(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def get_all_memories(self, user_id: int) -> list[dict[str, Any]]:
        """获取用户的所有记忆。"""

        def _run() -> list[dict[str, Any]]:
            with self.session_factory() as db:
                rows = db.scalars(
                    select(MemoryModel)
                    .where(MemoryModel.user_id == user_id)
                    .order_by(MemoryModel.importance.desc(), MemoryModel.created_at.desc())
                ).all()
                return [self._row_to_dict(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def get_all_memories_admin(self) -> list[dict[str, Any]]:
        """管理员：获取所有用户的记忆。"""

        def _run() -> list[dict[str, Any]]:
            with self.session_factory() as db:
                rows = db.scalars(
                    select(MemoryModel)
                    .order_by(MemoryModel.user_id, MemoryModel.importance.desc())
                ).all()
                return [self._row_to_dict(r) for r in rows]

        return await asyncio.to_thread(_run)

    async def delete_memory(self, memory_id: int, user_id: int | None = None) -> bool:
        """删除一条记忆。user_id 为 None 时管理员可删除任意记忆。"""

        def _run() -> bool:
            with self.session_factory() as db:
                row = db.get(MemoryModel, memory_id)
                if row is None:
                    return False
                if user_id is not None and row.user_id != user_id:
                    return False
                db.delete(row)
                db.commit()
                return True

        return await asyncio.to_thread(_run)

    async def get_memory_context(self, user_id: int, query: str, *, limit: int = 3) -> str:
        """获取与查询相关的记忆上下文，用于注入到 LLM 提示词中。"""
        records = await self.search_memory(user_id, query, limit=limit)
        if not records:
            return ""
        lines = ["## 用户记忆（来自历史对话）"]
        for r in records:
            lines.append(f"- [{r['memory_type']}] {r['content']}")
        return "\n".join(lines)

    async def extract_and_save_memories(
        self,
        user_id: int,
        user_message: str,
        assistant_response: str,
        llm_gateway=None,
    ) -> None:
        """用 LLM 从对话中提取关键信息并保存为记忆。

        每 2 次对话提取一次，使用多轮对话历史进行提取。
        """
        # 收集多轮对话历史
        if user_id not in self._conversation_buffers:
            self._conversation_buffers[user_id] = []
        self._conversation_buffers[user_id].append({
            "user": user_message,
            "assistant": assistant_response[:500],
        })
        # 只保留最近 6 轮对话
        self._conversation_buffers[user_id] = self._conversation_buffers[user_id][-6:]

        # 每 2 次对话提取一次
        count = self._conversation_counts.get(user_id, 0) + 1
        self._conversation_counts[user_id] = count
        _logger.info(f"Memory extraction check: user={user_id}, count={count}, will_extract={count % 2 == 0}")
        if count % 2 != 0:
            return

        try:
            from wuwei.llm import LLMGateway

            if llm_gateway is None:
                llm_gateway = LLMGateway.from_env()

            # 使用多轮对话历史
            history = self._conversation_buffers.get(user_id, [])
            conversation_lines = []
            for turn in history:
                conversation_lines.append(f"用户: {turn['user']}")
                conversation_lines.append(f"AI: {turn['assistant']}")
            conversation = "\n".join(conversation_lines)
            prompt = MEMORY_EXTRACTION_PROMPT.format(conversation=conversation)

            from wuwei.core.message import SystemMessage, HumanMessage
            response = await llm_gateway.generate(
                messages=[
                    SystemMessage(content="你是记忆提取器，只输出 JSON。"),
                    HumanMessage(content=prompt),
                ],
            )

            import json as json_lib
            content = response.message.content or "[]"
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            memories = json_lib.loads(content.strip())
            if not isinstance(memories, list):
                return

            for mem in memories:
                if isinstance(mem, dict) and mem.get("content"):
                    await self.add_memory(
                        user_id,
                        str(mem["content"]),
                        memory_type=mem.get("type", "fact"),
                        importance=float(mem.get("importance", 0.5)),
                        tags=["auto-extracted"],
                        source="auto",
                    )

            if memories:
                _logger.info(f"Extracted {len(memories)} memories for user {user_id}")

        except Exception as e:
            _logger.debug(f"Memory extraction failed (non-critical): {e}")

    @staticmethod
    def _row_to_dict(row: MemoryModel) -> dict[str, Any]:
        tags = []
        if row.tags_json:
            try:
                tags = json.loads(row.tags_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": row.id,
            "user_id": row.user_id,
            "content": row.content,
            "memory_type": row.memory_type,
            "importance": row.importance,
            "tags": tags,
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


MEMORY_EXTRACTION_PROMPT = """从以下对话中提取用户的关键信息，用于后续个性化服务。

只提取以下类型的信息：
- 用户的身份信息（姓名、职业、所在地等）
- 用户的偏好（喜欢什么、不喜欢什么）
- 用户的技术栈（使用什么语言、框架、工具）
- 用户的项目信息（在做什么项目、遇到什么问题）

对话内容：
{conversation}

输出 JSON 数组，每个元素包含：
- content: 记忆内容（简短明确）
- type: 记忆类型（fact/preference/tech/project）
- importance: 重要性（0.1-1.0）

如果没有值得提取的信息，返回空数组 []。

示例输出：
[
  {{"content": "用户叫张三", "type": "fact", "importance": 0.9}},
  {{"content": "用户喜欢用 Vue 3", "type": "preference", "importance": 0.7}}
]"""


# 全局单例（线程安全）
from app.core.singleton import ThreadSafeSingleton

_memory_service_singleton = ThreadSafeSingleton(UserMemoryService)


def get_memory_service() -> UserMemoryService:
    """获取记忆服务单例"""
    return _memory_service_singleton.get()
