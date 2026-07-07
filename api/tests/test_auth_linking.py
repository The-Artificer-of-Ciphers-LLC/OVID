"""Tests for account linking & confirm-gated email-merge resolution.

Covers:
- 409 Conflict carrying pending_link_id on a PROVIDER-VERIFIED email match (merge OFFER)
- a merge completes ONLY via re-auth through an already-linked provider (nOAuth defense)
- a plain login (no pending_link_id) never merges — the removed session-implicit-merge flaw
- an unverified provider profile email (e.g. GitHub GET /user) never triggers a merge
- Explicit /link and /unlink endpoints
- Cannot unlink the last provider
- Negative tests: invalid provider, already-linked provider, non-linked provider
- Boundary: provider linked to another user during explicit link
"""

import uuid
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.models import User, UserOAuthLink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user_with_link(
    db: Session,
    *,
    username: str = "user1",
    email: str = "user1@example.com",
    provider: str = "github",
    provider_id: str = "gh_111",
    display_name: str = "User One",
) -> tuple[User, UserOAuthLink]:
    """Create a user with one OAuth link."""
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email,
        display_name=display_name,
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


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


def _github_oauth_mocks(github_id=99999, email="shared@example.com", name="GH User", login="ghuser"):
    """Prepare mocked authlib OAuth client for GitHub login + callback.

    GitHub's GET /user profile email is intentionally NOT a verified signal; the
    mocked `get` returns the same profile dict for the (post-Task-2) GET /user/emails
    call too — which the callback treats as "no primary+verified entry" (a dict is not
    the expected list), so GitHub logins through this mock are always email_verified=False.
    """
    gh_user = {"id": github_id, "email": email, "name": name, "login": login}
    mock_oauth = MagicMock()
    mock_oauth.github.authorize_access_token = AsyncMock(return_value={"access_token": "gho_fake"})
    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = gh_user
    mock_oauth.github.get = AsyncMock(return_value=resp_mock)
    from starlette.responses import JSONResponse
    mock_oauth.github.authorize_redirect = AsyncMock(return_value=JSONResponse(content={"ok": True}))
    return mock_oauth


def _google_oauth_mocks(sub="google_123", email="shared@example.com", name="Google User", email_verified=True):
    """Prepare mocked authlib OAuth client for Google login + callback.

    Google is an OIDC provider whose id_token authlib has already verified, so its
    userinfo carries a trustworthy email_verified claim — defaulted True here to drive
    the verified-email merge-offer path.
    """
    userinfo = {"sub": sub, "email": email, "name": name, "email_verified": email_verified}
    mock_oauth = MagicMock()
    mock_oauth.google.authorize_access_token = AsyncMock(
        return_value={"access_token": "ya29_fake", "userinfo": userinfo}
    )
    from starlette.responses import JSONResponse
    mock_oauth.google.authorize_redirect = AsyncMock(return_value=JSONResponse(content={"ok": True}))
    return mock_oauth


# ---------------------------------------------------------------------------
# Tests: Email Conflict → 409
# ---------------------------------------------------------------------------

