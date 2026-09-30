"""mysql longtext: agent_messages.message_json / ppt_artifacts.deck_json,preview_html 升级为 LONGTEXT

Revision ID: 0002_mysql_longtext
Revises: baseline_20260930
Create Date: 2026-09-30

承接自已删除的 ``_ensure_compatible_schema()`` 中 create_all 不覆盖的行为：
MySQL 上 create_all 依据模型 Text 建的是 TEXT（64KB 上限），而工具返回数据
与 SVG deck 可能远超该上限；历史 compat 层在每次启动时用
``ALTER TABLE ... MODIFY COLUMN ... LONGTEXT`` 拉长。本迁移把该行为固化：

- 仅在 MySQL 方言执行；SQLite 开发库 TEXT 无长度上限，直接跳过；
- 表/列不存在或类型已是 LONGTEXT 时幂等跳过；
- downgrade 不回缩列类型（数据可能已超 TEXT 容量）。

注意：生产 MySQL 新库请在 create_all 建表后执行 ``alembic upgrade head``
（而非 stamp），确保本迁移实际生效；存量库此前已由 compat 层完成拉长，
``alembic stamp head`` 即可。详见 backend/alembic/README.md。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_mysql_longtext"
down_revision: Union[str, None] = "baseline_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 列)：与原 _ensure_compatible_schema 的 LONGTEXT 升级清单一致
_TARGETS: tuple[tuple[str, str], ...] = (
    ("agent_messages", "message_json"),
    ("ppt_artifacts", "deck_json"),
    ("ppt_artifacts", "preview_html"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 开发库 TEXT 无长度上限，无需处理

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, column in _TARGETS:
        if table not in tables:
            continue
        col = next((c for c in inspector.get_columns(table) if c["name"] == column), None)
        if col is None:
            continue
        type_str = str(col["type"]).upper()
        if "TEXT" in type_str and "LONG" not in type_str:
            op.execute(f"ALTER TABLE {table} MODIFY COLUMN {column} LONGTEXT")


def downgrade() -> None:
    # 不回缩列类型：存量数据可能已超过 TEXT 64KB 容量
    pass
