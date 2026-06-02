"""用户记忆服务

使用 wuwei 2.2.0 的 InMemoryMemoryStore 实现跨会话记忆。

触发时机：
- 提取：对话结束时（done 事件），用 LLM 从对话中提取关键信息
- 注入：发送消息前，根据用户消息搜索相关记忆，注入到上下文中

存储方式：
- 内存存储（InMemoryMemoryStore），进程重启后丢失
- 每用户独立命名空间（namespace = user_{id}）
"""

import asyncio
import logging
from typing import Any

from wuwei.memory import InMemoryMemoryStore, SimpleEmbedder

_logger = logging.getLogger("memory_service")

# 记忆提取提示词
MEMORY_EXTRACTION_PROMPT = """从以下对话中提取用户的关键信息，用于后续个性化服务。

只提取以下类型的信息：
- 用户偏好（喜欢的主题、风格、习惯）
- 重要事实（职业、项目、需求）
- 明确指令（"我总是要用xx主题"、"我不喜欢xx"）

忽略：
- 临时性对话内容
- 工具调用细节
- 不重要的寒暄

输出 JSON 数组，每条包含 content（事实描述）和 importance（0.0-1.0）。
如果没有值得记忆的信息，输出空数组 []。

对话内容：
{conversation}

输出（纯 JSON，不要代码块）："""


class UserMemoryService:
    """用户记忆服务（所有方法为 async）"""

    def __init__(self):
        self._embedder = SimpleEmbedder(dim=256)
        self._store = InMemoryMemoryStore(embedder=self._embedder)
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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """为用户添加一条记忆"""
        namespace = f"user_{user_id}"
        await self._store.add(
            content=content,
            namespace=namespace,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            metadata=metadata,
        )
        _logger.debug(f"Added memory for user {user_id}: {content[:50]}...")

    async def search_memory(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """搜索用户的记忆"""
        namespace = f"user_{user_id}"
        records = await self._store.search(query, namespace=namespace, limit=limit)
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

    async def get_all_memories(self, user_id: int) -> list[dict[str, Any]]:
        """获取用户的所有记忆"""
        namespace = f"user_{user_id}"
        records = await self._store.list_all(namespace=namespace)
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

    async def delete_memory(self, user_id: int, memory_id: str) -> bool:
        """删除用户的一条记忆"""
        namespace = f"user_{user_id}"
        try:
            await self._store.delete(memory_id, namespace=namespace)
            return True
        except Exception:
            return False

    async def get_memory_context(self, user_id: int, query: str, *, limit: int = 3) -> str:
        """获取与查询相关的记忆上下文，用于注入到 LLM 提示词中"""
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

        # 每 2 次对话提取一次（测试期间降低频率）
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

            import json
            content = response.message.content or "[]"
            # 提取 JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            memories = json.loads(content.strip())
            if not isinstance(memories, list):
                return

            for mem in memories:
                if isinstance(mem, dict) and mem.get("content"):
                    await self.add_memory(
                        user_id,
                        str(mem["content"]),
                        memory_type="fact",
                        importance=float(mem.get("importance", 0.5)),
                        tags=["auto-extracted"],
                    )

            if memories:
                _logger.info(f"Extracted {len(memories)} memories for user {user_id}")

        except Exception as e:
            _logger.debug(f"Memory extraction failed (non-critical): {e}")


# 全局单例
_memory_service: UserMemoryService | None = None


def get_memory_service() -> UserMemoryService:
    """获取记忆服务单例"""
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService()
    return _memory_service
