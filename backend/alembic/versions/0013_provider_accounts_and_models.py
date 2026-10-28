"""企业提供商支持多账号池 + 模型目录

两件事：

1. ``llm_provider_credentials`` 从「每个提供商一条」放开成「一个池」，
   并加选号所需的 ``priority`` / ``last_used_at`` / ``failure_count`` /
   ``disabled``。旧的 ``uq_llm_provider_credential`` 必须去掉，否则第二个
   账号插不进去。
2. 新增 ``llm_provider_chat_models``：把上游模型注册表（企业网关的
   ``/json/model-configs.json``、标准 OpenAI 的 ``/models``）落到本地，
   解决「模型 ID ≠ 请求体里的模型名」这类只能靠试错发现的问题。

SQLite 的限制：``UNIQUE`` 是表级约束，无法 ``DROP CONSTRAINT``，只能重建表。
MySQL 走正常的 drop index + add column。两条路径都在这里显式分开写，不做
「一种写法糊两边」的抽象 —— 这种迁移最怕的就是在某一种方言上静默半成功。

Revision ID: 0013_provider_accounts
Revises: 0012_llm_providers
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013_provider_accounts"
down_revision: Union[str, None] = "0012_llm_providers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "llm_provider_credentials"
_MODEL_TABLE = "llm_provider_chat_models"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    try:
        return {col["name"] for col in sa.inspect(op.get_bind()).get_columns(table)}
    except Exception:  # noqa: BLE001 —— 表不存在时按空集处理
        return set()


def _credential_columns() -> list[sa.Column]:
    """新结构的完整列定义（SQLite 重建时直接复用）。"""
    return [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("cookie_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("login_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("auto_refresh", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expire_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _rebuild_credentials_sqlite() -> None:
    """SQLite 去掉 ``UNIQUE(provider_id)`` 的唯一途径：建新表搬数据。

    旧数据全部保留 —— 只是把一个「只能有一条」的约束放开，不改变任何语义。
    新列给默认值，其中 priority=100 与模型默认值一致，老账号自然落在主力档。
    """
    op.execute(f"ALTER TABLE {_TABLE} RENAME TO {_TABLE}_legacy")
    op.create_table(
        _TABLE,
        *_credential_columns(),
        sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        f"""
        INSERT INTO {_TABLE} (
            id, provider_id, label, username, password_encrypted, cookie_encrypted,
            login_url, status, auto_refresh, expire_at, last_login_at, last_error,
            priority, last_used_at, failure_count, disabled, updated_at
        )
        SELECT
            id, provider_id, '', username, password_encrypted, cookie_encrypted,
            login_url, status, auto_refresh, expire_at, last_login_at, last_error,
            100, NULL, 0, 0, updated_at
        FROM {_TABLE}_legacy
        """
    )
    op.execute(f"DROP TABLE {_TABLE}_legacy")
    op.create_index("ix_llm_provider_credentials_provider_id", _TABLE, ["provider_id"])
    op.create_index("ix_llm_provider_credentials_status", _TABLE, ["status"])
    op.create_index("ix_llm_provider_credentials_priority", _TABLE, ["priority"])
    op.create_index("ix_llm_provider_credentials_disabled", _TABLE, ["disabled"])
    op.create_index("ix_llm_provider_cred_provider_status", _TABLE, ["provider_id", "status"])


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _has_table(_TABLE):
        # 全新部署：create_all 还没跑，直接按新结构建
        op.create_table(
            _TABLE,
            *_credential_columns(),
            sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_llm_provider_credentials_provider_id", _TABLE, ["provider_id"])
        op.create_index("ix_llm_provider_credentials_status", _TABLE, ["status"])
        op.create_index("ix_llm_provider_credentials_priority", _TABLE, ["priority"])
        op.create_index("ix_llm_provider_credentials_disabled", _TABLE, ["disabled"])
        op.create_index("ix_llm_provider_cred_provider_status", _TABLE, ["provider_id", "status"])
    else:
        existing = _columns(_TABLE)
        needs_new_columns = "priority" not in existing

        if dialect == "sqlite":
            # 只有旧结构（还带着 UNIQUE 约束）时才需要重建
            if "label" not in existing:
                _rebuild_credentials_sqlite()
            elif needs_new_columns:
                with op.batch_alter_table(_TABLE) as batch:
                    batch.add_column(sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
                    batch.add_column(sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
                    batch.add_column(sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
                    batch.add_column(sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        else:
            # MySQL：约束名即索引名，可以直接删
            try:
                op.drop_constraint("uq_llm_provider_credential", _TABLE, type_="unique")
            except Exception:  # noqa: BLE001 —— 已经删过或从没建过，都不是错误
                pass

            if "label" not in existing:
                op.add_column(_TABLE, sa.Column("label", sa.String(length=64), nullable=False, server_default=""))
            if needs_new_columns:
                op.add_column(_TABLE, sa.Column("priority", sa.Integer(), nullable=False, server_default="100"))
                op.add_column(_TABLE, sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
                op.add_column(_TABLE, sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
                op.add_column(_TABLE, sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()))

        # 复合索引服务「按 provider + status 捞候选账号」，是选号热路径
        try:
            op.create_index("ix_llm_provider_cred_provider_status", _TABLE, ["provider_id", "status"])
        except Exception:  # noqa: BLE001
            pass

    if not _has_table(_MODEL_TABLE):
        op.create_table(
            _MODEL_TABLE,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("provider_id", sa.Integer(), nullable=False),
            sa.Column("model_key", sa.String(length=128), nullable=False),
            sa.Column("model_name", sa.String(length=128), nullable=False),
            sa.Column("task_type", sa.String(length=48), nullable=False, server_default=""),
            sa.Column("max_tokens", sa.Integer(), nullable=True),
            sa.Column("extra_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["provider_id"], ["llm_providers.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("provider_id", "model_key", name="uq_llm_provider_model_key"),
        )
        op.create_index("ix_llm_provider_chat_models_provider_id", _MODEL_TABLE, ["provider_id"])
        op.create_index("ix_llm_provider_chat_models_task_type", _MODEL_TABLE, ["task_type"])
        op.create_index("ix_llm_provider_chat_models_enabled", _MODEL_TABLE, ["enabled"])


def downgrade() -> None:
    if _has_table(_MODEL_TABLE):
        op.drop_table(_MODEL_TABLE)

    # 回滚会丢掉「第二个及以后的账号」——这是放开约束的必然代价，
    # 保留 id 最小的那条以维持「单账号」语义，避免产生不可用的孤儿凭据。
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            f"DELETE FROM {_TABLE} WHERE id NOT IN "
            f"(SELECT MIN(id) FROM {_TABLE} GROUP BY provider_id)"
        )
