"""
知识库检索服务

提供多路检索和结果融合：
- BM25 全文检索
- 向量语义检索（可选）
- RRF 融合
- 权威性加权
- visibility/scope 权限过滤（private=owner/admin）
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import bindparam, select, and_, text
from sqlalchemy.orm import Session

from app.db.models import KBWikiPageModel, KnowledgeBaseModel
from app.services.knowledge.tokenizer import tokenize

logger = logging.getLogger(__name__)


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


class KnowledgeRetrieval:
    """知识库检索服务"""

    # 权威性权重
    AUTHORITY_WEIGHTS = {
        "L3": 2.0,
        "L2": 1.5,
        "L1": 1.0,
        "L0": 0.8,
    }

    # MySQL FULLTEXT 路径单次检索返回的候选上限（进入 RRF 融合前截断）
    BM25_TOP_K = 50

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
        """
        执行知识库检索

        Args:
            query: 查询文本
            knowledge_base_ids: 指定知识库 ID 列表（None 表示搜索所有有权限的知识库）
            user_id: 用户 ID（用于权限过滤）
            page_type: 过滤页面类型
            max_results: 最大结果数
            is_admin: 是否管理员（private=owner/admin）

        Returns:
            list[SearchResult]: 检索结果列表
        """
        logger.info(f"Searching knowledge base: query='{query[:50]}...'")

        # 获取可见的知识库
        visible_kb_ids = self._get_visible_knowledge_bases(
            knowledge_base_ids, user_id, is_admin=is_admin,
        )
        if not visible_kb_ids:
            return []

        # 多路检索
        bm25_results = self._bm25_search(query, visible_kb_ids, page_type)

        # RRF 融合（目前只有 BM25）
        fused = self._reciprocal_rank_fusion(bm25_results)

        # 权威性加权
        ranked = self._apply_authority_weights(fused)

        # 加载完整页面信息
        results = self._load_page_details(ranked[:max_results * 2])

        # 冲突标注
        results = self._annotate_conflicts(results)

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
        """获取用户可见的知识库 ID 列表（visibility/scope 过滤）。"""
        stmt = select(KnowledgeBaseModel).where(
            KnowledgeBaseModel.is_active.is_(True)
        )
        if knowledge_base_ids:
            stmt = stmt.where(KnowledgeBaseModel.id.in_(knowledge_base_ids))

        rows = self.db.execute(stmt).scalars().all()
        return [
            kb.id for kb in rows
            if can_view_knowledge_base(kb, user_id=user_id, is_admin=is_admin)
        ]

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
        match_expr = "MATCH(content) AGAINST(:query IN NATURAL LANGUAGE MODE)"

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

    def _bm25_search_python(
        self,
        query: str,
        knowledge_base_ids: list[int],
        page_type: Optional[str],
    ) -> list[tuple[int, float]]:
        """Python 内存 BM25（SQLite fallback 路径）。

        每篇文档只分词一次（此前 content 会被重复分词两次）；
        DF 用真实文档频率统计（此前 df=1 近似导致常见词 IDF 虚高）。
        """
        conditions = [
            KBWikiPageModel.knowledge_base_id.in_(knowledge_base_ids),
            KBWikiPageModel.is_active.is_(True),
        ]
        if page_type:
            conditions.append(KBWikiPageModel.page_type == page_type)

        stmt = select(KBWikiPageModel).where(and_(*conditions))
        pages = self.db.execute(stmt).scalars().all()

        doc_count = len(pages)
        if doc_count == 0:
            return []

        # 单遍预分词：文档词表（供评分与平均长度）、真实 DF 统计
        doc_terms_map: dict[int, list[str]] = {}
        df: dict[str, int] = defaultdict(int)
        total_len = 0
        for page in pages:
            terms = tokenize(page.content + " " + page.title)
            doc_terms_map[page.id] = terms
            total_len += len(terms)
            for term in set(terms):
                df[term] += 1
        avg_dl = total_len / doc_count

        query_terms = tokenize(query)
        results = []
        for page in pages:
            score = self._calculate_bm25_score(
                query_terms, doc_terms_map[page.id], df, doc_count, avg_dl,
                title_terms=tokenize(page.title),
            )
            if score > 0:
                results.append((page.id, score))

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

    def _apply_authority_weights(self, scores: dict[int, float]) -> list[tuple[int, float]]:
        """应用权威性权重"""
        return list(scores.items())

    def _load_page_details(
        self,
        ranked_items: list[tuple[int, float]],
    ) -> list[SearchResult]:
        """加载页面详细信息"""
        if not ranked_items:
            return []

        page_ids = [item[0] for item in ranked_items]
        score_map = dict(ranked_items)

        stmt = select(KBWikiPageModel).where(KBWikiPageModel.id.in_(page_ids))
        result = self.db.execute(stmt)
        pages = {p.id: p for p in result.scalars().all()}

        results = []
        for page_id, base_score in ranked_items:
            page = pages.get(page_id)
            if not page:
                continue

            # 应用权威性权重
            authority_weight = self.AUTHORITY_WEIGHTS.get(page.authority_level, 1.0)
            final_score = base_score * authority_weight

            # 解析来源和冲突
            try:
                sources = json.loads(page.sources_json) if page.sources_json else []
            except json.JSONDecodeError:
                sources = []

            try:
                conflicts = json.loads(page.conflicts_json) if page.conflicts_json else []
            except json.JSONDecodeError:
                conflicts = []

            results.append(SearchResult(
                page_id=page.id,
                title=page.title,
                content=page.content,
                page_type=page.page_type,
                score=final_score,
                sources=sources,
                authority_level=page.authority_level,
                conflicts=conflicts,
            ))

        # 按最终分数排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def _annotate_conflicts(self, results: list[SearchResult]) -> list[SearchResult]:
        """标注冲突信息"""
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
