"""Integration tests for BDDisc class — Tier 1/Tier 2 fallback, UHD detection, and error paths.

Negative tests:
  - No PLAYLIST directory
  - Empty PLAYLIST directory
  - All MPLS files malformed
  - All playlists under 60 seconds (filter removes all)
  - AACS dir present but Unit_Key_RO.inf missing → Tier 2 fallback
  - Tier 1 + Tier 2 both fail → clear error
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from conftest_bd import make_mpls_file
from ovid.bd_disc import BDDisc
from ovid.readers import BDFolderReader, open_reader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bd_dir(
    tmp_path: Path,
    mpls_files: dict[str, bytes] | None = None,
    aacs_files: dict[str, bytes] | None = None,
) -> Path:
    """Create a synthetic BD directory structure.  Returns root dir."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    bdmv = tmp_path / "BDMV"
    bdmv.mkdir(exist_ok=True)
    playlist_dir = bdmv / "PLAYLIST"
    playlist_dir.mkdir(exist_ok=True)

    if mpls_files:
        for name, data in mpls_files.items():
            (playlist_dir / name).write_bytes(data)

    if aacs_files:
        aacs_dir = tmp_path / "AACS"
        aacs_dir.mkdir(exist_ok=True)
        for name, data in aacs_files.items():
            (aacs_dir / name).write_bytes(data)

    return tmp_path


def _make_long_playlist(
    duration_seconds: float = 120.0,
    version: str = "0200",
    audio_streams: list | None = None,
    subtitle_streams: list | None = None,
    chapter_count: int = 5,
) -> bytes:
    """Build an MPLS file with a single play item of given duration."""
    if audio_streams is None:
        audio_streams = [(0x81, "eng", 6)]
    if subtitle_streams is None:
        subtitle_streams = [(0x90, "eng")]

    play_items = [
        {
            "clip_id": "00001",
            "in_time": 0.0,
            "out_time": duration_seconds,
            "audio_streams": audio_streams,
            "subtitle_streams": subtitle_streams,
        }
    ]
    chapter_marks = [
        {"mark_type": 1, "play_item_ref": 0, "timestamp": i * (duration_seconds / chapter_count)}
        for i in range(chapter_count)
    ]
    return make_mpls_file(
        version=version,
        play_items=play_items,
        chapter_marks=chapter_marks,
    )


# ===================================================================
# BDDisc.from_path — AACS Tier 1
# ===================================================================


class TestBDDiscTier1:
    """BDDisc with AACS Tier 1 fingerprint."""

    def test_tier1_with_aacs(self, tmp_path):
        """AACS directory with Unit_Key_RO.inf → Tier 1 fingerprint."""
        unit_key = b"unique_aacs_key_data_for_test"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": unit_key},
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 1
        assert disc.fingerprint.startswith("bd1-aacs-")
        assert len(disc.fingerprint) == 49  # "bd1-aacs-" (9) + 40 hex
        assert disc.format_type == "bluray"
        assert disc.canonical_string == ""
        assert disc.source_type == "BDFolderReader"
        assert len(disc.playlists) == 1

    def test_tier1_uhd(self, tmp_path):
        """UHD disc with AACS → uhd1-aacs- prefix."""
        unit_key = b"uhd_key_data"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist(version="0300")},
            aacs_files={"Unit_Key_RO.inf": unit_key},
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 1
        assert disc.fingerprint.startswith("uhd1-aacs-")
        assert disc.format_type == "uhd"

    def test_tier1_deterministic(self, tmp_path):
        """Same AACS key → same fingerprint."""
        unit_key = b"deterministic_key"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": unit_key},
        )

        disc1 = BDDisc.from_path(str(root))
        disc2 = BDDisc.from_path(str(root))
        assert disc1.fingerprint == disc2.fingerprint


# ===================================================================
# BDDisc.from_path — Tier 2 fallback
# ===================================================================


