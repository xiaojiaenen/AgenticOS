"""LLMOps：运行追踪 / 消息反馈 / 智能体发布 / Prompt 版本与评测（0017）。

新增 5 张表 + agent_profiles 发布三列。历史库与本库都从 0016 顺序升级；
本迁移全部使用「列/表存在性检查」幂等写法（项目里 0005 起的惯例，
SQLite batch 与 MySQL 双方言兼容）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_llmops_traces_publish_evals"
down_revision: Union[str, None] = "0016_credential_user_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table):
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


def _upgrade_publish_columns() -> None:
    """agent_profiles 增加 / 下线发布所需三列。"""
    if not _has_table("agent_profiles"):
        return
    if not _has_column("agent_profiles", "published"):
        op.add_column(
            "agent_profiles",
            sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )
    if not _has_column("agent_profiles", "publish_slug"):
        op.add_column(
            "agent_profiles",
            sa.Column("publish_slug", sa.String(length=32), nullable=True),
        )
        op.create_index(
            "ix_agent_profiles_publish_slug", "agent_profiles", ["publish_slug"],
            unique=True,
        )
    if not _has_column("agent_profiles", "publish_config_json"):
        op.add_column(
            "agent_profiles",
            sa.Column("publish_config_json", sa.Text(), nullable=True),
        )


def _create_traces() -> None:
    if _has_table("agent_run_traces"):
        return
    op.create_table(
        "agent_run_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("agent_profile_id", sa.Integer(), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="general"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("text_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reasoning_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("llm_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_run_traces_session", "agent_run_traces", ["session_id"])
    op.create_index("ix_agent_run_traces_status", "agent_run_traces", ["status"])
    op.create_index("ix_agent_run_traces_started", "agent_run_traces", ["started_at"])


def _create_feedbacks() -> None:
    if _has_table("agent_message_feedbacks"):
        return
    op.create_table(
        "agent_message_feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("message_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_feedbacks_session", "agent_message_feedbacks", ["session_id"])
    op.create_index("ix_agent_feedbacks_user", "agent_message_feedbacks", ["user_id"])


def _create_profile_versions() -> None:
    if _has_table("agent_profile_versions"):
        return
    op.create_table(
        "agent_profile_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_profile_versions_profile", "agent_profile_versions", ["profile_id", "version"],
    )


def _create_eval_tables() -> None:
    if not _has_table("agent_eval_datasets"):
        op.create_table(
            "agent_eval_datasets",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_table("agent_eval_cases"):
        op.create_table(
            "agent_eval_cases",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("input", sa.Text(), nullable=False),
            sa.Column("expected_json", sa.Text(), nullable=True),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_eval_cases_dataset", "agent_eval_cases", ["dataset_id"])
    if not _has_table("agent_eval_runs"):
        op.create_table(
            "agent_eval_runs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("dataset_id", sa.Integer(), nullable=False),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("profile_version", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
            sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("results_json", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_eval_runs_dataset", "agent_eval_runs", ["dataset_id"])
        op.create_index("ix_agent_eval_runs_status", "agent_eval_runs", ["status"])


def upgrade() -> None:
    _upgrade_publish_columns()
    _create_traces()
    _create_feedbacks()
    _create_profile_versions()
    _create_eval_tables()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in (
        "agent_eval_runs", "agent_eval_cases", "agent_eval_datasets",
        "agent_profile_versions", "agent_message_feedbacks", "agent_run_traces",
    ):
        if table in tables:
            op.drop_table(table)
    if _has_column("agent_profiles", "publish_config_json"):
        op.drop_column("agent_profiles", "publish_config_json")
    if _has_column("agent_profiles", "publish_slug"):
        op.drop_index("ix_agent_profiles_publish_slug", table_name="agent_profiles")
        op.drop_column("agent_profiles", "publish_slug")
    if _has_column("agent_profiles", "published"):
        op.drop_column("agent_profiles", "published")
