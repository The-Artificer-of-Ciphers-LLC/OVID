---
phase: 04-blu-ray-uhd-fingerprinting
plan: 03
subsystem: fingerprinting
tags: [python, dataclass, tdd, disc-identity, blu-ray, aacs]

# Dependency graph
requires:
  - phase: 04-01
    provides: select_canonical_playlists() and the frozen bd2_spec.py anti-obfuscation ruleset
  - phase: 04-02
    provides: identify_bd() Tier-2-primary/Tier-1-alias identity resolver
provides:
  - "BDDisc.identity property exposing the full DiscIdentitySet (primary/aliases/diagnostics)"
  - "BDDisc no longer short-circuits on Tier-1 (AACS) success — delegates entirely to identify_bd()"
  - "BDDisc.playlists consolidated onto select_canonical_playlists() survivor set"
affects: [phase-04 remaining plans, disc_structure.py normalize_bd_disc, cli.py fingerprint --json]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BDDisc mirrors Disc's from_path()/_identity_set/.identity pattern exactly (disc.py:33 → bd_disc.py:60)"
    - ".fingerprint/.tier kept as thin proxies computed from .identity.primary for zero-code-change back-compat with cli.py and disc_structure.py"

key-files:
  created: []
  modified:
    - ovid-client/src/ovid/bd_disc.py
    - ovid-client/tests/test_bd_disc.py

key-decisions:
  - "BDDisc._build() independently re-derives canonical_string via build_bd_canonical_string() (wrapped in try/except ValueError) rather than having identify_bd() expose it — identify_bd()'s current signature/return (DiscIdentitySet) has no canonical-string field to reuse, so the plan's advisory de-dup optimization was not applicable without changing 04-02's shipped API; documented here instead of silently deviating"
  - "playlists_field is empty in the degenerate Tier-1-primary case (tier_num == 1), matching the pre-existing test_all_playlists_under_60s_with_aacs_uses_tier1 regression guarantee"

requirements-completed: [FPRINT-03, FPRINT-04, FPRINT-06]

coverage:
  - id: D1
    description: "BDDisc.from_path() never returns a Tier-1-only fingerprint when Tier-2 is computable — Tier 2 is always primary, Tier 1 attached as alias via .identity"
    requirement: "FPRINT-03"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscAliasPair::test_bd2_primary_with_aacs_alias"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscAliasPair::test_uhd2_primary_with_uhd1_aacs_alias"
        status: pass
    human_judgment: false
  - id: D2
    description: "Degenerate-case regression preserved: all playlists under 60s + AACS present → Tier 1 becomes primary with no aliases, empty playlists"
    requirement: "FPRINT-03"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscNegative::test_all_playlists_under_60s_with_aacs_uses_tier1"
        status: pass
    human_judgment: false
  - id: D3
    description: "UHD discs flow through identify_bd() identically to standard Blu-ray, with format_type recorded correctly"
    requirement: "FPRINT-04"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscAliasPair::test_uhd2_primary_with_uhd1_aacs_alias"
        status: pass
    human_judgment: false
  - id: D4
    description: "Decoy/loop-padded playlists excluded from BDDisc.playlists (submitted title list), not just the fingerprint hash"
    requirement: "FPRINT-06"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscPlaylistConsolidation::test_playlists_excludes_loop_padded_decoy_not_just_short_ones"
        status: pass
    human_judgment: false
  - id: D5
    description: ".fingerprint/.tier remain valid back-compat proxies computed from .identity.primary; cli.py and disc_structure.py require zero code changes"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestBDDiscAliasPair::test_fingerprint_and_tier_are_thin_proxies_to_identity_primary"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_disc.py::TestCLIBDFingerprint::test_cli_fingerprint_bd_with_aacs_shows_bd2_primary"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-06
status: complete
---

# Phase 04 Plan 03: BDDisc Tier-1-short-circuit removal Summary

**Removed BDDisc's AACS Tier-1 short-circuit; `.identity` now exposes the full alias pair via `identify_bd()`, and `.playlists` is consolidated onto `select_canonical_playlists()`'s survivor set so decoy playlists never appear as submitted titles.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-06T17:59:47Z
- **Completed:** 2026-07-06T18:24:00Z
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files modified:** 2

