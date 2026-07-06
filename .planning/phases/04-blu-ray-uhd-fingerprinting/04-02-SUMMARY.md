---
phase: 04-blu-ray-uhd-fingerprinting
plan: 02
subsystem: fingerprint
tags: [python, disc-identity, aacs, blu-ray, tdd]

requires:
  - phase: 04-blu-ray-uhd-fingerprinting
    provides: "build_bd_canonical_string()/compute_aacs_fingerprint()/compute_bd_structure_fingerprint() (Plan 04-01) — the Tier-2/Tier-1 primitives identify_bd() composes"
provides:
  - "identify_bd() — Tier-2-primary/Tier-1-alias identity resolver for Blu-ray/UHD discs, mirroring identify_dvd()'s discipline exactly"
  - "ovid_bd2_identity()/aacs_identity() DiscIdentity builders plus OVID_BD2_METHOD/AACS_METHOD constants"
  - "5 new diagnostic codes: no_aacs_directory, aacs_unit_key_missing, aacs_fingerprint_failed, aacs_disc_id_available, tier2_unavailable_using_tier1_primary"
affects: ["04-03: bd_disc.py delegation to identify_bd()", "phase-05: any future BD lookup-alias work"]

tech-stack:
  added: []
  patterns:
    - "Always-primary, opportunistic-alias, one-diagnostic-per-branch identity resolution (mirrored from identify_dvd())"
    - "Duck-typed reader injection for testability (reader: has_aacs()/read_aacs_file()) instead of a bare callable, since two related reads are needed"

key-files:
  created:
    - ovid-client/tests/test_bd_identity.py
  modified:
    - ovid-client/src/ovid/disc_identity.py

key-decisions:
  - "Wrapped both the AACS-empty-check and the aacs_identity() call in a single try/except Exception, rather than only wrapping aacs_identity() as the plan's action text literally described — otherwise a non-bytes read_aacs_file() return value raises TypeError from len() outside any handler, which would crash identify_bd() instead of recording aacs_fingerprint_failed (needed to make the hash-failure test pass exactly as specified)."
  - "Deferred the plan's optional implementation note (surfacing the derived Tier-2 canonical string on the diagnostic/return value for Plan 04-03 reuse) — not required by any must_have/test in this plan, and adding an untested field to the shared DiscIdentitySet dataclass would be speculative scope; Plan 04-03 can recompute or receive it explicitly when bd_disc.py delegation is authored."

requirements-completed: [FPRINT-03]

coverage:
  - id: D1
    description: "identify_bd() keeps Tier-2 (bd2/uhd2) primary and attaches Tier-1 (AACS) as an alias whenever both are computable — never a silent Tier-1 short-circuit"
    requirement: FPRINT-03
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_keeps_bd2_primary_when_aacs_present"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every AACS-availability branch (no directory, missing/empty file, hash failure, success) records exactly one diagnostic code"
    requirement: FPRINT-03
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_falls_back_when_aacs_unavailable"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_rejects_invalid_or_empty_aacs_data"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_records_diagnostic_when_aacs_hash_fails"
        status: pass
    human_judgment: false
  - id: D3
    description: "When Tier-2 is genuinely unavailable (zero surviving playlists) but AACS is present, identify_bd() falls back to a Tier-1-primary DiscIdentitySet instead of raising"
    requirement: FPRINT-03
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_falls_back_to_tier1_primary_when_tier2_unavailable"
        status: pass
    human_judgment: false
  - id: D4
    description: "When neither tier is computable, identify_bd() propagates the underlying ValueError rather than returning a hollow identity"
    requirement: FPRINT-03
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_bd_identity.py#test_identify_bd_raises_when_neither_tier_available"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 04 Plan 02: identify_bd() Tier-2-Primary/Tier-1-Alias Resolver Summary

**Added `identify_bd()` to `disc_identity.py`, mirroring `identify_dvd()` exactly: Tier-2 (BDMV structure) is always primary when computable, Tier-1 (AACS) is attached only as an alias, and the only fallback to Tier-1-primary is the explicit, diagnosed, degenerate case where Tier-2 itself raises.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-06T17:46:34Z
- **Tasks:** 2 (TDD RED + GREEN)
- **Files modified:** 2

