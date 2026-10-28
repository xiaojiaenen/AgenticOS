"""
知识库检索服务

提供两路检索与融合：
- BM25 全文检索（MySQL FULLTEXT ngram / SQLite 走进程内 Python BM25）
- 向量语义检索（**段级** embedding 余弦，未配置 API Key 时自动关闭）
- RRF 选候选 + 相关度加权 + 本地启发式重排
- 权威性加权（排序 tie-break）
- 显式授权（kb_access_control / Casbin）与 visibility/scope 双重可见性过滤

**score 的语义**：对外暴露的 ``SearchResult.score`` 是 **0~1 的相对相关度**，
不是 BM25 原始分、也不是 RRF 排名分。计算分两步：

    1) 融合（决定候选集与粗分）
       bm25_norm = bm25_raw / 本次查询最高 BM25 分          （通道内归一到 0~1）
       vec_norm  = max(0, cosine(查询, 最佳段))               （绝对相似度）
       base      = 0.6 * bm25_norm + 0.4 * vec_norm           （向量不可用时退化为 bm25_norm）

    2) 重排（决定最终排序，见 ``rerank.py``）
       score = 0.55*base + 0.25*覆盖率 + 0.12*邻近度 + 0.08*通道一致性

这样 ``score_threshold`` 才是可解释的阈值：0.5 表示"至少命中一半相关度"，
而不是旧实现里 1/(60+rank) 那种最高只有 0.033、填任何正常阈值都会把结果
全部过滤掉的假阈值。
"""

import json
import logging
import re
import threading
import time
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sqlalchemy import bindparam, select, and_, text
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
# M6-A6：wiki 语料进程内缓存（仅 SQLite/dev 的 Python BM25 全量评分路径）
# ----------------------------------------------------------------------
#
# 为什么只缓存这一条路径：MySQL 走 FULLTEXT ngram，评分在数据库内完成，
# 进程内没有可复用的中间产物；只有 SQLite/dev 的 `_bm25_search_python`
# 会把整库文档拉进内存分词 —— 那是 O(语料量) 的重活，也是检索 P95 的主项。
#
# 缓存内容：语料快照（内容/标题/元信息）+ 分词结果 + DF/平均长度统计。
# 这些都是纯函数输入的产物，只随语料变化，查询词不参与缓存键。
#
# 失效：写入方（ingest_pipeline 等）在 commit 成功后调用 invalidate()。

_CACHE_TTL_SECONDS = 300.0
_CACHE_MAX_DOCS = 1000
_CACHE_MAX_ENTRIES = 8  # 保留最近若干个 (kb_ids, page_type) 组合的语料快照


class _CorpusEntry:
    """一份语料快照：文档 + 分词 + DF 统计。"""

    __slots__ = ("built_at", "docs", "doc_terms", "title_terms", "df", "avg_dl")

    def __init__(
        self,
        built_at: float,
        docs: list[tuple[int, str, str]],
        doc_terms: dict[int, list[str]],
        title_terms: dict[int, list[str]],
        df: dict[str, int],
        avg_dl: float,
    ) -> None:
        self.built_at = built_at
        self.docs = docs
        self.doc_terms = doc_terms
        self.title_terms = title_terms
        self.df = df
        self.avg_dl = avg_dl

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.built_at) > _CACHE_TTL_SECONDS


