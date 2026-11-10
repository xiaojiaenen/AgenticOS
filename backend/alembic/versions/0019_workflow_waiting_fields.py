"""工作流人工输入表单字段（0019）。

``workflow_runs.waiting_fields_json``：human_input 节点声明的表单字段
（``[{key,label,type,required,description}]`` 的 JSON）。

用途：智能体工具桥在**对话里**渲染人工输入表单（复用外部系统的
``UserInputPanel`` 契约）—— 用户在聊天里答复，工作流就地恢复；
管理面板/无会话场景（API 直跑）不依赖该列，仍走 waiting_input 提示。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019_workflow_waiting_fields"
down_revision: Union[str, None] = "0018_website_gallery_visibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "workflow_runs"


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return True
    return any(col["name"] == column for col in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    if not _has_table(_TABLE):
        return
    if _has_column(_TABLE, "waiting_fields_json"):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("waiting_fields_json", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_table(_TABLE):
        return
    if not _has_column(_TABLE, "waiting_fields_json"):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column("waiting_fields_json")
