"""反馈广场（GitHub-Issue 式）+ 用户最近活跃时间（0020）。

新增三张表：
- ``feedback_issues``   公开反馈/建议/缺陷（状态流转 + 投票 + 官方回复）
- ``feedback_comments`` 讨论 / 官方回复 / 系统状态变更评论
- ``feedback_votes``    「+1 / 我也有这个问题」一人一帖一票

并给 ``users`` 加 ``last_active_at``（鉴权心跳刷新，用于「最近活跃」展示）。

全部操作带存在性守卫，兼容 SQLite batch 与 MySQL 双方言（项目惯例）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_feedback_and_presence"
down_revision: Union[str, None] = "0019_workflow_waiting_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return True
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def _add_last_active() -> None:
    if not _has_table("users") or _has_column("users", "last_active_at"):
        return
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("last_active_at", sa.DateTime(), nullable=True))
    op.create_index("ix_users_last_active_at", "users", ["last_active_at"])


def _create_issues() -> None:
    if _has_table("feedback_issues"):
        return
    op.create_table(
        "feedback_issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="feature"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="medium"),
        sa.Column("visibility", sa.String(length=10), nullable=False, server_default="public"),
        sa.Column("context_json", sa.Text(), nullable=False),
        sa.Column("vote_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolved_by", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("shipped_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_issues_user_id", "feedback_issues", ["user_id"])
    op.create_index("ix_feedback_issues_type", "feedback_issues", ["type"])
    op.create_index("ix_feedback_issues_status", "feedback_issues", ["status"])
    op.create_index("ix_feedback_issues_visibility", "feedback_issues", ["visibility"])
    op.create_index("ix_feedback_issues_created_at", "feedback_issues", ["created_at"])
    op.create_index("ix_feedback_issues_status_created", "feedback_issues", ["status", "created_at"])
    op.create_index("ix_feedback_issues_votes", "feedback_issues", ["vote_count"])


def _create_comments() -> None:
    if _has_table("feedback_comments"):
        return
    op.create_table(
        "feedback_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["feedback_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_comments_issue_id", "feedback_comments", ["issue_id"])
    op.create_index("ix_feedback_comments_user_id", "feedback_comments", ["user_id"])


def _create_votes() -> None:
    if _has_table("feedback_votes"):
        return
    op.create_table(
        "feedback_votes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["feedback_issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issue_id", "user_id", name="uq_feedback_votes_issue_user"),
    )
    op.create_index("ix_feedback_votes_issue_id", "feedback_votes", ["issue_id"])
    op.create_index("ix_feedback_votes_user_id", "feedback_votes", ["user_id"])


def upgrade() -> None:
    _add_last_active()
    _create_issues()
    _create_comments()
    _create_votes()


def downgrade() -> None:
    for table in ("feedback_votes", "feedback_comments", "feedback_issues"):
        if _has_table(table):
            op.drop_table(table)
    if _has_table("users") and _has_column("users", "last_active_at"):
        op.drop_index("ix_users_last_active_at", table_name="users")
        with op.batch_alter_table("users") as batch:
            batch.drop_column("last_active_at")
