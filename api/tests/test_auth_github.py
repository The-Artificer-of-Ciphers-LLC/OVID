"""Tests for GitHub OAuth flow, user upsert, and /v1/auth/me."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.models import User, UserOAuthLink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_github_user(github_id=12345, email="octocat@github.com", name="Octocat", login="octocat"):
    """Return a dict matching GitHub's GET /user response."""
    return {"id": github_id, "email": email, "name": name, "login": login}


def _patch_oauth(github_user=None, token=None, status_code=200, token_error=None, api_error=None):
    """Context manager that patches authlib's OAuth client for GitHub.

    Returns patches for authorize_access_token and get (user API).
    Also patches _GITHUB_CLIENT_ID so the route guard passes.
    """
    if github_user is None:
        github_user = _mock_github_user()
    if token is None:
        token = {"access_token": "gho_fake_token_123"}

    mock_oauth = MagicMock()

    if token_error:
        from authlib.integrations.starlette_client import OAuthError
        mock_oauth.github.authorize_access_token = AsyncMock(side_effect=token_error)
    else:
        mock_oauth.github.authorize_access_token = AsyncMock(return_value=token)

    if api_error:
        mock_oauth.github.get = AsyncMock(side_effect=api_error)
    else:
        resp_mock = MagicMock()
        resp_mock.status_code = status_code
        resp_mock.json.return_value = github_user
        mock_oauth.github.get = AsyncMock(return_value=resp_mock)

    # Stack both patches: the oauth client and the client ID guard
    from contextlib import ExitStack
    def _combined():
        stack = ExitStack()
        stack.enter_context(patch("app.auth.routes.oauth", mock_oauth))
        stack.enter_context(patch("app.auth.routes._GITHUB_CLIENT_ID", "fake-client-id"))
        return stack

    return _combined()


# ---------------------------------------------------------------------------
# GitHub callback — happy path
# ---------------------------------------------------------------------------

class TestGitHubCallback:
    """Test the /v1/auth/github/callback endpoint."""

    def test_callback_creates_user_and_returns_jwt(self, client: TestClient, db_session: Session):
        """First-time OAuth login creates user + link and returns a JWT."""
        with _patch_oauth():
            resp = client.get("/v1/auth/github/callback")

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "github_12345"
        assert data["user"]["display_name"] == "Octocat"

        # Verify DB state
        user = db_session.query(User).filter(User.username == "github_12345").first()
        assert user is not None
        assert user.email == "octocat@github.com"
        assert user.email_verified is True

        link = db_session.query(UserOAuthLink).filter(
            UserOAuthLink.provider == "github",
            UserOAuthLink.provider_id == "12345",
        ).first()
        assert link is not None
        assert link.user_id == user.id

    def test_callback_upsert_idempotent(self, client: TestClient, db_session: Session):
        """Second callback with same GitHub ID returns same user (no duplicate)."""
        with _patch_oauth():
            resp1 = client.get("/v1/auth/github/callback")
        with _patch_oauth():
            resp2 = client.get("/v1/auth/github/callback")

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["user"]["id"] == resp2.json()["user"]["id"]

        # Only one user in DB
        users = db_session.query(User).filter(User.username == "github_12345").all()
        assert len(users) == 1

    def test_callback_github_user_no_email(self, client: TestClient, db_session: Session):
        """GitHub user with no public email still creates a user."""
        user_data = _mock_github_user(email=None)
        with _patch_oauth(github_user=user_data):
            resp = client.get("/v1/auth/github/callback")

        assert resp.status_code == 200
        user = db_session.query(User).filter(User.username == "github_12345").first()
        assert user is not None
        assert "noemail.placeholder" in user.email

    def test_callback_uses_login_when_no_name(self, client: TestClient, db_session: Session):
        """Falls back to login if name is None."""
        user_data = _mock_github_user(name=None, login="ghostuser")
        with _patch_oauth(github_user=user_data):
            resp = client.get("/v1/auth/github/callback")

        assert resp.status_code == 200
        assert resp.json()["user"]["display_name"] == "ghostuser"


# ---------------------------------------------------------------------------
# GitHub callback — failure modes
# ---------------------------------------------------------------------------

