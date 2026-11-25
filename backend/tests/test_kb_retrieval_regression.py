"""知识库检索回归测试（LlamaIndex 接管版）。

覆盖四块：
1. 中文查询召回：小型 fixture 语料（10 篇中文 wiki 页面）上，
   8 个中文查询的期望文档必须落在 top-3；
2. 旧 bigram vs jieba tokenizer 的召回对比：仅打印报告，不作失败断言；
3. BM25 通道：LlamaIndex BM25Retriever（bm25s 引擎）—— 方言无关，
   检索器实例缓存（TTL / LRU / 超限不缓存）与失效钩子；
4. 融合候选：QueryFusionRetriever（RECIPROcal_RANK）。

测试跑在 conftest 重定向的一次性 SQLite 库上。
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete

from app.db.models import KBWikiPageModel, KnowledgeBaseModel, UserModel
from app.db.session import create_db_session
from app.services.knowledge.retrieval import KnowledgeRetrieval
from app.services.knowledge.tokenizer import bigram_tokenize, tokenize

_KB_SLUG = "kb-retrieval-regression-test"

# (标题, 内容)：10 篇中文 wiki，主题相互区隔，但共享"流程/规范/说明"等常见词
_CORPUS: list[tuple[str, str]] = [
    (
        "MySQL 全文索引配置指南",
        "在生产 MySQL 5.7 以上版本中，知识库检索依赖 FULLTEXT ngram 索引。"
        "运维人员需要在低峰期执行 alembic upgrade 建立索引，"
        "ngram 分词器默认按两个字切分中文文本，适合全文检索场景。",
    ),
    (
        "Redis 缓存集群架构说明",
        "缓存集群使用三主三从的拓扑结构。缓存雪崩是指大量缓存同时过期，"
        "导致数据库瞬间承受全部读请求。应对方案是为过期时间添加随机抖动，"
        "并部署哨兵节点实现自动故障转移。",
    ),
    (
        "员工差旅报销流程",
        "差旅费用报销需要在出差结束后十个工作日内提交发票原件。"
        "高铁票和机票按照实际金额报销，住宿费每晚上限五百元，"
        "超标部分由个人承担。审批流程依次经过直属主管和财务部门。",
    ),
    (
        "新员工入职指南",
        "新员工报到当天需要携带身份证复印件和学历证明。"
        "行政同事会发放门禁卡和办公电脑，IT 部门负责开通企业邮箱账号。"
        "入职培训安排在每周一上午，内容包括公司制度和安全须知。",
    ),
    (
        "Python 代码编写规范",
        "所有 Python 模块必须通过类型检查，函数命名使用小写蛇形风格。"
        "每个函数应当编写文档字符串说明参数和返回值，"
        "单元测试覆盖率要求不低于百分之八十，提交前运行代码格式化工具。",
    ),
    (
        "客服工单处理手册",
        "客户投诉工单按优先级分为紧急、高、普通三档。"
        "紧急工单需要在三十分钟内响应，两小时内给出处理方案。"
        "若一线客服无法解决，工单将升级到二线技术支持团队处理。",
    ),
    (
        "产品发布检查清单",
        "每次版本发布前必须完成回归测试和性能压测。"
        "发布负责人需要确认灰度计划、回滚预案和公告文案已就绪，"
        "发布窗口安排在工作日晚上八点之后，避开业务高峰时段。",
    ),
    (
        "数据库备份与恢复策略",
        "核心业务库每天凌晨执行一次全量备份，每小时追加一次增量备份。"
        "备份文件保留三十天，并异地存储一份。"
        "恢复演练每季度进行一次，确保备份数据在四小时内可以完整还原。",
    ),
    (
        "会议室预订说明",
        "公司会议室通过办公系统预订，单次会议最长不超过两小时。"
        "大型路演厅需要提前三天申请，投影仪和视频会议设备由行政统一管理。"
        "取消会议请及时释放预订，避免资源浪费。",
    ),
    (
        "安全漏洞应急响应预案",
        "发现安全漏洞后应立即上报安全团队，不得对外披露细节。"
        "严重漏洞要求二十四小时内完成修复并发布补丁，"
        "响应结束后必须编写复盘报告，说明漏洞成因和整改措施。",
    ),
]

# (查询, 期望命中的标题片段)：期望文档必须出现在 top-3
_RECALL_CASES: list[tuple[str, str]] = [
    ("如何配置 MySQL 全文索引", "MySQL 全文索引"),
    ("缓存雪崩怎么办", "Redis 缓存集群"),
    ("差旅发票报销标准是多少", "差旅报销"),
    ("新员工入职需要带什么材料", "新员工入职"),
    ("Python 函数命名有什么规范", "Python 代码"),
    ("客户投诉工单升级流程", "客服工单"),
    ("数据库备份保留多久", "备份与恢复"),
    ("发现安全漏洞应该怎么上报", "安全漏洞应急"),
]


def _insert_corpus():
    """向测试库写入 fixture 语料，返回 (kb_id, page_ids)。"""
    with create_db_session() as db:
        user = UserModel(
            email="kb-retrieval-regression@test.local",
            name="kb-retrieval-regression",
            password_hash="test-only",
        )
        db.add(user)
        db.flush()

        kb = KnowledgeBaseModel(
            name="检索回归测试库",
            slug=_KB_SLUG,
            description="jieba + FULLTEXT 迁移回归语料",
            owner_id=user.id,
        )
        db.add(kb)
        db.flush()

        page_ids = []
        for idx, (title, content) in enumerate(_CORPUS):
            page = KBWikiPageModel(
                knowledge_base_id=kb.id,
                title=title,
                slug=f"regression-{idx}",
                page_type="concept",
                content=content,
                frontmatter_json="{}",
                sources_json="[]",
                conflicts_json="[]",
                authority_level="L1",
                is_active=True,
            )
            db.add(page)
            db.flush()
            page_ids.append(page.id)
        db.commit()
        return kb.id, user.id


def _remove_corpus(kb_id: int, user_id: int):
    with create_db_session() as db:
        db.execute(
            delete(KBWikiPageModel).where(
                KBWikiPageModel.knowledge_base_id == kb_id
            )
        )
        db.execute(
            delete(KnowledgeBaseModel).where(KnowledgeBaseModel.id == kb_id)
        )
        db.execute(delete(UserModel).where(UserModel.id == user_id))
        db.commit()


@pytest.fixture(scope="module")
def kb_fixture():
    kb_id, user_id = _insert_corpus()
    yield kb_id
    _remove_corpus(kb_id, user_id)


def _search(kb_id: int, query: str, tokenizer_fn=None) -> list:
    from app.db.session import SessionLocal

    retrieval = KnowledgeRetrieval(SessionLocal())
    if tokenizer_fn is not None:
        original = KnowledgeRetrieval._tokenize
        KnowledgeRetrieval._tokenize = lambda self, text: tokenizer_fn(text)
    try:
        return retrieval.search(query, knowledge_base_ids=[kb_id], max_results=10)
    finally:
        if tokenizer_fn is not None:
            KnowledgeRetrieval._tokenize = original
        retrieval.db.close()


# ---------------------------------------------------------------------------
# 1. 中文查询召回（新 jieba tokenizer，Python BM25 路径）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("query", "expected_title"), _RECALL_CASES)
def test_chinese_query_recall(kb_fixture, query, expected_title):
    """8 个中文查询的期望文档必须落在 top-3。"""
    kb_id = kb_fixture
    results = _search(kb_id, query)
    top3_titles = [r.title for r in results[:3]]
    assert any(expected_title in t for t in top3_titles), (
        f"query={query!r} top3={top3_titles!r} 未命中期望文档 {expected_title!r}"
    )


# ---------------------------------------------------------------------------
# 2. bigram vs jieba 召回对比（仅打印报告，不作失败断言）
# ---------------------------------------------------------------------------


def test_bigram_vs_jieba_recall_report(kb_fixture):
    """对比旧 bigram 与新 jieba 分词的 top-3 召回数，打印对比报告。"""
    kb_id = kb_fixture
    jieba_hits = 0
    bigram_hits = 0
    lines = []
    for query, expected_title in _RECALL_CASES:
        jieba_top3 = [r.title for r in _search(kb_id, query)[:3]]
        bigram_top3 = [
            r.title for r in _search(kb_id, query, tokenizer_fn=bigram_tokenize)[:3]
        ]
        jieba_hit = any(expected_title in t for t in jieba_top3)
        bigram_hit = any(expected_title in t for t in bigram_top3)
        jieba_hits += int(jieba_hit)
        bigram_hits += int(bigram_hit)
        lines.append(
            f"  query={query!r}\n"
            f"    jieba  top3={jieba_top3} hit={jieba_hit}\n"
            f"    bigram top3={bigram_top3} hit={bigram_hit}"
        )

    report = (
        "召回对比（top-3，共 %d 个查询）：\n%s\n"
        "  jieba  召回: %d/%d\n  bigram 召回: %d/%d\n"
        % (
            len(_RECALL_CASES),
            "\n".join(lines),
            jieba_hits,
            len(_RECALL_CASES),
            bigram_hits,
            len(_RECALL_CASES),
        )
    )
    print("\n" + report)


# ---------------------------------------------------------------------------
# 3. BM25 通道（LlamaIndex BM25Retriever / bm25s 引擎，方言无关）
# ---------------------------------------------------------------------------


def test_bm25_search_returns_normalized_shapes(kb_fixture):
    """BM25 通道返回 (page_id, raw_score) 列表；bm25s 与方言无关。"""
    from app.db.session import SessionLocal

    kb_id = kb_fixture
    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        results = retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)
        assert results, "bm25s 路径应返回结果"
        assert all(isinstance(pid, int) and isinstance(score, float) for pid, score in results)
        assert results == sorted(results, key=lambda x: x[1], reverse=True)
    finally:
        retrieval.db.close()


def test_bm25_search_engine_is_dialect_agnostic(kb_fixture):
    """LlamaIndex 接管后不再按方言分路：同一 session 无论方言都走 bm25s。"""
    from app.db.session import SessionLocal

    kb_id = kb_fixture
    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        # 旧实现按 _is_mysql/_is_postgres 分出三条路径；新实现只有一条
        assert not hasattr(retrieval, "_bm25_search_mysql")
        assert not hasattr(retrieval, "_bm25_search_postgres")
        assert not hasattr(retrieval, "_bm25_search_python")
        # 换个 session（不同 bind）结果一致
        retrieval2 = KnowledgeRetrieval(SessionLocal())
        try:
            r1 = retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)
            r2 = retrieval2._bm25_search("缓存雪崩", [kb_id], page_type=None)
            assert [pid for pid, _ in r1] == [pid for pid, _ in r2]
        finally:
            retrieval2.db.close()
    finally:
        retrieval.db.close()


# ---------------------------------------------------------------------------
# 4. tokenizer 单元行为
# ---------------------------------------------------------------------------


def test_tokenize_filters_punct_and_single_cjk():
    tokens = tokenize("知识库的检索，支持 MySQL！v2（2024）")
    assert "知识库" in tokens
    assert "检索" in tokens
    assert "mysql" in tokens
    assert "v2" in tokens
    assert "2024" in tokens
    # 单字中文（"的"）与标点不出现
    assert "的" not in tokens
    assert all(t for t in tokens)  # 无空 token


def test_bigram_tokenize_keeps_legacy_behavior():
    # 旧逻辑等价性：中文逐字二元切分，单字保留
    assert bigram_tokenize("知识库") == ["知识", "识库"]
    assert bigram_tokenize("字") == ["字"]
    assert "mysql" in bigram_tokenize("连接 mysql 数据库")


def test_jieba_lazy_load():
    """jieba 惰性加载：导入 tokenizer 模块不触发词典初始化。"""
    import importlib

    from app.services.knowledge import tokenizer

    importlib.reload(tokenizer)
    assert tokenizer._jieba is None  # 未触发加载
    tokenizer.tokenize("触发加载")
    assert tokenizer._jieba is not None


# ---------------------------------------------------------------------------
# 5. M6-A6：LlamaIndex 检索器实例缓存
# ---------------------------------------------------------------------------


def test_retriever_cache_hit_avoids_rebuild(kb_fixture, monkeypatch):
    """第二次检索应命中缓存，不再重新加载/分词整库建索引。"""
    from app.db.session import SessionLocal
    from app.services.knowledge import retrieval as retrieval_mod

    kb_id = kb_fixture
    retrieval_mod.invalidate_knowledge_cache()

    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)

        build_calls = {"n": 0}
        original_build = retrieval._build_bm25_retriever

        def counting_build(*args, **kwargs):
            build_calls["n"] += 1
            return original_build(*args, **kwargs)

        monkeypatch.setattr(retrieval, "_build_bm25_retriever", counting_build)
        retrieval._bm25_search("缓存集群", [kb_id], page_type=None)
        assert build_calls["n"] == 0, "第二次检索不应重建检索器"
    finally:
        retrieval.db.close()


def test_retriever_cache_invalidate_forces_rebuild(kb_fixture, monkeypatch):
    """写入失效钩子清空缓存后，下一次检索应重新加载语料。"""
    from app.db.session import SessionLocal
    from app.services.knowledge import retrieval as retrieval_mod

    kb_id = kb_fixture
    retrieval_mod.invalidate_knowledge_cache()

    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)

        retrieval_mod.invalidate_knowledge_cache()

        build_calls = {"n": 0}
        original_build = retrieval._build_bm25_retriever

        def counting_build(*args, **kwargs):
            build_calls["n"] += 1
            return original_build(*args, **kwargs)

        monkeypatch.setattr(retrieval, "_build_bm25_retriever", counting_build)
        retrieval._bm25_search("缓存集群", [kb_id], page_type=None)
        assert build_calls["n"] == 1, "失效后应重建检索器"
    finally:
        retrieval.db.close()


def test_retriever_cache_ttl_expiry(kb_fixture):
    """TTL 到期后条目应被丢弃并重建。"""
    import time

    from app.db.session import SessionLocal
    from app.services.knowledge import retrieval as retrieval_mod

    kb_id = kb_fixture
    retrieval_mod.invalidate_knowledge_cache()

    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)

        cache_key = retrieval_mod._RetrieverCache.make_key([kb_id], None)
        entry = retrieval_mod._RETRIEVER_CACHE.get(cache_key)
        assert entry is not None, "首次检索后应有缓存条目"
        # 缓存的是构建好的 LlamaIndex BM25Retriever（接管标志）
        from llama_index.retrievers.bm25 import BM25Retriever

        assert isinstance(entry.retriever, BM25Retriever)

        # 把 built_at 往前拨，模拟 TTL 到期
        entry.built_at = time.monotonic() - (retrieval_mod._CACHE_TTL_SECONDS + 1)
        assert retrieval_mod._RETRIEVER_CACHE.get(cache_key) is None, "过期条目应被丢弃"

        retrieval._bm25_search("缓存集群", [kb_id], page_type=None)
        fresh = retrieval_mod._RETRIEVER_CACHE.get(cache_key)
        assert fresh is not None and fresh is not entry, "应重建新条目"
    finally:
        retrieval.db.close()


def test_retriever_cache_lru_eviction():
    """超过条目上限时按 LRU 淘汰最旧的一条。"""
    from app.services.knowledge.retrieval import _CACHE_MAX_ENTRIES, _RetrieverCache, _RetrieverEntry

    cache = _RetrieverCache()
    entry = _RetrieverEntry(0.0, None, 0)
    for i in range(_CACHE_MAX_ENTRIES + 2):
        cache.put((i, None), entry)
    assert len(cache._entries) <= _CACHE_MAX_ENTRIES
    # 最旧的键已被淘汰
    assert cache.get((0, None)) is None


def test_retriever_cache_skips_oversized_corpus(kb_fixture, monkeypatch):
    """文档数超过上限时不入缓存（宁可重算也不给半截缓存）。"""
    from app.db.session import SessionLocal
    from app.services.knowledge import retrieval as retrieval_mod

    kb_id = kb_fixture
    retrieval_mod.invalidate_knowledge_cache()
    monkeypatch.setattr(retrieval_mod, "_CACHE_MAX_DOCS", 0)

    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)
        cache_key = retrieval_mod._RetrieverCache.make_key([kb_id], None)
        assert retrieval_mod._RETRIEVER_CACHE.get(cache_key) is None, "超大语料不应入缓存"
        # 检索结果仍应正确（降级为每次重算）
        assert retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)
    finally:
        retrieval.db.close()
        retrieval_mod.invalidate_knowledge_cache()


def test_fusion_uses_llamaindex_rrf(kb_fixture):
    """候选集来自 QueryFusionRetriever（RECIPROCAL_RANK）—— LlamaIndex 内建 RRF。"""
    from app.db.session import SessionLocal
    from app.services.knowledge import retrieval as retrieval_mod

    kb_id = kb_fixture
    retrieval_mod.invalidate_knowledge_cache()

    retrieval = KnowledgeRetrieval(SessionLocal())
    try:
        # 向量通道关闭（未配 embedding）：候选应来自 BM25 单通道排序
        results = retrieval.search("缓存雪崩怎么办", knowledge_base_ids=[kb_id], max_results=5)
        assert results
        assert all("vector" not in r.matched_by for r in results)
        # 融合候选函数可独立调用
        candidates = retrieval._fuse_candidates("缓存雪崩", [kb_id], None, 10)
        assert candidates, "融合候选不应为空"
    finally:
        retrieval.db.close()


def test_ingest_pipeline_imports_invalidate_hook():
    """ingest_pipeline 必须绑定失效钩子（写库成功后的防脏读入口）。"""
    from app.services.knowledge import ingest_pipeline as ip_mod
    from app.services.knowledge.retrieval import invalidate_knowledge_cache

    assert ip_mod.invalidate_knowledge_cache is invalidate_knowledge_cache
