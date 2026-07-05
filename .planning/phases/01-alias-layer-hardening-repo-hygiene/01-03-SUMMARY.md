---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 03
subsystem: api
tags: [fastapi, sqlalchemy, sqlite, postgresql, integrity-error, savepoint, state-machine, disc-identity]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene (plan 01)
    provides: api/app/verification.py — verify()/flag_dispute()/resolve_dispute()/VerificationTransitionError, the guarded state machine wired into routes in this plan
  - phase: 01-alias-layer-hardening-repo-hygiene (plan 02)
    provides: api/app/disc_identity.py's begin_nested()/IntegrityError/re-resolve savepoint pattern, mirrored here for the disc-row insert
provides:
  - All five inline disc.status mutations in api/app/routes/disc.py replaced with verify()/flag_dispute()/resolve_dispute() calls; flag_dispute is now the sole writer of status="disputed" across api/app/
  - VERIFY-02 crit #4 closed: a mismatched submission against an already-verified disc stays verified (200 + audit DiscEdit), never silently flips to disputed
  - IDENT-02 extended to the disc-row insert: submit_disc and register_disc savepoint-guard their new-Disc inserts and converge to the true winner on a losing race instead of splitting
affects: [phase-05 (write-concurrency work), ADR-0001 phase-3 dvdread1-* promotion (alias + disc-row race hardening both now landed)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Domain exception raised in a service module, caught at the route boundary and translated to the standard JSON error envelope (VerificationTransitionError -> 403/409, mirrors DiscIdentityConflict)"
    - "Shared _handle_existing_disc / _handle_existing_registered_disc helpers reused by both the up-front duplicate check and the disc-row losing-race recovery path, so the race-recovery branch gets identical auto-verify/dispute semantics for free"
    - "db.begin_nested() SAVEPOINT wraps release+disc creation together (not just the disc row) so a losing race unwinds both, never leaking an orphaned Release row"

key-files:
  created: []
  modified:
    - api/app/routes/disc.py
    - api/tests/test_disc_submit.py
    - api/tests/test_dispute.py
    - api/tests/conftest.py

key-decisions:
  - "Renamed the POST /v1/disc/{fingerprint}/resolve route handler from resolve_dispute to resolve_dispute_endpoint to free the resolve_dispute name for import from app.verification (URL path is unaffected — only the Python identifier changed)"
  - "A2 contract (open question, confirmed): a mismatched submission against a verified disc records an audit DiscEdit (edit_type=\"dispute_attempted\"), stays verified, and returns HTTP 200 with an explicit message — never disputed, never a silent no-op"
  - "submit_disc's release-match auto-verify branch always returns a message containing \"auto-verified\" and status \"verified\" regardless of verify()'s bool return, but creates a DiscEdit ONLY when verify() actually transitioned (True) — preserving Pitfall 4's distinction between this path's always-auto-verified UX and verify_disc's idempotent-200/no-edit contract"
  - "Included the Release creation inside submit_disc's disc-row insert SAVEPOINT (plan only specified the Disc insert) — a losing race must unwind both together or the Release row leaks as an orphan with no associated disc; this is a correctness fix (Rule 1), not scope creep"
  - "seed_test_disc gained a status kwarg (default \"verified\", unchanged) so tests can seed an unverified disc for the legitimate unverified->disputed path, instead of adding a parallel seed helper"

patterns-established:
  - "Route-boundary translation of a domain state-transition exception: catch VerificationTransitionError, inspect attempted_status + submitter identity for the self-verify 403 special case, otherwise 409 invalid_state via _error_response"

requirements-completed: [VERIFY-02, IDENT-02]

coverage:
  - id: D1
    description: "All five inline disc.status mutations replaced with verify()/flag_dispute()/resolve_dispute() calls; flag_dispute is the sole writer of status=\"disputed\" across api/app/"
    requirement: "VERIFY-02"
    verification:
      - kind: unit
        ref: "grep -rnE 'status[[:space:]]*=[[:space:]]*\"disputed\"' api/app/ -> exactly one hit (api/app/verification.py:69)"
        status: pass
      - kind: integration
        ref: "cd api && python -m pytest tests/ -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "A mismatched submission against an already-verified disc stays verified, returns 200, and records an audit DiscEdit — never silently flips to disputed (VERIFY-02 crit #4 / A2)"
    requirement: "VERIFY-02"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestDiscSubmitAutoVerify::test_mismatched_submission_against_verified_disc_stays_verified"
        status: pass
    human_judgment: false
  - id: D3
    description: "A mismatched submission against an unverified disc still moves it to disputed via the legitimate flag_dispute path"
    requirement: "VERIFY-02"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestDiscSubmitErrors::test_submit_duplicate_fingerprint_conflicting_metadata"
        status: pass
      - kind: integration
        ref: "api/tests/test_disc_submit.py::TestDiscSubmitAutoVerify::test_duplicate_conflicting_metadata_disputes"
        status: pass
      - kind: integration
        ref: "api/tests/test_dispute.py::TestSubmitStoresConflictData::test_submit_stores_conflict_data"
        status: pass
    human_judgment: false
  - id: D4
    description: "verify_disc preserves idempotent-200/no-extra-edit on already-verified, and 403 on self-verify — no regression from wiring in verify()"
    requirement: "VERIFY-02"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_verify.py::TestVerifyDisc::test_verify_already_verified_idempotent"
        status: pass
      - kind: integration
        ref: "api/tests/test_disc_verify.py::TestVerifyDisc::test_verify_already_verified_no_extra_edit"
        status: pass
      - kind: integration
        ref: "api/tests/test_disc_verify.py::TestVerifyDisc::test_self_verify_returns_403"
        status: pass
    human_judgment: false
  - id: D5
    description: "Two submissions racing the SAME new primary fingerprint converge to one disc row (disc-row race safe), via deterministic (non-threaded) injection"
    requirement: "IDENT-02"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_submit.py::TestDiscRowRace::test_new_fingerprint_losing_race_converges_to_one_disc"
        status: pass
    human_judgment: false

duration: 30min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 03: Verification Wiring + Disc-Row Race Safety (VERIFY-02, IDENT-02) Summary

**Rewired all five inline `disc.status` mutations in `routes/disc.py` into guarded `verify()`/`flag_dispute()`/`resolve_dispute()` calls (closing the silent verified->disputed flip, VERIFY-02 crit #4) and savepoint-guarded the disc-row insert in `submit_disc`/`register_disc` to converge losing races to a single row (IDENT-02).**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-07-05
- **Tasks:** 3/3 completed
- **Files modified:** 4 (0 created, 4 modified)

## Accomplishments

- Imported `verify`, `flag_dispute`, `resolve_dispute`, `VerificationTransitionError` from `app.verification` into `routes/disc.py`; renamed the `/resolve` route handler to `resolve_dispute_endpoint` to free the `resolve_dispute` name.
- `resolve_dispute_endpoint` (lines 241/245 mutations) now delegates to `verification.resolve_dispute()`, catching `VerificationTransitionError` -> 409 `invalid_state`.
- Extracted `_handle_existing_disc()` from `submit_disc`'s duplicate-submission branch (lines 422/444 mutations): matching metadata calls `verify()` (edit created only when it actually transitions); mismatched metadata calls `flag_dispute()` — when it refuses (disc already verified), the disc stays verified, an audit `DiscEdit` (`edit_type="dispute_attempted"`) is recorded, and the response is 200 with an explicit message, never disputed (A2 / crit #4).
- `verify_disc` (line 616 mutation) now calls `verify()`, branching on its bool return to preserve the idempotent-200/no-`DiscEdit` (already-verified) vs. 403 (self-verify) contracts.
- Savepoint-guarded the new-`Disc` insert in both `submit_disc` (together with its `Release` insert, to avoid leaking an orphaned release on a losing race) and `register_disc`, catching `sqlalchemy.exc.IntegrityError` specifically, `db.expire_all()`-ing the stale identity map, and re-resolving via `resolve_existing_disc_for_identities` to the true winner — extracted `_handle_existing_registered_disc()` so the race-recovery path in `register_disc` reuses the same duplicate-handling logic as the up-front check.
- `seed_test_disc` in `conftest.py` gained an optional `status` kwarg (default `"verified"`, unchanged for existing callers) so tests can seed an explicitly unverified disc for the legitimate dispute path.
- Rewrote the two behavior-change tests that previously encoded the silent-flip bug (`test_submit_duplicate_fingerprint_conflicting_metadata`, `test_duplicate_conflicting_metadata_disputes`) plus `test_dispute.py::test_submit_stores_conflict_data` to seed unverified discs; added `test_mismatched_submission_against_verified_disc_stays_verified` and `TestDiscRowRace::test_new_fingerprint_losing_race_converges_to_one_disc` (deterministic monkeypatch injection, no threading/asyncio, restored in `finally`).
- Confirmed RED against pre-fix `routes/disc.py` (both new tests failed for the expected reasons: silent flip to disputed; unguarded `IntegrityError` -> 500), then GREEN after Task 2 (status wiring) and Task 3 (race-safety) respectively. Full `api/tests/` suite: 254 passed, 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Rewrite the behavior-change tests to the guarded dispute contract** - `a157325` (test)
2. **Task 2 (GREEN): Replace the 5 inline status mutations with verification.py calls + catch VerificationTransitionError** - `520bb72` (feat)
3. **Task 3 (GREEN): Wrap the disc-row insert in submit_disc/register_disc with savepoint + IntegrityError re-resolve (IDENT-02)** - `5ffef92` (feat)

_TDD gate sequence confirmed in git log: test(01-03) -> feat(01-03) -> feat(01-03), in that order._

## Files Created/Modified

- `api/app/routes/disc.py` - Five inline status mutations replaced with `verify()`/`flag_dispute()`/`resolve_dispute()` calls; `resolve_dispute` route renamed to `resolve_dispute_endpoint`; new `_handle_existing_disc()` / `_handle_existing_registered_disc()` helpers; disc-row inserts in `submit_disc`/`register_disc` savepoint-guarded against `IntegrityError`
- `api/tests/test_disc_submit.py` - Two tests re-seeded unverified; added `test_mismatched_submission_against_verified_disc_stays_verified` and `TestDiscRowRace`
- `api/tests/test_dispute.py` - `test_submit_stores_conflict_data` re-seeded unverified
- `api/tests/conftest.py` - `seed_test_disc` gained a `status` kwarg (default `"verified"`)

## Decisions Made

- Renamed the `/resolve` route handler function (not the URL) to resolve the `resolve_dispute` name collision between the route and the imported `app.verification.resolve_dispute` function.
- A2 contract implemented as: audit `DiscEdit` with `edit_type="dispute_attempted"`, HTTP 200, message explicitly stating the disc remains verified — never a 200 that reports `"disputed"`.
- Included `Release` creation inside `submit_disc`'s disc-row-insert SAVEPOINT even though the plan's `<action>` text only mentioned wrapping the `Disc` insert — a losing race that rolled back only the `Disc` row would leave an orphaned, disc-less `Release` row committed alongside the race-recovery response. Wrapping both together in the same savepoint closes that leak. (Rule 1 — correctness fix, not scope creep.)
- Kept the coarse role gate (`current_user.role not in (...)`) at the route in `resolve_dispute_endpoint`, per D-11 — only the transition legality check moved into `verification.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Scoped the disc-row insert SAVEPOINT to include the Release creation, not just the Disc row**
- **Found during:** Task 3 (GREEN), while designing the savepoint wrap for `submit_disc`
- **Issue:** The plan's `<action>` described wrapping only `db.add(disc); db.flush()` in the savepoint. `submit_disc` creates and flushes a `Release` row *before* the `Disc` row in the same code path; if only the `Disc` insert were savepoint-scoped, a losing race would roll back just the `Disc` insert while the already-flushed `Release` row survived in the outer transaction — and the race-recovery path (`_handle_existing_disc`) would then `db.commit()` that orphaned, disc-less `Release` row as a side effect.
- **Fix:** Wrapped both the `Release` creation and the `Disc` creation together inside the single `db.begin_nested()` block in `submit_disc`, so a losing race on the `Disc` insert cleanly unwinds the `Release` insert too.
- **Files modified:** `api/app/routes/disc.py`
- **Verification:** `TestDiscRowRace::test_new_fingerprint_losing_race_converges_to_one_disc` passes; full suite green (254 passed).
- **Committed in:** `5ffef92` (Task 3 commit)

**2. [Rule 3 - Blocking] Added a `status` kwarg to `seed_test_disc` in conftest.py**
- **Found during:** Task 1 (RED), while rewriting the behavior-change tests
- **Issue:** `seed_test_disc` hardcoded `status="verified"`, but Task 1 requires seeding explicitly unverified discs to keep the legitimate `unverified->disputed` tests meaningful, per the plan's own `<read_first>` guidance ("pass an explicit unverified-status keyword to `seed_test_disc`, or add a `seed_unverified_disc` helper"). `conftest.py` was not listed in the plan's `files_modified`, but the fixture change was necessary infrastructure to execute Task 1 as specified.
- **Fix:** Added `status: str = "verified"` parameter (backward-compatible default), threaded through to the `Disc(...)` constructor.
- **Files modified:** `api/tests/conftest.py`
- **Verification:** All existing callers of `seed_test_disc`/`seeded_disc`/`seeded_disc_with_owner` fixtures unaffected (default unchanged); full suite green.
- **Committed in:** `a157325` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 correctness fix — Rule 1; 1 necessary test infrastructure — Rule 3).
**Impact on plan:** Both deviations were required to satisfy the plan's own stated intent (A2 contract's "no leaked state" implication, and the plan's own `<read_first>` guidance for Task 1). No scope creep beyond what was needed for VERIFY-02/IDENT-02.

## Issues Encountered

None beyond the deviations documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `flag_dispute` is now the sole writer of `status="disputed"` across `api/app/`; any future dispute-related code must route through `app.verification`, not a direct assignment.
- Both the alias-insert race (Plan 02) and the disc-row-insert race (this plan) are now closed under `gunicorn -w 4` concurrent workers, satisfying the `[Phase 1 -> Phase 5]` blocker noted in Plan 02's summary — IDENT-02 is now fully resolved across both write paths.
- No blockers for subsequent plans in this phase (Plan 04 — alias exposure in lookup responses — has no dependency on this plan's internals beyond the shared `routes/disc.py` file).

---
*Phase: 01-alias-layer-hardening-repo-hygiene*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: api/app/routes/disc.py
- FOUND: api/tests/test_disc_submit.py
- FOUND: api/tests/test_dispute.py
- FOUND: api/tests/conftest.py
- FOUND: .planning/phases/01-alias-layer-hardening-repo-hygiene/01-03-SUMMARY.md
- FOUND commit: a157325
- FOUND commit: 520bb72
- FOUND commit: 5ffef92
