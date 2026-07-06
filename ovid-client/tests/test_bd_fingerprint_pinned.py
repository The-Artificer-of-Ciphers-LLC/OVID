"""Golden/anti-tautology tests pinning the OVID-BD-2 Tier-2 fingerprint.

FPRINT-06/FPRINT-07: the heavily-obfuscated 23-playlist synthetic fixture in
``conftest_bd.py`` must collapse to exactly 1 canonical survivor through the
frozen ``select_canonical_playlists()`` pipeline, and the resulting Tier-2
hash must be pinned against a hardcoded literal — never re-derived by calling
``compute_bd_structure_fingerprint`` a second time inside the test itself
(Phase 1 D-14 anti-tautology convention). The hardcoded values below were
computed once via a throwaway ``python3 -c`` invocation against the fixture
builder and the two hash functions, then pasted here as literals.

If ``bd2_spec.py`` constants change without an ``OVID_BD2_VERSION`` bump,
these tests fail — that failure is the intended signal (see bd2_spec.py
module docstring).
"""

from __future__ import annotations

from conftest_bd import build_heavily_obfuscated_fixture
from ovid import bd2_spec
from ovid.bd_fingerprint import build_bd_canonical_string, compute_bd_structure_fingerprint

# Hardcoded, independently-computed literals — do NOT derive these by calling
# compute_bd_structure_fingerprint() inside a test (anti-tautology, D-14).
PINNED_BD2_HASH = "bd2-32128d27bbf90490a8d8ffa5a21bb89fa379ed5c"
PINNED_UHD2_HASH = "uhd2-32128d27bbf90490a8d8ffa5a21bb89fa379ed5c"


def test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture_bd():
    playlists = build_heavily_obfuscated_fixture(is_uhd=False)
    canonical = build_bd_canonical_string(playlists, is_uhd=False)
    fingerprint = compute_bd_structure_fingerprint(canonical, is_uhd=False)
    assert fingerprint == PINNED_BD2_HASH, (
        f"BD Tier-2 fingerprint drifted from pinned value. "
        f"Expected {PINNED_BD2_HASH}, got {fingerprint}. "
        f"If this is an intentional bd2_spec.py ruleset change, bump "
        f"OVID_BD2_VERSION and update this pinned literal."
    )


def test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture_uhd():
    playlists = build_heavily_obfuscated_fixture(is_uhd=True)
    canonical = build_bd_canonical_string(playlists, is_uhd=True)
    fingerprint = compute_bd_structure_fingerprint(canonical, is_uhd=True)
    assert fingerprint == PINNED_UHD2_HASH, (
        f"UHD Tier-2 fingerprint drifted from pinned value. "
        f"Expected {PINNED_UHD2_HASH}, got {fingerprint}. "
        f"If this is an intentional bd2_spec.py ruleset change, bump "
        f"OVID_BD2_VERSION and update this pinned literal."
    )


def test_canonical_string_uses_frozen_version_literal():
    playlists = build_heavily_obfuscated_fixture(is_uhd=False)
    canonical = build_bd_canonical_string(playlists, is_uhd=False)
    assert canonical.startswith(f"{bd2_spec.OVID_BD2_VERSION}|"), (
        f"Expected canonical string to start with '{bd2_spec.OVID_BD2_VERSION}|', "
        f"got: {canonical}"
    )


def test_canonical_string_reflects_single_survivor_after_full_pipeline():
    playlists = build_heavily_obfuscated_fixture(is_uhd=False)
    canonical = build_bd_canonical_string(playlists, is_uhd=False)
    # Field 1 (0-indexed after split) is the survivor count — proves the
    # pinned hash corresponds to the deduped/filtered corpus (1 survivor),
    # not the raw 23-entry input.
    assert canonical.split("|")[1] == "1", (
        f"Expected exactly 1 surviving playlist after filter+dedup, "
        f"canonical string was: {canonical}"
    )
