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


if __name__ == "__main__":
    main()
