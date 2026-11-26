"""0033_message_columns_longtext 迁移回归。

要点：MySQL 方言下把 0031 新增的 6 个结构化列从 TEXT 拉到 LONGTEXT；
非 MySQL 跳过；已是 LONGTEXT/MEDIUMTEXT 或缺列时幂等跳过。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "0033_message_columns_longtext.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_test_0033_longtext", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(dialect: str, columns: dict[str, str]) -> list[str]:
    """在 mock 的 bind/inspector 上跑迁移，返回所有 op.execute 的 SQL。"""
    from alembic import op

    class FakeType:
        def __init__(self, label: str) -> None:
            self._label = label

        def __str__(self) -> str:
            return self._label

    bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["agent_messages"]
    inspector.get_columns.return_value = [
        {"name": name, "type": FakeType(typ)}
        for name, typ in columns.items()
    ]
    executed: list[str] = []

    with patch.object(op, "get_bind", return_value=bind), \
         patch("sqlalchemy.inspect", return_value=inspector), \
         patch.object(op, "execute", side_effect=lambda sql: executed.append(sql)):
        _load_migration().upgrade()
    return executed


def test_mysql_upgrades_all_text_columns_to_longtext():
    columns = {
        "content_text": "TEXT",
        "content_parts_json": "TEXT",
        "tool_calls_json": "TEXT",
        "reasoning_text": "TEXT",
        "metadata_json": "TEXT",
        "message_json": "TEXT",
    }
    executed = _run_upgrade("mysql", columns)
    assert len(executed) == 6
    for column in columns:
        assert any(
            f"MODIFY COLUMN {column} LONGTEXT" in sql for sql in executed
        ), f"{column} 未被拉长为 LONGTEXT"


def test_mysql_skips_longtext_mediumtext_and_missing_columns():
    columns = {
        "content_text": "LONGTEXT",           # 已是目标类型
        "content_parts_json": "MEDIUMTEXT",   # 更大，无需动
        "tool_calls_json": "TEXT",            # 仍需升级
        # reasoning_text / metadata_json 缺列 → 跳过
    }
    executed = _run_upgrade("mysql", columns)
    assert len(executed) == 1
    assert "MODIFY COLUMN tool_calls_json LONGTEXT" in executed[0]


def test_non_mysql_dialect_is_noop():
    columns = {
        "content_text": "TEXT", "content_parts_json": "TEXT",
        "tool_calls_json": "TEXT", "reasoning_text": "TEXT",
        "metadata_json": "TEXT", "message_json": "TEXT",
    }
    assert _run_upgrade("sqlite", columns) == []
