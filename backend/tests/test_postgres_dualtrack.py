"""PostgreSQL 双轨验证（docs/design/数据库选型评估-MySQL到PostgreSQL.md 战线 C）。

把 PG 确立为「生产推荐 + 未来默认」后，**本文件是双轨测试的落点**：
在真实 PG（默认本机 Homebrew postgresql@16；可用 ``AGENTICOS_PG_TEST_URL``
指向任意实例）上完整验证方言敏感的两条链路：

1. **迁移矩阵**：``create_all`` + alembic stamp/upgrade 全链（含 0027 的
   pg_trgm 扩展与 GIN 索引）在 PG 上幂等通过 —— conftest 把常规测试钉在
   SQLite（test_alembic.py 覆盖 SQLite 链），这里补 PG 这一轨；
2. **知识库检索路径**：``_bm25_search_postgres``（pg_trgm 相似度，中文
   无需分词扩展）能召回并给出 0~1 分，且与 FlashRank 重排链路兼容。

PG 不可达时整文件 skip —— CI 里用容器实例跑（PG job），本地开发按需。
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

PG_URL = os.environ.get(
    "AGENTICOS_PG_TEST_URL",
    "postgresql+psycopg://xiaojia@localhost:5432/postgres",
)


def _pg_available() -> bool:
    try:
        engine = create_engine(PG_URL, pool_pre_ping=True)
        with engine.connect():
            pass
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001 —— 本机没起 PG / 无 psycopg 都按不可用
        return False


pytestmark = pytest.mark.skipif(
    not _pg_available(), reason="PostgreSQL 不可达（本机未启动或无 psycopg 驱动）"
)


@pytest.fixture(scope="module")
def pg_db_url():
    """独立的临时 PG 库：跑完即删，不污染本机其他库。"""

    dbname = f"agenticos_pg_dt_{uuid.uuid4().hex[:10]}"
    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin.dispose()

    base = PG_URL.rsplit("/", 1)[0]
    url = f"{base}/{dbname}"
    yield url

    admin = create_engine(PG_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="module")
def pg_engine(pg_db_url):
    """迁移全链（镜像 init_db 的全新库流程）：create_all → stamp 到 head 的
    前一版 → upgrade head —— 让 0027 这类「扩展/索引」尾部迁移真正执行。"""
    engine = create_engine(pg_db_url)
    from app.db.models import Base

    Base.metadata.create_all(engine)

    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # env.py 见 sqlalchemy.url 非空即用它建独立引擎
    cfg.set_main_option("sqlalchemy.url", pg_db_url)
    # 从空版本表跑全链（镜像 init_db 的全新库流程）：表类迁移被守卫跳过，
    # 扩展/索引类（0027 pg_trgm）真正执行；幂等重放一次验证安全。
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    yield engine
    engine.dispose()


def _pg_indexes(engine, table: str) -> set[str]:
    from sqlalchemy import inspect

    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def test_migrations_apply_and_trgm_index_created(pg_engine):
    """0027 在 PG 上建出 pg_trgm 扩展依赖的 GIN 索引。"""
    names = _pg_indexes(pg_engine, "kb_wiki_pages")
    assert "ix_kb_wiki_pages_title_trgm" in names
    assert "ix_kb_wiki_pages_content_trgm" in names
    # 关键业务表齐全（create_all + 迁移补列后的最终形态）
    from sqlalchemy import inspect

    tables = set(inspect(pg_engine).get_table_names())
    for required in ("users", "agent_sessions", "published_items", "kb_wiki_pages"):  # workflows 已下线
        assert required in tables, required


def test_trgm_similarity_search_recalls_chinese(pg_engine):
    """pg_trgm 相似度检索：中文查询能召回贴题页面（无需分词扩展）。"""
    Session = sessionmaker(bind=pg_engine)
    with Session() as db:
        from app.core.security import hash_password
        from app.db.models import KBWikiPageModel, KnowledgeBaseModel, UserModel

        owner = UserModel(
            email=f"pg-dt-{uuid.uuid4().hex[:8]}@t.local",
            name="PG DualTrack",
            password_hash=hash_password("password-123"),
            role="user",
            is_active=True,
        )
        db.add(owner)
        db.flush()

        kb = KnowledgeBaseModel(
            name="pg-dualtrack",
            slug=f"pg-dualtrack-{uuid.uuid4().hex[:8]}",
            visibility="private",
            owner_id=owner.id,
            is_active=True,
        )
        db.add(kb)
        db.flush()
        pages = [
            KBWikiPageModel(
                knowledge_base_id=kb.id,
                title="Redis 连接超时配置",
                slug="redis-timeout",
                summary="socket_timeout 生产建议",
                content="Redis 客户端 socket_timeout 默认 5 秒，集群环境下建议放大到 60 秒并开启 keepalive。",
                page_type="reference",
                is_active=True,
            ),
            KBWikiPageModel(
                knowledge_base_id=kb.id,
                title="团建活动纪要",
                slug="outing",
                summary="周五下午",
                content="本周五下午部门团建，地点在滨江公园，自愿参加。",
                page_type="reference",
                is_active=True,
            ),
        ]
        db.add_all(pages)
        db.commit()

        from app.services.knowledge.retrieval import KnowledgeRetrieval

        # LlamaIndex 接管后 BM25 走 bm25s（方言无关）；这里验证 PG 库上
        # 同一套检索路径贯通（不再有 _bm25_search_postgres 专路）。
        retriever = KnowledgeRetrieval(db)
        assert db.get_bind().dialect.name == "postgresql"
        hits = retriever._bm25_search("Redis 连接超时", [kb.id], None)
        assert hits, "PG 库上 bm25s 检索应至少命中标题贴题的页面"
        top_id = hits[0][0]
        assert top_id == pages[0].id, "Redis 超时页应排在团建纪要前"
        assert hits[0][1] > 0, "BM25 原始分应为正"

        # 走完整 search()（RRF + 重排 + FlashRank 融合），确认 PG 路径贯通。
        # private 库必须带 owner 视角，否则可见性过滤直接返回空。
        results = retriever.search(
            "Redis 连接超时", knowledge_base_ids=[kb.id], user_id=owner.id, max_results=5
        )
        assert results
        assert all(0.0 <= r.score <= 1.0 for r in results)
        assert results[0].title == "Redis 连接超时配置"

        # 清理
        db.execute(select(KBWikiPageModel))
        db.rollback()


def test_trgm_index_present_for_production_scale(pg_engine):
    """GIN trgm 索引存在（生产规模下 SIMILARITY 走索引扫描而非全表）。"""
    names = _pg_indexes(pg_engine, "kb_wiki_pages")
    assert "ix_kb_wiki_pages_summary_trgm" in names
