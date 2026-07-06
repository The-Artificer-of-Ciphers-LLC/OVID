"""D-02 registry backfill transform: ``backfill_fingerprint_registry``.

Tests the plain, Alembic-independent function in ``app.migrations_support``
directly against the project's in-memory SQLite harness — no Alembic
invocation anywhere in this file (Pitfall 5: CI never runs a real
``alembic upgrade head`` against Postgres, so this transform must be
provable without one).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.migrations_support import backfill_fingerprint_registry
from app.models import Disc, DiscIdentityAlias


def _seed_disc(db: Session, fingerprint: str) -> Disc:
    disc = Disc(fingerprint=fingerprint, format="DVD", status="verified")
    db.add(disc)
    db.flush()
    return disc


class TestBackfillFingerprintRegistry:
    """Task 1: one-time registry backfill from BOTH source tables."""

    def test_backfills_from_discs_and_aliases_with_counts(
        self, db_session: Session
    ) -> None:
        disc_a = _seed_disc(db_session, "dvd1-backfill-a")
        disc_b = _seed_disc(db_session, "dvd1-backfill-b")
        db_session.add(
            DiscIdentityAlias(disc_id=disc_a.id, fingerprint="dvdread1-backfill-a")
        )
        db_session.add(
            DiscIdentityAlias(disc_id=disc_b.id, fingerprint="dvdread1-backfill-b")
        )
        db_session.add(
            DiscIdentityAlias(disc_id=disc_b.id, fingerprint="dvd1-backfill-b-old")
        )
        db_session.commit()

        discs_count, aliases_count = backfill_fingerprint_registry(
            db_session.connection()
        )
        db_session.commit()

        assert discs_count == 2
        assert aliases_count == 3

        total_rows = db_session.execute(
            text("SELECT COUNT(*) FROM fingerprint_registry")
        ).scalar()
        assert total_rows == discs_count + aliases_count == 5

        registered_fingerprints = {
            row[0]
            for row in db_session.execute(
                text("SELECT fingerprint FROM fingerprint_registry")
            ).all()
        }
        assert registered_fingerprints == {
            "dvd1-backfill-a",
            "dvd1-backfill-b",
            "dvdread1-backfill-a",
            "dvdread1-backfill-b",
            "dvd1-backfill-b-old",
        }

    def test_is_dialect_portable_via_python_generated_uuids(
        self, db_session: Session
    ) -> None:
        """Each new registry row's id is generated in Python (uuid.uuid4()),
        not via a database-side UUID-generation function, so this transform
        is directly exercised against SQLite (not skipped/mocked)."""
        disc = _seed_disc(db_session, "dvd1-backfill-c")
        db_session.commit()

        discs_count, aliases_count = backfill_fingerprint_registry(
            db_session.connection()
        )
        db_session.commit()

        assert discs_count == 1
        assert aliases_count == 0

        row = db_session.execute(
            text(
                "SELECT id, fingerprint, disc_id FROM fingerprint_registry "
                "WHERE fingerprint = :fp"
            ),
            {"fp": "dvd1-backfill-c"},
        ).first()
        assert row is not None
        # id is a 32-char hex string (uuid.uuid4().hex), generated in Python.
        assert isinstance(row.id, str)
        assert len(row.id) == 32
        assert row.disc_id == disc.id.hex
