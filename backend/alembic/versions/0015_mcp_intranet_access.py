"""MCP 服务器接入增强：profile 级授权 + 内网连接选项

## 背景

MCP 服务器配置（``mcp_servers``）此前只有「连不连得上」这一层能力，
内网爬虫类服务要用它，缺三样东西：

1. **profile 级授权缺失**。``factory.py`` 里 MCP 工具是**无条件注册**到
   每一个 Agent 的注册表 —— 任何智能体都能调用任意 MCP 服务器的工具。
   外部系统有 ``agent_profile_external_systems`` 做这件事，MCP 没有，
   两套模型不一致。内网爬虫能访问内网站点，这种「全局可见」不可接受。
   → 新增 ``agent_profile_mcp_servers`` 关联表。

2. **自签证书无法放行**。MCP 官方 SDK 的 ``create_mcp_http_client()``
   只接受 headers / timeout / auth，**没有 verify 参数**；wuwei 的
   ``HTTPMCPClient`` 直接用它建客户端，没有替换点。内网服务普遍用自签
   CA，握手会直接失败。
   → 新增 ``verify_tls`` 列，平台侧自建 httpx 客户端（不改 site-packages）。

3. **出网地址不可控**。MCP 服务本身可能再去访问内网站点，这一跳的
   SSRF 风险在 MCP 服务侧、平台无法代管；但「平台连 MCP 服务」这一跳
   的地址是管理员配置的，需要可审计、可限制。
   → 新增 ``allowed_cidrs``（平台侧连接地址校验）与 ``user_accessible``
   （该服务是否允许被普通智能体使用）。

另加 ``external_system_id``：指向一个已配置的「集成」，用户的凭据从那里
取，在调用 MCP 工具时按 ``$CREDENTIAL.<字段>`` 注入（值不进模型上下文）。

## 幂等性（重要）

本迁移跑在三种库上：存量库（列不存在）、``create_all`` 建出来的新库
（列已存在）、以及被重跑过的库。因此**每一步都要先查存在性**，
不能无条件 ADD —— 否则 ``duplicate column name`` 直接中断升级。

参考 ``0014_usage_route_audit`` 的同一约定。

## SQLite 注意

SQLite **不支持** ``ALTER TABLE ... ADD CONSTRAINT``（alembic 抛
``NotImplementedError``），外键只能在建表时声明。故
``external_system_id`` 的外键用 ``batch_alter_table`` 重建表来加。

## 迁移策略

- 新列全部带 server_default，向后兼容既有行。
- ``verify_tls`` 默认 **True**（保持既有行为：默认校验证书）。
  只有管理员显式关掉才会放行自签证书 —— 默认放行是危险默认值。
- ``user_accessible`` 默认 **True**（保持既有行为：全局可见）。
  管理员可单独关掉某台内网服务。

Revision ID: 0015_mcp_intranet_access
Revises: 0014_usage_route_audit
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: Union[str, None] = "0015_mcp_intranet_access"
down_revision: Union[str, None] = "0014_usage_route_audit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "mcp_servers"
_PROFILE_TABLE = "agent_profile_mcp_servers"

# 新列：(列名, 列定义)
_COLUMNS: list[tuple[str, sa.Column]] = [
    ("verify_tls", sa.Column("verify_tls", sa.Boolean(), nullable=True, server_default=sa.text("1"))),
    ("allowed_cidrs", sa.Column("allowed_cidrs", sa.Text(), nullable=True, server_default="")),
    ("user_accessible", sa.Column("user_accessible", sa.Boolean(), nullable=True, server_default=sa.text("1"))),
    ("external_system_id", sa.Column("external_system_id", sa.Integer(), nullable=True)),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _TABLE in set(_inspector().get_table_names())


def _columns() -> set[str]:
    if not _has_table():
        return set()
    return {c["name"] for c in _inspector().get_columns(_TABLE)}


def _index_names() -> set[str]:
    if not _has_table():
        return set()
    return {idx["name"] for idx in _inspector().get_indexes(_TABLE) if idx.get("name")}


def _has_foreign_key(constraint_name: str) -> bool:
    if not _has_table():
        return False
    return any(
        fk.get("name") == constraint_name
        for fk in _inspector().get_foreign_keys(_TABLE)
    )


def upgrade() -> None:
    if not _has_table():
        # 全新库由 ``Base.metadata.create_all`` 建表（已含新列），无事可做。
        return

    existing_columns = _columns()
    existing_indexes = _index_names()

    # ── 纯新增列（无外键）──
    for name, column in _COLUMNS:
        if name == "external_system_id":
            continue
        if name in existing_columns:
            continue
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(column)

    # ── external_system_id（带外键，需 batch 重建）──
    if "external_system_id" not in existing_columns:
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(
                sa.Column("external_system_id", sa.Integer(), nullable=True)
            )
            batch.create_foreign_key(
                "fk_mcp_servers_external_system",
                "external_systems",
                ["external_system_id"],
                ["id"],
            )

    if "ix_mcp_servers_external_system_id" not in existing_indexes:
        op.create_index(
            "ix_mcp_servers_external_system_id", _TABLE, ["external_system_id"]
        )

    # ── profile 授权关联表 ──
    if _PROFILE_TABLE not in set(_inspector().get_table_names()):
        op.create_table(
            _PROFILE_TABLE,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("server_name", sa.String(length=120), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=True, server_default=sa.text("1")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["profile_id"], ["agent_profiles.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("profile_id", "server_name", name="uq_profile_mcp_server"),
        )
        op.create_index(
            "ix_agent_profile_mcp_servers_profile_id",
            _PROFILE_TABLE,
            ["profile_id"],
        )
        op.create_index(
            "ix_agent_profile_mcp_servers_server_name",
            _PROFILE_TABLE,
            ["server_name"],
        )


def downgrade() -> None:
    if _PROFILE_TABLE in set(_inspector().get_table_names()):
        op.drop_index(
            "ix_agent_profile_mcp_servers_server_name", table_name=_PROFILE_TABLE
        )
        op.drop_index(
            "ix_agent_profile_mcp_servers_profile_id", table_name=_PROFILE_TABLE
        )
        op.drop_table(_PROFILE_TABLE)

    if not _has_table():
        return

    existing_columns = _columns()
    existing_indexes = _index_names()

    if "ix_mcp_servers_external_system_id" in existing_indexes:
        op.drop_index("ix_mcp_servers_external_system_id", table_name=_TABLE)

    if "external_system_id" in existing_columns:
        with op.batch_alter_table(_TABLE) as batch:
            if _has_foreign_key("fk_mcp_servers_external_system"):
                batch.drop_constraint(
                    "fk_mcp_servers_external_system", type_="foreignkey"
                )
            batch.drop_column("external_system_id")

    for name in ("user_accessible", "allowed_cidrs", "verify_tls"):
        if name in existing_columns:
            with op.batch_alter_table(_TABLE) as batch:
                batch.drop_column(name)
