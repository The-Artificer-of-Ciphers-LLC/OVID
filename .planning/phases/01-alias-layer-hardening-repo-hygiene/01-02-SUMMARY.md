---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 02
subsystem: api
tags: [sqlalchemy, postgresql, sqlite, integrity-error, savepoint, concurrency, disc-identity]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene (plan 01)
    provides: api/app/verification.py (verification state machine) — unrelated module, no direct dependency, but shares the phase's file-scope discipline
provides:
  - Race-safe attach_lookup_aliases in api/app/disc_identity.py — insert-first / catch IntegrityError / re-resolve-the-winner, each insert scoped to its own SAVEPOINT
  - Deterministic losing-race regression suite in api/tests/test_disc_identity_race.py (no threading/asyncio — injects the losing state directly)
affects: [phase-01-plan-03 (disc-row insert reuses this convergence pattern), phase-05 (write-concurrency work depends on this landing first)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Insert-first / catch sqlalchemy.exc.IntegrityError / re-resolve-the-winner, replacing check-then-add TOCTOU"
    - "Per-insert db.begin_nested() SAVEPOINT scoping so one losing insert rolls back only itself, not sibling inserts or the outer transaction"
    - "db.expire_all() after a caught IntegrityError to discard the stale identity map before re-resolving"
    - "Deterministic race injection in tests (pre-inserted conflict row, or monkeypatched resolve to report a false negative) instead of threading/asyncio.gather against a StaticPool SQLite harness"

key-files:
  created:
    - api/tests/test_disc_identity_race.py
  modified:
    - api/app/disc_identity.py

key-decisions:
  - "D-01/D-02/D-03 (carried from CONTEXT.md/RESEARCH.md): unique-constraint + catch-IntegrityError + re-resolve is the ONLY IDENT-02 fix regression-testable on the in-memory SQLite harness; advisory locks / SELECT FOR UPDATE / SERIALIZABLE+retry are Postgres-only and silently no-op on SQLite"
  - "Each alias insert gets its own db.begin_nested() SAVEPOINT so a losing race unwinds only that alias — sibling aliases already committed in the same submission survive"
  - "A caught IntegrityError whose re-resolve unexpectedly returns None is NOT swallowed — it re-raises the original IntegrityError (no-wave-off rule); this is a genuinely-unexpected state, not a legitimate race outcome"
  - "Corrected two of the initially-drafted race tests: the plan's monkeypatch recipe (return None on resolve_disc_identity's first call) targeted the OLD pre-insert-check call shape; the NEW insert-first code only calls resolve_disc_identity once (post-conflict, inside the except handler), so the tests were re-targeted at that actual call site — exercising the 'genuinely unexpected, re-raise' branch instead of a scenario the new code no longer has"

patterns-established:
  - "Concurrent-worker write races on a UNIQUE-constrained column: attempt the insert first inside a SAVEPOINT, catch IntegrityError, discard stale ORM state, then re-resolve to the actual winner — do not read-then-write"

requirements-completed: [IDENT-02]

coverage:
  - id: D1
    description: "A losing-race alias insert catches IntegrityError, re-resolves, and converges to the winning disc — no duplicate/split alias row"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_race.py::TestAliasLosingRacePreInserted::test_own_disc_already_owns_alias_converges_no_duplicate"
        status: pass
    human_judgment: false
  - id: D2
    description: "One alias losing the race inside a multi-alias submission does NOT roll back sibling aliases already inserted (savepoint scope)"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_race.py::TestSiblingAliasSurvivesSavepointScope::test_sibling_alias_insert_survives_losing_race"
        status: pass
    human_judgment: false
  - id: D3
    description: "A genuine cross-disc alias collision still raises DiscIdentityConflict (→ 409), not swallowed"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_race.py::TestAliasLosingRacePreInserted::test_cross_disc_collision_still_raises_conflict"
        status: pass
    human_judgment: false
  - id: D4
    description: "No stale identity-map / PendingRollbackError state after a caught IntegrityError; a subsequent resolve returns the winner cleanly"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_race.py::TestNoStaleSessionStateAfterCaughtConflict::test_subsequent_resolve_after_conflict_is_clean"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 02: Alias Write-Path Race Hardening (IDENT-02) Summary

**Restructured `attach_lookup_aliases` from check-then-add TOCTOU to insert-first / catch-`IntegrityError` / re-resolve-the-winner, each insert scoped to its own `db.begin_nested()` SAVEPOINT, closing the concurrent-gunicorn-worker split/duplicate-pressing race.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-05
- **Tasks:** 3/3 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments

- Replaced the TOCTOU read-then-`db.add()` pattern in `api/app/disc_identity.py`'s `attach_lookup_aliases` with an insert-first flow: each alias insert runs inside its own `db.begin_nested()` SAVEPOINT with an explicit `db.flush()` so a UNIQUE-constraint violation surfaces immediately, scoped to just that alias.
- On a caught `sqlalchemy.exc.IntegrityError` (caught specifically, never bare `Exception`), `db.expire_all()` discards the stale ORM identity map left by the rolled-back savepoint, then re-resolves the fingerprint to find the actual winning disc — converging to a single alias row instead of a split/duplicate pressing.
- Preserved `DiscIdentityConflict` (→ 409) for genuine cross-disc collisions, and added a defensive re-raise for the genuinely-unexpected case where the post-conflict re-resolve unexpectedly finds nothing (no-wave-off rule — never silently swallowed).
- Added `api/tests/test_disc_identity_race.py`: five deterministic tests covering same-disc idempotent convergence, cross-disc conflict preservation, sibling-alias survival under savepoint scope, and clean session state after a caught conflict — none use `threading`/`asyncio.gather` (the in-memory `StaticPool` SQLite harness serializes those trivially and proves nothing per 01-RESEARCH.md "Pitfall 1").
- Confirmed RED against the pre-fix code (verified by temporarily reverting `disc_identity.py` and re-running — the reverted-code run failed on the sibling-survival assertion), then GREEN after the restructure, with the full `disc_identity_race` + `disc_identity_aliases` suites (12 tests) and the entire `api/tests/` suite (251 tests) passing.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Write deterministic losing-race regression tests** - `83c611c` (test)
2. **Task 2 (GREEN): Restructure attach_lookup_aliases to insert-first / catch / re-resolve in savepoints** - `c2afd98` (feat)
3. **Task 3 (REFACTOR): Confirm savepoint scope + full identity suite green** - `e26aa46` (refactor)

_TDD gate sequence confirmed in git log: test(01-02) → feat(01-02) → refactor(01-02), in that order._

## Files Created/Modified

- `api/tests/test_disc_identity_race.py` - Deterministic race regression suite (5 tests, no threading/asyncio.gather)
- `api/app/disc_identity.py` - `attach_lookup_aliases` restructured to insert-first / catch `IntegrityError` / re-resolve inside SAVEPOINT scope; imports `sqlalchemy.exc.IntegrityError`

## Decisions Made

- Kept `attach_lookup_aliases`'s public signature unchanged (per plan) — Plan 03's disc-row insert can reuse the same convergence pattern without touching this function's callers.
- Did not extract a separate shared helper for the insert-savepoint-catch-reresolve shape; the loop body is small enough to stay inline for this plan's scope. (Plan 03 can extract if the disc-row insert needs an identical shape and duplication becomes a real concern.)
- Chose to re-raise the original `IntegrityError` (rather than converting to a generic error or `DiscIdentityConflict`) when a post-conflict re-resolve unexpectedly returns `None` — this is an explicitly "genuinely unexpected" state per the plan's spec, not a legitimate race outcome, so surfacing the original error (not swallowing it) is correct per the no-wave-off rule.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in test design] Corrected two race tests whose monkeypatch scenario didn't map onto the new insert-first code shape**
- **Found during:** Task 2 (GREEN), while verifying the RED tests turned green
- **Issue:** The plan's `<action>` for Task 1 offered two equivalent injection techniques — pre-insert the conflicting row, OR monkeypatch `resolve_disc_identity` to return `None` on its first call (simulating a stale pre-insert check). That second technique was written against the OLD check-then-add code, where `resolve_disc_identity` runs as a pre-insert check. The restructured (GREEN) code has no such pre-check — `resolve_disc_identity` is called exactly once per alias, and only inside the `except IntegrityError` handler (the re-resolve-the-winner step). Mocking that single call to always return `None` therefore didn't simulate "a stale read before a real conflict exists" against the new code — it broke the only re-resolve call, which per spec should legitimately raise (re-raise the original `IntegrityError`) rather than raise `DiscIdentityConflict`, and my initial test asserted the latter.
- **Fix:** Rewrote `TestAliasLosingRaceStaleRead` to a single test (`test_reresolve_returning_none_after_genuine_conflict_reraises`) that exercises the actual "genuinely unexpected, re-raise" branch: monkeypatch `resolve_disc_identity` to always report no match despite a genuine pre-existing UNIQUE-constraint row, and assert the original `sqlalchemy.exc.IntegrityError` propagates rather than being swallowed or misclassified. Removed the now-redundant "own-disc idempotent no-op via stale read" test, since that behavior is already covered without a monkeypatch by `TestAliasLosingRacePreInserted::test_own_disc_already_owns_alias_converges_no_duplicate`.
- **Files modified:** `api/tests/test_disc_identity_race.py`
- **Verification:** Re-confirmed RED by temporarily reverting `api/app/disc_identity.py` to its pre-Task-2 content (`git checkout -- api/app/disc_identity.py`, restored from a scratch copy afterward — no commit history altered) and re-running the corrected test file: 4 passed / 1 failed (sibling-savepoint assertion), confirming the file as a whole still fails against the OLD code. Restored the Task 2 fix and re-ran: all 5 tests + the existing 7 alias tests green (12 total).
- **Committed in:** `c2afd98` (folded into the Task 2 GREEN commit, since the correction was discovered while turning RED to GREEN and the commit message documents it explicitly)

---

**Total deviations:** 1 auto-fixed (Rule 1 — test-design bug, not implementation).
**Impact on plan:** No scope creep. The correction kept the regression suite meaningful and aligned with the actual restructured code's control flow, rather than testing a scenario the fix eliminated. All four `<behavior>` bullets from the plan remain covered.

## Issues Encountered

None beyond the test-design correction documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `attach_lookup_aliases` is now race-safe under concurrent `gunicorn -w 4` workers; Plan 03 (disc-row insert race-hardening, if scoped separately) can reuse the identical insert-savepoint-catch-`IntegrityError`-reresolve shape shown in `api/app/disc_identity.py`.
- The `[Phase 1 → Phase 5]` blocker in STATE.md ("Alias write-path TOCTOU race (IDENT-02) ... MUST land before ADR 0001 Phase 3 dvdread1-* promotion") is now satisfied for the alias-insert path specifically; verification-state-machine consolidation (VERIFY-02, Plan 01) already landed. Confirm whether any remaining disc-row insert race work is still pending under a later plan in this phase before treating the full blocker as cleared.
- No blockers for subsequent plans in this phase.

---
*Phase: 01-alias-layer-hardening-repo-hygiene*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: api/tests/test_disc_identity_race.py
- FOUND: api/app/disc_identity.py
- FOUND: .planning/phases/01-alias-layer-hardening-repo-hygiene/01-02-SUMMARY.md
- FOUND commit: 83c611c
- FOUND commit: c2afd98
- FOUND commit: e26aa46
- FOUND commit: da8b571
