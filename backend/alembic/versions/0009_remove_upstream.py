"""移除企业上游功能：删除上游凭据表，upstream_api_keys 更名为 api_keys

企业上游（agents.gree.com Cookie 自动登录/透传）已整体移除。
API Key 网关（/v1/*，sk-agenticos-*）保留，仅去掉 upstream 命名：
``upstream_api_keys`` → ``api_keys``，模型由 ``UpstreamApiKeyModel``
改名为 ``ApiKeyModel``。

注意启动顺序：``init_db()`` 先按新 metadata 执行 ``create_all``（会建好
空的 ``api_keys``），随后才跑 ``alembic upgrade``。因此本迁移对
「新旧表并存」的库采用**搬迁数据**而非直接 rename。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_remove_upstream"
down_revision: Union[str, None] = "872c79f747bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_RENAMES = (
    # (旧索引名, 新索引名, 列定义)
    ("ix_upstream_api_keys_user_id", "ix_api_keys_user_id", "user_id"),
    ("ix_upstream_api_keys_prefix", "ix_api_keys_prefix", "prefix"),
    ("ix_upstream_api_keys_key_hash", "ix_api_keys_key_hash", "key_hash"),
)

_COLUMNS = "id, user_id, name, prefix, key_hash, enabled, last_used_at, created_at, updated_at"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1. 上游凭据表（用户名/密码/Cookie）随功能一并删除，避免敏感数据残留
    op.execute("DROP TABLE IF EXISTS upstream_credentials")

    # 2. upstream_api_keys → api_keys
    if not _has_table("upstream_api_keys"):
        return

    if _has_table("api_keys"):
        # create_all 已按新 metadata 建好空表：搬迁存量数据后删除旧表
        ignore = "OR IGNORE" if dialect == "sqlite" else "IGNORE"
        op.execute(
            f"INSERT {ignore} INTO api_keys ({_COLUMNS}) "
            f"SELECT {_COLUMNS} FROM upstream_api_keys"
        )
        op.execute("DROP TABLE IF EXISTS upstream_api_keys")
    else:
        op.rename_table("upstream_api_keys", "api_keys")
        _rename_indexes("api_keys")


def _rename_indexes(table: str) -> None:
    """把 ix_upstream_api_keys_* 索引改名为 ix_api_keys_*（best-effort）。

    SQLite 不支持 ALTER INDEX RENAME，只能 DROP + CREATE；
    MySQL 用 ALTER TABLE ... RENAME INDEX。索引缺失（历史库结构差异）时跳过。
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    for old, new, column in _INDEX_RENAMES:
        try:
            if dialect == "sqlite":
                op.execute(f"DROP INDEX IF EXISTS {old}")
                op.execute(f"CREATE INDEX IF NOT EXISTS {new} ON {table}({column})")
            elif dialect == "mysql":
                bind.execute(sa.text(f"ALTER TABLE {table} RENAME INDEX {old} TO {new}"))
        except Exception:  # noqa: BLE001 -- 索引不存在时保持库可用
            pass


def downgrade() -> None:
    """回滚：重建 upstream_api_keys 并迁回数据（upstream_credentials 不恢复）。"""
    bind = op.get_bind()
    dialect = bind.dialect.name

    if not _has_table("api_keys"):
        return

    if _has_table("upstream_api_keys"):
        ignore = "OR IGNORE" if dialect == "sqlite" else "IGNORE"
        op.execute(
            f"INSERT {ignore} INTO upstream_api_keys ({_COLUMNS}) "
            f"SELECT {_COLUMNS} FROM api_keys"
        )
        op.execute("DROP TABLE IF EXISTS api_keys")
    else:
        op.rename_table("api_keys", "upstream_api_keys")
        for new, old, column in _INDEX_RENAMES:
            try:
                if dialect == "sqlite":
                    op.execute(f"DROP INDEX IF EXISTS {new}")
                    op.execute(f"CREATE INDEX IF NOT EXISTS {old} ON upstream_api_keys({column})")
                elif dialect == "mysql":
                    bind.execute(sa.text(f"ALTER TABLE upstream_api_keys RENAME INDEX {new} TO {old}"))
            except Exception:  # noqa: BLE001
                pass
