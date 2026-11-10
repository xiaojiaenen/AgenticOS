"""agent_profiles 增加 customized_at（内置智能体可被管理员改写）。

背景：内置智能体此前一律 403「不可修改」。放开编辑后必须解决一个隐患：
``ensure_defaults`` 每次启动都会把内置 profile 的 system_prompt / 工具开关
按代码里的 ``BUILTIN_AGENT_PROFILES`` 回写一遍，管理员刚改完就被覆盖。
``customized_at`` 非空即表示「这是人工配置，别再动」，一键还原时清空。

Revision ID: 0022_agent_profile_customized_at
Revises: 0021_website_gallery_columns
Create Date: 2026-11-09
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_agent_profile_customized_at"
down_revision: Union[str, None] = "0021_website_gallery_columns"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    try:
        return column in {col["name"] for col in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return False


def upgrade() -> None:
    # 幂等：内网出现过「stamp 到新 revision 但列没加上」的漂移，
    # 单独 ensure 一次比只依赖 alembic 版本号稳。
    if _has_column("agent_profiles", "customized_at"):
        return
    with op.batch_alter_table("agent_profiles") as batch:
        batch.add_column(sa.Column("customized_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if not _has_column("agent_profiles", "customized_at"):
        return
    with op.batch_alter_table("agent_profiles") as batch:
        batch.drop_column("customized_at")
