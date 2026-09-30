"""知识库检索回归测试（jieba + MySQL FULLTEXT ngram 迁移）。

覆盖三块：
1. 中文查询召回：小型 fixture 语料（10 篇中文 wiki 页面）上，
   8 个中文查询的期望文档必须落在 top-3；
2. 旧 bigram vs 新 jieba tokenizer 的召回对比：仅打印报告，不作失败断言；
3. MySQL FULLTEXT 分支：mock db 验证 SQL/参数构造正确性 + 异常降级路径。

测试跑在 conftest 重定向的一次性 SQLite 库上（Python BM25 路径）。
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
# 3. MySQL FULLTEXT 分支（mock，不依赖真实 MySQL）
# ---------------------------------------------------------------------------


class _FakeDialect:
    def __init__(self, name):
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name):
        self.dialect = _FakeDialect(dialect_name)


class _FakeRow:
    def __init__(self, row_id, score):
        self.id = row_id
        self.score = score


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeMySQLSession:
    """捕获 SQL 与参数的假 Session（仅支撑 MySQL 分支所需接口）。"""

    def __init__(self, rows=None, exc=None):
        self.captured = []
        self._rows = rows or []
        self._exc = exc

    def get_bind(self):
        return _FakeBind("mysql")

    def execute(self, stmt, params=None):
        if self._exc is not None:
            raise self._exc
        self.captured.append((str(stmt), params))
        return _FakeResult(self._rows)


class FakeSQLiteSession(FakeMySQLSession):
    def get_bind(self):
        return _FakeBind("sqlite")


def test_mysql_branch_query_construction():
    """MySQL 分支生成 MATCH AGAINST 语句并按分数返回 top-k。"""
    session = FakeMySQLSession(rows=[_FakeRow(7, 12.5), _FakeRow(3, 4.0)])
    retrieval = KnowledgeRetrieval(session)
    results = retrieval._bm25_search("全文索引 配置", [1, 2], page_type="concept")

    assert results == [(7, 12.5), (3, 4.0)]
    sql, params = session.captured[0]
    assert "MATCH(content) AGAINST(:query IN NATURAL LANGUAGE MODE)" in sql
    assert "FROM kb_wiki_pages" in sql
    assert "ORDER BY score DESC" in sql
    assert "LIMIT :top_k" in sql
    assert "LEFT(content, 300) AS snippet" in sql
    # 只 SELECT 需要的列，不允许全量加载（SELECT * 或整行 ORM 查询）
    assert "SELECT *" not in sql
    assert params["kb_ids"] == [1, 2]
    assert params["query"] == "全文索引 配置"
    assert params["top_k"] == KnowledgeRetrieval.BM25_TOP_K
    assert params["page_type"] == "concept"
    assert params["is_active"] == 1


def test_mysql_branch_no_page_type_filter():
    """page_type 为空时不应出现 page_type 条件。"""
    session = FakeMySQLSession(rows=[])
    retrieval = KnowledgeRetrieval(session)
    retrieval._bm25_search("查询", [5], page_type=None)

    sql, params = session.captured[0]
    assert "page_type" not in sql
    assert "page_type" not in params


def test_mysql_branch_degrades_to_python_on_error():
    """MySQL 查询异常时降级到 Python BM25 路径。"""
    session = FakeMySQLSession(exc=RuntimeError("connection refused"))
    retrieval = KnowledgeRetrieval(session)

    fallback_calls = []
    original = KnowledgeRetrieval._bm25_search_python
    KnowledgeRetrieval._bm25_search_python = lambda self, q, ids, pt: (
        fallback_calls.append((q, ids, pt)) or [(999, 1.0)]
    )
    try:
        results = retrieval._bm25_search("查询词", [42], page_type=None)
    finally:
        KnowledgeRetrieval._bm25_search_python = original

    assert fallback_calls, "异常后未调用 Python 降级路径"
    assert fallback_calls[0] == ("查询词", [42], None)
    assert results == [(999, 1.0)]


def test_sqlite_session_uses_python_path(kb_fixture):
    """SQLite session 直接走 Python BM25（_is_mysql 判定为 False）。"""
    from app.db.session import SessionLocal

    kb_id = kb_fixture
    retrieval = KnowledgeRetrieval(SessionLocal())
    assert retrieval._is_mysql() is False

    results = retrieval._bm25_search("缓存雪崩", [kb_id], page_type=None)
    assert results, "Python BM25 路径应返回结果"
    assert all(isinstance(pid, int) and isinstance(score, float) for pid, score in results)


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