class TestGitHubCallbackErrors:
    """Negative tests for GitHub callback error handling."""

    def test_oauth_error_returns_401(self, client: TestClient):
        """OAuthError during token exchange → 401."""
        from authlib.integrations.starlette_client import OAuthError
        err = OAuthError(error="access_denied", description="User denied")
        with _patch_oauth(token_error=err):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"

    def test_token_exchange_exception_returns_502(self, client: TestClient):
        """Generic exception during token exchange → 502."""
        with _patch_oauth(token_error=Exception("connection timeout")):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 502

    def test_no_access_token_returns_401(self, client: TestClient):
        """Token response missing access_token → 401."""
        with _patch_oauth(token={"error": "bad_code"}):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 401

    def test_github_api_401_returns_401(self, client: TestClient):
        """GitHub user API returns 401 → 401 provider_error."""
        with _patch_oauth(status_code=401):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "provider_error"

    def test_github_api_500_returns_502(self, client: TestClient):
        """GitHub user API returns 500 → 502."""
        with _patch_oauth(status_code=500):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 502

    def test_github_api_exception_returns_502(self, client: TestClient):
        """Exception fetching GitHub user → 502."""
        with _patch_oauth(api_error=Exception("network error")):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 502

    def test_malformed_github_response_returns_401(self, client: TestClient):
        """GitHub response missing 'id' field → 401 provider_error."""
        with _patch_oauth(github_user={"login": "ghost", "email": None}):
            resp = client.get("/v1/auth/github/callback")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "provider_error"


# ---------------------------------------------------------------------------
# /v1/auth/me
# ---------------------------------------------------------------------------

class TestAuthMe:
    """Test the /v1/auth/me endpoint."""

    def test_me_returns_user_info(self, client: TestClient, test_user: User):
        """Valid JWT → user profile."""
        token = create_access_token(test_user.id)
        resp = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(test_user.id)
        assert data["username"] == test_user.username
        assert data["email"] == test_user.email
        assert data["role"] == "contributor"

    def test_me_without_token_returns_401(self, client: TestClient):
        """No auth header → 401."""
        resp = client.get("/v1/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client: TestClient):
        """Bad JWT → 401."""
        resp = client.get("/v1/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# web_redirect_uri — OAuth redirect to frontend
# ---------------------------------------------------------------------------

class TestWebRedirectUri:
    """Test the web_redirect_uri flow for browser-based OAuth."""

    def test_login_stores_redirect_and_callback_returns_302(self, client: TestClient, db_session: Session):
        """Login with web_redirect_uri stores value in session; callback returns 302 redirect with auth code."""
        from starlette.responses import JSONResponse

        # Mock authorize_redirect to return a simple 200 (simulates redirect to GitHub)
        mock_oauth = MagicMock()
        mock_authorize = AsyncMock(return_value=JSONResponse(content={"ok": True}))
        mock_oauth.github.authorize_redirect = mock_authorize

        # Step 1: Call login with web_redirect_uri — this stores it in session
        with patch("app.auth.routes.oauth", mock_oauth), \
             patch("app.auth.routes._GITHUB_CLIENT_ID", "fake-client-id"):
            login_resp = client.get(
                "/v1/auth/github/login?web_redirect_uri=http://localhost:3000/auth/callback"
            )
        assert login_resp.status_code == 200

        # Mock Redis for auth code storage
        mock_redis = MagicMock()
        mock_redis.setex = MagicMock()

        # Step 2: Call callback — the session still has web_redirect_uri
        with _patch_oauth(), patch("app.auth.routes.get_redis", return_value=mock_redis):
            # follow_redirects=False so we can inspect the 302
            callback_resp = client.get(
                "/v1/auth/github/callback",
                follow_redirects=False,
            )

        assert callback_resp.status_code == 302
        location = callback_resp.headers["location"]
        assert location.startswith("http://localhost:3000/auth/callback?")
        assert "code=" in location
        assert "token=" not in location

    def test_login_rejects_invalid_scheme(self, client: TestClient):
        """web_redirect_uri with javascript: scheme → 400."""
        with patch("app.auth.routes._GITHUB_CLIENT_ID", "fake-client-id"):
            resp = client.get(
                "/v1/auth/github/login?web_redirect_uri=javascript:alert(1)"
            )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "invalid_redirect_uri"

    def test_callback_without_redirect_returns_json(self, client: TestClient, db_session: Session):
        """Without web_redirect_uri in session, callback returns JSON (regression guard)."""
        with _patch_oauth():
            resp = client.get("/v1/auth/github/callback")

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert data["user"]["username"] == "github_12345"
