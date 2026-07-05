"""Deterministic regression tests for the alias write-path race (IDENT-02).

The in-memory SQLite test harness serializes all writes onto a single
``StaticPool`` connection (see ``conftest.py``), so real thread/process
concurrency cannot be reproduced here — spinning up parallel workers
against it would serialize trivially and prove nothing
(01-RESEARCH.md "Pitfall 1"). Instead these tests inject the *losing-race*
state deterministically: either by pre-inserting the conflicting row before
driving ``attach_lookup_aliases``, or by monkeypatching
``resolve_disc_identity`` to (incorrectly) report a fingerprint as
unresolved even though a genuine UNIQUE-constraint row already exists for
it — exercising the no-wave-off guardrail that a real conflict is never
silently swallowed.

Any monkeypatch is restored in a ``finally`` block (CLAUDE.md symbol-override
rule: save original, override, assert, restore).
"""

import pytest
from sqlalchemy.exc import IntegrityError
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
    """Monkeypatch resolve_disc_identity to simulate a stale read: a genuine
    UNIQUE-violation row exists, but the identity-resolution query
    (temporarily) reports it isn't there. Against the OLD check-then-add
    code this stale read is the pre-insert check itself, so the code
    proceeds to add() a row that the eventual flush/commit then rejects,
    uncaught. Against the NEW insert-first code, the only resolve call left
    is the post-conflict re-resolve inside the except handler — so forcing
    it to (incorrectly) report "no row found" exercises the no-wave-off
    guardrail: the original IntegrityError must propagate rather than be
    silently swallowed or misclassified."""

    def test_reresolve_returning_none_after_genuine_conflict_reraises(
        self, db_session: Session
    ) -> None:
        disc_a = _make_disc(db_session, "dvd1-race-primary-c")
        disc_winner = _make_disc(db_session, "dvd1-race-primary-winner")
        db_session.commit()

        # The alias genuinely already belongs to disc_winner — a real
        # UNIQUE-constraint collision exists for whichever code path
        # attempts to persist it under disc_a.
        db_session.add(
            DiscIdentityAlias(disc_id=disc_winner.id, fingerprint="dvdread1-race-stale")
        )
        db_session.commit()

        original_resolve = disc_identity.resolve_disc_identity

        def _always_stale(db, fingerprint, *, options=()):
            return None

        disc_identity.resolve_disc_identity = _always_stale
        try:
            with pytest.raises(IntegrityError):
                attach_lookup_aliases(
                    db_session,
                    disc_a,
                    "dvd1-race-primary-c",
                    ["dvdread1-race-stale"],
                )
                # Old check-then-add code would not raise from the call
                # itself — force the deferred flush so the real UNIQUE
                # violation surfaces instead of being silently missed.
                db_session.commit()
        finally:
            disc_identity.resolve_disc_identity = original_resolve
            db_session.rollback()

        # The genuine winner must remain the sole owner — no duplicate/split.
        rows = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-race-stale")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].disc_id == disc_winner.id


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
