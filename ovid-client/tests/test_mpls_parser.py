"""Unit tests for ovid.mpls_parser — MPLS playlist binary parsing."""

from __future__ import annotations

import struct

import pytest

from ovid.mpls_parser import (
    MplsPlaylist,
    MplsHeader,
    PlayItem,
    StreamEntry,
    ChapterMark,
    parse_mpls,
)
from conftest_bd import make_mpls_file, TICK_RATE


# =========================================================================
# Version detection
# =========================================================================

class TestVersionDetection:
    """MPLS version string parsing: 0200 = BD, 0300 = UHD."""

    def test_version_0200_standard_bd(self):
        data = make_mpls_file(version="0200", play_items=[
            {"clip_id": "00001", "in_time": 0, "out_time": 10.0},
        ])
        result = parse_mpls(data)
        assert result.version == "0200"
        assert result.header.version == "0200"

    def test_version_0300_uhd(self):
        data = make_mpls_file(version="0300", play_items=[
            {"clip_id": "00001", "in_time": 0, "out_time": 10.0},
        ])
        result = parse_mpls(data)
        assert result.version == "0300"
        assert result.header.version == "0300"


# =========================================================================
# Play items
# =========================================================================

class TestPlayItems:
    """PlayItem parsing: clip IDs, timestamps, and duration calculation."""

    def test_single_play_item(self):
        data = make_mpls_file(play_items=[
            {"clip_id": "00001", "in_time": 0.0, "out_time": 120.0},
        ])
        result = parse_mpls(data)
        assert len(result.play_items) == 1
        pi = result.play_items[0]
        assert pi.clip_id == "00001"
        assert pi.in_time == 0
        assert pi.out_time == 120 * TICK_RATE
        assert pi.duration_seconds == pytest.approx(120.0, abs=0.1)

    def test_multiple_play_items(self):
        data = make_mpls_file(play_items=[
            {"clip_id": "00001", "in_time": 0.0, "out_time": 600.0},
            {"clip_id": "00002", "in_time": 0.0, "out_time": 1800.0},
            {"clip_id": "00003", "in_time": 10.0, "out_time": 300.0},
        ])
        result = parse_mpls(data)
        assert len(result.play_items) == 3
        assert result.play_items[0].clip_id == "00001"
        assert result.play_items[0].duration_seconds == pytest.approx(600.0, abs=0.1)
        assert result.play_items[1].clip_id == "00002"
        assert result.play_items[1].duration_seconds == pytest.approx(1800.0, abs=0.1)
        assert result.play_items[2].clip_id == "00003"
        assert result.play_items[2].duration_seconds == pytest.approx(290.0, abs=0.1)

    def test_duration_from_45khz_ticks(self):
        """Verify duration is correctly computed from 45kHz tick timestamps."""
        # 1 hour = 3600 seconds = 162,000,000 ticks
        data = make_mpls_file(play_items=[
            {"clip_id": "00001", "in_time": 0.0, "out_time": 3600.0},
        ])
        result = parse_mpls(data)
        pi = result.play_items[0]
        assert pi.out_time == 3600 * TICK_RATE
        assert pi.duration_seconds == pytest.approx(3600.0, abs=0.1)

    def test_nonzero_in_time(self):
        """PlayItem with in_time > 0 — duration is out - in."""
        data = make_mpls_file(play_items=[
            {"clip_id": "00001", "in_time": 100.0, "out_time": 500.0},
        ])
        result = parse_mpls(data)
        assert result.play_items[0].duration_seconds == pytest.approx(400.0, abs=0.1)

    def test_zero_duration_play_item(self):
        """Play item with in_time == out_time → 0 duration."""
        data = make_mpls_file(play_items=[
            {"clip_id": "00001", "in_time": 50.0, "out_time": 50.0},
        ])
        result = parse_mpls(data)
        assert result.play_items[0].duration_seconds == 0.0


# =========================================================================
# Audio and subtitle streams
# =========================================================================

class TestStreams:
    """Stream extraction from PlayItem STN_table."""

    def test_audio_stream_ac3(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "audio_streams": [(0x81, "eng", 6)],
        }])
        result = parse_mpls(data)
        assert len(result.audio_streams) == 1
        a = result.audio_streams[0]
        assert a.codec == "AC3"
        assert a.language == "eng"
        assert a.channels == 6

    def test_audio_stream_truehd(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "audio_streams": [(0x83, "eng", 8)],
        }])
        result = parse_mpls(data)
        assert len(result.audio_streams) == 1
        assert result.audio_streams[0].codec == "TrueHD"
        assert result.audio_streams[0].channels == 8

    def test_audio_stream_dts_hd_ma(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "audio_streams": [(0x86, "fra", 6)],
        }])
        result = parse_mpls(data)
        assert result.audio_streams[0].codec == "DTS-HD MA"
        assert result.audio_streams[0].language == "fra"

    def test_multiple_audio_streams(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "audio_streams": [
                (0x81, "eng", 6),
                (0x83, "eng", 8),
                (0x81, "fra", 6),
                (0x82, "deu", 6),
            ],
        }])
        result = parse_mpls(data)
        assert len(result.audio_streams) == 4
        assert [s.language for s in result.audio_streams] == ["eng", "eng", "fra", "deu"]

    def test_subtitle_stream_pgs(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "subtitle_streams": [(0x90, "eng")],
        }])
        result = parse_mpls(data)
        assert len(result.subtitle_streams) == 1
        assert result.subtitle_streams[0].codec == "PGS"
        assert result.subtitle_streams[0].language == "eng"

    def test_multiple_subtitle_streams(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "subtitle_streams": [
                (0x90, "eng"),
                (0x90, "fra"),
                (0x90, "spa"),
            ],
        }])
        result = parse_mpls(data)
        assert len(result.subtitle_streams) == 3
        assert [s.language for s in result.subtitle_streams] == ["eng", "fra", "spa"]

    def test_no_audio_streams(self):
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 120.0,
            "audio_streams": [],
            "subtitle_streams": [],
        }])
        result = parse_mpls(data)
        assert result.audio_streams == []
        assert result.subtitle_streams == []


