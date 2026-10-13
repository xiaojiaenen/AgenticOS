"""MCP 服务器配置表

Revision ID: 0006_mcp_servers
Revises: 0005_user_owned_agents
Create Date: 2026-10-02

MCP(Model Context Protocol)服务器配置持久化：管理员在后台维护
stdio / http / sse 三种传输方式的服务地址与鉴权头，MCP 工具以
``mcp__<server>__<tool>`` 命名进入 Agent 工具目录。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_mcp_servers"
down_revision: Union[str, None] = "0005_user_owned_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("mcp_servers"):
        return
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("transport", sa.String(length=16), nullable=False, server_default="http"),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("command", sa.String(length=256), nullable=True),
        sa.Column("args_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("env_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("headers_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("timeout", sa.Float(), nullable=False, server_default="60.0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_connected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_mcp_servers_name", "mcp_servers", ["name"], unique=True)
    op.create_index("ix_mcp_servers_transport", "mcp_servers", ["transport"])
    op.create_index("ix_mcp_servers_enabled", "mcp_servers", ["enabled"])


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("mcp_servers"):
        return
    op.drop_index("ix_mcp_servers_enabled", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_transport", table_name="mcp_servers")
    op.drop_index("ix_mcp_servers_name", table_name="mcp_servers")
    op.drop_table("mcp_servers")