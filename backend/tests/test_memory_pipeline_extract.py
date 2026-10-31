"""记忆蒸馏管线（L1 两阶段提取整合）回归。

针对线上真实故障：早期管线每轮无条件提取、与既有记忆只有
"前 50 字符完全相同"的去重 —— 用户实测同一句"项目代号是 ORION"
被存了 6 遍（共 31 条 ORION 记忆），每轮注入上下文后模型继续编造。

改造后（Mem0 式）：取既有记忆对照（向量检索，失败回退最近记忆）→
单次 LLM 加性提取（prompt 带既有记忆编号，只输出净新增）→ 代码级
硬闸（MD5 / 前 50 字符 / difflib / 向量余弦）。本测试用假 LLM +
真 SQLite + 假 embedder 验证全链路。
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, MemoryModel
from app.services import memory_pipeline as mp
from app.services.memory_pipeline import MemoryPipeline


@pytest.fixture()
def sqlite_env(monkeypatch):
    """把 pipeline 的 DB 会话指到内存 SQLite，隔离于本地 MySQL。"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(mp, "create_db_session", factory)

    # 假 embedder：32 维按字符 bigram 造向量（同义文本字符组成相近 → 余弦高）
    class FakeEmbedder:
        async def embed(self, text: str) -> list[float]:
            vec = [0.0] * 32
            for i in range(len(text) - 1):
                vec[sum(map(ord, text[i:i + 2])) % 32] += 1.0
            return vec

    monkeypatch.setattr(mp, "get_embedder", lambda: FakeEmbedder())

    # 假向量库：记录 upsert；search 返回全部条目（模拟"最近记忆全部相关"）
    class FakeVectorStore:
        def __init__(self) -> None:
            self.docs: dict[int, list[float]] = {}

        async def upsert(self, entity_id, entity_type, user_id, layer, text, vector):
            self.docs[entity_id] = vector

        async def search(self, query_vector, user_id, layers, entity_types=("atom",), limit=10):
            return [
                {"doc_id": f"atom:{mid}", "score": 0.9, "entity_id": mid, "entity_type": "atom", "layer": "L1"}
                for mid in sorted(self.docs)
            ][:limit]

        async def delete(self, entity_type, entity_id):
            self.docs.pop(entity_id, None)

    fake_store = FakeVectorStore()
    monkeypatch.setattr(mp, "get_vector_store", lambda: fake_store)

    # BM25/FTS 索引在测试里是外部依赖，替成空操作
    class FakeBM25:
        async def index_document(self, *a, **k) -> None:
            pass

        async def delete_document(self, *a, **k) -> None:
            pass

    monkeypatch.setattr("app.services.memory_bm25.get_bm25_backend", lambda: FakeBM25())

    return {"store": fake_store, "factory": factory}


def _set_llm_response(responses: list[str]) -> None:
    """按调用顺序吐固定 LLM 输出。"""

    class FakeResp:
        def __init__(self, content: str) -> None:
            self.message = type("M", (), {"content": content})()

    class FakeGateway:
        def __init__(self, *a, **k) -> None:
            pass

        async def generate(self, messages):
            return FakeResp(responses.pop(0) if responses else '{"memories": []}')

    patch.object(mp, "build_llm", lambda **k: FakeGateway()).start()


def _rows(factory):
    s = factory()
    try:
        return s.query(MemoryModel).order_by(MemoryModel.id).all()
    finally:
        s.close()


@pytest.mark.asyncio
async def test_extracts_and_saves_new_facts(sqlite_env):
    """干净环境：LLM 提取的记忆经 on_turn_complete 正常入库。"""
    _set_llm_response([
        json.dumps({"memories": [
            {"content": "用户叫张三，在后端团队", "type": "fact", "importance": 0.9},
            {"content": "用户偏好 Vue 3 加 TypeScript", "type": "tech", "importance": 0.7},
        ]}),
    ])
    pipeline = MemoryPipeline()
    await pipeline.on_turn_complete(1, "s1", "我叫张三，喜欢用 Vue", "你好张三！")
    rows = _rows(sqlite_env["factory"])
    assert len(rows) == 2
    assert {r.content for r in rows} == {"用户叫张三，在后端团队", "用户偏好 Vue 3 加 TypeScript"}


