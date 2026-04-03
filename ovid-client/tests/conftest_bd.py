"""Synthetic MPLS binary fixture builders for deterministic Blu-ray testing.

These helpers construct minimal-but-valid .mpls blobs with known field values,
so unit tests can verify the parser against controlled inputs without needing
real disc images.

MPLS binary layout (big-endian):
  Header (40 bytes):
    0-3:   "MPLS" magic
    4-7:   version string ("0200" BD, "0300" UHD)
    8-11:  PlayList section offset (4 bytes BE)
    12-15: PlayListMark section offset (4 bytes BE)
    16-39: reserved / extension offsets

  PlayList section:
    0-3:   section length (4 bytes BE)
    4-5:   reserved
    6-7:   PlayItem count (2 bytes BE)
    8-9:   SubPath count (2 bytes BE)
    10+:   PlayItem entries (variable)

  Each PlayItem:
    0-1:   item length (2 bytes BE)
    2-6:   clip_id (5 ASCII chars)
    7-10:  codec_id (4 ASCII chars, "M2TS")
    11-12: reserved / connection_condition
    13:    ref_to_STC_id
    14-17: IN_time (4 bytes BE, 45kHz ticks)
    18-21: OUT_time (4 bytes BE, 45kHz ticks)
    22-29: UO_mask_table (8 bytes)
    30:    PlayItem_random_access_flag
    31:    still_mode
    32-33: still_time
    34+:   STN_table

  STN_table:
    0-1:   length (2 bytes BE)
    2-3:   reserved
    4:     n_video
    5:     n_audio
    6:     n_pg (subtitle)
    7:     n_ig
    8:     n_secondary_audio
    9:     n_secondary_video
    10:    n_secondary_pg
    11:    n_dv
    12+:   stream entries

  Each stream entry:
    0:     entry_length (1 byte)
    1:     stream_type (1 = primary)
    2-3:   PID (2 bytes, for stream_type 1)
    Then stream attributes:
      0:     attr_length (1 byte)
      1:     coding_type (1 byte)
      2:     format+sample_rate (audio) or char_code (PG)
      3-5:   language (3 ASCII bytes)

  PlayListMark section:
    0-3:   section length (4 bytes BE)
    4-5:   mark count (2 bytes BE)
    6+:    mark entries (14 bytes each)

  Each mark entry:
    0:     reserved
    1:     mark_type (1 = entry/chapter)
    2-3:   ref_to_PlayItem_id (2 bytes BE)
    4-7:   mark_time_stamp (4 bytes BE, 45kHz ticks)
    8-9:   entry_ES_PID (2 bytes)
    10-13: duration (4 bytes BE, 45kHz ticks)
"""

from __future__ import annotations

import struct

TICK_RATE = 45_000  # 45 kHz


def _seconds_to_ticks(seconds: float) -> int:
    """Convert seconds to 45 kHz ticks."""
    return int(seconds * TICK_RATE)


def _build_stream_entry(
    coding_type: int,
    language: str = "",
    channels: int = 0,
    pid: int = 0x1011,
) -> bytes:
    """Build a single stream entry for the STN_table.

    Returns bytes for: entry_length(1) + stream_type(1) + PID(2) +
                        attr_length(1) + coding_type(1) + format(1) + language(3)
    """
    # Stream type 1 = primary stream with 2-byte PID
    stream_type = 1
    pid_bytes = struct.pack(">H", pid)

    # Build attributes block
    #   coding_type (1 byte)
    #   format+sample_rate or char_code (1 byte)
    #   language (3 bytes)
    lang_bytes = language.encode("ascii").ljust(3, b"\x00")[:3]

    # For audio: format byte = (channel_layout << 4) | sample_rate
    # Channel layout encoding: 1=mono, 3=stereo, 6=5.1, 0x0C=7.1
    channel_layout_map = {1: 0x01, 2: 0x03, 6: 0x06, 8: 0x0C}
    channel_layout = channel_layout_map.get(channels, 0x03)

    format_byte = (channel_layout << 4) | 0x01  # sample_rate = 1 (48kHz)

    attr_data = bytes([coding_type, format_byte]) + lang_bytes
    attr_length = len(attr_data)

    # Entry payload: stream_type(1) + PID(2) + attr_length(1) + attr_data
    entry_payload = bytes([stream_type]) + pid_bytes + bytes([attr_length]) + attr_data
    entry_length = len(entry_payload)

    return bytes([entry_length]) + entry_payload


def _build_stn_table(
    audio_streams: list[tuple[int, str, int]] | None = None,
    subtitle_streams: list[tuple[int, str]] | None = None,
) -> bytes:
    """Build an STN_table for a PlayItem.

    Args:
        audio_streams: List of (coding_type, language_3char, channels).
            coding_type: 0x81=AC3, 0x83=TrueHD, 0x86=DTS-HD MA, etc.
        subtitle_streams: List of (coding_type, language_3char).
            coding_type: 0x90=PGS, 0x92=Text.
    """
    if audio_streams is None:
        audio_streams = []
    if subtitle_streams is None:
        subtitle_streams = []

    # Stream counts header (10 bytes after length+reserved)
    n_video = 0
    n_audio = len(audio_streams)
    n_pg = len(subtitle_streams)
    n_ig = 0
    n_sec_audio = 0
    n_sec_video = 0
    n_sec_pg = 0
    n_dv = 0

    header = bytes([
        0, 0,  # reserved
        n_video,
        n_audio,
        n_pg,
        n_ig,
        n_sec_audio,
        n_sec_video,
        n_sec_pg,
        n_dv,
    ])

    # Build stream entries
    entries = b""
    pid_counter = 0x1100

    for coding_type, lang, channels in audio_streams:
        entries += _build_stream_entry(coding_type, lang, channels, pid_counter)
        pid_counter += 1

    for coding_type, lang in subtitle_streams:
        entries += _build_stream_entry(coding_type, lang, 0, pid_counter)
        pid_counter += 1

    stn_body = header + entries
    # STN_table: 2-byte length + body
    stn_length = len(stn_body)
    return struct.pack(">H", stn_length) + stn_body


