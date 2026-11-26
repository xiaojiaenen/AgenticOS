"""MySQL：agent_messages 结构化列升级为 LONGTEXT

Revision ID: 0033_message_columns_longtext
Revises: 0032_agent_kb_binding

## 问题

0031 给 ``agent_messages`` 加的结构化列用的是 ``sa.Text()`` —— MySQL 下是
``TEXT``（64KB 上限）。但 ``models.py`` 里同一批列声明的是
``Text().with_variant(LONGTEXT, "mysql")``：

- content_text / content_parts_json / tool_calls_json / reasoning_text /
  metadata_json / message_json

生产存量库走 0031 加列（TEXT），0023 的 longtext 清单创建时间早于 0031，
不含这些新列，于是这些列一直停在 64KB。工具结果 / SVG 片段很容易超，
一旦超长 ``pymysql.err.DataError: (1406, Data too long ...)`` 会让
``_persist_session_messages`` 整批回滚 —— 用户看到"模型说了话但界面没内容"。

## 修法

与 0002 / 0023 同一思路：仅在 MySQL 方言执行；表/列不存在或已是
LONGTEXT/MEDIUMTEXT 时幂等跳过；downgrade 不回缩（存量数据可能已超 64KB）。

新库：create_all 已按模型建成 LONGTEXT，本迁移全部跳过；
存量库：补一次 ALTER TABLE ... MODIFY COLUMN ... LONGTEXT。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033_message_columns_longtext"
down_revision: Union[str, None] = "0032_agent_kb_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 与 models.py 里 with_variant(LONGTEXT, "mysql") 的列保持同步。
# message_json 由 0002 已升级，这里再列一次是无害的幂等保险。
_TARGETS: tuple[tuple[str, str], ...] = (
    ("agent_messages", "content_text"),
    ("agent_messages", "content_parts_json"),
    ("agent_messages", "tool_calls_json"),
    ("agent_messages", "reasoning_text"),
    ("agent_messages", "metadata_json"),
    ("agent_messages", "message_json"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 的 TEXT 无长度上限，无需处理

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "agent_messages" not in tables:
        return
    columns = {c["name"]: c for c in inspector.get_columns("agent_messages")}
    for _table, column in _TARGETS:
        col = columns.get(column)
        if col is None:
            continue
        type_str = str(col["type"]).upper()
        if "TEXT" in type_str and "LONG" not in type_str and "MEDIUM" not in type_str:
            op.execute(f"ALTER TABLE agent_messages MODIFY COLUMN {column} LONGTEXT")


def downgrade() -> None:
    # 不回缩：存量数据可能已超过 TEXT 64KB 容量，回缩会截断或报错
    pass
