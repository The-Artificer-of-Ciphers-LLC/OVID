"""Unit tests for the guarded verification state machine (app.verification)."""

from sqlalchemy.orm import Session

from app.models import Disc
from app.verification import (
    LEGAL_TRANSITIONS,
    VerificationTransitionError,
    flag_dispute,
    identify,
    resolve_dispute,
    verify,
)
from tests.conftest import seed_second_user, seed_test_user


def _make_disc(db: Session, status: str, submitted_by_id=None) -> Disc:
    """Build a bare disc row for state-machine unit tests (no HTTP layer)."""
    disc = Disc(
        fingerprint=f"dvd-VERIFY-{status}-{id(object())}",
        format="DVD",
        status=status,
        submitted_by=submitted_by_id,
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)
    return disc


class TestLegalTransitions:
    def test_legal_transitions_exact_set(self):
        assert LEGAL_TRANSITIONS == frozenset(
            {
                ("unverified", "verified"),
                ("disputed", "verified"),
                ("disputed", "unverified"),
                ("pending_identification", "unverified"),
            }
        )

    def test_no_transition_targets_disputed(self):
        """D-09: disputed is reachable ONLY through flag_dispute, never the table."""
        for _from, to in LEGAL_TRANSITIONS:
            assert to != "disputed"


class TestVerify:
    def test_verify_unverified_disc_returns_true_and_sets_verified(self, db_session):
        actor = seed_test_user(db_session)
        submitter = seed_second_user(db_session)
        disc = _make_disc(db_session, "unverified", submitted_by_id=submitter.id)

        result = verify(db_session, disc, actor)

        assert result is True
        assert disc.status == "verified"
        assert str(disc.verified_by) == str(actor.id)

    def test_verify_already_verified_disc_returns_false_idempotent(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "verified")

        result = verify(db_session, disc, actor)

        assert result is False
        assert disc.status == "verified"

    def test_verify_self_submission_raises(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "unverified", submitted_by_id=actor.id)

        try:
            verify(db_session, disc, actor)
            assert False, "expected VerificationTransitionError"
        except VerificationTransitionError as exc:
            assert exc.attempted_status == "verified"
            assert exc.disc_id == disc.id
            assert exc.current_status == "unverified"

    def test_verify_disputed_disc_returns_true(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "disputed")

        result = verify(db_session, disc, actor)

        assert result is True
        assert disc.status == "verified"

    def test_verify_already_verified_disc_by_original_submitter_is_idempotent(
        self, db_session
    ):
        """WR-01: the idempotency no-op must run BEFORE the self-submission
        guard. A disc already verified by someone else, then the ORIGINAL
        submitter calls verify() again, must get the same idempotent no-op
        every other caller gets — not a spurious VerificationTransitionError.
        """
        submitter = seed_test_user(db_session)
        other = seed_second_user(db_session)
        disc = _make_disc(db_session, "unverified", submitted_by_id=submitter.id)

        # Another contributor verifies it first.
        first_result = verify(db_session, disc, other)
        assert first_result is True
        assert disc.status == "verified"

        # The original submitter re-calling verify() must be a no-op, not
        # a self-submission error.
        result = verify(db_session, disc, submitter)

        assert result is False
        assert disc.status == "verified"


class TestFlagDispute:
    def test_flag_dispute_refuses_verified_disc(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "verified")

        result = flag_dispute(db_session, disc, actor, reason="metadata mismatch")

        assert result is False
        assert disc.status == "verified"

    def test_flag_dispute_unverified_disc_returns_true(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "unverified")

        result = flag_dispute(db_session, disc, actor, reason="metadata mismatch")

        assert result is True
        assert disc.status == "disputed"


class TestIdentify:
    """WR-03: the sole legal path from pending_identification to unverified."""

    def test_identify_pending_identification_disc_sets_unverified(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "pending_identification")

        identify(db_session, disc, actor)

        assert disc.status == "unverified"

    def test_identify_non_pending_disc_raises(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "unverified")

        try:
            identify(db_session, disc, actor)
            assert False, "expected VerificationTransitionError"
        except VerificationTransitionError as exc:
            assert exc.current_status == "unverified"
            assert exc.attempted_status == "unverified"


class TestResolveDispute:
    def test_resolve_dispute_verify_action_sets_verified(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "disputed")

        resolve_dispute(db_session, disc, actor, action="verify")

        assert disc.status == "verified"

    def test_resolve_dispute_reject_action_sets_unverified(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "disputed")

        resolve_dispute(db_session, disc, actor, action="reject")

        assert disc.status == "unverified"


class TestVerificationTransitionError:
    def test_error_carries_structured_attributes(self, db_session):
        actor = seed_test_user(db_session)
        disc = _make_disc(db_session, "unverified", submitted_by_id=actor.id)

        try:
            verify(db_session, disc, actor)
            assert False, "expected VerificationTransitionError"
        except VerificationTransitionError as exc:
            assert exc.disc_id == disc.id
            assert exc.current_status == "unverified"
            assert exc.attempted_status == "verified"
