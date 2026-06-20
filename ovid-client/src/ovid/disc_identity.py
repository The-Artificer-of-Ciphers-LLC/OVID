"""DVD Disc Identity selection and fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

from ovid.dvdread_adapter import LibdvdreadError, read_libdvdread_disc_id
from ovid.fingerprint import compute_fingerprint

OVID_DVD1_METHOD = "ovid-dvd-1"
OVID_DVD1_VERSION = "dvd1"
LIBDVDREAD_METHOD = "libdvdread-disc-id"
LIBDVDREAD_VERSION = "dvdread1"


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
    """Identify a DVD while keeping OVID-DVD-1 primary during Phase 1."""
    primary = ovid_dvd1_identity(canonical)
    aliases: list[DiscIdentity] = []
    diagnostics: list[DiscIdentityDiagnostic] = []

    try:
        disc_id_hex = read_libdvdread_disc_id(path)
        aliases.append(libdvdread_identity(disc_id_hex))
        diagnostics.append(
            DiscIdentityDiagnostic(code="libdvdread_disc_id_available")
        )
    except ValueError as exc:
        diagnostics.append(
            DiscIdentityDiagnostic(
                code="libdvdread_invalid_disc_id",
                message=str(exc),
            )
        )
    except LibdvdreadError as exc:
        diagnostics.append(
            DiscIdentityDiagnostic(code=exc.code, message=str(exc))
        )

    return DiscIdentitySet(
        primary=primary,
        aliases=aliases,
        diagnostics=diagnostics,
    )
