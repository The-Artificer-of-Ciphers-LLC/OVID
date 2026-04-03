"""Pure-Python MPLS binary parser for Blu-ray / UHD disc playlists.

Extracts the structural metadata needed for OVID-BD fingerprinting:
play items (clip references with in/out timestamps), stream attributes
(audio, subtitle, video), and chapter marks.

MPLS files are big-endian with a header identifying format version:
  "MPLS" + "0200" = standard Blu-ray
  "MPLS" + "0300" = 4K UHD

Key structures:
  - AppInfoPlayList (8 bytes of general info)
  - PlayList: PlayItem count + each PlayItem with STN_table for streams
  - PlayListMark: chapter marks with timestamps

Reference: Blu-ray Disc Association specification (AACS / BD-ROM Part 3).
All multi-byte integers are big-endian.
Timestamps are in 45 kHz ticks (standard MPEG-2 transport stream clock).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MPLS_MAGIC = b"MPLS"
_TICK_RATE = 45_000  # 45 kHz MPEG-2 clock

# Stream coding type values in STN_table
STREAM_CODING_TYPE_MAP: dict[int, str] = {
    0x01: "MPEG-2 Video",
    0x02: "MPEG-2 Video",
    0x1B: "H.264/AVC",
    0x24: "H.265/HEVC",
    0x80: "LPCM",
    0x81: "AC3",
    0x82: "DTS",
    0x83: "TrueHD",
    0x84: "AC3+",
    0x85: "DTS-HD HR",
    0x86: "DTS-HD MA",
    0xA1: "AC3+ Secondary",
    0xA2: "DTS-HD Secondary",
    0x90: "PGS",        # Presentation Graphics (subtitles)
    0x91: "IG",         # Interactive Graphics
    0x92: "Text Subtitle",
}

# Audio codec coding types (subset used for stream classification)
_AUDIO_CODING_TYPES = {0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0xA1, 0xA2}
_SUBTITLE_CODING_TYPES = {0x90, 0x92}

# Channel layout (4-bit field in audio stream attributes)
_CHANNEL_MAP: dict[int, int] = {
    0x01: 1,   # mono
    0x03: 2,   # stereo
    0x06: 6,   # 5.1
    0x0C: 8,   # 7.1
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MplsHeader:
    """MPLS file header: magic, version, and section offsets."""
    version: str          # "0200" = BD, "0300" = UHD
    playlist_start: int   # byte offset to PlayList section
    mark_start: int       # byte offset to PlayListMark section


@dataclass(frozen=True)
class StreamEntry:
    """A single stream from a PlayItem's STN_table."""
    stream_type: str   # human-readable codec name
    codec: str         # short codec id (e.g. "AC3", "DTS-HD MA", "PGS")
    language: str      # 3-letter ISO 639-2 code, or ""
    channels: int      # audio channel count (0 for non-audio)


@dataclass(frozen=True)
class PlayItem:
    """A single PlayItem (clip reference) from the PlayList."""
    clip_id: str           # 5-character clip filename (e.g. "00001")
    in_time: int           # start timestamp in 45 kHz ticks
    out_time: int          # end timestamp in 45 kHz ticks
    duration_seconds: float  # computed: (out_time - in_time) / 45000


@dataclass(frozen=True)
class ChapterMark:
    """A single mark entry from PlayListMark."""
    mark_type: int         # 1 = entry mark (chapter), 2 = link point
    play_item_ref: int     # index of the PlayItem this mark refers to
    timestamp: int         # 45 kHz ticks
    duration_seconds: float  # computed: timestamp / 45000


@dataclass(frozen=True)
class MplsPlaylist:
    """Complete parsed MPLS file."""
    header: MplsHeader
    play_items: list[PlayItem] = field(default_factory=list)
    audio_streams: list[StreamEntry] = field(default_factory=list)
    subtitle_streams: list[StreamEntry] = field(default_factory=list)
    chapter_marks: list[ChapterMark] = field(default_factory=list)

    @property
    def version(self) -> str:
        """Convenience accessor for header version."""
        return self.header.version


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ticks_to_seconds(ticks: int) -> float:
    """Convert 45 kHz MPEG-2 ticks to seconds (3 decimal places)."""
    return round(ticks / _TICK_RATE, 3)


