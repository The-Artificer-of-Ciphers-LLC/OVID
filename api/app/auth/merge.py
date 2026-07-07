"""Confirm-gated OAuth account-merge resolver (nOAuth defense — AUTH-08/AUTH-09).

`resolve_auth` is the single, pure, session-free choke point that decides — from
DB-shaped inputs alone (no ``Request``/session) — whether a provider login:

1. logs into an existing linked account (AUTH-06),
2. OFFERS a merge (a provider-VERIFIED email that matches an existing account →
   a ``PendingAccountLink`` row, **never** an attach and **never** a new user;
   D-05), or
3. creates a SEPARATE identity (unverified / non-matching email; D-06/D-07).

A pending merge is consumed ONLY when the SAME ``existing_user_id`` re-authenticates
via an ALREADY-linked provider (the trust anchor). The new provider's email is never
trusted as proof of ownership — that is the exact nOAuth vulnerability this closes
(D-01/D-02, RESEARCH Pitfall 1).

This module is additive and self-contained: it copies (does not import or mutate)
``users.py``'s upsert/exception shapes so the live login path is untouched at the
Wave 2 boundary. Plan 05 rewires the provider callbacks to call ``resolve_auth``.
"""

import logging
import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import PendingAccountLink, User, UserOAuthLink

logger = logging.getLogger(__name__)

# TTL for a merge OFFER — the window in which the existing account must re-auth.
_PENDING_LINK_TTL_MINUTES = 15
# Placeholder-email suffix (matches users.py) — a claimed address ending in this is
# never treated as a real, ownable email for the merge/collision decision.
_PLACEHOLDER_EMAIL_SUFFIX = "@noemail.placeholder"


# ---------------------------------------------------------------------------
# Domain exceptions (copy users.py's Exception-subclass shape)
# ---------------------------------------------------------------------------
class MergeReauthMismatchError(Exception):
    """A pending-merge consume was attempted without proving ownership of the
    existing account via an ALREADY-linked provider re-auth. Fail closed — never
    trust the new provider's email (nOAuth defense, D-02)."""


class PendingLinkInvalidError(Exception):
    """A pending link is missing, expired, or already consumed (single-use + TTL)."""


