"""Sync feed utilities — monotonic sequence counter and helpers.

The global sequence counter lives in the ``global_seq`` single-row table
(enforced by CHECK id = 1).  ``next_seq()`` atomically increments it
and returns the new value, suitable for stamping Disc/Release/DiscSet
records so downstream mirrors can request "changes since seq N".

On PostgreSQL the row is locked with ``FOR UPDATE`` to serialise
concurrent writers.  On SQLite ``with_for_update()`` is silently
ignored by SQLAlchemy's dialect compiler, and SQLite serialises all
writes to a single connection anyway, so test-harness correctness
is preserved.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GlobalSeq

logger = logging.getLogger(__name__)


def next_seq(db: Session) -> int:
    """Atomically increment the global sequence counter and return the new value.

    Must be called inside an existing transaction (the caller's request
    transaction).  The counter row is locked with ``FOR UPDATE`` on
    PostgreSQL; SQLAlchemy omits the clause on SQLite automatically.

    Returns:
        The new (post-increment) sequence number.

    Raises:
        RuntimeError: If the ``global_seq`` row is missing (DB not seeded).
    """
    # Use SQLAlchemy's with_for_update() — on PostgreSQL it emits
    # "SELECT ... FOR UPDATE"; on SQLite the clause is omitted by
    # the dialect compiler (see D023).
    stmt = (
        select(GlobalSeq)
        .where(GlobalSeq.id == 1)
        .with_for_update()
    )
    row = db.execute(stmt).scalar_one_or_none()

    if row is None:
        raise RuntimeError(
            "global_seq row missing — run the seed migration or call "
            "_seed_global_seq() in tests"
        )

    row.current_seq += 1
    db.flush()

    logger.debug("sync_seq_incremented new_seq=%d", row.current_seq)
    return row.current_seq
