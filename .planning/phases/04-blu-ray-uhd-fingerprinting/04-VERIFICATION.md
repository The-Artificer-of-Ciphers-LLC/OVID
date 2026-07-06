---
phase: 04-blu-ray-uhd-fingerprinting
verified: 2026-07-06T00:00:00Z
status: passed
score: 21/21 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 4: Blu-ray/UHD Fingerprinting Verification Report

**Phase Goal:** Blu-ray and 4K UHD discs reach fingerprinting parity with the DVD path — Tier 1 (AACS) and Tier 2 (BDMV structure), coexisting as an alias pair, backed by real fixtures and a versioned spec.
**Verified:** 2026-07-06
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Tier-2 filter/repeat/tie-break constants live in one frozen module, no duplicate copies | ✓ VERIFIED | `ovid-client/src/ovid/bd2_spec.py` defines `OVID_BD2_VERSION`, `MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS`; `grep -c "_MIN_DURATION_SECONDS" bd_fingerprint.py` → 0; `bd_fingerprint.py:29` imports constants from `bd2_spec` |
| 2 | Byte-identical clip sequences (renumbered decoys) collapse to one canonical block | ✓ VERIFIED | `select_canonical_playlists()` dedups by `_clip_sequence()` tuple (bd_fingerprint.py:97-102); `test_dedup_by_clip_sequence_excludes_duplicate_decoy` passes |
| 3 | Loop-padded decoy (clip_id repeats > MAX_CLIP_REPEATS) excluded from canonical string | ✓ VERIFIED | `_clip_repeat_count()` + filter (bd_fingerprint.py:50-59, 88); `test_max_clip_repeats_filter_excludes_loop_padded_decoy` passes |
| 4 | Tie-break is content-based clip sequence, never filename | ✓ VERIFIED | sort key `(-x[2], _clip_sequence(x[1]))` (bd_fingerprint.py:114), no filename in sort key; `test_tie_break_is_clip_sequence_not_filename` passes |
| 5 | `identify_bd()` never short-circuits to Tier-1-only when Tier-2 is computable | ✓ VERIFIED | `disc_identity.py:185-210` — Tier-2 attempted after Tier-1, becomes primary whenever `build_bd_canonical_string()` succeeds; `test_identify_bd_keeps_bd2_primary_when_aacs_present` passes |
| 6 | Every AACS availability branch records exactly one diagnostic, never silently dropped | ✓ VERIFIED | `disc_identity.py:164-183` — 5 distinct branches (`no_aacs_directory`, `aacs_unit_key_missing`, `aacs_fingerprint_failed`, `aacs_disc_id_available`, plus the Tier2-unavailable fallback code), each appends exactly one diagnostic |
| 7 | Tier-2-unavailable + AACS-available falls back to Tier-1-primary (documented, diagnosed) | ✓ VERIFIED | `disc_identity.py:187-198` returns `tier2_unavailable_using_tier1_primary` diagnostic + Tier-1 primary; `test_identify_bd_falls_back_to_tier1_primary_when_tier2_unavailable` passes; regression `test_all_playlists_under_60s_with_aacs_uses_tier1` independently re-run and PASSED |
| 8 | Neither tier computable → propagates ValueError, no hollow identity | ✓ VERIFIED | `disc_identity.py:199` bare `raise` when `tier1_identity is None`; `test_identify_bd_raises_when_neither_tier_available` passes |
| 9 | `BDDisc.from_path()` returns bd2-/uhd2- primary with bd1-aacs-/uhd1-aacs- alias — never bare Tier-1-only when both compute | ✓ VERIFIED | `bd_disc.py:144-165` delegates entirely to `identify_bd()`; `grep -rn "_try_aacs_tier1"` across `ovid-client/` returns 0 matches (short-circuit fully removed) |
| 10 | `BDDisc.fingerprint`/`.tier` continue to work for existing callers (cli.py, disc_structure.py) with zero caller changes | ✓ VERIFIED | `cli.py:231-234` `_disc_identity_set()` uses generic `getattr(disc, "_identity_set", None)` — matches `BDDisc`'s dataclass field name unchanged; `disc_structure.py:142` reads `bd_disc.format_type` unchanged |
| 11 | Decoy playlists excluded from `BDDisc.playlists`, not just the fingerprint hash | ✓ VERIFIED | `bd_disc.py:148-150` populates `playlists_field` from `select_canonical_playlists()` survivors (same pipeline as the Tier-2 hash), not a separate ad-hoc filter |
| 12 | UHD discs flow through the same tiered path, format recorded end-to-end | ✓ VERIFIED | `bd_disc.py:127-130` UHD detection via MPLS header version; `disc_structure.py:142,185` maps `format_type` → `format="UHD"/"Blu-ray"` in the normalized submission payload |
| 13 | Pre-existing degenerate-case regression continues to pass unmodified | ✓ VERIFIED | Ran `test_all_playlists_under_60s_with_aacs_uses_tier1` in isolation — 1 passed |
| 14 | `ovid-client-tests` CI job runs on both `ubuntu-latest` and `macos-latest` | ✓ VERIFIED | `.github/workflows/ci.yml:16` `os: [ubuntu-latest, macos-latest]` under `fail-fast: false` matrix |
| 15 | Committed CI-enforced fixture exercising all 3 D-06 defenses, pinned hash not re-derived | ✓ VERIFIED | `conftest_bd.py:318` `build_heavily_obfuscated_fixture()` (23 playlists: main feature, renumbered dup, loop-pad decoy, 20 short menu decoys); `test_bd_fingerprint_pinned.py` asserts against hardcoded `PINNED_BD2_HASH`/`PINNED_UHD2_HASH` string literals, never calls the hash fn twice to compare against itself |
| 16 | Real-disc hardware-gated cross-drive determinism test exists, never commits/prints raw AACS bytes | ✓ VERIFIED | `test_bd_real_disc.py` gated on `OVID_TEST_DISC_PATH`/`_2` env vars + `real_disc` marker; docstring D-11 legal boundary; only `.fingerprint`/`.canonical_string`/`.identity.diagnostics` are asserted, no raw byte access |
| 17 | Pinned test fails if `bd2_spec.py` constants change without an `OVID_BD2_VERSION` bump | ✓ VERIFIED | Mechanism verified by construction: `PINNED_BD2_HASH`/`PINNED_UHD2_HASH` are SHA-256 outputs of the current constants; any constant change alters `compute_bd_structure_fingerprint()`'s output and the literal comparison fails |
| 18 | `docs/fingerprint-spec.md` documents OVID-BD-2 Tier 1 & 2, mirroring OVID-DVD-1 structure incl. its own Versioning section | ✓ VERIFIED | `docs/fingerprint-spec.md:171-244` full "OVID-BD-2 Fingerprint Algorithm Specification" section: Overview, Alias-Pair Behavior, Tier 1, Tier 2, Format Detection, Versioning |
| 19 | AACS Disc ID legal-boundary wording (SHA-1 of plaintext file, not a decryption key) stated explicitly | ✓ VERIFIED | `docs/fingerprint-spec.md:193-197` — explicit "AACS Disc ID ≡ SHA-1(AACS/Unit_Key_RO.inf)... not a decryption key" wording; matching code-level docstrings in `bd_fingerprint.py:1-9,119-127` and `disc_identity.py:122-127` |
| 20 | UHD header-version heuristic limits documented, not presented as spec-guaranteed | ✓ VERIFIED | `docs/fingerprint-spec.md:229-231` — explicitly states this is "a community-corroborated convention, not a licensed BDA specification guarantee" |
| 21 | Manual pre-release cross-drive verification step documented | ✓ VERIFIED | `docs/contributing.md:147-163` "Manual pre-release verification (Blu-ray/UHD)" subsection referencing `test_bd_real_disc.py`, `OVID_TEST_DISC_PATH`/`_2` |

