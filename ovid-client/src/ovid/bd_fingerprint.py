"""Blu-ray disc fingerprint algorithms: AACS Tier 1 and BDMV Tier 2 structure hash.

Tier 1 (AACS):
  SHA-1 of the raw Unit_Key_RO.inf bytes → prefix ``bd1-aacs-`` or ``uhd1-aacs-``.
  This is the most stable identifier since AACS keys are per-disc-pressing.
  This value is what the FOSS Blu-ray tooling ecosystem (libaacs, MakeMKV
  keydb.cfg) calls the "AACS Disc ID": a one-way SHA-1 digest of a plaintext
  UDF file, not a decryption key. Computing it involves no descrambling and
  no AACS device keys.

Tier 2 (BDMV structure):
  Canonical string encoding playlist structure, selected via the frozen
  OVID-BD-2 ruleset in ``bd2_spec.py`` (minimum-duration filter, max-clip-repeat
  decoy filter, clip-sequence dedup, clip-sequence tie-break) → SHA-256 first
  40 hex chars → prefix ``bd2-`` or ``uhd2-``.

The frozen ``bd2_spec`` filter/dedup/tie-break pipeline removes short
menu/preview playlists and studio anti-rip obfuscation (loop-padded or
renumbered/duplicated decoy playlists) that would otherwise fragment the
fingerprint space between identical disc pressings (FPRINT-06).
"""

from __future__ import annotations

import collections
import hashlib
import logging

from ovid.bd2_spec import MAX_CLIP_REPEATS, MIN_DURATION_SECONDS, OVID_BD2_VERSION
from ovid.mpls_parser import MplsPlaylist

logger = logging.getLogger(__name__)


def _total_duration(playlist: MplsPlaylist) -> float:
    """Sum of all play item durations in a playlist."""
    return sum(pi.duration_seconds for pi in playlist.play_items)


def _clip_sequence(playlist: MplsPlaylist) -> tuple:
    """Return the content-based clip sequence for a playlist.

    A tuple of ``(clip_id, in_time, out_time)`` per play item, used for
    dedup and tie-break decisions instead of the (studio-controlled,
    renumberable) `.mpls` filename.
    """
    return tuple((pi.clip_id, pi.in_time, pi.out_time) for pi in playlist.play_items)


def _clip_repeat_count(playlist: MplsPlaylist) -> int:
    """Return the max number of times any single clip_id repeats in a playlist.

    A high repeat count indicates a loop-padded decoy playlist (the same
    clip referenced many times to inflate apparent duration).
    """
    if not playlist.play_items:
        return 0
    counts = collections.Counter(pi.clip_id for pi in playlist.play_items)
    return max(counts.values())


def select_canonical_playlists(
    playlists: list[tuple[str, MplsPlaylist]],
) -> list[tuple[str, MplsPlaylist, float]]:
    """Filter, dedup, and sort playlists per the frozen OVID-BD-2 ruleset.

    Pipeline (FPRINT-06, D-06/D-07/D-08 — see ``bd2_spec.py``):
      1. Filter to playlists with total duration >= ``MIN_DURATION_SECONDS``
         AND clip-repeat count <= ``MAX_CLIP_REPEATS`` (excludes menus and
         loop-padded decoy playlists).
      2. Dedup survivors by content-based clip sequence (first occurrence
         wins) — collapses byte-identical duplicate/renumbered decoys.
      3. Sort by ``(-duration, clip_sequence)`` — never by filename.

    Args:
        playlists: List of (filename, MplsPlaylist) tuples.

    Returns:
        List of (filename, MplsPlaylist, duration) tuples, filtered,
        deduped, and sorted.

    Raises:
        ValueError: If no playlists survive the filter step.
    """
    filtered: list[tuple[str, MplsPlaylist, float]] = []
    for fname, pl in playlists:
        dur = _total_duration(pl)
        if dur >= MIN_DURATION_SECONDS and _clip_repeat_count(pl) <= MAX_CLIP_REPEATS:
            filtered.append((fname, pl, dur))

    if not filtered:
        raise ValueError(
            f"No valid playlists after 60-second filter "
            f"(had {len(playlists)} playlist(s), all under {MIN_DURATION_SECONDS}s)"
        )

    # Dedup by content-based clip sequence — first occurrence wins.
    deduped: dict[tuple, tuple[str, MplsPlaylist, float]] = {}
    for fname, pl, dur in filtered:
        key = _clip_sequence(pl)
        if key not in deduped:
            deduped[key] = (fname, pl, dur)

    survivors = list(deduped.values())

    logger.info(
        "BD structure hash: %d/%d playlists survive filter+dedup",
        len(survivors),
        len(playlists),
    )

    # Deterministic sort: by total duration descending, then clip sequence
    # ascending (content-based tie-break — never filename).
    survivors.sort(key=lambda x: (-x[2], _clip_sequence(x[1])))

    return survivors


