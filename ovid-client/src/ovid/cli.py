"""OVID CLI — disc fingerprinting command-line interface.

Entry point: ``ovid fingerprint <path>``
"""

from __future__ import annotations

import json
import sys
from typing import Any, Union

import click

from ovid.disc import Disc


@click.group()
def main() -> None:
    """OVID — Open Video Disc Identification Database client."""


@main.command()
@click.argument("path")
@click.option("--json", "-j", "output_json", is_flag=True, default=False,
              help="Output structured JSON with fingerprint and disc structure.")
def fingerprint(path: str, output_json: bool) -> None:
    """Compute and print the OVID fingerprint for a disc source.

    PATH may be a VIDEO_TS folder (DVD), BDMV folder (Blu-ray/UHD),
    an ISO image, or a block device.
    """
    try:
        result = _detect_and_fingerprint(path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    if output_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(result["fingerprint"])


@main.command()
@click.argument("fingerprint")
@click.option("--api-url", default=None, help="OVID API base URL.")
@click.option("--token", default=None, help="Bearer token for API auth.")
def lookup(fingerprint: str, api_url: str | None, token: str | None) -> None:
    """Look up disc metadata by OVID fingerprint.

    Queries the OVID API and displays a Rich-formatted summary of the
    disc including release info, edition, and title/track details.
    """
    from ovid.client import OVIDClient

    client = OVIDClient(base_url=api_url, token=token)
    data = client.lookup(fingerprint)

    if data is None:
        click.echo(f"No disc found for fingerprint: {fingerprint}", err=True)
        sys.exit(1)

    _render_lookup(data)


@main.command()
@click.argument("path")
@click.option("--api-url", default=None, help="OVID API base URL.")
@click.option("--token", default=None, help="Bearer token for API auth.")
def submit(path: str, api_url: str | None, token: str | None) -> None:
    """Submit disc metadata to the OVID database via an interactive wizard.

    PATH may be a VIDEO_TS folder, an ISO image, or a block device.
    Steps: fingerprint → TMDB search → pick release → edition/disc# → submit.
    """
    from rich.console import Console
    from rich.prompt import IntPrompt, Prompt

    from ovid.client import OVIDClient
    from ovid.tmdb import get_movie, search_movies

    console = Console()
    client = OVIDClient(base_url=api_url, token=token)

    # ── Step 1: Parse disc ──────────────────────────────────────────
    try:
        disc: Union[Disc, "BDDisc"] = _open_disc(path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    from ovid.bd_disc import BDDisc as _BDDisc
    is_bd = isinstance(disc, _BDDisc)

    console.print(f"\n[bold]Disc fingerprint:[/bold] {disc.fingerprint}")
    if is_bd:
        fmt_label = "UHD" if disc.format_type == "uhd" else "Blu-ray"
        console.print(
            f"  Format: {fmt_label}  ·  "
            f"Tier: {disc.tier}  ·  "
            f"Playlists: {len(disc.playlists)}"
        )
    else:
        console.print(
            f"  VTS count: {disc.vts_count}  ·  "
            f"Title count: {disc.title_count}"
        )

    # ── Step 2: TMDB search (or manual fallback) ────────────────────
    tmdb_id: int | None = None
    imdb_id: str = ""
    title: str = ""
    year: str = ""

    results = _tmdb_search_flow(console, search_movies)

    if results is not None:
        # User picked a TMDB result
        tmdb_id = results["id"]
        title = results["title"]
        year = results["year"]

        # Fetch full details for imdb_id
        details = get_movie(tmdb_id)
        if details:
            imdb_id = details.get("imdb_id", "")
    else:
        # Manual entry fallback
        title = Prompt.ask("\nMovie title")
        year = Prompt.ask("Release year")

    # ── Step 3: Edition / disc numbering ────────────────────────────
    edition_name = Prompt.ask(
        "Edition name (blank for standard)", default=""
    )
    disc_number = IntPrompt.ask("Disc number", default=1)
    total_discs = IntPrompt.ask("Total discs", default=1)

    # ── Step 3b: Set membership (D-12) ───────────────────────────────
    disc_set_id = None
    if click.confirm("Part of a multi-disc set?", default=False):
        # Search for existing sets
        search_query = click.prompt(
            "Search for existing set (release title or edition)",
            default="",
            show_default=False,
        )
        if search_query.strip():
            results = client.search_sets(search_query)
            if results and results.get("results"):
                console.print("[bold]Matching sets:[/bold]")
                for i, s in enumerate(results["results"], 1):
                    edition = s.get("edition_name") or "No edition"
                    disc_count = len(s.get("discs", []))
                    total = s.get("total_discs", 0)
                    console.print(
                        f"  {i}. {edition} ({disc_count}/{total} discs linked)"
                    )
                choice = click.prompt(
                    "Select set number (or 0 to create new)",
                    type=int,
                    default=0,
                )
                if 1 <= choice <= len(results["results"]):
                    selected = results["results"][choice - 1]
                    disc_set_id = selected["id"]
                    console.print(
                        f"[green]Selected set: "
                        f"{selected.get('edition_name', 'Unnamed')}[/green]"
                    )
            else:
                console.print("[dim]No matching sets found.[/dim]")

        if disc_set_id is None and click.confirm("Create a new set?", default=True):
            # Derive release_id from search results when available
            _release_id: str | None = None
            if (
                search_query.strip()
                and results
                and results.get("results")
            ):
                _release_id = results["results"][0].get("release_id")
            if _release_id is None:
                console.print(
                    "[yellow]No release found — submit the disc first, "
                    "then link it to a set.[/yellow]"
                )
            else:
                new_edition = click.prompt(
                    "Edition name (optional)",
                    default="",
                    show_default=False,
                )
                new_total = click.prompt(
                    "Total discs in set", type=int, default=2
                )
                try:
                    new_set = client.create_set(
                        release_id=_release_id,
                        edition_name=new_edition.strip() or None,
                        total_discs=new_total,
                    )
                    disc_set_id = new_set["id"]
                    console.print(
                        f"[green]Created new set: "
                        f"{new_edition or 'Unnamed'} "
                        f"({new_total} discs)[/green]"
                    )
                except click.ClickException as exc:
                    console.print(
                        f"[yellow]Could not create set: "
                        f"{exc.message}[/yellow]"
                    )

    # ── Step 4: Build payload from Disc structure ───────────────────
    year_int: int | None = None
    if year:
        try:
            year_int = int(year)
        except ValueError:
            year_int = None

    payload = _build_submit_payload(
        disc=disc,
        title=title,
        year=year_int,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        edition_name=edition_name or None,
        disc_number=disc_number,
        total_discs=total_discs,
    )
    if disc_set_id:
        payload["disc_set_id"] = disc_set_id

    # ── Step 5: Submit ──────────────────────────────────────────────
    try:
        result = client.submit(payload)
        console.print(
            f"\n[green]✓[/green] Disc submitted — "
            f"status: {result.get('status', 'unknown')}"
        )
    except click.ClickException:
        raise
    except Exception as exc:
        click.echo(f"Error submitting disc: {exc}", err=True)
        sys.exit(1)


# ------------------------------------------------------------------
# Auto-detection helpers
# ------------------------------------------------------------------

def _is_bd_path(path: str) -> bool:
    """Check whether *path* contains a BDMV subdirectory (case-insensitive)."""
    import os

    if not os.path.isdir(path):
        return False
    basename = os.path.basename(os.path.normpath(path))
    if basename.upper() == "BDMV":
        return True
    try:
        for entry in os.listdir(path):
            if entry.upper() == "BDMV" and os.path.isdir(os.path.join(path, entry)):
                return True
    except OSError:
        pass
    return False


def _open_disc(path: str) -> Union[Disc, Any]:
    """Open a disc from *path*, auto-detecting BD vs DVD.

    Returns a :class:`BDDisc` or :class:`Disc` instance.
    """
    if _is_bd_path(path):
        from ovid.bd_disc import BDDisc
        return BDDisc.from_path(path)
    return Disc.from_path(path)


def _detect_and_fingerprint(path: str) -> dict:
    """Auto-detect BD vs DVD, parse, and return a structured result dict.

    Returns a dict with keys:
    - ``fingerprint``: the OVID fingerprint string
    - ``format``: ``'DVD'``, ``'Blu-ray'``, or ``'UHD'``
    - ``source_type``: reader class name
    - ``structure``: format-specific disc structure

    For Blu-ray/UHD, ``tier`` is also included (1 or 2).
    """
    if _is_bd_path(path):
        from ovid.bd_disc import BDDisc
        bd = BDDisc.from_path(path)
        fmt = "UHD" if bd.format_type == "uhd" else "Blu-ray"
        return {
            "fingerprint": bd.fingerprint,
            "format": fmt,
            "tier": bd.tier,
            "source_type": bd.source_type,
            "structure": _bd_structure(bd),
        }

    disc = Disc.from_path(path)
    return {
        "fingerprint": disc.fingerprint,
        "format": "DVD",
        "source_type": disc.source_type,
        "structure": _dvd_structure(disc),
    }


def _bd_structure(bd: Any) -> dict:
    """Build the JSON-serialisable structure dict for a Blu-ray disc."""
    playlists = []
    for pl in bd.playlists:
        play_items = []
        for pi in pl.play_items:
            play_items.append({
                "clip_id": pi.clip_id,
                "in_time": pi.in_time,
                "out_time": pi.out_time,
                "duration_seconds": pi.duration_seconds,
            })

        audio_streams = []
        for s in pl.audio_streams:
            audio_streams.append({
                "codec": s.codec,
                "language": s.language,
                "channels": s.channels,
            })

        subtitle_streams = []
        for s in pl.subtitle_streams:
            subtitle_streams.append({
                "codec": s.codec,
                "language": s.language,
            })

        chapters = []
        for ch in pl.chapter_marks:
            chapters.append({
                "mark_type": ch.mark_type,
                "play_item_ref": ch.play_item_ref,
                "timestamp": ch.timestamp,
                "duration_seconds": ch.duration_seconds,
            })

        playlists.append({
            "version": pl.header.version,
            "play_items": play_items,
            "audio_streams": audio_streams,
            "subtitle_streams": subtitle_streams,
            "chapters": chapters,
        })

    return {"playlists": playlists}


def _dvd_structure(disc: Disc) -> dict:
    """Build the JSON-serialisable structure dict for a DVD disc."""
    vts_list = []
    for vts in disc._vts_list:
        pgcs = []
        for pgc in vts.pgc_list:
            pgcs.append({
                "duration_seconds": pgc.duration_seconds,
                "chapter_count": pgc.chapter_count,
            })

        audio_streams = []
        for s in vts.audio_streams:
            audio_streams.append({
                "codec": s.codec,
                "language": s.language,
                "channels": s.channels,
            })

        subtitle_streams = []
        for s in vts.subtitle_streams:
            subtitle_streams.append({
                "language": s.language,
            })

        vts_list.append({
            "pgcs": pgcs,
            "audio_streams": audio_streams,
            "subtitle_streams": subtitle_streams,
        })

    return {
        "vts_count": disc.vts_count,
        "title_count": disc.title_count,
        "vts": vts_list,
    }


# ------------------------------------------------------------------
# Submit helpers
# ------------------------------------------------------------------

def _tmdb_search_flow(
    console: "rich.console.Console",  # noqa: F821
    search_fn,
) -> dict | None:
    """Run the TMDB search → pick loop.

    Returns the chosen ``{id, title, year, overview}`` dict, or ``None``
    if the user should fall back to manual entry (no API key, empty results,
    or user opts out).
    """
    import os

    from rich.prompt import IntPrompt, Prompt
    from rich.table import Table

    if not os.environ.get("TMDB_API_KEY"):
        console.print(
            "\n[yellow]TMDB_API_KEY not set — entering title manually.[/yellow]"
        )
        return None

    while True:
        query = Prompt.ask("\nSearch TMDB for movie title")
        results = search_fn(query)

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            retry = Prompt.ask(
                "Try another search? (y/n)", choices=["y", "n"], default="y"
            )
            if retry == "n":
                return None
            continue

        table = Table(title="TMDB Results")
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Title", min_width=20)
        table.add_column("Year", width=6)
        table.add_column("Overview", max_width=50)

        for i, r in enumerate(results[:10], start=1):
            overview = (r.get("overview") or "")[:80]
            if len(r.get("overview", "")) > 80:
                overview += "…"
            table.add_row(
                str(i),
                r["title"],
                r.get("year", ""),
                overview,
            )

        console.print(table)
        console.print("[dim]Enter 0 to search again, or -1 for manual entry.[/dim]")

        pick = IntPrompt.ask("Pick a result", default=1)
        if pick == -1:
            return None
        if pick == 0:
            continue
        if 1 <= pick <= len(results[:10]):
            return results[pick - 1]

        console.print("[red]Invalid selection.[/red]")


def _build_submit_payload(
    *,
    disc: Union["Disc", Any],
    title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str,
    edition_name: str | None,
    disc_number: int,
    total_discs: int,
) -> dict:
    """Build the POST /v1/disc JSON payload from Disc or BDDisc structure."""
    from ovid.bd_disc import BDDisc

    if isinstance(disc, BDDisc):
        return _build_bd_submit_payload(
            bd_disc=disc,
            title=title,
            year=year,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
            edition_name=edition_name,
            disc_number=disc_number,
            total_discs=total_discs,
        )

    return _build_dvd_submit_payload(
        disc=disc,
        title=title,
        year=year,
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
        edition_name=edition_name,
        disc_number=disc_number,
        total_discs=total_discs,
    )


def _build_dvd_submit_payload(
    *,
    disc: "Disc",
    title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str,
    edition_name: str | None,
    disc_number: int,
    total_discs: int,
) -> dict:
    """Build the POST /v1/disc JSON payload from DVD Disc structure."""
    titles: list[dict] = []
    title_index = 0
    first_title = True

    for vts in disc._vts_list:
        audio_tracks = []
        for ai, stream in enumerate(vts.audio_streams):
            audio_tracks.append({
                "track_index": ai,
                "language_code": stream.language,
                "codec": stream.codec,
                "channels": stream.channels,
            })

        subtitle_tracks = []
        for si, stream in enumerate(vts.subtitle_streams):
            subtitle_tracks.append({
                "track_index": si,
                "language_code": stream.language,
            })

        for pgc in vts.pgc_list:
            titles.append({
                "title_index": title_index,
                "is_main_feature": first_title,
                "duration_secs": pgc.duration_seconds,
                "chapter_count": pgc.chapter_count,
                "audio_tracks": audio_tracks,
                "subtitle_tracks": subtitle_tracks,
            })
            title_index += 1
            first_title = False

    release: dict = {
        "title": title,
        "year": year,
        "content_type": "movie",
    }
    if tmdb_id is not None:
        release["tmdb_id"] = tmdb_id
    if imdb_id:
        release["imdb_id"] = imdb_id

    payload: dict = {
        "fingerprint": disc.fingerprint,
        "format": "DVD",
        "release": release,
        "titles": titles,
        "disc_number": disc_number,
        "total_discs": total_discs,
    }
    if edition_name:
        payload["edition_name"] = edition_name

    return payload


def _build_bd_submit_payload(
    *,
    bd_disc: Any,
    title: str,
    year: int | None,
    tmdb_id: int | None,
    imdb_id: str,
    edition_name: str | None,
    disc_number: int,
    total_discs: int,
) -> dict:
    """Build the POST /v1/disc JSON payload from BDDisc structure.

    Each playlist becomes a title entry. The first playlist with the
    longest duration is marked as the main feature.
    """
    fmt = "UHD" if bd_disc.format_type == "uhd" else "Blu-ray"

    titles: list[dict] = []
    title_index = 0

    # Find longest playlist to mark as main feature
    longest_idx = 0
    longest_dur = 0.0
    for i, pl in enumerate(bd_disc.playlists):
        dur = sum(pi.duration_seconds for pi in pl.play_items)
        if dur > longest_dur:
            longest_dur = dur
            longest_idx = i

    for i, pl in enumerate(bd_disc.playlists):
        total_duration = sum(pi.duration_seconds for pi in pl.play_items)
        chapter_count = len([m for m in pl.chapter_marks if m.mark_type == 1])

        audio_tracks = []
        for ai, stream in enumerate(pl.audio_streams):
            audio_tracks.append({
                "track_index": ai,
                "language_code": stream.language,
                "codec": stream.codec,
                "channels": stream.channels,
            })

        subtitle_tracks = []
        for si, stream in enumerate(pl.subtitle_streams):
            subtitle_tracks.append({
                "track_index": si,
                "language_code": stream.language,
            })

        titles.append({
            "title_index": title_index,
            "is_main_feature": (i == longest_idx),
            "duration_secs": total_duration,
            "chapter_count": chapter_count,
            "audio_tracks": audio_tracks,
            "subtitle_tracks": subtitle_tracks,
        })
        title_index += 1

    release: dict = {
        "title": title,
        "year": year,
        "content_type": "movie",
    }
    if tmdb_id is not None:
        release["tmdb_id"] = tmdb_id
    if imdb_id:
        release["imdb_id"] = imdb_id

    payload: dict = {
        "fingerprint": bd_disc.fingerprint,
        "format": fmt,
        "release": release,
        "titles": titles,
        "disc_number": disc_number,
        "total_discs": total_discs,
    }
    if edition_name:
        payload["edition_name"] = edition_name

    return payload


def _render_lookup(data: dict) -> None:
    """Render disc lookup response as Rich-formatted output."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    release = data.get("release") or {}
    title = release.get("title", "Unknown")
    year = release.get("year")
    edition = data.get("edition_name") or "—"
    confidence = data.get("confidence", "unknown")
    disc_num = data.get("disc_number", 1)
    total_discs = data.get("total_discs", 1)
    disc_format = data.get("format", "unknown")

    # Header section
    year_str = f" ({year})" if year else ""
    console.print(f"\n[bold]{title}{year_str}[/bold]")
    console.print(
        f"  Edition: {edition}  ·  "
        f"Disc {disc_num}/{total_discs}  ·  "
        f"Format: {disc_format}  ·  "
        f"Confidence: {confidence}"
    )
    console.print(f"  Fingerprint: {data.get('fingerprint', '?')}\n")

    # Titles table
    titles = data.get("titles", [])
    if not titles:
        console.print("[dim]No title information available.[/dim]")
        return

    table = Table(title="Titles", show_lines=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=12)
    table.add_column("Duration", justify="right")
    table.add_column("Ch.", justify="right", width=4)
    table.add_column("Audio", min_width=10)
    table.add_column("Subtitles", min_width=10)

    for t in titles:
        idx = str(t.get("title_index", "?"))
        name = t.get("display_name") or t.get("title_type") or "—"
        if t.get("is_main_feature"):
            name = f"[bold]{name}[/bold] ★"

        dur_secs = t.get("duration_secs")
        if dur_secs is not None:
            m, s = divmod(dur_secs, 60)
            h, m = divmod(m, 60)
            duration = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        else:
            duration = "—"

        chapters = str(t.get("chapter_count", "—"))

        audio_langs = [
            tr.get("language", "?")
            for tr in t.get("audio_tracks", [])
        ]
        sub_langs = [
            tr.get("language", "?")
            for tr in t.get("subtitle_tracks", [])
        ]

        table.add_row(
            idx,
            name,
            duration,
            chapters,
            ", ".join(audio_langs) or "—",
            ", ".join(sub_langs) or "—",
        )

    console.print(table)
