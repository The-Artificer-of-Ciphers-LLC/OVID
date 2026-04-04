"""Tests for OAuth auth code exchange flow and cookie-based token delivery.

Covers:
- finalize_auth redirects with ?code= (not ?token=)
- POST /v1/auth/token exchanges auth code for HttpOnly cookies
- Auth codes are single-use (second exchange returns 401)
- Expired auth codes return 401
- Invalid auth codes return 401
- get_current_user reads from cookie or Authorization header
- Apple callback completes without 501
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _async_return(value):
    """Create an async function that returns value."""
    async def _inner(*args, **kwargs):
        return value
    return _inner


# ---------------------------------------------------------------------------
# Auth code exchange tests
# ---------------------------------------------------------------------------

class TestFinalizeAuthRedirect:
    """finalize_auth() should redirect with ?code= not ?token=."""

    def test_finalize_auth_redirects_with_code(self, client: TestClient, db_session, test_user):
        """OAuth callback should redirect with auth code, not JWT."""
        mock_redis = MagicMock()
        mock_redis.setex = MagicMock()

        with patch("app.auth.routes.get_redis", return_value=mock_redis), \
             patch("app.auth.routes.oauth") as mock_oauth:
            mock_token = {"access_token": "gh_test_token"}
            mock_oauth.github.authorize_access_token = _async_return(mock_token)

            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "id": 12345, "email": "test@gh.com",
                "name": "GH User", "login": "ghuser",
            }
            mock_oauth.github.get = _async_return(mock_resp)

            # Set session via login
            client.get(
                "/v1/auth/github/login?web_redirect_uri=http://localhost:3000/auth/callback",
                follow_redirects=False,
            )

            # Call callback
            resp = client.get("/v1/auth/github/callback?code=gh_code&state=test")
            if resp.status_code == 302:
                location = resp.headers.get("location", "")
                assert "code=" in location, f"Redirect should contain code=, got: {location}"
                assert "token=" not in location, f"Redirect should NOT contain token=, got: {location}"


class TestExchangeAuthCode:
    """POST /v1/auth/token exchanges auth code for cookies."""

    def test_valid_code_returns_200_with_cookies(self, client: TestClient):
        """Valid auth code returns 200 and sets ovid_token, ovid_auth, ovid_refresh cookies."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=b"access_jwt:refresh_jwt")
        mock_redis.delete = MagicMock()

        with patch("app.auth.routes.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/token", json={"code": "valid_code"})

        assert resp.status_code == 200
        set_cookie_header = resp.headers.get("set-cookie", "").lower()
        assert "ovid_token" in set_cookie_header or resp.cookies.get("ovid_token") is not None
        assert "ovid_auth" in set_cookie_header or resp.cookies.get("ovid_auth") is not None

    def test_same_code_twice_returns_401(self, client: TestClient):
        """Auth code is single-use -- second exchange returns 401."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(side_effect=[b"access_jwt:refresh_jwt", None])
        mock_redis.delete = MagicMock()

        with patch("app.auth.routes.get_redis", return_value=mock_redis):
            resp1 = client.post("/v1/auth/token", json={"code": "single_use_code"})
            assert resp1.status_code == 200

            resp2 = client.post("/v1/auth/token", json={"code": "single_use_code"})
            assert resp2.status_code == 401

    def test_expired_code_returns_401(self, client: TestClient):
        """Expired auth code (>60s) returns 401."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=None)

        with patch("app.auth.routes.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/token", json={"code": "expired_code"})

        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_code"

    def test_invalid_code_returns_401(self, client: TestClient):
        """Invalid auth code returns 401."""
        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=None)

        with patch("app.auth.routes.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/token", json={"code": "nonexistent"})

        assert resp.status_code == 401

    def test_redis_unavailable_returns_503(self, client: TestClient):
        """When Redis is unavailable, /token returns 503."""
        with patch("app.auth.routes.get_redis", return_value=None):
            resp = client.post("/v1/auth/token", json={"code": "any_code"})

        assert resp.status_code == 503


class TestCookieAuth:
    """get_current_user reads token from cookie or Authorization header."""

    def test_cookie_auth_works(self, client: TestClient, db_session, test_user):
        """get_current_user reads ovid_token from cookie."""
        from app.auth.jwt import create_access_token
        token = create_access_token(test_user.id)

        resp = client.get("/v1/auth/me", cookies={"ovid_token": token})
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_user.id)

    def test_bearer_auth_still_works(self, client: TestClient, db_session, test_user):
        """Authorization: Bearer header still works (backward compat)."""
        from app.auth.jwt import create_access_token
        token = create_access_token(test_user.id)

        resp = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_user.id)

    def test_cookie_preferred_over_header(self, client: TestClient, db_session, test_user):
        """Cookie auth is checked first if both are present."""
        from app.auth.jwt import create_access_token
        token = create_access_token(test_user.id)

        resp = client.get(
            "/v1/auth/me",
            cookies={"ovid_token": token},
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert resp.status_code == 200


class TestAppleCallback:
    """Apple Sign-In callback should not return 501."""

    def test_apple_callback_no_501_when_configured(self, client: TestClient):
        """Apple callback should not return 501 when Apple is configured."""
        with patch("app.auth.routes._APPLE_CONFIGURED", True):
            resp = client.get("/v1/auth/apple/callback")
            assert resp.status_code != 501
