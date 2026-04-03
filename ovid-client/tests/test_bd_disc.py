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
        """All playlists under 60 seconds → ValueError from structure hash."""
        root = _make_bd_dir(
            tmp_path,
            mpls_files={
                "00001.mpls": _make_long_playlist(duration_seconds=30.0),
                "00002.mpls": _make_long_playlist(duration_seconds=45.0),
            },
        )
        with pytest.raises(ValueError, match="No valid playlists"):
            BDDisc.from_path(str(root))

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