@dataclass
class AuthResult:
    """Outcome of ``resolve_auth``.

    Exactly one of ``user`` / ``merge_offer`` is populated for a given login:
    a login/consume/new-identity yields ``user``; a verified-email match yields a
    ``merge_offer`` (``PendingAccountLink``) with ``user is None``.
    """

    user: "User | None"
    merge_offer: "PendingAccountLink | None" = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    """Normalize a DB datetime to timezone-aware UTC.

    ``DateTime(timezone=True)`` columns round-trip as tz-aware on PostgreSQL but as
    NAIVE on SQLite (test engine); comparing a naive value against an aware ``now``
    raises ``TypeError``. Mirror ``app/anti_sybil.py``'s normalization so the TTL
    comparison is correct cross-platform.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _resolve_existing_link(db: Session, provider: str, provider_id: str) -> "User | None":
    """Return the User owning the (provider, provider_id) link, or None.

    Copies ``user_upsert``'s link-lookup query shape (users.py:39-46).
    """
    link = (
        db.query(UserOAuthLink)
        .filter(
            UserOAuthLink.provider == provider,
            UserOAuthLink.provider_id == provider_id,
        )
        .first()
    )
    return link.user if link is not None else None


def _create_user_with_link(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: str | None,
    email_verified: bool,
    display_name: str | None,
) -> User:
    """Create a new User + UserOAuthLink (copy of ``user_upsert``'s create block).

    Unlike ``user_upsert``, ``email_verified`` is passed through from the caller's
    per-provider verified signal — NOT the old hardcoded ``provider == "github"``
    heuristic. ``email=None`` falls back to a provider-scoped placeholder so the
    unique-email constraint is never violated (D-07 separate identity).
    """
    user = User(
        username=f"{provider}_{provider_id}",
        email=email or f"{provider}_{provider_id}{_PLACEHOLDER_EMAIL_SUFFIX}",
        display_name=display_name,
        email_verified=email_verified,
    )
    db.add(user)
    db.flush()

    db.add(UserOAuthLink(user_id=user.id, provider=provider, provider_id=provider_id))
    db.commit()
    db.refresh(user)

    logger.info("auth_resolve provider=%s user_id=%s (new)", provider, user.id)
    return user


def _load_pending_link(db: Session, pending_link_id: str) -> PendingAccountLink:
    """Load a PendingAccountLink by id, raising if the id is malformed or missing."""
    try:
        _pid = _uuid.UUID(pending_link_id) if isinstance(pending_link_id, str) else pending_link_id
    except (ValueError, AttributeError):
        raise PendingLinkInvalidError("Invalid pending link id")
    pending = db.query(PendingAccountLink).filter(PendingAccountLink.id == _pid).first()
    if pending is None:
        raise PendingLinkInvalidError("Pending link not found")
    return pending


def _consume_pending_link(db: Session, pending: PendingAccountLink) -> None:
    """Mark a pending link single-use consumed and commit."""
    pending.consumed_at = _utcnow()
    db.commit()


# ---------------------------------------------------------------------------
# Public resolver
# ---------------------------------------------------------------------------
def resolve_auth(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: str | None,
    email_verified: bool,
    display_name: str | None,
    link_to_user_id: str | None = None,
    pending_link_id: str | None = None,
) -> AuthResult:
    """Resolve a provider login into an ``AuthResult`` (pure — no Request/session).

    Non-pending path (this plan):
    1. Existing (provider, provider_id) link → log into that user.
    2. ``link_to_user_id`` set → explicit link a new provider to that user.
    3. New identity with a provider-VERIFIED email matching an existing account →
       create a ``PendingAccountLink`` OFFER (no attach, no new user).
    4. Otherwise → create a SEPARATE identity (placeholder email if the claimed
       address would collide).

    Pending-merge consume path (leading ``pending_link_id`` branch): reject the offer
    unless the SAME ``existing_user_id`` re-authenticates via an ALREADY-linked
    provider (single-use + TTL enforced; fail closed on mismatch/expiry/reuse).
    """
    # 0. Pending-merge consume (re-auth required). Runs first so a presented
    #    pending_link_id is always validated against the freshly-authed identity.
    if pending_link_id is not None:
        pending = _load_pending_link(db, pending_link_id)
        # Single-use + TTL are the primary guards — check before any attach.
        if pending.consumed_at is not None:
            logger.info("pending_link_rejected reason=consumed pending_link_id=%s", pending.id)
            raise PendingLinkInvalidError("Pending link already consumed")
        if _ensure_aware(pending.expires_at) <= _utcnow():
            logger.info("pending_link_rejected reason=expired pending_link_id=%s", pending.id)
            raise PendingLinkInvalidError("Pending link expired")

        # The trust anchor: the re-auth must resolve to an ALREADY-linked provider
        # owned by the SAME existing account. Never trust the new provider's email.
        freshly = _resolve_existing_link(db, provider, provider_id)
        if freshly is None or str(freshly.id) != str(pending.existing_user_id):
            logger.info(
                "merge_reauth_mismatch pending_link_id=%s provider=%s",
                pending.id,
                provider,
            )
            raise MergeReauthMismatchError(
                "Re-authentication did not prove ownership of the existing account"
            )

        # Attach the new provider to the existing user. Guard against a duplicate
        # link so a race/double-consume can't crash (consumed_at is the real guard).
        if _resolve_existing_link(db, pending.new_provider, pending.new_provider_id) is None:
            db.add(
                UserOAuthLink(
                    user_id=freshly.id,
                    provider=pending.new_provider,
                    provider_id=pending.new_provider_id,
                )
            )
        _consume_pending_link(db, pending)  # commits the attach + consumed_at
        db.refresh(freshly)
        logger.info(
            "pending_link_consumed existing_user_id=%s new_provider=%s",
            pending.existing_user_id,
            pending.new_provider,
        )
        return AuthResult(user=freshly, merge_offer=None)

    # 1. Existing-link login (AUTH-06).
    existing = _resolve_existing_link(db, provider, provider_id)
    if existing is not None:
        logger.info("auth_resolve provider=%s user_id=%s (existing)", provider, existing.id)
        return AuthResult(user=existing, merge_offer=None)

    # 2. Explicit link (AUTH-06 explicit path).
    if link_to_user_id is not None:
        try:
            _uid = _uuid.UUID(link_to_user_id) if isinstance(link_to_user_id, str) else link_to_user_id
        except (ValueError, AttributeError):
            raise ValueError("Invalid user ID for explicit linking")
        user = db.query(User).filter(User.id == _uid).first()
        if not user:
            raise ValueError("User not found for explicit linking")
        db.add(UserOAuthLink(user_id=user.id, provider=provider, provider_id=provider_id))
        db.commit()
        db.refresh(user)
        logger.info("auth_resolve provider=%s linked to user_id=%s", provider, user.id)
        return AuthResult(user=user, merge_offer=None)

    # 3/4. New identity — verified-email merge OFFER vs. separate identity.
    claimed_email = (
        email if (email and not email.endswith(_PLACEHOLDER_EMAIL_SUFFIX)) else None
    )
    owner = (
        db.query(User).filter(User.email == claimed_email).first()
        if claimed_email is not None
        else None
    )

    # The verified-email gate is the SINGLE choke point that turns a provider email
    # claim into a merge OFFER (never an attach) — the confirm-gate that closes
    # nOAuth. Only a provider-VERIFIED signal on a matching existing account offers.
    if email_verified and claimed_email is not None and owner is not None:
        pending = PendingAccountLink(
            existing_user_id=owner.id,
            new_provider=provider,
            new_provider_id=provider_id,
            expires_at=_utcnow() + timedelta(minutes=_PENDING_LINK_TTL_MINUTES),
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        logger.info(
            "pending_link_created existing_user_id=%s new_provider=%s",
            owner.id,
            provider,
        )
        return AuthResult(user=None, merge_offer=pending)

    # Separate identity. If the claimed email would collide with an existing account
    # (unverified match, or any non-offer case), drop to a placeholder email so the
    # unique-email constraint blocks a silent overwrite (D-07).
    safe_email = None if owner is not None else claimed_email
    user = _create_user_with_link(
        db,
        provider=provider,
        provider_id=provider_id,
        email=safe_email,
        email_verified=email_verified,
        display_name=display_name,
    )
    return AuthResult(user=user, merge_offer=None)
