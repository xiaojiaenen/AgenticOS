"""段级切片表 kb_chunks

Revision ID: 0011_kb_chunks
Revises: 0010_drop_departments
Create Date: 2026-10-27

知识库检索从「页级向量」下沉到「段级向量」：

- 新增 ``kb_chunks`` 表，一页切成若干段（Markdown 语义边界 + 整句 overlap），
  每段一个 embedding；
- 向量召回按段算，长页的局部内容不再被全局平均掉；
- 命中片段直接取真正命中的那一段，替代原来的「猜哪段相关」启发式。

页级 ``kb_wiki_pages.embedding`` 保留不动：段表为空（存量库尚未重建、
或向量化失败）时检索自动退化为页级向量。

MySQL 上额外给 ``kb_chunks.content`` 建 FULLTEXT ngram 索引，为后续
「段级字面召回」留出口；SQLite（开发/测试）走 Python 侧逻辑，直接 no-op。

存量库需要执行 ``POST /knowledge/bases/{id}/reindex``（或管理端「重建索引」）
才会补出切片；不重建也能正常检索，只是仍走页级向量。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0011_kb_chunks"
down_revision: Union[str, None] = "0010_drop_departments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "kb_chunks"
_FULLTEXT_INDEX = "ft_kb_chunks_content"


def _index_exists(bind, table: str, index_name: str) -> bool:
    row = bind.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :table AND index_name = :index_name"
        ),
        {"table": table, "index_name": index_name},
    ).scalar()
    return bool(row)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("page_id", sa.Integer(), sa.ForeignKey("kb_wiki_pages.id"), nullable=False),
            sa.Column(
                "knowledge_base_id",
                sa.Integer(),
                sa.ForeignKey("knowledge_bases.id"),
                nullable=False,
            ),
            sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("heading", sa.String(length=500), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("char_start", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("char_end", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("embedding", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
        op.create_index("ix_kb_chunks_page_id", _TABLE, ["page_id"])
        op.create_index("ix_kb_chunks_knowledge_base_id", _TABLE, ["knowledge_base_id"])
        op.create_index("ix_kb_chunks_page_chunk", _TABLE, ["page_id", "chunk_index"])
        op.create_index("ix_kb_chunks_kb", _TABLE, ["knowledge_base_id"])

    # FULLTEXT 只在 MySQL 上有意义（SQLite 走 Python 侧 BM25）
    if bind.dialect.name != "mysql":
        return
    if _index_exists(bind, _TABLE, _FULLTEXT_INDEX):
        return
    try:
        op.execute(
            f"CREATE FULLTEXT INDEX {_FULLTEXT_INDEX} ON {_TABLE} (content) "
            f"WITH PARSER ngram"
        )
    except Exception:
        try:
            op.execute(f"CREATE FULLTEXT INDEX {_FULLTEXT_INDEX} ON {_TABLE} (content)")
        except Exception:
            pass  # 并发/重放场景下已存在，幂等跳过


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(_TABLE):
        return
    if bind.dialect.name == "mysql" and _index_exists(bind, _TABLE, _FULLTEXT_INDEX):
        try:
            op.execute(f"DROP INDEX {_FULLTEXT_INDEX} ON {_TABLE}")
        except Exception:
            pass
    op.drop_table(_TABLE)
