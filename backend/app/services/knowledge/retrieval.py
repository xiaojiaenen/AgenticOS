"""
知识库检索服务（LlamaIndex 全量接管版）

检索机制全部由 LlamaIndex 组件承担，旧手写实现（MySQL FULLTEXT /
PG trgm / Python BM25 三路 + 手写 RRF）已整体退役：

- BM25：``llama_index.retrievers.bm25.BM25Retriever``（bm25s 引擎）。
  页级语料 jieba 预分词（空格连接喂给 bm25s 的分词器）；标题/摘要加权
  通过语料文本重复计入，与旧实现的加权口径等价。
- 向量：``KBVectorRetriever``（LlamaIndex ``BaseRetriever``）—— 段级
  embedding 余弦 + 页级 max 聚合；库里无切片时自动退回页级向量。
- 融合：RRF k=60（与旧实现同一论文参数），直接复用两路检索的排名，
  不引入 LLM 查询改写、不重复检索。
- 重排：启发式四信号（``rerank.score_result``）+ FlashRank cross-encoder
  精排（``rerank.rerank_scores``）。

**score 的语义不变**：对外暴露的 ``SearchResult.score`` 是 **0~1 的相对
相关度**，不是 BM25 原始分、也不是 RRF 排名分。计算分两步：

    1) 融合（决定候选集与粗分）
       bm25_norm = bm25_raw / 本次查询最高 BM25 分          （通道内归一到 0~1）
       vec_norm  = max(0, cosine(查询, 最佳段))               （绝对相似度）
       base      = 0.6 * bm25_norm + 0.4 * vec_norm           （向量不可用时退化为 bm25_norm）

    2) 重排（决定最终排序，见 ``rerank.py``）
       score = 0.55*base + 0.25*覆盖率 + 0.12*邻近度 + 0.08*通道一致性

这样 ``score_threshold`` 才是可解释的阈值：0.5 表示"至少命中一半相关度"。

安全边界不变：显式授权（kb_access_control / Casbin）与 visibility/scope
双重可见性过滤在检索器构建**之前**完成 —— 检索器只看到已过滤的 kb_ids。
"""

import json
import logging
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from typing import Optional

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.retrievers.bm25 import BM25Retriever
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import KBChunkModel, KBWikiPageModel, KnowledgeBaseModel, UserModel
from app.services.knowledge import rerank as rerank_mod
from app.services.knowledge.acl import explicit_role, load_grants, role_allows
from app.services.knowledge.embedder import (
    cosine_similarity,
    get_knowledge_embedder,
    unpack_vector,
)
from app.services.knowledge.tokenizer import tokenize

logger = logging.getLogger(__name__)
_settings = get_settings()

# ----------------------------------------------------------------------
# 语料缓存（LlamaIndex 检索器实例缓存）
# ----------------------------------------------------------------------
#
# BM25Retriever 构建时要把整库语料分词建索引 —— 这是检索 P95 的主项，
# 必须进程内缓存。缓存对象从旧的「分词快照」换成「构建好的检索器实例」：
# 语义不变（TTL / LRU / 超大语料不缓存），失效入口也不变
# （ingest_pipeline 在 commit 成功后调用 invalidate_knowledge_cache）。

_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_DOCS = 1000
_CACHE_MAX_ENTRIES = 8  # 保留最近若干个 (kb_ids, page_type) 组合的检索器

_QUERY_EMBED_CACHE_SIZE = 64  # 查询向量去重缓存（同查询只 embed 一次）

# ----------------------------------------------------------------------
# 检索质量在线指标（优化方案 2.4 / 3.5：命中率、无结果率可观测）
# ----------------------------------------------------------------------
#
# 进程内滑动窗口采样（默认保留最近 2000 次），不落库 —— 这是运营看板的
# 「趋势口径」而不是审计事实；要看跨进程/跨重启的精确值再接 OTel/DB。
# 采样对象：经权限过滤后的真实检索（_get_visible_knowledge_bases 之后）。

_RETRIEVAL_METRICS_MAX_SAMPLES = 2000
_retrieval_metrics_lock = threading.Lock()
_retrieval_metrics: deque = deque(maxlen=_RETRIEVAL_METRICS_MAX_SAMPLES)


def record_search_metrics(
    *,
    query: str,
    result_count: int,
    latency_ms: int,
    kb_ids: list[int],
    matched_channels: list[str],
    stages_ms: dict[str, int] | None = None,
    cache_hit: bool | None = None,
) -> None:
    """每次对外检索结束时记录一条采样（search() 末尾调用）。"""
    sample = {
        "ts": time.time(),
        "query_preview": (query or "")[:60],
        "result_count": result_count,
        "latency_ms": latency_ms,
        "kb_ids": list(kb_ids)[:10],
        "channels": matched_channels,
        "stages_ms": dict(stages_ms or {}),
        "cache_hit": cache_hit,
    }
    with _retrieval_metrics_lock:
        _retrieval_metrics.appendleft(sample)