class _CorpusCache:
    """进程内 LRU + TTL 缓存，线程安全。

    用 OrderedDict 实现 LRU（上限 ``_CACHE_MAX_ENTRIES`` 个语料快照），
    每个快照内部文档数再受 ``_CACHE_MAX_DOCS`` 约束 —— 超限时不做部分缓存，
    直接每次重算：语料已经大到缓存不划算，半截缓存只会给出错误的评分。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple, _CorpusEntry] = OrderedDict()

    @staticmethod
    def make_key(knowledge_base_ids: list[int], page_type: Optional[str]) -> tuple:
        return (tuple(sorted(knowledge_base_ids)), page_type)

    def get(self, key: tuple) -> _CorpusEntry | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expired:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry

    def put(self, key: tuple, entry: _CorpusEntry) -> None:
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
                "docs": sum(len(e.docs) for e in self._entries.values()),
                "fresh": sum(1 for e in self._entries.values() if not (now - e.built_at > _CACHE_TTL_SECONDS)),
            }


_CORPUS_CACHE = _CorpusCache()


def invalidate_knowledge_cache() -> None:
    """清空 wiki 语料缓存。

    任何写入 kb_wiki_pages 的路径在 **commit 成功之后** 调用，
    否则失败回滚的写入会把旧语料误清（清空只是性能损失，但没必要），
    更糟的是没清导致读脏数据。
    """
    _CORPUS_CACHE.invalidate_all()
    logger.info("Knowledge corpus cache invalidated")


def can_view_knowledge_base(
    kb: KnowledgeBaseModel,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> bool:
    """知识库可见性判定。

    - admin：全部可见
    - visibility=private：仅 owner/admin
    - scope=personal：仅 owner/admin
    - scope=team：owner 恒可见；非 owner 仅 public（团队 ACL 未落地前的保守策略）
    - scope=org / 非 private：可见
    """
    if is_admin:
        return True
    if kb.visibility == "private":
        return user_id is not None and kb.owner_id == user_id
    if kb.scope == "personal":
        return user_id is not None and kb.owner_id == user_id
    if kb.scope == "team":
        if user_id is not None and kb.owner_id == user_id:
            return True
        return kb.visibility == "public"
    # org 或其他
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

    # MySQL FULLTEXT 路径单次检索返回的候选上限（进入融合前截断）
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

        logger.info("Searching knowledge base: query='%s...'", query[:50])

        # 获取可见的知识库
        visible_kb_ids = self._get_visible_knowledge_bases(
            knowledge_base_ids, user_id, is_admin=is_admin,
        )
        if not visible_kb_ids:
            return []

        # 两路检索：BM25（字面）+ 向量（语义，段级）
        bm25_hits = self._bm25_search(query, visible_kb_ids, page_type)
        vector_hits, chunk_snippets = self._vector_search(query, visible_kb_ids, page_type)

        if not bm25_hits and not vector_hits:
            return []

        # 候选集：RRF 排序，两路都命中的页面天然靠前，用它决定「取哪些页」
        fused = self._reciprocal_rank_fusion(bm25_hits, vector_hits)
        candidate_ids = list(fused.keys())[: max_results * 3]

        # 粗排依据：归一化相关度（RRF 只负责选候选，不参与对外 score）
        relevance = self._blend_relevance(bm25_hits, vector_hits)
        matched_by = self._matched_channels(bm25_hits, vector_hits)

        query_terms = tokenize(query)
        results = self._load_page_details(
            candidate_ids,
            relevance,
            matched_by,
            query_terms=query_terms,
            chunk_snippets=chunk_snippets,
        )

        # 重排：把「通道内相对强弱」换成「查询与命中片段的贴合度」
        for item in results:
            item.score = rerank_mod.score_result(
                base_score=item.score,
                query_terms=query_terms,
                # 标题参与词面信号：标题命中是最强的相关性证据之一
                text=f"{item.title}\n{item.snippet or item.content[: self.SNIPPET_MAX_CHARS]}",
                channels=item.matched_by,
            )

        # 相关度优先，同分时权威性高的靠前
        results.sort(
            key=lambda r: (r.score, self.AUTHORITY_WEIGHTS.get(r.authority_level, 1.0)),
            reverse=True,
        )

        # 相似度阈值：低于阈值的结果视为未命中（召回测试用它看参数影响）
        if score_threshold is not None and score_threshold > 0:
            results = [r for r in results if r.score >= score_threshold]

        return results[:max_results]

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

    def _bm25_search(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> list[tuple[int, float]]:
        """BM25 全文检索。

        - MySQL（生产）：FULLTEXT ngram 索引 MATCH AGAINST，仅取 top N，
          不再全量加载文档；查询异常时降级到 Python 路径。
        - SQLite（开发/测试）：Python BM25（jieba 分词 + 真实 DF 统计）。
        """
        if not knowledge_base_ids:
            return []

        if self._is_mysql():
            try:
                return self._bm25_search_mysql(query, knowledge_base_ids, page_type)
            except Exception as e:  # noqa: BLE001 —— 任何 MySQL 异常都降级，不阻断检索
                logger.warning(
                    "MySQL FULLTEXT 检索失败，降级到 Python BM25: %s", e,
                )
        return self._bm25_search_python(query, knowledge_base_ids, page_type)

    def _is_mysql(self) -> bool:
        """当前 session 是否运行在 MySQL 方言上。"""
        try:
            return self.db.get_bind().dialect.name == "mysql"
        except Exception:  # noqa: BLE001 —— 探测失败按非 MySQL 处理
            return False

    def _bm25_search_mysql(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> list[tuple[int, float]]:
        """MySQL FULLTEXT ngram 检索（索引由 0003 迁移建立）。

        NATURAL LANGUAGE MODE 下 ngram parser 自动对查询做二元切分，
        relevance 即 BM25 权重。只 SELECT 需要的列，避免全量加载。
        """
        conditions = [
            "knowledge_base_id IN :kb_ids",
            "is_active = :is_active",
        ]
        if page_type:
            conditions.append("page_type = :page_type")
        where_clause = " AND ".join(conditions)
        # 标题与摘要一并参与匹配：长文档的要点常出现在摘要里
        match_expr = (
            "(MATCH(content) AGAINST(:query IN NATURAL LANGUAGE MODE) "
            "+ MATCH(COALESCE(summary, '')) AGAINST(:query IN NATURAL LANGUAGE MODE) * 0.8 "
            "+ MATCH(title) AGAINST(:query IN NATURAL LANGUAGE MODE) * 1.5)"
        )

        stmt = text(f"""
            SELECT id, title, LEFT(content, 300) AS snippet, {match_expr} AS score
            FROM kb_wiki_pages
            WHERE {where_clause} AND {match_expr} > 0
            ORDER BY score DESC
            LIMIT :top_k
        """).bindparams(bindparam("kb_ids", expanding=True))

        params: dict = {
            "kb_ids": list(knowledge_base_ids),
            "is_active": 1,
            "query": query,
            "top_k": self.BM25_TOP_K,
        }
        if page_type:
            params["page_type"] = page_type

        rows = self.db.execute(stmt, params).fetchall()
        return [(int(row.id), float(row.score)) for row in rows]

    def _build_corpus(
        self,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> _CorpusEntry | None:
        """加载语料并一次性完成分词 + DF 统计。

        文档数超过 ``_CACHE_MAX_DOCS`` 时返回 None（不入缓存），由调用方
        走一次性计算路径 —— 缓存不下来的语料，缓存它只会浪费内存。
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

        docs: list[tuple[int, str, str]] = []
        doc_terms: dict[int, list[str]] = {}
        title_terms: dict[int, list[str]] = {}
        df: dict[str, int] = defaultdict(int)
        total_len = 0
        for page in pages:
            docs.append((page.id, page.title, page.content))
            # 摘要重复计入一次：等价于给摘要更高权重，命中摘要也能召回本页
            # （来自 c28da003 切片摘要索引，与 M6 语料缓存重构合并保留）
            summary_text = (getattr(page, "summary", None) or "")
            terms = tokenize(
                page.content + " " + page.title + (" " + summary_text * 2 if summary_text else "")
            )
            doc_terms[page.id] = terms
            title_terms[page.id] = tokenize(page.title)
            total_len += len(terms)
            for term in set(terms):
                df[term] += 1
        avg_dl = total_len / len(docs)

        return _CorpusEntry(time.monotonic(), docs, doc_terms, title_terms, dict(df), avg_dl)

    def _bm25_search_python(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> list[tuple[int, float]]:
        """Python 内存 BM25（SQLite fallback 路径）。

        M6-A6：语料快照 + 分词结果 + DF 统计走进程内缓存（TTL 300s / LRU），
        同一批知识库在 TTL 内的重复检索不再重复全库分词。
        文档数超过缓存上限时自动降级为每次重算（不返回错误的半截缓存）。
        """
        if not knowledge_base_ids:
            return []

        cache_key = _CorpusCache.make_key(knowledge_base_ids, page_type)
        entry = _CORPUS_CACHE.get(cache_key)

        if entry is None:
            entry = self._build_corpus(knowledge_base_ids, page_type)
            if entry is None:
                return []
            if len(entry.docs) <= _CACHE_MAX_DOCS:
                _CORPUS_CACHE.put(cache_key, entry)
            else:
                logger.info(
                    "Knowledge corpus too large to cache (%d docs > %d), skipping cache",
                    len(entry.docs),
                    _CACHE_MAX_DOCS,
                )

        doc_count = len(entry.docs)
        query_terms = tokenize(query)

        results = []
        for page_id, _title, _content in entry.docs:
            score = self._calculate_bm25_score(
                query_terms,
                entry.doc_terms[page_id],
                entry.df,
                doc_count,
                entry.avg_dl,
                title_terms=entry.title_terms.get(page_id),
            )
            if score > 0:
                results.append((page_id, score))

        # 按分数排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _reciprocal_rank_fusion(
        self,
        *result_lists: list[tuple[int, float]],
        k: int = 60,
    ) -> dict[int, float]:
        """
        Reciprocal Rank Fusion (RRF) 融合多路检索结果

        RRF(d) = sum(1 / (k + rank_i(d)))
        """
        scores = defaultdict(float)

        for results in result_lists:
            for rank, (page_id, _) in enumerate(results, 1):
                scores[page_id] += 1.0 / (k + rank)

        # 按融合分数排序
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return dict(sorted_items)

    def _vector_search(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> tuple[list[tuple[int, float]], dict[int, str]]:
        """向量语义检索（**段级** embedding 余弦，页级作兜底）。

        返回 ``(hits, best_chunk_text)``：
        - ``hits``：``[(page_id, 该页最佳段的余弦相似度)]``，已按相似度降序截断；
        - ``best_chunk_text``：``{page_id: 最佳段正文}``，直接当作命中片段用，
          不再靠启发式猜「页内哪段相关」。

        为什么按段而不是按页：页级向量把整页压成一个点，长页（编译出的
        source_summary / synthesis 常几千字）的主题被平均，问其中某一节往往
        召不回本页。段级取 ``max`` 聚合，长页里真正相关的那一段不会被稀释。

        兜底：库里一条切片都没有（存量库尚未重建索引）时，自动退回页级
        ``kb_wiki_pages.embedding``，语义通道不会因此整条消失。
        """
        embedder = get_knowledge_embedder()
        if not embedder.is_enabled():
            return [], {}

        query_vector = embedder.embed_query(query)
        if not query_vector:
            return [], {}
        query_np = np.asarray(query_vector, dtype=np.float32)

        min_similarity = _settings.knowledge_vector_min_similarity
        dimensions = embedder.dimensions

        chunk_stmt = (
            select(KBChunkModel.page_id, KBChunkModel.content, KBChunkModel.embedding)
            .join(KBWikiPageModel, KBWikiPageModel.id == KBChunkModel.page_id)
            .where(
                and_(
                    KBChunkModel.knowledge_base_id.in_(knowledge_base_ids),
                    KBChunkModel.embedding.isnot(None),
                    KBWikiPageModel.is_active.is_(True),
                )
            )
        )
        if page_type:
            chunk_stmt = chunk_stmt.where(KBWikiPageModel.page_type == page_type)

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
            return self._page_level_vector_search(query_np, knowledge_base_ids, page_type, dimensions)

        hits = sorted(best_by_page.items(), key=lambda item: item[1][0], reverse=True)
        top_k = _settings.knowledge_vector_top_k
        hits = hits[:top_k]
        return (
            [(page_id, score) for page_id, (score, _text) in hits],
            {page_id: text for page_id, (_score, text) in hits},
        )

    def _page_level_vector_search(
        self,
        query_np: np.ndarray,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
        dimensions: int,
    ) -> tuple[list[tuple[int, float]], dict[int, str]]:
        """页级向量兜底路径（无切片时）。"""
        conditions = [
            KBWikiPageModel.knowledge_base_id.in_(knowledge_base_ids),
            KBWikiPageModel.is_active.is_(True),
            KBWikiPageModel.embedding.isnot(None),
        ]
        if page_type:
            conditions.append(KBWikiPageModel.page_type == page_type)

        stmt = select(KBWikiPageModel.id, KBWikiPageModel.embedding).where(and_(*conditions))
        rows = self.db.execute(stmt).all()

        min_similarity = _settings.knowledge_vector_min_similarity
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
        return hits[: _settings.knowledge_vector_top_k], {}

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

    @staticmethod
    def _matched_channels(
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

    def _tokenize(self, text: str) -> list[str]:
        """分词入口：委托 tokenizer 模块（jieba 词级分词）。

        旧的 bigram 逻辑保留在 ``tokenizer.bigram_tokenize``，
        供 SQLite FTS5 兼容场景与新旧召回对比使用。
        """
        return tokenize(text)

    def _calculate_bm25_score(
        self,
        query_terms: list[str],
        doc_terms: list[str],
        df: dict[str, int],
        doc_count: int,
        avg_dl: float,
        title_terms: Optional[list[str]] = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> float:
        """计算单文档 BM25 分数。

        IDF 使用真实文档频率：``(N - df + 0.5) / (df + 0.5)``，
        常见词权重自然衰减，稀有词权重升高（修复迁移前 df=1 的近似）。
        标题命中沿用迁移前的固定加权（+10/词）。
        """
        doc_term_freq: dict[str, int] = defaultdict(int)
        for term in doc_terms:
            doc_term_freq[term] += 1

        dl = len(doc_terms)
        score = 0.0
        for term in set(query_terms):
            tf = doc_term_freq.get(term, 0)
            if tf == 0:
                continue

            term_df = df.get(term) or 1
            idf = max(0.0, (doc_count - term_df + 0.5) / (term_df + 0.5))

            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1)))
            score += idf * tf_norm

        # 标题命中加权
        if title_terms:
            for term in set(query_terms):
                if term in title_terms:
                    score += 10

        return score


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
