"""作品库：网站部署可见性（public/private）+ 私密访问令牌（0018）。

产品语义：
- ``public``  → 审批通过后发布到 nginx /sites/{slug}/，作品库所有人可见；
- ``private`` → 仅部署者（和管理员）在作品库可见，访问走后端带签名的
  私有端点（deploy 时签发 30 天令牌，存库，可随时重置）——
  **绝不落到公开的 /sites/ 路径**，否则「私密」形同虚设。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_website_gallery_visibility"
down_revision: Union[str, None] = "0017_llmops_traces_publish_evals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    # 表不存在时返回 True（而不是 False）：空 SQLite 基线上
    # website_deploys 可能还没建（由 ORM create_all 负责），此时
    # 跳过整个迁移比炸掉强 —— 0017 同款守卫。
    if not _has_table(table):
        return True
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    table = "website_deploys"
    if not _has_table(table):
        return
    if not _has_column(table, "visibility"):
        # 私有默认：已存在的历史部署不加声明就当私密处理，避免「升级后
        # 原本没打算公开的网站突然出现在公开作品库里」。
        op.add_column(
            table,
            sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
        )
    if not _has_column(table, "access_token"):
        # 私密站点的访问令牌（部署完成时签发的 30 天 JWT，可重置）
        op.add_column(
            table,
            sa.Column("access_token", sa.String(length=512), nullable=True),
        )
    if _has_table(table) and not any(
        ix["name"] == "ix_website_deploys_visibility"
        for ix in sa.inspect(op.get_bind()).get_indexes(table)
    ):
        op.create_index("ix_website_deploys_visibility", table, ["visibility"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(table):
        indexes = [ix["name"] for ix in inspector.get_indexes(table)]
        if "ix_website_deploys_visibility" in indexes:
            op.drop_index("ix_website_deploys_visibility", table_name=table)
        columns = [c["name"] for c in inspector.get_columns(table)]
        if "access_token" in columns:
            op.drop_column(table, "access_token")
        if "visibility" in columns:
            op.drop_column(table, "visibility")
