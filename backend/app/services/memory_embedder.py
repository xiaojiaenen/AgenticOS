"""向量生成器：复用 OpenAI 配置，带 Redis 缓存。

存储策略：
- 向量本身不进 DB（避免 BLOB 膨胀）
- 缓存到 Redis 24h（同内容不重复计费）
- 真正使用时由 vector_store 持久化到 Redis VECTOR 索引
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Sequence

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis, is_redis_memory

_logger = logging.getLogger("memory_embedder")
_settings = get_settings()


class MemoryEmbedder:
    """文本 → 向量，带内容哈希缓存"""

    def __init__(self) -> None:
        self._model = _settings.memory_embedding_model
        self._dim = _settings.memory_embedding_dimensions
        self._base_url = (_settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._api_key = _settings.openai_api_key or ""

    async def embed(self, text: str) -> list[float]:
        """单条文本 → 向量"""
        if not text.strip():
            return [0.0] * self._dim

        cache_key = f"emb:{self._model}:{hashlib.sha256(text.encode()).hexdigest()}"

        # 缓存命中（内存 Redis 也支持，作为开发环境加速）
        redis = get_redis()
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        # 调用 OpenAI Embeddings API
        vector = await self._call_api([text])
        if not vector:
            return [0.0] * self._dim

        # 写入缓存（24h TTL）
        try:
            await redis.set(cache_key, json.dumps(vector[0]), ex=86400)
        except Exception:
            pass

        return vector[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """批量文本 → 向量列表"""
        if not texts:
            return []
        return await self._call_api(list(texts))

    async def _call_api(self, inputs: list[str]) -> list[list[float]]:
        if not self._api_key:
            _logger.warning("OPENAI_API_KEY 未配置，embedding 返回零向量")
            return [[0.0] * self._dim] * len(inputs)

        try:
            # 单次最多 64 条，避免超限
            results: list[list[float]] = []
            for i in range(0, len(inputs), 64):
                batch = [t[:8000] for t in inputs[i:i + 64]]  # 截断保护
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"{self._base_url}/embeddings",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={"model": self._model, "input": batch},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for item in data["data"]:
                        results.append(item["embedding"])
            return results
        except Exception as e:
            _logger.warning(f"Embedding API 调用失败: {e}")
            return [[0.0] * self._dim] * len(inputs)


_embedder_singleton: MemoryEmbedder | None = None


def get_embedder() -> MemoryEmbedder:
    """获取 embedder 单例"""
    global _embedder_singleton
    if _embedder_singleton is None:
        _embedder_singleton = MemoryEmbedder()
    return _embedder_singleton
