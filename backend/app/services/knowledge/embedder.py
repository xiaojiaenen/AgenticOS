"""知识库向量化：embedding 生成、编码存取与批量回填。

设计取舍
--------
- **页级向量**：一个 Wiki 页 = 一个切片（与《知识库系统设计方案》里
  ``chunk_size=4000`` 的量级一致，编译产物页通常在 500~3000 字）。不引入
  独立 chunk 表：页本身就是人类可读的最小知识单元，切片表只会让溯源变复杂。
- **同步实现**：检索链路（``KnowledgeRetrieval``）与编译链路（``IngestPipeline``）
  都是同步的，所以这里用 ``httpx.Client`` 而不是 ``AsyncClient`` —— 避免在同步
  代码里 ``asyncio.run`` 造事件循环。
- **降级而非报错**：未配置 API Key、上游超时、返回维度不符，一律返回 ``None``
  并由调用方跳过向量召回。BM25 仍然可用，检索不会因为向量不可用而整体失败。
- **存储格式**：``kb_wiki_pages.embedding`` 存 base64(float32 小端)。
  1536 维 = 6144 字节 → base64 后 8KB，比 JSON 数组（约 25KB）省三分之二，
  解码走 ``numpy.frombuffer``，无精度损失（float32 就是上游返回的精度）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Sequence

import httpx
import numpy as np

from app.core.config import get_settings

logger = logging.getLogger("knowledge.embedder")

# 查询向量进程内缓存：同一句话在 TTL 内不重复请求上游
_QUERY_CACHE_TTL_SECONDS = 600.0
_QUERY_CACHE_MAX_ENTRIES = 256


class _QueryVectorCache:
    """LRU + TTL 的查询向量缓存（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                return None
            built_at, vector = item
            if time.monotonic() - built_at > _QUERY_CACHE_TTL_SECONDS:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return vector

    def put(self, key: str, vector: list[float]) -> None:
        with self._lock:
            self._entries[key] = (time.monotonic(), vector)
            self._entries.move_to_end(key)
            while len(self._entries) > _QUERY_CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_QUERY_CACHE = _QueryVectorCache()


def clear_query_vector_cache() -> None:
    _QUERY_CACHE.clear()


# ---------------------------------------------------------------------------
# 向量编解码
# ---------------------------------------------------------------------------


def pack_vector(vector: Sequence[float]) -> str:
    """float 列表 → base64(float32 小端)。"""
    return base64.b64encode(
        np.asarray(vector, dtype="<f4").tobytes()
    ).decode("ascii")