def _safe_unpack(fmt: str, data: bytes, offset: int, context: str = "") -> tuple:
    """Unpack with bounds checking and a clear error on truncation."""
    size = struct.calcsize(fmt)
    if offset + size > len(data):
        raise ValueError(
            f"MPLS truncated at offset 0x{offset:04X}: need {size} bytes for "
            f"{context or fmt}, but only {len(data) - offset} available "
            f"(total file size: {len(data)})"
        )
    return struct.unpack_from(fmt, data, offset)


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_header(data: bytes) -> MplsHeader:
    """Parse the 40-byte MPLS header."""
    if len(data) < 40:
        raise ValueError(
            f"MPLS data too short ({len(data)} bytes); minimum 40 bytes required "
            f"for header"
        )

    magic = data[0:4]
    if magic != _MPLS_MAGIC:
        raise ValueError(
            f"Invalid MPLS magic: expected {_MPLS_MAGIC!r}, got {magic!r}"
        )

    version = data[4:8].decode("ascii", errors="replace")

    # PlayList start offset at byte 8 (4 bytes BE)
    playlist_start = _safe_unpack(">I", data, 8, "playlist_start")[0]
    # PlayListMark start offset at byte 12 (4 bytes BE)
    mark_start = _safe_unpack(">I", data, 12, "mark_start")[0]

    return MplsHeader(
        version=version,
        playlist_start=playlist_start,
        mark_start=mark_start,
    )


def _parse_stn_table(
    data: bytes, stn_offset: int, stn_length: int,
) -> tuple[list[StreamEntry], list[StreamEntry]]:
    """Parse the STN_table within a PlayItem to extract audio and subtitle streams.

    STN_table layout (relative to stn_offset):
      0-1: length (2 bytes, BE) — already consumed by caller
      2-3: reserved
      4:   number of primary video streams
      5:   number of primary audio streams
      6:   number of PG (subtitle) streams
      7:   number of IG (interactive graphics) streams
      8:   number of secondary audio streams
      9:   number of secondary video streams
      10:  number of secondary PG streams (BD-J)
      11:  number of DV streams (UHD)
      12+: stream entries (variable)

    Each stream entry:
      0:   length of the entry (1 byte)
      1:   stream_type (1 byte — indicates mux position)
      Then depending on stream_type:
        type 1: 2 bytes PID
        type 2: 4 bytes (sub-path)
        type 3: 4 bytes (sub-path)
        type 4: 4 bytes (sub-path)
      After PID/sub-path data:
        coding_type (1 byte)
        For audio: format (4 bits) + sample_rate (4 bits), language (3 bytes)
        For PG: language (3 bytes)
    """
    audio_streams: list[StreamEntry] = []
    subtitle_streams: list[StreamEntry] = []

    # STN body layout (after the 2-byte length consumed by caller):
    #   0-1: reserved
    #   2:   n_video
    #   3:   n_audio
    #   4:   n_pg (subtitle)
    #   5:   n_ig
    #   6:   n_secondary_audio
    #   7:   n_secondary_video
    #   8:   n_secondary_pg
    #   9:   n_dv
    #   10+: stream entries

    # Need at least 10 bytes for the header part of the STN table
    if stn_offset + 10 > len(data):
        return audio_streams, subtitle_streams

    # Extract stream counts (after 2 reserved bytes)
    n_video = data[stn_offset + 2]
    n_audio = data[stn_offset + 3]
    n_pg = data[stn_offset + 4]
    n_ig = data[stn_offset + 5]
    n_sec_audio = data[stn_offset + 6]
    n_sec_video = data[stn_offset + 7]

    total_entries = n_video + n_audio + n_pg + n_ig + n_sec_audio + n_sec_video
    pos = stn_offset + 10  # start of stream entries
    stn_end = stn_offset + stn_length

    for entry_idx in range(total_entries):
        if pos >= stn_end or pos >= len(data):
            break

        # Stream entry: length (1 byte)
        entry_len = data[pos]
        entry_start = pos + 1

        if entry_start + entry_len > len(data):
            break

        # The first byte of the entry payload is the stream_type
        if entry_len < 1:
            pos = entry_start + entry_len
            continue

        stream_type_byte = data[entry_start]

        # Determine how many bytes the PID/ref data uses
        if stream_type_byte == 1:
            pid_size = 2
        elif stream_type_byte in (2, 3, 4):
            pid_size = 4
        else:
            pid_size = 2  # default assumption

        attr_offset = entry_start + 1 + pid_size

        # Stream attributes: length (1 byte), then coding_type, then format-specific
        if attr_offset >= len(data):
            pos = entry_start + entry_len
            continue

        attr_len = data[attr_offset]
        coding_offset = attr_offset + 1

        if coding_offset >= len(data):
            pos = entry_start + entry_len
            continue

        coding_type = data[coding_offset]
        codec_name = STREAM_CODING_TYPE_MAP.get(coding_type, f"unknown(0x{coding_type:02X})")

        # Short codec name for StreamEntry.codec
        short_codec = codec_name

        language = ""
        channels = 0

        if coding_type in _AUDIO_CODING_TYPES:
            # Audio attributes: format+sample_rate (1 byte), then 3-byte language
            if coding_offset + 2 <= len(data):
                format_byte = data[coding_offset + 1]
                channel_layout = (format_byte >> 4) & 0x0F
                channels = _CHANNEL_MAP.get(channel_layout, channel_layout)

            if coding_offset + 5 <= len(data):
                lang_bytes = data[coding_offset + 2: coding_offset + 5]
                try:
                    language = lang_bytes.decode("ascii").strip("\x00")
                except UnicodeDecodeError:
                    language = ""

            audio_streams.append(StreamEntry(
                stream_type=short_codec,
                codec=short_codec,
                language=language,
                channels=channels,
            ))

        elif coding_type in _SUBTITLE_CODING_TYPES:
            # PG subtitle attributes: 1 byte (char_code), then 3-byte language
            if coding_offset + 5 <= len(data):
                lang_bytes = data[coding_offset + 2: coding_offset + 5]
                try:
                    language = lang_bytes.decode("ascii").strip("\x00")
                except UnicodeDecodeError:
                    language = ""

            subtitle_streams.append(StreamEntry(
                stream_type=short_codec,
                codec=short_codec,
                language=language,
                channels=0,
            ))

        # Advance past this entry
        pos = entry_start + entry_len

    return audio_streams, subtitle_streams


