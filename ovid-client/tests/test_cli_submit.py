"""CLI tests for the ``ovid submit`` wizard command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from ovid.cli import main
from ovid.ifo_parser import AudioStream, PGCInfo, SubtitleStream, VTSInfo, VMGInfo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_disc(**overrides) -> MagicMock:
    """Return a mock Disc with realistic structure data."""
    pgc1 = PGCInfo(duration_seconds=7200, chapter_count=20)
    pgc2 = PGCInfo(duration_seconds=300, chapter_count=1)
    vts1 = VTSInfo(
        pgc_list=[pgc1],
        audio_streams=[
            AudioStream(codec="AC3", language="en", channels=6),
            AudioStream(codec="DTS", language="fr", channels=6),
        ],
        subtitle_streams=[
            SubtitleStream(language="en"),
            SubtitleStream(language="es"),
        ],
    )
    vts2 = VTSInfo(
        pgc_list=[pgc2],
        audio_streams=[AudioStream(codec="AC3", language="en", channels=2)],
        subtitle_streams=[],
    )

    disc = MagicMock()
    disc.fingerprint = "dvd1-abc123def456"
    disc.vts_count = 2
    disc.title_count = 3
    disc._vmg = VMGInfo(vts_count=2, title_count=3)
    disc._vts_list = [vts1, vts2]
    disc.configure_mock(**overrides)
    return disc


TMDB_SEARCH_RESULTS = [
    {"id": 603, "title": "The Matrix", "year": "1999", "overview": "A hacker discovers reality."},
    {"id": 604, "title": "The Matrix Reloaded", "year": "2003", "overview": "Neo continues."},
]

TMDB_MOVIE_DETAILS = {
    "id": 603,
    "title": "The Matrix",
    "year": "1999",
    "overview": "A hacker discovers reality.",
    "imdb_id": "tt0133093",
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestSubmitHappyPath:
    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie", return_value=TMDB_MOVIE_DETAILS)
    @patch("ovid.tmdb.search_movies", return_value=TMDB_SEARCH_RESULTS)
    @patch("ovid.disc.Disc.from_path")
    def test_full_wizard(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_from_path.return_value = _make_disc()

        mock_client = MagicMock()
        mock_client.submit.return_value = {"status": "pending"}
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        # Input sequence: TMDB query, pick #1, edition (blank), disc# 1, total 1, set N
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "tok123"],
            input="The Matrix\n1\n\n1\n1\nN\n",
        )

        assert result.exit_code == 0, result.output
        assert "submitted" in result.output.lower() or "✓" in result.output

        # Verify submit was called
        mock_client.submit.assert_called_once()
        payload = mock_client.submit.call_args[0][0]
        assert payload["fingerprint"] == "dvd1-abc123def456"
        assert payload["format"] == "DVD"
        assert payload["release"]["title"] == "The Matrix"
        assert payload["release"]["tmdb_id"] == 603
        assert payload["release"]["imdb_id"] == "tt0133093"

    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie", return_value=TMDB_MOVIE_DETAILS)
    @patch("ovid.tmdb.search_movies", return_value=TMDB_SEARCH_RESULTS)
    @patch("ovid.disc.Disc.from_path")
    def test_token_from_flag(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_from_path.return_value = _make_disc()
        mock_client = MagicMock()
        mock_client.submit.return_value = {"status": "pending"}
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "my-secret-token"],
            input="The Matrix\n1\n\n1\n1\nN\n",
        )

        assert result.exit_code == 0, result.output
        mock_client_cls.assert_called_once_with(base_url=None, token="my-secret-token")


# ---------------------------------------------------------------------------
# Manual entry fallback (no TMDB_API_KEY)
# ---------------------------------------------------------------------------

class TestSubmitManualFallback:
    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie")
    @patch("ovid.tmdb.search_movies", return_value=[])
    @patch("ovid.disc.Disc.from_path")
    def test_no_tmdb_key_manual_entry(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TMDB_API_KEY", raising=False)
        mock_from_path.return_value = _make_disc()
        mock_client = MagicMock()
        mock_client.submit.return_value = {"status": "pending"}
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        # Input: movie title, year, edition, disc#, total, set N
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "tok"],
            input="The Matrix\n1999\n\n1\n1\nN\n",
        )

        assert result.exit_code == 0, result.output
        payload = mock_client.submit.call_args[0][0]
        assert payload["release"]["title"] == "The Matrix"
        assert payload["release"]["year"] == 1999
        assert "tmdb_id" not in payload["release"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestSubmitErrors:
    @patch("ovid.disc.Disc.from_path")
    def test_invalid_disc_path(self, mock_from_path: MagicMock) -> None:
        mock_from_path.side_effect = FileNotFoundError("Path does not exist: /nope")
        runner = CliRunner()
        result = runner.invoke(main, ["submit", "/nope"])
        assert result.exit_code != 0
        assert "Error" in result.output or "error" in result.output.lower()

    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie", return_value=TMDB_MOVIE_DETAILS)
    @patch("ovid.tmdb.search_movies", return_value=TMDB_SEARCH_RESULTS)
    @patch("ovid.disc.Disc.from_path")
    def test_api_401_auth_error(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_from_path.return_value = _make_disc()
        mock_client = MagicMock()
        mock_client.submit.side_effect = click.ClickException(
            "API submit failed (401): Invalid token"
        )
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "bad"],
            input="The Matrix\n1\n\n1\n1\nN\n",
        )
        assert result.exit_code != 0
        assert "401" in result.output

    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie", return_value=TMDB_MOVIE_DETAILS)
    @patch("ovid.tmdb.search_movies", return_value=TMDB_SEARCH_RESULTS)
    @patch("ovid.disc.Disc.from_path")
    def test_api_409_conflict(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_from_path.return_value = _make_disc()
        mock_client = MagicMock()
        mock_client.submit.side_effect = click.ClickException(
            "API submit failed (409): Disc already exists"
        )
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "tok"],
            input="The Matrix\n1\n\n1\n1\nN\n",
        )
        assert result.exit_code != 0
        assert "409" in result.output or "already exists" in result.output.lower()


# ---------------------------------------------------------------------------
# Payload mapping
# ---------------------------------------------------------------------------

class TestPayloadMapping:
    @patch("ovid.client.OVIDClient")
    @patch("ovid.tmdb.get_movie", return_value=TMDB_MOVIE_DETAILS)
    @patch("ovid.tmdb.search_movies", return_value=TMDB_SEARCH_RESULTS)
    @patch("ovid.disc.Disc.from_path")
    def test_pgcs_become_titles_with_tracks(
        self,
        mock_from_path: MagicMock,
        mock_search: MagicMock,
        mock_get_movie: MagicMock,
        mock_client_cls: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("TMDB_API_KEY", "fake-key")
        mock_from_path.return_value = _make_disc()
        mock_client = MagicMock()
        mock_client.submit.return_value = {"status": "pending"}
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["submit", "/dev/dvd", "--token", "tok"],
            input="The Matrix\n1\n\n1\n1\nN\n",
        )
        assert result.exit_code == 0, result.output

        payload = mock_client.submit.call_args[0][0]
        titles = payload["titles"]

        # 2 VTS: VTS1 has 1 PGC, VTS2 has 1 PGC → 2 titles
        assert len(titles) == 2

        # First title (VTS1 PGC1) — main feature
        t0 = titles[0]
        assert t0["title_index"] == 0
        assert t0["is_main_feature"] is True
        assert t0["duration_secs"] == 7200
        assert t0["chapter_count"] == 20
        assert len(t0["audio_tracks"]) == 2
        assert t0["audio_tracks"][0]["language_code"] == "en"
        assert t0["audio_tracks"][0]["codec"] == "AC3"
        assert t0["audio_tracks"][0]["channels"] == 6
        assert t0["audio_tracks"][1]["language_code"] == "fr"
        assert len(t0["subtitle_tracks"]) == 2
        assert t0["subtitle_tracks"][0]["language_code"] == "en"

        # Second title (VTS2 PGC1) — not main
        t1 = titles[1]
        assert t1["title_index"] == 1
        assert t1["is_main_feature"] is False
        assert t1["duration_secs"] == 300
        assert len(t1["audio_tracks"]) == 1
        assert t1["audio_tracks"][0]["channels"] == 2
        assert len(t1["subtitle_tracks"]) == 0


# ---------------------------------------------------------------------------
# Chapter data in submit payloads
# ---------------------------------------------------------------------------

class TestChapterPayloads:
    """Chapter data inclusion in BD and DVD submit payloads."""

    def test_dvd_submit_payload_includes_chapters(self) -> None:
        """DVD normalization populates title chapters from PGC chapter_start_times."""
        from ovid.disc_structure import normalize_dvd_disc

        pgc1 = PGCInfo(
            duration_seconds=7200,
            chapter_count=3,
            chapter_start_times=[0.0, 300.7, 1200.0],
        )
        vts1 = VTSInfo(
            pgc_list=[pgc1],
            audio_streams=[AudioStream(codec="AC3", language="en", channels=6)],
            subtitle_streams=[],
        )
        disc = MagicMock()
        disc.fingerprint = "dvd1-test"
        disc._vts_list = [vts1]

        structure = normalize_dvd_disc(disc)

        chapters = structure.titles[0].chapters
        assert len(chapters) == 3
        assert (chapters[0].chapter_index, chapters[0].name, chapters[0].start_time_secs) == (1, None, 0)
        assert (chapters[1].chapter_index, chapters[1].name, chapters[1].start_time_secs) == (2, None, 301)
        assert (chapters[2].chapter_index, chapters[2].name, chapters[2].start_time_secs) == (3, None, 1200)

    def test_bd_submit_payload_includes_chapters(self) -> None:
        """BD normalization populates title chapters from MPLS chapter marks."""
        from ovid.disc_structure import normalize_bd_disc
        from ovid.mpls_parser import ChapterMark, MplsHeader, MplsPlaylist, PlayItem

        pl = MplsPlaylist(
            header=MplsHeader(version="0200", playlist_start=40, mark_start=100),
            play_items=[PlayItem(clip_id="00001", in_time=0, out_time=45000 * 7200, duration_seconds=7200.0)],
            audio_streams=[],
            subtitle_streams=[],
            chapter_marks=[
                ChapterMark(mark_type=1, play_item_ref=0, timestamp=0, duration_seconds=0.0),
                ChapterMark(mark_type=1, play_item_ref=0, timestamp=4500000, duration_seconds=100.0),
                ChapterMark(mark_type=2, play_item_ref=0, timestamp=5000000, duration_seconds=111.0),
                ChapterMark(mark_type=1, play_item_ref=0, timestamp=9000000, duration_seconds=200.0),
            ],
        )

        bd_disc = MagicMock()
        bd_disc.fingerprint = "bd1-aacs-test"
        bd_disc.format_type = "bluray"
        bd_disc.playlists = [pl]

        structure = normalize_bd_disc(bd_disc)

        chapters = structure.titles[0].chapters
        # 3 marks with mark_type==1 (the mark_type==2 is skipped)
        assert len(chapters) == 3
        assert (chapters[0].chapter_index, chapters[0].name, chapters[0].start_time_secs) == (1, None, 0)
        assert (chapters[1].chapter_index, chapters[1].name, chapters[1].start_time_secs) == (2, None, 100)
        assert (chapters[2].chapter_index, chapters[2].name, chapters[2].start_time_secs) == (3, None, 200)

    def test_bd_submit_payload_missing_bdmt(self) -> None:
        """BD normalization populates chapters without bdmt metadata (names stay None, D-08)."""
        from ovid.disc_structure import normalize_bd_disc
        from ovid.mpls_parser import ChapterMark, MplsHeader, MplsPlaylist, PlayItem

        pl = MplsPlaylist(
            header=MplsHeader(version="0200", playlist_start=40, mark_start=100),
            play_items=[PlayItem(clip_id="00001", in_time=0, out_time=45000 * 120, duration_seconds=120.0)],
            audio_streams=[],
            subtitle_streams=[],
            chapter_marks=[
                ChapterMark(mark_type=1, play_item_ref=0, timestamp=0, duration_seconds=0.0),
            ],
        )

        bd_disc = MagicMock()
        bd_disc.fingerprint = "bd2-test"
        bd_disc.format_type = "bluray"
        bd_disc.playlists = [pl]

        # Should not raise; chapters come from marks with name=None (no bdmt).
        structure = normalize_bd_disc(bd_disc)
        assert len(structure.titles) == 1
        chapters = structure.titles[0].chapters
        assert len(chapters) == 1
        assert chapters[0].name is None
