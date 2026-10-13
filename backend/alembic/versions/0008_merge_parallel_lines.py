"""merge parallel migration lines (permissions/perf) with (user-agents/mcp/summary)

Revision ID: 872c79f747bb
Revises: 0005_permissions_and_audit, 0007_page_summary
Create Date: 2026-10-13 10:11:03.986306

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '872c79f747bb'
down_revision: Union[str, None] = ('0005_permissions_and_audit', '0007_page_summary')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