def _parse_play_items(
    data: bytes, playlist_offset: int,
) -> tuple[list[PlayItem], list[StreamEntry], list[StreamEntry]]:
    """Parse the PlayList section starting at playlist_offset.

    PlayList section layout:
      0-3: length of PlayList section (4 bytes BE) — excludes these 4 bytes
      4-5: reserved
      6-7: number of PlayItems (2 bytes BE)
      8-9: number of SubPaths (2 bytes BE)
      10+: PlayItem entries (variable length)

    Each PlayItem:
      0-1: length of PlayItem (2 bytes BE)
      2-6: clip information filename (5 ASCII chars, e.g. "00001")
      7-10: clip codec identifier (4 ASCII chars, e.g. "M2TS")
      11-12: reserved / connection condition flags
      13:   ref_to_STC_id
      14-17: IN_time (4 bytes BE, 45 kHz ticks)
      18-21: OUT_time (4 bytes BE, 45 kHz ticks)
      ... more fields ...
      Then at variable offset: STN_table

    Returns play_items, collected audio_streams, collected subtitle_streams.
    """
    play_items: list[PlayItem] = []
    all_audio: list[StreamEntry] = []
    all_subs: list[StreamEntry] = []

    # Read section length and play item count
    (section_length,) = _safe_unpack(
        ">I", data, playlist_offset, "PlayList section length"
    )
    section_end = playlist_offset + 4 + section_length

    if playlist_offset + 10 > len(data):
        raise ValueError(
            f"MPLS truncated: PlayList header requires 10 bytes at offset "
            f"0x{playlist_offset:04X}"
        )

    (n_play_items,) = _safe_unpack(
        ">H", data, playlist_offset + 6, "PlayItem count"
    )
    # (n_sub_paths,) at offset +8, not needed for fingerprinting

    pos = playlist_offset + 10  # start of first PlayItem

    for i in range(n_play_items):
        if pos + 2 > len(data) or pos >= section_end:
            break

        (item_length,) = _safe_unpack(">H", data, pos, f"PlayItem[{i}] length")
        item_start = pos + 2  # data starts after the 2-byte length field

        if item_start + 20 > len(data):
            # PlayItem is truncated — stop parsing remaining items gracefully
            # rather than crashing. This handles the case where n_play_items
            # exceeds the actual data available.
            break

        # Clip ID: 5 ASCII chars at item_start + 0
        clip_id_bytes = data[item_start: item_start + 5]
        try:
            clip_id = clip_id_bytes.decode("ascii")
        except UnicodeDecodeError:
            clip_id = clip_id_bytes.hex()

        # IN_time at item_start + 14, OUT_time at item_start + 18
        # (skipping clip codec id, connection_condition, etc.)
        (in_time,) = _safe_unpack(">I", data, item_start + 14, f"PlayItem[{i}] IN_time")
        (out_time,) = _safe_unpack(">I", data, item_start + 18, f"PlayItem[{i}] OUT_time")

        duration_seconds = _ticks_to_seconds(out_time - in_time) if out_time >= in_time else 0.0

        play_items.append(PlayItem(
            clip_id=clip_id,
            in_time=in_time,
            out_time=out_time,
            duration_seconds=duration_seconds,
        ))

        # STN_table follows at a fixed offset within the PlayItem.
        # After the base PlayItem fields (clip info, times, UO_mask, etc.),
        # the STN_table starts. For standard BD (0200), the STN_table
        # starts at item_start + 34. We read its 2-byte length first.
        stn_offset = item_start + 34
        if stn_offset + 2 <= len(data) and stn_offset < item_start + item_length:
            (stn_length,) = _safe_unpack(">H", data, stn_offset, f"PlayItem[{i}] STN length")
            # The STN data starts right after the 2-byte length
            stn_data_offset = stn_offset + 2
            if stn_length > 0 and stn_data_offset + stn_length <= len(data):
                audio, subs = _parse_stn_table(data, stn_data_offset, stn_length)
                all_audio.extend(audio)
                all_subs.extend(subs)

        # Advance to next PlayItem
        pos = item_start + item_length

    return play_items, all_audio, all_subs