def _build_play_item(
    clip_id: str = "00001",
    in_time_seconds: float = 0.0,
    out_time_seconds: float = 0.0,
    audio_streams: list[tuple[int, str, int]] | None = None,
    subtitle_streams: list[tuple[int, str]] | None = None,
) -> bytes:
    """Build a single PlayItem binary block.

    Returns bytes for: item_length(2) + item_data
    """
    clip_id_bytes = clip_id.encode("ascii").ljust(5, b"0")[:5]
    codec_id = b"M2TS"

    in_time = _seconds_to_ticks(in_time_seconds)
    out_time = _seconds_to_ticks(out_time_seconds)

    # Fixed fields before STN_table (34 bytes total from start of item data)
    item_data = bytearray()
    item_data += clip_id_bytes                        # 0-4: clip_id (5 bytes)
    item_data += codec_id                             # 5-8: codec_id (4 bytes)
    item_data += b"\x00\x00"                          # 9-10: reserved/connection
    item_data += b"\x00"                              # 11: ref_to_STC_id
    item_data += b"\x00\x00"                          # 12-13: padding to align IN_time at +14
    item_data += struct.pack(">I", in_time)           # 14-17: IN_time
    item_data += struct.pack(">I", out_time)          # 18-21: OUT_time
    item_data += b"\x00" * 8                          # 22-29: UO_mask_table
    item_data += b"\x00"                              # 30: random_access_flag
    item_data += b"\x00"                              # 31: still_mode
    item_data += b"\x00\x00"                          # 32-33: still_time

    # STN_table at offset 34
    stn = _build_stn_table(audio_streams, subtitle_streams)
    item_data += stn

    # PlayItem: 2-byte length + data
    item_length = len(item_data)
    return struct.pack(">H", item_length) + bytes(item_data)


def _build_mark_entry(
    mark_type: int = 1,
    play_item_ref: int = 0,
    timestamp_seconds: float = 0.0,
    duration_ticks: int = 0,
) -> bytes:
    """Build a single 14-byte mark entry."""
    timestamp = _seconds_to_ticks(timestamp_seconds)
    entry = bytearray(14)
    entry[0] = 0           # reserved
    entry[1] = mark_type
    struct.pack_into(">H", entry, 2, play_item_ref)
    struct.pack_into(">I", entry, 4, timestamp)
    struct.pack_into(">H", entry, 8, 0)  # entry_ES_PID
    struct.pack_into(">I", entry, 10, duration_ticks)
    return bytes(entry)


def make_mpls_file(
    version: str = "0200",
    play_items: list[dict] | None = None,
    chapter_marks: list[dict] | None = None,
) -> bytes:
    """Build a minimal-but-valid MPLS binary blob.

    Args:
        version: "0200" for standard BD, "0300" for UHD.
        play_items: List of dicts with keys:
            - clip_id (str): 5-char clip name, default "00001"
            - in_time (float): start time in seconds, default 0.0
            - out_time (float): end time in seconds, default 0.0
            - audio_streams (list): [(coding_type, lang, channels), ...]
            - subtitle_streams (list): [(coding_type, lang), ...]
        chapter_marks: List of dicts with keys:
            - mark_type (int): 1=chapter, 2=link, default 1
            - play_item_ref (int): PlayItem index, default 0
            - timestamp (float): time in seconds, default 0.0

    Returns:
        bytes: Complete MPLS file contents.
    """
    if play_items is None:
        play_items = []
    if chapter_marks is None:
        chapter_marks = []

    # ---- Build PlayList section ----
    play_item_data = b""
    for pi in play_items:
        play_item_data += _build_play_item(
            clip_id=pi.get("clip_id", "00001"),
            in_time_seconds=pi.get("in_time", 0.0),
            out_time_seconds=pi.get("out_time", 0.0),
            audio_streams=pi.get("audio_streams"),
            subtitle_streams=pi.get("subtitle_streams"),
        )

    # PlayList section: length(4) + reserved(2) + n_items(2) + n_subpaths(2) + items
    playlist_body = (
        b"\x00\x00"                                   # reserved
        + struct.pack(">H", len(play_items))           # PlayItem count
        + struct.pack(">H", 0)                         # SubPath count
        + play_item_data
    )
    playlist_length = len(playlist_body)
    playlist_section = struct.pack(">I", playlist_length) + playlist_body

    # ---- Build PlayListMark section ----
    mark_entries = b""
    for cm in chapter_marks:
        mark_entries += _build_mark_entry(
            mark_type=cm.get("mark_type", 1),
            play_item_ref=cm.get("play_item_ref", 0),
            timestamp_seconds=cm.get("timestamp", 0.0),
        )

    mark_body = struct.pack(">H", len(chapter_marks)) + mark_entries
    mark_length = len(mark_body)
    mark_section = struct.pack(">I", mark_length) + mark_body

    # ---- Assemble the full MPLS file ----
    # Header is 40 bytes
    # PlayList section starts right after the header
    header_size = 40
    playlist_offset = header_size
    mark_offset = playlist_offset + len(playlist_section)

    header = bytearray(header_size)
    header[0:4] = b"MPLS"
    header[4:8] = version.encode("ascii")[:4]
    struct.pack_into(">I", header, 8, playlist_offset)
    struct.pack_into(">I", header, 12, mark_offset)

    return bytes(header) + playlist_section + mark_section
