"""promote dvdread1-* to primary DVD fingerprint (ADR 0001 Phase 3)

Revision ID: 900000000006
Revises: 900000000005
Create Date: 2026-07-06 23:15:00.000000

One-time data migration (D-01): for every disc that has a recorded
``dvdread1-*`` Lookup Alias, promotes that alias to the disc's primary
``discs.fingerprint`` and demotes the old ``dvd1-*`` value to a new alias
row — the entire promotion runs within Alembic's single migration
transaction on ``op.get_bind()``'s connection, atomic with Alembic's own
post-``upgrade()`` ``alembic_version`` stamp write (see the ``commit=False``
call below). Per-disc commit-as-you-go (SQLAlchemy 2.0's pattern) is only
used on the standalone/direct-call path, not here. Any disc with no
recorded ``dvdread1-*`` alias is left untouched, permanently on ``dvd1-*``.

Chained strictly AFTER revision 900000000005 (the fingerprint_registry
create+backfill migration), per the phase's locked sequencing — the
cross-table arbitration backstop must exist before this migration
increases write concurrency on the shared fingerprint namespace.

This is a thin wrapper around ``promote_all_dvdread1_discs()``
(``app.migrations_support``, Plan 05-02) — it contains no promotion logic
of its own; see that module for the tested transform.
"""
from typing import Sequence, Union

from alembic import op

from app.migrations_support import promote_all_dvdread1_discs


# revision identifiers, used by Alembic.
revision: str = '900000000006'
down_revision: Union[str, None] = '900000000005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    # promote_all_dvdread1_discs() already prints its own completion summary
    # ("Promotion complete: N discs promoted...") — no need to print again.
    #
    # commit=False: Alembic owns this migration's transaction on
    # `connection` and, once upgrade() returns, writes the alembic_version
    # stamp for this revision using that same transaction. If this call
    # were allowed to commit `connection` mid-migration (the default),
    # Alembic's migration transaction would end early and its later
    # alembic_version write would land in a transaction Alembic no longer
    # commits — silently discarding the stamp (observed live: promotion
    # data applied, but alembic_version stayed pinned at 900000000005
    # forever, so this migration re-ran as a no-op on every subsequent
    # `alembic upgrade head`). commit=False leaves all transaction control
    # to Alembic, so the promotion and the version stamp commit atomically
    # as one Alembic transaction.
    promote_all_dvdread1_discs(connection, commit=False)


def downgrade() -> None:
    # Explicit documented no-op: reversing a promotion en masse is not a
    # sanctioned operation per D-03's Disc.fingerprint immutability
    # guarantee — a downgrade here would itself violate the
    # anti-fragmentation guarantee ADR 0001 protects. Never raise
    # NotImplementedError; a downgrade attempt should be a deliberate no-op.
    pass