def _parse_marks(data: bytes, mark_offset: int) -> list[ChapterMark]:
    """Parse the PlayListMark section starting at mark_offset.

    PlayListMark section layout:
      0-3: length of section (4 bytes BE)
      4-5: number of marks (2 bytes BE)
      6+:  mark entries (14 bytes each)

    Each mark entry (14 bytes):
      0:   reserved
      1:   mark_type (1 = entry/chapter, 2 = link point)
      2-3: ref_to_PlayItem_id (2 bytes BE)
      4-7: mark_time_stamp (4 bytes BE, 45 kHz ticks)
      8-9: entry_ES_PID (2 bytes, ignored)
      10-13: duration (4 bytes BE, 45 kHz ticks)
    """
    marks: list[ChapterMark] = []

    (section_length,) = _safe_unpack(
        ">I", data, mark_offset, "PlayListMark section length"
    )

    if mark_offset + 6 > len(data):
        return marks

    (n_marks,) = _safe_unpack(">H", data, mark_offset + 4, "mark count")

    pos = mark_offset + 6  # start of mark entries

    for i in range(n_marks):
        if pos + 14 > len(data):
            break

        mark_type = data[pos + 1]
        (play_item_ref,) = _safe_unpack(">H", data, pos + 2, f"mark[{i}] play_item_ref")
        (timestamp,) = _safe_unpack(">I", data, pos + 4, f"mark[{i}] timestamp")
        (duration_ticks,) = _safe_unpack(">I", data, pos + 10, f"mark[{i}] duration")

        marks.append(ChapterMark(
            mark_type=mark_type,
            play_item_ref=play_item_ref,
            timestamp=timestamp,
            duration_seconds=_ticks_to_seconds(timestamp),
        ))

        pos += 14

    return marks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_mpls(data: bytes) -> MplsPlaylist:
    """Parse an MPLS binary blob into an MplsPlaylist.

    Args:
        data: Raw bytes of an .mpls file.

    Returns:
        MplsPlaylist with header, play_items, audio_streams, subtitle_streams,
        and chapter_marks.

    Raises:
        ValueError: On truncated data, invalid magic, or structural errors.
    """
    if len(data) == 0:
        raise ValueError("MPLS data is empty (0 bytes)")

    header = _parse_header(data)

    play_items, audio_streams, subtitle_streams = _parse_play_items(
        data, header.playlist_start,
    )

    chapter_marks: list[ChapterMark] = []
    if header.mark_start > 0 and header.mark_start < len(data):
        chapter_marks = _parse_marks(data, header.mark_start)

    return MplsPlaylist(
        header=header,
        play_items=play_items,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
        chapter_marks=chapter_marks,
    )
