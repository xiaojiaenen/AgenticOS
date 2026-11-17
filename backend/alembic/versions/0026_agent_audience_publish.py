"""智能体启用范围三态 + 文件型作品发布表

Revision ID: 0026_agent_audience_publish
Revises: 0025_short_links
Create Date: 2026-11-20

## 变更

``agent_profiles`` 新增：

- ``audience_mode`` 三态授权：``all``（全体）/ ``selected``（仅名单内用户）/
  ``none``（暂不开放给任何人）。原先"名单为空 = 全体"的隐式约定无法表达
  "先不让任何人使用"，只能靠 listed=False 那种容易被绕过的方式近似。

新增表 ``published_items``：作品库里 PPT / 文档 / 表格等**文件型**产物的
发布记录（网站走 ``website_deploys``，两者发布语义不同，分表存）。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_agent_audience_publish"
down_revision: Union[str, None] = "0025_short_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(bind, table: str, column: str) -> bool:
    try:
        return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:  # noqa: BLE001
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── agent_profiles.audience_mode ──
    if inspector.has_table("agent_profiles") and not _has_column(bind, "agent_profiles", "audience_mode"):
        op.add_column(
            "agent_profiles",
            sa.Column("audience_mode", sa.String(16), nullable=True, server_default="all"),
        )
        op.create_index(
            "ix_agent_profiles_audience_mode", "agent_profiles", ["audience_mode"], unique=False
        )
        # 历史数据统一回填成 all：老语义是"名单为空 = 全体"，等价于 all。
        try:
            bind.execute(
                sa.text("UPDATE agent_profiles SET audience_mode = 'all' WHERE audience_mode IS NULL")
            )
        except Exception:  # noqa: BLE001
            pass

    # ── agent_profile_audiences（此前只有 create_all 建表，没有迁移）──
    if not inspector.has_table("agent_profile_audiences"):
        op.create_table(
            "agent_profile_audiences",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["profile_id"], ["agent_profiles.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("profile_id", "user_id", name="uq_agent_profile_audience"),
        )
        op.create_index(
            "ix_agent_profile_audiences_profile_id",
            "agent_profile_audiences",
            ["profile_id"],
            unique=False,
        )
        op.create_index(
            "ix_agent_profile_audiences_user_id",
            "agent_profile_audiences",
            ["user_id"],
            unique=False,
        )

    # ── published_items ──
    if not inspector.has_table("published_items"):
        op.create_table(
            "published_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("session_id", sa.String(128), nullable=False),
            sa.Column("source_ref", sa.String(160), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("visibility", sa.String(16), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("short_code", sa.String(16), nullable=False),
            sa.Column("file_path", sa.String(300), nullable=False),
            sa.Column("cover_path", sa.String(300), nullable=True),
            sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_viewed_at", sa.DateTime(), nullable=True),
            sa.Column("requested_by", sa.Integer(), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("kind", "session_id", "source_ref", "user_id", "visibility", "status",
                    "requested_by"):
            op.create_index(f"ix_published_items_{col}", "published_items", [col], unique=False)
        op.create_index(
            "ix_published_items_short_code", "published_items", ["short_code"], unique=True
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("published_items"):
        op.drop_table("published_items")

    if inspector.has_table("agent_profile_audiences"):
        op.drop_table("agent_profile_audiences")

    if inspector.has_table("agent_profiles") and _has_column(bind, "agent_profiles", "audience_mode"):
        try:
            op.drop_index("ix_agent_profiles_audience_mode", table_name="agent_profiles")
        except Exception:  # noqa: BLE001
            pass
        op.drop_column("agent_profiles", "audience_mode")
