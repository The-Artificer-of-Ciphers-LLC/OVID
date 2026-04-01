"""Unit tests for ovid.ifo_parser — VMG/VTS parsing and BCD time decoding."""

from __future__ import annotations

import pytest

from ovid.ifo_parser import (
    VMGInfo,
    VTSInfo,
    PGCInfo,
    AudioStream,
    SubtitleStream,
    decode_bcd_time,
    parse_vmg,
    parse_vts,
)
from conftest import encode_bcd_time, make_vmg_ifo, make_vts_ifo


# =========================================================================
# BCD time decoding
# =========================================================================

class TestDecodeBcdTime:
    """decode_bcd_time: 4-byte BCD → total seconds."""

    def test_zero(self):
        raw = encode_bcd_time(0, 0, 0)
        assert decode_bcd_time(raw) == 0

    def test_one_hour_thirty_minutes_forty_five_seconds(self):
        raw = encode_bcd_time(1, 30, 45)
        assert decode_bcd_time(raw) == 5445

    def test_max_reasonable_duration(self):
        """9:59:59 — the largest time we'd realistically see."""
        raw = encode_bcd_time(9, 59, 59)
        assert decode_bcd_time(raw) == 35999

    def test_boundary_59_minutes_59_seconds(self):
        raw = encode_bcd_time(0, 59, 59)
        assert decode_bcd_time(raw) == 3599

    def test_single_second(self):
        raw = encode_bcd_time(0, 0, 1)
        assert decode_bcd_time(raw) == 1

    def test_fps_flag_does_not_affect_result(self):
        """Different fps flags should produce the same whole-second value."""
        raw_25 = encode_bcd_time(1, 0, 0, fps_flag=1)
        raw_30 = encode_bcd_time(1, 0, 0, fps_flag=3)
        assert decode_bcd_time(raw_25) == 3600
        assert decode_bcd_time(raw_30) == 3600

    def test_invalid_bcd_nibble_does_not_crash(self):
        """A BCD byte with invalid nibbles (0xAA) should not crash."""
        raw = bytes([0xAA, 0xAA, 0xAA, 0x00])
        # Invalid nibbles are clamped to 0
        result = decode_bcd_time(raw)
        assert isinstance(result, int)
        assert result == 0  # all nibbles clamped

    def test_truncated_input_raises(self):
        with pytest.raises(ValueError, match="4 bytes"):
            decode_bcd_time(b"\x00\x00")


# =========================================================================
# VMG parsing (VIDEO_TS.IFO)
# =========================================================================

class TestParseVMG:
    """parse_vmg: extract VTS count and title count from VMG blobs."""

    def test_basic_vmg(self):
        data = make_vmg_ifo(vts_count=3, title_entries=8)
        info = parse_vmg(data)
        assert isinstance(info, VMGInfo)
        assert info.vts_count == 3
        assert info.title_count == 8

    def test_single_vts(self):
        data = make_vmg_ifo(vts_count=1, title_entries=1)
        info = parse_vmg(data)
        assert info.vts_count == 1
        assert info.title_count == 1

    def test_many_titles(self):
        data = make_vmg_ifo(vts_count=10, title_entries=99)
        info = parse_vmg(data)
        assert info.vts_count == 10
        assert info.title_count == 99

    def test_truncated_file_raises(self):
        with pytest.raises(ValueError, match="too short"):
            parse_vmg(b"\x00" * 10)

    def test_wrong_identifier_raises(self):
        bad = bytearray(4096)
        bad[0:12] = b"NOT-A-VMG!!!"
        with pytest.raises(ValueError, match="Invalid VMG identifier"):
            parse_vmg(bytes(bad))


# =========================================================================
# VTS parsing (VTS_XX_0.IFO)
# =========================================================================

