"""WR-02 regression: cross-table fingerprint arbitration.

A race between "new disc claims fingerprint F" and "attach F as a Lookup
Alias of a DIFFERENT disc" must never silently split identity. The
``fingerprint_registry`` table's global ``UNIQUE(fingerprint)`` column
arbitrates this atomically, collapsing the cross-table race into the same
insert/IntegrityError/re-resolve convergence idiom already used for
same-table alias races (see test_disc_identity_race.py).

As with test_disc_identity_race.py, the in-memory SQLite test harness
serializes all writes onto a single ``StaticPool`` connection, so real
thread/process concurrency cannot be reproduced here — the losing-race
state is constructed deterministically instead (either by pre-inserting
the conflicting registry row, or by racing a second disc's registration
inside a nested savepoint).
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.disc_identity import attach_lookup_aliases, register_fingerprint
from app.models import Disc, FingerprintRegistry


def _make_disc(db: Session, fingerprint: str, status: str = "unverified") -> Disc:
    disc = Disc(fingerprint=fingerprint, format="DVD", status=status)
    db.add(disc)
    db.flush()
    return disc


class TestRegisterFingerprintArbitration:
    """Direct register_fingerprint() arbitration — the raw helper, no
    attach_lookup_aliases involvement."""

    def test_fresh_fingerprint_registers_successfully(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-wr02-fresh-a")
        db_session.commit()

        register_fingerprint(db_session, "dvd1-wr02-fresh-a", disc_a.id)
        db_session.commit()

        rows = (
            db_session.query(FingerprintRegistry)
            .filter(FingerprintRegistry.fingerprint == "dvd1-wr02-fresh-a")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_a.id

    def test_cross_table_race_is_caught_by_registry(
        self, db_session: Session
    ) -> None:
        """Simulates the exact WR-02 scenario: disc A already registered a
        fingerprint; a second disc B independently attempts to claim the
        SAME fingerprint string (the cross-table "new disc" vs. "alias
        attach" race). The registry's global UNIQUE must reject the second
        claim inside its own savepoint, leaving disc A the sole owner."""
        disc_a = _make_disc(db_session, "dvd1-wr02-race-a")
        db_session.add(
            FingerprintRegistry(fingerprint="dvd1-wr02-shared", disc_id=disc_a.id)
        )
        db_session.commit()

        disc_b = _make_disc(db_session, "dvd1-wr02-race-b")
        db_session.commit()

        raised = False
        try:
            with db_session.begin_nested():
                register_fingerprint(db_session, "dvd1-wr02-shared", disc_b.id)
                db_session.flush()
        except IntegrityError:
            raised = True

        assert raised, (
            "the registry's global UNIQUE(fingerprint) must reject a second "
            "disc claiming an already-registered fingerprint — this is the "
            "exact cross-table split WR-02 exists to prevent"
        )

        db_session.expire_all()
        rows = (
            db_session.query(FingerprintRegistry)
            .filter(FingerprintRegistry.fingerprint == "dvd1-wr02-shared")
            .all()
        )
        assert len(rows) == 1, "no duplicate/split registry row after the losing race"
        assert rows[0].disc_id == disc_a.id


class TestAttachLookupAliasesRegistryIntegration:
    """Proves the wiring itself: attach_lookup_aliases() must register every
    new Lookup Alias fingerprint into fingerprint_registry inside the same
    savepoint, not just the raw helper in isolation."""

    def test_new_alias_is_registered_exactly_once(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-wr02-integ-a")
        db_session.commit()

        attach_lookup_aliases(
            db_session, disc_a, "dvd1-wr02-integ-a", ["dvdread1-wr02-integ-alias"]
        )
        db_session.commit()

        rows = (
            db_session.query(FingerprintRegistry)
            .filter(FingerprintRegistry.fingerprint == "dvdread1-wr02-integ-alias")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_a.id

    def test_cross_disc_alias_collision_still_raises_conflict_and_registry_unchanged(
        self, db_session: Session
    ) -> None:
        """A same-table alias collision now ALSO independently violates the
        registry's UNIQUE — either constraint surfacing as IntegrityError
        must converge to the identical existing recovery path, and the
        registry must retain exactly one row for the contested fingerprint."""
        disc_a = _make_disc(db_session, "dvd1-wr02-integ-b")
        disc_b = _make_disc(db_session, "dvd1-wr02-integ-c")
        db_session.commit()

        # disc_b already owns this alias (and its registry entry).
        attach_lookup_aliases(
            db_session, disc_b, "dvd1-wr02-integ-c", ["dvdread1-wr02-integ-conflict"]
        )
        db_session.commit()

        from app.disc_identity import DiscIdentityConflict

        raised = False
        try:
            attach_lookup_aliases(
                db_session,
                disc_a,
                "dvd1-wr02-integ-b",
                ["dvdread1-wr02-integ-conflict"],
            )
        except DiscIdentityConflict as exc:
            raised = True
            assert exc.existing_disc.id == disc_b.id

        assert raised, "expected DiscIdentityConflict for genuine cross-disc collision"

        db_session.expire_all()
        registry_rows = (
            db_session.query(FingerprintRegistry)
            .filter(FingerprintRegistry.fingerprint == "dvdread1-wr02-integ-conflict")
            .all()
        )
        assert len(registry_rows) == 1
        assert registry_rows[0].disc_id == disc_b.id
