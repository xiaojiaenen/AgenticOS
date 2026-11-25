"""知识库 PG 检索路径：pg_trgm 扩展 + GIN 三元组索引

Revision ID: 0027_kb_postgres_trgm
Revises: 0026_agent_audience_publish
Create Date: 2026-11-18

## 变更

仅 **PostgreSQL** 方言执行（其他方言 no-op，遵守迁移幂等纪律）：

1. ``CREATE EXTENSION IF NOT EXISTS pg_trgm`` —— contrib 扩展，无额外安装；
2. ``kb_wiki_pages`` 的 title / summary / content 建 GIN trgm 索引 ——
   ``_bm25_search_postgres`` 的 ``SIMILARITY()`` 查询从全表扫描降到索引扫描。

中文友好性：trigram 是**字符级** 3-gram，CJK 不需要 zhparser/pg_jieba 分词
扩展；排序质量由上层 FlashRank 重排兜住（数据库选型评估文档：配合
reranker 时关键词层不需要很精确）。

回滚：仅删索引与扩展（扩展可能被其他应用共用，用 ``IF EXISTS`` 尽力而为）。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_kb_postgres_trgm"
down_revision: Union[str, None] = "0026_agent_audience_publish"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    ("ix_kb_wiki_pages_title_trgm", "title"),
    ("ix_kb_wiki_pages_summary_trgm", "summary"),
    ("ix_kb_wiki_pages_content_trgm", "content"),
)


def _is_postgres(bind) -> bool:
    try:
        return bind.dialect.name == "postgresql"
    except Exception:  # noqa: BLE001
        return False


def _table_exists(bind, table: str) -> bool:
    try:
        return sa.inspect(bind).has_table(table)
    except Exception:  # noqa: BLE001
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _is_postgres(bind) or not _table_exists(bind, "kb_wiki_pages"):
        return

    # pg_trgm 是 contrib 扩展；托管 PG（RDS 等）一般也预装。失败不阻断迁移
    # —— 检索路径本身会降级 Python BM25，索引只是性能优化。
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except Exception:  # noqa: BLE001
        return

    for name, column in _INDEXES:
        bind.execute(
            sa.text(f'DROP INDEX IF EXISTS "{name}"')
        )
        bind.execute(
            sa.text(
                f'CREATE INDEX IF NOT EXISTS "{name}" ON kb_wiki_pages '
                f"USING gin ({column} gin_trgm_ops)"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _is_postgres(bind):
        return
    for name, _column in _INDEXES:
        bind.execute(sa.text(f'DROP INDEX IF EXISTS "{name}"'))