# =========================================================================
# Chapter marks
# =========================================================================

class TestChapterMarks:
    """ChapterMark parsing from PlayListMark section."""

    def test_single_chapter(self):
        data = make_mpls_file(
            play_items=[
                {"clip_id": "00001", "in_time": 0, "out_time": 120.0},
            ],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 0.0},
            ],
        )
        result = parse_mpls(data)
        assert len(result.chapter_marks) == 1
        cm = result.chapter_marks[0]
        assert cm.mark_type == 1
        assert cm.play_item_ref == 0
        assert cm.timestamp == 0
        assert cm.duration_seconds == 0.0

    def test_multiple_chapters(self):
        data = make_mpls_file(
            play_items=[
                {"clip_id": "00001", "in_time": 0, "out_time": 7200.0},
            ],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 0.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 600.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 1200.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 1800.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 2400.0},
            ],
        )
        result = parse_mpls(data)
        assert len(result.chapter_marks) == 5
        assert result.chapter_marks[0].duration_seconds == pytest.approx(0.0)
        assert result.chapter_marks[1].duration_seconds == pytest.approx(600.0, abs=0.1)
        assert result.chapter_marks[4].duration_seconds == pytest.approx(2400.0, abs=0.1)

    def test_zero_chapters(self):
        data = make_mpls_file(
            play_items=[
                {"clip_id": "00001", "in_time": 0, "out_time": 120.0},
            ],
            chapter_marks=[],
        )
        result = parse_mpls(data)
        assert result.chapter_marks == []

    def test_chapter_timestamp_45khz_conversion(self):
        """Chapter timestamp at exactly 90 seconds = 4,050,000 ticks."""
        data = make_mpls_file(
            play_items=[
                {"clip_id": "00001", "in_time": 0, "out_time": 120.0},
            ],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 90.0},
            ],
        )
        result = parse_mpls(data)
        cm = result.chapter_marks[0]
        assert cm.timestamp == 90 * TICK_RATE
        assert cm.duration_seconds == pytest.approx(90.0, abs=0.01)


# =========================================================================
# Zero / empty cases
# =========================================================================

class TestEdgeCases:
    """Edge cases: zero play items, zero chapters, zero streams."""

    def test_zero_play_items(self):
        data = make_mpls_file(play_items=[], chapter_marks=[])
        result = parse_mpls(data)
        assert result.play_items == []
        assert result.audio_streams == []
        assert result.subtitle_streams == []
        assert result.chapter_marks == []

    def test_data_class_types(self):
        """Verify all returned objects are the correct types."""
        data = make_mpls_file(
            play_items=[{
                "clip_id": "00001", "in_time": 0, "out_time": 120.0,
                "audio_streams": [(0x81, "eng", 6)],
                "subtitle_streams": [(0x90, "eng")],
            }],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 0.0},
            ],
        )
        result = parse_mpls(data)
        assert isinstance(result, MplsPlaylist)
        assert isinstance(result.header, MplsHeader)
        assert isinstance(result.play_items[0], PlayItem)
        assert isinstance(result.audio_streams[0], StreamEntry)
        assert isinstance(result.subtitle_streams[0], StreamEntry)
        assert isinstance(result.chapter_marks[0], ChapterMark)


# =========================================================================
# Negative test cases
# =========================================================================

