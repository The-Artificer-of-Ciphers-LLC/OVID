"""OVID-DVD-1 fingerprint algorithm: canonical string builder and SHA-256 hash.

Implements spec §2.1:
  1. Build a deterministic UTF-8 canonical string from parsed VMG + VTS data.
  2. SHA-256 hash → first 40 hex chars → prefix ``dvd1-``.

The canonical string encodes disc structure (title sets, PGC durations,
chapter counts, audio/subtitle language codes) and nothing else — no
timestamps, file sizes, or filesystem metadata.
"""

from __future__ import annotations

import hashlib

from ovid.ifo_parser import VMGInfo, VTSInfo


def build_canonical_string(vmg: VMGInfo, vts_list: list[VTSInfo]) -> str:
    """Build the OVID-DVD-1 canonical string from parsed IFO structures.

    Format (pipe-delimited, no spaces)::

        OVID-DVD-1|{VTS_count}|{title_count}|{vts1_block}|{vts2_block}|...

    Each VTS block::

        {pgc_count}:{dur}:{chaps}:{audio}:{subs},{dur}:{chaps}:{audio}:{subs},...

    Where:
      - ``dur`` is total seconds (int)
      - ``chaps`` is chapter count (int)
      - ``audio`` is comma-joined language codes from VTS audio streams
      - ``subs`` is comma-joined language codes from VTS subtitle streams

    Audio and subtitle languages are VTS-level attributes repeated for each
    PGC entry in the canonical string.
    """
    parts: list[str] = [
        "OVID-DVD-1",
        str(vmg.vts_count),
        str(vmg.title_count),
    ]

    for vts in vts_list:
        audio_str = ",".join(s.language for s in vts.audio_streams)
        subs_str = ",".join(s.language for s in vts.subtitle_streams)

        pgc_entries: list[str] = []
        for pgc in vts.pgc_list:
            pgc_entries.append(
                f"{pgc.duration_seconds}:{pgc.chapter_count}:{audio_str}:{subs_str}"
            )

        pgc_count = len(vts.pgc_list)

        if pgc_entries:
            vts_block = f"{pgc_count}:{','.join(pgc_entries)}"
        else:
            # VTS with no PGCs — just the count (0)
            vts_block = str(pgc_count)

        parts.append(vts_block)

    return "|".join(parts)


def compute_fingerprint(canonical: str) -> str:
    """SHA-256 hash a canonical string → ``dvd1-{first 40 hex chars}``.

    The canonical string is encoded as UTF-8 before hashing.
    """
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"dvd1-{digest[:40]}"
