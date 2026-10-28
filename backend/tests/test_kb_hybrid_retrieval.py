"""知识库混合检索（BM25 + 向量）与评分语义测试。

覆盖：
1. score 是 0~1 的相对相关度，阈值语义可用（旧实现最高 0.033，阈值形同虚设）；
2. 纯语义命中（字面零重叠）能被向量通道召回；
3. 向量不可用时自动退化为纯 BM25，且分数不被压低；
4. 命中片段取页内最相关的一段，而不是固定取开头；
5. 向量编解码往返、维度不符时拒绝使用；
6. 重建索引在未启用时返回 enabled=false 而不是抛错。
"""

from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy import delete

from app.db.models import KBWikiPageModel, KnowledgeBaseModel, UserModel
from app.db.session import create_db_session
from app.services.knowledge import retrieval as retrieval_mod
from app.services.knowledge.embedder import (
    cosine_similarity,
    pack_vector,
    unpack_vector,
)
from app.services.knowledge.retrieval import KnowledgeRetrieval

_KB_SLUG = "kb-hybrid-retrieval-test"

# 4 维假向量：让测试不依赖真实 embedding 服务
_PAGES = [
    # (title, content, 假向量)
    (
        "Redis 缓存雪崩应对",
        "缓存同时过期会让数据库瞬间承受全部读请求。应对方案是给过期时间加随机抖动。",
        [1.0, 0.0, 0.0, 0.0],
    ),
    (
        "报销流程",
        "差旅报销需要在十个工作日内提交发票原件，住宿费上限每晚五百元。",
        [0.0, 1.0, 0.0, 0.0],
    ),
    (
        "会议室预订",
        "会议室通过办公系统预订，单次会议最长不超过两小时。",
        [0.0, 0.0, 1.0, 0.0],
    ),
]


class _FakeEmbedder:
    """可控的假 embedder：查询向量由测试指定。"""

    dimensions = 4

    def __init__(self, query_vector: list[float] | None) -> None:
        self._query_vector = query_vector

    def is_enabled(self) -> bool:
        return self._query_vector is not None

    def embed_query(self, text: str):  # noqa: ARG002 —— 测试里不关心查询文本
        return self._query_vector


@pytest.fixture
def kb_fixture():
    with create_db_session() as db:
        user = UserModel(
            email="kb-hybrid@test.local",
            name="kb-hybrid",
            password_hash="test-only",
        )
        db.add(user)
        db.flush()
        kb = KnowledgeBaseModel(
            name="混合检索测试库",
            slug=_KB_SLUG,
            description="",
            owner_id=user.id,
        )
        db.add(kb)
        db.flush()

        page_ids = []
        for idx, (title, content, vector) in enumerate(_PAGES):
            page = KBWikiPageModel(
                knowledge_base_id=kb.id,
                title=title,
                slug=f"hybrid-{idx}",
                page_type="concept",
                content=content,
                summary=None,
                frontmatter_json="{}",
                sources_json="[]",
                conflicts_json="[]",
                embedding=pack_vector(vector),
                authority_level="L1",
                is_active=True,
            )
            db.add(page)
            db.flush()
            page_ids.append(page.id)
        db.commit()
        kb_id, user_id = kb.id, user.id

    retrieval_mod.invalidate_knowledge_cache()
    yield kb_id
    with create_db_session() as db:
        db.execute(delete(KBWikiPageModel).where(KBWikiPageModel.knowledge_base_id == kb_id))
        db.execute(delete(KnowledgeBaseModel).where(KnowledgeBaseModel.id == kb_id))
        db.execute(delete(UserModel).where(UserModel.id == user_id))
        db.commit()
    retrieval_mod.invalidate_knowledge_cache()


