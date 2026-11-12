"""作品库增强：展示标题、封面截图、访问统计、来源会话归属

Revision ID: 0024_gallery_insights
Revises: 0023_longtext_metadata
Create Date: 2026-11-20

## 背景

作品库此前只有 ``project_slug``（工作区目录名 ``u<uid>_s<ts><rand>_v<n>``），
纯机器标识不可读；也没有封面、没有访问量。

## 变更

``website_deploys`` 新增：

- ``title``          展示名。部署时由用户填写，留空则由模型/会话标题派生
- ``cover_path``     封面截图相对路径（部署完成后 Playwright 异步截图 + 压缩）
- ``view_count``     累计访问次数（含直接访问、私密端点、作品库外链，
                     凡经过本平台站点的请求都计数）
- ``last_viewed_at`` 最近一次访问时间

新表 ``website_views``：访问明细（时间 / 来源 / UA / referer 域名），
用于后续按天聚合与「从哪里点进来的」分析。只存必要字段，不留 IP。

## 会话绑定

``website_deploys.session_id`` 早已存在（来源会话）。本次不新增列，
改为在删除会话时提示用户「网站将无法再通过对话更新」，由前端确认。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024_gallery_insights"
down_revision: Union[str, None] = "0023_longtext_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, column: str) -> bool:
    try:
        return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:  # noqa: BLE001 —— 表不存在
        return False


def upgrade() -> None:
    bind = op.get_bind()

    # 1) website_deploys 新列（幂等：create_all 可能已建好）
    if _has_table(bind, "website_deploys"):
        additions = [
            ("title", sa.String(200), True),
            ("cover_path", sa.String(512), True),
            ("view_count", sa.Integer(), False),
            ("last_viewed_at", sa.DateTime(), True),
        ]
        for name, type_, nullable in additions:
            if not _has_column(bind, "website_deploys", name):
                op.add_column(
                    "website_deploys",
                    sa.Column(name, type_, nullable=nullable, server_default=None if nullable else "0"),
                )

    # 2) 访问明细表
    if not _has_table(bind, "website_views"):
        op.create_table(
            "website_views",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("deploy_id", sa.Integer(), sa.ForeignKey("website_deploys.id"), index=True),
            sa.Column("project_slug", sa.String(128), index=True),
            # 访问来源：direct(直接打开) / gallery(作品库) / embed(嵌入) / api(接口)
            sa.Column("source", sa.String(32), server_default="direct"),
            sa.Column("referer_host", sa.String(255), nullable=True),
            sa.Column("user_agent", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), index=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "website_views"):
        op.drop_table("website_views")
    if _has_table(bind, "website_deploys"):
        for name in ("last_viewed_at", "view_count", "cover_path", "title"):
            if _has_column(bind, "website_deploys", name):
                op.drop_column("website_deploys", name)
