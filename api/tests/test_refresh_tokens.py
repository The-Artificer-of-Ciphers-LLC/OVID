"""Tests for refresh token creation, rotation, and blacklisting.

Covers:
- create_access_token() returns 1-hour expiry with type: access
- create_refresh_token() returns 30-day expiry with type: refresh
- POST /v1/auth/refresh rotates tokens and blacklists old refresh
- Blacklisted refresh token returns 401
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.auth.config import SECRET_KEY


class TestAccessTokenExpiry:
    """create_access_token() should return 1-hour expiry."""

    def test_access_token_has_1_hour_expiry(self):
        """Access token should expire in approximately 1 hour."""
        from app.auth.jwt import create_access_token
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")

        now = datetime.now(timezone.utc)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta = exp - now

        # Should be approximately 1 hour (allow 5s tolerance)
        assert timedelta(minutes=59) < delta < timedelta(hours=1, seconds=5)

    def test_access_token_has_type_access(self):
        """Access token should have type: access claim."""
        from app.auth.jwt import create_access_token
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")
        assert payload.get("type") == "access"

    def test_access_token_has_jti(self):
        """Access token should have a jti claim."""
        from app.auth.jwt import create_access_token
        user_id = uuid.uuid4()
        token = create_access_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")
        assert "jti" in payload
        # Should be a valid UUID
        uuid.UUID(payload["jti"])


class TestRefreshToken:
    """create_refresh_token() should return 30-day expiry with type: refresh."""

    def test_refresh_token_has_30_day_expiry(self):
        """Refresh token should expire in approximately 30 days."""
        from app.auth.jwt import create_refresh_token
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")

        now = datetime.now(timezone.utc)
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta = exp - now

        assert timedelta(days=29, hours=23) < delta < timedelta(days=30, seconds=5)

    def test_refresh_token_has_type_refresh(self):
        """Refresh token should have type: refresh claim."""
        from app.auth.jwt import create_refresh_token
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")
        assert payload.get("type") == "refresh"

    def test_refresh_token_has_jti(self):
        """Refresh token should have a jti claim."""
        from app.auth.jwt import create_refresh_token
        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=["HS256"], issuer="ovid")
        assert "jti" in payload
        uuid.UUID(payload["jti"])


class TestRefreshRotation:
    """POST /v1/auth/refresh should rotate tokens and blacklist old."""

    def test_refresh_returns_new_tokens(self, client: TestClient, db_session, test_user):
        """Valid refresh token returns new access + refresh tokens."""
        from app.auth.jwt import create_refresh_token
        old_refresh = create_refresh_token(test_user.id)

        mock_redis = MagicMock()
        mock_redis.get = MagicMock(return_value=None)  # Not blacklisted
        mock_redis.setnx = MagicMock(return_value=True)
        mock_redis.expire = MagicMock()

        with patch("app.auth.jwt.get_redis", return_value=mock_redis):
            resp = client.post(
                "/v1/auth/refresh",
                cookies={"ovid_refresh": old_refresh},
            )

        assert resp.status_code == 200

    def test_blacklisted_refresh_returns_401(self, client: TestClient, db_session, test_user):
        """Blacklisted refresh token returns 401."""
        from app.auth.jwt import create_refresh_token
        old_refresh = create_refresh_token(test_user.id)

        mock_redis = MagicMock()
        # Blacklisted: EXISTS returns 1
        mock_redis.get = MagicMock(return_value=b"1")

        with patch("app.auth.jwt.get_redis", return_value=mock_redis):
            resp = client.post(
                "/v1/auth/refresh",
                cookies={"ovid_refresh": old_refresh},
            )

        assert resp.status_code == 401

    def test_missing_refresh_returns_401(self, client: TestClient):
        """Missing refresh token cookie returns 401."""
        resp = client.post("/v1/auth/refresh")
        assert resp.status_code == 401

    def test_invalid_refresh_returns_401(self, client: TestClient):
        """Invalid refresh token returns 401."""
        resp = client.post(
            "/v1/auth/refresh",
            cookies={"ovid_refresh": "not_a_valid_jwt"},
        )
        assert resp.status_code == 401
