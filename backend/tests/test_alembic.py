"""TECH-DEBT-2026-09：alembic 迁移链验证。

- 临时 SQLite 上 `alembic upgrade head` 可执行且幂等；
- `alembic stamp head` 幂等（存量库基线对齐路径）；
- 在 create_all 建好的全量 schema 上 upgrade head 不报错（新库路径）。

通过 subprocess 调用（每例独立的 DATABASE_URL，避免与 conftest 的测试库串扰）。
"""

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _current_head_revision() -> str:
    """动态解析迁移链的 head revision。

    不硬编码：M6 里 alembic 有并行推进的迁移线（性能线 / 权限线 / MCP 线），
    写死字符串会让每加一个迁移就要改测试。按 alembic 自己的版本目录解析，
    新迁移提交后本测试自动跟进，迁移链分叉（多头）时立即失败。

    并行线合并后由 0008_merge_parallel_lines 收口为单一 head。
    """
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1, f"迁移链分叉，检出多个 head: {heads}"
    return heads[0]


HEAD_REVISION = _current_head_revision()


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


# ---------------------------------------------------------------------------
# 增量迁移的「列真的建出来了吗」守卫
#
# 上面的用例只证明迁移链能跑通；一个 add_column 写成空实现、写错表名、
# 或 guard 逻辑写反（表存在却 skip），链测试依然全绿，生产升级后却会在
# 第一次读写该列时炸。每个带新列的迁移都应在此登记一条断言。
# ---------------------------------------------------------------------------

# (表名, 列名, 迁移前所在版本) —— 新增列迁移清单
_EXPECTED_NEW_COLUMNS = [
    ("workflow_runs", "waiting_fields_json", "0018_website_gallery_visibility"),
]


def test_incremental_migrations_add_expected_columns(tmp_path: Path):
    """从老版本升级到 head：每个登记的新列必须真实存在且可写。

    构造方式：先用 create_all 建全量 schema（含新列），再手工删掉目标列、
    把版本钉回迁移前，然后 upgrade head —— 模拟「线上老库」的真实形态。
    """
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    db_path = tmp_path / "incremental.db"
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

    # 模拟老库：版本先钉到迁移前（create_all 不建 alembic_version），再删掉新列
    stamp = _run_alembic(["stamp", _EXPECTED_NEW_COLUMNS[0][2]], url)
    assert stamp.returncode == 0, stamp.stderr

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            op = Operations(MigrationContext.configure(conn))
            for table, column, _from_rev in _EXPECTED_NEW_COLUMNS:
                with op.batch_alter_table(table) as batch:
                    batch.drop_column(column)
    finally:
        engine.dispose()

    result = _run_alembic(["upgrade", "head"], url)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert _read_version(url) == HEAD_REVISION

    # 关键断言：列真实存在，且 SQL 能引用（类型/表名没写歪）
    engine = create_engine(url)
    try:
        inspector = sa.inspect(engine)
        with engine.begin() as conn:
            for table, column, _from_rev in _EXPECTED_NEW_COLUMNS:
                columns = {c["name"] for c in inspector.get_columns(table)}
                assert column in columns, (
                    f"{table}.{column} 迁移后仍不存在（迁移可能是空实现或 guard 写反）"
                )
                conn.execute(text(f"UPDATE {table} SET {column} = '[]' WHERE 1 = 0"))
    finally:
        engine.dispose()
