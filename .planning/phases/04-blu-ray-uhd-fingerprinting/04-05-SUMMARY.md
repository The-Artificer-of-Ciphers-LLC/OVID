---
phase: 04-blu-ray-uhd-fingerprinting
plan: 05
subsystem: testing
tags: [bluray, uhd, fingerprint, pytest, mpls, aacs, anti-tautology, golden-test]

requires:
  - phase: 04-blu-ray-uhd-fingerprinting
    provides: "frozen bd2_spec.py constants + select_canonical_playlists()/build_bd_canonical_string() pipeline (04-01), BDDisc.identity/identify_bd() (04-02/04-03)"
provides:
  - "23-playlist heavily-obfuscated synthetic BD/UHD fixture exercising min-duration filter, max-clip-repeat filter, and clip-sequence dedup simultaneously"
  - "pinned/golden Tier-2 hash regression test (anti-tautology, hardcoded literal)"
  - "hardware-gated real-disc + cross-drive determinism test scaffold for FPRINT-05 manual verification"
affects: [04-blu-ray-uhd-fingerprinting-plan-06, release-verification]

tech-stack:
  added: []
  patterns:
    - "Golden/pinned-hash regression test with hardcoded, independently-computed literal (Phase 1 D-14 anti-tautology convention) applied to BD/UHD fingerprints"
    - "Hardware-gated real-disc test mirrored from test_real_disc.py's env-var + pytest marker gating pattern, extended with a second env var for cross-drive determinism proof"

key-files:
  created:
    - ovid-client/tests/test_bd_fingerprint_pinned.py
    - ovid-client/tests/test_bd_real_disc.py
  modified:
    - ovid-client/tests/conftest_bd.py

key-decisions:
  - "Composed the 23-playlist obfuscated fixture as 1 main feature + 1 byte-identical renumbered duplicate + 1 loop-padded 3x-repeat decoy + 20 short (5-55s, cycled) filler/menu playlists, matching the plan's fixed spec exactly — verified to collapse to exactly 1 survivor via select_canonical_playlists()"
  - "Pinned hash literals (bd2-32128d27bbf90490a8d8ffa5a21bb89fa379ed5c, uhd2-32128d27bbf90490a8d8ffa5a21bb89fa379ed5c) were computed once via a throwaway python3 -c invocation against the fixture builder + hash functions, then hardcoded as literals — never re-derived inside the test itself"
  - "test_bd_real_disc.py's TestRealBDDiscCrossDrive class is skipif-gated at the class level on OVID_TEST_DISC_PATH_2, keeping the single-disc assertions independently runnable with just OVID_TEST_DISC_PATH set"

requirements-completed: [FPRINT-05, FPRINT-06, FPRINT-07]

coverage:
  - id: D1
    description: "23-playlist heavily-obfuscated synthetic BDMV fixture collapses to exactly 1 canonical survivor through the frozen filter/dedup/tie-break pipeline"
    requirement: FPRINT-07
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint_pinned.py#test_canonical_string_reflects_single_survivor_after_full_pipeline"
        status: pass
      - kind: other
        ref: "python3 -c invocation asserting len(build_heavily_obfuscated_fixture())==23 and len(select_canonical_playlists(...))==1"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pinned/golden Tier-2 hash test for the obfuscated fixture uses a hardcoded, independently-computed literal (not re-derived in-test) — fails if bd2_spec.py drifts without an OVID_BD2_VERSION bump"
    requirement: FPRINT-06
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint_pinned.py#test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture_bd"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint_pinned.py#test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture_uhd"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint_pinned.py#test_canonical_string_uses_frozen_version_literal"
        status: pass
    human_judgment: false
  - id: D3
    description: "Hardware-gated real-disc test (test_bd_real_disc.py) mirrors test_real_disc.py's DVD gating pattern, collects and skips cleanly with no hardware, includes a cross-drive determinism test for FPRINT-05, and never asserts on raw AACS bytes"
    requirement: FPRINT-05
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_real_disc.py (collects, 6 SKIPPED, 0 errors when OVID_TEST_DISC_PATH/OVID_TEST_DISC_PATH_2 unset)"
        status: pass
      - kind: other
        ref: "grep -c 'Unit_Key_RO' ovid-client/tests/test_bd_real_disc.py == 0"
        status: pass
    human_judgment: true
    rationale: "The actual cross-drive/cross-OS determinism assertion (TestRealBDDiscCrossDrive) can only run against real physical BD/UHD discs and >=2 drives, which no CI runner has. This test is the human-gated mechanism Plan 04-06 will use during pre-release verification; it is proven to collect and skip correctly here, but the substantive proof requires human-operated hardware."

duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 4 Plan 5: Obfuscated Fixture + Pinned Golden Tests + Real-Disc Determinism Summary

