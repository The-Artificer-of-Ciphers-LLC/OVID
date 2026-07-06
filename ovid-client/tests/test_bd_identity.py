"""Tests for Blu-ray/UHD Disc Identity selection and fallback (FPRINT-03).

Mirrors ``test_disc_identity.py``'s structure: unit tests for the two
identity-builder helpers, then integration tests for ``identify_bd()``
covering every AACS-availability branch plus the Tier-2-unavailable
fallback/raise cases that ``test_bd_disc.py`` already encodes as
end-to-end regressions.
"""

from __future__ import annotations

from conftest_bd import make_mpls_file
import pytest

from ovid.bd_fingerprint import compute_aacs_fingerprint, compute_bd_structure_fingerprint
from ovid.disc_identity import (
    DiscIdentitySet,
    aacs_identity,
    identify_bd,
    ovid_bd2_identity,
)
from ovid.mpls_parser import parse_mpls


class _FakeReader:
    """Minimal duck-typed AACS reader test double (not a real BDFolderReader)."""

    def __init__(self, has_aacs_result: bool, aacs_data: bytes | None = None) -> None:
        self._has_aacs_result = has_aacs_result
        self._aacs_data = aacs_data

    def has_aacs(self) -> bool:
        return self._has_aacs_result

    def read_aacs_file(self, name: str) -> bytes | None:
        return self._aacs_data


def _valid_playlists() -> list[tuple[str, object]]:
    """One playlist, single play-item, 120s duration — survives the filter."""
    data = make_mpls_file(
        play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 120.0}]
    )
    return [("00001.mpls", parse_mpls(data))]


def _all_short_playlists() -> list[tuple[str, object]]:
    """One playlist, single play-item, 10s duration — filtered out entirely."""
    data = make_mpls_file(
        play_items=[{"clip_id": "00001", "in_time": 0.0, "out_time": 10.0}]
    )
    return [("00001.mpls", parse_mpls(data))]


def test_ovid_bd2_identity_uses_existing_fingerprint_format() -> None:
    canonical = "OVID-BD-2|1|1:120:5::"

    identity = ovid_bd2_identity(canonical, is_uhd=False)

    assert identity.fingerprint == compute_bd_structure_fingerprint(canonical, False)
    assert identity.fingerprint_version == "bd2"
    assert identity.method == "ovid-bd-2"

    uhd_identity = ovid_bd2_identity(canonical, is_uhd=True)

    assert uhd_identity.fingerprint == compute_bd_structure_fingerprint(canonical, True)
    assert uhd_identity.fingerprint_version == "uhd2"
    assert uhd_identity.method == "ovid-bd-2"


def test_aacs_identity_uses_distinct_version() -> None:
    identity = aacs_identity(b"fake_unit_key_data", is_uhd=False)

    assert identity.fingerprint == compute_aacs_fingerprint(b"fake_unit_key_data", False)
    assert identity.fingerprint_version == "bd1-aacs"
    assert identity.method == "aacs-disc-id"

    uhd_identity = aacs_identity(b"fake_unit_key_data", is_uhd=True)

    assert uhd_identity.fingerprint == compute_aacs_fingerprint(b"fake_unit_key_data", True)
    assert uhd_identity.fingerprint_version == "uhd1-aacs"
    assert uhd_identity.method == "aacs-disc-id"


def test_identify_bd_keeps_bd2_primary_when_aacs_present() -> None:
    playlists = _valid_playlists()
    reader = _FakeReader(True, b"fake_unit_key_data")

    identity_set = identify_bd(playlists, False, reader=reader)

    assert isinstance(identity_set, DiscIdentitySet)
    assert identity_set.primary.fingerprint_version == "bd2"
    assert [a.fingerprint for a in identity_set.aliases] == [
        compute_aacs_fingerprint(b"fake_unit_key_data", False)
    ]
    assert "aacs_disc_id_available" in [d.code for d in identity_set.diagnostics]


def test_identify_bd_falls_back_when_aacs_unavailable() -> None:
    playlists = _valid_playlists()
    reader = _FakeReader(False)

    identity_set = identify_bd(playlists, False, reader=reader)

    assert identity_set.primary.fingerprint_version == "bd2"
    assert identity_set.aliases == []
    assert "no_aacs_directory" in [d.code for d in identity_set.diagnostics]


def test_identify_bd_rejects_invalid_or_empty_aacs_data() -> None:
    playlists = _valid_playlists()
    reader = _FakeReader(True, b"")

    identity_set = identify_bd(playlists, False, reader=reader)

    assert identity_set.primary.fingerprint_version == "bd2"
    assert identity_set.aliases == []
    assert "aacs_unit_key_missing" in [d.code for d in identity_set.diagnostics]


def test_identify_bd_records_diagnostic_when_aacs_hash_fails() -> None:
    playlists = _valid_playlists()
    # A non-bytes payload forces hashlib.sha1() (inside aacs_identity()) to
    # raise TypeError — simulates a malformed Unit_Key_RO.inf reader result.
    reader = _FakeReader(True, aacs_data=12345)  # type: ignore[arg-type]

    identity_set = identify_bd(playlists, False, reader=reader)

    assert identity_set.primary.fingerprint_version == "bd2"
    assert identity_set.aliases == []
    assert "aacs_fingerprint_failed" in [d.code for d in identity_set.diagnostics]


def test_identify_bd_falls_back_to_tier1_primary_when_tier2_unavailable() -> None:
    playlists = _all_short_playlists()
    reader = _FakeReader(True, b"valid_key_for_fallback")

    identity_set = identify_bd(playlists, False, reader=reader)

    assert identity_set.primary.fingerprint_version in ("bd1-aacs", "uhd1-aacs")
    assert identity_set.primary.fingerprint == compute_aacs_fingerprint(
        b"valid_key_for_fallback", False
    )
    assert identity_set.aliases == []
    assert "tier2_unavailable_using_tier1_primary" in [
        d.code for d in identity_set.diagnostics
    ]


def test_identify_bd_raises_when_neither_tier_available() -> None:
    playlists = _all_short_playlists()
    reader = _FakeReader(False)

    with pytest.raises(ValueError, match="No valid playlists"):
        identify_bd(playlists, False, reader=reader)
