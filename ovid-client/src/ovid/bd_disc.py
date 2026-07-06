"""High-level BDDisc class — the public API for fingerprinting a Blu-ray source.

Usage::

    disc = BDDisc.from_path("/path/to/bluray")
    print(disc.fingerprint)      # bd2-def456... (or, degenerate case, bd1-aacs-abc123...)
    print(disc.tier)             # 2 (structure hash) or, degenerate case, 1 (AACS)
    print(disc.format_type)      # 'bluray' or 'uhd'
    print(disc.identity)         # full DiscIdentitySet: primary + aliases + diagnostics
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ovid.bd_fingerprint import build_bd_canonical_string, select_canonical_playlists
from ovid.disc_identity import DiscIdentitySet, identify_bd
from ovid.mpls_parser import MplsPlaylist, parse_mpls
from ovid.readers.bd_folder import BDFolderReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BDDisc:
    """A parsed Blu-ray disc with its OVID fingerprint.

    Create via :meth:`from_path` — do not instantiate directly.

    Tier 2 (BDMV structure) is always computed and used as primary whenever
    at least one playlist survives the anti-obfuscation filter, regardless
    of AACS availability. Tier 1 (AACS) is attached as an alias whenever
    readable — see ``.identity`` for the full ``DiscIdentitySet`` (primary +
    aliases + diagnostics). Tier 1 becomes primary only in the fully-
    degenerate case where Tier 2 cannot be computed at all (zero playlists
    survive the filter).

    Attributes:
        fingerprint: The OVID fingerprint string — thin proxy for
            ``identity.primary.fingerprint`` (bd2-*, uhd2-*, or, in the
            degenerate case, bd1-aacs-*/uhd1-aacs-*).
        tier: Thin proxy derived from ``identity.primary.fingerprint_version``
            — 2 for structure hash, 1 for the degenerate AACS-only case.
        format_type: ``'bluray'`` or ``'uhd'``.
        canonical_string: The canonical string (populated for Tier 2, empty for
            the degenerate Tier-1-primary case).
        source_type: Name of the reader class used.
        playlists: List of parsed MplsPlaylist objects that survived the same
            anti-obfuscation filter used for the Tier-2 hash (empty in the
            degenerate Tier-1-primary case).
    """

    fingerprint: str
    tier: int
    format_type: str
    canonical_string: str
    source_type: str
    playlists: list[MplsPlaylist] = field(repr=False)
    _identity_set: DiscIdentitySet = field(repr=False)

    @property
    def identity(self) -> DiscIdentitySet:
        """The full Disc Identity Set: primary, aliases, and diagnostics."""
        return self._identity_set

    @classmethod
    def from_path(cls, path: str) -> "BDDisc":
        """Auto-detect BD source, parse MPLS files, and compute fingerprint.

        Delegates identity resolution to :func:`ovid.disc_identity.identify_bd`
        — Tier 2 (BDMV structure) is always primary when computable, Tier 1
        (AACS) is attached as an alias when available.

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

        # Detect UHD from any playlist's version header (check before filtering
        # so discs with only short playlists can still be classified)
        is_uhd = any(
            pl.header.version == "0300" for _, pl in parsed_playlists
        )
        format_type = "uhd" if is_uhd else "bluray"
        logger.info("Detected format: %s", format_type)

        # Independently derive the canonical string (used to populate
        # canonical_string on the returned BDDisc). This deterministically
        # re-derives the same success/failure outcome identify_bd() computes
        # internally for Tier 2 — a ValueError here means identify_bd() will
        # also find Tier 2 unavailable and, if AACS was readable, fall back
        # to a degenerate Tier-1-primary result.
        try:
            canonical = build_bd_canonical_string(parsed_playlists, is_uhd)
        except ValueError:
            canonical = ""

        identity_set = identify_bd(parsed_playlists, is_uhd, reader=reader)
        fp = identity_set.primary.fingerprint
        tier_num = 2 if identity_set.primary.fingerprint_version in ("bd2", "uhd2") else 1

        if tier_num == 2:
            survivors = select_canonical_playlists(parsed_playlists)
            playlists_field = [pl for _, pl, _ in survivors]
        else:
            # Degenerate Tier-1-primary case: Tier 2 was not computable, so
            # there is no survivor set — playlists is empty (matches the
            # pre-existing degenerate-case regression guarantee).
            playlists_field = []

        return cls(
            fingerprint=fp,
            tier=tier_num,
            format_type=format_type,
            canonical_string=canonical,
            source_type=source_type,
            playlists=playlists_field,
            _identity_set=identity_set,
        )
