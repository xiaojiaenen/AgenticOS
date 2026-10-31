"""向量生成器：本地 bge 模型优先，远程 API 兜底，带 Redis 缓存。

2026-10-31 教训：线上 OPENAI_BASE_URL=api.deepseek.com（没有 embeddings
端点），embed 全部失败后**静默返回零向量** —— 整个记忆向量体系瘫痪
（向量检索静默退化为 BM25-only、去重闸的余弦恒为 0），却无人察觉。
因此：

- **本地模型优先**：配置了 ``KNOWLEDGE_EMBEDDING_LOCAL_MODEL`` 就走本地
  bge（与知识库语义检索共用同一套模型与 HF 缓存，零 API 成本、内网可用）；
- 远程 API 只是回退（text-embedding-3-small 等真支持 /embeddings 的端点）；
- **失败抛异常而不是返回零向量**：零向量会污染余弦计算（与任何向量
  相似度恒 0，去重/检索静默失效）。所有调用方都有 try/except 容忍降级。

存储策略：
- 向量不进 DB（避免 BLOB 膨胀），Redis 缓存 24h + vector store 持久化
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Sequence

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis

_logger = logging.getLogger("memory_embedder")
_settings = get_settings()


class MemoryEmbeddingError(RuntimeError):
    """向量生成失败（本地模型不可用或远程 API 故障）。"""


class MemoryEmbedder:
    """文本 → 向量。本地模型优先，远程 API 兜底，带内容哈希缓存。"""

    def __init__(self) -> None:
        self._model = _settings.memory_embedding_model
        self._base_url = (_settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._api_key = _settings.openai_api_key or ""
        # 本地模型（与知识库共用配置与 HF 缓存）：配置了就用，零 API 成本
        self._local_model = (_settings.knowledge_embedding_local_model or "").strip()
        self._local_dims = _settings.knowledge_embedding_local_dimensions or None
        self._local: object | None = None  # 懒加载 LocalEmbedder
        self._dim = _settings.memory_embedding_dimensions
        if self._local_model:
            _logger.info(
                "memory embedder: using local model %s (dims cfg=%s)",
                self._local_model, self._local_dims,
            )

    @property
    def backend(self) -> str:
        """当前向量后端标识（local:<model> / remote:<model>）。"""
        return f"local:{self._local_model}" if self._local_model else f"remote:{self._model}"

    @property
    def dimensions(self) -> int:
        """实际输出维度。本地模型懒加载后以真实维度为准。"""
        if self._local_model and self._local is not None:
            dims = getattr(self._local, "dimensions", None)
            if dims:
                return int(dims)
        if self._local_model:
            return self._local_dims or 1024
        return self._dim

    def _get_local(self):
        if self._local is None:
            from app.services.knowledge.local_embedder import get_local_embedder

            # 不传 expected_dims：以模型真实维度为准（vector store 跟随本属性）
            self._local = get_local_embedder(self._local_model)
        return self._local

    async def embed(self, text: str) -> list[float]:
        """单条文本 → 向量。失败抛 MemoryEmbeddingError（调用方降级）。"""
        if not text.strip():
            raise MemoryEmbeddingError("empty text")

        cache_key = f"emb:{self.backend}:{hashlib.sha256(text.encode()).hexdigest()}"

        # 缓存命中（内存 Redis 也支持，作为开发环境加速）
        redis = get_redis()
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

        if self._local_model:
            vectors = await asyncio.to_thread(self._get_local().encode, [text])
            vector = vectors[0]
        else:
            vectors = await self._call_api([text])
            vector = vectors[0]

        # 写入缓存（24h TTL）
        try:
            await redis.set(cache_key, json.dumps(vector), ex=86400)
        except Exception:
            pass
        return vector

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """批量文本 → 向量列表。失败抛 MemoryEmbeddingError。"""
        if not texts:
            return []
        if self._local_model:
            return await asyncio.to_thread(self._get_local().encode, list(texts))
        return await self._call_api(list(texts))

    async def _call_api(self, inputs: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise MemoryEmbeddingError("OPENAI_API_KEY 未配置，远程 embedding 不可用")

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
            raise MemoryEmbeddingError(f"Embedding API 调用失败: {e}") from e


_embedder_singleton: MemoryEmbedder | None = None


def get_embedder() -> MemoryEmbedder:
    """获取 embedder 单例"""
    global _embedder_singleton
    if _embedder_singleton is None:
        _embedder_singleton = MemoryEmbedder()
    return _embedder_singleton
