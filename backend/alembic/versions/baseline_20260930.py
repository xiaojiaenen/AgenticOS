"""baseline: 对齐既有库结构（引入 alembic，TECH-DEBT-2026-09）

Revision ID: baseline_20260930
Revises:
Create Date: 2026-09-30

空基线迁移（head 起点）。

背景：在引入 alembic 之前，schema 演进由两条路径完成：
1. ``Base.metadata.create_all()``（新库建全量表结构，启动时自动执行）；
2. ``app/db/session.py`` 的 ``_ensure_compatible_schema()`` 手写 ALTER TABLE
   补列（已在本次重构中删除）。

因此本迁移刻意为空 —— 既有库的结构不在此重放。基线对齐方式：

- 存量库（开发/生产）：直接 ``alembic stamp head``，把版本标记推到 head。
- 新库（开发 SQLite）：应用启动时 create_all 建全量 schema 后，同样
  ``alembic stamp head``。
- 新库（生产 MySQL）：create_all 建表后执行 ``alembic upgrade head``，
  让 0002_mysql_longtext 把大文本列拉长为 LONGTEXT（见该迁移说明）。

详见 backend/alembic/README.md。
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "baseline_20260930"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """空基线：不执行任何 DDL（既有结构由 create_all / 历史 compat 层建立）。"""
    pass


def downgrade() -> None:
    """基线不可回退（无对应 DDL）。"""
    pass
