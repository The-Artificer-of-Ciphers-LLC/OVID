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
from pathlib import Path

import pytest

from conftest_bd import make_mpls_file
from ovid.bd_fingerprint import (
    build_bd_canonical_string,
    compute_aacs_fingerprint,
    compute_bd_structure_fingerprint,
)
from ovid.mpls_parser import parse_mpls
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
    clip_id: str = "00001",
) -> bytes:
    """Build an MPLS file with a single play item of given duration."""
    if audio_streams is None:
        audio_streams = [(0x81, "eng", 6)]  # AC3, English, 5.1
    if subtitle_streams is None:
        subtitle_streams = [(0x90, "eng")]  # PGS English

    play_items = [
        {
            "clip_id": clip_id,
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

    def test_deduped_playlists_still_sort_by_duration_then_clip_sequence(self):
        """Distinct-content playlists sort by duration descending, then clip-sequence.

        NOTE: this test previously used two byte-identical 120s fixtures
        (both default clip_id "00001") to exercise the filename tie-break.
        Under the frozen ruleset (FPRINT-06/D-06), byte-identical clip
        sequences are a real dedup collision — those two playlists would
        now correctly collapse into one canonical block. To keep this test
        exercising the *tie-break* path (not the dedup path), `pl_120b` is
        given a distinct clip_id so all three playlists remain distinct
        after dedup, and the tie-break is verified to be clip-sequence
        based rather than filename based.
        """
        pl_120 = parse_mpls(_make_long_playlist(duration_seconds=120.0, chapter_count=5))
        pl_180 = parse_mpls(_make_long_playlist(duration_seconds=180.0))
        # Same duration as pl_120, but distinct clip_id (avoids the dedup
        # collision) AND a distinct chapter_count (makes the two 120s blocks
        # content-distinguishable so tie-break order is observable).
        pl_120b = parse_mpls(
            _make_long_playlist(duration_seconds=120.0, clip_id="00002", chapter_count=3)
        )

        canonical = build_bd_canonical_string(
            [
                ("00003.mpls", pl_120),
                ("00001.mpls", pl_180),
                ("00002.mpls", pl_120b),
            ],
            is_uhd=False,
        )
        parts = canonical.split("|")
        assert parts[1] == "3"  # all 3 playlists remain distinct after dedup

        # First block should be the 180s playlist.
        # 180s → int(180) = 180
        assert ":180:" in parts[2]
        # 120s blocks: clip-sequence tie-break sorts clip_id "00001" (pl_120,
        # chapter_count=5) before clip_id "00002" (pl_120b, chapter_count=3),
        # regardless of filename ("00002.mpls" sorts before "00003.mpls").
        assert parts[3].split(":")[2] == "5"
        assert parts[4].split(":")[2] == "3"

    def test_max_clip_repeats_filter_excludes_loop_padded_decoy(self):
        """A playlist whose clip_id repeats more than MAX_CLIP_REPEATS times
        (a loop-padded decoy playlist) is excluded from the canonical string."""
        decoy_data = make_mpls_file(
            version="0200",
            play_items=[
                {"clip_id": "00099", "in_time": 0.0, "out_time": 30.0},
                {"clip_id": "00099", "in_time": 30.0, "out_time": 60.0},
                {"clip_id": "00099", "in_time": 60.0, "out_time": 90.0},
            ],
        )
        decoy = parse_mpls(decoy_data)
        normal = parse_mpls(_make_long_playlist(duration_seconds=120.0, clip_id="00001"))

        canonical = build_bd_canonical_string(
            [("00099.mpls", decoy), ("00001.mpls", normal)], is_uhd=False
        )
        parts = canonical.split("|")
        assert parts[1] == "1"  # only the non-repeating playlist survives

    def test_dedup_by_clip_sequence_excludes_duplicate_decoy(self):
        """Two playlists with byte-identical clip sequences collapse to one
        canonical block, regardless of filename."""
        pl_a = parse_mpls(_make_long_playlist(duration_seconds=120.0))
        pl_b = parse_mpls(_make_long_playlist(duration_seconds=120.0))

        canonical = build_bd_canonical_string(
            [("00001.mpls", pl_a), ("00099.mpls", pl_b)], is_uhd=False
        )
        parts = canonical.split("|")
        assert parts[1] == "1"  # second playlist is a dedup-collapsed duplicate

    def test_tie_break_is_clip_sequence_not_filename(self):
        """Tie-break between same-duration playlists is by clip-sequence
        content, never by .mpls filename."""
        pl_a = parse_mpls(
            _make_long_playlist(duration_seconds=120.0, clip_id="00005", chapter_count=1)
        )
        pl_b = parse_mpls(
            _make_long_playlist(duration_seconds=120.0, clip_id="00001", chapter_count=9)
        )

        canonical = build_bd_canonical_string(
            [("00001.mpls", pl_a), ("00002.mpls", pl_b)], is_uhd=False
        )
        parts = canonical.split("|")
        # clip_id "00001" (playlist B) sorts first by clip-sequence tie-break,
        # despite its filename ("00002.mpls") sorting after "00001.mpls".
        assert ":9:" in parts[2]

    def test_canonical_string_uses_ovid_bd2_version_constant(self):
        """The canonical-string version prefix is sourced from the frozen
        bd2_spec module, not a hardcoded literal (D-08: v1 is frozen as-is,
        no version bump this phase)."""
        from ovid import bd2_spec

        assert bd2_spec.OVID_BD2_VERSION == "OVID-BD-2"

        pl = parse_mpls(_make_long_playlist(duration_seconds=120.0))
        canonical = build_bd_canonical_string([("00001.mpls", pl)], is_uhd=False)
        assert canonical.split("|")[0] == bd2_spec.OVID_BD2_VERSION

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
        assert block_parts[3] == "2"    # 2 audio streams (CR-01 count field)
        assert block_parts[4] == "AC3+eng+6,TrueHD+fre+8"
        assert block_parts[5] == "2"    # 2 subtitle streams (CR-01 count field)
        assert block_parts[6] == "eng,spa"

    def test_determinism_across_calls(self):
        """Same input → same canonical string."""
        mpls_data = _make_long_playlist(duration_seconds=120.0)
        pl = parse_mpls(mpls_data)
        playlists = [("00001.mpls", pl)]

        c1 = build_bd_canonical_string(playlists, is_uhd=False)
        c2 = build_bd_canonical_string(playlists, is_uhd=False)
        assert c1 == c2

    def test_zero_subtitle_streams_differs_from_one_empty_language_subtitle(self):
        """Regression (CR-01): a playlist with zero subtitle streams and a
        playlist with exactly one subtitle stream whose language could not be
        decoded (empty/null language field — common for forced/unlabeled PG
        tracks) must NOT produce the same canonical string or fingerprint.

        Before the fix, both cases joined to an identical empty
        ``subtitle_info`` field (``",".join([]) == ",".join(['']) == ""``),
        silently collapsing two structurally different discs into the same
        ``bd2-``/``uhd2-`` fingerprint.
        """
        audio = [(0x81, "eng", 6)]

        no_subs_data = make_mpls_file(
            version="0200",
            play_items=[
                {
                    "clip_id": "00001",
                    "in_time": 0.0,
                    "out_time": 120.0,
                    "audio_streams": audio,
                    "subtitle_streams": [],
                }
            ],
        )
        one_empty_sub_data = make_mpls_file(
            version="0200",
            play_items=[
                {
                    "clip_id": "00001",
                    "in_time": 0.0,
                    "out_time": 120.0,
                    "audio_streams": audio,
                    "subtitle_streams": [(0x90, "")],  # empty/unparsed language
                }
            ],
        )

        pl_no_subs = parse_mpls(no_subs_data)
        pl_one_empty_sub = parse_mpls(one_empty_sub_data)

        # Sanity: confirm the parsed structures really do differ in
        # subtitle stream count before asserting on the derived strings.
        assert len(pl_no_subs.subtitle_streams) == 0
        assert len(pl_one_empty_sub.subtitle_streams) == 1
        assert pl_one_empty_sub.subtitle_streams[0].language == ""

        canonical_no_subs = build_bd_canonical_string(
            [("00001.mpls", pl_no_subs)], is_uhd=False
        )
        canonical_one_empty_sub = build_bd_canonical_string(
            [("00001.mpls", pl_one_empty_sub)], is_uhd=False
        )

        assert canonical_no_subs != canonical_one_empty_sub, (
            "0 subtitle streams and 1 empty-language subtitle stream "
            "produced the identical canonical string — fingerprint "
            "collision (CR-01)."
        )

        fp_no_subs = compute_bd_structure_fingerprint(
            canonical_no_subs, is_uhd=False
        )
        fp_one_empty_sub = compute_bd_structure_fingerprint(
            canonical_one_empty_sub, is_uhd=False
        )
        assert fp_no_subs != fp_one_empty_sub, (
            "0 subtitle streams and 1 empty-language subtitle stream "
            "produced the identical bd2- fingerprint — collision (CR-01)."
        )


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

    def test_read_aacs_file_permission_error_is_distinct_from_missing(self, tmp_path):
        """WR-02 regression: a present-but-unreadable AACS file raises OSError
        instead of silently returning None like a genuinely missing file.

        The IO failure is injected deterministically by monkeypatching the
        ``open`` builtin (not via ``chmod``, which is a no-op under root and
        is platform-dependent) so this test is reproducible cross-platform
        and in root-run CI/Docker.
        """
        aacs_data = b"fake_unit_key_data"
        root = _make_bd_dir(
            tmp_path,
            mpls_files={"00001.mpls": _make_long_playlist()},
            aacs_files={"Unit_Key_RO.inf": aacs_data},
        )
        with BDFolderReader(str(root)) as reader:
            real_open = open

            def _raise_permission_error(file, *args, **kwargs):
                if str(file).endswith("Unit_Key_RO.inf"):
                    raise PermissionError("injected: permission denied")
                return real_open(file, *args, **kwargs)

            import builtins

            original_open = builtins.open
            builtins.open = _raise_permission_error
            try:
                with pytest.raises(PermissionError):
                    reader.read_aacs_file("Unit_Key_RO.inf")
            finally:
                builtins.open = original_open

            # Sanity: a genuinely missing file still returns None, not raise.
            assert reader.read_aacs_file("does_not_exist.inf") is None

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