**Score:** 21/21 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `ovid-client/src/ovid/bd2_spec.py` | Frozen constants module | ✓ VERIFIED | 3 constants, substantial docstring, wired via import in `bd_fingerprint.py` |
| `select_canonical_playlists()`, `_clip_sequence()`, `_clip_repeat_count()` (bd_fingerprint.py) | Filter/dedup/tie-break pipeline | ✓ VERIFIED | All present, wired into `build_bd_canonical_string()` |
| `identify_bd()`, `ovid_bd2_identity()`, `aacs_identity()`, `OVID_BD2_METHOD`, `AACS_METHOD` (disc_identity.py) | Alias-pair identity resolution | ✓ VERIFIED | All present, wired into `bd_disc.py` |
| `BDDisc.identity` property / `_identity_set` field (bd_disc.py) | Full DiscIdentitySet accessor | ✓ VERIFIED | Present, wired to `cli.py`'s generic getattr |
| `.github/workflows/ci.yml` matrix.os addition | macos-latest added | ✓ VERIFIED | `os: [ubuntu-latest, macos-latest]` |
| `build_heavily_obfuscated_fixture()` (conftest_bd.py) | 23-playlist synthetic corpus | ✓ VERIFIED | Present, produces 1 survivor via full pipeline |
| `ovid-client/tests/test_bd_fingerprint_pinned.py` | Golden/anti-tautology tests | ✓ VERIFIED | 4 tests, hardcoded literal comparison |
| `ovid-client/tests/test_bd_real_disc.py` | Hardware-gated cross-drive test | ✓ VERIFIED | Present, skips cleanly without env vars |
| `docs/fingerprint-spec.md` OVID-BD-2 section | Spec documentation | ✓ VERIFIED | Full section present |
| `docs/contributing.md` manual pre-release subsection | Cross-drive verification doc | ✓ VERIFIED | Present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `build_bd_canonical_string()` | `select_canonical_playlists()` | Direct call, `bd2_spec.py` constants only | ✓ WIRED | `bd_fingerprint.py:175` |
| `identify_bd()` | `build_bd_canonical_string()` | ValueError signals Tier-2 unavailability | ✓ WIRED | `disc_identity.py:186-199`, exception path tested |
| `identify_bd()` | `reader.has_aacs()`/`read_aacs_file()` | Injected duck-typed reader | ✓ WIRED | `disc_identity.py:164,167` |
| `BDDisc._build()` | `identify_bd()` | Identity resolution | ✓ WIRED | `bd_disc.py:144` |
| `BDDisc._build()` | `select_canonical_playlists()` | Consolidated playlist survivor set | ✓ WIRED | `bd_disc.py:149` |
| `BDDisc._identity_set` | `cli.py` `_disc_identity_set()` | Generic getattr, no cli.py changes | ✓ WIRED | `cli.py:231-234` |
| `docs/fingerprint-spec.md` Versioning | `bd2_spec.py` `OVID_BD2_VERSION` | Version-bump-mints-new-namespace | ✓ WIRED | Doc explicitly references constant names and mechanism |
| `docs/contributing.md` manual step | `test_bd_real_disc.py` | Referenced by filename and env vars | ✓ WIRED | Doc references exact test file and env var names |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full ovid-client suite passes | `pytest ovid-client/tests/ -q` | 237 passed, 16 skipped (real_disc hardware tests) | ✓ PASS |
| Degenerate-case regression in isolation | `pytest -k test_all_playlists_under_60s_with_aacs_uses_tier1` | 1 passed | ✓ PASS |
| No Tier-1 short-circuit remains in source | `grep -rn "_try_aacs_tier1" ovid-client/` | 0 matches | ✓ PASS |
| No raw AACS key material stored/logged | `grep -rn "Unit_Key_RO" ovid-client/` | All hits are read-for-hashing or docstring/test references, no persistence/logging of raw bytes | ✓ PASS |
| Focused module test runs (bd_fingerprint, bd_identity, bd_disc, pinned) | `pytest test_bd_fingerprint.py test_bd_identity.py test_bd_disc.py test_bd_fingerprint_pinned.py -q` | 80 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FPRINT-01 | 04-01, 04-06 | Tier 1 AACS fingerprint (`bd1-aacs-*`) + legal wording | ✓ SATISFIED | `compute_aacs_fingerprint()`, docs section |
| FPRINT-02 | 04-01 | Tier 2 structure fingerprint (`bd2-*`) | ✓ SATISFIED | `build_bd_canonical_string()`/`compute_bd_structure_fingerprint()` |
| FPRINT-03 | 04-02, 04-03 | Alias pair, no short-circuit | ✓ SATISFIED | `identify_bd()`, `bd_disc.py` refactor |
| FPRINT-04 | 04-03, 04-06 | UHD via same path, format recorded | ✓ SATISFIED | `disc_structure.py` format mapping |
| FPRINT-05 | 04-04, 04-05, 04-06 | Cross-drive/cross-OS determinism | ✓ SATISFIED | CI matrix, real-disc test, manual doc step |
| FPRINT-06 [guardrail] | 04-01, 04-03, 04-05 | Frozen versioned constants | ✓ SATISFIED | `bd2_spec.py`, pinned test — **see note below on REQUIREMENTS.md checkbox** |
| FPRINT-07 | 04-05 | Real/obfuscated fixture corpus | ✓ SATISFIED | `build_heavily_obfuscated_fixture()` |
| DOCS-01 | 04-06 | Fingerprint spec updated | ✓ SATISFIED | `docs/fingerprint-spec.md` OVID-BD-2 section |