class TestParseVTS:
    """parse_vts: extract PGCs, audio streams, subtitle streams from VTS blobs."""

    def test_single_pgc(self):
        data = make_vts_ifo(
            pgcs=[(1, 30, 45, 12)],
            audio_streams=[(0, "en", 6)],
            subtitle_streams=["en"],
        )
        info = parse_vts(data)
        assert isinstance(info, VTSInfo)
        assert len(info.pgc_list) == 1
        assert info.pgc_list[0].duration_seconds == 5445
        assert info.pgc_list[0].chapter_count == 12

    def test_multiple_pgcs(self):
        data = make_vts_ifo(
            pgcs=[
                (2, 0, 0, 28),   # 7200s
                (0, 1, 44, 3),   # 104s
                (0, 1, 28, 2),   # 88s
            ],
        )
        info = parse_vts(data)
        assert len(info.pgc_list) == 3
        assert info.pgc_list[0].duration_seconds == 7200
        assert info.pgc_list[0].chapter_count == 28
        assert info.pgc_list[1].duration_seconds == 104
        assert info.pgc_list[1].chapter_count == 3
        assert info.pgc_list[2].duration_seconds == 88
        assert info.pgc_list[2].chapter_count == 2

    def test_zero_pgcs(self):
        """Zero PGCs should produce an empty list, not a crash."""
        data = make_vts_ifo(pgcs=[], audio_streams=[], subtitle_streams=[])
        info = parse_vts(data)
        assert info.pgc_list == []

    def test_audio_ac3(self):
        data = make_vts_ifo(audio_streams=[(0, "en", 6)])
        info = parse_vts(data)
        assert len(info.audio_streams) == 1
        assert info.audio_streams[0].codec == "AC3"
        assert info.audio_streams[0].language == "en"
        assert info.audio_streams[0].channels == 6

    def test_audio_dts(self):
        data = make_vts_ifo(audio_streams=[(6, "fr", 2)])
        info = parse_vts(data)
        assert len(info.audio_streams) == 1
        assert info.audio_streams[0].codec == "DTS"
        assert info.audio_streams[0].language == "fr"
        assert info.audio_streams[0].channels == 2

    def test_audio_lpcm(self):
        data = make_vts_ifo(audio_streams=[(4, "ja", 2)])
        info = parse_vts(data)
        assert info.audio_streams[0].codec == "LPCM"

    def test_audio_mpeg1(self):
        data = make_vts_ifo(audio_streams=[(2, "de", 2)])
        info = parse_vts(data)
        assert info.audio_streams[0].codec == "MPEG-1"

    def test_audio_mpeg2(self):
        data = make_vts_ifo(audio_streams=[(3, "es", 6)])
        info = parse_vts(data)
        assert info.audio_streams[0].codec == "MPEG-2"

    def test_multiple_audio_streams(self):
        data = make_vts_ifo(
            audio_streams=[
                (0, "en", 6),
                (6, "fr", 6),
                (0, "es", 2),
            ],
        )
        info = parse_vts(data)
        assert len(info.audio_streams) == 3
        assert info.audio_streams[0] == AudioStream(codec="AC3", language="en", channels=6)
        assert info.audio_streams[1] == AudioStream(codec="DTS", language="fr", channels=6)
        assert info.audio_streams[2] == AudioStream(codec="AC3", language="es", channels=2)

    def test_subtitle_streams(self):
        data = make_vts_ifo(subtitle_streams=["en", "fr", "es"])
        info = parse_vts(data)
        assert len(info.subtitle_streams) == 3
        assert info.subtitle_streams[0] == SubtitleStream(language="en")
        assert info.subtitle_streams[1] == SubtitleStream(language="fr")
        assert info.subtitle_streams[2] == SubtitleStream(language="es")

    def test_zero_audio_streams(self):
        data = make_vts_ifo(audio_streams=[])
        info = parse_vts(data)
        assert info.audio_streams == []

    def test_zero_subtitle_streams(self):
        data = make_vts_ifo(subtitle_streams=[])
        info = parse_vts(data)
        assert info.subtitle_streams == []

    def test_truncated_file_raises(self):
        with pytest.raises(ValueError, match="too short"):
            parse_vts(b"\x00" * 10)

    def test_wrong_identifier_raises(self):
        bad = bytearray(8192)
        bad[0:12] = b"NOT-A-VTS!!!"
        with pytest.raises(ValueError, match="Invalid VTS identifier"):
            parse_vts(bytes(bad))

    def test_full_scenario_lotr_style(self):
        """Approximate a Lord of the Rings-style disc structure:
        3 PGCs, multiple audio/subtitle languages."""
        data = make_vts_ifo(
            pgcs=[
                (2, 1, 27, 28),    # 7287s, 28 chapters
                (0, 1, 44, 3),     # 104s, 3 chapters
            ],
            audio_streams=[
                (0, "en", 6),      # AC3 English 5.1
                (0, "fr", 6),      # AC3 French 5.1
                (0, "es", 2),      # AC3 Spanish stereo
            ],
            subtitle_streams=["en", "fr", "es", "pt"],
        )
        info = parse_vts(data)

        assert len(info.pgc_list) == 2
        assert info.pgc_list[0].duration_seconds == 7287
        assert info.pgc_list[0].chapter_count == 28
        assert info.pgc_list[1].duration_seconds == 104
        assert info.pgc_list[1].chapter_count == 3

        assert len(info.audio_streams) == 3
        assert [s.language for s in info.audio_streams] == ["en", "fr", "es"]
        assert [s.codec for s in info.audio_streams] == ["AC3", "AC3", "AC3"]

        assert len(info.subtitle_streams) == 4
        assert [s.language for s in info.subtitle_streams] == ["en", "fr", "es", "pt"]
