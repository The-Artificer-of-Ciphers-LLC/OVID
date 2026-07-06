"""Alembic-independent, directly pytest-testable per-row migration logic.

CI never runs a real ``alembic upgrade head`` against Postgres (only
``pytest`` against the in-memory SQLite test harness — see
``.github/workflows/ci.yml``), so any nontrivial migration transform must be
factored into plain functions taking a SQLAlchemy ``Connection`` that are
directly callable from a pytest test using the project's existing
``db_session``/in-memory-SQLite fixtures, with zero Alembic invocation
required for unit coverage.

This module holds the D-01 promotion transform: rewriting a disc's primary
``discs.fingerprint`` from a ``dvd1-*`` value to its already-recorded
``dvdread1-*`` alias, one disc at a time, idempotently and resumably. The
Alembic migration file that wraps ``promote_all_dvdread1_discs()`` (Plan
05-06) is a thin caller of this module — it contains no promotion logic of
its own.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def promote_one_disc(connection: Connection, dvd1_fingerprint: str) -> bool:
    """Promote a single disc from ``dvd1-*`` primary to ``dvdread1-*`` primary.

    Looks up a disc whose current ``discs.fingerprint`` still equals
    ``dvd1_fingerprint`` AND that has a recorded ``dvdread1-*`` Lookup Alias.
    If found: deletes that alias row, sets ``discs.fingerprint`` to the
    ``dvdread1-*`` value, and inserts the OLD ``dvd1-*`` value as a new
    alias row (with a fresh ``created_at`` so it sorts after any
    pre-existing aliases, per D-06 primary-first-by-``(created_at, id)``
    ordering).

    Idempotent: the WHERE clause guards on ``discs.fingerprint`` still
    equaling the OLD ``dvd1-*`` value, so an already-promoted disc (or a
    disc with no ``dvdread1-*`` alias at all) is a safe no-op. Never
    raises. Returns ``True`` if a promotion occurred, ``False`` otherwise.
    """
    row = connection.execute(
        text(
            "SELECT d.id AS disc_id, a.id AS alias_id, a.fingerprint AS dvdread1_fp "
            "FROM discs d JOIN disc_identity_aliases a ON a.disc_id = d.id "
            "WHERE d.fingerprint = :dvd1_fp AND a.fingerprint LIKE 'dvdread1-%'"
        ),
        {"dvd1_fp": dvd1_fingerprint},
    ).first()
    if row is None:
        return False  # already promoted, or no dvdread1-* alias — safe no-op

    connection.execute(
        text("DELETE FROM disc_identity_aliases WHERE id = :alias_id"),
        {"alias_id": row.alias_id},
    )
    connection.execute(
        text("UPDATE discs SET fingerprint = :new_fp WHERE id = :disc_id"),
        {"new_fp": row.dvdread1_fp, "disc_id": row.disc_id},
    )
    connection.execute(
        text(
            "INSERT INTO disc_identity_aliases (id, disc_id, fingerprint, created_at) "
            "VALUES (:id, :disc_id, :old_fp, :now)"
        ),
        {
            # .hex: raw text() binds are untyped (NullType) — they bypass
            # the ORM UUID type decorator's bind processor entirely, so a
            # bare uuid.UUID object fails to bind against the sqlite3 DBAPI
            # ("type 'UUID' is not supported"). row.disc_id (itself read
            # back through a raw SELECT) is already the plain hex-no-dash
            # string the column is physically stored as under SQLite's
            # non-native UUID storage; use the matching .hex format for the
            # freshly-generated id so it round-trips identically.
            "id": uuid.uuid4().hex,
            "disc_id": row.disc_id,
            "old_fp": dvd1_fingerprint,
            "now": _utcnow(),
        },
    )
    return True


def promote_all_dvdread1_discs(connection: Connection) -> int:
    """Bulk-promote every disc that has a recorded ``dvdread1-*`` alias.

    Enumerates every disc currently on a ``dvd1-*`` primary fingerprint,
    then calls :func:`promote_one_disc` for each — committing after EVERY
    candidate (promoted or not) so the enumeration's own transaction
    segment never grows unbounded across a large table. This is
    SQLAlchemy 2.0's "commit as you go" pattern
    [docs.sqlalchemy.org/en/20/core/connections.html]: the connection
    auto-begins a new transaction segment on the next ``execute()`` call
    after ``commit()``.

    Per-disc commits make an interrupted run safely resumable: re-running
    this function from scratch after a partial pass only re-processes
    already-promoted discs, which :func:`promote_one_disc` treats as a
    no-op (idempotency guard), and discs not yet reached are simply
    promoted on the next pass.

    Returns the total number of discs promoted in this run.
    """
    candidates = [
        row[0]
        for row in connection.execute(
            text("SELECT fingerprint FROM discs WHERE fingerprint LIKE 'dvd1-%'")
        ).all()
    ]

    promoted_count = 0
    for i, dvd1_fingerprint in enumerate(candidates, start=1):
        if promote_one_disc(connection, dvd1_fingerprint):
            promoted_count += 1
        connection.commit()
        if i % 100 == 0:
            print(f"  ...promoted {promoted_count}/{i} discs processed")

    print(f"Promotion complete: {promoted_count} discs promoted to dvdread1-* primary")
    return promoted_count
