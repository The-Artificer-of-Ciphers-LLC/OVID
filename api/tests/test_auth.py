"""Tests for JWT utilities and auth dependency."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, decode_access_token
from app.auth.deps import get_current_user
from app.models import User

# Re-use the test secret key set by conftest
_TEST_SECRET = "test-secret-key-for-unit-tests-32b"


# ---------------------------------------------------------------------------
# JWT create / decode
# ---------------------------------------------------------------------------
class TestCreateAccessToken:
    def test_returns_decodable_jwt(self):
        """create_access_token returns a JWT with correct sub, iss, exp."""
        uid = uuid.uuid4()
        token = create_access_token(uid)

        payload = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"], issuer="ovid")
        assert payload["sub"] == str(uid)
        assert payload["iss"] == "ovid"
        assert "exp" in payload
        assert "iat" in payload

    def test_expiry_is_approximately_30_days(self):
        """Token expiry should be roughly 30 days from now."""
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"], issuer="ovid")

        exp_dt = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat_dt = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
        delta = exp_dt - iat_dt
        assert 29 <= delta.days <= 31


class TestDecodeAccessToken:
    def test_valid_token(self):
        """decode_access_token succeeds on a valid token."""
        uid = uuid.uuid4()
        token = create_access_token(uid)
        payload = decode_access_token(token)
        assert payload["sub"] == str(uid)
        assert payload["iss"] == "ovid"

    def test_expired_token(self):
        """decode_access_token raises ExpiredSignatureError on expired token."""
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iss": "ovid",
            "iat": datetime.now(timezone.utc) - timedelta(days=31),
        }
        token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_tampered_token(self):
        """decode_access_token raises on a token signed with wrong key."""
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iss": "ovid",
        }
        token = pyjwt.encode(payload, "wrong-key", algorithm="HS256")
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token(token)

    def test_garbage_token(self):
        """decode_access_token raises on garbage input."""
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_wrong_issuer(self):
        """decode_access_token raises when issuer doesn't match 'ovid'."""
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iss": "not-ovid",
        }
        token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token(token)


# ---------------------------------------------------------------------------
# get_current_user dependency (via endpoint integration)
# ---------------------------------------------------------------------------
class TestGetCurrentUser:
    """Test get_current_user through a real FastAPI app with the test DB."""

    def test_valid_token_returns_user(self, client, test_user, auth_header):
        """Valid Bearer token for an existing user → endpoint receives User."""
        # Use the submit endpoint as a proxy — it requires auth.
        # A 422 (validation error) means auth passed; 401 means it didn't.
        resp = client.post("/v1/disc", json={}, headers=auth_header)
        assert resp.status_code != 401

    def test_missing_header_returns_401(self, client):
        """No Authorization header → 401 missing_token."""
        resp = client.post("/v1/disc", json={})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"

    def test_empty_bearer_returns_401(self, client):
        """'Bearer ' with no token → 401 missing_token."""
        resp = client.post("/v1/disc", json={}, headers={"Authorization": "Bearer "})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"

    def test_non_bearer_scheme_returns_401(self, client):
        """'Basic abc123' → 401 missing_token."""
        resp = client.post("/v1/disc", json={}, headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"

    def test_expired_token_returns_401(self, client, test_user):
        """Expired JWT → 401 expired_token."""
        payload = {
            "sub": str(test_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iss": "ovid",
            "iat": datetime.now(timezone.utc) - timedelta(days=31),
        }
        token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")
        resp = client.post("/v1/disc", json={}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "expired_token"

    def test_garbage_token_returns_401(self, client):
        """Garbage token → 401 invalid_token."""
        resp = client.post("/v1/disc", json={}, headers={"Authorization": "Bearer garbage.token.here"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_token"

    def test_valid_jwt_for_deleted_user_returns_401(self, client, db_session):
        """JWT with sub pointing to nonexistent user → 401 invalid_token."""
        fake_id = uuid.uuid4()
        token = create_access_token(fake_id)
        resp = client.post("/v1/disc", json={}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_token"

    def test_token_signed_with_wrong_key_returns_401(self, client):
        """Token signed with different secret → 401 invalid_token."""
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "iss": "ovid",
        }
        token = pyjwt.encode(payload, "different-secret", algorithm="HS256")
        resp = client.post("/v1/disc", json={}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_token"
