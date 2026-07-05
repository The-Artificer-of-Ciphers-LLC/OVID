"""Deterministic regression tests for the alias write-path race (IDENT-02).

The in-memory SQLite test harness serializes all writes onto a single
``StaticPool`` connection (see ``conftest.py``), so real thread/process
concurrency cannot be reproduced here — spinning up parallel workers
against it would serialize trivially and prove nothing
(01-RESEARCH.md "Pitfall 1"). Instead these tests inject the *losing-race*
state deterministically: either by pre-inserting the conflicting row before
driving ``attach_lookup_aliases``, or by monkeypatching
``resolve_disc_identity`` to simulate a stale read (returning ``None``) on
its first call while the row already exists underneath it.

Any monkeypatch is restored in a ``finally`` block (CLAUDE.md symbol-override
rule: save original, override, assert, restore).
"""

import uuid

from sqlalchemy.orm import Session

import app.disc_identity as disc_identity
from app.disc_identity import (
    DiscIdentityConflict,
    attach_lookup_aliases,
)
from app.models import Disc, DiscIdentityAlias


def _make_disc(db: Session, fingerprint: str, status: str = "unverified") -> Disc:
    disc = Disc(fingerprint=fingerprint, format="DVD", status=status)
    db.add(disc)
    db.flush()
    return disc


