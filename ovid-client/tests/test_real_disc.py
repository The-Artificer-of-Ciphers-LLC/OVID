"""Tests for real DVD discs — skipped unless OVID_TEST_DISC_PATH is set.

Set OVID_TEST_DISC_PATH to a VIDEO_TS folder or ISO path to run:

    OVID_TEST_DISC_PATH=/mnt/dvd/VIDEO_TS python -m pytest tests/test_real_disc.py -v
"""

from __future__ import annotations

import os
import re

import pytest

DISC_PATH = os.environ.get("OVID_TEST_DISC_PATH")

pytestmark = [
    pytest.mark.real_disc,
    pytest.mark.skipif(
        DISC_PATH is None,
        reason="OVID_TEST_DISC_PATH not set — skipping real disc tests",
    ),
]


@pytest.fixture(scope="module")
def real_disc():
    """Parse the real disc once for the entire module."""
    from ovid.disc import Disc

    assert DISC_PATH is not None  # guarded by skipif above
    return Disc.from_path(DISC_PATH)


class TestRealDiscFingerprint:
    """Verify fingerprint format and structural sanity on a real disc."""

    def test_fingerprint_has_dvd1_prefix(self, real_disc):
        assert real_disc.fingerprint.startswith("dvd1-"), (
            f"Expected dvd1- prefix, got: {real_disc.fingerprint}"
        )

    def test_fingerprint_is_hex_after_prefix(self, real_disc):
        _, hex_part = real_disc.fingerprint.split("-", 1)
        assert re.fullmatch(r"[0-9a-f]+", hex_part), (
            f"Expected hex hash after prefix, got: {hex_part}"
        )

    def test_fingerprint_length(self, real_disc):
        # dvd1- (5 chars) + 64-char SHA-256 hex = 69 chars
        assert len(real_disc.fingerprint) == 69, (
            f"Expected 69-char fingerprint, got {len(real_disc.fingerprint)}: "
            f"{real_disc.fingerprint}"
        )

    def test_fingerprint_deterministic(self, real_disc):
        """Parse the same disc again — fingerprint must match."""
        from ovid.disc import Disc

        disc2 = Disc.from_path(DISC_PATH)
        assert disc2.fingerprint == real_disc.fingerprint

    def test_canonical_string_starts_with_version(self, real_disc):
        assert real_disc.canonical_string.startswith("OVID-DVD-1|"), (
            f"Expected OVID-DVD-1| prefix in canonical string"
        )


class TestRealDiscStructure:
    """Sanity-check structural metadata from a real disc."""

    def test_has_at_least_one_vts(self, real_disc):
        assert real_disc.vts_count >= 1

    def test_has_at_least_one_title(self, real_disc):
        assert real_disc.title_count >= 1

    def test_vts_list_length_matches_count(self, real_disc):
        assert len(real_disc._vts_list) == real_disc.vts_count

    def test_source_type_is_reader(self, real_disc):
        assert real_disc.source_type.endswith("Reader"), (
            f"Expected a *Reader source type, got: {real_disc.source_type}"
        )
