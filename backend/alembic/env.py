"""Alembic 迁移环境（TECH-DEBT-2026-09 引入）。

- target_metadata 接 ``app.db.models.Base.metadata``；
- 连接复用 ``app.db.session.engine``（与运行时同一 DATABASE_URL），
  也可在 alembic.ini 的 ``sqlalchemy.url`` 显式覆盖（优先级更高）。
"""

import os
import sys
from logging.config import fileConfig

from alembic import context

# 保证 `app` 可导入（alembic.ini 的 prepend_sys_path 之外的双保险，
# 兼容直接以 python -m alembic 从任意目录调用）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

from app.db.models import Base  # noqa: E402

target_metadata = Base.metadata


def _resolve_connectable():
    """返回用于迁移的引擎/连接。

    alembic.ini 的 sqlalchemy.url 非空时按它建独立引擎；
    否则复用应用运行时的 engine（同一 DATABASE_URL）。
    """
    url = config.get_main_option("sqlalchemy.url")
    if url:
        from sqlalchemy import create_engine

        return create_engine(url)
    from app.db.session import engine

    return engine


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (--sql)."""
    engine = _resolve_connectable()
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode（直连数据库）."""
    connectable = _resolve_connectable()

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
