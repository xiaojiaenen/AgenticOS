"""补齐缺失索引 + 清理废弃明文密码列 + video_artifacts 用户外键

Revision ID: 0004_indexes_and_cleanup
Revises: 0003_kb_fulltext_ngram
Create Date: 2026-10-01

内容：
- 补 dashboard 高频查询的复合索引（agent_usage_events）与过滤列索引
  （skills.visibility / memories.visibility / memories.authority_level /
  website_deploys.project_slug / kb_access_control.granted_by）；
- user_email_credentials.password 列已弃用（明文残留，迁移至
  password_encrypted），统一置 NULL 清除敏感数据残留；
- video_artifacts.user_id 补外键（全库唯一一个无 FK 的 user_id），
  先清理孤儿行再通过 batch_alter_table 添加（SQLite 需重建表）；
- 全部步骤幂等：索引/约束已存在时跳过。

downgrade 只回滚索引；已清除的明文密码与已加的外键不回滚。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0004_indexes_and_cleanup"
down_revision: Union[str, None] = "0003_kb_fulltext_ngram"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 索引名, 列)
_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("agent_usage_events", "ix_usage_user_created", ("user_id", "created_at")),
    ("agent_usage_events", "ix_usage_session_created", ("session_id", "created_at")),
    ("skills", "ix_skills_visibility", ("visibility",)),
    ("memories", "ix_memories_visibility", ("visibility",)),
    ("memories", "ix_memories_authority_level", ("authority_level",)),
    ("website_deploys", "ix_website_deploys_project_slug", ("project_slug",)),
    ("kb_access_control", "ix_kb_access_granted_by", ("granted_by",)),
)


def _has_index(inspector, table: str, index_name: str) -> bool:
    try:
        return any(idx["name"] == index_name for idx in inspector.get_indexes(table))
    except Exception:  # noqa: BLE001 —— 表不存在等情况视为无索引
        return False


def _has_foreign_key(inspector, table: str, constraint_name: str) -> bool:
    try:
        return any(
            fk.get("name") == constraint_name
            for fk in inspector.get_foreign_keys(table)
        )
    except Exception:  # noqa: BLE001
        return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, index_name, columns in _INDEXES:
        if not inspector.has_table(table) or _has_index(inspector, table, index_name):
            continue
        try:
            op.create_index(index_name, table, list(columns))
        except Exception as exc:  # noqa: BLE001 —— 已存在/方言差异时跳过
            print(f"skip index {index_name}: {exc}")

    # 清理已弃用的明文密码列数据（列保留以兼容旧 schema，内容置空）
    if inspector.has_table("user_email_credentials"):
        bind.execute(text("UPDATE user_email_credentials SET password = NULL WHERE password IS NOT NULL AND password <> ''"))

    # video_artifacts.user_id 补外键
    if inspector.has_table("video_artifacts") and not _has_foreign_key(
        inspector, "video_artifacts", "fk_video_artifacts_user"
    ):
        bind.execute(
            text(
                "DELETE FROM video_artifacts WHERE user_id IS NOT NULL "
                "AND user_id NOT IN (SELECT id FROM users)"
            )
        )
        with op.batch_alter_table("video_artifacts") as batch_op:
            batch_op.create_foreign_key(
                "fk_video_artifacts_user", "users", ["user_id"], ["id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, index_name, _columns in _INDEXES:
        if _has_index(inspector, table, index_name):
            op.drop_index(index_name, table_name=table)
