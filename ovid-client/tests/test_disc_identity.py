"""Tests for DVD Disc Identity selection and fallback."""

from __future__ import annotations

from ovid.disc_identity import (
    DiscIdentitySet,
    identify_dvd,
    libdvdread_identity,
    ovid_dvd1_identity,
)
from ovid.dvdread_adapter import LibdvdreadUnavailable
from ovid.fingerprint import compute_fingerprint


def test_ovid_dvd1_identity_uses_existing_fingerprint_format() -> None:
    canonical = "OVID-DVD-1|1|1|1:60:1::"

    identity = ovid_dvd1_identity(canonical)

    assert identity.fingerprint == compute_fingerprint(canonical)
    assert identity.fingerprint_version == "dvd1"
    assert identity.method == "ovid-dvd-1"


def test_libdvdread_identity_uses_distinct_version() -> None:
    identity = libdvdread_identity("AABBCCDDEEFF00112233445566778899")

    assert identity.fingerprint == "dvdread1-aabbccddeeff00112233445566778899"
    assert identity.fingerprint_version == "dvdread1"
    assert identity.method == "libdvdread-disc-id"


def test_identify_dvd_keeps_ovid_dvd1_primary_in_phase_one() -> None:
    canonical = "OVID-DVD-1|1|1|1:60:1::"

    identity_set = identify_dvd(
        "/disc/path",
        canonical,
        read_libdvdread_disc_id=lambda path: "00112233445566778899aabbccddeeff",
    )

    assert isinstance(identity_set, DiscIdentitySet)
    assert identity_set.primary.fingerprint == compute_fingerprint(canonical)
    assert identity_set.primary.fingerprint_version == "dvd1"
    assert [identity.fingerprint for identity in identity_set.aliases] == [
        "dvdread1-00112233445566778899aabbccddeeff"
    ]
    assert identity_set.diagnostics[0].code == "libdvdread_disc_id_available"


def test_identify_dvd_falls_back_when_libdvdread_is_unavailable() -> None:
    canonical = "OVID-DVD-1|1|1|1:60:1::"

    def missing_libdvdread(path: str) -> str:
        raise LibdvdreadUnavailable()

    identity_set = identify_dvd(
        "/disc/path",
        canonical,
        read_libdvdread_disc_id=missing_libdvdread,
    )

    assert identity_set.primary.fingerprint == compute_fingerprint(canonical)
    assert identity_set.aliases == []
    assert identity_set.diagnostics[0].code == "libdvdread_unavailable"


def test_identify_dvd_rejects_invalid_libdvdread_disc_id() -> None:
    canonical = "OVID-DVD-1|1|1|1:60:1::"

    identity_set = identify_dvd(
        "/disc/path",
        canonical,
        read_libdvdread_disc_id=lambda path: "not-hex",
    )

    assert identity_set.primary.fingerprint == compute_fingerprint(canonical)
    assert identity_set.aliases == []
    assert identity_set.diagnostics[0].code == "libdvdread_invalid_disc_id"
