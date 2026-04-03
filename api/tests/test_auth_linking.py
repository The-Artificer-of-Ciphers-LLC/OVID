"""Tests for account linking & email conflict resolution.

Covers:
- 409 Conflict on email match (implicit linking initiation)
- pending_link session state drives implicit merge
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
    """Prepare mocked authlib OAuth client for GitHub callback."""
    gh_user = {"id": github_id, "email": email, "name": name, "login": login}
    mock_oauth = MagicMock()
    mock_oauth.github.authorize_access_token = AsyncMock(return_value={"access_token": "gho_fake"})
    resp_mock = MagicMock()
    resp_mock.status_code = 200
    resp_mock.json.return_value = gh_user
    mock_oauth.github.get = AsyncMock(return_value=resp_mock)
    return mock_oauth


def _google_oauth_mocks(sub="google_123", email="shared@example.com", name="Google User"):
    """Prepare mocked authlib OAuth client for Google callback."""
    userinfo = {"sub": sub, "email": email, "name": name}
    mock_oauth = MagicMock()
    mock_oauth.google.authorize_access_token = AsyncMock(
        return_value={"access_token": "ya29_fake", "userinfo": userinfo}
    )
    return mock_oauth


# ---------------------------------------------------------------------------
# Tests: Email Conflict → 409
# ---------------------------------------------------------------------------

class TestEmailConflict:
    """When a new OAuth login has an email already in use, return 409."""

    def test_github_login_email_conflict_returns_409(self, client: TestClient, db_session: Session):
        """A user logs in with GitHub where the email is already used by another user."""
        existing_user, _ = _create_user_with_link(
            db_session, username="existing", email="shared@example.com",
            provider="google", provider_id="goog_existing",
        )

        mock_oauth = _github_oauth_mocks(github_id=55555, email="shared@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/github/callback", params={"code": "test_code", "state": "s"})

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "email_conflict"
        assert body["existing_user_id"] == str(existing_user.id)

    def test_google_login_email_conflict_returns_409(self, client: TestClient, db_session: Session):
        """A Google login with a pre-existing email should get 409."""
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
        assert body["existing_user_id"] == str(existing_user.id)

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
# Tests: Implicit Merge via pending_link
# ---------------------------------------------------------------------------

class TestImplicitMerge:
    """After 409, re-authenticating with the existing account merges the pending link."""

    def test_pending_link_merges_on_next_login(self, client: TestClient, db_session: Session):
        """
        Flow:
        1. User A exists (google, shared@example.com).
        2. New GitHub login with shared@example.com → 409, pending_link stored in session.
        3. User A re-authenticates via their Google login → pending GitHub link merged into A.
        """
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="shared@example.com",
            provider="google", provider_id="goog_a",
        )

        # Step 2: GitHub login triggers 409
        mock_gh = _github_oauth_mocks(github_id=77777, email="shared@example.com")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_gh))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/github/callback", params={"code": "c1", "state": "s1"})

        assert resp.status_code == 409

        # Step 3: Re-authenticate as user A via Google (existing link resolves)
        mock_google = _google_oauth_mocks(sub="goog_a", email="shared@example.com", name="User A")

        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            resp2 = client.get("/v1/auth/google/callback", params={"code": "c2", "state": "s2"})

        assert resp2.status_code == 200
        body = resp2.json()
        assert body["user"]["id"] == str(user_a.id)

        # Verify the GitHub link was merged into user A
        db_session.expire_all()
        links = db_session.query(UserOAuthLink).filter_by(user_id=user_a.id).all()
        providers = {l.provider for l in links}
        assert providers == {"github", "google"}

    def test_pending_link_cleared_after_merge(self, client: TestClient, db_session: Session):
        """After merge, the pending_link should be consumed — a subsequent login should not re-merge."""
        user_a, _ = _create_user_with_link(
            db_session, username="user_a", email="shared@example.com",
            provider="google", provider_id="goog_a",
        )

        # Trigger 409
        mock_gh = _github_oauth_mocks(github_id=77777, email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_gh))
            stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake_id"))
            client.get("/v1/auth/github/callback", params={"code": "c1", "state": "s1"})

        # Merge
        mock_google = _google_oauth_mocks(sub="goog_a", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            client.get("/v1/auth/google/callback", params={"code": "c2", "state": "s2"})

        # Re-authenticate again — no pending_link should remain
        mock_google2 = _google_oauth_mocks(sub="goog_a", email="shared@example.com")
        with ExitStack() as stack:
            stack.enter_context(patch("app.auth.routes.oauth", mock_google2))
            stack.enter_context(patch("app.auth.routes._GOOGLE_CLIENT_ID", "fake_id"))
            resp = client.get("/v1/auth/google/callback", params={"code": "c3", "state": "s3"})

        assert resp.status_code == 200
        # Should still be only 2 links (google + github), not a duplicate
        db_session.expire_all()
        links = db_session.query(UserOAuthLink).filter_by(user_id=user_a.id).all()
        assert len(links) == 2


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


# ---------------------------------------------------------------------------
# Tests: Mastodon Placeholder Email
# ---------------------------------------------------------------------------

class TestMastodonPlaceholderEmail:
    """Mastodon placeholder emails should use @noemail.placeholder and not trigger conflicts."""

    def test_mastodon_callback_uses_noemail_placeholder(self, client: TestClient, db_session: Session):
        """The mastodon callback should store an @noemail.placeholder email, not username@domain."""
        from app.auth.users import user_upsert

        # Directly test user_upsert with what mastodon callback would pass
        user = user_upsert(
            db_session,
            provider="mastodon",
            provider_id="mastodon.social:1234",
            email="mastodon_1234@noemail.placeholder",
            display_name="MastoUser",
        )
        assert user.email == "mastodon_1234@noemail.placeholder"

        # A different user with a different real email should not be blocked
        user2 = user_upsert(
            db_session,
            provider="github",
            provider_id="gh_9999",
            email="realuser@gmail.com",
            display_name="GH User",
        )
        # Different users created successfully
        assert user2.id != user.id

    def test_noemail_placeholder_skips_conflict_check(self, db_session: Session):
        """user_upsert with @noemail.placeholder email should never raise EmailConflictError."""
        from app.auth.users import user_upsert

        # Create a user with a real email
        user_upsert(
            db_session, provider="github", provider_id="gh_1",
            email="john@example.com", display_name="John",
        )

        # A mastodon login with a placeholder email should NOT conflict even
        # if we reuse the same email pattern
        user2 = user_upsert(
            db_session, provider="mastodon", provider_id="masto:999",
            email="mastodon_999@noemail.placeholder", display_name="MastoUser",
        )
        assert user2 is not None


# ---------------------------------------------------------------------------
# Tests: user_upsert unit-level edge cases
# ---------------------------------------------------------------------------

class TestUserUpsertEdgeCases:
    """Direct unit tests for user_upsert edge cases."""

    def test_email_conflict_raises_with_correct_user_id(self, db_session: Session):
        """EmailConflictError includes the existing user's ID."""
        from app.auth.users import user_upsert, EmailConflictError

        existing = user_upsert(
            db_session, provider="github", provider_id="gh_first",
            email="conflict@test.com", display_name="First",
        )

        with pytest.raises(EmailConflictError) as exc_info:
            user_upsert(
                db_session, provider="google", provider_id="goog_second",
                email="conflict@test.com", display_name="Second",
            )

        assert exc_info.value.existing_user_id == str(existing.id)
        assert exc_info.value.email == "conflict@test.com"

    def test_link_to_nonexistent_user_raises(self, db_session: Session):
        """Explicit linking to a non-existent user_id should raise ValueError."""
        from app.auth.users import user_upsert

        with pytest.raises(ValueError, match="User not found"):
            user_upsert(
                db_session, provider="github", provider_id="gh_orphan",
                email=None, display_name=None,
                link_to_user_id=str(uuid.uuid4()),
            )

    def test_provider_already_linked_error(self, db_session: Session):
        """Linking a provider already owned by another user raises ProviderAlreadyLinkedError."""
        from app.auth.users import user_upsert, ProviderAlreadyLinkedError

        user_a = user_upsert(
            db_session, provider="github", provider_id="gh_shared_id",
            email="a@test.com", display_name="A",
        )

        user_b_raw = User(
            id=uuid.uuid4(), username="user_b", email="b@test.com",
            display_name="B", role="contributor",
        )
        db_session.add(user_b_raw)
        db_session.commit()

        with pytest.raises(ProviderAlreadyLinkedError):
            user_upsert(
                db_session, provider="github", provider_id="gh_shared_id",
                email=None, display_name=None,
                link_to_user_id=str(user_b_raw.id),
            )

    def test_null_email_does_not_trigger_conflict(self, db_session: Session):
        """When email is None, no conflict check should happen."""
        from app.auth.users import user_upsert

        user_upsert(
            db_session, provider="github", provider_id="gh_1",
            email="real@test.com", display_name="User1",
        )

        # Second user with None email should succeed
        user2 = user_upsert(
            db_session, provider="google", provider_id="goog_1",
            email=None, display_name="User2",
        )
        assert user2 is not None
