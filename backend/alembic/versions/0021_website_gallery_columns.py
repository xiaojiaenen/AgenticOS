"""确保 website_deploys 具备作品库所需列（0021）。

0018 已经加过 ``visibility`` / ``access_token``。但内网出现过「版本号已 stamped
到较新 revision、实际列却没加上」的 schema 漂移——只靠 0018 的守卫无法补回
（upgrade 不会重跑已标记执行的迁移）。本迁移独立地再做一次幂等 ensure：
无论当前 version 是 0017 还是被误 stamp 的 0018，upgrade 到 head 都会补齐缺失列。

同时把「启动时自动升级」接进 ``app.db.session.init_db``，从机制上消除
「代码加了字段、库没跑迁移」的漂移。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_website_gallery_columns"
down_revision: Union[str, None] = "0020_feedback_and_presence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "website_deploys"


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return True
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_table(_TABLE):
        return
    if not _has_column(_TABLE, "visibility"):
        op.add_column(
            _TABLE,
            sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
        )
    if not _has_column(_TABLE, "access_token"):
        op.add_column(_TABLE, sa.Column("access_token", sa.String(length=512), nullable=True))
    indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes(_TABLE)}
    if "ix_website_deploys_visibility" not in indexes:
        op.create_index("ix_website_deploys_visibility", _TABLE, ["visibility"])


def downgrade() -> None:
    # 这两列由 0018 负责新增；0021 只做补齐，回滚不删列（避免把 0018 的成果
    # 一并撤掉造成版本语义混乱）。
    return
