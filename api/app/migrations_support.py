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

from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
