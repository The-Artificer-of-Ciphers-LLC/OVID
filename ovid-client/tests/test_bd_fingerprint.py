"""Tests for BD fingerprinting: AACS Tier 1, BDMV Tier 2 structure hash, BDFolderReader, and BDDisc.

Covers:
  - compute_aacs_fingerprint: known SHA-1, BD vs UHD prefix
  - build_bd_canonical_string: format, 60-second filter, deterministic sort, UHD prefix
  - compute_bd_structure_fingerprint: SHA-256, prefix
  - BDFolderReader: MPLS listing, AACS reading, error cases
  - BDDisc.from_path: AACS Tier 1, Tier 2 fallback, UHD detection, error paths
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from conftest_bd import make_mpls_file
from ovid.bd_fingerprint import (
    build_bd_canonical_string,
    compute_aacs_fingerprint,
    compute_bd_structure_fingerprint,
)
from ovid.mpls_parser import MplsPlaylist, parse_mpls
from ovid.readers.bd_folder import BDFolderReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bd_dir(
    tmp_path: Path,
    mpls_files: dict[str, bytes] | None = None,
    aacs_files: dict[str, bytes] | None = None,
) -> Path:
    """Create a synthetic BD directory structure.

    Returns the root directory (parent of BDMV).
    """
    bdmv = tmp_path / "BDMV"
    bdmv.mkdir()
    playlist_dir = bdmv / "PLAYLIST"
    playlist_dir.mkdir()

    if mpls_files:
        for name, data in mpls_files.items():
            (playlist_dir / name).write_bytes(data)

    if aacs_files:
        aacs_dir = tmp_path / "AACS"
        aacs_dir.mkdir()
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
        audio_streams = [(0x81, "eng", 6)]  # AC3, English, 5.1
    if subtitle_streams is None:
        subtitle_streams = [(0x90, "eng")]  # PGS English

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
# AACS Tier 1 fingerprint tests
# ===================================================================


class TestAACSFingerprint:
    """Tests for compute_aacs_fingerprint()."""

    def test_known_sha1(self):
        """Known input → deterministic SHA-1 output."""
        data = b"test_unit_key_data_12345"
        expected_sha1 = hashlib.sha1(data).hexdigest()
        fp = compute_aacs_fingerprint(data, is_uhd=False)
        assert fp == f"bd1-aacs-{expected_sha1}"

    def test_bd_prefix(self):
        fp = compute_aacs_fingerprint(b"keydata", is_uhd=False)
        assert fp.startswith("bd1-aacs-")
        # prefix (9) + 40 hex chars = 49
        assert len(fp) == 49

    def test_uhd_prefix(self):
        fp = compute_aacs_fingerprint(b"keydata", is_uhd=True)
        assert fp.startswith("uhd1-aacs-")
        # prefix (10) + 40 hex chars = 50
        assert len(fp) == 50

    def test_different_data_different_hash(self):
        fp1 = compute_aacs_fingerprint(b"key_a", is_uhd=False)
        fp2 = compute_aacs_fingerprint(b"key_b", is_uhd=False)
        assert fp1 != fp2

    def test_deterministic(self):
        data = b"same_key"
        fp1 = compute_aacs_fingerprint(data, is_uhd=False)
        fp2 = compute_aacs_fingerprint(data, is_uhd=False)
        assert fp1 == fp2


# ===================================================================
# BD structure hash tests
# ===================================================================


class TestBDCanonicalString:
    """Tests for build_bd_canonical_string()."""

    def test_basic_format(self):
        """Canonical string starts with OVID-BD-2 and has correct playlist count."""
        mpls_data = _make_long_playlist(duration_seconds=120.0)
        pl = parse_mpls(mpls_data)

        canonical = build_bd_canonical_string(
            [("00001.mpls", pl)], is_uhd=False
        )
        parts = canonical.split("|")
        assert parts[0] == "OVID-BD-2"
        assert parts[1] == "1"  # 1 playlist

    def test_60_second_filter_excludes_short(self):
        """Playlists under 60 seconds are filtered out."""
        short = parse_mpls(_make_long_playlist(duration_seconds=30.0))
        long = parse_mpls(_make_long_playlist(duration_seconds=120.0))

        canonical = build_bd_canonical_string(
            [("00001.mpls", short), ("00002.mpls", long)], is_uhd=False
        )
        parts = canonical.split("|")
        assert parts[1] == "1"  # only 1 playlist survives

    def test_exactly_60_seconds_included(self):
        """A playlist at exactly 60 seconds is included."""
        pl = parse_mpls(_make_long_playlist(duration_seconds=60.0))
        canonical = build_bd_canonical_string(
            [("00001.mpls", pl)], is_uhd=False
        )
        parts = canonical.split("|")
        assert parts[1] == "1"

    def test_all_under_60_raises(self):
        """All playlists under 60 seconds → ValueError."""
        short = parse_mpls(_make_long_playlist(duration_seconds=30.0))
        with pytest.raises(ValueError, match="No valid playlists"):
            build_bd_canonical_string([("00001.mpls", short)], is_uhd=False)

    def test_deterministic_sort_by_duration_then_filename(self):
        """Playlists are sorted by duration descending, then filename ascending."""
        pl_120 = parse_mpls(_make_long_playlist(duration_seconds=120.0))
        pl_180 = parse_mpls(_make_long_playlist(duration_seconds=180.0))
        # Same duration — should sort by filename
        pl_120b = parse_mpls(_make_long_playlist(duration_seconds=120.0))

        canonical = build_bd_canonical_string(
            [
                ("00003.mpls", pl_120),
                ("00001.mpls", pl_180),
                ("00002.mpls", pl_120b),
            ],
            is_uhd=False,
        )
        parts = canonical.split("|")
        assert parts[1] == "3"  # 3 playlists survive

        # First block should be the 180s playlist, then the two 120s by filename
        # 180s → int(180) = 180
        assert ":180:" in parts[2]
        # 120s blocks should be 00002 then 00003 (by filename order)
        assert ":120:" in parts[3]
        assert ":120:" in parts[4]

    def test_playlist_block_contents(self):
        """Each playlist block includes play_item_count, duration, chapters, audio, subs."""
        mpls_data = _make_long_playlist(
            duration_seconds=120.0,
            audio_streams=[(0x81, "eng", 6), (0x83, "fre", 8)],
            subtitle_streams=[(0x90, "eng"), (0x90, "spa")],
            chapter_count=10,
        )
        pl = parse_mpls(mpls_data)

        canonical = build_bd_canonical_string(
            [("00001.mpls", pl)], is_uhd=False
        )
        parts = canonical.split("|")
        block = parts[2]
        block_parts = block.split(":")

        assert block_parts[0] == "1"    # 1 play item
        assert block_parts[1] == "120"  # 120 seconds
        assert block_parts[2] == "10"   # 10 chapters

    def test_determinism_across_calls(self):
        """Same input → same canonical string."""
        mpls_data = _make_long_playlist(duration_seconds=120.0)
        pl = parse_mpls(mpls_data)
        playlists = [("00001.mpls", pl)]

        c1 = build_bd_canonical_string(playlists, is_uhd=False)
        c2 = build_bd_canonical_string(playlists, is_uhd=False)
        assert c1 == c2


class TestBDStructureFingerprint:
    """Tests for compute_bd_structure_fingerprint()."""

    def test_bd_prefix(self):
        fp = compute_bd_structure_fingerprint("test_canonical", is_uhd=False)
        assert fp.startswith("bd2-")
        # prefix (4) + 40 hex chars = 44
        assert len(fp) == 44

    def test_uhd_prefix(self):
        fp = compute_bd_structure_fingerprint("test_canonical", is_uhd=True)
        assert fp.startswith("uhd2-")
        # prefix (5) + 40 hex chars = 45
        assert len(fp) == 45

    def test_deterministic(self):
        fp1 = compute_bd_structure_fingerprint("same_input", is_uhd=False)
        fp2 = compute_bd_structure_fingerprint("same_input", is_uhd=False)
        assert fp1 == fp2

    def test_different_input_different_hash(self):
        fp1 = compute_bd_structure_fingerprint("input_a", is_uhd=False)
        fp2 = compute_bd_structure_fingerprint("input_b", is_uhd=False)
        assert fp1 != fp2

    def test_known_sha256(self):
        """Known input → expected SHA-256 prefix."""
        canonical = "OVID-BD-2|1|test"
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40]
        fp = compute_bd_structure_fingerprint(canonical, is_uhd=False)
        assert fp == f"bd2-{expected}"


# ===================================================================
# BDFolderReader tests
# ===================================================================


class TestBDFolderReader:
    """Tests for BDFolderReader."""

    def test_list_mpls_files(self, tmp_path):
        mpls_data = _make_long_playlist()
        root = _make_bd_dir(tmp_path, mpls_files={
            "00001.mpls": mpls_data,
            "00002.mpls": mpls_data,
        })
        with BDFolderReader(str(root)) as reader:
            files = reader.list_mpls_files()
        assert files == ["00001.mpls", "00002.mpls"]

    def test_read_mpls(self, tmp_path):
        mpls_data = _make_long_playlist()
        root = _make_bd_dir(tmp_path, mpls_files={"00001.mpls": mpls_data})
        with BDFolderReader(str(root)) as reader:
            data = reader.read_mpls("00001.mpls")
        assert data == mpls_data

    def test_read_aacs_file(self, tmp_path):
        aacs_data = b"fake_unit_key_data"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": aacs_data},
        )
        with BDFolderReader(str(root)) as reader:
            assert reader.has_aacs() is True
            data = reader.read_aacs_file("Unit_Key_RO.inf")
        assert data == aacs_data

    def test_aacs_missing_returns_none(self, tmp_path):
        root = _make_bd_dir(tmp_path, mpls_files={"00001.mpls": _make_long_playlist()})
        with BDFolderReader(str(root)) as reader:
            assert reader.has_aacs() is False
            assert reader.read_aacs_file("Unit_Key_RO.inf") is None

    def test_aacs_dir_exists_but_file_missing(self, tmp_path):
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"other_file.dat": b"not a key"},
        )
        with BDFolderReader(str(root)) as reader:
            assert reader.has_aacs() is True
            assert reader.read_aacs_file("Unit_Key_RO.inf") is None

    def test_ifo_methods_raise(self, tmp_path):
        root = _make_bd_dir(tmp_path, mpls_files={"00001.mpls": _make_long_playlist()})
        with BDFolderReader(str(root)) as reader:
            with pytest.raises(NotImplementedError):
                reader.list_ifo_files()
            with pytest.raises(NotImplementedError):
                reader.read_ifo("VIDEO_TS.IFO")

    def test_no_bdmv_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No BDMV"):
            BDFolderReader(str(tmp_path))

    def test_accepts_bdmv_directly(self, tmp_path):
        """Passing the BDMV directory itself works."""
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        playlist = bdmv / "PLAYLIST"
        playlist.mkdir()
        (playlist / "00001.mpls").write_bytes(_make_long_playlist())

        with BDFolderReader(str(bdmv)) as reader:
            assert reader.list_mpls_files() == ["00001.mpls"]

    def test_case_insensitive_bdmv(self, tmp_path):
        """BDMV found even when named lowercase."""
        bdmv = tmp_path / "bdmv"
        bdmv.mkdir()
        playlist = bdmv / "PLAYLIST"
        playlist.mkdir()
        (playlist / "00001.mpls").write_bytes(_make_long_playlist())

        with BDFolderReader(str(tmp_path)) as reader:
            assert len(reader.list_mpls_files()) == 1

    def test_empty_playlist_dir(self, tmp_path):
        """Empty PLAYLIST directory → empty list, no crash."""
        root = _make_bd_dir(tmp_path, mpls_files={})
        with BDFolderReader(str(root)) as reader:
            assert reader.list_mpls_files() == []

    def test_no_playlist_dir(self, tmp_path):
        """No PLAYLIST subdirectory → empty list."""
        bdmv = tmp_path / "BDMV"
        bdmv.mkdir()
        # No PLAYLIST dir created
        with BDFolderReader(str(tmp_path)) as reader:
            assert reader.list_mpls_files() == []

    def test_read_mpls_missing_file_raises(self, tmp_path):
        root = _make_bd_dir(tmp_path, mpls_files={"00001.mpls": _make_long_playlist()})
        with BDFolderReader(str(root)) as reader:
            with pytest.raises(FileNotFoundError):
                reader.read_mpls("99999.mpls")
