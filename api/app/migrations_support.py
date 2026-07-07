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

It also holds the D-02 registry-backfill transform,
``backfill_fingerprint_registry()``: a one-time, non-per-row-idempotent
bulk populate of the ``fingerprint_registry`` table (Plan 05-01's WR-02
arbitration table) from both ``discs.fingerprint`` and
``disc_identity_aliases.fingerprint``. Unlike ``promote_one_disc``, this
needs no ``WHERE``-guard resumability — Alembic's own revision tracking
guarantees the migration calling it runs exactly once.
"""

import sqlite3
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _register_sqlite_datetime_adapter() -> None:
    """Register a ``sqlite3`` datetime adapter matching SQLAlchemy's own
    ``DATETIME`` bind_processor storage format exactly (naive,
    space-separated, microsecond-precision — see
    ``sqlalchemy.dialects.sqlite.base.DATETIME.bind_processor``).

    Raw ``text()`` SQL binds in this module are untyped (``NullType``) and
    bypass the ORM's ``DateTime`` type decorator entirely. Without this
    registration, the stdlib ``sqlite3`` driver falls back to its own
    default adapter, which is (a) deprecated as of Python 3.12 and (b)
    preserves ``tzinfo`` in its ``str(datetime)`` output (e.g. a
    ``"...+00:00"`` suffix for our UTC-aware ``_utcnow()`` values) — a
    DIFFERENT stored string than ORM-driven inserts into the exact same
    column (which strip ``tzinfo``). That mismatch is a genuine read-back
    inconsistency, not merely a cosmetic warning: querying the same column
    later via the ORM would return tz-aware ``datetime`` objects for
    raw-SQL-inserted rows and tz-naive ones for ORM-inserted rows, and
    comparing/sorting the two together raises ``TypeError: can't compare
    offset-naive and offset-aware datetimes`` (relevant to D-06's
    ``(created_at, id)`` alias ordering). This adapter unifies both paths
    on SQLAlchemy's own storage format so every row round-trips
    identically regardless of which code path inserted it. Registering it
    has no effect on PostgreSQL — it only configures the stdlib
    ``sqlite3`` module's process-global adapter registry; ``psycopg2`` is
    a separate driver and is unaffected.
    """

    def _adapt(dt: datetime) -> str:
        return (
            f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d} "
            f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}.{dt.microsecond:06d}"
        )

    sqlite3.register_adapter(datetime, _adapt)


_register_sqlite_datetime_adapter()


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
    disc with no ``dvdread1-*`` alias at all) is a safe no-op. May raise
    on database errors (e.g. a constraint violation or connectivity
    failure) — callers run inside the migration's own transaction and are
    expected to let such errors propagate rather than swallow them.
    Returns ``True`` if a promotion occurred, ``False`` otherwise.
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


def backfill_fingerprint_registry(connection: Connection) -> tuple[int, int]:
    """One-time bulk backfill of ``fingerprint_registry`` from both source
    tables (D-02, WR-02 arbitration).

    Reads every ``(id, fingerprint)`` row from ``discs`` and every
    ``(disc_id, fingerprint)`` row from ``disc_identity_aliases``, then
    inserts one new ``fingerprint_registry`` row per source row. Each new
    row's id is generated in Python (``uuid.uuid4()``) rather than relying
    on a database-side UUID-generation function, so this transform is
    dialect-portable and runs identically against SQLite and PostgreSQL —
    the exact same code path is directly exercised (and asserted) by the
    in-memory SQLite pytest harness, never skipped/mocked.

    This is a one-time, non-per-row-idempotent bulk backfill: unlike
    :func:`promote_one_disc`, it needs no ``WHERE``-guard resumability,
    since Alembic's own revision tracking guarantees the caller's
    ``upgrade()`` runs exactly once.

    ``discs.fingerprint`` and ``disc_identity_aliases.fingerprint`` are each
    independently UNIQUE *within their own table*, but nothing enforces
    uniqueness *across* the two tables prior to this phase — the exact
    cross-table gap WR-02 closes going forward. So pre-existing production
    data could (in principle) already have the same string as both a
    disc's primary fingerprint and a different disc's alias. The registry's
    global ``UNIQUE(fingerprint)`` would reject a literal duplicate insert,
    so this backfill deduplicates by fingerprint value, inserting each
    distinct string exactly once (discs win ties, since they are processed
    first).

    Returns ``(count_from_discs, count_from_aliases)`` — the number of
    registry rows actually inserted from each source table (post-dedupe).
    """
    disc_rows = connection.execute(
        text("SELECT id, fingerprint FROM discs")
    ).all()
    alias_rows = connection.execute(
        text("SELECT disc_id, fingerprint FROM disc_identity_aliases")
    ).all()

    seen_fingerprints: set[str] = set()
    discs_inserted = 0
    aliases_inserted = 0

    for row in disc_rows:
        if row.fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(row.fingerprint)
        connection.execute(
            text(
                "INSERT INTO fingerprint_registry "
                "(id, fingerprint, disc_id, created_at) "
                "VALUES (:id, :fingerprint, :disc_id, :now)"
            ),
            {
                # .hex: raw text() binds are untyped (NullType) and bypass
                # the ORM UUID type decorator's bind processor — see
                # promote_one_disc's docstring above for the same gotcha.
                "id": uuid.uuid4().hex,
                "fingerprint": row.fingerprint,
                "disc_id": row.id,
                "now": _utcnow(),
            },
        )
        discs_inserted += 1

    for row in alias_rows:
        if row.fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(row.fingerprint)
        connection.execute(
            text(
                "INSERT INTO fingerprint_registry "
                "(id, fingerprint, disc_id, created_at) "
                "VALUES (:id, :fingerprint, :disc_id, :now)"
            ),
            {
                "id": uuid.uuid4().hex,
                "fingerprint": row.fingerprint,
                "disc_id": row.disc_id,
                "now": _utcnow(),
            },
        )
        aliases_inserted += 1

    return discs_inserted, aliases_inserted