def _search(kb_id: int, query: str, **kwargs):
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return KnowledgeRetrieval(db).search(
            query, knowledge_base_ids=[kb_id], max_results=10, **kwargs
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 1. 评分语义
# ---------------------------------------------------------------------------


def test_score_is_normalized_to_zero_one(kb_fixture):
    """score 必须是 0~1 的相对相关度，而不是 1/(60+rank) 那种排名分。"""
    results = _search(kb_fixture, "缓存雪崩")
    assert results, "应召回至少一条"
    assert all(0.0 <= r.score <= 1.0 for r in results), [r.score for r in results]
    # 命中最相关页面时，分数应明显高于旧实现的上限 0.033
    assert results[0].score > 0.5, results[0].score
    # 排序与分数单调一致（api 使用者会直接展示这个分数）
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_threshold_filters_meaningfully(kb_fixture):
    """阈值 0.8 应能滤掉弱命中，而不是把结果全清空或全保留。"""
    baseline = _search(kb_fixture, "缓存雪崩")
    strict = _search(kb_fixture, "缓存雪崩", score_threshold=0.8)
    assert len(strict) <= len(baseline)
    assert strict, "最强命中自身得分应高于 0.8，阈值不该清空全部结果"
    assert all(r.score >= 0.8 for r in strict)


# ---------------------------------------------------------------------------
# 2. 纯语义召回
# ---------------------------------------------------------------------------


def test_pure_semantic_recall_without_lexical_overlap(kb_fixture, monkeypatch):
    """查询与正文零字面重叠时，向量通道应把语义一致的页面召回。"""
    monkeypatch.setattr(
        retrieval_mod, "get_knowledge_embedder", lambda: _FakeEmbedder([1.0, 0.0, 0.0, 0.0])
    )

    query = "大量请求瞬间打到数据库怎么办"  # 与「缓存雪崩」页无共同词
    results = _search(kb_fixture, query)

    assert results, "向量通道应召回语义相关页面"
    top = results[0]
    assert top.title == "Redis 缓存雪崩应对"
    assert "vector" in top.matched_by


def test_vector_channel_can_be_disabled(kb_fixture, monkeypatch):
    """向量不可用时不报错，且退化路径的分数不被 0.6 权重压低。"""
    monkeypatch.setattr(retrieval_mod, "get_knowledge_embedder", lambda: _FakeEmbedder(None))

    results = _search(kb_fixture, "缓存雪崩")
    assert results
    assert all("vector" not in r.matched_by for r in results)
    # 只有 BM25 通道时，最相关页面的归一化分应接近 1
    assert results[0].score > 0.9, results[0].score


def test_both_channels_boost_score(kb_fixture, monkeypatch):
    """两路都命中时分数应高于仅 BM25 命中。"""
    bm25_only = _search(kb_fixture, "缓存雪崩")[0].score
    monkeypatch.setattr(
        retrieval_mod, "get_knowledge_embedder", lambda: _FakeEmbedder([1.0, 0.0, 0.0, 0.0])
    )
    fused = _search(kb_fixture, "缓存雪崩")[0]
    assert "bm25" in fused.matched_by and "vector" in fused.matched_by
    assert fused.score >= bm25_only


# ---------------------------------------------------------------------------
# 3. 命中片段
# ---------------------------------------------------------------------------


def test_snippet_picks_relevant_paragraph(kb_fixture):
    """长页面里，片段应来自与查询最相关的那一段，而不是固定取开头。"""

    with create_db_session() as db:
        page = db.query(KBWikiPageModel).filter(
            KBWikiPageModel.knowledge_base_id == kb_fixture,
            KBWikiPageModel.title == "报销流程",
        ).one()
        page.content = (
            "第一章 总则\n\n本文档描述公司行政管理的总体原则与适用范围。\n\n"
            "第二章 发票要求\n\n差旅报销必须提交发票原件，缺一不可。\n\n"
            "第三章 附则\n\n本规定自发布之日起施行。"
        )
        db.commit()

    retrieval_mod.invalidate_knowledge_cache()
    results = _search(kb_fixture, "发票原件")
    target = next(r for r in results if r.title == "报销流程")
    assert "发票原件" in target.snippet
    assert target.snippet.strip() != target.content[: len(target.snippet)].strip()


# ---------------------------------------------------------------------------
# 4. 向量编解码
# ---------------------------------------------------------------------------


def test_vector_roundtrip_and_dimension_guard():
    vector = [0.1, -0.25, 0.5, 1.0]
    payload = pack_vector(vector)
    decoded = unpack_vector(payload, 4)
    assert decoded is not None
    assert np.allclose(decoded, np.array(vector, dtype="<f4"), atol=1e-6)

    # 换过模型（维度变化）后旧向量必须被拒绝，而不是算出无意义相似度
    assert unpack_vector(payload, 1536) is None
    assert unpack_vector("not-base64!!", 4) is None
    assert unpack_vector(None, 4) is None


def test_cosine_similarity_bounds():
    a = np.array([1.0, 0.0], dtype="<f4")
    b = np.array([0.0, 1.0], dtype="<f4")
    assert cosine_similarity(a, a) == pytest.approx(1.0)
    assert cosine_similarity(a, b) == pytest.approx(0.0)
    assert cosine_similarity(a, np.zeros(2, dtype="<f4")) == 0.0


# ---------------------------------------------------------------------------
# 5. 重建索引的降级行为
# ---------------------------------------------------------------------------


def test_reindex_reports_disabled_without_api_key(kb_fixture):
    """未启用向量时重建索引返回 enabled=false，不抛异常。"""
    from app.services.knowledge.ingest_pipeline import reindex_knowledge_base

    stats = reindex_knowledge_base(kb_fixture)
    assert stats["enabled"] is False
    assert stats["embedded"] == 0
    assert "未启用" in stats["message"]
