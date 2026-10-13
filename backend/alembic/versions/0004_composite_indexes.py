"""M6-A3 composite indexes for the dashboard and conversation hot paths.

Revision ID: 0004_composite_indexes
Revises: 0003_kb_fulltext_ngram
Create Date: 2026-09-30

Adds four composite indexes that match the real query shapes in
``app/api/v1/endpoints/dashboard.py`` and the conversation history readers:

- ``agent_usage_events(user_id, created_at)``  -- per-user aggregation + time window scan
- ``agent_usage_events(session_id, created_at)`` -- per-session aggregation + time window scan
- ``agent_messages(session_id, id)``          -- history paging ordered by id
- ``agent_sessions(user_id, updated_at)``      -- session list ordered by updated_at

Alembic autogenerate never emits composite indexes, so the declarations were
added by hand to ``app/db/models.py`` as well (``__table_args__``) to keep the
model metadata in sync with the database.

Behavior contract:
- Idempotent on both dialects. MySQL checks ``information_schema.statistics``,
  SQLite checks ``PRAGMA index_list``; existing indexes are skipped.
- Missing tables are skipped, so the migration also runs on partially created
  databases without failing.
- ``downgrade`` drops the indexes it created and leaves tables/data alone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0004_composite_indexes"
down_revision: Union[str, None] = "0003_kb_fulltext_ngram"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, index_name, columns)
_TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("agent_usage_events", "ix_agent_usage_events_user_created", ("user_id", "created_at")),
    ("agent_usage_events", "ix_agent_usage_events_session_created", ("session_id", "created_at")),
    ("agent_messages", "ix_agent_messages_session_ord", ("session_id", "id")),
    ("agent_sessions", "ix_agent_sessions_user_updated", ("user_id", "updated_at")),
)


def _mysql_index_exists(bind, table: str, index_name: str) -> bool:
    row = bind.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = :table AND index_name = :index_name"
        ),
        {"table": table, "index_name": index_name},
    ).scalar()
    return bool(row)


def _sqlite_index_exists(bind, table: str, index_name: str) -> bool:
    rows = bind.execute(
        text(f"PRAGMA index_list('{table}')"),  # noqa: S608 -- table from a constant tuple
    ).fetchall()
    for row in rows:
        # PRAGMA index_list returns (seq, name, unique, origin, partial)
        if len(row) > 1 and str(row[1]) == index_name:
            return True
    return False


def _index_exists(bind, table: str, index_name: str) -> bool:
    if bind.dialect.name == "mysql":
        return _mysql_index_exists(bind, table, index_name)
    if bind.dialect.name == "sqlite":
        return _sqlite_index_exists(bind, table, index_name)
    # Unknown dialect: fall back to the SQLAlchemy inspector.
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    created: list[tuple[str, str]] = []
    for table, index_name, columns in _TARGETS:
        if table not in tables:
            continue
        if _index_exists(bind, table, index_name):
            continue
        op.create_index(index_name, table, list(columns), unique=False)
        created.append((table, index_name))
    for table, index_name in created:
        print(f"created index {index_name} on {table}")  # noqa: T201


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table, index_name, _columns in _TARGETS:
        if table not in tables:
            continue
        if not _index_exists(bind, table, index_name):
            continue
        op.drop_index(index_name, table_name=table)
