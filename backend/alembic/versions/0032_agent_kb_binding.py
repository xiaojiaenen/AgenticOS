"""智能体绑定知识库白名单字段

Revision ID: 0032_agent_kb_binding
Revises: 0031_message_columns
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_agent_kb_binding"
down_revision: Union[str, None] = "0031_message_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    if table not in sa.inspect(bind).get_table_names():
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    # 新空库走 baseline + alembic 链，agent_profiles 由 0005 创建；
    # 已有库可能已含此列。两种都要幂等。
    cols = _columns("agent_profiles")
    if not cols:
        # 表尚未由迁移链创建（baseline 只建部分表）：跳过，启动时
        # Base.metadata.create_all() 会按当前模型建表（含此列）。
        return
    if "knowledge_base_ids_json" not in cols:
        op.add_column("agent_profiles", sa.Column("knowledge_base_ids_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if "knowledge_base_ids_json" in _columns("agent_profiles"):
        op.drop_column("agent_profiles", "knowledge_base_ids_json")
