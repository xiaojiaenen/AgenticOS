"""用户记忆服务

使用 wuwei 2.2.0 的 InMemoryMemoryStore 实现跨会话记忆。

触发时机：
- 提取：对话结束时（done 事件），从对话中提取关键信息
- 注入：发送消息前，根据用户消息搜索相关记忆，注入到上下文中

存储方式：
- 内存存储（InMemoryMemoryStore），进程重启后丢失
- 每用户独立命名空间（namespace = user_{id}）
"""

import logging
from typing import Any

from wuwei.memory import InMemoryMemoryStore, SimpleEmbedder

_logger = logging.getLogger("memory_service")


class UserMemoryService:
    """用户记忆服务"""

    def __init__(self):
        self._embedder = SimpleEmbedder(dim=256)
        self._store = InMemoryMemoryStore(embedder=self._embedder)
        self._initialized = False

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._initialized = True
            _logger.info("UserMemoryService initialized")

    def add_memory(
        self,
        user_id: int,
        content: str,
        *,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """为用户添加一条记忆"""
        self._ensure_initialized()
        namespace = f"user_{user_id}"
        self._store.add(
            content=content,
            namespace=namespace,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            metadata=metadata,
        )
        _logger.debug(f"Added memory for user {user_id}: {content[:50]}...")

    def search_memory(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """搜索用户的记忆"""
        self._ensure_initialized()
        namespace = f"user_{user_id}"
        records = self._store.search(query, namespace=namespace, limit=limit)
        return [
            {
                "id": r.id,
                "content": r.content,
                "memory_type": r.memory_type,
                "importance": r.importance,
                "tags": r.tags,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    def get_all_memories(self, user_id: int) -> list[dict[str, Any]]:
        """获取用户的所有记忆"""
        self._ensure_initialized()
        namespace = f"user_{user_id}"
        records = self._store.list_all(namespace=namespace)
        return [
            {
                "id": r.id,
                "content": r.content,
                "memory_type": r.memory_type,
                "importance": r.importance,
                "tags": r.tags,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]

    def delete_memory(self, user_id: int, memory_id: str) -> bool:
        """删除用户的一条记忆"""
        self._ensure_initialized()
        namespace = f"user_{user_id}"
        try:
            self._store.delete(memory_id, namespace=namespace)
            return True
        except Exception:
            return False

    def get_memory_context(self, user_id: int, query: str, *, limit: int = 3) -> str:
        """获取与查询相关的记忆上下文，用于注入到 LLM 提示词中"""
        self._ensure_initialized()
        records = self.search_memory(user_id, query, limit=limit)
        if not records:
            return ""
        lines = ["## 用户记忆（来自历史对话）"]
        for r in records:
            lines.append(f"- [{r['memory_type']}] {r['content']}")
        return "\n".join(lines)


# 全局单例
_memory_service: UserMemoryService | None = None


def get_memory_service() -> UserMemoryService:
    """获取记忆服务单例"""
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service
