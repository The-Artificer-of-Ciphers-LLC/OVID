---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 05
subsystem: api
tags: [fastapi, sqlalchemy, sqlite, fingerprint, concurrency, disc-identity]

# Dependency graph
requires:
  - phase: 05-adr-0001-completion-dvdread1-promotion (Plan 01)
    provides: "FingerprintRegistry ORM model + register_fingerprint(db, fingerprint, disc_id) helper, contractually invoked inside the caller's own db.begin_nested() savepoint (WR-02)."
provides:
  - "_select_primary(fingerprint, aliases) — pure server-side primary-selection helper colocated with _method_of() in api/app/routes/disc.py"
  - "register_disc/submit_disc's new-disc creation SAVEPOINTs now select the dvdread1-* primary when present and register it in the WR-02 fingerprint_registry"
  - "Explicit mixed-fleet zero-fragmentation regression test proving an old client's dvd1-* resubmission can never demote an already-promoted disc"
affects: [05-06, 05-07]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Server-side hybrid primary selection at first-insert time (D-03): a pure candidate-selection function is called once inside the new-disc SAVEPOINT, before the domain row is constructed, so both the persisted primary and the WR-02 registry entry are chosen consistently in the same atomic unit as the insert."]

key-files:
  created: []
  modified:
    - api/app/routes/disc.py
    - api/tests/test_disc_submit.py
    - api/tests/test_disc_identity_aliases.py

key-decisions:
  - "_select_primary() is a pure function taking (fingerprint, aliases) and returning (primary, remaining_aliases) — it never touches the DB or the request object, keeping it directly unit-testable without HTTP/TestClient plumbing"
  - "register_fingerprint() call for the new-disc primary is placed inside the SAME db.begin_nested() block as the Disc insert (after its own db.flush()), followed by a second db.flush() — mirroring the exact insert-first/flush pattern already used for aliases in attach_lookup_aliases(), so a losing race on either UNIQUE constraint rolls back atomically together (T-05-12)"
  - "attach_lookup_aliases() for both routes is now called with (primary_fp, alias_fps) instead of (body.fingerprint, body.fingerprint_aliases) — the demoted candidate is attached as a Lookup Alias rather than re-declared against the client's original (now non-primary) fingerprint string"
  - "Disc.fingerprint immutability on every existing-disc code path was NOT touched by this plan — confirmed by the mixed-fleet regression test passing even before Task 2's wiring landed, proving the invariant was already structurally sound and this plan's job was purely to add correct NEW-disc selection logic"

patterns-established:
  - "Select-then-construct: any future server-side normalization of submitted identity strings should run as a pure helper immediately before the domain row is constructed inside its creation SAVEPOINT, not after — so the registry registration and the persisted row are always consistent with the same selection decision"

requirements-completed: [IDENT-04]

