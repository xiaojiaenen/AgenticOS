"""agent_messages 结构化列（阶段一）

Revision ID: 0031_message_columns
Revises: 0030_drop_kb_team

## 变更
- agent_messages 增加结构化列（message_id/role/content_text/...），
  message_json 保留做灰度回退；
- 存量 JSON 一次性回填到结构化列（幂等：只填结构化列为空的行）。
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_message_columns"
down_revision: Union[str, None] = "0030_drop_kb_team"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_COLUMNS = {
    "message_id": sa.String(64),
    "role": sa.String(16),
    "content_text": sa.Text(),
    "content_parts_json": sa.Text(),
    "tool_calls_json": sa.Text(),
    "tool_call_id": sa.String(64),
    "name": sa.String(128),
    "reasoning_text": sa.Text(),
    "metadata_json": sa.Text(),
    "status": sa.String(16),
}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_messages" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("agent_messages")}

    for name, typ in NEW_COLUMNS.items():
        if name not in existing:
            op.add_column("agent_messages", sa.Column(name, typ, nullable=True))

    if "message_id" not in existing:
        # 普通索引（非唯一）：去重靠应用层 session_storage.message_signature，
        # 不是靠 DB 唯一约束。不要把它改成 unique=True —— 存量重复数据 +
        # NULL 跨方言语义会让迁移失败。
        op.create_index("ix_agent_messages_message_id", "agent_messages", ["message_id"])
    for col in ("role", "tool_call_id"):
        if col not in existing:
            op.create_index(f"ix_agent_messages_{col}", "agent_messages", [col])

    # ── 存量回填 ──
    # 只处理结构化列还为空的行（幂等，可重跑）
    rows = bind.execute(
        sa.text("SELECT id, message_json FROM agent_messages WHERE role IS NULL AND message_json IS NOT NULL")
    ).fetchall()
    for row_id, raw in rows:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        def _dump(value):
            return json.dumps(value, ensure_ascii=False) if value else None
        bind.execute(
            sa.text("""
                UPDATE agent_messages SET
                  message_id=:mid, role=:role, content_text=:content,
                  content_parts_json=:parts, tool_calls_json=:tools,
                  tool_call_id=:tcid, name=:name, reasoning_text=:reason,
                  metadata_json=:meta, status=:status
                WHERE id=:id
            """),
            {
                "id": row_id,
                "mid": data.get("id"),
                "role": data.get("role"),
                "content": data.get("content") or "",
                "parts": _dump(data.get("content_parts")),
                "tools": _dump(data.get("tool_calls")),
                "tcid": data.get("tool_call_id"),
                "name": data.get("name"),
                "reason": data.get("reasoning_content") or None,
                "meta": _dump(data.get("metadata")),
                "status": data.get("status"),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "agent_messages" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("agent_messages")}
    for name in NEW_COLUMNS:
        if name in existing:
            op.drop_column("agent_messages", name)
    for idx in ("ix_agent_messages_message_id", "ix_agent_messages_role", "ix_agent_messages_tool_call_id"):
        try:
            op.drop_index(idx, table_name="agent_messages")
        except Exception:  # noqa: BLE001 - 索引可能不存在
            pass
