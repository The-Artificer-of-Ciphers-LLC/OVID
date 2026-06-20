"""add disc identity aliases

Revision ID: 900000000003
Revises: 900000000002
Create Date: 2026-06-20 01:20:00.000000

Stores secondary Disc Identity strings that resolve to the same physical
disc pressing as the Primary Fingerprint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '900000000003'
down_revision: Union[str, None] = '900000000002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'disc_identity_aliases',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('disc_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['disc_id'], ['discs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    op.create_index(
        'idx_disc_identity_aliases_fingerprint',
        'disc_identity_aliases',
        ['fingerprint'],
    )
    op.create_index(
        'idx_disc_identity_aliases_disc_id',
        'disc_identity_aliases',
        ['disc_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_disc_identity_aliases_disc_id', table_name='disc_identity_aliases')
    op.drop_index(
        'idx_disc_identity_aliases_fingerprint',
        table_name='disc_identity_aliases',
    )
    op.drop_table('disc_identity_aliases')
