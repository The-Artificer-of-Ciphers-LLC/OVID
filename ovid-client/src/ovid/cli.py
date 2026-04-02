"""OVID CLI — disc fingerprinting command-line interface.

Entry point: ``ovid fingerprint <path>``
"""

from __future__ import annotations

import sys

import click

from ovid.disc import Disc


@click.group()
def main() -> None:
    """OVID — Open Video Disc Identification Database client."""


@main.command()
@click.argument("path")
def fingerprint(path: str) -> None:
    """Compute and print the OVID fingerprint for a DVD source.

    PATH may be a VIDEO_TS folder, an ISO image, or a block device.
    """
    try:
        disc = Disc.from_path(path)
    except (FileNotFoundError, ValueError, OSError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(disc.fingerprint)


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