@pytest.mark.asyncio
async def test_similar_rephrase_is_blocked_by_hard_gate(sqlite_env):
    """核心回归：重复事实被硬闸拦截，不再重复入库。

    第一轮与第二轮的提取内容只差一个句号 —— difflib ≈ 0.98，走 difflib 闸
    （向量余弦的数学语义由 test_hard_gate_semantic_and_exact 单独覆盖；
    真实语义向量下"项目代号是 ORION"这种换措辞对余弦 ≥0.92，同样会拦）。
    """
    _set_llm_response([
        json.dumps({"memories": [{"content": "用户的项目代号是 ORION", "type": "project", "importance": 0.8}]}),
    ])
    pipeline = MemoryPipeline()
    await pipeline.on_turn_complete(1, "s1", "记住我的项目代号是 ORION", "好的")
    assert len(_rows(sqlite_env["factory"])) == 1

    # 第二轮：模型又提取了一条几乎相同的同一事实
    _set_llm_response([
        json.dumps({"memories": [{"content": "用户的项目代号是 ORION。", "type": "project", "importance": 0.8}]}),
    ])
    await pipeline.on_turn_complete(1, "s1", "我的项目是 ORION", "了解")
    # 旧管线上这里会再存一条；现在硬闸必须拦下
    assert len(_rows(sqlite_env["factory"])) == 1


@pytest.mark.asyncio
async def test_per_turn_limit(sqlite_env):
    """单轮最多入库 3 条，LLM 输出再多也被截断（六条彼此无关的事实）。"""
    _set_llm_response([
        json.dumps({"memories": [
            {"content": "用户的主语言是 Python", "type": "tech", "importance": 0.5},
            {"content": "用户的常驻城市是杭州", "type": "fact", "importance": 0.5},
            {"content": "用户偏好简洁的沟通风格", "type": "preference", "importance": 0.5},
            {"content": "用户的团队使用 GitLab 做代码托管", "type": "fact", "importance": 0.5},
            {"content": "用户在业余时间喜欢爬山", "type": "fact", "importance": 0.5},
            {"content": "用户的机器是 Macbook Pro", "type": "fact", "importance": 0.5},
        ]}),
    ])
    pipeline = MemoryPipeline()
    await pipeline.on_turn_complete(1, "s1", "自述一堆事实", "好的")
    rows = _rows(sqlite_env["factory"])
    assert len(rows) == mp._MAX_ATOMS_PER_TURN


@pytest.mark.asyncio
async def test_extraction_prompt_has_negative_rules():
    """prompt 必须带负面清单与既有记忆对照段 —— 这两条是治乱的根本。"""
    prompt = mp.ATOM_EXTRACTION_PROMPT
    assert "existing_memories" in prompt and "conversation" in prompt
    for banned in ("进行时流水", "不要重复提取", "最多输出 3 条"):
        assert banned in prompt, f"prompt 缺少关键约束: {banned}"


@pytest.mark.asyncio
async def test_hard_gate_semantic_and_exact():
    """硬闸语义：MD5/前缀必拦；向量同向拦；正交（无关）不拦。"""
    dup = await MemoryPipeline._is_duplicate(
        "项目代号是 ORION",
        [1.0, 0.0],
        ["用户的项目代号为 ORION"],
        [[0.99, 0.1]],  # 近同向 → 余弦 ≈ 0.995
    )
    assert dup is True

    unrelated = await MemoryPipeline._is_duplicate(
        "项目代号是 ORION",
        [1.0, 0.0],
        ["完全不同话题的无关记忆内容"],
        [[0.0, 1.0]],  # 正交 → 余弦 0
    )
    assert unrelated is False

    exact = await MemoryPipeline._is_duplicate(
        "同样的内容",
        None,
        ["同样的内容"],
        [None],  # 向量失败时 MD5/前缀/difflib 仍然生效
    )
    assert exact is True
