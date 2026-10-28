"""下线部门体系：删除 departments 表、users.department_id 与相关角色绑定

Revision ID: 0010_drop_departments
Revises: 0009_remove_upstream
Create Date: 2026-10-27

背景
----
产品侧确认不再需要「部门」这一层：授权模型收敛为「用户 → 角色 → Casbin 策略」。
本迁移做三件事：

1. 清掉 ``casbin_rule`` 里与部门相关的规则（``dept_admin`` 角色、``dept:<id>`` 域），
   否则存量策略会在新代码里变成永不命中的死规则；
2. 删除 ``users.department_id``（含 FK 与索引）；
3. 删除 ``departments`` 表。

**这是不可逆的数据删除**：部门树、成员归属、部门管理员绑定都会永久丢失。
``downgrade`` 只能重建空表与空列，不恢复数据 —— 需要回滚请用迁移前的备份。

SQLite 兼容：``users.department_id`` 带外键，SQLite 不支持直接 DROP COLUMN，
统一走 ``batch_alter_table``（重建表副本再换名）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_drop_departments"
down_revision: Union[str, None] = "0009_remove_upstream"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_department_rules() -> None:
    """清理部门域与 dept_admin 角色相关策略。

    ``casbin_rule`` 列语义：v0=sub、v1=obj（g 规则里是角色）、v2=dom。
    用 ``inspect`` 判断表是否存在，避免在从未初始化 Casbin 的库上失败。
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "casbin_rule" not in inspector.get_table_names():
        return

    op.execute(
        sa.text(
            "DELETE FROM casbin_rule "
            "WHERE ptype = 'g' AND (v1 = 'dept_admin' OR v2 LIKE 'dept:%')"
        )
    )
    op.execute(
        sa.text("DELETE FROM casbin_rule WHERE ptype = 'p' AND v0 = 'dept_admin'")
    )

    # 内置角色行也一并清掉，否则角色列表里会留一个永远没有策略、也没人能绑的空壳
    if "roles" in inspector.get_table_names():
        op.execute(sa.text("DELETE FROM roles WHERE slug = 'dept_admin'"))


def upgrade() -> None:
    _drop_department_rules()

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "department_id" in columns:
            # SQLite 的 batch 模式会重建整张表并按反射结果重建索引：
            # 若先删列再建索引，就会生成 `CREATE INDEX ... (department_id)`
            # 这种引用已删列的语句而整体失败。索引必须在删列前显式清掉。
            index_names = {idx.get("name") for idx in inspector.get_indexes("users")}
            if "ix_users_department_id" in index_names:
                op.drop_index("ix_users_department_id", table_name="users")
            with op.batch_alter_table("users") as batch_op:
                batch_op.drop_column("department_id")

    if "departments" in tables:
        op.drop_table("departments")


def downgrade() -> None:
    """重建空表与空列（仅保证 schema 可回退，不恢复任何数据）。"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "departments" not in tables:
        op.create_table(
            "departments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("path", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("ldap_dn", sa.String(length=512), nullable=True),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["parent_id"], ["departments.id"]),
        )
        op.create_index("ix_departments_name", "departments", ["name"])
        op.create_index("ix_departments_parent_id", "departments", ["parent_id"])
        op.create_index("ix_departments_path", "departments", ["path"])
        op.create_index("ix_departments_ldap_dn", "departments", ["ldap_dn"])
        op.create_index("ix_departments_is_active", "departments", ["is_active"])

    if "users" in tables:
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "department_id" not in columns:
            with op.batch_alter_table("users") as batch_op:
                batch_op.add_column(sa.Column("department_id", sa.Integer(), nullable=True))
                batch_op.create_index("ix_users_department_id", ["department_id"])
