"""add sync seq numbers

Revision ID: 900000000001
Revises: 800000000000
Create Date: 2026-04-03 13:30:00.000000

Adds the global_seq single-row counter table and seq_num columns to
discs, releases, and disc_sets for the sync feed (D023, R018).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '900000000001'
down_revision: Union[str, None] = '800000000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- global_seq table: single-row monotonic counter ---
    op.create_table(
        'global_seq',
        sa.Column('id', sa.Integer(), nullable=False, default=1),
        sa.Column('current_seq', sa.BigInteger(), nullable=False, default=0),
        sa.CheckConstraint('id = 1', name='ck_global_seq_single_row'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Seed the initial row
    op.execute("INSERT INTO global_seq (id, current_seq) VALUES (1, 0)")

    # --- seq_num columns on disc/release/disc_set tables ---
    op.add_column('discs', sa.Column('seq_num', sa.BigInteger(), nullable=True))
    op.create_index('ix_discs_seq_num', 'discs', ['seq_num'])

    op.add_column('releases', sa.Column('seq_num', sa.BigInteger(), nullable=True))
    op.create_index('ix_releases_seq_num', 'releases', ['seq_num'])

    op.add_column('disc_sets', sa.Column('seq_num', sa.BigInteger(), nullable=True))
    op.create_index('ix_disc_sets_seq_num', 'disc_sets', ['seq_num'])


def downgrade() -> None:
    op.drop_index('ix_disc_sets_seq_num', table_name='disc_sets')
    op.drop_column('disc_sets', 'seq_num')

    op.drop_index('ix_releases_seq_num', table_name='releases')
    op.drop_column('releases', 'seq_num')

    op.drop_index('ix_discs_seq_num', table_name='discs')
    op.drop_column('discs', 'seq_num')

    op.drop_table('global_seq')