**Note (documentation inconsistency, not a code gap):** `.planning/REQUIREMENTS.md` line 17 shows FPRINT-06's checkbox as unchecked (`- [ ]`) while the traceability table at line 130 marks it "Complete." Code evidence (frozen `bd2_spec.py` module, pinned anti-tautology test, `select_canonical_playlists()` enforcement) fully satisfies FPRINT-06. This is a stale checkbox in REQUIREMENTS.md that should be corrected for bookkeeping accuracy but does not indicate missing implementation.

No orphaned requirements found — all 8 requirement IDs (FPRINT-01 through 07, DOCS-01) declared in plan frontmatter are present in REQUIREMENTS.md and traced to Phase 4.

### Anti-Patterns Found

None. Scanned all 13 phase-modified/created files for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented|coming soon` — zero matches.

### Human Verification Required

None. All must-haves are verifiable via static inspection and automated tests; the two hardware-dependent behaviors (cross-drive/cross-OS determinism) are covered by an environment-gated test that skips cleanly in CI and a documented manual pre-release procedure — this is the intentional, documented design (FPRINT-05's own acceptance criteria), not an unverified gap.

### Gaps Summary

No gaps found. All 21 derived observable truths across the 6 phase plans (04-01 through 04-06) verified directly against shipped source and a live, independently-executed test run (237 passed, 16 cleanly skipped, 0 failed). The Tier-1 short-circuit is confirmed fully removed (`_try_aacs_tier1` absent), the alias-pair behavior is implemented and tested including the degenerate fallback and hard-failure cases, the FPRINT-06 guardrail constants are frozen in a dedicated module backed by a hardcoded (non-tautological) pinned-hash test, CI runs cross-platform, and both `docs/fingerprint-spec.md` and `docs/contributing.md` carry the required documentation. One minor documentation bookkeeping inconsistency was found (REQUIREMENTS.md checkbox for FPRINT-06) — recommended for a quick doc fix but does not block phase completion.

---

_Verified: 2026-07-06_
_Verifier: Claude (gsd-verifier)_