class TestEmailConflict:
    """A PROVIDER-VERIFIED email already in use yields a 409 merge OFFER carrying a
    pending_link_id; an UNVERIFIED colliding email forks a separate identity instead."""

    def test_google_verified_email_conflict_returns_409_with_pending_link(self, client: TestClient, db_session: Session):
        """A Google login (verified email) matching an existing account returns 409 with
        a pending_link_id backed by a real PendingAccountLink row — and MUST NOT leak the
        internal existing_user_id (ME-02: user/UUID enumeration)."""
        existing_user, _ = _create_user_with_link(
            db_session, username="existing", email="shared@example.com",
            provider="github", provider_id="gh_existing",
        )

        mock_oauth = _google_oauth_mocks(sub="google_new_123", email="shared@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/google/callback", params={"code": "test_code", "state": "s"})

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "email_conflict"
        assert "existing_user_id" not in body
        assert "pending_link_id" in body

        # pending_link_id must reference a real, unconsumed offer for the existing user.
        from app.models import PendingAccountLink
        pending = db_session.query(PendingAccountLink).filter(
            PendingAccountLink.id == uuid.UUID(body["pending_link_id"])
        ).first()
        assert pending is not None
        assert str(pending.existing_user_id) == str(existing_user.id)
        assert pending.new_provider == "google"
        assert pending.consumed_at is None

    def test_github_unverified_profile_email_does_not_merge(self, client: TestClient, db_session: Session):
        """GitHub's GET /user profile email is not a verified signal (Pitfall 2): a
        colliding-but-unverified GitHub login forks a SEPARATE identity, never a merge."""
        existing_user, _ = _create_user_with_link(
            db_session, username="existing", email="shared@example.com",
            provider="google", provider_id="goog_existing",
        )

        mock_oauth = _github_oauth_mocks(github_id=55555, email="shared@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/github/callback", params={"code": "test_code", "state": "s"})

        # No merge, no offer: a separate identity is created (unverified email dropped).
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["id"] != str(existing_user.id)

        from app.models import PendingAccountLink
        assert db_session.query(PendingAccountLink).count() == 0
        # Existing account untouched — still owns the address, still one link.
        db_session.expire_all()
        db_session.refresh(existing_user)
        assert existing_user.email == "shared@example.com"
        assert len(existing_user.oauth_links) == 1

    def test_placeholder_email_does_not_trigger_conflict(self, client: TestClient, db_session: Session):
        """Placeholder emails (@noemail.placeholder) should never trigger a 409."""
        _create_user_with_link(
            db_session, username="existing",
            email="github_999@noemail.placeholder",
            provider="github", provider_id="gh_999",
        )

        # Login with null email — user_upsert generates a placeholder that should not conflict
        mock_oauth = _github_oauth_mocks(github_id=888, email=None, name="No Email", login="noemail")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/github/callback", params={"code": "test_code", "state": "s"})

        assert resp.status_code == 200
        assert "token" in resp.json()

    def test_same_provider_same_id_returns_existing_user_not_conflict(self, client: TestClient, db_session: Session):
        """Re-logging in with the same provider+id should return the existing user, not 409."""
        user, _ = _create_user_with_link(
            db_session, username="returning", email="returning@example.com",
            provider="github", provider_id="42",
        )

        mock_oauth = _github_oauth_mocks(github_id=42, email="returning@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/github/callback", params={"code": "c", "state": "s"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["id"] == str(user.id)


# ---------------------------------------------------------------------------
# Tests: Confirm-gated merge via re-auth (nOAuth defense)
# ---------------------------------------------------------------------------

class TestReauthMerge:
    """A verified-email merge OFFER completes ONLY when the existing account re-auths
    through an already-linked provider carrying pending_link_id. A plain login never
    merges (the removed session-implicit-merge flaw)."""

    def test_verified_merge_completes_only_via_reauth(self, client: TestClient, db_session: Session):
        """
        Flow (nOAuth-safe):
        1. User A exists, linked via GitHub, email shared@example.com.
        2. A new Google login (verified, shared@example.com) → 409 + pending_link_id.
        3. User A re-authenticates via GitHub (already-linked) carrying pending_link_id
           → the Google provider is attached to User A and a JWT for A is issued.
        """
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="shared@example.com",
            provider="github", provider_id="gh_a",
        )

        # Step 2: verified Google login for the NEW provider → 409 offer.
        mock_google = _google_oauth_mocks(sub="goog_new", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            offer = client.get("/v1/auth/google/callback", params={"code": "c1", "state": "s1"})

        assert offer.status_code == 409
        pending_link_id = offer.json()["pending_link_id"]

        # Step 3: re-auth via GitHub (already-linked) carrying pending_link_id in session.
        mock_gh = _github_oauth_mocks(github_id="gh_a", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_gh))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            # /login stashes pending_link_id into the session; the callback consumes it.
            client.get("/v1/auth/github/login", params={"pending_link_id": pending_link_id})
            resp = client.get("/v1/auth/github/callback", params={"code": "c2", "state": "s2"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["id"] == str(user_a.id)

        # The Google provider is now attached to User A.
        db_session.expire_all()
        links = db_session.query(UserOAuthLink).filter_by(user_id=user_a.id).all()
        providers = {l.provider for l in links}
        assert providers == {"github", "google"}

        # The offer is single-use consumed.
        from app.models import PendingAccountLink
        pending = db_session.query(PendingAccountLink).filter(
            PendingAccountLink.id == uuid.UUID(pending_link_id)
        ).first()
        assert pending.consumed_at is not None

    def test_plain_login_without_pending_link_does_not_merge(self, client: TestClient, db_session: Session):
        """A plain login (no pending_link_id) never merges into the existing account —
        the removed session-carried implicit-merge flaw. Repeating the verified login
        just re-offers; the existing account is never silently linked."""
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="shared@example.com",
            provider="github", provider_id="gh_a",
        )

        # Verified Google login → 409 offer (creates a pending row).
        mock_google = _google_oauth_mocks(sub="goog_new", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            first = client.get("/v1/auth/google/callback", params={"code": "c1", "state": "s1"})
        assert first.status_code == 409

        # A SECOND verified Google login WITHOUT pending_link_id must NOT merge — it just
        # re-offers (409), never attaches Google to User A.
        mock_google2 = _google_oauth_mocks(sub="goog_new", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google2))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            second = client.get("/v1/auth/google/callback", params={"code": "c2", "state": "s2"})
        assert second.status_code == 409

        # User A was never linked to Google by a plain login.
        db_session.expire_all()
        links = db_session.query(UserOAuthLink).filter_by(user_id=user_a.id).all()
        assert {l.provider for l in links} == {"github"}

    def test_cross_account_reauth_is_rejected(self, client: TestClient, db_session: Session):
        """Pitfall 1 regression (nOAuth): presenting User A's pending_link_id while
        re-authenticating as a DIFFERENT existing account (User B) is rejected — the
        offer is never consumed and the new provider is never attached to anyone."""
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="shared@example.com",
            provider="github", provider_id="gh_a",
        )
        user_b, _ = _create_user_with_link(
            db_session, username="user_b", email="b@example.com",
            provider="google", provider_id="goog_b",
        )

        # A verified Google login (new provider goog_new) matching User A → 409 offer.
        mock_google = _google_oauth_mocks(sub="goog_new", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            offer = client.get("/v1/auth/google/callback", params={"code": "c1", "state": "s1"})
        assert offer.status_code == 409
        pending_link_id = offer.json()["pending_link_id"]

        # User B (unrelated) re-auths via their OWN google link carrying A's pending id.
        mock_gb = _google_oauth_mocks(sub="goog_b", email="b@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_gb))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            client.get("/v1/auth/google/login", params={"pending_link_id": pending_link_id})
            resp = client.get("/v1/auth/google/callback", params={"code": "c2", "state": "s2"})

        # Fail closed: mismatch → 400, offer NOT consumed, goog_new attached to no one.
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "merge_reauth_required"

        db_session.expire_all()
        from app.models import PendingAccountLink
        pending = db_session.query(PendingAccountLink).filter(
            PendingAccountLink.id == uuid.UUID(pending_link_id)
        ).first()
        assert pending.consumed_at is None
        assert db_session.query(UserOAuthLink).filter_by(provider="google", provider_id="goog_new").first() is None
        # Neither account gained the offered provider.
        assert {l.provider for l in user_a.oauth_links} == {"github"}
        assert {l.provider for l in db_session.query(UserOAuthLink).filter_by(user_id=user_b.id).all()} == {"google"}


# ---------------------------------------------------------------------------
# Tests: Multi-provider login (AUTH-06)
# ---------------------------------------------------------------------------

class TestMultiProviderLogin:
    """A user with multiple linked providers can log in via ANY of them (AUTH-06)."""

    def test_login_via_any_linked_provider_returns_same_user(self, client: TestClient, db_session: Session):
        user, _ = _create_user_with_link(
            db_session, username="multi", email="multi@example.com",
            provider="github", provider_id="gh_multi",
        )
        db_session.add(UserOAuthLink(user_id=user.id, provider="google", provider_id="goog_multi"))
        db_session.commit()

        # Log in via GitHub (existing link resolves — no offer, no new user).
        mock_gh = _github_oauth_mocks(github_id="gh_multi", email="multi@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_gh))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            gh_resp = client.get("/v1/auth/github/callback", params={"code": "c1", "state": "s1"})
        assert gh_resp.status_code == 200
        assert gh_resp.json()["user"]["id"] == str(user.id)

        # Log in via Google (the other linked provider) → same account.
        mock_google = _google_oauth_mocks(sub="goog_multi", email="multi@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            g_resp = client.get("/v1/auth/google/callback", params={"code": "c2", "state": "s2"})
        assert g_resp.status_code == 200
        assert g_resp.json()["user"]["id"] == str(user.id)

        # No accidental new users or links were created by either login.
        db_session.expire_all()
        assert db_session.query(User).count() == 1
        assert db_session.query(UserOAuthLink).filter_by(user_id=user.id).count() == 2


# ---------------------------------------------------------------------------
# Tests: Explicit Linking via /link and /unlink
# ---------------------------------------------------------------------------

class TestExplicitLinkUnlink:
    """Tests for GET /providers, POST /link/{provider}, DELETE /unlink/{provider}."""

    def test_list_providers(self, client: TestClient, db_session: Session):
        """GET /providers returns the provider names linked to the user."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")
        link2 = UserOAuthLink(user_id=user.id, provider="google", provider_id="goog_1")
        db_session.add(link2)
        db_session.commit()

        resp = client.get("/v1/auth/providers", headers=_auth_header(user))
        assert resp.status_code == 200
        body = resp.json()
        assert set(body["providers"]) == {"github", "google"}

    def test_list_providers_unauthenticated(self, client: TestClient):
        """GET /providers without auth should 401."""
        resp = client.get("/v1/auth/providers")
        assert resp.status_code == 401

    def test_link_provider_sets_session_and_redirects(self, client: TestClient, db_session: Session):
        """POST /link/{provider} should store link_to_user_id in session and redirect."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")

        resp = client.post(
            "/v1/auth/link/google",
            headers=_auth_header(user),
            follow_redirects=False,
        )
        assert resp.status_code in (302, 307)
        assert "/v1/auth/google/login" in resp.headers.get("location", "")

    @pytest.mark.parametrize("provider", ["mastodon", "indieauth"])
    def test_link_domain_provider_returns_400(self, client: TestClient, db_session: Session, provider: str):
        """R-3: POST /link/{mastodon,indieauth} needs a domain/url a bare POST
        can't carry — explicit 400 link_requires_domain, no session mutation,
        no redirect to a login route that would itself just 400."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")

        resp = client.post(
            f"/v1/auth/link/{provider}",
            headers=_auth_header(user),
            follow_redirects=False,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "link_requires_domain"

    def test_link_invalid_provider_returns_400(self, client: TestClient, db_session: Session):
        """POST /link/{provider} with an unsupported provider name should 400."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")

        resp = client.post(
            "/v1/auth/link/fakeprovider",
            headers=_auth_header(user),
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "invalid_provider"

    def test_unlink_provider(self, client: TestClient, db_session: Session):
        """DELETE /unlink/{provider} removes the link when user has multiple providers."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")
        link2 = UserOAuthLink(user_id=user.id, provider="google", provider_id="goog_1")
        db_session.add(link2)
        db_session.commit()

        resp = client.delete("/v1/auth/unlink/google", headers=_auth_header(user))
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unlinked"
        assert body["provider"] == "google"

        db_session.expire_all()
        remaining = db_session.query(UserOAuthLink).filter_by(user_id=user.id).all()
        assert len(remaining) == 1
        assert remaining[0].provider == "github"

    def test_unlink_last_provider_returns_400(self, client: TestClient, db_session: Session):
        """DELETE /unlink/{provider} with only one link should fail with 400."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")

        resp = client.delete("/v1/auth/unlink/github", headers=_auth_header(user))
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "cannot_unlink_last"

    def test_unlink_nonexistent_provider_returns_404(self, client: TestClient, db_session: Session):
        """DELETE /unlink/{provider} when provider is not linked should 404."""
        user, _ = _create_user_with_link(db_session, provider="github", provider_id="gh_1")

        resp = client.delete("/v1/auth/unlink/google", headers=_auth_header(user))
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["error"] == "not_found"

    def test_explicit_link_end_to_end(self, client: TestClient, db_session: Session):
        """Full explicit link flow: POST /link/github → GitHub callback → link added."""
        user, _ = _create_user_with_link(
            db_session, username="explicit_user", email="explicit@example.com",
            provider="google", provider_id="goog_explicit",
        )

        mock_oauth = _github_oauth_mocks(github_id=44444, email="different@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))

            # Step 1: POST /link/github sets session
            client.post(
                "/v1/auth/link/github",
                headers=_auth_header(user),
                follow_redirects=False,
            )

            # Step 2: GitHub callback with link_to_user_id in session
            resp = client.get("/v1/auth/github/callback", params={"code": "c", "state": "s"})

        assert resp.status_code == 200
        body = resp.json()
        # The callback should return user (the existing one, not a new one)
        assert body["user"]["id"] == str(user.id)

        # Verify both links exist
        db_session.expire_all()
        links = db_session.query(UserOAuthLink).filter_by(user_id=user.id).all()
        providers = {l.provider for l in links}
        assert providers == {"google", "github"}


# ---------------------------------------------------------------------------
# Tests: Provider Already Linked to Another User
# ---------------------------------------------------------------------------

class TestProviderAlreadyLinked:
    """Attempting to link a provider account already linked to another user."""

    def test_explicit_link_provider_already_linked_to_other_user(self, client: TestClient, db_session: Session):
        """
        User A has github:12345. User B starts explicit link flow for the same GitHub account.
        On callback, finalize_auth should detect ProviderAlreadyLinkedError → 400.
        """
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="a@example.com",
            provider="github", provider_id="12345",
        )
        user_b, _ = _create_user_with_link(
            db_session, username="user_b", email="b@example.com",
            provider="google", provider_id="goog_b",
        )

        mock_oauth = _github_oauth_mocks(github_id=12345, email="a@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))

            # User B initiates explicit link
            client.post(
                "/v1/auth/link/github",
                headers=_auth_header(user_b),
                follow_redirects=False,
            )

            # Callback returns GitHub account already linked to user A
            resp = client.get("/v1/auth/github/callback", params={"code": "test", "state": "s"})

        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["error"] == "already_linked"
