"""切片摘要列（Summary Auto-Gen）

Revision ID: 0007_page_summary
Revises: 0006_mcp_servers
Create Date: 2026-10-02

知识库 Wiki 页面增加 ``summary`` 列：编译时写入 frontmatter.summary，
检索时标题/摘要一并参与匹配——长文档的要点常出现在摘要里，
标题不符但摘要命中也能召回本页（参考 Dify 的 Summary Auto-Gen）。

存量数据留空即可（检索逻辑对空摘要自动跳过），后续重新编译会补齐。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_page_summary"
down_revision: Union[str, None] = "0006_mcp_servers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("kb_wiki_pages"):
        return
    columns = {c["name"] for c in inspector.get_columns("kb_wiki_pages")}
    if "summary" in columns:
        return
    # MySQL 上正文是 LONGTEXT，摘要用 TEXT 足够
    op.add_column(
        "kb_wiki_pages",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    # 存量回填：用标题做初始摘要，至少让新页面有个可匹配的短文本
    op.execute(
        "UPDATE kb_wiki_pages SET summary = title "
        "WHERE summary IS NULL AND title IS NOT NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("kb_wiki_pages"):
        return
    columns = {c["name"] for c in sa.inspect(bind).get_columns("kb_wiki_pages")}
    if "summary" in columns:
        op.drop_column("kb_wiki_pages", "summary")