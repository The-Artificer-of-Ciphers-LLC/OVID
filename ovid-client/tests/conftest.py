"""Synthetic IFO binary fixture builders for deterministic testing.

These helpers construct minimal-but-valid VIDEO_TS.IFO (VMG) and VTS_XX_0.IFO
blobs with known field values, so unit tests can verify the parser against
controlled inputs without needing real disc images.
"""

from __future__ import annotations

import struct

SECTOR_SIZE = 2048


def encode_bcd_time(hours: int, minutes: int, seconds: int, fps_flag: int = 3) -> bytes:
    """Encode hours/minutes/seconds into 4-byte BCD playback time.

    fps_flag: high 2 bits of byte 3 (01=25fps, 11=29.97fps).  Default 3 = 29.97.
    Frames are set to 0.
    """
    def _to_bcd(val: int) -> int:
        return ((val // 10) << 4) | (val % 10)

    return bytes([
        _to_bcd(hours),
        _to_bcd(minutes),
        _to_bcd(seconds),
        (fps_flag << 6),  # 0 frames
    ])


def make_vmg_ifo(vts_count: int, title_entries: int) -> bytes:
    """Build a minimal VIDEO_TS.IFO (VMG) binary blob.

    Layout:
      0x0000: 12-byte identifier "DVDVIDEO-VMG"
      0x003E: VTS count (2 bytes BE)
      0x00C4: TT_SRPT sector offset (4 bytes BE) — points to sector 1
      sector 1 (offset 2048): TT_SRPT header — first 2 bytes = title count

    The blob is padded to be at least 2 sectors (4096 bytes).
    """
    buf = bytearray(SECTOR_SIZE * 2)

    # Identifier
    buf[0:12] = b"DVDVIDEO-VMG"

    # VTS count at 0x3E
    struct.pack_into(">H", buf, 0x3E, vts_count)

    # TT_SRPT sector offset at 0x00C4 — point to sector 1
    struct.pack_into(">I", buf, 0x00C4, 1)

    # TT_SRPT at sector 1 (offset 2048): title count
    tt_srpt_offset = SECTOR_SIZE
    struct.pack_into(">H", buf, tt_srpt_offset, title_entries)

    return bytes(buf)


def make_vts_ifo(
    pgcs: list[tuple[int, int, int, int]] | None = None,
    audio_streams: list[tuple[int, str, int]] | None = None,
    subtitle_streams: list[str] | None = None,
) -> bytes:
    """Build a minimal VTS_XX_0.IFO binary blob.

    Args:
        pgcs: List of (hours, minutes, seconds, chapter_count) tuples.
        audio_streams: List of (coding_mode, language_2char, channels) tuples.
            coding_mode: 0=AC3, 2=MPEG-1, 3=MPEG-2, 4=LPCM, 6=DTS.
        subtitle_streams: List of 2-character language codes.

    Layout:
      0x0000: 12-byte identifier "DVDVIDEO-VTS"
      0x00CC: VTS_PGCI sector offset (4 bytes BE) — points to sector 2
      0x0200: Audio attributes (count + descriptors)
      0x0254: Subtitle attributes (count + descriptors)
      sector 2 (offset 4096): VTS_PGCI table
    """
    if pgcs is None:
        pgcs = []
    if audio_streams is None:
        audio_streams = []
    if subtitle_streams is None:
        subtitle_streams = []

    # Need enough space: header sectors + PGCI sector.
    # PGCI at sector 2.  Each PGC block needs ~256 bytes (we'll use much less).
    pgci_sector = 2
    pgci_byte_offset = pgci_sector * SECTOR_SIZE

    # Allocate enough room
    total_size = pgci_byte_offset + SECTOR_SIZE + len(pgcs) * 256
    buf = bytearray(total_size)

    # Identifier
    buf[0:12] = b"DVDVIDEO-VTS"

    # VTS_PGCI sector offset at 0x00CC
    struct.pack_into(">I", buf, 0x00CC, pgci_sector)

    # --- Audio attributes at 0x0200 ---
    struct.pack_into(">H", buf, 0x0200, len(audio_streams))
    # reserved 2 bytes at 0x0202 (already zero)
    for i, (coding_mode, lang, channels) in enumerate(audio_streams):
        off = 0x0204 + i * 8
        buf[off] = (coding_mode & 0x07) << 5  # coding mode in high 3 bits
        buf[off + 1] = (channels - 1) & 0x07  # channels - 1 in low 3 bits
        if len(lang) >= 2:
            buf[off + 2] = ord(lang[0])
            buf[off + 3] = ord(lang[1])

    # --- Subtitle attributes at 0x0254 ---
    struct.pack_into(">H", buf, 0x0254, len(subtitle_streams))
    # reserved 2 bytes at 0x0256 (already zero)
    for i, lang in enumerate(subtitle_streams):
        off = 0x0258 + i * 6
        if len(lang) >= 2:
            buf[off + 2] = ord(lang[0])
            buf[off + 3] = ord(lang[1])

    # --- VTS_PGCI table at pgci_byte_offset ---
    # Header: 2 bytes pgc_count + 2 reserved + 4 bytes end_offset
    struct.pack_into(">H", buf, pgci_byte_offset, len(pgcs))
    # Search pointer entries start at pgci_byte_offset + 8
    # Each entry: 4 bytes category/pad + 4 bytes relative offset to PGC block

    # PGC blocks start after the search pointer table
    pgc_data_start = 8 + len(pgcs) * 8  # relative to pgci_byte_offset

    for i, (hrs, mins, secs, chapters) in enumerate(pgcs):
        # Search pointer entry
        sp_off = pgci_byte_offset + 8 + i * 8
        pgc_rel = pgc_data_start + i * 256
        struct.pack_into(">I", buf, sp_off + 4, pgc_rel)

        # PGC block
        pgc_abs = pgci_byte_offset + pgc_rel
        # Ensure buffer is big enough
        while pgc_abs + 8 > len(buf):
            buf.extend(b"\x00" * SECTOR_SIZE)

        buf[pgc_abs + 0x02] = chapters  # nr_of_programs = chapter count
        buf[pgc_abs + 0x03] = chapters  # nr_of_cells (= chapters for simple case)

        # BCD playback time at PGC+0x04
        bcd = encode_bcd_time(hrs, mins, secs)
        buf[pgc_abs + 0x04: pgc_abs + 0x08] = bcd

    return bytes(buf)
