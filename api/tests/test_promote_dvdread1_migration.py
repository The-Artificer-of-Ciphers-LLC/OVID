"""D-01 promotion transform: ``promote_one_disc`` / ``promote_all_dvdread1_discs``.

These test the plain, Alembic-independent functions in
``app.migrations_support`` directly against the project's in-memory SQLite
harness — no Alembic invocation anywhere in this file (Pitfall 5: CI never
runs a real ``alembic upgrade head`` against Postgres, so this transform
must be provable without one).
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.migrations_support import promote_one_disc
from app.models import Disc, DiscIdentityAlias


def _seed_disc_with_alias(
    db: Session,
    *,
    dvd1_fingerprint: str,
    dvdread1_fingerprint: str | None,
) -> Disc:
    """Seed a Disc whose primary fingerprint is ``dvd1_fingerprint``, plus an
    optional ``dvdread1-*`` Lookup Alias row. Commits so the raw-SQL
    promotion helpers (which operate on ``connection`` rather than the ORM
    session) see durable state."""
    disc = Disc(fingerprint=dvd1_fingerprint, format="DVD", status="verified")
    db.add(disc)
    db.flush()
    if dvdread1_fingerprint is not None:
        db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=dvdread1_fingerprint))
    db.commit()
    return disc


def _fetch_disc_row(db: Session, disc_id: uuid.UUID):
    # .hex: raw text() binds are untyped and bypass the ORM UUID type
    # decorator's bind processor, so a bare uuid.UUID fails against sqlite3;
    # the column is physically stored as hex-no-dash under SQLite, so a
    # dashed str(disc_id) would silently match zero rows instead of erroring.
    return db.execute(
        text("SELECT id, fingerprint FROM discs WHERE id = :id"),
        {"id": disc_id.hex},
    ).first()


def _fetch_alias_rows(db: Session, disc_id: uuid.UUID):
    return db.execute(
        text(
            "SELECT id, fingerprint FROM disc_identity_aliases WHERE disc_id = :id"
        ),
        {"id": disc_id.hex},
    ).all()


class TestPromoteOneDisc:
    """Task 1: per-disc promotion + idempotency."""

    def test_promotes_disc_with_dvdread1_alias(self, db_session: Session) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-a",
            dvdread1_fingerprint="dvdread1-promote-a",
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-a")

        assert result is True

        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-a"

        alias_rows = _fetch_alias_rows(db_session, disc.id)
        alias_fingerprints = {row.fingerprint for row in alias_rows}
        assert alias_fingerprints == {"dvd1-promote-a"}, (
            "the OLD dvd1-* value must now exist as the sole alias row; the "
            "dvdread1-* alias row must be gone (deleted, not duplicated)"
        )

    def test_already_promoted_disc_is_safe_noop(self, db_session: Session) -> None:
        # discs.fingerprint no longer equals the dvd1-* value passed in
        # (already promoted, or was never that value) -> False, zero changes.
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvdread1-promote-b",
            dvdread1_fingerprint=None,
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-b")

        assert result is False
        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-b"
        assert _fetch_alias_rows(db_session, disc.id) == []

    def test_disc_with_no_dvdread1_alias_is_safe_noop(
        self, db_session: Session
    ) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-c",
            dvdread1_fingerprint=None,
        )

        result = promote_one_disc(db_session.connection(), "dvd1-promote-c")

        assert result is False
        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvd1-promote-c"
        assert _fetch_alias_rows(db_session, disc.id) == []

    def test_double_invocation_is_idempotent(self, db_session: Session) -> None:
        disc = _seed_disc_with_alias(
            db_session,
            dvd1_fingerprint="dvd1-promote-d",
            dvdread1_fingerprint="dvdread1-promote-d",
        )

        first = promote_one_disc(db_session.connection(), "dvd1-promote-d")
        second = promote_one_disc(db_session.connection(), "dvd1-promote-d")

        assert first is True
        assert second is False, (
            "a second invocation for the same dvd1-* value must be a no-op "
            "(idempotent re-run safety), proven via an actual double call"
        )

        disc_row = _fetch_disc_row(db_session, disc.id)
        assert disc_row.fingerprint == "dvdread1-promote-d"
        alias_rows = _fetch_alias_rows(db_session, disc.id)
        assert {row.fingerprint for row in alias_rows} == {"dvd1-promote-d"}