## Accomplishments
- `test_bd_identity.py` (8 tests + `_FakeReader` test double) added, mirroring `test_disc_identity.py`'s structure, covering both identity-builder helpers and every `identify_bd()` branch (AACS present/absent/empty/hash-failure, Tier-2-unavailable-with-AACS fallback, Tier-2-unavailable-without-AACS raise)
- `identify_bd()`, `ovid_bd2_identity()`, `aacs_identity()`, `OVID_BD2_METHOD`, `AACS_METHOD` added to `disc_identity.py` — the FPRINT-03 gap-closing seam that stops `BDDisc` from ever short-circuiting to a Tier-1-only result when Tier-2 is also computable
- Confirmed the two `test_bd_disc.py` degenerate-case regressions (`test_all_playlists_under_60s`, `test_all_playlists_under_60s_with_aacs_uses_tier1`) are preserved by this function's contract at the unit level; full `BDDisc`-level wiring lands in Plan 04-03

## Task Commits

1. **Task 1: RED — test_bd_identity.py mirroring test_disc_identity.py, plus the Tier-2-unavailable fallback case** - `0e5fa86` (test)
2. **Task 2: GREEN — identify_bd(), ovid_bd2_identity(), aacs_identity() in disc_identity.py** - `828684a` (feat)

_No REFACTOR commit was needed — the GREEN implementation required no cleanup pass._

## Files Created/Modified
- `ovid-client/tests/test_bd_identity.py` - 8 new tests + `_FakeReader` duck-typed AACS reader test double
- `ovid-client/src/ovid/disc_identity.py` - `identify_bd()`, `ovid_bd2_identity()`, `aacs_identity()`, `OVID_BD2_METHOD`, `AACS_METHOD`

## Decisions Made
- Wrapped the AACS-empty-check together with the `aacs_identity()` call inside one `try/except Exception`, rather than only wrapping the `aacs_identity()` call as the plan's action text literally described. A non-bytes `read_aacs_file()` return value (the hash-failure test's `12345` int) raises `TypeError` from `len()` before `aacs_identity()` is ever called; without widening the `try` block that `TypeError` would propagate uncaught instead of being recorded as `aacs_fingerprint_failed`. This is a Rule 1 (bug) auto-fix — the test-encoded behavior is the source of truth and both are still one-diagnostic-per-branch.
- Deferred the plan's optional implementation note about surfacing the derived Tier-2 canonical string for Plan 04-03's reuse. No `must_have`/test in this plan requires it, and adding an untested field to the shared `DiscIdentitySet` dataclass now would be speculative scope. Plan 04-03 (the `bd_disc.py` delegation plan) can recompute the canonical string itself or this can be added there with test coverage.
- Typed the `reader` parameter as `"BDFolderReader"` under `TYPE_CHECKING` (not imported at runtime) to keep the fully-type-annotated convention without adding a runtime import — confirmed no circular-import risk (`ovid.readers.bd_folder` only imports `ovid.readers.base`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Widened the AACS try/except to cover the empty-check, not just aacs_identity()**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** The plan's literal action text placed `try/except` only around the `aacs_identity(unit_key_data, is_uhd)` call, with the `unit_key_data is None or len(unit_key_data) == 0` check as a separate `if` outside any handler. The hash-failure test (`test_identify_bd_records_diagnostic_when_aacs_hash_fails`) injects a non-bytes `12345` as `unit_key_data`, so `len(12345)` raises `TypeError` at the `if` check itself — before `aacs_identity()` is ever reached — which would propagate uncaught under the plan's literal placement.
- **Fix:** Moved the `if unit_key_data is None or len(...) == 0` check inside the same `try` block that wraps `aacs_identity()`, so any exception from either the emptiness check or the identity builder is caught and recorded as `aacs_fingerprint_failed`.
- **Files modified:** ovid-client/src/ovid/disc_identity.py
- **Verification:** `test_identify_bd_records_diagnostic_when_aacs_hash_fails` passes; all 8 new tests + 5 existing DVD tests pass; full suite green (230 passed, 10 skipped)
- **Committed in:** 828684a (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix, no scope creep — required to satisfy the plan's own test specification)
**Impact on plan:** Necessary correctness fix to make the plan's specified test pass; behavior matches every other must_have/acceptance criterion unchanged.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `identify_bd()` is unit-tested and ready for Plan 04-03 to wire into `bd_disc.py`, replacing the current `_try_aacs_tier1`-then-early-return short-circuit
- The two `test_bd_disc.py` end-to-end regression tests (`test_all_playlists_under_60s`, `test_all_playlists_under_60s_with_aacs_uses_tier1`) still pass unmodified via the old `BDDisc._build()` path — Plan 04-03 must re-verify them against the new `identify_bd()`-delegated path
- No blockers

---
*Phase: 04-blu-ray-uhd-fingerprinting*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: ovid-client/tests/test_bd_identity.py
- FOUND: ovid-client/src/ovid/disc_identity.py
- FOUND: commit 0e5fa86 (test)
- FOUND: commit 828684a (feat)
