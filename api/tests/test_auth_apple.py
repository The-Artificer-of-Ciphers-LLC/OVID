"""Tests for Apple Sign-In OAuth flow."""

import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserOAuthLink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_test_ec_key():
    """Generate a test ES256 private key and return PEM string."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem


def _make_apple_id_token(sub="apple.user.001", email="user@icloud.com"):
    """Create a fake Apple ID token JWT (unsigned — we skip verification)."""
    payload = {
        "iss": "https://appleid.apple.com",
        "sub": sub,
        "aud": "com.ovid.test",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "email": email,
        "email_verified": "true",
    }
    # Sign with HS256 for testing — production uses RS256
    return pyjwt.encode(payload, "test-key", algorithm="HS256")


def _make_apple_id_token_no_email(sub="apple.user.002"):
    """Apple ID token with no email claim."""
    payload = {
        "iss": "https://appleid.apple.com",
        "sub": sub,
        "aud": "com.ovid.test",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return pyjwt.encode(payload, "test-key", algorithm="HS256")


def _patch_apple_configured():
    """Patch Apple env vars so routes are active."""
    return ExitStack(), {
        "app.auth.routes._APPLE_CONFIGURED": True,
        "app.auth.routes._APPLE_CLIENT_ID": "com.ovid.test",
        "app.auth.routes._APPLE_TEAM_ID": "TEAM123",
        "app.auth.routes._APPLE_KEY_ID": "KEY123",
        "app.auth.routes._APPLE_PRIVATE_KEY": _generate_test_ec_key(),
    }


def _apple_patches(token_response=None, token_status=200, token_error=None):
    """Return an ExitStack with Apple config + mocked httpx."""
    stack = ExitStack()
    _, config_patches = _patch_apple_configured()
    for target, value in config_patches.items():
        stack.enter_context(patch(target, value))

    if token_error:
        mock_post = AsyncMock(side_effect=token_error)
    else:
        if token_response is None:
            token_response = {
                "access_token": "apple_access_token",
                "id_token": _make_apple_id_token(),
                "token_type": "Bearer",
            }
        mock_resp = MagicMock()
        mock_resp.status_code = token_status
        mock_resp.json.return_value = token_response
        mock_resp.text = str(token_response)
        mock_post = AsyncMock(return_value=mock_resp)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = mock_post

    stack.enter_context(patch("app.auth.routes.httpx.AsyncClient", return_value=mock_client))
    return stack


# ---------------------------------------------------------------------------
# Apple callback — happy path
# ---------------------------------------------------------------------------

class TestAppleCallback:
    def test_callback_decodes_id_token_and_upserts_user(self, client: TestClient, db_session: Session):
        """Apple callback extracts sub from ID token and creates user."""
        with _apple_patches():
            resp = client.get("/v1/auth/apple/callback?code=auth_code_123")

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "apple_apple.user.001"

        user = db_session.query(User).filter(User.username == "apple_apple.user.001").first()
        assert user is not None
        assert user.email == "user@icloud.com"

        link = db_session.query(UserOAuthLink).filter(
            UserOAuthLink.provider == "apple",
            UserOAuthLink.provider_id == "apple.user.001",
        ).first()
        assert link is not None

    def test_callback_idempotent(self, client: TestClient, db_session: Session):
        """Second callback with same Apple sub returns same user."""
        with _apple_patches():
            resp1 = client.get("/v1/auth/apple/callback?code=code1")
        with _apple_patches():
            resp2 = client.get("/v1/auth/apple/callback?code=code2")

        assert resp1.json()["user"]["id"] == resp2.json()["user"]["id"]

    def test_callback_no_email_in_id_token(self, client: TestClient, db_session: Session):
        """Apple ID token without email still creates user with placeholder."""
        token_resp = {
            "access_token": "at",
            "id_token": _make_apple_id_token_no_email(),
            "token_type": "Bearer",
        }
        with _apple_patches(token_response=token_resp):
            resp = client.get("/v1/auth/apple/callback?code=code3")

        assert resp.status_code == 200
        user = db_session.query(User).filter(User.username == "apple_apple.user.002").first()
        assert user is not None
        assert "noemail.placeholder" in user.email


# ---------------------------------------------------------------------------
# Apple callback — error paths
# ---------------------------------------------------------------------------

class TestAppleCallbackErrors:
    def test_not_configured_returns_501(self, client: TestClient):
        """Apple routes return 501 when env vars not set."""
        resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 501
        assert "not configured" in resp.json()["detail"]

    def test_login_not_configured_returns_501(self, client: TestClient):
        """Apple login returns 501 when not configured."""
        resp = client.get("/v1/auth/apple/login")
        assert resp.status_code == 501

    def test_no_code_returns_401(self, client: TestClient):
        """Missing authorization code → 401."""
        with _apple_patches():
            resp = client.get("/v1/auth/apple/callback")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"

    def test_token_exchange_timeout_returns_502(self, client: TestClient):
        """httpx timeout during token exchange → 502."""
        import httpx
        with _apple_patches(token_error=httpx.TimeoutException("timeout")):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 502

    def test_token_exchange_error_returns_502(self, client: TestClient):
        """Generic exception during token exchange → 502."""
        with _apple_patches(token_error=Exception("connection error")):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 502

    def test_token_endpoint_non_200_returns_401(self, client: TestClient):
        """Apple token endpoint returns error status → 401."""
        with _apple_patches(token_status=400, token_response={"error": "invalid_grant"}):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "auth_failed"

    def test_no_id_token_in_response_returns_401(self, client: TestClient):
        """Token response missing id_token → 401."""
        with _apple_patches(token_response={"access_token": "at"}):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "provider_error"

    def test_invalid_id_token_returns_401(self, client: TestClient):
        """Malformed id_token string → 401."""
        with _apple_patches(token_response={"id_token": "not.valid.jwt", "access_token": "at"}):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_token"

    def test_id_token_missing_sub_returns_401(self, client: TestClient):
        """ID token with no sub claim → 401."""
        bad_token = pyjwt.encode(
            {"iss": "apple", "exp": int(time.time()) + 3600, "iat": int(time.time())},
            "k", algorithm="HS256",
        )
        with _apple_patches(token_response={"id_token": bad_token, "access_token": "at"}):
            resp = client.get("/v1/auth/apple/callback?code=abc")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_token"