**23-playlist heavily-obfuscated synthetic BD fixture collapsing to 1 canonical survivor, backed by a hardcoded-literal golden hash test and a hardware-gated real-disc/cross-drive test scaffold**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-06
- **Tasks:** 2/2 completed
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- Added `build_heavily_obfuscated_fixture()` to `conftest_bd.py`: a fixed, fully-specified 23-playlist BDMV corpus (1 main feature, 1 byte-identical renumbered duplicate, 1 loop-padded 3x-repeat decoy, 20 short fillers under 60s) that exercises all three OVID-BD-2 anti-obfuscation defenses (min-duration filter, max-clip-repeat filter, clip-sequence dedup) simultaneously and proves the pipeline collapses it to exactly 1 canonical survivor
- Added `test_bd_fingerprint_pinned.py` with 4 tests: two golden/pinned-hash tests (BD and UHD) asserting against hardcoded, independently-computed 44/45-char literals — never re-derived by calling the hash function a second time inside the test (anti-tautology, Phase 1 D-14 convention) — plus a frozen-version-literal check and a single-survivor structural check
- Added `test_bd_real_disc.py` mirroring `test_real_disc.py`'s env-var + `pytest.mark.real_disc` gating pattern, with `TestRealBDDiscFingerprint` (5 tests: prefix, hex format, determinism, canonical-string version, identity diagnostics) and a class-level-gated `TestRealBDDiscCrossDrive` (1 test) for the FPRINT-05 ≥2-drives proof — all assertions operate only on `.fingerprint`/`.canonical_string`/`.identity.diagnostics`, never raw AACS bytes

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend conftest_bd.py with a heavily-obfuscated fixture builder** - `39d379e` (test)
2. **Task 2: Pinned/golden determinism tests + real_disc-gated cross-drive test** - `b626e84` (test)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified

- `ovid-client/tests/conftest_bd.py` - added `build_heavily_obfuscated_fixture(is_uhd)` (133 lines added), returning the 23-tuple unfiltered playlist corpus
- `ovid-client/tests/test_bd_fingerprint_pinned.py` (new) - 4 golden/pinned tests for the obfuscated fixture's Tier-2 hash
- `ovid-client/tests/test_bd_real_disc.py` (new) - hardware-gated real-disc + cross-drive determinism tests

## Decisions Made

- Pinned hash literals were computed once via a throwaway `python3 -c` script importing the fixture builder and hash functions directly, then pasted as hardcoded string constants (`PINNED_BD2_HASH`, `PINNED_UHD2_HASH`) at the top of the test module — satisfies the anti-tautology requirement since the test never calls `compute_bd_structure_fingerprint()` to produce its own expected value.
- Filler playlist durations cycle through 5-55s in 5s increments (`5.0 + (i % 11) * 5.0`) across all 20 filenames rather than requiring exactly 20 distinct duration values, since the plan's "5-55 seconds in 5-second increments" range only yields 11 distinct steps — all 20 fillers remain well under `MIN_DURATION_SECONDS` (60s) regardless, so the filter behavior is unaffected.
- Discovered during Task 2 verification: local `pip install -e '.[dev]'` regenerated `ovid-client/src/ovid_client.egg-info/PKG-INFO` and `SOURCES.txt` as a side effect of running the test suite in a scratch venv. These are tracked build artifacts unrelated to this plan's scope — reverted via `git restore` before staging so only the plan's intended files were committed.

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria (23 tuples, 1 survivor, 4 passing pinned tests, 6 cleanly-skipped real-disc tests, zero `Unit_Key_RO` references) were met without needing Rule 1-4 auto-fixes.

## Issues Encountered

Running the test suite required a local virtualenv + `pip install -e '.[dev]'` since Homebrew's system Python 3 is externally managed (PEP 668) and blocks bare `pip install`. Resolved by creating a scratch venv under the session's scratchpad directory, matching the CI workflow's `pip install -e '.[dev]'` step. No project files were affected by this — only the transient egg-info regeneration noted above, which was reverted.

## User Setup Required

None - no external service configuration required. The real-disc tests in `test_bd_real_disc.py` are intentionally hardware-gated (`OVID_TEST_DISC_PATH`/`OVID_TEST_DISC_PATH_2`) and will be exercised manually as part of Plan 04-06's pre-release verification, not as part of this plan's automated scope.

## Next Phase Readiness

The obfuscated fixture, pinned golden test, and real-disc test scaffold are all in place and passing (237 passed, 16 skipped across the full `ovid-client` suite, zero regressions). Plan 04-06 can proceed to use `test_bd_real_disc.py` for the manual pre-release cross-drive/cross-OS verification step it documents.

---
*Phase: 04-blu-ray-uhd-fingerprinting*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files and referenced commit hashes verified present in the working tree and git history.
