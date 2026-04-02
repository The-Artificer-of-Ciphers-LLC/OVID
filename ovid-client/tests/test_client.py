"""Unit tests for OVIDClient — HTTP wrapper for the OVID API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
import pytest

from ovid.client import OVIDClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOOKUP = {
    "request_id": "abc-123",
    "fingerprint": "sha256:deadbeef",
    "format": "DVD",
    "status": "verified",
    "confidence": "high",
    "edition_name": "Special Edition",
    "disc_number": 1,
    "total_discs": 2,
    "release": {
        "title": "The Matrix",
        "year": 1999,
        "content_type": "movie",
        "tmdb_id": 603,
    },
    "titles": [
        {
            "title_index": 1,
            "is_main_feature": True,
            "title_type": "feature",
            "display_name": "Main Feature",
            "duration_secs": 8160,
            "chapter_count": 34,
            "audio_tracks": [
                {"index": 0, "language": "en", "codec": "ac3", "channels": 6},
            ],
            "subtitle_tracks": [
                {"index": 0, "language": "en"},
                {"index": 1, "language": "fr"},
            ],
        },
    ],
}

SAMPLE_SUBMIT_RESPONSE = {
    "request_id": "xyz-789",
    "fingerprint": "sha256:deadbeef",
    "status": "pending",
    "message": "Disc submitted successfully",
}


def _mock_response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("No JSON")
    return resp


# ---------------------------------------------------------------------------
# Constructor / env defaults
# ---------------------------------------------------------------------------

class TestOVIDClientInit:
    def test_defaults(self) -> None:
        client = OVIDClient()
        assert client.base_url == "http://localhost:8000"
        assert client.token is None

    def test_constructor_args(self) -> None:
        client = OVIDClient(base_url="https://api.example.com/", token="tok123")
        assert client.base_url == "https://api.example.com"  # trailing slash stripped
        assert client.token == "tok123"

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OVID_API_URL", "https://env.example.com")
        monkeypatch.setenv("OVID_TOKEN", "env-token")
        client = OVIDClient()
        assert client.base_url == "https://env.example.com"
        assert client.token == "env-token"

    def test_constructor_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OVID_API_URL", "https://env.example.com")
        client = OVIDClient(base_url="https://arg.example.com")
        assert client.base_url == "https://arg.example.com"


# ---------------------------------------------------------------------------
# lookup()
# ---------------------------------------------------------------------------

class TestLookup:
    @patch("ovid.client.requests.Session.get")
    def test_found(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, SAMPLE_LOOKUP)
        client = OVIDClient(base_url="http://test:8000")
        result = client.lookup("sha256:deadbeef")

        assert result is not None
        assert result["release"]["title"] == "The Matrix"
        mock_get.assert_called_once_with("http://test:8000/v1/disc/sha256:deadbeef")

    @patch("ovid.client.requests.Session.get")
    def test_not_found(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(404)
        client = OVIDClient(base_url="http://test:8000")
        result = client.lookup("sha256:missing")

        assert result is None

    @patch("ovid.client.requests.Session.get")
    def test_server_error_raises(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(
            500,
            json_data={"error": "internal", "message": "database down"},
        )
        client = OVIDClient(base_url="http://test:8000")

        with pytest.raises(click.ClickException, match="500"):
            client.lookup("sha256:broken")


# ---------------------------------------------------------------------------
# submit()
# ---------------------------------------------------------------------------

class TestSubmit:
    @patch("ovid.client.requests.Session.post")
    def test_success(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(201, SAMPLE_SUBMIT_RESPONSE)
        client = OVIDClient(base_url="http://test:8000", token="secret")
        result = client.submit({"fingerprint": "sha256:deadbeef"})

        assert result["status"] == "pending"
        # Verify Bearer header was sent
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer secret"

    @patch("ovid.client.requests.Session.post")
    def test_unauthorized_raises(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(
            401,
            json_data={"error": "unauthorized", "message": "Invalid token"},
        )
        client = OVIDClient(base_url="http://test:8000", token="bad")

        with pytest.raises(click.ClickException, match="401"):
            client.submit({"fingerprint": "x"})

    @patch("ovid.client.requests.Session.post")
    def test_conflict_raises(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(
            409,
            json_data={"error": "conflict", "message": "Disc already exists"},
        )
        client = OVIDClient(base_url="http://test:8000", token="tok")

        with pytest.raises(click.ClickException, match="409"):
            client.submit({"fingerprint": "x"})

    @patch("ovid.client.requests.Session.post")
    def test_server_error_raises(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(500, text="Internal Server Error")
        client = OVIDClient(base_url="http://test:8000", token="tok")

        with pytest.raises(click.ClickException, match="500"):
            client.submit({"fingerprint": "x"})

    @patch("ovid.client.requests.Session.post")
    def test_no_token_omits_header(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(201, SAMPLE_SUBMIT_RESPONSE)
        client = OVIDClient(base_url="http://test:8000")  # no token
        client.submit({"fingerprint": "sha256:deadbeef"})

        call_kwargs = mock_post.call_args
        assert "Authorization" not in call_kwargs.kwargs["headers"]
