"""add fingerprint_registry table (WR-02 cross-table arbitration)

Revision ID: 900000000005
Revises: 900000000004
Create Date: 2026-07-06 23:00:00.000000

Creates the ``fingerprint_registry`` table (D-02): a single table with a
global ``UNIQUE(fingerprint)`` column that both the new-disc insert path
and ``attach_lookup_aliases`` register into first, collapsing a "new disc
claims F" vs. "attach F as an alias of a different disc" race into the
same insert/IntegrityError/re-resolve convergence idiom already used for
same-table alias races (WR-02).

Backfills the registry from BOTH ``discs.fingerprint`` and
``disc_identity_aliases.fingerprint`` inside this SAME migration
transaction — no window where the registry lags reality. Must run
strictly BEFORE revision 900000000006 (the dvdread1-* promotion
migration), since promotion increases write concurrency on the shared
fingerprint namespace and needs the arbitration backstop to already exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.migrations_support import backfill_fingerprint_registry


# revision identifiers, used by Alembic.
revision: str = '900000000005'
down_revision: Union[str, None] = '900000000004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fingerprint_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(length=50), nullable=False),
        sa.Column('disc_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['disc_id'], ['discs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fingerprint'),
    )
    op.create_index(
        'idx_fingerprint_registry_disc_id',
        'fingerprint_registry',
        ['disc_id'],
    )

    connection = op.get_bind()
    discs_count, aliases_count = backfill_fingerprint_registry(connection)
    print(
        f"fingerprint_registry backfilled: {discs_count} from discs, "
        f"{aliases_count} from disc_identity_aliases"
    )


def downgrade() -> None:
    op.drop_index('idx_fingerprint_registry_disc_id', table_name='fingerprint_registry')
    op.drop_table('fingerprint_registry')
