"""The single guarded writer of disc.status, consolidating scattered inline mutations."""

import uuid

from sqlalchemy.orm import Session

from app.models import Disc, User


class VerificationTransitionError(Exception):
    """Raised when a requested ``disc.status`` transition is not permitted."""

    def __init__(
        self, disc_id: uuid.UUID, current_status: str, attempted_status: str
    ) -> None:
        self.disc_id = disc_id
        self.current_status = current_status
        self.attempted_status = attempted_status
        super().__init__(
            f"Disc '{disc_id}' cannot transition from '{current_status}' "
            f"to '{attempted_status}'"
        )


# Legal general-purpose transitions. NOTE: no tuple targets "disputed" by
# design (D-09) — disputed is reachable ONLY through flag_dispute(), which
# is the sole function that ever writes the disputed status, and it
# refuses to touch a disc that is already verified. This closes the
# silent-flip bug (VERIFY-02 crit #4).
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("unverified", "verified"),
        ("disputed", "verified"),
        ("disputed", "unverified"),
        ("pending_identification", "unverified"),
    }
)


def verify(db: Session, disc: Disc, actor: User) -> bool:
    """Promote ``disc`` toward ``verified``.

    Returns ``False`` (idempotent no-op) when already verified. Raises
    :class:`VerificationTransitionError` when the submitter attempts to
    verify their own submission (D-11) or the transition is illegal.
    """
    if disc.status == "verified":
        return False

    if disc.submitted_by is not None and str(disc.submitted_by) == str(actor.id):
        raise VerificationTransitionError(disc.id, disc.status, "verified")

    if (disc.status, "verified") not in LEGAL_TRANSITIONS:
        raise VerificationTransitionError(disc.id, disc.status, "verified")

    disc.status = "verified"
    disc.verified_by = actor.id
    return True


def identify(db: Session, disc: Disc, actor: User) -> None:
    """Transition a ``pending_identification`` disc to ``unverified``.

    Called when the first release metadata is attached to a disc that was
    pre-registered without metadata (e.g. via ``register_disc()`` for ARM
    — WR-03). Raises :class:`VerificationTransitionError` if ``disc`` is
    not currently ``pending_identification``, matching the guarded-writer
    contract of :func:`verify` and :func:`flag_dispute`.
    """
    if disc.status != "pending_identification":
        raise VerificationTransitionError(disc.id, disc.status, "unverified")

    if (disc.status, "unverified") not in LEGAL_TRANSITIONS:
        raise VerificationTransitionError(disc.id, disc.status, "unverified")

    disc.status = "unverified"


def flag_dispute(db: Session, disc: Disc, actor: User, reason: str) -> bool:
    """Flag ``disc`` as disputed — the ONLY function that writes this status.

    Refuses to touch an already-``verified`` disc: returns ``False`` with
    no write, closing the silent-flip bug (VERIFY-02 crit #4).
    """
    if disc.status == "verified":
        return False

    disc.status = "disputed"
    return True


def resolve_dispute(db: Session, disc: Disc, actor: User, action: str) -> None:
    """Resolve a disputed disc via trusted/editor/admin action.

    ``action="verify"`` promotes to ``verified``; ``action="reject"``
    reverts to ``unverified``. Guarded by :data:`LEGAL_TRANSITIONS`.

    W6: requires ``disc.status == "disputed"`` up front. Without this,
    ``(unverified, "verified") in LEGAL_TRANSITIONS`` (true in general — the
    normal two-contributor auto-verify path uses it) would let this
    function promote a merely-unverified disc straight to verified,
    bypassing structural_match, the anti-Sybil gate, and the self-confirm
    check that ``verify()`` enforces for that same transition elsewhere.
    """
    target = "verified" if action == "verify" else "unverified"
    if disc.status != "disputed":
        raise VerificationTransitionError(disc.id, disc.status, target)
    if (disc.status, target) not in LEGAL_TRANSITIONS:
        raise VerificationTransitionError(disc.id, disc.status, target)

    disc.status = target
    if target == "verified":
        disc.verified_by = actor.id
