"""OpenTelemetry span 落库表（战线 D：纯库埋点写自家 DB）

Revision ID: 0028_otel_spans
Revises: 0027_kb_postgres_trgm
Create Date: 2026-11-18

## 变更

新增表 ``otel_spans``：OpenTelemetry SDK 的 DBSpanExporter 批量写入
（纯库埋点，沿用现有 traces 展示，不接 Langfuse 等外部系统）。
create_all 已覆盖建表；本迁移让**已有库**也能补上（幂等：has_table 守卫）。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028_otel_spans"
down_revision: Union[str, None] = "0027_kb_postgres_trgm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("otel_spans"):
        return
    op.create_table(
        "otel_spans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(length=32), nullable=False, index=True),
        sa.Column("span_id", sa.String(length=16), nullable=False, unique=True),
        sa.Column("parent_span_id", sa.String(length=16), nullable=True, index=True),
        sa.Column("name", sa.String(length=200), nullable=False, index=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="internal"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unset"),
        sa.Column("attributes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("otel_spans"):
        op.drop_table("otel_spans")
