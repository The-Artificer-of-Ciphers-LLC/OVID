"""Tests for Google OAuth flow."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from authlib.integrations.starlette_client import OAuthError
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserOAuthLink


def _patch_google_configured():
    return ExitStack(), {
        "app.auth.routes._GOOGLE_CLIENT_ID": "google_test_client_id",
        "app.auth.routes._GOOGLE_CLIENT_SECRET": "google_test_client_secret",
    }


def _google_patches(token_response=None, token_error=None, userinfo=None, userinfo_error=None):
    stack = ExitStack()
    _, config_patches = _patch_google_configured()
    for target, value in config_patches.items():
        stack.enter_context(patch(target, value))

    # Register google on oauth so it exists
    from app.auth.routes import oauth
    if "google" not in oauth._registry:
        oauth.register(name="google", client_id="test")

    mock_oauth_google = MagicMock()

    if token_error:
        mock_oauth_google.authorize_access_token = AsyncMock(side_effect=token_error)
    else:
        if token_response is None:
            token_response = {
                "access_token": "google_access_token",
                "userinfo": userinfo or {
                    "sub": "google.user.001",
                    "email": "google.user@example.com",
                    "name": "Google User",
                }
            }
        mock_oauth_google.authorize_access_token = AsyncMock(return_value=token_response)

    # Patch the google oauth client in the routes module
    stack.enter_context(patch("app.auth.routes.oauth.google", mock_oauth_google))
    return stack


class TestGoogleCallback:
    def test_callback_creates_user(self, client: TestClient, db_session: Session):
        with _google_patches():
            resp = client.get("/v1/auth/google/callback?code=abc")
            
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "google_google.user.001"
        assert data["user"]["display_name"] == "Google User"

        user = db_session.query(User).filter(User.username == "google_google.user.001").first()
        assert user is not None
        assert user.email == "google.user@example.com"
        
        link = db_session.query(UserOAuthLink).filter(
            UserOAuthLink.provider == "google",
            UserOAuthLink.provider_id == "google.user.001",
        ).first()
        assert link is not None

    def test_callback_idempotent(self, client: TestClient, db_session: Session):
        with _google_patches():
            resp1 = client.get("/v1/auth/google/callback?code=abc")
        with _google_patches():
            resp2 = client.get("/v1/auth/google/callback?code=def")
            
        assert resp1.json()["user"]["id"] == resp2.json()["user"]["id"]


class TestGoogleCallbackErrors:
    def test_not_configured_returns_501(self, client: TestClient):
        resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 501
        assert "not configured" in resp.json()["detail"]

    def test_login_not_configured_returns_501(self, client: TestClient):
        resp = client.get("/v1/auth/google/login")
        assert resp.status_code == 501

    def test_oauth_error_returns_401(self, client: TestClient):
        with _google_patches(token_error=OAuthError("invalid_request", "invalid request")):
            resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"
        
    def test_generic_token_error_returns_502(self, client: TestClient):
        with _google_patches(token_error=Exception("connection error")):
            resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 502

    def test_no_token_returns_401(self, client: TestClient):
        with _google_patches(token_response={}):
            resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"
        
    def test_no_userinfo_returns_401(self, client: TestClient):
        with _google_patches(token_response={"access_token": "token"}):
            resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"

    def test_malformed_userinfo_returns_401(self, client: TestClient):
        with _google_patches(userinfo={"email": "no_sub@example.com"}):
            resp = client.get("/v1/auth/google/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "provider_error"

