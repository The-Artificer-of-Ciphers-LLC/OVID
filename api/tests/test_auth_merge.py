"""Isolated unit tests for the confirm-gated OAuth account-merge resolver.

Covers AUTH-08 (nOAuth defense) and AUTH-09 (isolated resolve_auth unit tests):
- existing-link login returns the linked user with no offer (AUTH-06)
- a PROVIDER-VERIFIED email match creates a PendingAccountLink OFFER, never an
  attach and never a new user (D-05, required case 1)
- an UNVERIFIED colliding email forks a SEPARATE identity, never a merge offer
  and never a unique-email collision (D-06/D-07, required case 2)
- a merge is consumed ONLY when the SAME existing_user_id re-authenticates via an
  already-linked provider; mismatch/expired/consumed fail closed (D-02, req case 3)

These are pure DB-shaped unit tests: resolve_auth takes only DB-shaped args, so
there is NO TestClient, NO Request/session, and NO respx here — just the bare
`db_session` fixture from conftest.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.auth.merge import (
    AuthResult,
    MergeReauthMismatchError,
    PendingLinkInvalidError,
    resolve_auth,
)
from app.models import PendingAccountLink, User, UserOAuthLink


# ---------------------------------------------------------------------------
# Helpers (mirror test_auth_linking.py's _create_user_with_link shape)
# ---------------------------------------------------------------------------

def _create_user_with_link(
    db: Session,
    *,
    username: str = "user1",
    email: str = "user1@example.com",
    email_verified: bool = True,
    provider: str = "github",
    provider_id: str = "gh_111",
    display_name: str = "User One",
) -> tuple[User, UserOAuthLink]:
    """Create a user with one OAuth link (bare-session seeding helper)."""
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email,
        display_name=display_name,
        email_verified=email_verified,
        role="contributor",
    )
    db.add(user)
    db.flush()
    link = UserOAuthLink(
        user_id=user.id,
        provider=provider,
        provider_id=provider_id,
    )
    db.add(link)
    db.commit()
    db.refresh(user)
    return user, link


def _create_pending_link(
    db: Session,
    *,
    existing_user_id: uuid.UUID,
    new_provider: str = "github",
    new_provider_id: str = "gh_new",
    expires_in_minutes: int = 15,
    consumed: bool = False,
) -> PendingAccountLink:
    """Seed a PendingAccountLink OFFER row directly for consume-path tests."""
    now = datetime.now(timezone.utc)
    pending = PendingAccountLink(
        existing_user_id=existing_user_id,
        new_provider=new_provider,
        new_provider_id=new_provider_id,
        expires_at=now + timedelta(minutes=expires_in_minutes),
        consumed_at=now if consumed else None,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return pending


# ---------------------------------------------------------------------------
# Task 1: login / offer / separate-identity path
# ---------------------------------------------------------------------------

class TestResolveAuthLoginOfferSeparate:
    def test_existing_link_login_returns_user_no_offer(self, db_session: Session):
        """AUTH-06: a (provider, provider_id) that already has a link returns that
        user — no offer, no new user."""
        user, _ = _create_user_with_link(
            db_session, provider="github", provider_id="gh_111"
        )
        before = db_session.query(User).count()

        result = resolve_auth(
            db_session,
            provider="github",
            provider_id="gh_111",
            email="user1@example.com",
            email_verified=True,
            display_name="User One",
        )

        assert isinstance(result, AuthResult)
        assert result.merge_offer is None
        assert result.user is not None
        assert str(result.user.id) == str(user.id)
        assert db_session.query(User).count() == before  # no new user

    def test_verified_email_match_creates_offer_no_attach(self, db_session: Session):
        """AUTH-08 / D-05 (required case 1): a provider-verified email that matches
        an existing account creates a PendingAccountLink OFFER, user=None, and does
        NOT attach a link or create a user."""
        owner, _ = _create_user_with_link(
            db_session,
            username="owner",
            email="shared@example.com",
            provider="github",
            provider_id="gh_owner",
        )
        users_before = db_session.query(User).count()
        links_before = db_session.query(UserOAuthLink).count()

        result = resolve_auth(
            db_session,
            provider="google",
            provider_id="g_new",
            email="shared@example.com",
            email_verified=True,
            display_name="Same Person",
        )

        # OFFER, not a merge: no user returned, a pending row exists.
        assert result.user is None
        assert isinstance(result.merge_offer, PendingAccountLink)
        assert str(result.merge_offer.existing_user_id) == str(owner.id)
        assert result.merge_offer.new_provider == "google"
        assert result.merge_offer.new_provider_id == "g_new"
        assert result.merge_offer.consumed_at is None
        # expires_at is in the future (TTL set).
        exp = result.merge_offer.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        assert exp > datetime.now(timezone.utc)

        # No attach, no new user.
        assert db_session.query(User).count() == users_before
        assert db_session.query(UserOAuthLink).count() == links_before
        assert (
            db_session.query(UserOAuthLink)
            .filter(UserOAuthLink.provider == "google", UserOAuthLink.provider_id == "g_new")
            .first()
            is None
        )

    def test_unverified_colliding_email_forks_separate_identity(self, db_session: Session):
        """D-06/D-07 (required case 2): an UNVERIFIED email that collides with an
        existing account forks a SEPARATE new user whose email is NOT the colliding
        address, creates NO pending row, and leaves the existing account untouched."""
        owner, _ = _create_user_with_link(
            db_session,
            username="owner",
            email="shared@example.com",
            provider="github",
            provider_id="gh_owner",
        )

        result = resolve_auth(
            db_session,
            provider="mastodon",
            provider_id="m_1",
            email="shared@example.com",
            email_verified=False,
            display_name="Impersonator?",
        )

        assert result.merge_offer is None
        assert result.user is not None
        # A genuinely separate identity — different user, different email.
        assert str(result.user.id) != str(owner.id)
        assert result.user.email != "shared@example.com"
        # No merge offer was ever persisted.
        assert db_session.query(PendingAccountLink).count() == 0
        # Existing account untouched (still owns the address, no new link on it).
        db_session.refresh(owner)
        assert owner.email == "shared@example.com"
        assert len(owner.oauth_links) == 1

    def test_verified_email_no_owner_creates_normal_user(self, db_session: Session):
        """A verified email nobody owns creates a normal new user+link with
        email_verified=True and merge_offer=None."""
        result = resolve_auth(
            db_session,
            provider="google",
            provider_id="g_2",
            email="fresh@example.com",
            email_verified=True,
            display_name="Fresh User",
        )

        assert result.merge_offer is None
        assert result.user is not None
        assert result.user.email == "fresh@example.com"
        assert result.user.email_verified is True
        assert db_session.query(PendingAccountLink).count() == 0
        link = (
            db_session.query(UserOAuthLink)
            .filter(UserOAuthLink.provider == "google", UserOAuthLink.provider_id == "g_2")
            .first()
        )
        assert link is not None
        assert str(link.user_id) == str(result.user.id)

    def test_explicit_link_path_attaches_link(self, db_session: Session):
        """AUTH-06 explicit linking: link_to_user_id attaches a new provider to that
        user and returns it (no offer)."""
        user, _ = _create_user_with_link(
            db_session, provider="github", provider_id="gh_111"
        )
        users_before = db_session.query(User).count()

        result = resolve_auth(
            db_session,
            provider="google",
            provider_id="g_x",
            email=None,
            email_verified=False,
            display_name=None,
            link_to_user_id=str(user.id),
        )

        assert result.merge_offer is None
        assert result.user is not None
        assert str(result.user.id) == str(user.id)
        assert db_session.query(User).count() == users_before  # no new user
        link = (
            db_session.query(UserOAuthLink)
            .filter(UserOAuthLink.provider == "google", UserOAuthLink.provider_id == "g_x")
            .first()
        )
        assert link is not None
        assert str(link.user_id) == str(user.id)
