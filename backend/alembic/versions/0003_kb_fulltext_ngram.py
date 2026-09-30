"""kb wiki 全文索引：kb_wiki_pages.content 增加 MySQL FULLTEXT ngram 索引

Revision ID: 0003_kb_fulltext_ngram
Revises: 0002_mysql_longtext
Create Date: 2026-09-30

知识库检索 BM25 路径从 Python 全量内存评分迁移到 MySQL FULLTEXT：
``MATCH(content) AGAINST(... IN NATURAL LANGUAGE MODE)``。中文检索依赖
ngram parser（内置，要求 MySQL >= 5.7.6，默认 ngram_token_size=2，与
检索侧 bigram/jieba 词粒度匹配）。

行为约定：
- 仅 MySQL 方言执行；SQLite（开发/测试）走 Python BM25，直接 no-op；
- 幂等：索引已存在或表不存在时跳过（查 information_schema.statistics）；
- ngram 索引创建失败时（如 MySQL < 5.7.6）降级创建普通 FULLTEXT 索引，
  再失败（如已存在）静默跳过 —— 检索侧对索引缺失同样有 Python 降级路径；
- downgrade 删除索引（不动表与数据）。

部署注意：FULLTEXT 索引创建会锁表（5.6/5.7 InnoDB 为 FULLTEXT 构建
期间 DML 会被阻塞），大表请在低峰期执行；存量库此前由
``alembic stamp head`` 对齐基线，本次需真正执行 ``alembic upgrade head``
（先 stamp 到 0002 再 upgrade，或直接 upgrade，迁移自身幂等可重跑）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0003_kb_fulltext_ngram"
down_revision: Union[str, None] = "0002_mysql_longtext"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 列)
_TARGETS: tuple[tuple[str, str], ...] = (
    ("kb_wiki_pages", "content"),
)


def _index_exists(bind, table: str, index_name: str) -> bool:
    """通过 information_schema 精确判断索引是否存在。

    不用 inspector.get_indexes：MySQL 方言对 FULLTEXT 索引的枚举
    在不同 SQLAlchemy 版本行为不一致，information_schema 最可靠。
    """
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
    if bind.dialect.name != "mysql":
        return  # SQLite 开发/测试库走 Python BM25，无需 FULLTEXT

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column in _TARGETS:
        if table not in tables:
            continue
        index_name = f"ft_{table}_{column}"
        if _index_exists(bind, table, index_name):
            continue
        try:
            # ngram parser：MySQL >= 5.7.6 内置，中文按二元切分建索引
            op.execute(
                f"CREATE FULLTEXT INDEX {index_name} ON {table} ({column}) "
                f"WITH PARSER ngram"
            )
        except Exception:
            # 老版本 MySQL 无 ngram：降级为默认 parser 的 FULLTEXT
            #（英文可用；中文检索由检索侧 Python 降级路径兜底）
            try:
                op.execute(
                    f"CREATE FULLTEXT INDEX {index_name} ON {table} ({column})"
                )
            except Exception:
                pass  # 并发/重放场景下索引已存在，幂等跳过


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column in _TARGETS:
        if table not in tables:
            continue
        index_name = f"ft_{table}_{column}"
        if not _index_exists(bind, table, index_name):
            continue
        try:
            op.execute(f"DROP INDEX {index_name} ON {table}")
        except Exception:
            pass