def get_retrieval_metrics() -> dict:
    """检索质量汇总（后台看板 / eval 调参用）。

    - hit_rate：有结果的查询占比（相对最近窗口）；
    - empty_rate：无结果率（调参的首要信号）；
    - p50/p95 延迟与通道分布（rerank 前后对比可由 channels 里 bm25/vector
      占比粗读 —— 两通道都命中的查询融合质量更好）。
    """
    with _retrieval_metrics_lock:
        samples = list(_retrieval_metrics)
    if not samples:
        return {"window": 0, "hit_rate": None, "empty_rate": None, "latency_ms_p50": None,
                "latency_ms_p95": None, "channels": {}, "no_result_queries": []}
    total = len(samples)
    hits = [s for s in samples if s["result_count"] > 0]
    latencies = sorted(s["latency_ms"] for s in samples if s["latency_ms"] is not None)

    def _pct(values: list[int], p: float) -> int | None:
        if not values:
            return None
        idx = min(len(values) - 1, max(0, int(round(p * (len(values) - 1)))))
        return values[idx]

    channels: dict[str, int] = {}
    for s in samples:
        for c in s["channels"]:
            channels[c] = channels.get(c, 0) + 1
    no_result = [
        {"query": s["query_preview"], "ts": s["ts"], "kb_ids": s["kb_ids"]}
        for s in samples[:50] if s["result_count"] == 0
    ]
    def _stage_pct(name: str, p: float) -> int | None:
        values = sorted(
            s["stages_ms"][name] for s in samples
            if name in (s.get("stages_ms") or {})
        )
        return _pct(values, p)

    cached = [s for s in samples if s.get("cache_hit") is True]
    return {
        "window": total,
        "hit_rate": round(len(hits) / total, 3),
        "empty_rate": round((total - len(hits)) / total, 3),
        "latency_ms_p50": _pct(latencies, 0.50),
        "latency_ms_p95": _pct(latencies, 0.95),
        "stages_ms_p50": {
            name: _stage_pct(name, 0.50)
            for name in ("bm25", "vector", "rerank")
            if _stage_pct(name, 0.50) is not None
        },
        "stages_ms_p95": {
            name: _stage_pct(name, 0.95)
            for name in ("bm25", "vector", "rerank")
            if _stage_pct(name, 0.95) is not None
        },
        "bm25_cache_hit_rate": round(len(cached) / total, 3) if total else None,
        "channels": channels,
        "no_result_queries": no_result,
    }


class _RetrieverEntry:
    """一份缓存条目：构建好的 BM25 检索器 + 语料页数。"""

    __slots__ = ("built_at", "retriever", "doc_count")

    def __init__(self, built_at: float, retriever: BM25Retriever, doc_count: int) -> None:
        self.built_at = built_at
        self.retriever = retriever
        self.doc_count = doc_count

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.built_at) > _CACHE_TTL_SECONDS


