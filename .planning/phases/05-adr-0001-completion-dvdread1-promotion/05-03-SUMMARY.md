---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 03
subsystem: fingerprint
tags: [ovid-client, disc-identity, dvd, libdvdread, tdd]

# Dependency graph
requires:
  - phase: 04-blu-ray-uhd-fingerprinting
    provides: identify_bd()'s Tier-2-primary/Tier-1-alias pattern, mirrored here
provides:
  - "identify_dvd() flipped to prefer dvdread1-* as primary whenever libdvdread succeeds, with dvd1-* demoted to the sole alias"
  - "Byte-identical dvd1-*-primary/zero-alias fallback when libdvdread is unavailable or returns an invalid Disc ID"
affects: [05-04-arm-payload-fix, 05-05-server-side-primary-selection, 05-06-promotion-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "identify_dvd() now mirrors identify_bd()'s Tier-2-primary/Tier-1-alias shape exactly: always compute the Tier-1 (dvd1) identity first, attempt Tier-2 (dvdread1) opportunistically, flip primary/alias only on Tier-2 success, never touch the fallback branches"

key-files:
  created: []
  modified:
    - ovid-client/src/ovid/disc_identity.py
    - ovid-client/tests/test_disc_identity.py

key-decisions:
  - "identify_dvd() flip closes RESEARCH.md Open Question #1 and D-03: dvdread1-* becomes client-computed primary whenever libdvdread succeeds; dvd1-* demoted to sole alias"
  - "libdvdread_identity()'s hex-validation ValueError must be raised and caught inside the SAME try block as read_libdvdread_disc_id() — moving it outside (as first drafted) let the invalid-hex path raise uncaught; fixed during GREEN (Rule 1)"

patterns-established:
  - "Tier-2-primary/Tier-1-alias flip pattern for DVD identity, matching the BD/UHD precedent from Phase 4"

requirements-completed: [IDENT-03]

coverage:
  - id: D1
    description: "identify_dvd() returns dvdread1-* as primary and dvd1-* as sole alias when libdvdread succeeds"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_disc_identity.py#test_identify_dvd_prefers_dvdread1_primary_when_available"
        status: pass
    human_judgment: false
  - id: D2
    description: "identify_dvd() falls back to dvd1-* primary with zero aliases when libdvdread is unavailable or returns an invalid Disc ID (unchanged behavior)"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "ovid-client/tests/test_disc_identity.py#test_identify_dvd_falls_back_when_libdvdread_is_unavailable"
        status: pass
      - kind: unit
        ref: "ovid-client/tests/test_disc_identity.py#test_identify_dvd_rejects_invalid_libdvdread_disc_id"
        status: pass
      - kind: integration
        ref: "ovid-client/tests/test_disc.py (all cases, unmodified)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 3: Flip identify_dvd() to prefer dvdread1-* primary Summary

**identify_dvd() now returns dvdread1-* as client-computed primary whenever libdvdread succeeds (dvd1-* demoted to sole alias), mirroring identify_bd()'s Tier-2-primary/Tier-1-alias pattern, with the dvd1-*-primary/zero-alias fallback byte-identical to prior behavior.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-06T21:24:40Z
- **Completed:** 2026-07-06T21:29:55Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- `identify_dvd()` in `ovid-client/src/ovid/disc_identity.py` flipped: `dvd1_identity` is always computed first (unchanged); on `read_libdvdread_disc_id()` success, `dvdread1_identity` becomes primary with `dvd1_identity` as the sole alias
- Fallback paths (libdvdread unavailable → `LibdvdreadError`; invalid Disc ID hex → `ValueError`) return `dvd1-*` primary with zero aliases, exactly as before — verified via the two unchanged failure-path tests
- `test_identify_dvd_keeps_ovid_dvd1_primary_in_phase_one` rewritten to `test_identify_dvd_prefers_dvdread1_primary_when_available`, asserting the new primary/alias shape
- Confirmed `Disc.from_path()` (`ovid-client/src/ovid/disc.py`) required zero changes — it consumes `identity_set.primary.fingerprint` generically
- Confirmed via grep that no other `ovid-client` source file assumes `identify_dvd()`'s primary is always `dvd1-*` — blast radius fully contained to `disc_identity.py` and its test file
- Full `ovid-client` suite green: 242 passed, 0 failed, 16 skipped (`real_disc` hardware-marker tests, expected without a physical disc)

## Task Commits

TDD RED/GREEN cycle, committed atomically:

1. **RED — rewrite success-path test to assert new dvdread1-primary behavior** - `e770aab` (test)
2. **GREEN — flip identify_dvd() to prefer dvdread1-* primary** - `3479f4f` (feat)

**Plan metadata:** commit pending (docs: complete plan)

## Files Created/Modified
- `ovid-client/src/ovid/disc_identity.py` - `identify_dvd()` flipped to Tier-2-primary (dvdread1) / Tier-1-alias (dvd1) shape; fallback branches unchanged
- `ovid-client/tests/test_disc_identity.py` - success-path test renamed/rewritten to assert new primary/alias assignment; the two failure-path tests confirmed unchanged

## Decisions Made
- Followed the plan's exact action: compute `dvd1_identity` unconditionally first, attempt `read_libdvdread_disc_id()`, build `dvdread1_identity` on success and flip primary/alias, otherwise return the unchanged `dvd1-*`-primary/zero-alias fallback with existing diagnostic codes
- Chose to move `libdvdread_identity(disc_id_hex)`'s call inside the same `try` block as `read_libdvdread_disc_id(path)` (rather than after the try/except) so its own hex-validation `ValueError` is caught by the same `except ValueError` branch — see Deviations below

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `libdvdread_identity()`'s ValueError escaped the exception handler in the first draft**
- **Found during:** Task 1 GREEN verification (`pytest tests/test_disc_identity.py tests/test_disc.py`)
- **Issue:** The initial implementation called `read_libdvdread_disc_id(path)` inside the `try` block but called `libdvdread_identity(disc_id_hex)` (which raises `ValueError` on invalid hex) *after* the try/except, so `test_identify_dvd_rejects_invalid_libdvdread_disc_id`'s `"not-hex"` case raised uncaught instead of hitting the `except ValueError` branch.
- **Fix:** Moved `dvdread1_identity = libdvdread_identity(disc_id_hex)` inside the same `try` block as `read_libdvdread_disc_id(path)`, so both the disc-ID-read failure and the hex-validation failure converge on the identical `except ValueError` / `except LibdvdreadError` handling — matching the plan's specified behavior exactly.
- **Files modified:** `ovid-client/src/ovid/disc_identity.py`
- **Verification:** `pytest tests/test_disc_identity.py tests/test_disc.py -v` → 15 passed; full suite → 242 passed, 0 failed, 16 skipped
- **Committed in:** `3479f4f` (GREEN commit, same commit — caught before commit, not a separate fix commit)

---

**Total deviations:** 1 auto-fixed (1 bug, caught during GREEN verification before commit)
**Impact on plan:** Necessary correctness fix to make the plan's specified exception-handling shape actually converge as intended. No scope creep — contained entirely within `identify_dvd()`.

## Issues Encountered
None beyond the auto-fixed issue above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `identify_dvd()`'s client-side flip is complete and isolated to `ovid-client`; `disc.fingerprint` (as sent by any caller, including ARM's bare-fingerprint auto-register path) is now `dvdread1-*` whenever computable
- Ready for Plan 05-04 (ARM payload fix to also send `fingerprint_aliases`) and Plan 05-05 (server-side `_select_primary()` — the server never blindly trusts the client's declared primary, per D-03 belt-and-suspenders)
- No blockers

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*
