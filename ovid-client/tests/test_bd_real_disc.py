"""Tests for real Blu-ray/UHD discs — skipped unless OVID_TEST_DISC_PATH is set.

Mirrors test_real_disc.py's DVD gating pattern (env var + real_disc marker).

Set OVID_TEST_DISC_PATH to a BDMV folder or mounted-disc path to run the
single-disc assertions:

    OVID_TEST_DISC_PATH=/mnt/bluray python -m pytest tests/test_bd_real_disc.py -v

Additionally set OVID_TEST_DISC_PATH_2 to a *second* physical drive/disc path
(the same physical disc pressing, read from a different drive) to also run
the FPRINT-05 cross-drive determinism test:

    OVID_TEST_DISC_PATH=/mnt/bluray_drive_a \\
    OVID_TEST_DISC_PATH_2=/mnt/bluray_drive_b \\
    python -m pytest tests/test_bd_real_disc.py -v

Legal boundary (D-11): every assertion in this file operates only on
``.fingerprint`` / ``.canonical_string`` / ``.identity.diagnostics`` string or
structural values. Raw AACS ``Unit_Key_RO.inf`` bytes are never read,
printed, logged, or asserted against here.
"""

from __future__ import annotations

import os
import re

import pytest

from ovid import bd2_spec

DISC_PATH = os.environ.get("OVID_TEST_DISC_PATH")
DISC_PATH_2 = os.environ.get("OVID_TEST_DISC_PATH_2")

pytestmark = [
    pytest.mark.real_disc,
    pytest.mark.skipif(
        DISC_PATH is None,
        reason="OVID_TEST_DISC_PATH not set — skipping real BD/UHD disc tests",
    ),
]


@pytest.fixture(scope="module")
def real_bd_disc():
    """Parse the real BD/UHD disc once for the entire module."""
    from ovid.bd_disc import BDDisc

    assert DISC_PATH is not None  # guarded by skipif above
    return BDDisc.from_path(DISC_PATH)


class TestRealBDDiscFingerprint:
    """Verify fingerprint format and structural sanity on a real BD/UHD disc."""

    def test_fingerprint_has_bd2_or_uhd2_prefix(self, real_bd_disc):
        assert real_bd_disc.fingerprint.startswith(("bd2-", "uhd2-")), (
            f"Expected bd2- or uhd2- prefix, got: {real_bd_disc.fingerprint}"
        )

    def test_fingerprint_is_hex_after_prefix(self, real_bd_disc):
        _, hex_part = real_bd_disc.fingerprint.split("-", 1)
        assert re.fullmatch(r"[0-9a-f]+", hex_part), (
            f"Expected hex hash after prefix, got: {hex_part}"
        )

    def test_fingerprint_deterministic(self, real_bd_disc):
        """Parse the same disc again — fingerprint must match."""
        from ovid.bd_disc import BDDisc

        disc2 = BDDisc.from_path(DISC_PATH)
        assert disc2.fingerprint == real_bd_disc.fingerprint

    def test_canonical_string_starts_with_frozen_version(self, real_bd_disc):
        if real_bd_disc.tier != 2:
            pytest.skip(
                "Tier 1 disc (degenerate AACS-only case) has an empty "
                "canonical_string — nothing to assert."
            )
        assert real_bd_disc.canonical_string.startswith(
            bd2_spec.OVID_BD2_VERSION + "|"
        ), (
            f"Expected canonical string to start with "
            f"'{bd2_spec.OVID_BD2_VERSION}|', got: {real_bd_disc.canonical_string}"
        )

    def test_identity_selection_has_diagnostics(self, real_bd_disc):
        assert real_bd_disc.identity is not None
        assert real_bd_disc.identity.diagnostics


@pytest.mark.skipif(
    DISC_PATH_2 is None,
    reason="OVID_TEST_DISC_PATH_2 not set — skipping cross-drive determinism test",
)
class TestRealBDDiscCrossDrive:
    """FPRINT-05: prove the fingerprint is identical across >=2 drives."""

    def test_cross_drive_fingerprint_matches(self):
        from ovid.bd_disc import BDDisc

        assert DISC_PATH is not None  # guarded by module-level skipif
        assert DISC_PATH_2 is not None  # guarded by class-level skipif

        disc_a = BDDisc.from_path(DISC_PATH)
        disc_b = BDDisc.from_path(DISC_PATH_2)
        assert disc_a.fingerprint == disc_b.fingerprint, (
            f"Fingerprint mismatch across drives: {disc_a.fingerprint} != "
            f"{disc_b.fingerprint}"
        )