class TestBDDiscTier2:
    """BDDisc with BDMV Tier 2 structure hash (no AACS)."""

    def test_tier2_no_aacs(self, tmp_path):
        """No AACS directory → Tier 2 structure hash."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2
        assert disc.fingerprint.startswith("bd2-")
        assert len(disc.fingerprint) == 44  # "bd2-" (4) + 40 hex
        assert disc.format_type == "bluray"
        assert disc.canonical_string.startswith("OVID-BD-2|")

    def test_tier2_uhd(self, tmp_path):
        """UHD disc without AACS → uhd2- prefix."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist(version="0300")},
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2
        assert disc.fingerprint.startswith("uhd2-")
        assert disc.format_type == "uhd"

    def test_aacs_dir_but_no_unit_key_falls_to_tier2(self, tmp_path):
        """AACS directory exists but Unit_Key_RO.inf missing → Tier 2 fallback."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"MKB_RO.inf": b"not a unit key"},  # wrong file
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2
        assert disc.fingerprint.startswith("bd2-")

    def test_tier2_deterministic(self, tmp_path):
        """Same disc structure → same Tier 2 fingerprint."""
        mpls = _make_long_playlist()
        root = _make_bd_dir(tmp_path, mpls_files={"00001.mpls": mpls})

        disc1 = BDDisc.from_path(str(root))
        disc2 = BDDisc.from_path(str(root))
        assert disc1.fingerprint == disc2.fingerprint
        assert disc1.canonical_string == disc2.canonical_string

    def test_different_structures_different_fingerprints(self, tmp_path):
        """Different disc contents → different fingerprints."""
        root_a = _make_bd_dir(
            tmp_path / "a",
            mpls_files={"00001.mpls": _make_long_playlist(duration_seconds=120.0)},
        )
        root_b = _make_bd_dir(
            tmp_path / "b",
            mpls_files={"00001.mpls": _make_long_playlist(duration_seconds=180.0)},
        )

        disc_a = BDDisc.from_path(str(root_a))
        disc_b = BDDisc.from_path(str(root_b))
        assert disc_a.fingerprint != disc_b.fingerprint

    def test_multiple_playlists(self, tmp_path):
        """Multiple playlists above threshold are all included."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(duration_seconds=120.0),
                "00002.mpls": _make_long_playlist(duration_seconds=180.0),
                "00003.mpls": _make_long_playlist(duration_seconds=30.0),  # filtered
            },
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2
        # Canonical string should have 2 playlists (the 30s one filtered)
        parts = disc.canonical_string.split("|")
        assert parts[1] == "2"


# ===================================================================
# Negative / error path tests
# ===================================================================


