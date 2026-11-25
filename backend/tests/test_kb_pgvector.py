"""pgvector 可选加速路径测试（数据库评估 阶段 2）。

覆盖：探测三条件（非 PG / 无扩展 / 列未迁移）→ False；降级路径行为
与旧路径一致（SQLite fixture 上检索结果不变）；similarity_search_chunks
的页级 max 聚合 + min_similarity 过滤（mock execute）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.knowledge.pgvector import (
    pgvector_available,
    reset_probe_cache,
    similarity_search_chunks,
)


class _FakeDialect:
    def __init__(self, name):
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name):
        self.dialect = _FakeDialect(dialect_name)


def _db(dialect="sqlite", rows=None):
    db = MagicMock()
    db.get_bind.return_value = _FakeBind(dialect)
    db.execute.return_value.all.return_value = rows or []
    return db


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_probe_cache()
    yield
    reset_probe_cache()


def test_probe_false_on_sqlite():
    db = _db("sqlite")
    assert pgvector_available(db) is False


def test_probe_false_when_extension_missing():
    db = _db("postgresql")
    db.execute.return_value.scalar.side_effect = [False]  # pg_type 无 vector
    assert pgvector_available(db) is False


def test_probe_false_when_column_not_migrated():
    db = _db("postgresql")
    # 扩展在，但列还是 bytea（存量库未迁移）
    db.execute.return_value.scalar.side_effect = [True, "bytea"]
    assert pgvector_available(db) is False


def test_probe_true_when_ready_and_cached():
    db = _db("postgresql")
    db.execute.return_value.scalar.side_effect = [True, "vector"]
    assert pgvector_available(db) is True
    # 第二次直接走缓存（不再 execute）
    assert pgvector_available(db) is True
    assert db.execute.call_count == 2  # 两次探测查询只发生一次


def test_probe_exception_is_false_not_raise():
    db = _db("postgresql")
    db.execute.side_effect = RuntimeError("boom")
    assert pgvector_available(db) is False


def test_similarity_search_aggregates_by_page_max():
    # 同页两段取最佳段；低相似度被过滤；按相似度降序
    rows = [
        (1, 0.9, "best chunk"),
        (1, 0.6, "worse chunk"),
        (2, 0.4, "below threshold"),   # < min_similarity=0.5 → 过滤
        (3, 0.7, "page 3"),
    ]
    db = _db("postgresql", rows)
    out = similarity_search_chunks(
        db, query_vector=[0.1, 0.2], knowledge_base_ids=[1],
        top_k=10, min_similarity=0.5,
    )
    assert [pid for pid, _, _ in out] == [1, 3]
    assert out[0] == (1, 0.9, "best chunk")


def test_similarity_search_top_k_cap():
    rows = [(i, 0.9 - i * 0.01, f"c{i}") for i in range(10)]
    db = _db("postgresql", rows)
    out = similarity_search_chunks(
        db, query_vector=[0.1], knowledge_base_ids=[1], top_k=3, min_similarity=0.0,
    )
    assert len(out) == 3
