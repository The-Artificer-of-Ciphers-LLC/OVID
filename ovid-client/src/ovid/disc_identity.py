"""DVD and Blu-ray/UHD Disc Identity selection and fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import TYPE_CHECKING, Callable

from ovid.bd_fingerprint import (
    build_bd_canonical_string,
    build_bd_canonical_string_from_survivors,
    compute_aacs_fingerprint,
    compute_bd_structure_fingerprint,
)
from ovid.dvdread_adapter import LibdvdreadError, read_libdvdread_disc_id
from ovid.fingerprint import compute_fingerprint
from ovid.mpls_parser import MplsPlaylist

if TYPE_CHECKING:
    from ovid.readers.bd_folder import BDFolderReader

OVID_DVD1_METHOD = "ovid-dvd-1"
OVID_DVD1_VERSION = "dvd1"
LIBDVDREAD_METHOD = "libdvdread-disc-id"
LIBDVDREAD_VERSION = "dvdread1"
OVID_BD2_METHOD = "ovid-bd-2"
AACS_METHOD = "aacs-disc-id"


@dataclass(frozen=True)
class DiscIdentity:
    """A single Disc Identity string and the method that produced it."""

    fingerprint: str
    method: str
    fingerprint_version: str


@dataclass(frozen=True)
class DiscIdentityDiagnostic:
    """Diagnostic detail about Disc Identity selection."""

    code: str
    message: str | None = None


@dataclass(frozen=True)
class DiscIdentitySet:
    """Primary Disc Identity plus any known Lookup Aliases."""

    primary: DiscIdentity
    aliases: list[DiscIdentity] = field(default_factory=list)
    diagnostics: list[DiscIdentityDiagnostic] = field(default_factory=list)


def ovid_dvd1_identity(canonical: str) -> DiscIdentity:
    """Build the current OVID-DVD-1 structural identity."""
    return DiscIdentity(
        fingerprint=compute_fingerprint(canonical),
        method=OVID_DVD1_METHOD,
        fingerprint_version=OVID_DVD1_VERSION,
    )


def libdvdread_identity(disc_id_hex: str) -> DiscIdentity:
    """Build a libdvdread Disc ID identity from 16 bytes encoded as hex."""
    normalised = disc_id_hex.lower()
    if re.fullmatch(r"[0-9a-f]{32}", normalised) is None:
        raise ValueError("libdvdread Disc ID must be 32 hex characters")
    return DiscIdentity(
        fingerprint=f"{LIBDVDREAD_VERSION}-{normalised}",
        method=LIBDVDREAD_METHOD,
        fingerprint_version=LIBDVDREAD_VERSION,
    )


def identify_dvd(
    path: str,
    canonical: str,
    *,
    read_libdvdread_disc_id: Callable[[str], str] = read_libdvdread_disc_id,
) -> DiscIdentitySet:
    """Identify a DVD, preferring the libdvdread Disc ID (dvdread1-*) as primary.

    Mirrors ``identify_bd()``'s Tier-2-primary/Tier-1-alias pattern (D-03,
    RESEARCH.md Open Question #1): OVID-DVD-1 (``dvd1-*``) is always computed
    first, exactly as before. Whenever ``read_libdvdread_disc_id`` succeeds,
    the resulting ``dvdread1-*`` identity becomes primary and the ``dvd1-*``
    identity is demoted to the sole alias — this is the flip. When libdvdread
    is unavailable (``LibdvdreadError``) or returns an invalid Disc ID
    (``ValueError``), ``dvd1-*`` remains primary with zero aliases, unchanged
    from today — a disc computed with no ``dvdread1-*`` string stays
    permanently ``dvd1-*``-primary client-side.
    """
    dvd1_identity = ovid_dvd1_identity(canonical)

    try:
        disc_id_hex = read_libdvdread_disc_id(path)
        dvdread1_identity = libdvdread_identity(disc_id_hex)
    except ValueError as exc:
        return DiscIdentitySet(
            primary=dvd1_identity,
            aliases=[],
            diagnostics=[
                DiscIdentityDiagnostic(
                    code="libdvdread_invalid_disc_id",
                    message=str(exc),
                )
            ],
        )
    except LibdvdreadError as exc:
        return DiscIdentitySet(
            primary=dvd1_identity,
            aliases=[],
            diagnostics=[DiscIdentityDiagnostic(code=exc.code, message=str(exc))],
        )

    return DiscIdentitySet(
        primary=dvdread1_identity,
        aliases=[dvd1_identity],
        diagnostics=[DiscIdentityDiagnostic(code="libdvdread_disc_id_available")],
    )


def ovid_bd2_identity(canonical: str, is_uhd: bool) -> DiscIdentity:
    """Build the current OVID-BD-2 (or UHD-2) structural identity."""
    version = "uhd2" if is_uhd else "bd2"
    return DiscIdentity(
        fingerprint=compute_bd_structure_fingerprint(canonical, is_uhd),
        method=OVID_BD2_METHOD,
        fingerprint_version=version,
    )


def aacs_identity(unit_key_data: bytes, is_uhd: bool) -> DiscIdentity:
    """Build an AACS Disc ID identity from raw Unit_Key_RO.inf bytes.

    ``unit_key_data`` is the plaintext AACS Disc ID material only — a
    one-way SHA-1 digest input, never a decryption key. See
    ``compute_aacs_fingerprint`` for the legal/technical distinction.
    """
    version = "uhd1-aacs" if is_uhd else "bd1-aacs"
    return DiscIdentity(
        fingerprint=compute_aacs_fingerprint(unit_key_data, is_uhd),
        method=AACS_METHOD,
        fingerprint_version=version,
    )


def identify_bd(
    playlists: list[tuple[str, MplsPlaylist]],
    is_uhd: bool,
    *,
    reader: "BDFolderReader",
    survivors: list[tuple[str, MplsPlaylist, float]] | None = None,
) -> DiscIdentitySet:
    """Identify a Blu-ray/UHD disc, keeping Tier-2 (BDMV structure) primary.

    Mirrors ``identify_dvd()``'s always-primary/opportunistic-alias/
    one-diagnostic-per-branch discipline (FPRINT-03): Tier 1 (AACS) is
    attempted first and independently, recording exactly one diagnostic per
    branch (no AACS directory, missing/empty key file, read error, hash
    failure, or success). Tier 2 (BDMV structure) is then attempted;
    whenever it is computable it becomes primary with any Tier-1 identity
    attached as an alias — `identify_bd()` never short-circuits to a
    Tier-1-only result just because Tier 1 succeeded.

    The one exception is the fully-degenerate case where Tier 2 itself
    cannot be computed (zero playlists survive the anti-obfuscation
    filter): if Tier 1 is available it becomes primary as a documented,
    diagnosed fallback (preserving the disc's only computable identity);
    if neither tier is available, the underlying ``ValueError`` from Tier 2
    propagates (with the diagnostics collected so far appended) rather than
    returning a hollow identity.

    Args:
        playlists: List of (filename, MplsPlaylist) tuples.
        is_uhd: True if disc is UHD (4K), False for standard Blu-ray.
        reader: The BD folder reader, used for AACS access.
        survivors: Optional pre-computed output of
            ``select_canonical_playlists(playlists)``. Callers that have
            already run the filter/dedup/sort pipeline (e.g. ``BDDisc._build()``,
            which also needs the survivor set for ``.playlists``) should pass
            it here so the pipeline is not re-run a second time (WR-03). When
            omitted, the canonical string is computed from ``playlists``
            directly, exactly as before.
    """
    diagnostics: list[DiscIdentityDiagnostic] = []
    tier1_identity: DiscIdentity | None = None

    if not reader.has_aacs():
        diagnostics.append(DiscIdentityDiagnostic(code="no_aacs_directory"))
    else:
        try:
            unit_key_data = reader.read_aacs_file("Unit_Key_RO.inf")
        except OSError as exc:
            # Present but unreadable (permission denied, I/O error, etc.) —
            # distinct from "missing" (WR-02) so operators can act on the
            # actual cause instead of assuming the key file doesn't exist.
            diagnostics.append(
                DiscIdentityDiagnostic(
                    code="aacs_unit_key_read_error", message=str(exc)
                )
            )
        else:
            try:
                if unit_key_data is None or len(unit_key_data) == 0:
                    diagnostics.append(
                        DiscIdentityDiagnostic(code="aacs_unit_key_missing")
                    )
                else:
                    tier1_identity = aacs_identity(unit_key_data, is_uhd)
                    diagnostics.append(
                        DiscIdentityDiagnostic(code="aacs_disc_id_available")
                    )
            except TypeError as exc:
                # WR-01: narrowed from a bare `except Exception` — the only
                # expected failure here is a non-bytes reader result (e.g. a
                # test double or future reader bug returning something other
                # than bytes/None), which makes `len()`/`hashlib.sha1()`
                # raise TypeError. A broader catch would silently swallow
                # genuine programming errors (AttributeError, MemoryError,
                # etc.) as a benign diagnostic instead of surfacing them.
                diagnostics.append(
                    DiscIdentityDiagnostic(
                        code="aacs_fingerprint_failed", message=str(exc)
                    )
                )

    try:
        if survivors is not None:
            canonical = build_bd_canonical_string_from_survivors(survivors, is_uhd)
        else:
            canonical = build_bd_canonical_string(playlists, is_uhd)
    except ValueError as exc:
        if tier1_identity is not None:
            diagnostics.append(
                DiscIdentityDiagnostic(
                    code="tier2_unavailable_using_tier1_primary"
                )
            )
            return DiscIdentitySet(
                primary=tier1_identity,
                aliases=[],
                diagnostics=diagnostics,
            )
        # IN-03: preserve the diagnostics already collected (e.g.
        # "no_aacs_directory") instead of discarding them on a bare re-raise
        # — they explain *why* neither tier was available.
        diag_codes = [d.code for d in diagnostics]
        raise ValueError(f"{exc} (diagnostics: {diag_codes})") from exc

    primary = ovid_bd2_identity(canonical, is_uhd)
    aliases: list[DiscIdentity] = (
        [tier1_identity] if tier1_identity is not None else []
    )

    return DiscIdentitySet(
        primary=primary,
        aliases=aliases,
        diagnostics=diagnostics,
    )