## Accomplishments
- `BDDisc._try_aacs_tier1()` deleted entirely — identity resolution now delegates to `identify_bd()` (Plan 04-02), which always makes Tier 2 primary when computable and attaches Tier 1 as an alias
- New `BDDisc.identity` property + `_identity_set` frozen dataclass field expose the full `DiscIdentitySet` (primary, aliases, diagnostics), consumed automatically by `cli.py`'s existing generic `_disc_identity_set()` getattr helper with zero `cli.py` changes
- `BDDisc.playlists` now built from `select_canonical_playlists()`'s survivor set (the same set used for the Tier-2 hash) instead of an ad-hoc 60-second-only filter — a loop-padded decoy playlist that passes the duration filter but fails the max-clip-repeat filter is now excluded from the submitted title list too
- Rewrote 3 stale tests (`test_tier1_with_aacs`, `test_tier1_uhd`, `test_cli_fingerprint_bd_tier1`) that asserted the old short-circuit behavior; added 4 new tests covering the alias pair, diagnostics, proxy behavior, and playlist consolidation
- The pre-existing degenerate-case regression (`test_all_playlists_under_60s_with_aacs_uses_tier1`) still passes unmodified in behavior, with new `.identity` assertions added to prove consistency

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: RED — rewrite stale short-circuit tests, add alias-pair/diagnostics/playlist-consolidation tests** - `33a4327` (test)
2. **Task 2: GREEN — BDDisc.identity, delegate to identify_bd(), consolidate playlist filtering** - `ea3de7f` (feat)

_Note: RED commit shows exactly 7 expected failures against the pre-refactor implementation; all 28 unrelated tests remained green throughout._

## Files Created/Modified
- `ovid-client/src/ovid/bd_disc.py` - Removed `_try_aacs_tier1`; `_build()` now calls `identify_bd()` and `select_canonical_playlists()`; added `.identity` property and `_identity_set` field
- `ovid-client/tests/test_bd_disc.py` - Renamed `TestBDDiscTier1` → `TestBDDiscAliasPair`; rewrote 3 stale tests; added 4 new tests including a new `TestBDDiscPlaylistConsolidation` class

## Decisions Made
- `canonical_string` is independently re-derived in `_build()` via `build_bd_canonical_string()` wrapped in `try/except ValueError`, rather than reusing a value exposed by `identify_bd()`. The plan's advisory note suggested reuse "if `identify_bd()` exposes the canonical string it derived" — as shipped in Plan 04-02, `identify_bd()`'s return type (`DiscIdentitySet`) has no canonical-string field, so there was nothing to reuse without changing 04-02's already-shipped, tested API. This is a one-line double-computation of a lightweight string-formatting call (not the SHA-256 hash itself, which happens once inside `identify_bd()`), so the plan-checker's redundant-work concern is negligible in practice. Documented here rather than silently accepting or silently expanding scope into 04-02.
- Kept `playlists_field = []` for the degenerate Tier-1-primary case (mirrors old behavior exactly) since no survivor set exists when Tier 2 itself is uncomputable.

## Deviations from Plan

None — plan executed exactly as written. The one implementation note above (canonical_string re-derivation) was explicitly flagged as advisory-only in the plan ("This is guidance, not a hard requirement") and is documented as a decision, not a deviation.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- FPRINT-03/04/06 fully closed for the `BDDisc` integration surface; `identify_bd()` (04-02) and `select_canonical_playlists()` (04-01) are now both consumed end-to-end through the public `BDDisc.from_path()` API
- `cli.py` and `disc_structure.py` required zero code changes — confirms the `.identity`/`_identity_set` pattern established for DVD (`Disc`) generalizes cleanly to Blu-ray/UHD (`BDDisc`)
- Full `ovid-client` suite green: 233 passed, 10 skipped (pre-existing `real_disc` hardware-marker tests, `OVID_TEST_DISC_PATH` not set — unrelated to this plan)
- Remaining Phase 04 plans can build on `BDDisc.identity` for any downstream alias-pair consumption (e.g. API submission payloads) with no further `BDDisc` internals changes expected

---
*Phase: 04-blu-ray-uhd-fingerprinting*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files exist on disk and both task commits (`33a4327`, `ea3de7f`) are present in git history.
