"""AI 提供商：llm_providers 与 llm_provider_credentials

把「用哪个大模型后端」从环境变量提升为可管理的实体。企业上游
（Cookie 认证）只是其中一种 ``provider_type``，不再是全局硬编码路径。

``llm_provider_credentials`` 是**系统级单账号**：提供商由管理员全局切换，
所以只需要一份登录态，不需要像旧 ``upstream_credentials`` 那样按用户存。

Revision ID: 0012_llm_providers
Revises: 0011_kb_chunks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_llm_providers"
down_revision: Union[str, None] = "0011_kb_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # create_all 可能已经按新 metadata 建好表（启动顺序：init_db → alembic），
    # 因此两个表都要做存在性判断，避免重复建表报错。
    if not _has_table("llm_providers"):
        op.create_table(
            "llm_providers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("provider_type", sa.String(length=32), nullable=False),
            sa.Column("base_url", sa.String(length=512), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("api_key_encrypted", sa.Text(), nullable=True),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False),
            sa.Column("max_tokens", sa.Integer(), nullable=True),
            sa.Column("extra_json", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_llm_provider_slug"),
        )
        op.create_index("ix_llm_providers_slug", "llm_providers", ["slug"])
        op.create_index("ix_llm_providers_provider_type", "llm_providers", ["provider_type"])
        op.create_index("ix_llm_providers_enabled", "llm_providers", ["enabled"])
        op.create_index("ix_llm_providers_is_default", "llm_providers", ["is_default"])

    if not _has_table("llm_provider_credentials"):
        op.create_table(
            "llm_provider_credentials",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("password_encrypted", sa.Text(), nullable=False),
            sa.Column("cookie_encrypted", sa.Text(), nullable=False),
            sa.Column("login_url", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("auto_refresh", sa.Boolean(), nullable=False),
            sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_id", name="uq_llm_provider_credential"),
        )
        op.create_index(
            "ix_llm_provider_credentials_provider_id",
            "llm_provider_credentials",
            ["provider_id"],
        )
        op.create_index("ix_llm_provider_credentials_status", "llm_provider_credentials", ["status"])


def downgrade() -> None:
    # 先删子表再删父表：MySQL 会校验外键
    op.drop_table("llm_provider_credentials")
    op.drop_table("llm_providers")
