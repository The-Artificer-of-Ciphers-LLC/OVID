"""add disc_edits ip_hash column and cooldown index

Revision ID: 900000000004
Revises: 900000000003
Create Date: 2026-07-05 22:40:00.000000

Adds a nullable, salted/truncated HMAC-SHA256 IP-subnet hash column to
disc_edits (D-06 privacy) and a composite index
(user_id, edit_type, created_at) backing the worker-safe Postgres
confirmation cooldown (VERIFY-04/D-13). Historical rows keep ip_hash NULL,
so the anti-Sybil IP signal fails open (D-07) — no data backfill required.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '900000000004'
down_revision: Union[str, None] = '900000000003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'disc_edits',
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'idx_disc_edits_user_type_created',
        'disc_edits',
        ['user_id', 'edit_type', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('idx_disc_edits_user_type_created', table_name='disc_edits')
    op.drop_column('disc_edits', 'ip_hash')
