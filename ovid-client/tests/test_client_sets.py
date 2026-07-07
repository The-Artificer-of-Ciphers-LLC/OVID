"""Tests for OVIDClient set search and creation methods."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
import pytest

from ovid.client import OVIDClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESPONSE = {
    "request_id": "search-001",
    "results": [
        {
            "id": "set-uuid-1",
            "release_id": "rel-uuid-1",
            "edition_name": "Extended Edition",
            "total_discs": 4,
            "discs": [{"id": "disc-1"}, {"id": "disc-2"}],
        },
    ],
    "page": 1,
    "total_pages": 1,
    "total_results": 1,
}

SAMPLE_CREATE_RESPONSE = {
    "request_id": "create-001",
    "id": "set-uuid-new",
    "release_id": "rel-uuid-1",
    "edition_name": "Extended Edition",
    "total_discs": 4,
    "created_at": "2026-04-04T00:00:00Z",
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
# search_sets()
# ---------------------------------------------------------------------------

class TestSearchSets:
    @patch("ovid.client.requests.Session.get")
    def test_search_happy_path(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, SAMPLE_SEARCH_RESPONSE)
        client = OVIDClient(base_url="http://test:8000")
        result = client.search_sets("matrix")

        assert result is not None
        assert result["total_results"] == 1
        assert result["results"][0]["edition_name"] == "Extended Edition"
        mock_get.assert_called_once_with(
            "http://test:8000/v1/set",
            params={"q": "matrix", "page": 1},
        )

    @patch("ovid.client.requests.Session.get")
    def test_search_with_page(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(200, SAMPLE_SEARCH_RESPONSE)
        client = OVIDClient(base_url="http://test:8000")
        client.search_sets("matrix", page=2)

        mock_get.assert_called_once_with(
            "http://test:8000/v1/set",
            params={"q": "matrix", "page": 2},
        )

    @patch("ovid.client.requests.Session.get")
    def test_search_returns_none_on_error(self, mock_get: MagicMock) -> None:
        mock_get.return_value = _mock_response(400)
        client = OVIDClient(base_url="http://test:8000")
        result = client.search_sets("")

        assert result is None


# ---------------------------------------------------------------------------
# create_set()
# ---------------------------------------------------------------------------

class TestCreateSet:
    @patch("ovid.client.requests.Session.post")
    def test_create_happy_path(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(201, SAMPLE_CREATE_RESPONSE)
        client = OVIDClient(base_url="http://test:8000", token="test-token")
        result = client.create_set(
            release_id="rel-uuid-1",
            edition_name="Extended Edition",
            total_discs=4,
        )

        assert result["id"] == "set-uuid-new"
        assert result["total_discs"] == 4

        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token"
        body = call_kwargs.kwargs["json"]
        assert body["release_id"] == "rel-uuid-1"
        assert body["edition_name"] == "Extended Edition"
        assert body["total_discs"] == 4

    @patch("ovid.client.requests.Session.post")
    def test_create_without_token(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(201, SAMPLE_CREATE_RESPONSE)
        client = OVIDClient(base_url="http://test:8000")
        client.create_set(release_id="rel-uuid-1")

        call_kwargs = mock_post.call_args
        assert "Authorization" not in call_kwargs.kwargs["headers"]

    @patch("ovid.client.requests.Session.post")
    def test_create_error_raises(self, mock_post: MagicMock) -> None:
        mock_post.return_value = _mock_response(
            404,
            json_data={"error": "not_found", "message": "Release not found"},
        )
        client = OVIDClient(base_url="http://test:8000", token="tok")

        with pytest.raises(click.ClickException, match="404"):
            client.create_set(release_id="bad-uuid")