coverage:
  - id: D1
    description: "_select_primary() correctly prefers a dvdread1-* candidate among fingerprint+aliases (promoting it), passes through unchanged when already primary or when absent, and is unaffected by unrelated BD aliases"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_submit.py::TestSelectPrimary (4 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "New-disc submissions via both POST /v1/disc and POST /v1/disc/register prefer a dvdread1-* candidate as the persisted primary, with the demoted dvd1-* candidate stored as a Lookup Alias"
    requirement: "IDENT-04"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestSelectPrimaryWiring::test_submit_disc_prefers_dvdread1_primary_on_new_disc"
        status: pass
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestSelectPrimaryWiring::test_register_disc_prefers_dvdread1_primary_on_new_disc"
        status: pass
    human_judgment: false
  - id: D3
    description: "Mixed-fleet zero-fragmentation guarantee: an old client resubmitting dvd1-* as its declared primary against an already-promoted (dvdread1-* primary) disc can never demote it back to dvd1-*"
    requirement: "IDENT-04"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestSelectPrimaryWiring::test_old_client_resubmit_cannot_demote_promoted_disc"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full api/ test suite remains green after the wiring change, including the pre-existing test_disc_submit.py classes and IDENT-02/VERIFY-01..04 regressions"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/ full suite (349 passed)"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 5: Server-Side Hybrid Primary Selection (D-03) Summary

**Added `_select_primary()` so the server — not the client — picks `dvdread1-*` as the primary fingerprint on new-disc submissions, wired it plus `register_fingerprint()` into both `register_disc`/`submit_disc` new-disc SAVEPOINTs, and proved the mixed-fleet zero-fragmentation guarantee with an explicit regression test.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-06T18:04:39-04:00
- **Completed:** 2026-07-06T18:08:36-04:00
- **Tasks:** 2 completed
- **Files modified:** 3 (1 modified — routes/disc.py, 2 test files)

## Accomplishments
- Added `_select_primary(fingerprint, aliases) -> tuple[str, list[str]]` in `api/app/routes/disc.py`, colocated with `_method_of()`. Pure function, no DB/HTTP dependency, directly unit-tested with 4 cases (promote, already-primary no-op, absent no-op, unrelated-BD-alias-doesn't-disturb-preference).
- Wired `_select_primary()` + `register_fingerprint()` into `register_disc`'s and `submit_disc`'s new-disc creation SAVEPOINTs: the chosen primary constructs the `Disc` row, is registered in the WR-02 `fingerprint_registry` inside the same savepoint, and the demoted candidate flows through as a Lookup Alias via `attach_lookup_aliases(db, disc, primary_fp, alias_fps)`.
- Proved the D-03 mixed-fleet zero-fragmentation guarantee with `test_old_client_resubmit_cannot_demote_promoted_disc`: an old client resubmitting `dvd1-already-promoted` (a stale dvd1-primary belief) against a disc already promoted to `dvdread1-already-promoted` primary auto-verifies (200) without ever demoting `Disc.fingerprint` back to `dvd1-*`.
- Full `api/` test suite green: 349 passed (342 pre-existing + 7 new: 4 `TestSelectPrimary` + 3 `TestSelectPrimaryWiring`).

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: `_select_primary()` pure function** - `cc7dec7` (test, RED — combined with Task 2's RED tests in one commit since both were added before any implementation) → `daa9142` (feat, GREEN)
2. **Task 2: Wire into register_disc/submit_disc + mixed-fleet regression** - `30034de` (feat, GREEN — wiring + pre-existing-test fixture fix)

_TDD gate sequence confirmed: `cc7dec7` (test) precedes `daa9142` (feat) precedes `30034de` (feat) in git log — RED then GREEN. No REFACTOR commit was needed. Both tasks' tests were authored in the single `cc7dec7` RED commit (collection failed on the not-yet-existing `_select_primary` import, which is a valid RED state covering both tasks); each task's corresponding implementation commit turned its subset of tests GREEN, verified independently before committing (`TestSelectPrimary` -k filter after `daa9142`, `TestSelectPrimaryWiring`/`Wiring` -k filter after `30034de`)._

## Files Created/Modified
- `api/app/routes/disc.py` - Added `_select_primary()` helper; imported `register_fingerprint`; wired both into `register_disc`'s and `submit_disc`'s new-disc SAVEPOINTs; updated both routes' post-savepoint `attach_lookup_aliases()` calls to use the selected primary/alias split
- `api/tests/test_disc_submit.py` - Added `TestSelectPrimary` (4 unit tests) and `TestSelectPrimaryWiring` (3 integration tests, including a local `_seed_promoted_disc()` helper mirroring `seed_test_disc`'s structure with dvdread1-/dvd1-prefixed fingerprints)
- `api/tests/test_disc_identity_aliases.py` - Renamed a stale fixture alias (`dvdread1-submit-alias` → `bd1-submit-alias`) whose original assumption (client-declared `dvd1-*` primary always wins) was invalidated by the new D-03 behavior

## Decisions Made
- `_select_primary()` kept as a pure function with no DB/session dependency, enabling direct unit testing without TestClient/HTTP overhead for Task 1.
- `register_fingerprint()` for the new-disc primary is invoked inside the same `db.begin_nested()` block as the `Disc` insert (after `db.flush()` for `disc.id`, followed by its own `db.flush()`) — reusing the exact insert-first/flush idiom already established for aliases in `attach_lookup_aliases()` (Plan 05-01), so a losing race on either UNIQUE constraint (`discs.fingerprint` or `fingerprint_registry.fingerprint`) rolls back the whole savepoint atomically.
- Confirmed (via the mixed-fleet test passing even before Task 2's wiring landed) that `Disc.fingerprint` immutability on every existing-disc code path was already structurally sound — this plan's entire behavioral surface is the NEW-disc creation branch's selection logic, matching the plan's stated purpose exactly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stale test fixture assumption invalidated by new D-03 behavior**
- **Found during:** Task 2 (full suite verification after wiring)
- **Issue:** `test_disc_identity_aliases.py`'s shared `VALID_PAYLOAD` submitted `fingerprint="dvd1-submit-primary"` with `fingerprint_aliases=["dvdread1-submit-alias"]` on a NEW-disc submission — exactly the case D-03 now correctly flips (server prefers the dvdread1-* candidate). Two tests (`test_submit_stores_alias_and_lookup_returns_primary`, `test_edits_accepts_alias_and_returns_primary`) asserted the old pre-D-03 behavior (client-declared primary always wins), which is now incorrect.
- **Fix:** Renamed the alias fixture from `dvdread1-submit-alias` to a neutral `bd1-submit-alias` (a different, non-`dvdread1` identity method prefix) across the file. This test's actual intent — proving alias storage/lookup/edits mechanics work regardless of which specific fingerprint is primary — is unaffected by the rename and no longer accidentally exercises D-03's preference logic.
- **Files modified:** `api/tests/test_disc_identity_aliases.py`
- **Verification:** Full `api/` suite green (349 passed) after the rename
- **Committed in:** `30034de` (part of Task 2's GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug — stale test fixture)
**Impact on plan:** Necessary to satisfy the plan's own acceptance criterion ("the full existing api/tests/ suite remains green"). No scope creep — the fix only touched fingerprint string literals in an unrelated pre-existing test file, not its assertions' intent.

## Issues Encountered
None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `_select_primary()` and the D-03 server-side primary-selection contract are now live on both new-disc creation routes, ready for any subsequent plan (05-06, 05-07) that touches the promotion/backfill or cutover-operability work.
- The mixed-fleet zero-fragmentation guarantee is now proven by an explicit, permanent regression test — future changes to `register_disc`/`submit_disc`/`_handle_existing_disc` that risk reintroducing a `Disc.fingerprint` reassignment on the existing-disc path will be caught by `test_old_client_resubmit_cannot_demote_promoted_disc`.
- No blockers.

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*

## Self-Check: PASSED
