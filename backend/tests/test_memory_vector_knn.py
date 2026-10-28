"""记忆向量检索的 RediSearch 命令构造测试。

历史缺陷：``search()`` 只传了过滤条件就 ``SORTBY __embedding_score``，
既没有 ``=>[KNN ...]`` 子句、又引用了只有 KNN 才会生成的别名字段，
RediSearch 直接报错，被 ``except`` 吞成空列表 —— 对外表现是"混合检索"
实际上永远是纯 BM25，且没有任何告警。

本测试锁定三件事：
1. 命令里必须出现 ``=>[KNN k @embedding $embedding AS ...]``；
2. ``PARAMS`` 声明的参数名必须与 KNN 子句里引用的变量一致；
3. ``RETURN`` 把向量距离取回来，并换算成"越大越相近"的相似度。
"""

from __future__ import annotations

import asyncio

import numpy as np

from app.services import memory_vector_store as mvs


class _FakeRedis:
    """捕获命令并返回一条构造好的响应。"""

    def __init__(self, response) -> None:
        self.commands: list[tuple] = []
        self._response = response

    async def execute_command(self, *args, **kwargs):
        self.commands.append(args)
        return self._response


def _run(coro):
    return asyncio.run(coro)


def test_search_uses_knn_clause(monkeypatch):
    # 返回形状：[total, key, [f1, v1, f2, v2, f3, v3, f4, v4]]
    response = [
        1,
        b"memory:vec:atom:7",
        [
            b"entity_id", b"7",
            b"entity_type", b"atom",
            b"layer", b"L1",
            b"vector_score", b"0.2",
        ],
    ]
    fake = _FakeRedis(response)
    monkeypatch.setattr(mvs, "_get_binary_redis", lambda: fake)

    store = mvs.MemoryVectorStore()
    store._initialized = True  # 跳过 FT.CREATE

    hits = _run(store.search([0.1] * 4, user_id=3, layers=("L1", "L2"), limit=5))

    assert fake.commands, "应发起一次 FT.SEARCH"
    args = fake.commands[0]
    query = args[2]

    assert "=>[KNN 5 @embedding $embedding" in query, query
    assert "@user_id:[3 3]" in query
    assert "@layer:{L1|L2}" in query

    # PARAMS 2 embedding <bytes> —— 参数名必须和 KNN 子句里的 $embedding 对上
    idx = args.index("PARAMS")
    assert args[idx + 1] == 2
    assert args[idx + 2] == "embedding"
    assert "$embedding" in query

    # 距离必须先 RETURN 回来，才能换算成相似度
    ret_idx = args.index("RETURN")
    assert "vector_score" in args[ret_idx:ret_idx + 6]
    sort_idx = args.index("SORTBY")
    assert args[sort_idx + 1] == "vector_score"

    assert hits and hits[0]["entity_id"] == 7
    assert hits[0]["layer"] == "L1"
    # 余弦距离 0.2 → 相似度 0.8（越大越相近）
    assert hits[0]["score"] == 0.8


def test_search_parses_withscores_shape(monkeypatch):
    """兼容三段形状（key + score + fields），避免参数组合变化后错位。"""
    response = [
        1,
        b"memory:vec:scenario:9",
        0.35,
        [b"entity_id", b"9", b"entity_type", b"scenario", b"layer", b"L2"],
    ]
    fake = _FakeRedis(response)
    monkeypatch.setattr(mvs, "_get_binary_redis", lambda: fake)

    store = mvs.MemoryVectorStore()
    store._initialized = True
    hits = _run(store.search([0.0] * 4, user_id=1, layers=("L2",), limit=3))

    assert len(hits) == 1
    assert hits[0]["entity_id"] == 9
    assert hits[0]["entity_type"] == "scenario"
    assert hits[0]["score"] == 0.65


def test_search_returns_empty_without_redis(monkeypatch):
    """Redis 不可用（内存 fallback）时返回空列表，不抛异常。"""
    monkeypatch.setattr(mvs, "_get_binary_redis", lambda: None)
    store = mvs.MemoryVectorStore()
    store._initialized = True
    assert _run(store.search([0.1] * 4, user_id=1, layers=("L1",), limit=3)) == []


def test_upsert_packs_float32(monkeypatch):
    """写入的是 float32 小端字节，维度必须与索引 DIM 一致。"""
    fake = _FakeRedis(True)

    class _HsetRedis(_FakeRedis):
        async def hset(self, key, mapping=None):
            self.last = (key, mapping)
            return 1

    fake2 = _HsetRedis(True)
    monkeypatch.setattr(mvs, "_get_binary_redis", lambda: fake2)

    store = mvs.MemoryVectorStore()
    store._initialized = True
    vector = [0.5] * mvs._settings.memory_embedding_dimensions
    _run(store.upsert(1, "atom", 1, "L1", "文本", vector))

    key, mapping = fake2.last
    assert key == "memory:vec:atom:1"
    raw = mapping["embedding"]
    assert isinstance(raw, bytes)
    assert len(raw) == 4 * len(vector)
    assert np.frombuffer(raw, dtype=np.float32)[0] == np.float32(0.5)
