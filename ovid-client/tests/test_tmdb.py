"""Unit tests for the TMDB search module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ovid.tmdb import get_movie, search_movies


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_result(
    id: int, title: str, release_date: str = "2023-06-15", overview: str = "A movie."
) -> MagicMock:
    obj = MagicMock()
    obj.id = id
    obj.title = title
    obj.release_date = release_date
    obj.overview = overview
    return obj


def _make_details(
    id: int,
    title: str,
    release_date: str = "2023-06-15",
    overview: str = "A movie.",
    imdb_id: str = "tt1234567",
) -> MagicMock:
    obj = MagicMock()
    obj.id = id
    obj.title = title
    obj.release_date = release_date
    obj.overview = overview
    obj.imdb_id = imdb_id
    return obj


# ---------------------------------------------------------------------------
# search_movies
# ---------------------------------------------------------------------------

class TestSearchMovies:
    def test_no_api_key_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        assert search_movies("anything") == []

    @patch("ovid.tmdb.Movie")
    @patch("ovid.tmdb.TMDb")
    def test_returns_mapped_results(
        self, mock_tmdb_cls: MagicMock, mock_movie_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_movie = MagicMock()
        mock_movie.search.return_value = [
            _make_search_result(603, "The Matrix", "1999-03-31", "A hacker discovers reality is simulated."),
            _make_search_result(604, "The Matrix Reloaded", "2003-05-15"),
        ]
        mock_movie_cls.return_value = mock_movie

        results = search_movies("matrix")

        assert len(results) == 2
        assert results[0] == {
            "id": 603,
            "title": "The Matrix",
            "year": "1999",
            "overview": "A hacker discovers reality is simulated.",
        }
        assert results[1]["year"] == "2003"

    @patch("ovid.tmdb.Movie")
    @patch("ovid.tmdb.TMDb")
    def test_exception_returns_empty(
        self, mock_tmdb_cls: MagicMock, mock_movie_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_movie_cls.return_value.search.side_effect = RuntimeError("network error")
        assert search_movies("matrix") == []

    @patch("ovid.tmdb.Movie")
    @patch("ovid.tmdb.TMDb")
    def test_empty_release_date(
        self, mock_tmdb_cls: MagicMock, mock_movie_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_movie = MagicMock()
        mock_movie.search.return_value = [_make_search_result(1, "No Date", release_date="")]
        mock_movie_cls.return_value = mock_movie

        results = search_movies("no date")
        assert results[0]["year"] == ""


# ---------------------------------------------------------------------------
# get_movie
# ---------------------------------------------------------------------------

class TestGetMovie:
    def test_no_api_key_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        assert get_movie(603) is None

    @patch("ovid.tmdb.Movie")
    @patch("ovid.tmdb.TMDb")
    def test_returns_dict_with_imdb_id(
        self, mock_tmdb_cls: MagicMock, mock_movie_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_movie = MagicMock()
        mock_movie.details.return_value = _make_details(
            603, "The Matrix", "1999-03-31", imdb_id="tt0133093"
        )
        mock_movie_cls.return_value = mock_movie

        result = get_movie(603)
        assert result is not None
        assert result["id"] == 603
        assert result["title"] == "The Matrix"
        assert result["year"] == "1999"
        assert result["imdb_id"] == "tt0133093"

    @patch("ovid.tmdb.Movie")
    @patch("ovid.tmdb.TMDb")
    def test_exception_returns_none(
        self, mock_tmdb_cls: MagicMock, mock_movie_cls: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_movie_cls.return_value.details.side_effect = RuntimeError("not found")
        assert get_movie(999999) is None
