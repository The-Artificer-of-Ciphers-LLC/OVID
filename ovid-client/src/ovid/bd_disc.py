"""High-level BDDisc class — the public API for fingerprinting a Blu-ray source.

Usage::

    disc = BDDisc.from_path("/path/to/bluray")
    print(disc.fingerprint)      # bd1-aacs-abc123... or bd2-def456...
    print(disc.tier)             # 1 (AACS) or 2 (structure hash)
    print(disc.format_type)      # 'bluray' or 'uhd'
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ovid.bd_fingerprint import (
    build_bd_canonical_string,
    compute_aacs_fingerprint,
    compute_bd_structure_fingerprint,
)
from ovid.mpls_parser import MplsPlaylist, parse_mpls
from ovid.readers.bd_folder import BDFolderReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BDDisc:
    """A parsed Blu-ray disc with its OVID fingerprint.

    Create via :meth:`from_path` — do not instantiate directly.

    Attributes:
        fingerprint: The OVID fingerprint string (bd1-aacs-*, uhd1-aacs-*, bd2-*, uhd2-*).
        tier: 1 for AACS-based fingerprint, 2 for structure hash.
        format_type: ``'bluray'`` or ``'uhd'``.
        canonical_string: The canonical string (populated for Tier 2, empty for Tier 1).
        source_type: Name of the reader class used.
        playlists: List of parsed MplsPlaylist objects.
    """

    fingerprint: str
    tier: int
    format_type: str
    canonical_string: str
    source_type: str
    playlists: list[MplsPlaylist] = field(repr=False)

    @classmethod
    def from_path(cls, path: str) -> "BDDisc":
        """Auto-detect BD source, parse MPLS files, and compute fingerprint.

        Tries AACS Tier 1 first (SHA-1 of Unit_Key_RO.inf), falls back to
        Tier 2 (BDMV structure hash).

        Args:
            path: Path to a directory containing a BDMV subdirectory.

        Returns:
            A :class:`BDDisc` instance with fingerprint and structural metadata.

        Raises:
            FileNotFoundError: If *path* does not exist or has no BDMV data.
            ValueError: If no valid MPLS playlists are found.
        """
        import os

        if not os.path.exists(path):
            raise FileNotFoundError(f"Path does not exist: {path}")

        reader = BDFolderReader(path)
        source_type = type(reader).__name__

        try:
            return cls._build(reader, source_type)
        finally:
            reader.close()

    @classmethod
    def _build(cls, reader: BDFolderReader, source_type: str) -> "BDDisc":
        """Core build logic separated from path handling for testability."""
        # Parse all MPLS files
        mpls_files = reader.list_mpls_files()
        if not mpls_files:
            raise ValueError(
                "No MPLS playlist files found in BDMV/PLAYLIST"
            )

        logger.info("Found %d MPLS file(s) in BDMV/PLAYLIST", len(mpls_files))

        parsed_playlists: list[tuple[str, MplsPlaylist]] = []
        for fname in mpls_files:
            try:
                data = reader.read_mpls(fname)
                pl = parse_mpls(data)
                parsed_playlists.append((fname, pl))
            except (ValueError, OSError) as exc:
                logger.warning("Skipping malformed MPLS %s: %s", fname, exc)
                continue

        if not parsed_playlists:
            raise ValueError(
                "All MPLS files in BDMV/PLAYLIST are malformed or unreadable"
            )

        # Detect UHD from first valid playlist's version header
        is_uhd = any(
            pl.header.version == "0300" for _, pl in parsed_playlists
        )
        format_type = "uhd" if is_uhd else "bluray"
        logger.info("Detected format: %s", format_type)

        # Try AACS Tier 1
        tier1_fp = cls._try_aacs_tier1(reader, is_uhd)
        if tier1_fp is not None:
            logger.info("Using AACS Tier 1 fingerprint")
            return cls(
                fingerprint=tier1_fp,
                tier=1,
                format_type=format_type,
                canonical_string="",
                source_type=source_type,
                playlists=[pl for _, pl in parsed_playlists],
            )

        # Fall back to Tier 2 structure hash
        logger.info("AACS Tier 1 unavailable, falling back to Tier 2 structure hash")
        canonical = build_bd_canonical_string(parsed_playlists, is_uhd)
        fp = compute_bd_structure_fingerprint(canonical, is_uhd)

        return cls(
            fingerprint=fp,
            tier=2,
            format_type=format_type,
            canonical_string=canonical,
            source_type=source_type,
            playlists=[pl for _, pl in parsed_playlists],
        )

    @staticmethod
    def _try_aacs_tier1(reader: BDFolderReader, is_uhd: bool) -> str | None:
        """Attempt AACS Tier 1 fingerprint.  Returns None on any failure."""
        if not reader.has_aacs():
            logger.info("No AACS directory found")
            return None

        unit_key_data = reader.read_aacs_file("Unit_Key_RO.inf")
        if unit_key_data is None:
            logger.warning("AACS directory exists but Unit_Key_RO.inf not found")
            return None

        if len(unit_key_data) == 0:
            logger.warning("Unit_Key_RO.inf is empty")
            return None

        try:
            return compute_aacs_fingerprint(unit_key_data, is_uhd)
        except Exception as exc:
            logger.warning("AACS Tier 1 fingerprint failed: %s", exc)
            return None