class TestAliasLosingRacePreInserted:
    """The conflicting alias row already exists (pre-inserted) before our
    disc attempts to attach the same alias fingerprint — simulates a worker
    that lost the race and is now retrying/re-resolving."""

    def test_own_disc_already_owns_alias_converges_no_duplicate(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-a")
        db_session.commit()

        # Alias already attached to disc A (simulates the winning insert that
        # already landed before this call runs).
        db_session.add(
            DiscIdentityAlias(disc_id=disc_a.id, fingerprint="dvdread1-race-alias")
        )
        db_session.commit()

        # Re-driving attach_lookup_aliases for the SAME disc + SAME alias must
        # converge to exactly one alias row owned by disc A — no duplicate,
        # no unhandled IntegrityError.
        attach_lookup_aliases(
            db_session, disc_a, "dvd1-race-primary-a", ["dvdread1-race-alias"]
        )
        db_session.commit()

        rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-alias")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_a.id

    def test_cross_disc_collision_still_raises_conflict(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-a2")
        disc_b = _make_disc(db_session, "dvd1-race-primary-b2")
        db_session.commit()

        # Alias already belongs to disc B (a genuinely different pressing).
        db_session.add(
            DiscIdentityAlias(disc_id=disc_b.id, fingerprint="dvdread1-race-conflict")
        )
        db_session.commit()

        try:
            attach_lookup_aliases(
                db_session, disc_a, "dvd1-race-primary-a2", ["dvdread1-race-conflict"]
            )
            raised = False
        except DiscIdentityConflict as exc:
            raised = True
            assert exc.existing_disc.id == disc_b.id

        assert raised, "expected DiscIdentityConflict for genuine cross-disc collision"

        # The conflict must not have been silently swallowed into a duplicate
        # row owned by disc A.
        rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-conflict")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_b.id


class TestAliasLosingRaceStaleRead:
    """Monkeypatch resolve_disc_identity to return None on its first call —
    simulating a stale read that occurred BEFORE a concurrent worker's
    insert landed — while the alias row already exists underneath it."""

    def test_stale_read_then_conflicting_insert_converges_to_winner(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-c")
        disc_winner = _make_disc(db_session, "dvd1-race-primary-winner")
        db_session.commit()

        # The alias already belongs to disc_winner (the "other worker" that
        # won the race), but our stale read (monkeypatched below) won't see
        # it on the first call.
        db_session.add(
            DiscIdentityAlias(disc_id=disc_winner.id, fingerprint="dvdread1-race-stale")
        )
        db_session.commit()

        original_resolve = disc_identity.resolve_disc_identity
        call_count = {"n": 0}

        def _stale_first_call(db, fingerprint, *, options=()):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return original_resolve(db, fingerprint, options=options)

        disc_identity.resolve_disc_identity = _stale_first_call
        try:
            try:
                attach_lookup_aliases(
                    db_session,
                    disc_a,
                    "dvd1-race-primary-c",
                    ["dvdread1-race-stale"],
                )
                raised = False
            except DiscIdentityConflict as exc:
                raised = True
                assert exc.existing_disc.id == disc_winner.id
        finally:
            disc_identity.resolve_disc_identity = original_resolve

        # disc_winner is a DIFFERENT disc than disc_a, so this must surface
        # as a genuine cross-disc conflict, not a silent swallow.
        assert raised, "expected DiscIdentityConflict when stale read collides cross-disc"

        rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-stale")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_winner.id

    def test_stale_read_own_disc_conflict_is_idempotent_noop(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-d")
        db_session.commit()

        # Alias already belongs to disc_a itself (our own prior insert that
        # the stale read below won't see on its first call).
        db_session.add(
            DiscIdentityAlias(disc_id=disc_a.id, fingerprint="dvdread1-race-ownstale")
        )
        db_session.commit()

        original_resolve = disc_identity.resolve_disc_identity
        call_count = {"n": 0}

        def _stale_first_call(db, fingerprint, *, options=()):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None
            return original_resolve(db, fingerprint, options=options)

        disc_identity.resolve_disc_identity = _stale_first_call
        try:
            attach_lookup_aliases(
                db_session,
                disc_a,
                "dvd1-race-primary-d",
                ["dvdread1-race-ownstale"],
            )
            db_session.commit()
        finally:
            disc_identity.resolve_disc_identity = original_resolve

        rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-ownstale")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_a.id


class TestSiblingAliasSurvivesSavepointScope:
    """In a multi-alias submission [a1, a2], a2 losing its race must NOT
    roll back a1's already-committed insert (savepoint scope, not the
    whole outer transaction)."""

    def test_sibling_alias_insert_survives_losing_race(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-e")
        disc_other = _make_disc(db_session, "dvd1-race-primary-other")
        db_session.commit()

        # a2's fingerprint already belongs to a DIFFERENT disc, so attaching
        # both [a1, a2] together must: insert a1 successfully, then raise
        # DiscIdentityConflict for a2 — without discarding a1.
        db_session.add(
            DiscIdentityAlias(disc_id=disc_other.id, fingerprint="dvdread1-race-a2")
        )
        db_session.commit()

        try:
            attach_lookup_aliases(
                db_session,
                disc_a,
                "dvd1-race-primary-e",
                ["dvdread1-race-a1", "dvdread1-race-a2"],
            )
            raised = False
        except DiscIdentityConflict:
            raised = True

        assert raised, "expected DiscIdentityConflict on the second (a2) alias"

        db_session.expire_all()
        a1_rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-a1")
            .all()
        )
        assert len(a1_rows) == 1, "sibling alias a1 must survive a2's savepoint rollback"
        assert a1_rows[0].disc_id == disc_a.id


class TestNoStaleSessionStateAfterCaughtConflict:
    """After a caught IntegrityError, the session must not be left in a
    PendingRollbackError / stale-identity-map state — a subsequent
    resolve must return the winner cleanly."""

    def test_subsequent_resolve_after_conflict_is_clean(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-f")
        disc_winner = _make_disc(db_session, "dvd1-race-primary-winner2")
        db_session.commit()

        db_session.add(
            DiscIdentityAlias(disc_id=disc_winner.id, fingerprint="dvdread1-race-clean")
        )
        db_session.commit()

        try:
            attach_lookup_aliases(
                db_session, disc_a, "dvd1-race-primary-f", ["dvdread1-race-clean"]
            )
        except DiscIdentityConflict:
            pass

        # The session must still be usable — no PendingRollbackError.
        from app.disc_identity import resolve_disc_identity

        resolution = resolve_disc_identity(db_session, "dvdread1-race-clean")
        assert resolution is not None
        assert resolution.disc.id == disc_winner.id
