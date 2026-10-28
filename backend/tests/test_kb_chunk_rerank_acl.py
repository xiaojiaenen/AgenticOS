"""段级切片、启发式重排、知识库 ACL 的测试。

覆盖四块：

1. **切块器**：标题跟踪、超长块按句子切分、overlap 回带整句、偏移可回溯；
2. **段级召回**：页级向量「答错」时，段级向量仍能命中长页里那一节，
   并且命中片段直接来自那一段；
3. **重排**：查询词在片段里挨得近的排前，覆盖全的排前；
4. **ACL**：private 库显式共享后可见、未共享不可见、共享成员端点只能
   owner/admin 改。

外加 LDAP 「免管理员授权」的默认值守护。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    KBAccessControlModel,
    KBChunkModel,
    KBWikiPageModel,
    KnowledgeBaseModel,
    UserModel,
)
from app.db.session import SessionLocal, create_db_session
from app.main import app
from app.services.knowledge import retrieval as retrieval_mod
from app.services.knowledge.embedder import pack_vector

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. 切块器
# ---------------------------------------------------------------------------


def test_chunker_tracks_heading_and_offsets():
    from app.services.knowledge.chunker import chunk_markdown

    content = (
        "# 部署规范\n\n"
        "## 端口\n\n服务监听 8080，被占用时改成 8081。\n\n"
        "## 超时\n\n上游超时默认 30 秒，重试两次。"
    )
    chunks = chunk_markdown(content, max_chars=200, overlap=0, min_chars=10)

    assert chunks, "应切出至少一段"
    # 标题被正确归属
    headings = [c.heading for c in chunks if c.heading]
    assert "端口" in headings or "超时" in headings
    # 偏移落在原文范围内且单调不回退
    for chunk in chunks:
        assert 0 <= chunk.char_start < chunk.char_end <= len(content)
    # 每一段都真实存在于原文（允许拼接处的空白差异）
    for chunk in chunks:
        head = chunk.text.splitlines()[0]
        assert head in content


def test_chunker_splits_oversized_block_at_sentence_boundary():
    from app.services.knowledge.chunker import chunk_markdown

    body = "缓存同时过期会让数据库承受全部读请求。" * 12
    chunks = chunk_markdown(body, max_chars=100, overlap=0, min_chars=10)

    assert len(chunks) >= 3
    # 不硬切：每段都停在句号上（除非是最后一段被截）
    assert all(len(c.text) <= 120 for c in chunks)
    assert all(c.text.endswith("。") for c in chunks[:-1])


def test_chunker_overlap_repeats_whole_sentences():
    from app.services.knowledge.chunker import chunk_markdown

    first = "第一段讲成因。第二段讲影响与连接池压力。"
    second = "第三段说明抖动过期时间的具体做法，并给出验证方式。"
    chunks = chunk_markdown(f"{first}\n\n{second}", max_chars=40, overlap=15, min_chars=5)

    assert len(chunks) == 2
    # 第二段的回带前缀必须是第一段里的整句片段，而不是半句话
    prefix = chunks[1].text.splitlines()[0]
    assert prefix in chunks[0].text
    assert prefix.endswith("。")


def test_chunker_empty_content():
    from app.services.knowledge.chunker import chunk_markdown

    assert chunk_markdown("") == []
    assert chunk_markdown("   \n\n  ") == []


# ---------------------------------------------------------------------------
# 2. 重排信号
# ---------------------------------------------------------------------------


def test_rerank_prefers_adjacent_terms():
    from app.services.knowledge.rerank import score_result

    query_terms = ["端口", "超时"]
    adjacent = score_result(
        base_score=0.8,
        query_terms=query_terms,
        text="端口与超时",
        channels=["bm25"],
    )
    scattered = score_result(
        base_score=0.8,
        query_terms=query_terms,
        text="端口" + "无关内容" * 20 + "超时",
        channels=["bm25"],
    )
    assert adjacent > scattered


def test_rerank_prefers_full_coverage():
    from app.services.knowledge.rerank import score_result

    query_terms = ["端口", "超时", "重试"]
    full = score_result(
        base_score=0.7,
        query_terms=query_terms,
        text="端口超时重试",
        channels=["bm25"],
    )
    partial = score_result(
        base_score=0.7,
        query_terms=query_terms,
        text="端口配置说明",
        channels=["bm25"],
    )
    assert full > partial


def test_rerank_rewards_channel_agreement():
    from app.services.knowledge.rerank import score_result

    kwargs = dict(base_score=0.7, query_terms=["端口"], text="端口配置")
    both = score_result(channels=["bm25", "vector"], **kwargs)
    single = score_result(channels=["bm25"], **kwargs)
    assert both > single
    assert 0.0 <= single <= 1.0 and 0.0 <= both <= 1.0


# ---------------------------------------------------------------------------
# 3. 段级召回（集成）
# ---------------------------------------------------------------------------

_PAGE_CONTENT = (
    "# 缓存雪崩\n\n"
    "## 现象\n\n"
    "大量 key 在同一时刻过期，数据库瞬间承受全部读请求，响应时间飙升。\n\n"
    "## 应对\n\n"
    "给过期时间加随机抖动，把集中过期打散到不同时刻。\n"
)


@pytest.fixture
def kb_env():
    """一个 private 知识库：owner + 局外人 + 一页长文档（页向量故意「答错」）。"""
    suffix = uuid4().hex[:8]
    with create_db_session() as db:
        owner = UserModel(
            email=f"kb-owner-{suffix}@test.local",
            name="owner",
            password_hash=hash_password("pw-123456"),
        )
        outsider = UserModel(
            email=f"kb-outsider-{suffix}@test.local",
            name="outsider",
            password_hash=hash_password("pw-123456"),
        )
        db.add_all([owner, outsider])
        db.flush()

        kb = KnowledgeBaseModel(
            name="段级切片测试库",
            slug=f"kb-chunk-{suffix}",
            description="",
            owner_id=owner.id,
            visibility="private",
            scope="personal",
        )
        db.add(kb)
        db.flush()

        page = KBWikiPageModel(
            knowledge_base_id=kb.id,
            title="Redis 缓存雪崩应对",
            slug=f"chunk-page-{suffix}",
            page_type="concept",
            content=_PAGE_CONTENT,
            summary=None,
            frontmatter_json="{}",
            sources_json="[]",
            conflicts_json="[]",
            # 页级向量指向「现象」那一节：如果检索还在用页向量，
            # 查「随机抖动」就会被这一页以 0 相似度挡掉
            embedding=pack_vector([0.0, 1.0, 0.0, 0.0]),
            authority_level="L1",
            is_active=True,
        )
        db.add(page)
        db.flush()
        page_id = page.id

        # 段级切片：「应对」这一节才是查询想要的
        db.add_all(
            [
                KBChunkModel(
                    page_id=page_id,
                    knowledge_base_id=kb.id,
                    chunk_index=0,
                    heading="现象",
                    content="大量 key 在同一时刻过期，数据库瞬间承受全部读请求。",
                    char_start=0,
                    char_end=40,
                    embedding=pack_vector([0.0, 1.0, 0.0, 0.0]),
                ),
                KBChunkModel(
                    page_id=page_id,
                    knowledge_base_id=kb.id,
                    chunk_index=1,
                    heading="应对",
                    content="给过期时间加随机抖动，把集中过期打散到不同时刻。",
                    char_start=41,
                    char_end=len(_PAGE_CONTENT),
                    embedding=pack_vector([1.0, 0.0, 0.0, 0.0]),
                ),
            ]
        )
        db.commit()

        ids = {
            "kb_id": kb.id,
            "page_id": page_id,
            "owner_id": owner.id,
            "outsider_id": outsider.id,
            "owner_email": owner.email,
            "outsider_email": outsider.email,
        }

    retrieval_mod.invalidate_knowledge_cache()
    yield ids

    with create_db_session() as db:
        db.execute(delete(KBChunkModel).where(KBChunkModel.knowledge_base_id == ids["kb_id"]))
        db.execute(
            delete(KBAccessControlModel).where(
                KBAccessControlModel.knowledge_base_id == ids["kb_id"]
            )
        )
        db.execute(delete(KBWikiPageModel).where(KBWikiPageModel.knowledge_base_id == ids["kb_id"]))
        db.execute(delete(KnowledgeBaseModel).where(KnowledgeBaseModel.id == ids["kb_id"]))
        db.execute(delete(UserModel).where(UserModel.id.in_([ids["owner_id"], ids["outsider_id"]])))
        db.commit()
    retrieval_mod.invalidate_knowledge_cache()


class _FakeEmbedder:
    """查询向量固定为「应对」那一节的方向。"""

    dimensions = 4

    def __init__(self, vector):
        self._vector = vector

    def is_enabled(self):
        return self._vector is not None

    def embed_query(self, _text):
        return self._vector


def _search(kb_id: int, query: str, user_id: int, **kwargs):
    db = SessionLocal()
    try:
        return retrieval_mod.KnowledgeRetrieval(db).search(
            query, knowledge_base_ids=[kb_id], user_id=user_id, max_results=10, **kwargs
        )
    finally:
        db.close()


def test_chunk_vector_recall_beats_page_vector(kb_env, monkeypatch):
    """页向量答错时，段级向量仍能把长页里正确的那一节召回。"""
    monkeypatch.setattr(
        retrieval_mod,
        "get_knowledge_embedder",
        lambda: _FakeEmbedder([1.0, 0.0, 0.0, 0.0]),
    )

    results = _search(kb_env["kb_id"], "随机抖动", kb_env["owner_id"])
    assert results, "段级向量应召回该页"
    top = results[0]
    assert top.page_id == kb_env["page_id"]
    assert "vector" in top.matched_by
    # 命中片段直接来自「应对」那一段
    assert "随机抖动" in top.snippet


def test_snippet_uses_best_chunk_even_without_vectors(kb_env):
    """纯 BM25 场景下片段也来自段级切片，而不是按空白行临时猜。"""
    results = _search(kb_env["kb_id"], "随机抖动", kb_env["owner_id"])
    assert results
    top = results[0]
    assert "vector" not in top.matched_by, "本用例默认关闭向量通道"
    assert "随机抖动" in top.snippet


def test_chunk_path_falls_back_to_page_vector_when_no_chunks(kb_env, monkeypatch):
    """没有切片时退回页级向量（不能因为切片表为空就丢掉整个语义通道）。"""
    monkeypatch.setattr(
        retrieval_mod,
        "get_knowledge_embedder",
        lambda: _FakeEmbedder([0.0, 1.0, 0.0, 0.0]),
    )
    with create_db_session() as db:
        db.execute(delete(KBChunkModel).where(KBChunkModel.knowledge_base_id == kb_env["kb_id"]))
        db.commit()

    results = _search(kb_env["kb_id"], "完全无关的提问", kb_env["owner_id"])
    assert results, "页级向量兜底应召回"
    assert "vector" in results[0].matched_by


def test_rebuild_page_chunks_writes_rows(kb_env):
    from app.services.knowledge.chunk_index import rebuild_page_chunks

    with create_db_session() as db:
        page = db.get(KBWikiPageModel, kb_env["page_id"])
        stats = rebuild_page_chunks(db, page, embed=False)
        db.commit()

    assert stats["chunks"] >= 2
    assert stats["embedded"] == 0  # embed=False 不写向量

    with create_db_session() as db:
        rows = (
            db.query(KBChunkModel)
            .filter(KBChunkModel.page_id == kb_env["page_id"])
            .order_by(KBChunkModel.chunk_index)
            .all()
        )
        assert len(rows) >= 2
        assert all(row.content.strip() for row in rows)
        # 标题被记录到段上（向量化时用于补上下文）
        assert any(row.heading for row in rows)
        # 重建是整体替换，不残留旧切片
        assert len(rows) == stats["chunks"]


class _StubBatchEmbedder:
    """可用的假 embedding：任何文本都返回固定 4 维向量。"""

    dimensions = 4

    def is_enabled(self):
        return True

    def embed_batch(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, _text):
        return [1.0, 0.0, 0.0, 0.0]


def test_reindex_backfills_chunks_for_pages_with_page_vectors(kb_env, monkeypatch):
    """非 force 重建也要补「有页向量但没切片」的存量页。

    这是段级检索上线的迁移路径：存量页的页向量是完整的，只按
    ``embedding IS NULL`` 过滤会永远补不出切片。
    """
    from app.services.knowledge import chunk_index as chunk_index_mod
    from app.services.knowledge import embedder as embedder_mod
    from app.services.knowledge.ingest_pipeline import reindex_knowledge_base

    with create_db_session() as db:
        db.execute(delete(KBChunkModel).where(KBChunkModel.knowledge_base_id == kb_env["kb_id"]))
        db.commit()
        # 前提：页向量存在
        page = db.get(KBWikiPageModel, kb_env["page_id"])
        assert page.embedding

    stub = _StubBatchEmbedder()
    # chunk_index 在模块顶层绑定了 get_knowledge_embedder，两个命名空间都要打补丁
    monkeypatch.setattr(embedder_mod, "get_knowledge_embedder", lambda: stub)
    monkeypatch.setattr(chunk_index_mod, "get_knowledge_embedder", lambda: stub)

    stats = reindex_knowledge_base(kb_env["kb_id"])
    assert stats["enabled"] is True
    assert stats["checked"] >= 1, "有页向量但缺切片的页面必须被选中"
    assert stats["chunks"] >= 2
    assert stats["chunks_embedded"] >= 1

    with create_db_session() as db:
        rows = db.query(KBChunkModel).filter(KBChunkModel.page_id == kb_env["page_id"]).all()
        assert len(rows) >= 2
        assert all(row.embedding for row in rows)


# ---------------------------------------------------------------------------
# 4. ACL
# ---------------------------------------------------------------------------


def test_private_kb_invisible_until_granted(kb_env):
    """private 库：局外人搜不到；加进共享成员后能搜到。"""
    kb_id = kb_env["kb_id"]
    outsider_id = kb_env["outsider_id"]

    assert _search(kb_id, "随机抖动", outsider_id) == []

    with create_db_session() as db:
        db.add(
            KBAccessControlModel(
                knowledge_base_id=kb_id,
                principal_type="user",
                principal_id=outsider_id,
                role="viewer",
                granted_by=kb_env["owner_id"],
            )
        )
        db.commit()

    results = _search(kb_id, "随机抖动", outsider_id)
    assert results, "被显式共享后应能检索到 private 知识库"
    assert results[0].page_id == kb_env["page_id"]


def test_acl_role_hierarchy():
    from app.services.knowledge.acl import role_allows

    assert role_allows("viewer", "read")
    assert not role_allows("viewer", "write")
    assert role_allows("editor", "write")
    assert not role_allows("editor", "delete")
    assert role_allows("admin", "delete")
    assert not role_allows(None, "read")


def _admin_headers() -> tuple[dict, str]:
    email = f"kb-acl-admin-{uuid4().hex}@test.local"
    with create_db_session() as db:
        admin = UserModel(
            email=email,
            name="acl-admin",
            password_hash=hash_password("pw-123456"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        settings = get_settings()
        token = create_access_token(
            {"sub": str(admin.id), "email": admin.email, "role": admin.role},
            secret=settings.auth_secret_key,
            expires_in_seconds=settings.auth_token_expire_minutes * 60,
        )
    return {"Authorization": f"Bearer {token}"}, email


def test_acl_endpoints_list_and_replace(kb_env):
    headers, admin_email = _admin_headers()
    kb_id = kb_env["kb_id"]

    try:
        response = client.get(f"/api/v1/knowledge/bases/{kb_id}/acl", headers=headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

        payload = {
            "entries": [
                {"principal_type": "user", "principal_id": kb_env["outsider_id"], "role": "editor"}
            ]
        }
        response = client.put(
            f"/api/v1/knowledge/bases/{kb_id}/acl", headers=headers, json=payload
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["principal_id"] == kb_env["outsider_id"]
        assert items[0]["role"] == "editor"
        assert items[0]["email"] == kb_env["outsider_email"]

        # 重复提交同样内容 = 幂等替换，不产生重复行
        response = client.put(
            f"/api/v1/knowledge/bases/{kb_id}/acl", headers=headers, json=payload
        )
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

        # 清空成员
        response = client.put(
            f"/api/v1/knowledge/bases/{kb_id}/acl", headers=headers, json={"entries": []}
        )
        assert response.status_code == 200
        assert response.json()["items"] == []
    finally:
        with create_db_session() as db:
            db.execute(delete(UserModel).where(UserModel.email == admin_email))
            db.commit()


def test_acl_endpoint_rejects_unknown_user(kb_env):
    headers, admin_email = _admin_headers()
    try:
        response = client.put(
            f"/api/v1/knowledge/bases/{kb_env['kb_id']}/acl",
            headers=headers,
            json={"entries": [{"principal_type": "user", "principal_id": 99999999, "role": "viewer"}]},
        )
        assert response.status_code == 400
        assert "用户不存在" in response.json()["detail"]
    finally:
        with create_db_session() as db:
            db.execute(delete(UserModel).where(UserModel.email == admin_email))
            db.commit()


# ---------------------------------------------------------------------------
# 5. LDAP 免管理员授权
# ---------------------------------------------------------------------------


def test_ldap_auto_create_users_defaults_to_true():
    """LDAP bind 成功即建号登录，不再需要管理员预先授权。"""
    from app.services.ldap_auth_service import DEFAULTS, LdapConfig

    assert DEFAULTS["auto_create_users"] is True
    assert LdapConfig().auto_create_users is True


# ---------------------------------------------------------------------------
# 6. Embedding 端点与失败冷却
# ---------------------------------------------------------------------------


def test_embedder_prefers_dedicated_embedding_endpoint(monkeypatch):
    """聊天与 embedding 常不是同一家（DeepSeek 就没有 /embeddings）。"""
    from app.services.knowledge.embedder import KnowledgeEmbedder

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "sk-embed-only")
    get_settings.cache_clear()

    embedder = KnowledgeEmbedder()
    assert embedder._base_url == "https://api.siliconflow.cn/v1"  # noqa: SLF001
    assert embedder._api_key == "sk-embed-only"  # noqa: SLF001


def test_embedder_falls_back_to_general_openai_endpoint(monkeypatch):
    from app.services.knowledge.embedder import KnowledgeEmbedder

    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.delenv("KNOWLEDGE_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_EMBEDDING_API_KEY", raising=False)
    get_settings.cache_clear()

    embedder = KnowledgeEmbedder()
    assert embedder._base_url == "https://api.openai.com/v1"  # noqa: SLF001


def test_embedder_cools_down_after_transport_failure(monkeypatch):
    """上游挂了之后冷却期内不再发请求，避免每次检索都白等一次超时。"""
    import httpx

    from app.services.knowledge import embedder as embedder_mod

    monkeypatch.setenv("KNOWLEDGE_VECTOR_ENABLED", "true")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "sk-x")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()

    calls = {"n": 0}

    class _FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            calls["n"] += 1
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(embedder_mod.httpx, "Client", _FailingClient)

    embedder = embedder_mod.KnowledgeEmbedder()
    assert embedder.embed_query("第一次") is None
    assert embedder.embed_query("第二次") is None
    assert calls["n"] == 1, "冷却期内不应再发请求"
