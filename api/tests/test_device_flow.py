"""Tests for RFC 8628 Device Authorization Grant endpoints.

Covers:
- POST /v1/auth/device/authorize returns device_code, user_code, etc.
- POST /v1/auth/device/token with pending device returns 428
- POST /v1/auth/device/token with approved device returns tokens
- POST /v1/auth/device/token with expired device returns 401
- POST /v1/auth/device/token polled too fast returns 429 slow_down
- POST /v1/auth/device/approve with valid user_code approves device
"""

import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _mock_redis_store():
    """Create a mock Redis that stores values in a dict."""
    store = {}
    mock = MagicMock()

    def _setex(key, ttl, value):
        store[key] = {"value": value, "ttl": ttl}

    def _get(key):
        entry = store.get(key)
        if entry is None:
            return None
        return entry["value"].encode() if isinstance(entry["value"], str) else entry["value"]

    def _delete(key):
        store.pop(key, None)

    def _ttl(key):
        entry = store.get(key)
        return entry["ttl"] if entry else 0

    mock.setex = MagicMock(side_effect=_setex)
    mock.get = MagicMock(side_effect=_get)
    mock.delete = MagicMock(side_effect=_delete)
    mock.ttl = MagicMock(side_effect=_ttl)
    mock._store = store  # expose for test inspection
    return mock


class TestDeviceAuthorize:
    """POST /v1/auth/device/authorize returns device flow parameters."""

    def test_authorize_returns_device_code_and_user_code(self, client: TestClient):
        """Should return device_code, user_code (8 chars), verification_uri, etc."""
        mock_redis = _mock_redis_store()

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/device/authorize")

        assert resp.status_code == 200
        data = resp.json()
        assert "device_code" in data
        assert "user_code" in data
        assert len(data["user_code"]) == 8
        assert "verification_uri" in data
        assert data["expires_in"] == 900
        assert data["interval"] == 5

    def test_authorize_redis_unavailable_returns_503(self, client: TestClient):
        """When Redis is unavailable, returns 503."""
        with patch("app.auth.device_flow.get_redis", return_value=None):
            resp = client.post("/v1/auth/device/authorize")

        assert resp.status_code == 503


class TestDeviceToken:
    """POST /v1/auth/device/token polls for authorization result."""

    def test_pending_device_returns_428(self, client: TestClient):
        """Pending device code returns 428 authorization_pending."""
        mock_redis = _mock_redis_store()
        device_data = json.dumps({
            "user_code": "ABCD1234",
            "status": "pending",
            "last_poll": 0,
        })
        mock_redis._store["device:test_device_code"] = {"value": device_data, "ttl": 900}

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/device/token", json={"device_code": "test_device_code"})

        assert resp.status_code == 428
        assert resp.json()["detail"]["error"] == "authorization_pending"

    def test_approved_device_returns_tokens(self, client: TestClient, db_session, test_user):
        """Approved device code returns access_token and refresh_token."""
        mock_redis = _mock_redis_store()
        device_data = json.dumps({
            "user_code": "ABCD1234",
            "status": "approved",
            "user_id": str(test_user.id),
            "last_poll": 0,
        })
        mock_redis._store["device:test_device_code"] = {"value": device_data, "ttl": 900}

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/device/token", json={"device_code": "test_device_code"})

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"

    def test_expired_device_returns_401(self, client: TestClient):
        """Expired device code (not in Redis) returns 401."""
        mock_redis = _mock_redis_store()

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/device/token", json={"device_code": "expired_code"})

        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "expired_token"

    def test_slow_down_on_rapid_polling(self, client: TestClient):
        """Polling faster than interval returns 429 slow_down."""
        mock_redis = _mock_redis_store()
        device_data = json.dumps({
            "user_code": "ABCD1234",
            "status": "pending",
            "last_poll": time.time(),  # Just polled
        })
        mock_redis._store["device:fast_poll_code"] = {"value": device_data, "ttl": 900}

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post("/v1/auth/device/token", json={"device_code": "fast_poll_code"})

        assert resp.status_code == 429
        assert resp.json()["detail"]["error"] == "slow_down"


class TestDeviceApprove:
    """POST /v1/auth/device/approve approves a device by user_code."""

    def test_approve_valid_user_code(self, client: TestClient, db_session, test_user):
        """Authenticated user approves device via user_code."""
        from app.auth.jwt import create_access_token
        token = create_access_token(test_user.id)

        mock_redis = _mock_redis_store()
        device_data = json.dumps({
            "user_code": "TESTCODE",
            "status": "pending",
            "last_poll": 0,
        })
        mock_redis._store["device:dc_123"] = {"value": device_data, "ttl": 900}
        mock_redis._store["usercode:TESTCODE"] = {"value": "dc_123", "ttl": 900}

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post(
                "/v1/auth/device/approve",
                json={"user_code": "TESTCODE"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        assert resp.json()["approved"] is True

        # Verify the device was actually approved in the store
        stored = json.loads(mock_redis._store["device:dc_123"]["value"])
        assert stored["status"] == "approved"
        assert stored["user_id"] == str(test_user.id)

    def test_approve_invalid_user_code(self, client: TestClient, db_session, test_user):
        """Invalid user_code returns 404."""
        from app.auth.jwt import create_access_token
        token = create_access_token(test_user.id)

        mock_redis = _mock_redis_store()

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post(
                "/v1/auth/device/approve",
                json={"user_code": "INVALID1"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 404

    def test_approve_requires_auth(self, client: TestClient):
        """Approve without auth returns 401."""
        mock_redis = _mock_redis_store()

        with patch("app.auth.device_flow.get_redis", return_value=mock_redis):
            resp = client.post(
                "/v1/auth/device/approve",
                json={"user_code": "ANYCODE1"},
            )

        assert resp.status_code == 401