def compute_aacs_fingerprint(unit_key_data: bytes, is_uhd: bool) -> str:
    """Compute AACS Tier 1 fingerprint from Unit_Key_RO.inf bytes.

    This is the AACS Disc ID as used by the FOSS Blu-ray tooling ecosystem
    (libaacs, MakeMKV keydb.cfg): a one-way SHA-1 digest of the plaintext
    Unit_Key_RO.inf bytes. It is a stable identifier only — never a
    decryption key, and computing it involves no descrambling or AACS
    device keys.

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

    Playlists are selected via the frozen OVID-BD-2 ruleset
    (``select_canonical_playlists()``, see ``bd2_spec.py``): filtered by
    minimum duration and max-clip-repeat decoy exclusion, deduped by
    content-based clip sequence, then sorted by total duration descending,
    then by clip-sequence ascending (never filename) for deterministic
    ordering.

    ``is_uhd`` is intentionally unused in the body below: the canonical
    structure is format-agnostic (Tier 1 and Tier 2 are computed identically
    regardless of BD vs UHD — see "Format Detection (UHD)" in
    ``docs/fingerprint-spec.md``). Only the ``uhd2-``/``bd2-`` prefix, applied
    downstream in ``compute_bd_structure_fingerprint()``, differs. Do not
    "clean up" this parameter by mixing it into the canonical string — that
    would silently mint a new fingerprint space without an ``OVID_BD2_VERSION``
    bump.

    Format (pipe-delimited)::

        OVID-BD-2|{playlist_count}|{pl1_block}|{pl2_block}|...

    Each playlist block::

        {play_item_count}:{total_duration}:{chapter_count}:{audio_count}:{audio_info}:{subtitle_count}:{subtitle_info}

    Where:
      - ``play_item_count`` is the number of PlayItems
      - ``total_duration`` is total seconds as int
      - ``chapter_count`` is the number of chapter marks (mark_type == 1)
      - ``audio_count`` is the number of audio streams (``len(pl.audio_streams)``)
      - ``audio_info`` is comma-joined ``codec+lang+channels`` for each audio stream
      - ``subtitle_count`` is the number of subtitle streams (``len(pl.subtitle_streams)``)
      - ``subtitle_info`` is comma-joined language codes for each subtitle stream

    The explicit ``audio_count``/``subtitle_count`` fields (CR-01) disambiguate
    "zero streams" from "one stream whose joined value happens to be empty"
    (e.g. an unparsed/null-language subtitle track) — both previously
    collapsed to the same empty ``subtitle_info`` field, causing a real
    fingerprint collision between structurally different discs.

    Args:
        playlists: List of (filename, MplsPlaylist) tuples.
        is_uhd: True if disc is UHD (4K), False for standard Blu-ray.

    Returns:
        The canonical string.

    Raises:
        ValueError: If no playlists survive the filter (see
            ``select_canonical_playlists``).
    """
    # is_uhd is intentionally unused here — see the docstring note above.
    filtered = select_canonical_playlists(playlists)
    return build_bd_canonical_string_from_survivors(filtered, is_uhd)


def build_bd_canonical_string_from_survivors(
    survivors: list[tuple[str, MplsPlaylist, float]],
    is_uhd: bool,
) -> str:
    """Build the OVID-BD-2 canonical string from an already-selected survivor list.

    This is the shared implementation behind :func:`build_bd_canonical_string`,
    split out so callers that have already run ``select_canonical_playlists()``
    (e.g. to populate ``BDDisc.playlists``) can reuse that single result
    instead of re-running the filter/dedup/sort pipeline a second time.

    ``survivors`` must already be filtered, deduped, and sorted — this
    function does not run ``select_canonical_playlists()`` itself and does
    not raise ``ValueError`` for an empty input (an empty ``survivors`` list
    simply yields ``playlist_count == 0``). See :func:`build_bd_canonical_string`
    for the full field format.

    ``is_uhd`` is intentionally unused here — see the note on
    :func:`build_bd_canonical_string`.

    Args:
        survivors: The output of ``select_canonical_playlists()`` — a list of
            (filename, MplsPlaylist, duration) tuples.
        is_uhd: True if disc is UHD (4K), False for standard Blu-ray.

    Returns:
        The canonical string.
    """
    # is_uhd is intentionally unused here — see the docstring note above.
    parts: list[str] = [OVID_BD2_VERSION, str(len(survivors))]

    for fname, pl, dur in survivors:
        play_item_count = len(pl.play_items)
        total_duration = int(dur)
        chapter_count = sum(1 for m in pl.chapter_marks if m.mark_type == 1)

        # Audio info: codec+language+channels per stream
        audio_parts: list[str] = []
        for s in pl.audio_streams:
            audio_parts.append(f"{s.codec}+{s.language}+{s.channels}")
        audio_count = len(pl.audio_streams)
        audio_info = ",".join(audio_parts)

        # Subtitle info: language codes
        sub_parts: list[str] = [s.language for s in pl.subtitle_streams]
        subtitle_count = len(pl.subtitle_streams)
        subtitle_info = ",".join(sub_parts)

        block = (
            f"{play_item_count}:{total_duration}:{chapter_count}:"
            f"{audio_count}:{audio_info}:{subtitle_count}:{subtitle_info}"
        )
        parts.append(block)

    return "|".join(parts)


def compute_bd_structure_fingerprint(canonical: str, is_uhd: bool) -> str:
    """SHA-256 hash a BD canonical string → ``bd2-{first 40 hex chars}`` or ``uhd2-...``.

    The canonical string is encoded as UTF-8 before hashing.
    """
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    prefix = "uhd2-" if is_uhd else "bd2-"
    return f"{prefix}{digest[:40]}"
