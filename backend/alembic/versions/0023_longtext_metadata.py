"""MySQL：metadata_json 等长文本列升级为 LONGTEXT（修 1406 Data too long）

Revision ID: 0023_longtext_metadata
Revises: 0022_agent_profile_customized_at
Create Date: 2026-11-10

## 问题

生产 MySQL 上 ``agent_sessions.metadata_json`` 是 ``TEXT``（64KB 上限），
而它存的是 ``session.metadata`` 的完整 JSON —— 其中 ``action_log`` 会随
会话长度**线性增长**（每步工具调用追加一条记录）。实测某会话已达
59 KB，再聊几轮就撞顶：

    pymysql.err.DataError: (1406, "Data too long for column 'metadata_json' at row 1")

后果不是「元数据没存上」这么轻：``save_meta`` 与 ``_persist_session_messages``
在同一个 ``finally`` 里顺序执行，前者抛错会让后者**整轮不执行** ——
用户看到的是「模型说了话但界面没内容」，刷新后只剩思考（思考挂在更早的
消息上，已落库），工具链也断在中间。表现和「模型没回复」几乎一样，
极难定位。

## 修法

把这类「存 JSON / 存大文本」的列统一拉到 ``LONGTEXT``（4GB）。与
``0002_mysql_longtext`` 同一思路，只是覆盖后来新增的列：

- 仅在 MySQL 方言执行；SQLite 的 TEXT 无长度上限，直接跳过
- 表/列不存在、或类型已是 LONGTEXT 时幂等跳过
- downgrade 不回缩（数据可能已超 TEXT 容量）

## 顺带覆盖的列

除了 ``agent_sessions.metadata_json``，同类风险列一并拉长 —— 它们的
增长模式相同（存 JSON、存渲染产物），只是还没撞顶：

- ``workflow_runs.*_json`` / ``agent_run_traces.*_json``
- ``skills.trigger_patterns_json`` / ``validation_rules_json``
- ``agent_profile_versions.config_json``
- ``llm_providers.extra_json`` / ``llm_provider_chat_models.extra_json``

**注意**：新库请在 ``create_all`` 建表后执行 ``alembic upgrade head``
（而非 stamp），否则本迁移不会生效。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_longtext_metadata"
down_revision: Union[str, None] = "0022_agent_profile_customized_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (表, 列)：所有「存 JSON / 大文本、会随使用增长」的列。
# 顺序无所谓，缺表缺列都会跳过。
_TARGETS: tuple[tuple[str, str], ...] = (
    # 直接导致本次故障
    ("agent_sessions", "metadata_json"),
    # 同类风险：存 JSON 且随会话增长
    ("workflow_runs", "node_status_json"),
    ("workflow_runs", "outputs_json"),
    ("workflow_runs", "waiting_fields_json"),
    ("agent_run_traces", "steps_json"),
    ("agent_run_traces", "metadata_json"),
    ("skills", "trigger_patterns_json"),
    ("skills", "validation_rules_json"),
    ("agent_profile_versions", "config_json"),
    ("llm_providers", "extra_json"),
    ("llm_provider_chat_models", "extra_json"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return  # SQLite 的 TEXT 无长度上限

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    changed: list[str] = []
    for table, column in _TARGETS:
        if table not in tables:
            continue
        col = next((c for c in inspector.get_columns(table) if c["name"] == column), None)
        if col is None:
            continue
        type_str = str(col["type"]).upper()
        # 已是 LONGTEXT / MEDIUMTEXT 就不动；只有纯 TEXT 需要拉长
        if "TEXT" in type_str and "LONG" not in type_str and "MEDIUM" not in type_str:
            op.execute(f"ALTER TABLE {table} MODIFY COLUMN {column} LONGTEXT")
            changed.append(f"{table}.{column}")

    if changed:
        print(f"[0023] 已升级为 LONGTEXT: {', '.join(changed)}")


def downgrade() -> None:
    # 不回缩：存量数据可能已超过 TEXT 64KB 容量，回缩会直接截断或报错
    pass
