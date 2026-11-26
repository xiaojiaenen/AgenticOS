"""删除知识库的 team 共享字段（组织模型下线，team 共享从未落地）

Revision ID: 0030_drop_kb_team
Revises: 0029_permission_matrix

## 变更
- knowledge_bases 表删除 ``team_id`` 列
- scope 的历史值 'team' 归并为 'org'（公开可见），不再有团队作用域

SQLite 需 batch_alter_table 重建表；PG/MySQL 直接 drop column。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030_drop_kb_team"
down_revision: Union[str, None] = "0029_permission_matrix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "knowledge_bases" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("knowledge_bases")}
    if "team_id" not in cols:
        return

    # 历史 team 值归并为 org（公开可见），避免删列后遗留语义不明的值
    op.execute(
        sa.text("UPDATE knowledge_bases SET scope = 'org' WHERE scope = 'team'")
    )

    if bind.dialect.name == "sqlite":
        # 先显式删索引：batch_alter_table 重建时会尝试为旧索引建模，
        # 而 team_id 列已被 drop，导致 CREATE INDEX ... team_id 失败。
        try:
            op.drop_index("ix_knowledge_bases_team_id", table_name="knowledge_bases")
        except Exception:  # noqa: BLE001 - 索引可能不存在
            pass
        with op.batch_alter_table("knowledge_bases") as batch:
            batch.drop_column("team_id")
    else:
        op.drop_index("ix_knowledge_bases_team_id", table_name="knowledge_bases")
        op.drop_column("knowledge_bases", "team_id")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "knowledge_bases" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("knowledge_bases")}
    if "team_id" in cols:
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("knowledge_bases") as batch:
            batch.add_column(sa.Column("team_id", sa.Integer(), nullable=True))
    else:
        op.add_column("knowledge_bases", sa.Column("team_id", sa.Integer(), nullable=True))