class _RetrieverCache:
    """进程内 LRU + TTL 缓存，线程安全。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, _RetrieverEntry] = OrderedDict()

    @staticmethod
    def make_key(knowledge_base_ids: list[int], page_type: Optional[str]) -> tuple:
        return (tuple(sorted(knowledge_base_ids)), page_type)

    def get(self, key: tuple) -> _RetrieverEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expired:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry

    def put(self, key: tuple, entry: _RetrieverEntry) -> None:
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > _CACHE_MAX_ENTRIES:
                self._entries.popitem(last=False)

    def invalidate_all(self) -> None:
        with self._lock:
            self._entries.clear()

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            return {
                "entries": len(self._entries),
                "docs": sum(e.doc_count for e in self._entries.values()),
                "fresh": sum(1 for e in self._entries.values() if not (now - e.built_at > _CACHE_TTL_SECONDS)),
            }


_RETRIEVER_CACHE = _RetrieverCache()


def invalidate_knowledge_cache() -> None:
    """清空知识库语料缓存（LlamaIndex 检索器实例）。

    任何写入 kb_wiki_pages 的路径在 **commit 成功之后** 调用，
    否则失败回滚的写入会把旧语料误清（清空只是性能损失，但没必要），
    更糟的是没清导致读脏数据。
    """
    _RETRIEVER_CACHE.invalidate_all()
    logger.info("Knowledge corpus cache invalidated")


def can_view_knowledge_base(
    kb: KnowledgeBaseModel,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> bool:
    """知识库可见性判定。

    - admin：全部可见
    - visibility=private：仅 owner/admin
    - visibility=restricted：仅 owner/admin（其他用户须走显式 ACL 授权，
      由 require_kb_access 的 explicit_role 判定，这里作为兜底拒绝）
    - scope=personal：仅 owner/admin
    - scope=org + visibility=public：可见

    team 作用域已随组织模型下线（字段删除、判定分支移除）；存量库若仍有
    scope='team' 的历史值，按 org 处理（公开可见），不会误锁住已有数据。
    """
    if is_admin:
        return True
    if kb.visibility in ("private", "restricted"):
        return user_id is not None and kb.owner_id == user_id
    if kb.scope == "personal":
        return user_id is not None and kb.owner_id == user_id
    # org（含历史 team 值）
    return True


@dataclass
class SearchResult:
    """检索结果"""
    page_id: int
    title: str
    content: str
    page_type: str
    score: float
    sources: list[str] = field(default_factory=list)
    authority_level: str = "L1"
    conflicts: list[dict] = field(default_factory=list)
    related_pages: list[int] = field(default_factory=list)
    # 命中片段：取页内与查询最相关的一段（长文档的要点往往不在开头）
    snippet: str = ""
    # 该页被哪些通道命中：["bm25", "vector"]
    matched_by: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------
# LlamaIndex 检索器
# ----------------------------------------------------------------------


class KBVectorRetriever(BaseRetriever):
    """段级向量检索（LlamaIndex ``BaseRetriever``）。

    为什么按段而不是按页：页级向量把整页压成一个点，长页（编译出的
    source_summary / synthesis 常几千字）的主题被平均，问其中某一节往往
    召不回本页。段级取 ``max`` 聚合，长页里真正相关的那一段不会被稀释。

    兜底：库里一条切片都没有（存量库尚未重建索引）时，自动退回页级
    ``kb_wiki_pages.embedding``，语义通道不会因此整条消失。

    返回的 NodeWithScore：``node.id_`` 是 page_id 字符串，
    ``node.text`` 是该页最佳段正文（直接当命中片段用），
    ``score`` 是余弦相似度。
    """

    def __init__(self, db: Session, knowledge_base_ids: list[int], page_type: Optional[str]):
        super().__init__()
        self.db = db
        self.knowledge_base_ids = knowledge_base_ids
        self.page_type = page_type
        # 查询向量去重：同一实例（fusion 会重复调用 _retrieve）只 embed 一次
        self._embed_cache: OrderedDict[str, list[float] | None] = OrderedDict()

    def _query_vector(self, query: str) -> list[float] | None:
        cached = self._embed_cache.get(query)
        if cached is not None:
            self._embed_cache.move_to_end(query)
            return cached
        vector = None
        try:
            embedder = get_knowledge_embedder()
            if embedder.is_enabled():
                vector = embedder.embed_query(query)
        except Exception as e:  # noqa: BLE001 —— embedding 服务故障退化为纯 BM25
            logger.warning("向量通道 embed 查询失败，退化为纯 BM25: %s", e)
            vector = None
        self._embed_cache[query] = vector
        while len(self._embed_cache) > _QUERY_EMBED_CACHE_SIZE:
            self._embed_cache.popitem(last=False)
        return vector

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query_vector = self._query_vector(query_bundle.query_str or "")
        if not query_vector:
            return []
        import numpy as np

        query_np = np.asarray(query_vector, dtype=np.float32)

        min_similarity = _settings.knowledge_vector_min_similarity
        dimensions = get_knowledge_embedder().dimensions

        # pgvector 加速路径（数据库评估 阶段 2）：PG + vector 扩展 + vector 列
        # 三者齐备时走库内 <=> 排序（HNSW 索引生效）；任何条件不满足自动
        # 降级到「拉全量 + 应用侧余弦」的旧路径，行为完全一致。
        from app.services.knowledge.pgvector import pgvector_available, similarity_search_chunks

        if pgvector_available(self.db):
            try:
                fast = similarity_search_chunks(
                    self.db,
                    query_vector=query_vector,
                    knowledge_base_ids=self.knowledge_base_ids,
                    top_k=_settings.knowledge_vector_top_k,
                    min_similarity=min_similarity,
                    page_type=self.page_type,
                )
                if fast:
                    return [
                        NodeWithScore(
                            node=TextNode(id_=str(pid), text=content, metadata={"page_id": pid}),
                            score=sim,
                        )
                        for pid, sim, content in fast
                    ]
                # 库内检索无命中：可能切片全无 → 走页级兜底
                return self._page_level_fallback(query_np)
            except Exception as e:  # noqa: BLE001 —— SQL 异常降级应用侧余弦
                logger.warning("pgvector 检索失败，降级应用侧余弦: %s", e)
                from app.services.knowledge.pgvector import reset_probe_cache

                reset_probe_cache()

        chunk_stmt = (
            select(KBChunkModel.page_id, KBChunkModel.content, KBChunkModel.embedding)
            .join(KBWikiPageModel, KBWikiPageModel.id == KBChunkModel.page_id)
            .where(
                and_(
                    KBChunkModel.knowledge_base_id.in_(self.knowledge_base_ids),
                    KBChunkModel.embedding.isnot(None),
                    KBWikiPageModel.is_active.is_(True),
                )
            )
        )
        if self.page_type:
            chunk_stmt = chunk_stmt.where(KBWikiPageModel.page_type == self.page_type)

        scanned = 0
        best_by_page: dict[int, tuple[float, str]] = {}
        for page_id, content, payload in self.db.execute(chunk_stmt).all():
            page_vector = unpack_vector(payload, dimensions)
            if page_vector is None:
                # 维度不符（换过模型）或格式损坏：跳过而不是算出错的值
                continue
            scanned += 1
            similarity = cosine_similarity(query_np, page_vector)
            if similarity < min_similarity:
                continue
            key = int(page_id)
            current = best_by_page.get(key)
            if current is None or similarity > current[0]:
                best_by_page[key] = (similarity, content)

        if scanned == 0:
            # 没有任何可用切片 → 页级兜底（存量库/切片失败）
            return self._page_level_fallback(query_np)

        hits = sorted(best_by_page.items(), key=lambda item: item[1][0], reverse=True)
        hits = hits[: _settings.knowledge_vector_top_k]
        return [
            NodeWithScore(
                node=TextNode(id_=str(page_id), text=text, metadata={"page_id": page_id}),
                score=float(score),
            )
            for page_id, (score, text) in hits
        ]

    def _page_level_fallback(self, query_np) -> list[NodeWithScore]:
        """页级向量兜底路径（无切片时）。"""
        conditions = [
            KBWikiPageModel.knowledge_base_id.in_(self.knowledge_base_ids),
            KBWikiPageModel.is_active.is_(True),
            KBWikiPageModel.embedding.isnot(None),
        ]
        if self.page_type:
            conditions.append(KBWikiPageModel.page_type == self.page_type)

        stmt = select(KBWikiPageModel.id, KBWikiPageModel.embedding).where(and_(*conditions))
        rows = self.db.execute(stmt).all()

        min_similarity = _settings.knowledge_vector_min_similarity
        dimensions = get_knowledge_embedder().dimensions
        hits: list[tuple[int, float]] = []
        for page_id, payload in rows:
            page_vector = unpack_vector(payload, dimensions)
            if page_vector is None:
                continue
            similarity = cosine_similarity(query_np, page_vector)
            if similarity < min_similarity:
                continue
            hits.append((int(page_id), similarity))

        hits.sort(key=lambda item: item[1], reverse=True)
        hits = hits[: _settings.knowledge_vector_top_k]
        return [
            NodeWithScore(
                node=TextNode(id_=str(page_id), text="", metadata={"page_id": page_id}),
                score=float(score),
            )
            for page_id, score in hits
        ]


class KBBM25Retriever(BaseRetriever):
    """BM25 检索（LlamaIndex ``BM25Retriever``/bm25s 引擎的薄包装）。

    语料在构建期完成 jieba 预分词（空格连接喂给 bm25s 的正则分词器），
    查询侧同样预分词。``_tokenize`` 从所属的 ``KnowledgeRetrieval`` 实例
    注入，保证查询侧分词可替换（召回对比工具依赖这一点）。
    """

    def __init__(self, bm25: BM25Retriever, retrieval: "KnowledgeRetrieval"):
        super().__init__()
        self._bm25 = bm25
        self._retrieval = retrieval

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        query = query_bundle.query_str or ""
        tokens = self._retrieval._tokenize(query)  # noqa: SLF001 —— 同包内部协作
        if not tokens:
            return []
        nodes = self._bm25.retrieve(QueryBundle(query_str=" ".join(tokens)))
        # bm25s 对全库排序：零分（没有任何查询词命中）的文档也会进 top-k，
        # 必须过滤，否则不相干页面会混进候选集（旧实现 score > 0 等价语义）
        return [n for n in nodes if (n.score or 0.0) > 0.0]


# ----------------------------------------------------------------------
# 检索服务
# ----------------------------------------------------------------------


class KnowledgeRetrieval:
    """知识库检索服务"""

    # 权威性权重：只用于同等相关度时的排序 tie-break，不参与 score 计算。
    # 混进 score 会让「权威」污染「相关」，阈值就再也说不清是什么意思了。
    AUTHORITY_WEIGHTS = {
        "L3": 2.0,
        "L2": 1.5,
        "L1": 1.0,
        "L0": 0.8,
    }

    # BM25 通道单次检索返回的候选上限（进入融合前截断）
    BM25_TOP_K = 50

    # 双路融合时两通道的权重（相关度加权，非 RRF）
    WEIGHT_BM25 = 0.6
    WEIGHT_VECTOR = 0.4

    # 命中片段的长度上限
    SNIPPET_MAX_CHARS = 400

    def __init__(self, db: Session):
        self.db = db

    def search(
        self,
        query: str,
        knowledge_base_ids: Optional[list[int]] = None,
        user_id: Optional[int] = None,
        page_type: Optional[str] = None,
        max_results: int = 10,
        is_admin: bool = False,
        score_threshold: float | None = None,
    ) -> list[SearchResult]:
        """执行知识库检索

        Args:
            query: 查询文本
            knowledge_base_ids: 指定知识库 ID 列表（None 表示搜索所有有权限的知识库）
            user_id: 用户 ID（用于权限过滤）
            page_type: 过滤页面类型
            max_results: 最大结果数
            is_admin: 是否管理员（private=owner/admin）
            score_threshold: 相对相关度阈值（0~1），低于视为未命中

        Returns:
            list[SearchResult]: 检索结果列表，score 为 0~1 的相对相关度
        """
        query = (query or "").strip()
        if not query:
            return []

        _t0 = time.monotonic()
        _stages: dict[str, int] = {}
        logger.info("Searching knowledge base: query='%s...'", query[:50])

        # 获取可见的知识库
        visible_kb_ids = self._get_visible_knowledge_bases(
            knowledge_base_ids, user_id, is_admin=is_admin,
        )
        if not visible_kb_ids:
            return []

        # 两路检索：BM25（字面，bm25s）+ 向量（语义，段级）—— 均为 LlamaIndex 检索器
        _t1 = time.monotonic()
        bm25_hits = self._bm25_search(query, visible_kb_ids, page_type)
        _t2 = time.monotonic()
        _stages["bm25"] = int((_t2 - _t1) * 1000)
        vector_hits, chunk_snippets = self._vector_search(query, visible_kb_ids, page_type)
        _t3 = time.monotonic()
        _stages["vector"] = int((_t3 - _t2) * 1000)

        if not bm25_hits and not vector_hits:
            return []

        # 候选集：RRF(k=60) 决定「取哪些页」，两路都命中的页面天然靠前。
        # 直接复用上面两路检索的排名结果 —— 旧实现在这里又跑一遍 BM25+向量，
        # 单次 search 实际做了 4 次检索（冷启动重复建索引，P95 主因）。
        candidate_ids = self._fuse_candidates(
            query, visible_kb_ids, page_type, max_results * 3,
            bm25_hits=bm25_hits, vector_hits=vector_hits,
        )

        # 粗排依据：归一化相关度（RRF 只负责选候选，不参与对外 score）
        relevance = self._blend_relevance(bm25_hits, vector_hits)
        matched_by = self._matched_channels(bm25_hits, vector_hits)

        query_terms = self._tokenize(query)
        results = self._load_page_details(
            candidate_ids,
            relevance,
            matched_by,
            query_terms=query_terms,
            chunk_snippets=chunk_snippets,
        )

        # 重排：把「通道内相对强弱」换成「查询与命中片段的贴合度」。
        # 第一级是启发式四信号（零依赖、零抖动）；第二级是 FlashRank
        # cross-encoder 精排 top-K（战线 B4，模型不可用自动整段降级）。
        for item in results:
            item.score = rerank_mod.score_result(
                base_score=item.score,
                query_terms=query_terms,
                # 标题参与词面信号：标题命中是最强的相关性证据之一
                text=f"{item.title}\n{item.snippet or item.content[: self.SNIPPET_MAX_CHARS]}",
                channels=item.matched_by,
            )
        self._apply_flashrank_rerank(query, results)
        _stages["rerank"] = int((time.monotonic() - _t3) * 1000)

        # 相关度优先，同分时权威性高的靠前
        results.sort(
            key=lambda r: (r.score, self.AUTHORITY_WEIGHTS.get(r.authority_level, 1.0)),
            reverse=True,
        )

        # 相似度阈值：低于阈值的结果视为未命中（召回测试用它看参数影响）
        if score_threshold is not None and score_threshold > 0:
            results = [r for r in results if r.score >= score_threshold]

        final = results[:max_results]
        record_search_metrics(
            query=query,
            result_count=len(final),
            latency_ms=int((time.monotonic() - _t0) * 1000),
            kb_ids=visible_kb_ids,
            matched_channels=sorted({c for r in final for c in r.matched_by}),
            stages_ms=_stages,
            cache_hit=_RETRIEVER_CACHE.get(_RetrieverCache.make_key(visible_kb_ids, page_type)) is not None,
        )
        return final

    def _apply_flashrank_rerank(self, query: str, results: list[SearchResult]) -> None:
        """FlashRank cross-encoder 精排 top-K（战线 B4）。

        - ``KB_RERANK_BACKEND=heuristic`` 跳过（显式关闭）；
        - 模型不可用/推理失败 → rerank_scores 返回 None → 保持启发式结果；
        - 融合：``final = w*flashrank + (1-w)*heuristic``（w 可配），只对
          按启发式分排序后的头部 top-K 精排，其余保持启发式分 —— 兼顾
          精度与 cross-encoder 的 p95 抖动。
        """
        if not results:
            return
        try:
            settings = get_settings()
        except Exception:  # noqa: BLE001 —— 测试环境缺配置时按默认 auto
            settings = None
        backend = (getattr(settings, "knowledge_rerank_backend", "auto") or "auto").lower()
        if backend == "heuristic":
            return

        # 启发式分高的先送精排（top-K 截断）
        ordered = sorted(results, key=lambda r: r.score, reverse=True)
        top_k = max(1, int(getattr(settings, "knowledge_rerank_top_k", 20) or 20))
        head = ordered[:top_k]
        texts = [f"{r.title}\n{r.snippet or r.content[: self.SNIPPET_MAX_CHARS]}" for r in head]
        scores = rerank_mod.rerank_scores(query, texts)
        if scores is None:
            return  # 降级：启发式结果保持原样

        weight = float(getattr(settings, "knowledge_rerank_flashrank_weight", 0.65) or 0.65)
        for item, fr_score in zip(head, scores):
            item.score = rerank_mod.blend_score(flashrank=fr_score, heuristic=item.score, weight=weight)
        logger.debug(
            "flashrank rerank applied: query=%r head=%d/%d weight=%.2f",
            query[:50], len(head), len(results), weight,
        )

    def _get_visible_knowledge_bases(
        self,
        knowledge_base_ids: Optional[list[int]],
        user_id: Optional[int],
        is_admin: bool = False,
    ) -> list[int]:
        """获取用户可见的知识库 ID 列表。

        两个来源取并集：
        1. **显式授权**（``kb_access_control`` 成员表 / Casbin 直接策略）——
           被分享过的人，即使库是 private 也能读到；
        2. **可见性兜底**（``can_view_knowledge_base``）—— public/org 对所有人可见。

        只查其中一个都会出问题：只查 1 会让存量公开库全部搜不到；
        只查 2 会让「我已经被加进成员列表」的人搜不到自己的库。
        """
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.is_active.is_(True)
        )
        if knowledge_base_ids:
            stmt = stmt.where(KnowledgeBaseModel.id.in_(knowledge_base_ids))

        rows = self.db.execute(stmt).scalars().all()
        if not rows:
            return []

        user = self.db.get(UserModel, user_id) if user_id else None
        grants = load_grants(self.db, [kb.id for kb in rows]) if user else {}

        visible: list[int] = []
        for kb in rows:
            if user is not None:
                role = explicit_role(user, kb, grants.get(kb.id, []))
                if role_allows(role, "read"):
                    visible.append(kb.id)
                    continue
            if can_view_knowledge_base(kb, user_id=user_id, is_admin=is_admin):
                visible.append(kb.id)
        return visible

    # ----------------------------------------------------------------------
    # BM25 通道（LlamaIndex BM25Retriever / bm25s）
    # ----------------------------------------------------------------------

    def _build_bm25_retriever(
        self,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> tuple[BM25Retriever, int] | None:
        """加载语料并构建 LlamaIndex BM25Retriever（bm25s 引擎）。

        语料文本 = jieba 预分词（空格连接），标题/摘要按旧口径重复计入
        （content ×1 + title ×1 + summary ×2），等价于给标题/摘要更高权重。
        文档数为 0 返回 None；超过 ``_CACHE_MAX_DOCS`` 不入缓存（每次重算）。
        """
        conditions = [
            KBWikiPageModel.knowledge_base_id.in_(knowledge_base_ids),
            KBWikiPageModel.is_active.is_(True),
        ]
        if page_type:
            conditions.append(KBWikiPageModel.page_type == page_type)

        stmt = select(KBWikiPageModel).where(and_(*conditions))
        pages = self.db.execute(stmt).scalars().all()
        if not pages:
            return None

        nodes = []
        for page in pages:
            summary_text = (getattr(page, "summary", None) or "")
            corpus_text = page.content + " " + page.title + (
                " " + summary_text * 2 if summary_text else ""
            )
            tokens = " ".join(tokenize(corpus_text))
            nodes.append(
                TextNode(
                    id_=str(page.id),
                    text=tokens,
                    metadata={"page_id": int(page.id)},
                )
            )

        retriever = BM25Retriever(
            nodes=nodes,
            # bm25s 要求 k ≤ 语料规模（k of N is larger than the number of available scores）
            similarity_top_k=min(self.BM25_TOP_K, len(nodes)),
            # 语料已是 jieba 词级 token，词干化没有意义还拖慢构建
            skip_stemming=True,
        )
        return retriever, len(nodes)

    def _bm25_search(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> list[tuple[int, float]]:
        """BM25 全文检索（LlamaIndex BM25Retriever，bm25s 引擎）。

        语料级检索器实例走进程内缓存（TTL 300s / LRU / 超限不缓存），
        同一批知识库在 TTL 内的重复检索不再重复全库分词建索引。
        返回 ``[(page_id, bm25_raw_score)]``（未归一，归一在 _blend_relevance）。
        """
        if not knowledge_base_ids:
            return []

        cache_key = _RetrieverCache.make_key(knowledge_base_ids, page_type)
        entry = _RETRIEVER_CACHE.get(cache_key)

        if entry is None:
            built = self._build_bm25_retriever(knowledge_base_ids, page_type)
            if built is None:
                return []
            retriever, doc_count = built
            if doc_count <= _CACHE_MAX_DOCS:
                entry = _RetrieverEntry(time.monotonic(), retriever, doc_count)
                _RETRIEVER_CACHE.put(cache_key, entry)
            else:
                logger.info(
                    "Knowledge corpus too large to cache (%d docs > %d), skipping cache",
                    doc_count, _CACHE_MAX_DOCS,
                )
                entry = _RetrieverEntry(time.monotonic(), retriever, doc_count)

        channel = KBBM25Retriever(entry.retriever, self)
        nodes = channel.retrieve(QueryBundle(query_str=query))
        return [(int(n.metadata["page_id"]), float(n.score or 0.0)) for n in nodes]

    def _vector_search(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> tuple[list[tuple[int, float]], dict[int, str]]:
        """向量语义检索（LlamaIndex KBVectorRetriever，段级余弦 + 页级 max）。

        返回 ``(hits, best_chunk_text)``：
        - ``hits``：``[(page_id, 该页最佳段的余弦相似度)]``，已按相似度降序截断；
        - ``best_chunk_text``：``{page_id: 最佳段正文}``，直接当作命中片段用，
          不再靠启发式猜「页内哪段相关」。
        """
        channel = KBVectorRetriever(self.db, knowledge_base_ids, page_type)
        nodes = channel.retrieve(QueryBundle(query_str=query))
        if not nodes:
            return [], {}
        hits = [(int(n.metadata["page_id"]), float(n.score or 0.0)) for n in nodes]
        snippets = {pid: (n.node.get_content() or "") for pid, n in zip(hits, nodes)}
        return hits, snippets

    def _fuse_candidates(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
        top_k: int,
        *,
        bm25_hits: Optional[list[tuple[int, float]]] = None,
        vector_hits: Optional[list[tuple[int, float]]] = None,
    ) -> list[int]:
        """RRF(k=60) 选候选页。

        只负责「取哪些页」——RRF 排名分不参与对外 score（见模块 docstring）。
        某一通道无候选时，融合退化为单通道排序。

        优先复用 ``search()`` 已经拿到的两路排名（``bm25_hits`` / ``vector_hits``），
        避免重复检索。独立调用（如回归测试）未传时才自行检索，保持向后兼容。
        """
        k = 60.0
        if bm25_hits is None:
            bm25_hits = self._bm25_search(query, knowledge_base_ids, page_type)
        if vector_hits is None:
            vector_hits, _ = self._vector_search(query, knowledge_base_ids, page_type)

        fused_scores: dict[int, float] = {}
        for hits in (bm25_hits, vector_hits):
            for rank, (page_id, _score) in enumerate(hits):
                fused_scores[page_id] = fused_scores.get(page_id, 0.0) + 1.0 / (rank + k)

        ordered = sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
        return [page_id for page_id, _ in ordered[:top_k]]

    def _tokenize(self, text: str) -> list[str]:
        """分词入口：委托 tokenizer 模块（jieba 词级分词）。

        旧的 bigram 逻辑保留在 ``tokenizer.bigram_tokenize``，
        供新旧召回对比使用（_search 可注入替换）。
        """
        return tokenize(text)

    def _blend_relevance(
        self,
        bm25_hits: list[tuple[int, float]],
        vector_hits: list[tuple[int, float]],
    ) -> dict[int, float]:
        """把两路分数折算成 0~1 的相对相关度。

        - BM25 是相对分（无上界），按本次查询的最高分归一到 0~1；
        - 余弦本身就在 [-1, 1]，负相关截断为 0；
        - 向量通道整体不可用（无 Key / 未建索引）时，权重全部给 BM25，
          避免把所有存量页面按 0.6 上限压低。
        """
        relevance: dict[int, float] = {}
        has_vector = bool(vector_hits)

        if bm25_hits:
            top = max(score for _, score in bm25_hits) or 1.0
            weight = self.WEIGHT_BM25 if has_vector else 1.0
            for page_id, score in bm25_hits:
                relevance[page_id] = weight * max(0.0, score / top)

        if vector_hits:
            weight = self.WEIGHT_VECTOR if bm25_hits else 1.0
            for page_id, similarity in vector_hits:
                relevance[page_id] = relevance.get(page_id, 0.0) + weight * max(0.0, similarity)

        # 浮点累加后可能略微超过 1，截断保证 score_threshold 的语义稳定
        return {page_id: min(1.0, value) for page_id, value in relevance.items()}

    def _matched_channels(
        self,
        bm25_hits: list[tuple[int, float]],
        vector_hits: list[tuple[int, float]],
    ) -> dict[int, list[str]]:
        """记录每个页面被哪些通道命中（排查「为什么这条排前面」用）。"""
        channels: dict[int, list[str]] = {}
        if bm25_hits:
            for page_id, _ in bm25_hits:
                channels.setdefault(page_id, []).append("bm25")
        if vector_hits:
            for page_id, _ in vector_hits:
                channels.setdefault(page_id, []).append("vector")
        return channels

    def _best_snippet(self, content: str, query_terms: list[str]) -> str:
        """挑页内与查询最相关的一段作为命中片段。

        长文档的要点常在中段，直接 ``content[:500]`` 会给出与问题无关的开头。
        这里按空行/标题切段，用查询词命中数选段；全部不命中时退回开头。
        """
        text = (content or "").strip()
        if not text:
            return ""
        if not query_terms:
            return text[: self.SNIPPET_MAX_CHARS]

        terms = set(query_terms)
        segments = [seg.strip() for seg in re.split(r"\n\s*\n|\n(?=#{1,6}\s)", text) if seg.strip()]
        if not segments:
            segments = [text]

        best_segment = segments[0]
        best_score = -1
        for segment in segments:
            score = len(terms & set(tokenize(segment)))
            if score > best_score:
                best_score = score
                best_segment = segment

        if len(best_segment) <= self.SNIPPET_MAX_CHARS:
            return best_segment
        return best_segment[: self.SNIPPET_MAX_CHARS] + "..."

    def _best_chunk_snippets(
        self,
        page_ids: list[int],
        query_terms: list[str],
    ) -> dict[int, str]:
        """无向量时按词面命中挑每页最佳的段（供命中片段使用）。

        向量通道会直接给出「语义最像」的那一段；纯 BM25 场景（未配 embedding）
        没有这个信息，但段级切片依然在库里 —— 从里面按查询词命中数挑一段，
        比按空白行临时切分再猜准得多，尤其是页内有多个小标题时。
        """
        if not page_ids or not query_terms:
            return {}

        rows = self.db.execute(
            select(KBChunkModel.page_id, KBChunkModel.content).where(
                KBChunkModel.page_id.in_(page_ids)
            )
        ).all()

        terms = {t for t in query_terms if t}
        best: dict[int, tuple[int, str]] = {}
        for page_id, content in rows:
            hits = len(terms & set(tokenize(content)))
            if hits == 0:
                continue
            key = int(page_id)
            current = best.get(key)
            if current is None or hits > current[0]:
                best[key] = (hits, content)
        return {page_id: text for page_id, (_hits, text) in best.items()}

    def _load_page_details(
        self,
        page_ids: list[int],
        relevance: dict[int, float],
        matched_channels: dict[int, list[str]] | None = None,
        query_terms: list[str] | None = None,
        chunk_snippets: dict[int, str] | None = None,
    ) -> list[SearchResult]:
        """加载页面详细信息，并写入相关度、命中通道与命中片段。

        片段优先取「向量通道选中的最佳段」（真实命中的那一段），
        没有切片时退回 ``_best_snippet`` 的词面启发式。
        """
        if not page_ids:
            return []

        stmt = select(KBWikiPageModel).where(KBWikiPageModel.id.in_(page_ids))
        pages = {p.id: p for p in self.db.execute(stmt).scalars().all()}
        snippet_map = dict(chunk_snippets or {})

        # 向量通道没覆盖到的页（纯 BM25 场景），用切片里的词面最佳段补上
        missing = [pid for pid in page_ids if pid not in snippet_map]
        if missing and query_terms:
            snippet_map.update(self._best_chunk_snippets(missing, query_terms))
        chunk_snippets = snippet_map

        results = []
        for page_id in page_ids:
            page = pages.get(page_id)
            if not page:
                continue

            try:
                sources = json.loads(page.sources_json) if page.sources_json else []
            except json.JSONDecodeError:
                sources = []

            try:
                conflicts = json.loads(page.conflicts_json) if page.conflicts_json else []
            except json.JSONDecodeError:
                conflicts = []

            snippet = chunk_snippets.get(page_id) or self._best_snippet(
                page.content, query_terms or []
            )
            if len(snippet) > self.SNIPPET_MAX_CHARS:
                snippet = snippet[: self.SNIPPET_MAX_CHARS] + "..."

            results.append(SearchResult(
                page_id=page.id,
                title=page.title,
                content=page.content,
                page_type=page.page_type,
                score=relevance.get(page_id, 0.0),
                sources=sources,
                authority_level=page.authority_level,
                conflicts=conflicts,
                snippet=snippet,
                matched_by=list((matched_channels or {}).get(page_id, [])),
            ))

        return results


def search_knowledge_base(
    db: Session,
    query: str,
    knowledge_base_ids: Optional[list[int]] = None,
    user_id: Optional[int] = None,
    max_results: int = 5,
    is_admin: bool = False,
) -> list[SearchResult]:
    """
    知识库检索便捷函数
    """
    retrieval = KnowledgeRetrieval(db)
    return retrieval.search(
        query=query,
        knowledge_base_ids=knowledge_base_ids,
        user_id=user_id,
        max_results=max_results,
        is_admin=is_admin,
    )
