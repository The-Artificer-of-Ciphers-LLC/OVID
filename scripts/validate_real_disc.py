#!/usr/bin/env python3
"""Validate a real DVD disc — fingerprint, display structure, optionally submit to OVID API.

Usage:
    python scripts/validate_real_disc.py /path/to/VIDEO_TS
    python scripts/validate_real_disc.py /path/to/disc.iso --submit

Requires ovid-client to be installed (pip install -e ovid-client).
"""

from __future__ import annotations

import argparse
import os
import sys


def _format_duration(secs: int) -> str:
    """Format seconds as H:MM:SS or M:SS."""
    h, remainder = divmod(secs, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint a DVD disc and display its structure.",
        epilog="Set OVID_API_URL to override the default API endpoint (http://localhost:8000).",
    )
    parser.add_argument(
        "path",
        help="Path to a VIDEO_TS folder, ISO image, or block device",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit the disc to the OVID API (requires OVID_API_URL and OVID_TOKEN)",
    )
    parser.add_argument(
        "--title",
        default="Unknown Disc",
        help="Release title for --submit (default: 'Unknown Disc')",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Release year for --submit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output fingerprint and structure as JSON",
    )
    args = parser.parse_args(argv)

    # Late import so --help works without ovid installed
    try:
        from ovid.disc import Disc
    except ImportError:
        print(
            "Error: ovid-client is not installed. Run: pip install -e ovid-client",
            file=sys.stderr,
        )
        return 1

    path = os.path.expanduser(args.path)

    try:
        disc = Disc.from_path(path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error parsing disc: {exc}", file=sys.stderr)
        return 1

    if args.json:
        import json
        structure = _build_structure_dict(disc)
        print(json.dumps(structure, indent=2))
    else:
        _print_disc_info(disc)

    if args.submit:
        return _submit_disc(disc, title=args.title, year=args.year)

    return 0


def _build_structure_dict(disc) -> dict:
    """Build a JSON-serialisable dict of the disc structure."""
    vts_entries = []
    for vi, vts in enumerate(disc._vts_list, 1):
        titles = []
        for pi, pgc in enumerate(vts.pgc_list):
            titles.append({
                "pgc_index": pi,
                "duration_secs": pgc.duration_seconds,
                "duration_display": _format_duration(pgc.duration_seconds),
                "chapter_count": pgc.chapter_count,
            })
        audio = [
            {"codec": a.codec, "language": a.language, "channels": a.channels}
            for a in vts.audio_streams
        ]
        subtitles = [
            {"language": s.language} for s in vts.subtitle_streams
        ]
        vts_entries.append({
            "vts_number": vi,
            "title_count": len(vts.pgc_list),
            "titles": titles,
            "audio_streams": audio,
            "subtitle_streams": subtitles,
        })

    return {
        "fingerprint": disc.fingerprint,
        "source_type": disc.source_type,
        "canonical_string": disc.canonical_string,
        "vts_count": disc.vts_count,
        "title_count": disc.title_count,
        "vts": vts_entries,
    }


def _print_disc_info(disc) -> None:
    """Print human-readable disc structure to stdout."""
    print(f"Fingerprint:  {disc.fingerprint}")
    print(f"Source type:  {disc.source_type}")
    print(f"VTS count:    {disc.vts_count}")
    print(f"Title count:  {disc.title_count}")
    print(f"Canonical:    {disc.canonical_string}")
    print()

    for vi, vts in enumerate(disc._vts_list, 1):
        audio_desc = ", ".join(
            f"{a.codec}/{a.language or '??'}/{a.channels}ch"
            for a in vts.audio_streams
        ) or "none"
        sub_desc = ", ".join(
            s.language or "??" for s in vts.subtitle_streams
        ) or "none"

        print(f"  VTS {vi}:")
        print(f"    Audio:     {audio_desc}")
        print(f"    Subtitles: {sub_desc}")

        for pi, pgc in enumerate(vts.pgc_list):
            dur = _format_duration(pgc.duration_seconds)
            print(f"    PGC {pi}: {dur}  ({pgc.chapter_count} chapters)")
        print()


def _submit_disc(disc, *, title: str, year: int | None) -> int:
    """Submit disc to the OVID API. Returns exit code."""
    api_url = os.environ.get("OVID_API_URL")
    if not api_url:
        print(
            "Error: OVID_API_URL environment variable is required for --submit",
            file=sys.stderr,
        )
        return 1

    try:
        from ovid.client import OVIDClient
    except ImportError:
        print("Error: ovid-client not installed", file=sys.stderr)
        return 1

    # Build a minimal payload matching the API schema
    from ovid.cli import _build_submit_payload

    payload = _build_submit_payload(
        disc=disc,
        title=title,
        year=year,
        tmdb_id=None,
        imdb_id="",
        edition_name=None,
        disc_number=1,
        total_discs=1,
    )

    client = OVIDClient(base_url=api_url)
    try:
        result = client.submit(payload)
        print(f"\nSubmitted successfully.")
        print(f"  Fingerprint: {result.get('fingerprint', disc.fingerprint)}")
        print(f"  Title:       {result.get('release', {}).get('title', title)}")
        return 0
    except Exception as exc:
        print(f"Error submitting: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