def unpack_vector(payload: str | None, expected_dim: int | None = None) -> np.ndarray | None:
    """base64(float32) → np.ndarray；格式不符或维度不符返回 None。

    维度校验是必要的：换了 embedding 模型（如 1536 → 3072）后，库里存量向量
    与新查询向量维度不一致，直接算余弦会抛异常或得到无意义结果。
    """
    if not payload:
        return None
    try:
        raw = base64.b64decode(payload)
    except (ValueError, TypeError):
        return None
    if len(raw) % 4 != 0 or len(raw) == 0:
        return None
    vector = np.frombuffer(raw, dtype="<f4")
    if expected_dim and vector.shape[0] != expected_dim:
        return None
    return vector


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度 → [-1, 1]；任一侧为零向量时返回 0。"""
    norm = float(np.linalg.norm(a)) * float(np.linalg.norm(b))
    if norm <= 0.0:
        return 0.0
    return float(np.dot(a, b) / norm)


# ---------------------------------------------------------------------------
# Embedding 客户端
# ---------------------------------------------------------------------------


class KnowledgeEmbedder:
    """知识库 embedding 生成器（同步、可降级）。"""

    # 单次请求文本上限，避免超长页把上游打挂
    MAX_CHARS = 8000
    # 每批条数
    BATCH_SIZE = 32

    def __init__(self) -> None:
        # 构造时读配置（而不是用模块级快照）：配置在运行期改过之后
        # reset_knowledge_embedder() 能真正生效
        settings = get_settings()
        self._model = settings.knowledge_embedding_model
        self._dim = settings.knowledge_embedding_dimensions
        # embedding 独立端点优先：聊天走 DeepSeek 而 embedding 走别家是常态
        base_url = settings.knowledge_embedding_base_url or settings.openai_base_url
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._api_key = (
            settings.knowledge_embedding_api_key or settings.openai_api_key or ""
        ).strip()
        self._timeout = settings.knowledge_embedding_timeout_seconds
        self._cooldown = settings.knowledge_embedding_cooldown_seconds
        self._failed_until = 0.0

        # 后端选择：local（本地模型） / remote（HTTP API）。
        #
        # 本地模式优先：一旦配了本地模型路径或模型名，就完全不走网络 ——
        # 内网部署和「不想烧 API 额度」的场景都靠它。本地模型不可用时
        # 抛错给上层（降级到 BM25），而不是偷偷改走远程 —— 那会让用户
        # 以为自己在用本地模型，实际在花钱调 API。
        self._local_model = (settings.knowledge_embedding_local_model or "").strip()
        self._local_backend = bool(self._local_model)
        # 是否已经从 provider 配置解析过端点。
        # 延迟到首次使用才解析：embedder 是单例，构造时机可能在启动早期
        # （还没有 db session），而且管理员改配置后我们希望下次使用就生效。
        self._provider_resolved = False
        self._resolve_source = "env"

    @property
    def dimensions(self) -> int:
        """当前配置的向量维度（存量的维度校验基准）。"""
        return self._dim

    @property
    def model(self) -> str:
        return self._model

    def _ensure_provider_endpoint(self) -> None:
        """首次使用时从 provider 配置解析端点，覆盖 env 基线。

        只在还没解析过、且不是本地模式时执行。解析失败静默保留 env 基线 ——
        配了 provider 但解析出错时，老部署的 env 配置仍应生效。
        """
        if self._provider_resolved or self._local_backend:
            return
        self._provider_resolved = True
        try:
            from app.db.session import create_db_session
            from app.services.llm_providers.resolve_models import resolve_embedding_endpoint

            with create_db_session() as db:
                endpoint = resolve_embedding_endpoint(db)
        except Exception:  # noqa: BLE001 —— 解析失败不该让检索崩
            logger.debug("解析 provider embedding 端点失败，沿用 env 配置", exc_info=True)
            return

        if endpoint is None:
            return
        self._resolve_source = endpoint.source
        if endpoint.source == "local":
            # 解析层认为该用本地模型（配置在运行期变了）
            self._local_model = endpoint.model
            self._local_backend = True
            if endpoint.dimensions:
                self._dim = endpoint.dimensions
            return
        if endpoint.api_key:
            self._base_url = endpoint.base_url or self._base_url
            self._api_key = endpoint.api_key
            self._model = endpoint.model
            if endpoint.dimensions:
                self._dim = endpoint.dimensions
            logger.info(
                "knowledge embedding 端点来自 %s：model=%s base=%s",
                endpoint.source, self._model, self._base_url,
            )

    def is_enabled(self) -> bool:
        """向量召回是否可用。

        本地模式只要配了模型名就算可用（不需要 API Key）；
        远程模式要求开关打开 + 有 Key。
        """
        settings = get_settings()
        if not settings.knowledge_vector_enabled:
            return False
        self._ensure_provider_endpoint()
        if self._local_backend:
            return True
        return bool(self._api_key)

    @property
    def backend(self) -> str:
        """当前后端：local / remote。"""
        return "local" if self._local_backend else "remote"

    @property
    def source(self) -> str:
        """配置来源：local / provider:<slug> / env。"""
        return "local" if self._local_backend else self._resolve_source

    def _cooling_down(self) -> bool:
        """上游刚失败过，冷却期内不再发请求（省掉每次检索的等待）。"""
        return time.monotonic() < self._failed_until

    def _mark_failure(self) -> None:
        self._failed_until = time.monotonic() + max(0.0, self._cooldown)

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(f"{self._model}:{text}".encode()).hexdigest()
        return digest

    def embed_query(self, text: str) -> list[float] | None:
        """查询向量（走进程内缓存）。"""
        text = (text or "").strip()
        if not text or not self.is_enabled() or self._cooling_down():
            return None

        key = self._cache_key(text)
        cached = _QUERY_CACHE.get(key)
        if cached is not None:
            return cached

        vectors = self._call_api([text])
        if not vectors or vectors[0] is None:
            return None
        _QUERY_CACHE.put(key, vectors[0])
        return vectors[0]

    def embed_text(self, text: str) -> list[float] | None:
        """页面正文向量（不缓存：正文只在上传/重建时算一次，缓存无收益）。"""
        text = (text or "").strip()
        if not text or not self.is_enabled() or self._cooling_down():
            return None
        vectors = self._call_api([text])
        if not vectors:
            return None
        return vectors[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float] | None]:
        """批量向量化，返回与输入等长的列表（失败位为 None）。"""
        if not texts:
            return []
        if not self.is_enabled() or self._cooling_down():
            return [None] * len(texts)

        results: list[list[float] | None] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            chunk = list(texts[start:start + self.BATCH_SIZE])
            results.extend(self._call_api(chunk))
            if self._cooling_down():
                # 上一批已经失败（上游不可用），剩余批次不再空等
                break
        # 上游返回条数异常时补齐，保证下标对齐
        while len(results) < len(texts):
            results.append(None)
        return results[: len(texts)]

    def _call_api(self, inputs: list[str]) -> list[list[float] | None]:
        """向量化入口：按后端分流到本地模型或远程 API。"""
        if self._local_backend:
            return self._call_local(inputs)
        if not self._api_key:
            return [None] * len(inputs)

        prepared = [(t or "")[: self.MAX_CHARS] for t in inputs]
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": prepared},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 —— 向量不可用不得让检索整体失败
            self._mark_failure()
            logger.warning(
                "knowledge embedding 调用失败（%.0fs 内跳过向量通道）: %s｜"
                "若上游不支持 /embeddings（如 DeepSeek），请单独配置 "
                "KNOWLEDGE_EMBEDDING_BASE_URL / KNOWLEDGE_EMBEDDING_API_KEY",
                self._cooldown,
                exc,
            )
            return [None] * len(inputs)

        items = data.get("data") or []
        if len(items) != len(prepared):
            logger.warning(
                "knowledge embedding 返回条数不符: 期望 %d 实际 %d", len(prepared), len(items)
            )
            return [None] * len(inputs)

        vectors: list[list[float] | None] = []
        for item in items:
            embedding = item.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != self._dim:
                logger.warning(
                    "knowledge embedding 维度不符: 期望 %d 实际 %s",
                    self._dim,
                    len(embedding) if isinstance(embedding, list) else "n/a",
                )
                vectors.append(None)
                continue
            vectors.append(embedding)
        return vectors

    def _call_local(self, inputs: list[str]) -> list[list[float] | None]:
        """用本地 sentence-transformers 模型向量化。

        失败时不设冷却（本地失败通常是配置/依赖问题，重试没意义但也不该
        让用户等 60 秒），直接把异常打成明确日志并返回 None 让上层降级。
        """
        from app.services.knowledge.local_embedder import (
            LocalEmbedderUnavailable,
            get_local_embedder,
        )

        prepared = [(t or "")[: self.MAX_CHARS] for t in inputs]
        try:
            embedder = get_local_embedder(
                self._local_model, expected_dims=self._dim or None
            )
            vectors = embedder.encode(prepared)
        except LocalEmbedderUnavailable as exc:
            logger.error("本地嵌入不可用：%s", exc)
            return [None] * len(inputs)
        except Exception as exc:  # noqa: BLE001
            logger.error("本地嵌入推理失败：%s", exc, exc_info=True)
            return [None] * len(inputs)

        out: list[list[float] | None] = []
        for vec in vectors:
            if not isinstance(vec, list) or len(vec) != self._dim:
                logger.warning(
                    "本地嵌入维度不符：期望 %d 实际 %s",
                    self._dim,
                    len(vec) if isinstance(vec, list) else "n/a",
                )
                out.append(None)
                continue
            out.append(vec)
        return out


def page_embedding_text(title: str, summary: str | None, content: str) -> str:
    """页面 → 待向量化文本。

    标题与摘要前置：它们是人工/编译提炼的要点，比正文开头更能代表页面主题。
    """
    parts = [title or ""]
    if summary:
        parts.append(summary)
    parts.append(content or "")
    return "\n".join(p for p in parts if p)


_embedder_singleton: KnowledgeEmbedder | None = None
_embedder_lock = threading.Lock()


def get_knowledge_embedder() -> KnowledgeEmbedder:
    global _embedder_singleton
    if _embedder_singleton is None:
        with _embedder_lock:
            if _embedder_singleton is None:
                _embedder_singleton = KnowledgeEmbedder()
    return _embedder_singleton


def reset_knowledge_embedder() -> None:
    """测试用：丢弃单例（配置变化后重新读取）。

    同时清空本地模型单例 —— 换了模型名却还复用旧模型，会让维度校验
    报出与配置无关的错，很难排查。
    """
    global _embedder_singleton
    with _embedder_lock:
        _embedder_singleton = None
    try:
        from app.services.knowledge.local_embedder import reset_local_embedders

        reset_local_embedders()
    except Exception:  # noqa: BLE001
        pass


def dumps_diagnostics() -> str:
    """诊断信息（排查「为什么没有向量召回」时用）。"""
    settings = get_settings()
    embedder = get_knowledge_embedder()
    return json.dumps(
        {
            "enabled": embedder.is_enabled(),
            "model": embedder.model,
            "dimensions": embedder.dimensions,
            "backend": embedder.backend,
            "source": embedder.source,
            "has_api_key": bool(embedder._api_key),  # noqa: SLF001 —— 诊断用途
            "base_url": embedder._base_url,  # noqa: SLF001 —— 诊断用途
            "dedicated_endpoint": bool(settings.knowledge_embedding_base_url),
            "cooling_down": embedder._cooling_down(),  # noqa: SLF001 —— 诊断用途
        },
        ensure_ascii=False,
    )
