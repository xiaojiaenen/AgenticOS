"""作品短链、网站说明、取消部署状态

Revision ID: 0025_short_links
Revises: 0024_gallery_insights
Create Date: 2026-11-20

## 变更

``website_deploys`` 新增：

- ``short_code``   8 位短链码。对外地址 /s/<code>，不再暴露
  ``u<uid>_s<时间戳><随机>_v<n>`` 这类目录名。
- ``description``  网站说明，部署时用户填写，审批页展示给管理员。

新增状态值 ``cancelled``（用户取消部署，保留源码）与 ``superseded``
（已提交新版本，旧版下架等待重新审批）。两者都是字符串列，无需 DDL。

历史数据：为已有 deployed 记录补发短码（幂等：已有码的跳过）。
"""
from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_short_links"
down_revision: Union[str, None] = "0024_gallery_insights"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def _has_column(bind, table: str, column: str) -> bool:
    try:
        return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}
    except Exception:  # noqa: BLE001
        return False


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("website_deploys"):
        return

    if not _has_column(bind, "website_deploys", "short_code"):
        op.add_column("website_deploys", sa.Column("short_code", sa.String(16), nullable=True))
        op.create_index(
            "ix_website_deploys_short_code", "website_deploys", ["short_code"], unique=False
        )
    if not _has_column(bind, "website_deploys", "description"):
        op.add_column("website_deploys", sa.Column("description", sa.Text(), nullable=True))

    # 历史记录补短码：只对已上线且没有码的补
    try:
        rows = bind.execute(
            sa.text(
                "SELECT id FROM website_deploys "
                "WHERE short_code IS NULL AND status = 'deployed'"
            )
        ).fetchall()
        for (row_id,) in rows:
            code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
            bind.execute(
                sa.text("UPDATE website_deploys SET short_code = :c WHERE id = :i"),
                {"c": code, "i": row_id},
            )
    except Exception:  # noqa: BLE001 —— 补码失败不影响结构升级
        pass


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "website_deploys", "description"):
        op.drop_column("website_deploys", "description")
    if _has_column(bind, "website_deploys", "short_code"):
        try:
            op.drop_index("ix_website_deploys_short_code", table_name="website_deploys")
        except Exception:  # noqa: BLE001
            pass
        op.drop_column("website_deploys", "short_code")
