"""add sync_state table

Revision ID: 900000000002
Revises: 900000000001
Create Date: 2026-04-03 14:00:00.000000

Adds the sync_state key-value table used by the mirror-mode sync daemon
to track last-synced sequence numbers, snapshot ETags, etc.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '900000000002'
down_revision: Union[str, None] = '900000000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_state',
        sa.Column('key', sa.String(50), nullable=False),
        sa.Column('value', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('sync_state')
