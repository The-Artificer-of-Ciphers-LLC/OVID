---
phase: 04-blu-ray-uhd-fingerprinting
plan: 01
subsystem: fingerprinting
tags: [bluray, uhd, mpls, fingerprint, tdd, security]

# Dependency graph
requires: []
provides:
  - "ovid.bd2_spec module: frozen OVID-BD-2 constants (OVID_BD2_VERSION, MIN_DURATION_SECONDS, MAX_CLIP_REPEATS)"
  - "select_canonical_playlists(): filter + dedup + content-based tie-break pipeline"
  - "_clip_sequence()/_clip_repeat_count() helpers for content-based playlist identity"
  - "Closed filename-based tie-break obfuscation hole in build_bd_canonical_string()"
affects: [04-03-bddisc-refactor, 04-05-fixture-corpus]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Frozen, version-tagged constants module (bd2_spec.py) as single source of truth for anti-obfuscation ruleset — any edit without a version bump is a fingerprint-drift bug, not a config tweak"
    - "Content-based playlist identity (clip_id, in_time, out_time tuple) replaces filename-based sort/dedup for tamper resistance"

key-files:
  created:
    - ovid-client/src/ovid/bd2_spec.py
  modified:
    - ovid-client/src/ovid/bd_fingerprint.py
    - ovid-client/tests/test_bd_fingerprint.py

key-decisions:
  - "OVID_BD2_VERSION frozen at 'OVID-BD-2' (unchanged literal) — this phase freezes the pre-release v1 ruleset, not a version migration (D-08)"
  - "Tie-break key is the full clip-sequence tuple (clip_id, in_time, out_time), never filename — closes the exploited Lionsgate/ScreenPass-style renumbering obfuscation"
  - "Dedup happens after the min-duration/max-clip-repeat filter, keyed on first-occurrence clip sequence"

patterns-established:
  - "Frozen constants module pattern: bd2_spec.py documents in its own docstring why an unversioned edit is a correctness bug, not a tuning knob"

requirements-completed: [FPRINT-01, FPRINT-02, FPRINT-06]

coverage:
  - id: D1
    description: "Tier-2 filter/max-clip-repeat/tie-break constants frozen in bd2_spec.py — no duplicate hardcoded copies remain in bd_fingerprint.py"
    requirement: "FPRINT-06"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint.py::TestBDCanonicalString::test_canonical_string_uses_ovid_bd2_version_constant"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two playlists with identical (clip_id, in_time, out_time) sequences across all play-items collapse to one canonical block, regardless of filename"
    requirement: "FPRINT-06"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint.py::TestBDCanonicalString::test_dedup_by_clip_sequence_excludes_duplicate_decoy"
        status: pass
    human_judgment: false
  - id: D3
    description: "A playlist whose in-item clip_id repeats more than MAX_CLIP_REPEATS times (loop-padded decoy) is excluded from the canonical string"
    requirement: "FPRINT-06"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint.py::TestBDCanonicalString::test_max_clip_repeats_filter_excludes_loop_padded_decoy"
        status: pass
    human_judgment: false
  - id: D4
    description: "Tie-break order between same-duration playlists is determined by clip-sequence content, never by .mpls filename"
    requirement: "FPRINT-06"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint.py::TestBDCanonicalString::test_tie_break_is_clip_sequence_not_filename"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_fingerprint.py::TestBDCanonicalString::test_deduped_playlists_still_sort_by_duration_then_clip_sequence"
        status: pass
    human_judgment: false

# Metrics
duration: 30min
completed: 2026-07-06
status: complete
---

# Phase 04 Plan 01: Freeze OVID-BD-2 Tier-2 Ruleset Summary

