"""Redis Vector 存储：基于 RediSearch 的 KNN 向量检索。

使用 Redis Stack 的 VECTOR + FT.SEARCH 实现。
- 索引名: memory_vector_index
- Key 前缀: memory:vec:{entity_type}:{entity_id}
- 距离度量: COSINE
- 算法: HNSW

Redis 不可用（内存 fallback）时，向量检索降级为空，BM25 仍可工作。
注意：需要单独的 binary client（decode_responses=False）处理向量字节。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.redis import is_redis_memory

_logger = logging.getLogger("memory_vector_store")
_settings = get_settings()

_INDEX_NAME = "memory_vector_index"
_KEY_PREFIX = "memory:vec:"

# 单独的 binary redis client（懒加载）
_binary_client = None


def _get_binary_redis():
    """获取 decode_responses=False 的 redis client（用于存取二进制向量）"""
    global _binary_client
    if _binary_client is not None:
        return _binary_client

    if is_redis_memory() or not _settings.redis_url:
        return None  # 内存 fallback 不支持向量

    try:
        import redis.asyncio as aioredis
        if _settings.redis_cluster:
            _logger.warning("Cluster 模式暂不支持单独 binary client，向量检索降级")
            return None
        _binary_client = aioredis.from_url(_settings.redis_url, decode_responses=False)
        return _binary_client
    except Exception as e:
        _logger.warning(f"创建 binary redis client 失败: {e}")
        return None


class MemoryVectorStore:
    """向量存储：Redis VECTOR 优先，不可用时降级为空"""

    def __init__(self) -> None:
        self._dim = _settings.memory_embedding_dimensions
        self._initialized = False

    async def _ensure_index(self) -> bool:
        """创建 RediSearch 索引（如不存在）"""
        if self._initialized:
            return True

        client = _get_binary_redis()
        if client is None:
            return False

        try:
            await client.execute_command(
                "FT.CREATE", _INDEX_NAME,
                "ON", "HASH",
                "PREFIX", 1, _KEY_PREFIX,
                "SCHEMA",
                "user_id", "NUMERIC", "SORTABLE",
                "layer", "TAG",
                "entity_type", "TAG",
                "entity_id", "NUMERIC", "SORTABLE",
                "embedding", "VECTOR", "HNSW", "TYPE", "FLOAT32",
                "DIM", str(self._dim), "DISTANCE_METRIC", "COSINE",
            )
            _logger.info(f"Vector index created: {_INDEX_NAME}")
        except Exception as e:
            if "Index already exists" not in str(e):
                _logger.warning(f"创建向量索引失败: {e}")
                return False

        self._initialized = True
        return True

    async def upsert(
        self,
        entity_id: int,
        entity_type: str,    # "atom" | "scenario"
        user_id: int,
        layer: str,
        text: str,
        embedding: list[float],
    ) -> None:
        """写入或更新一条向量"""
        if not await self._ensure_index():
            return

        client = _get_binary_redis()
        if client is None:
            return

        try:
            key = f"{_KEY_PREFIX}{entity_type}:{entity_id}"
            vector_bytes = np.array(embedding, dtype=np.float32).tobytes()
            await client.hset(key, mapping={
                "user_id": str(user_id).encode(),
                "layer": layer.encode(),
                "entity_type": entity_type.encode(),
                "entity_id": str(entity_id).encode(),
                "embedding": vector_bytes,
                "text": text[:500].encode(),
            })
        except Exception as e:
            _logger.warning(f"Vector upsert 失败 {entity_type}:{entity_id}: {e}")

    async def search(
        self,
        query_embedding: list[float],
        user_id: int,
        layers: tuple[str, ...],
        entity_types: tuple[str, ...] = ("atom", "scenario"),
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """KNN 向量检索"""
        if not await self._ensure_index():
            return []

        client = _get_binary_redis()
        if client is None:
            return []

        try:
            query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
            layer_filter = "|".join(layers)
            type_filter = "|".join(entity_types)

            result = await client.execute_command(
                "FT.SEARCH", _INDEX_NAME,
                f"@user_id:[{user_id} {user_id}] "
                f"@layer:{{{layer_filter}}} "
                f"@entity_type:{{{type_filter}}}",
                "WITHSCORES",
                "LIMIT", 0, limit,
                "SORTBY", "__embedding_score",
                "PARAMS", 2, "embedding", query_vector,
                "DIALECT", 2,
            )
            return self._parse_search_result(result)
        except Exception as e:
            _logger.warning(f"Vector search 失败: {e}")
            return []

    async def delete(self, entity_type: str, entity_id: int) -> None:
        """删除一条向量"""
        client = _get_binary_redis()
        if client is None:
            return
        try:
            await client.delete(f"{_KEY_PREFIX}{entity_type}:{entity_id}")
        except Exception as e:
            _logger.debug(f"Vector delete 失败: {e}")

    @staticmethod
    def _parse_search_result(result: Any) -> list[dict[str, Any]]:
        """解析 FT.SEARCH 返回。

        FT.SEARCH 返回格式（DIALECT 2 + WITHSCORES）：
        [total_count, key1, score1, fields1, key2, score2, fields2, ...]
        """
        if not result or result[0] == 0:
            return []

        items: list[dict[str, Any]] = []
        # result[0] 是总数，之后是 [key, score, fields] 三元组
        i = 1
        while i + 2 < len(result):
            doc_id = result[i]
            score = result[i + 1]
            fields_raw = result[i + 2]

            # fields_raw 是 [field1, value1, field2, value2, ...]
            field_map: dict[str, Any] = {}
            if isinstance(fields_raw, list):
                for j in range(0, len(fields_raw), 2):
                    if j + 1 < len(fields_raw):
                        k = fields_raw[j]
                        v = fields_raw[j + 1]
                        if isinstance(k, bytes):
                            k = k.decode()
                        field_map[k] = v

            def _decode(v):
                if isinstance(v, bytes):
                    return v.decode()
                return v

            items.append({
                "doc_id": doc_id.decode() if isinstance(doc_id, bytes) else doc_id,
                "score": float(score),
                "entity_id": int(_decode(field_map.get("entity_id", "0"))),
                "entity_type": _decode(field_map.get("entity_type", "")),
                "layer": _decode(field_map.get("layer", "")),
            })
            i += 3

        return items


_vector_store_singleton: MemoryVectorStore | None = None


def get_vector_store() -> MemoryVectorStore:
    """获取 vector store 单例"""
    global _vector_store_singleton
    if _vector_store_singleton is None:
        _vector_store_singleton = MemoryVectorStore()
    return _vector_store_singleton
