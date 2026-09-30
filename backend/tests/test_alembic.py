"""TECH-DEBT-2026-09：alembic 迁移链验证。

- 临时 SQLite 上 `alembic upgrade head` 可执行且幂等；
- `alembic stamp head` 幂等（存量库基线对齐路径）；
- 在 create_all 建好的全量 schema 上 upgrade head 不报错（新库路径）。

通过 subprocess 调用（每例独立的 DATABASE_URL，避免与 conftest 的测试库串扰）。
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
HEAD_REVISION = "0003_kb_fulltext_ngram"


def _run_alembic(args: list[str], database_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def _read_version(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchall()
            return rows[0][0] if rows else None
    finally:
        engine.dispose()


def _test_db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'alembic_test.db').as_posix()}"


def test_upgrade_head_on_empty_sqlite(tmp_path: Path):
    url = _test_db_url(tmp_path)

    result = _run_alembic(["upgrade", "head"], url)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert _read_version(url) == HEAD_REVISION


def test_upgrade_head_idempotent(tmp_path: Path):
    url = _test_db_url(tmp_path)

    first = _run_alembic(["upgrade", "head"], url)
    assert first.returncode == 0, first.stderr
    second = _run_alembic(["upgrade", "head"], url)
    assert second.returncode == 0, second.stderr
    assert _read_version(url) == HEAD_REVISION


def test_stamp_head_idempotent(tmp_path: Path):
    """存量库基线路径：stamp head 可重复执行且最终停在 head。"""
    url = _test_db_url(tmp_path)

    for _ in range(2):
        result = _run_alembic(["stamp", "head"], url)
        assert result.returncode == 0, result.stderr
    assert _read_version(url) == HEAD_REVISION


def test_upgrade_head_on_create_all_schema(tmp_path: Path):
    """新库路径：create_all 建全量 schema 后 upgrade head 不报错。"""
    db_path = tmp_path / "create_all_test.db"
    url = f"sqlite:///{db_path.as_posix()}"

    create_all = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.db.session import engine\n"
            "from app.db.models import Base\n"
            "Base.metadata.create_all(bind=engine)\n",
        ],
        cwd=str(BACKEND_DIR),
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert create_all.returncode == 0, create_all.stderr

    result = _run_alembic(["upgrade", "head"], url)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert _read_version(url) == HEAD_REVISION