**Froze the Tier-2 anti-obfuscation constants into `bd2_spec.py` and replaced `build_bd_canonical_string()`'s filename-based tie-break with a content-based filter → max-clip-repeat filter → clip-sequence dedup → clip-sequence tie-break pipeline (FPRINT-06).**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-07-06T17:04:38Z (prior plan commit baseline)
- **Completed:** 2026-07-06T17:33:01Z
- **Tasks:** 2 (TDD: RED, GREEN)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- New frozen, version-tagged `ovid-client/src/ovid/bd2_spec.py` module: `OVID_BD2_VERSION`, `MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS` — single source of truth for the Tier-2 ruleset, replacing the previously duplicated `_MIN_DURATION_SECONDS` constant.
- `select_canonical_playlists()` in `bd_fingerprint.py`: filters by min-duration + max-clip-repeat decoy exclusion, dedups by content-based clip sequence, sorts by `(-duration, clip_sequence)` — never filename.
- `build_bd_canonical_string()` now delegates to `select_canonical_playlists()` and sources its version prefix from `bd2_spec.OVID_BD2_VERSION` instead of a hardcoded `"OVID-BD-2"` literal.
- Closed the real, exploited filename-renumbering obfuscation hole (studios reorder `.mpls` files to defeat naive tie-breaks).
- Applied the FPRINT-01/D-10 docstring wording fix clarifying "AACS Disc ID" terminology equivalence with the FOSS Blu-ray tooling ecosystem (libaacs, MakeMKV keydb.cfg) — a stable one-way SHA-1 identifier, never a decryption key.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: RED — tests for frozen ruleset** - `8b91974` (test)
2. **Task 2: GREEN — bd2_spec.py + content-based filter/dedup/tie-break** - `f22e2ce` (feat)

**Plan metadata:** _pending final docs commit_

## Files Created/Modified
- `ovid-client/src/ovid/bd2_spec.py` - New frozen constants module (`OVID_BD2_VERSION`, `MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS`)
- `ovid-client/src/ovid/bd_fingerprint.py` - `select_canonical_playlists()`, `_clip_sequence()`, `_clip_repeat_count()` added; `build_bd_canonical_string()` rewritten to delegate; AACS docstring wording fix
- `ovid-client/tests/test_bd_fingerprint.py` - 4 new tests + 1 rewritten test (`test_deterministic_sort_by_duration_then_filename` → `test_deduped_playlists_still_sort_by_duration_then_clip_sequence`); `_make_long_playlist` helper extended with optional `clip_id` param

## Decisions Made
- `OVID_BD2_VERSION` stays `"OVID-BD-2"` (D-08) — this is a freeze of the pre-release v1 ruleset, not a version bump; future constant edits must bump this literal.
- Tie-break and dedup both key on the full `(clip_id, in_time, out_time)` tuple per play item — the minimal content signature that is expensive for a studio to spoof without changing actual disc content.
- Rewrote (rather than skipped) the pre-existing byte-identical-fixture test, since the new dedup rule makes that fixture pairing a real, intentional collision — the rewritten test now asserts the correct post-dedup tie-break behavior with distinguishable fixtures.

## Deviations from Plan

None - plan executed exactly as written. The one design judgment call (making the rewritten `test_deduped_playlists_still_sort_by_duration_then_clip_sequence` fixtures also content-distinguishable via a differing `chapter_count`, not just a differing `clip_id`) was necessary to satisfy the plan's own RED acceptance criterion — with only a distinct `clip_id` and otherwise-identical block content, the test could not fail under the old filename-based implementation (block strings don't include clip_id), so it would not have proven RED. This is squarely within the task's `<behavior>` intent ("all three playlists in this test remain distinct after dedup") and required no architectural change — filed as an implementation refinement, not a deviation rule invocation.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `bd2_spec.py` and `select_canonical_playlists()` are now available for Plan 04-03 (BDDisc refactor) and Plan 04-05 (pinned/obfuscated fixture corpus) to build on.
- Full `ovid-client` test suite green: 222 passed, 10 skipped (real-disc hardware markers, unaffected).
- No blockers for subsequent Phase 04 plans.

---
*Phase: 04-blu-ray-uhd-fingerprinting*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files verified present on disk; all task commit hashes (`8b91974`, `f22e2ce`, `56e333d`) verified present in git log.
