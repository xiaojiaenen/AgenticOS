"""用户自建智能体：agent_profiles 增加 owner_id / visibility

Revision ID: 0005_user_owned_agents
Revises: 0004_indexes_and_cleanup
Create Date: 2026-10-02

背景
----
此前所有智能体（profile）都由管理员在后台创建，普通用户只能在"智能体商店"
里安装。本迁移让每个用户可以自建智能体、自选工具：

- ``owner_id``：NULL = 平台内置（任何角色都不可删改）；有值 = 该用户自建，
  仅本人与管理员可管理。存量数据保持 NULL，无需回填。
- ``visibility``：``private`` = 仅自己可用；``public`` = 可出现在商店供他人安装。

幂等：列已存在时跳过。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_user_owned_agents"
down_revision: Union[str, None] = "0004_indexes_and_cleanup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = (
    sa.Column("owner_id", sa.Integer(), nullable=True),
    sa.Column("visibility", sa.String(length=16), nullable=True),
)


def _table_exists(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    # 空库升级时表尚未由 create_all 建立，整段跳过（后续 baseline 会建全量 schema）
    if not _table_exists("agent_profiles"):
        return

    if not _has_column("agent_profiles", "owner_id"):
        op.add_column("agent_profiles", _COLUMNS[0])
    if not _has_column("agent_profiles", "visibility"):
        op.add_column("agent_profiles", _COLUMNS[1])
    op.execute("UPDATE agent_profiles SET visibility = 'private' WHERE visibility IS NULL")


def downgrade() -> None:
    if _has_column("agent_profiles", "visibility"):
        op.drop_column("agent_profiles", "visibility")
    if _has_column("agent_profiles", "owner_id"):
        op.drop_column("agent_profiles", "owner_id")