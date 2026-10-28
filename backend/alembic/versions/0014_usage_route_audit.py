"""用量表补审计维度：这次请求走了哪个提供商、哪条凭据、哪个模型

## 背景

``agent_usage_events`` 原来只有 ``user_id`` / ``session_id`` / ``model_name``：

- ``model_name`` 的取值兜底成 ``settings.openai_model``（``.env`` 里的值），
  而实际模型由**当前生效的提供商**决定 —— 管理员切了提供商之后，用量库里
  记的还是旧模型名，按模型聚合的图整个是错的。
- 企业网关的凭据是**系统级共享池**，``_agenticos_credential_id`` 这个埋点
  挂在网关上却没有任何消费者。结果就是「能查谁用的，查不到走的哪条凭据」，
  某个号被限流时无法定位影响面。

## 口径（重要，不要改反）

新增列**只用于审计**，不参与用量归属：

- 用量归属 = ``user_id``（发起请求的人）。按用户/会话聚合出来的 token 数
  才是「这个人用了多少」。
- ``provider_*`` / ``credential_id`` / ``account_label`` = 路由标签。一个号被
  多人共用，按账号聚合出来的 token 数对谁都不成立，不能拿来顶替用户口径。

``credential_id`` **不加外键**：凭据会因换号、Key 泄露轮换而被删除，而用量是
历史事实，不能因为删了个账号就让历史统计悬挂或级联消失。

## 顺带清理

``agent_usage_events`` 上有一对**完全重复**的复合索引：``ix_usage_user_created``
（user_id, created_at）与 ``ix_agent_usage_events_user_created`` 字段相同，
session 维度同理。根因是模型里写了两个 ``__table_args__``，后一个覆盖前一个，
而两批迁移各自建了一份。这里删掉 ``ix_usage_*`` 那对，保留模型声明的另一对。

Revision ID: 0014_usage_route_audit
Revises: 0013_provider_accounts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_usage_route_audit"
down_revision: Union[str, None] = "0013_provider_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "agent_usage_events"

# (列名, 列定义)。顺序即 ADD COLUMN 顺序，全部可空 —— 存量行没有路由信息。
_COLUMNS: list[tuple[str, sa.Column]] = [
    ("provider_id", sa.Column("provider_id", sa.Integer(), nullable=True)),
    ("provider_slug", sa.Column("provider_slug", sa.String(length=64), nullable=True)),
    ("provider_name", sa.Column("provider_name", sa.String(length=120), nullable=True)),
    ("credential_id", sa.Column("credential_id", sa.Integer(), nullable=True)),
    ("account_label", sa.Column("account_label", sa.String(length=64), nullable=True)),
    (
        "tokens_estimated",
        sa.Column(
            "tokens_estimated",
            sa.Boolean(),
            nullable=False,
            # 必须是 ``text("0")``：字符串 "0" 会渲染成 DEFAULT '0'，SQLite
            # 存文本，ORM 的 Boolean 做 bool('0') 得到 True，存量行会被全部
            # 误判成「token 是估算的」。
            server_default=sa.text("0"),
        ),
    ),
]

_INDEXES: list[tuple[str, str]] = [
    ("ix_agent_usage_events_provider_id", "provider_id"),
    ("ix_agent_usage_events_provider_slug", "provider_slug"),
    ("ix_agent_usage_events_credential_id", "credential_id"),
]

# 要清理的重复索引（与 ix_agent_usage_events_* 字段完全相同）
_DUPLICATE_INDEXES = ("ix_usage_user_created", "ix_usage_session_created")


def _bind():
    return op.get_bind()


def _has_table() -> bool:
    return sa.inspect(_bind()).has_table(_TABLE)


def _columns() -> set[str]:
    if not _has_table():
        return set()
    return {col["name"] for col in sa.inspect(_bind()).get_columns(_TABLE)}


def _index_names() -> set[str]:
    if not _has_table():
        return set()
    return {idx["name"] for idx in sa.inspect(_bind()).get_indexes(_TABLE)}


def upgrade() -> None:
    if not _has_table():
        # 全新库由 ``Base.metadata.create_all`` 建表，这里无事可做。
        return

    existing_columns = _columns()
    existing_indexes = _index_names()

    # SQLite 不支持一次 ADD 多列，逐列加也最省事；两方言都支持 ADD COLUMN。
    for name, column in _COLUMNS:
        if name in existing_columns:
            continue
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(column)

    for index_name, column_name in _INDEXES:
        if index_name in existing_indexes:
            continue
        op.create_index(index_name, _TABLE, [column_name])

    # 清理重复索引：DROP INDEX 两方言都支持，但索引不存在时会报错，
    # 所以先查一遍（迁移可能被重跑到一个已清理过的库上）。
    for index_name in _DUPLICATE_INDEXES:
        if index_name not in existing_indexes:
            continue
        try:
            op.drop_index(index_name, table_name=_TABLE)
        except Exception:  # noqa: BLE001 —— 清理是尽力而为，不该阻断升级
            pass


def downgrade() -> None:
    if not _has_table():
        return

    existing_indexes = _index_names()
    for index_name, _ in _INDEXES:
        if index_name not in existing_indexes:
            continue
        try:
            op.drop_index(index_name, table_name=_TABLE)
        except Exception:  # noqa: BLE001
            pass

    existing_columns = _columns()
    for name, _ in reversed(_COLUMNS):
        if name not in existing_columns:
            continue
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(name)

    # 重复索引不重建：它们本来就是冗余的，回滚到旧版本也不需要靠它们。
