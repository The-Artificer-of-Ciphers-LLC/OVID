"""Pure-Python IFO binary parser for DVD VIDEO_TS.IFO (VMG) and VTS_XX_0.IFO files.

Extracts the structural metadata needed for OVID-DVD-1 fingerprinting:
VTS count, title count, PGC durations, chapter counts, audio/subtitle streams.

Reference: DVD-Video specification (ECMA-267 / ISO 9660 + UDF bridge).
IFO files use big-endian byte order throughout.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

SECTOR_SIZE = 2048

AUDIO_CODEC_MAP = {
    0: "AC3",
    2: "MPEG-1",
    3: "MPEG-2",
    4: "LPCM",
    6: "DTS",
}


@dataclass(frozen=True)
class AudioStream:
    """A single audio stream from VTS attributes."""
    codec: str
    language: str
    channels: int


@dataclass(frozen=True)
class SubtitleStream:
    """A single subtitle stream from VTS attributes."""
    language: str


@dataclass(frozen=True)
class PGCInfo:
    """A single Program Chain: playback duration and chapter count."""
    duration_seconds: int
    chapter_count: int


@dataclass(frozen=True)
class VTSInfo:
    """Parsed content of a VTS_XX_0.IFO file."""
    pgc_list: list[PGCInfo] = field(default_factory=list)
    audio_streams: list[AudioStream] = field(default_factory=list)
    subtitle_streams: list[SubtitleStream] = field(default_factory=list)


@dataclass(frozen=True)
class VMGInfo:
    """Parsed content of VIDEO_TS.IFO (Video Manager)."""
    vts_count: int
    title_count: int


# ---------------------------------------------------------------------------
# BCD time decoding
# ---------------------------------------------------------------------------

def _decode_bcd_byte(b: int) -> int:
    """Decode a single BCD-encoded byte.  Invalid nibbles (>9) are clamped to 0
    to avoid crashes on malformed data."""
    hi = (b >> 4) & 0x0F
    lo = b & 0x0F
    # Defensive: clamp invalid BCD nibbles rather than crashing.
    if hi > 9:
        hi = 0
    if lo > 9:
        lo = 0
    return hi * 10 + lo


def decode_bcd_time(b: bytes) -> int:
    """Decode a 4-byte BCD-encoded PGC playback time to total seconds.

    Layout (bytes 0-3):
        byte 0: hours   (BCD)
        byte 1: minutes (BCD)
        byte 2: seconds (BCD)
        byte 3: frames  (BCD low 6 bits) + frame-rate flag (high 2 bits)
                frame-rate flag: 01 = 25 fps, 11 = 29.97 fps (ignored for whole-second rounding)

    Returns total whole seconds (frames are dropped per spec §2.1).
    """
    if len(b) < 4:
        raise ValueError(f"BCD time requires 4 bytes, got {len(b)}")

    hours = _decode_bcd_byte(b[0])
    minutes = _decode_bcd_byte(b[1])
    seconds = _decode_bcd_byte(b[2])
    # byte 3: frames — ignored per spec (round to whole seconds)
    return hours * 3600 + minutes * 60 + seconds


# ---------------------------------------------------------------------------
# VMG parser  (VIDEO_TS.IFO)
# ---------------------------------------------------------------------------

_VMG_ID = b"DVDVIDEO-VMG"
_VTS_ID = b"DVDVIDEO-VTS"


def parse_vmg(data: bytes) -> VMGInfo:
    """Parse a VIDEO_TS.IFO (VMG) binary blob.

    Extracts:
      - VTS count (offset 0x3E, 2 bytes BE)
      - Title count from TT_SRPT table (sector offset at 0x00C4)

    Raises ValueError on truncated or misidentified data.
    """
    if len(data) < 0x100:
        raise ValueError(
            f"VMG data too short ({len(data)} bytes); minimum ~256 bytes required"
        )

    identifier = data[0:12]
    if identifier != _VMG_ID:
        raise ValueError(
            f"Invalid VMG identifier: expected {_VMG_ID!r}, got {identifier!r}"
        )

    vts_count = struct.unpack_from(">H", data, 0x3E)[0]

    # TT_SRPT sector offset lives at 0x00C4 (4 bytes BE).
    tt_srpt_sector = struct.unpack_from(">I", data, 0x00C4)[0]
    tt_srpt_offset = tt_srpt_sector * SECTOR_SIZE

    # The TT_SRPT header: first 2 bytes = number of title entries.
    if tt_srpt_offset + 2 > len(data):
        # Can't read TT_SRPT — return 0 titles as best-effort.
        return VMGInfo(vts_count=vts_count, title_count=0)

    title_count = struct.unpack_from(">H", data, tt_srpt_offset)[0]
    return VMGInfo(vts_count=vts_count, title_count=title_count)


# ---------------------------------------------------------------------------
# VTS parser  (VTS_XX_0.IFO)
# ---------------------------------------------------------------------------

def _parse_audio_streams(data: bytes) -> list[AudioStream]:
    """Parse audio stream attributes starting at VTS IFO offset 0x0200.

    Layout at 0x0200:
        2 bytes: number of audio streams (BE)
        Then 8 bytes per stream:
            byte 0: high 3 bits = coding mode
            bytes 2-3: language code (ISO 639-2, 2 ASCII chars)
            byte 5 bits 2-0: quantization / DRC (we don't need this)
            byte 1 bits 2-0: number of channels minus 1
    """
    if len(data) < 0x0202:
        return []

    stream_count = struct.unpack_from(">H", data, 0x0200)[0]
    if stream_count == 0:
        return []

    streams: list[AudioStream] = []
    base = 0x0204  # first stream descriptor starts 4 bytes after count
    # Actually in real IFO, the area at 0x0200 is:
    #   2 bytes: number of streams
    #   2 bytes: reserved
    #   then 8 bytes per stream
    # But many implementations treat offset 0x0202 as start with 8-byte stride.
    # Let's use the standard layout: count at 0x0200, then 8*stream blocks starting at 0x0204.
    # However, the DVD spec actually packs it as: 0x0200 = count(2) + reserved(2), then 8 bytes each.

    for i in range(stream_count):
        offset = base + i * 8
        if offset + 8 > len(data):
            break

        coding_byte = data[offset]
        coding_mode = (coding_byte >> 5) & 0x07
        codec = AUDIO_CODEC_MAP.get(coding_mode, f"unknown({coding_mode})")

        # Language code: 2 bytes at stream_offset + 2
        lang_hi = data[offset + 2]
        lang_lo = data[offset + 3]
        if 0x20 < lang_hi < 0x7F and 0x20 < lang_lo < 0x7F:
            language = chr(lang_hi) + chr(lang_lo)
        else:
            language = ""

        # Channels: low 3 bits of byte 1 = channels - 1
        channels = (data[offset + 1] & 0x07) + 1

        streams.append(AudioStream(codec=codec, language=language, channels=channels))

    return streams


def _parse_subtitle_streams(data: bytes) -> list[SubtitleStream]:
    """Parse subtitle stream attributes starting at VTS IFO offset 0x0254.

    Layout at 0x0254:
        2 bytes: number of subtitle streams (BE)
        2 bytes: reserved
        Then 6 bytes per stream:
            bytes 2-3: language code (ISO 639-2, 2 ASCII chars)
    """
    if len(data) < 0x0256:
        return []

    stream_count = struct.unpack_from(">H", data, 0x0254)[0]
    if stream_count == 0:
        return []

    streams: list[SubtitleStream] = []
    base = 0x0258  # after count(2) + reserved(2)

    for i in range(stream_count):
        offset = base + i * 6
        if offset + 6 > len(data):
            break

        lang_hi = data[offset + 2]
        lang_lo = data[offset + 3]
        if 0x20 < lang_hi < 0x7F and 0x20 < lang_lo < 0x7F:
            language = chr(lang_hi) + chr(lang_lo)
        else:
            language = ""

        streams.append(SubtitleStream(language=language))

    return streams


def _parse_pgci(data: bytes, pgci_offset: int) -> list[PGCInfo]:
    """Parse the VTS_PGCI (Program Chain Information) table.

    The PGCI table header (at pgci_offset):
        2 bytes: number of PGCs (BE)
        2 bytes: reserved
        4 bytes: end offset relative to pgci_offset (unused here)

    Then for each PGC, an 8-byte search-pointer entry:
        1 byte:  PGC category
        3 bytes: reserved/padding
        4 bytes: byte offset of PGC block relative to pgci_offset (BE)

    Each PGC block:
        offset +0x00: 2 bytes — reserved
        offset +0x02: 1 byte  — nr_of_programs (= chapter count)
        offset +0x03: 1 byte  — nr_of_cells
        offset +0x04: 4 bytes — playback time (BCD)
    """
    if pgci_offset + 8 > len(data):
        return []

    pgc_count = struct.unpack_from(">H", data, pgci_offset)[0]
    if pgc_count == 0:
        return []

    pgcs: list[PGCInfo] = []
    search_ptr_base = pgci_offset + 8  # after header (2+2+4 bytes)

    for i in range(pgc_count):
        entry_offset = search_ptr_base + i * 8
        if entry_offset + 8 > len(data):
            break

        # PGC block offset relative to pgci_offset
        pgc_rel_offset = struct.unpack_from(">I", data, entry_offset + 4)[0]
        pgc_abs_offset = pgci_offset + pgc_rel_offset

        if pgc_abs_offset + 8 > len(data):
            break

        # nr_of_programs at PGC+0x02, nr_of_cells at PGC+0x03
        nr_of_programs = data[pgc_abs_offset + 0x02]
        # chapter_count from the task plan says "cell count" but spec §2.1 says
        # "number of chapters (cell count)".  The nr_of_programs is the chapter count
        # in DVD parlance (programs = chapters), while nr_of_cells is the cell count.
        # The spec says "number of chapters (cell count)" — use nr_of_programs as chapter count.
        chapter_count = nr_of_programs

        # Playback time: 4 bytes BCD at PGC+0x04
        time_bytes = data[pgc_abs_offset + 0x04: pgc_abs_offset + 0x08]
        duration = decode_bcd_time(time_bytes)

        pgcs.append(PGCInfo(duration_seconds=duration, chapter_count=chapter_count))

    return pgcs


def parse_vts(data: bytes) -> VTSInfo:
    """Parse a VTS_XX_0.IFO binary blob.

    Extracts audio attributes, subtitle attributes, and PGC info (durations + chapters).

    Raises ValueError on truncated or misidentified data.
    """
    if len(data) < 0x100:
        raise ValueError(
            f"VTS data too short ({len(data)} bytes); minimum ~256 bytes required"
        )

    identifier = data[0:12]
    if identifier != _VTS_ID:
        raise ValueError(
            f"Invalid VTS identifier: expected {_VTS_ID!r}, got {identifier!r}"
        )

    audio_streams = _parse_audio_streams(data)
    subtitle_streams = _parse_subtitle_streams(data)

    # VTS_PGCI sector offset at 0x00CC (4 bytes BE)
    pgci_sector = struct.unpack_from(">I", data, 0x00CC)[0]
    pgci_offset = pgci_sector * SECTOR_SIZE

    pgc_list = _parse_pgci(data, pgci_offset)

    return VTSInfo(
        pgc_list=pgc_list,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
    )
