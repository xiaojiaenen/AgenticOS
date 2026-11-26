"""权限矩阵：角色自定义权限点 + 用户多角色关联表

Revision ID: 0029_permission_matrix
Revises: 0028_otel_spans

## 变更
- roles 表加 ``permissions_json``（角色自定义权限点；null = 用内置默认展开）
- 新增 ``user_roles`` 表（用户 ↔ 角色多对多，支持一个用户多个角色）

两条都做幂等守卫（已有库补迁移、全新库 create_all 已建好时跳过）。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_permission_matrix"
down_revision: Union[str, None] = "0028_otel_spans"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) roles.permissions_json
    if "roles" in insp.get_table_names() and "permissions_json" not in _columns("roles"):
        op.add_column("roles", sa.Column("permissions_json", sa.Text(), nullable=True))

    # 2) user_roles 表
    if "user_roles" not in insp.get_table_names():
        op.create_table(
            "user_roles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("role_slug", sa.String(length=64), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("user_id", "role_slug", name="uq_user_roles"),
        )


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "user_roles" in insp.get_table_names():
        op.drop_table("user_roles")
    if "roles" in insp.get_table_names() and "permissions_json" in _columns("roles"):
        op.drop_column("roles", "permissions_json")