class TestNegativeCases:
    """Malformed inputs: truncation, bad magic, empty file."""

    def test_empty_file(self):
        with pytest.raises(ValueError, match="empty"):
            parse_mpls(b"")

    def test_truncated_header(self):
        """File too short even for the 40-byte header."""
        with pytest.raises(ValueError, match="too short"):
            parse_mpls(b"MPLS0200" + b"\x00" * 10)

    def test_wrong_magic(self):
        """File with wrong magic bytes."""
        bad = bytearray(100)
        bad[0:4] = b"NOPE"
        bad[4:8] = b"0200"
        with pytest.raises(ValueError, match="Invalid MPLS magic"):
            parse_mpls(bytes(bad))

    def test_truncated_playlist_section(self):
        """Header is valid but points to a PlayList section beyond EOF."""
        header = bytearray(40)
        header[0:4] = b"MPLS"
        header[4:8] = b"0200"
        # playlist_start points beyond file
        struct.pack_into(">I", header, 8, 9999)
        struct.pack_into(">I", header, 12, 9999)
        with pytest.raises(ValueError, match="truncated|short"):
            parse_mpls(bytes(header))

    def test_play_item_count_exceeds_data(self):
        """Header claims more play items than bytes available.

        We craft a valid header + PlayList section header that says 100 items
        but the file is too short to contain them. Parser should handle
        gracefully (stop parsing, not crash).
        """
        header = bytearray(40)
        header[0:4] = b"MPLS"
        header[4:8] = b"0200"
        struct.pack_into(">I", header, 8, 40)   # playlist starts at 40
        struct.pack_into(">I", header, 12, 60)   # marks at 60

        # PlayList section: length(4) + reserved(2) + n_items(2) + n_subpaths(2)
        playlist = bytearray(20)
        struct.pack_into(">I", playlist, 0, 16)   # section length = 16
        struct.pack_into(">H", playlist, 6, 100)  # claim 100 items
        struct.pack_into(">H", playlist, 8, 0)

        # Mark section (minimal)
        marks = bytearray(6)
        struct.pack_into(">I", marks, 0, 2)  # section length = 2
        struct.pack_into(">H", marks, 4, 0)  # 0 marks

        data = bytes(header) + bytes(playlist) + bytes(marks)
        # Should not crash — just parse 0 items since data is insufficient
        result = parse_mpls(data)
        assert len(result.play_items) == 0


# =========================================================================
# Full scenario test
# =========================================================================

class TestFullScenario:
    """Realistic BD structure: movie-like playlist with multiple streams."""

    def test_lotr_style_bd(self):
        """Approximate a Lord of the Rings BD: main feature + bonus content,
        multiple audio tracks, many subtitle languages, chapters."""
        data = make_mpls_file(
            version="0200",
            play_items=[
                {
                    "clip_id": "00001",
                    "in_time": 0.0,
                    "out_time": 7200.0,  # 2 hours
                    "audio_streams": [
                        (0x83, "eng", 8),   # TrueHD 7.1 English
                        (0x81, "fra", 6),   # AC3 5.1 French
                        (0x81, "spa", 6),   # AC3 5.1 Spanish
                        (0x82, "deu", 6),   # DTS 5.1 German
                    ],
                    "subtitle_streams": [
                        (0x90, "eng"),
                        (0x90, "fra"),
                        (0x90, "spa"),
                        (0x90, "deu"),
                    ],
                },
            ],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 0.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 300.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 900.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 1800.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 3000.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 4200.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 5400.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 6600.0},
            ],
        )
        result = parse_mpls(data)

        # Play items
        assert len(result.play_items) == 1
        assert result.play_items[0].clip_id == "00001"
        assert result.play_items[0].duration_seconds == pytest.approx(7200.0, abs=0.1)

        # Audio
        assert len(result.audio_streams) == 4
        assert result.audio_streams[0].codec == "TrueHD"
        assert result.audio_streams[0].channels == 8
        assert [s.language for s in result.audio_streams] == ["eng", "fra", "spa", "deu"]

        # Subtitles
        assert len(result.subtitle_streams) == 4
        assert [s.language for s in result.subtitle_streams] == ["eng", "fra", "spa", "deu"]

        # Chapters
        assert len(result.chapter_marks) == 8
        assert all(cm.mark_type == 1 for cm in result.chapter_marks)

        # Version
        assert result.version == "0200"

    def test_uhd_disc(self):
        """4K UHD disc with HEVC video reference."""
        data = make_mpls_file(
            version="0300",
            play_items=[
                {
                    "clip_id": "00800",
                    "in_time": 0.0,
                    "out_time": 5400.0,  # 1.5 hours
                    "audio_streams": [
                        (0x86, "eng", 8),   # DTS-HD MA 7.1
                        (0x84, "eng", 8),   # AC3+ 7.1
                    ],
                    "subtitle_streams": [
                        (0x90, "eng"),
                    ],
                },
            ],
            chapter_marks=[
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 0.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 1800.0},
                {"mark_type": 1, "play_item_ref": 0, "timestamp": 3600.0},
            ],
        )
        result = parse_mpls(data)
        assert result.version == "0300"
        assert len(result.play_items) == 1
        assert result.play_items[0].clip_id == "00800"
        assert result.audio_streams[0].codec == "DTS-HD MA"
        assert result.audio_streams[1].codec == "AC3+"
        assert len(result.chapter_marks) == 3

    def test_many_streams(self):
        """Stress test: many audio + subtitle streams (32 each)."""
        audio = [(0x81, f"a{i:02d}", 6) for i in range(32)]
        subs = [(0x90, f"s{i:02d}") for i in range(32)]
        data = make_mpls_file(play_items=[{
            "clip_id": "00001", "in_time": 0, "out_time": 100.0,
            "audio_streams": audio,
            "subtitle_streams": subs,
        }])
        result = parse_mpls(data)
        assert len(result.audio_streams) == 32
        assert len(result.subtitle_streams) == 32
