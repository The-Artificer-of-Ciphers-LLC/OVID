"""Blu-ray disc fingerprint algorithms: AACS Tier 1 and BDMV Tier 2 structure hash.

Tier 1 (AACS):
  SHA-1 of the raw Unit_Key_RO.inf bytes → prefix ``bd1-aacs-`` or ``uhd1-aacs-``.
  This is the most stable identifier since AACS keys are per-disc-pressing.

Tier 2 (BDMV structure):
  Canonical string encoding playlist structure (filtered by 60-second minimum
  duration to exclude menu/preview playlists) → SHA-256 first 40 hex chars →
  prefix ``bd2-`` or ``uhd2-``.

The 60-second obfuscation filter removes short playlists that often differ
between disc pressings without being part of the main content.
"""

from __future__ import annotations

import hashlib
import logging

from ovid.mpls_parser import MplsPlaylist

logger = logging.getLogger(__name__)

# Minimum playlist duration in seconds to include in the structure hash.
# Playlists shorter than this are typically menus or anti-rip obfuscation.
_MIN_DURATION_SECONDS = 60.0


def _total_duration(playlist: MplsPlaylist) -> float:
    """Sum of all play item durations in a playlist."""
    return sum(pi.duration_seconds for pi in playlist.play_items)


def compute_aacs_fingerprint(unit_key_data: bytes, is_uhd: bool) -> str:
    """Compute AACS Tier 1 fingerprint from Unit_Key_RO.inf bytes.

    Returns:
        ``bd1-aacs-{sha1_hex}`` or ``uhd1-aacs-{sha1_hex}`` (40 hex chars after prefix).
    """
    sha1 = hashlib.sha1(unit_key_data).hexdigest()
    prefix = "uhd1-aacs-" if is_uhd else "bd1-aacs-"
    return f"{prefix}{sha1}"


def build_bd_canonical_string(
    playlists: list[tuple[str, MplsPlaylist]],
    is_uhd: bool,
) -> str:
    """Build the OVID-BD-2 canonical string from parsed MPLS playlists.

    Playlists with total duration < 60 seconds are filtered out.
    Remaining playlists are sorted by total duration descending, then by
    filename ascending for deterministic ordering.

    Format (pipe-delimited)::

        OVID-BD-2|{playlist_count}|{pl1_block}|{pl2_block}|...

    Each playlist block::

        {play_item_count}:{total_duration}:{chapter_count}:{audio_info}:{subtitle_info}

    Where:
      - ``play_item_count`` is the number of PlayItems
      - ``total_duration`` is total seconds as int
      - ``chapter_count`` is the number of chapter marks (mark_type == 1)
      - ``audio_info`` is comma-joined ``codec+lang+channels`` for each audio stream
      - ``subtitle_info`` is comma-joined language codes for each subtitle stream

    Args:
        playlists: List of (filename, MplsPlaylist) tuples.
        is_uhd: True if disc is UHD (4K), False for standard Blu-ray.

    Returns:
        The canonical string.

    Raises:
        ValueError: If no playlists survive the 60-second filter.
    """
    # Filter by minimum duration
    filtered: list[tuple[str, MplsPlaylist, float]] = []
    for fname, pl in playlists:
        dur = _total_duration(pl)
        if dur >= _MIN_DURATION_SECONDS:
            filtered.append((fname, pl, dur))

    if not filtered:
        raise ValueError(
            f"No valid playlists after 60-second filter "
            f"(had {len(playlists)} playlist(s), all under {_MIN_DURATION_SECONDS}s)"
        )

    logger.info(
        "BD structure hash: %d/%d playlists survive 60s filter",
        len(filtered),
        len(playlists),
    )

    # Deterministic sort: by total duration descending, then filename ascending
    filtered.sort(key=lambda x: (-x[2], x[0]))

    parts: list[str] = ["OVID-BD-2", str(len(filtered))]

    for fname, pl, dur in filtered:
        play_item_count = len(pl.play_items)
        total_duration = int(dur)
        chapter_count = sum(1 for m in pl.chapter_marks if m.mark_type == 1)

        # Audio info: codec+language+channels per stream
        audio_parts: list[str] = []
        for s in pl.audio_streams:
            audio_parts.append(f"{s.codec}+{s.language}+{s.channels}")
        audio_info = ",".join(audio_parts) if audio_parts else ""

        # Subtitle info: language codes
        sub_parts: list[str] = [s.language for s in pl.subtitle_streams]
        subtitle_info = ",".join(sub_parts) if sub_parts else ""

        block = f"{play_item_count}:{total_duration}:{chapter_count}:{audio_info}:{subtitle_info}"
        parts.append(block)

    return "|".join(parts)


def compute_bd_structure_fingerprint(canonical: str, is_uhd: bool) -> str:
    """SHA-256 hash a BD canonical string → ``bd2-{first 40 hex chars}`` or ``uhd2-...``.

    The canonical string is encoded as UTF-8 before hashing.
    """
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    prefix = "uhd2-" if is_uhd else "bd2-"
    return f"{prefix}{digest[:40]}"
