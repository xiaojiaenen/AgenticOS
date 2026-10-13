"""M6-C permissions, departments, roles and audit tables.

Revision ID: 0005_permissions_and_audit
Revises: 0004_composite_indexes
Create Date: 2026-09-30

Introduces the enterprise permission surface described in
``docs/m6-design.md`` section 4:

- ``departments``  department tree with a materialized ``path``
- ``roles``        custom (non-builtin) Casbin role metadata
- ``casbin_rule``  Casbin policy storage (v0..v5 / ptype layout)
- ``audit_logs``   audit trail with the two composite lookup indexes
- ``users.department_id`` FK back to the department tree

Behavior contract:
- Idempotent on both dialects. Every ``create_table`` is guarded by an
  inspector lookup, so the migration is a no-op on databases where
  ``create_all()`` already built the schema (the "new library" path
  covered by ``tests/test_alembic.py``).
- ``users.department_id`` is added separately, since SQLite cannot
  ``ALTER TABLE ... ADD COLUMN ... REFERENCES``; on SQLite the FK is
  declared at table-build time only and the column is skipped when it
  already exists.
- ``downgrade`` drops what this migration created and leaves
  pre-existing tables alone.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0005_permissions_and_audit"
down_revision: Union[str, None] = "0004_composite_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("casbin_rule", "ix_casbin_rule_ptype_v0_v1", ("ptype", "v0", "v1")),
    ("audit_logs", "ix_audit_logs_actor_created", ("actor_id", "created_at")),
    ("audit_logs", "ix_audit_logs_resource_created", ("resource_type", "resource_id", "created_at")),
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_exists(bind, table: str, index_name: str) -> bool:
    if bind.dialect.name == "mysql":
        row = bind.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() "
                "AND table_name = :table AND index_name = :index_name"
            ),
            {"table": table, "index_name": index_name},
        ).scalar()
        return bool(row)
    if bind.dialect.name == "sqlite":
        rows = bind.execute(
            text(f"PRAGMA index_list('{table}')"),  # noqa: S608 -- table from a constant tuple
        ).fetchall()
        return any(len(row) > 1 and str(row[1]) == index_name for row in rows)
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table))


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(col.get("name") == column for col in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()

    if "departments" not in tables:
        op.create_table(
            "departments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("path", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("ldap_dn", sa.String(length=512), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["departments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if "roles" not in tables:
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug", name="uq_roles_slug"),
        )
    if "casbin_rule" not in tables:
        op.create_table(
            "casbin_rule",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ptype", sa.String(length=16), nullable=False),
            sa.Column("v0", sa.String(length=256), nullable=True),
            sa.Column("v1", sa.String(length=256), nullable=True),
            sa.Column("v2", sa.String(length=256), nullable=True),
            sa.Column("v3", sa.String(length=256), nullable=True),
            sa.Column("v4", sa.String(length=256), nullable=True),
            sa.Column("v5", sa.String(length=256), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if "audit_logs" not in tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("resource_type", sa.String(length=64), nullable=True),
            sa.Column("resource_id", sa.String(length=64), nullable=True),
            sa.Column("result", sa.String(length=16), nullable=False, server_default="allow"),
            sa.Column("ip", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=512), nullable=True),
            sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    # Composite indexes (declared on the model too, so create_all builds them).
    for table, index_name, columns in _INDEXES:
        if table not in _table_names():
            continue
        if _index_exists(bind, table, index_name):
            continue
        op.create_index(index_name, table, list(columns), unique=False)

    # users.department_id — SQLite cannot add a column with a REFERENCES
    # clause, so the FK is only declared where ALTER TABLE supports it;
    # fresh SQLite databases already get it from create_table above.
    if "users" in _table_names() and not _column_exists(bind, "users", "department_id"):
        dialect = bind.dialect.name
        if dialect == "sqlite":
            op.execute(text("ALTER TABLE users ADD COLUMN department_id INTEGER"))
        else:
            op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
            op.create_foreign_key("fk_users_department_id", "users", "departments", ["department_id"], ["id"])
        op.create_index("ix_users_department_id", "users", ["department_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    for table, index_name, _columns in _INDEXES:
        if table in _table_names() and _index_exists(bind, table, index_name):
            op.drop_index(index_name, table_name=table)

    if "users" in _table_names() and _column_exists(bind, "users", "department_id"):
        # The FK constraint only exists on dialects that allowed ALTER ADD COLUMN.
        if bind.dialect.name != "sqlite":
            try:
                op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
            except Exception:  # noqa: BLE001 - constraint may already be gone
                pass
        if _index_exists(bind, "users", "ix_users_department_id"):
            op.drop_index("ix_users_department_id", table_name="users")
        with op.batch_alter_table("users") as batch:
            batch.drop_column("department_id")

    for table in ("audit_logs", "casbin_rule", "roles", "departments"):
        if table in _table_names():
            op.drop_table(table)