class TestBDDiscNegative:
    """Error paths for BDDisc.from_path() and related components."""

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError, match="does not exist"):
            BDDisc.from_path("/nonexistent/path/to/bd")

    def test_no_bdmv_directory(self, tmp_path):
        """Directory with no BDMV → FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="No BDMV"):
            BDDisc.from_path(str(tmp_path))

    def test_no_playlist_dir(self, tmp_path):
        """BDMV exists but no PLAYLIST directory → ValueError (no MPLS files)."""
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        # No PLAYLIST dir
        with pytest.raises(ValueError, match="No MPLS"):
            BDDisc.from_path(str(tmp_path))

    def test_empty_playlist_dir(self, tmp_path):
        """Empty PLAYLIST directory → ValueError."""
        root = _make_bd_dir(tmp_path, mpls_files={})
        with pytest.raises(ValueError, match="No MPLS"):
            BDDisc.from_path(str(root))

    def test_all_mpls_malformed(self, tmp_path):
        """All MPLS files are malformed → ValueError."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": b"not_valid_mpls_data",
                "00002.mpls": b"\x00\x01\x02",
            },
        )
        with pytest.raises(ValueError, match="malformed"):
            BDDisc.from_path(str(root))

    def test_all_playlists_under_60s(self, tmp_path):
        """All playlists under 60 seconds, no AACS → ValueError from structure hash."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(duration_seconds=30.0),
                "00002.mpls": _make_long_playlist(duration_seconds=45.0),
            },
        )
        with pytest.raises(ValueError, match="No valid playlists"):
            BDDisc.from_path(str(root))

    def test_all_playlists_under_60s_with_aacs_uses_tier1(self, tmp_path):
        """All playlists under 60 seconds but AACS present → Tier 1 succeeds.

        Regression test: previously the 60-second filter ran before the AACS
        check, causing a ValueError even when a Tier 1 fingerprint was available.
        """
        unit_key = b"aacs_key_for_short_playlist_disc"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(duration_seconds=30.0),
                "00002.mpls": _make_long_playlist(duration_seconds=45.0),
            },
            aacs_files={"Unit_Key_RO.inf": unit_key},
        )

        disc = BDDisc.from_path(str(root))
        assert disc.tier == 1
        assert disc.fingerprint.startswith("bd1-aacs-")
        assert disc.format_type == "bluray"
        # All playlists filtered out — playlists list is empty for Tier 1
        assert disc.playlists == []

    def test_mixed_valid_and_malformed(self, tmp_path):
        """Some MPLS files malformed, some valid → succeeds with valid ones."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(duration_seconds=120.0),
                "00002.mpls": b"garbage_data",
            },
        )
        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2
        assert len(disc.playlists) == 1

    def test_empty_unit_key_falls_to_tier2(self, tmp_path):
        """Empty Unit_Key_RO.inf → falls back to Tier 2."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": b""},  # empty
        )
        disc = BDDisc.from_path(str(root))
        assert disc.tier == 2


# ===================================================================
# open_reader() auto-detection tests for BD
# ===================================================================


class TestOpenReaderBD:
    """open_reader() auto-detects BDMV and returns BDFolderReader."""

    def test_bd_directory_returns_bd_reader(self, tmp_path):
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
        )
        reader = open_reader(str(root))
        try:
            assert isinstance(reader, BDFolderReader)
        finally:
            reader.close()

    def test_dvd_directory_still_returns_folder_reader(self, tmp_path):
        """Directory with VIDEO_TS but no BDMV → FolderReader (no regression)."""
        from ovid.readers import FolderReader
        from conftest import make_vmg_ifo

        vts_dir = tmp_path / "VIDEO_TS"
        vts_dir.mkdir()
        (vts_dir / "VIDEO_TS.IFO").write_bytes(make_vmg_ifo(1, 1))

        reader = open_reader(str(tmp_path))
        try:
            assert isinstance(reader, FolderReader)
        finally:
            reader.close()

    def test_bd_takes_priority_over_dvd(self, tmp_path):
        """Both BDMV and VIDEO_TS present → BD takes priority."""
        from conftest import make_vmg_ifo

        # Create both structures
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        playlist = bdmv / "PLAYLIST"
        playlist.mkdir()
        (playlist / "00001.mpls").write_bytes(_make_long_playlist())

        vts_dir = tmp_path / "VIDEO_TS"
        vts_dir.mkdir()
        (vts_dir / "VIDEO_TS.IFO").write_bytes(make_vmg_ifo(1, 1))

        reader = open_reader(str(tmp_path))
        try:
            assert isinstance(reader, BDFolderReader)
        finally:
            reader.close()


# ===================================================================
# CLI integration tests — BD fingerprint, --json, and submit payload
# ===================================================================


class TestCLIBDFingerprint:
    """CLI `ovid fingerprint` with Blu-ray sources and --json flag."""

    def test_cli_fingerprint_bd_folder(self, tmp_path):
        """CLI fingerprints a BD folder and prints a bd1/bd2/uhd prefix."""
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
        )
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", str(root)])

        assert result.exit_code == 0
        output = result.output.strip()
        # No AACS → Tier 2 → bd2- prefix
        assert output.startswith("bd2-")
        assert len(output) == 44  # "bd2-" (4) + 40 hex

    def test_cli_fingerprint_bd_tier1(self, tmp_path):
        """CLI fingerprints a BD folder with AACS → bd1-aacs- prefix."""
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": b"some_aacs_key_data"},
        )
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", str(root)])

        assert result.exit_code == 0
        output = result.output.strip()
        assert output.startswith("bd1-aacs-")

    def test_cli_fingerprint_uhd(self, tmp_path):
        """CLI fingerprints UHD disc → uhd2- prefix."""
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist(version="0300")},
        )
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", str(root)])

        assert result.exit_code == 0
        output = result.output.strip()
        assert output.startswith("uhd2-")

    def test_cli_fingerprint_json_bd(self, tmp_path):
        """--json flag outputs valid JSON with BD structure keys."""
        import json
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(
                    duration_seconds=120.0,
                    audio_streams=[(0x81, "eng", 6)],
                    subtitle_streams=[(0x90, "eng")],
                    chapter_count=5,
                ),
            },
        )
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", "--json", str(root)])

        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["fingerprint"].startswith("bd2-")
        assert data["format"] == "Blu-ray"
        assert data["tier"] == 2
        assert data["source_type"] == "BDFolderReader"
        assert "structure" in data
        assert "playlists" in data["structure"]
        assert len(data["structure"]["playlists"]) == 1

        pl = data["structure"]["playlists"][0]
        assert "play_items" in pl
        assert "audio_streams" in pl
        assert "subtitle_streams" in pl
        assert "chapters" in pl
        assert pl["version"] == "0200"

    def test_cli_fingerprint_json_dvd(self, tmp_path):
        """--json flag works for DVD too (backward compat)."""
        import json
        from click.testing import CliRunner
        from conftest import make_vmg_ifo, make_vts_ifo
        from ovid.cli import main as cli_main

        vmg = make_vmg_ifo(vts_count=1, title_entries=1)
        vts = make_vts_ifo(
            pgcs=[(1, 30, 0, 12)],
            audio_streams=[(0, "en", 6)],
            subtitle_streams=["en"],
        )
        vts_dir = tmp_path / "VIDEO_TS"
        vts_dir.mkdir()
        (vts_dir / "VIDEO_TS.IFO").write_bytes(vmg)
        (vts_dir / "VTS_01_0.IFO").write_bytes(vts)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", "--json", str(tmp_path)])

        assert result.exit_code == 0
        data = json.loads(result.output)

        assert data["fingerprint"].startswith("dvd1-")
        assert data["format"] == "DVD"
        assert data["source_type"] == "FolderReader"
        assert "structure" in data
        assert "vts" in data["structure"]
        assert data["structure"]["vts_count"] == 1
        assert data["structure"]["title_count"] == 1
        assert "tier" not in data  # DVD has no tier

    def test_cli_fingerprint_still_works_dvd(self, tmp_path):
        """Existing DVD path still produces dvd1- fingerprint (no regressions)."""
        from click.testing import CliRunner
        from conftest import make_vmg_ifo, make_vts_ifo
        from ovid.cli import main as cli_main

        vmg = make_vmg_ifo(vts_count=1, title_entries=1)
        vts = make_vts_ifo(
            pgcs=[(0, 45, 30, 8)],
            audio_streams=[(0, "en", 6)],
            subtitle_streams=["en"],
        )
        vts_dir = tmp_path / "VIDEO_TS"
        vts_dir.mkdir()
        (vts_dir / "VIDEO_TS.IFO").write_bytes(vmg)
        (vts_dir / "VTS_01_0.IFO").write_bytes(vts)

        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", str(tmp_path)])

        assert result.exit_code == 0
        output = result.output.strip()
        assert output.startswith("dvd1-")
        assert len(output) == 45

    def test_cli_fingerprint_json_short_flag(self, tmp_path):
        """-j shorthand works for --json."""
        import json
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
        )
        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", "-j", str(root)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "fingerprint" in data

    def test_cli_fingerprint_invalid_path(self):
        """Invalid path still returns error exit code."""
        from click.testing import CliRunner
        from ovid.cli import main as cli_main

        runner = CliRunner()
        result = runner.invoke(cli_main, ["fingerprint", "/no/such/path"])
        assert result.exit_code == 1


# ===================================================================
# Submit payload tests — BD
# ===================================================================


class TestBuildSubmitPayloadBD:
    """_build_submit_payload() with BDDisc objects."""

    def test_build_submit_payload_bd(self, tmp_path):
        """BD disc produces a payload with format='Blu-ray' and playlist-based titles."""
        from ovid.cli import _build_submit_payload

        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(
                    duration_seconds=7200.0,
                    audio_streams=[(0x81, "eng", 6), (0x83, "fra", 8)],
                    subtitle_streams=[(0x90, "eng"), (0x90, "spa")],
                    chapter_count=20,
                ),
                "00002.mpls": _make_long_playlist(
                    duration_seconds=120.0,
                    audio_streams=[(0x81, "eng", 2)],
                    subtitle_streams=[],
                    chapter_count=1,
                ),
            },
        )
        disc = BDDisc.from_path(str(root))

        payload = _build_submit_payload(
            disc=disc,
            title="Test Movie",
            year=2024,
            tmdb_id=12345,
            imdb_id="tt9999999",
            edition_name="Collector's Edition",
            disc_number=1,
            total_discs=2,
        )

        assert payload["fingerprint"] == disc.fingerprint
        assert payload["format"] == "Blu-ray"
        assert payload["disc_number"] == 1
        assert payload["total_discs"] == 2
        assert payload["edition_name"] == "Collector's Edition"
        assert payload["release"]["title"] == "Test Movie"
        assert payload["release"]["year"] == 2024
        assert payload["release"]["tmdb_id"] == 12345
        assert payload["release"]["imdb_id"] == "tt9999999"

        titles = payload["titles"]
        assert len(titles) == 2

        # Main feature should be the longest playlist (7200s)
        main_title = [t for t in titles if t["is_main_feature"]]
        assert len(main_title) == 1
        assert main_title[0]["duration_secs"] == 7200.0
        assert main_title[0]["chapter_count"] == 20
        assert len(main_title[0]["audio_tracks"]) == 2
        assert len(main_title[0]["subtitle_tracks"]) == 2

    def test_build_submit_payload_uhd(self, tmp_path):
        """UHD disc produces format='UHD'."""
        from ovid.cli import _build_submit_payload

        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(
                    duration_seconds=120.0,
                    version="0300",
                ),
            },
        )
        disc = BDDisc.from_path(str(root))

        payload = _build_submit_payload(
            disc=disc,
            title="UHD Movie",
            year=2025,
            tmdb_id=None,
            imdb_id="",
            edition_name=None,
            disc_number=1,
            total_discs=1,
        )

        assert payload["format"] == "UHD"
        assert "tmdb_id" not in payload["release"]
        assert "imdb_id" not in payload["release"]
        assert "edition_name" not in payload

    def test_build_submit_payload_dvd_unchanged(self, tmp_path):
        """DVD disc still produces format='DVD' (no regressions)."""
        from conftest import make_vmg_ifo, make_vts_ifo
        from ovid.cli import _build_submit_payload
        from ovid.disc import Disc

        vmg = make_vmg_ifo(vts_count=1, title_entries=1)
        vts = make_vts_ifo(
            pgcs=[(1, 30, 0, 12)],
            audio_streams=[(0, "en", 6)],
            subtitle_streams=["en"],
        )
        vts_dir = tmp_path / "VIDEO_TS"
        vts_dir.mkdir()
        (vts_dir / "VIDEO_TS.IFO").write_bytes(vmg)
        (vts_dir / "VTS_01_0.IFO").write_bytes(vts)

        disc = Disc.from_path(str(tmp_path))

        payload = _build_submit_payload(
            disc=disc,
            title="DVD Movie",
            year=2020,
            tmdb_id=None,
            imdb_id="",
            edition_name=None,
            disc_number=1,
            total_discs=1,
        )

        assert payload["format"] == "DVD"
        assert payload["fingerprint"].startswith("dvd1-")
