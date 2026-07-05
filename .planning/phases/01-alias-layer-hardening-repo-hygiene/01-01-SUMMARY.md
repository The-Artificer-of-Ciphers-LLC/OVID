---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 01
subsystem: api
tags: [sqlalchemy, fastapi, state-machine, verification, tdd]

# Dependency graph
requires: []
provides:
  - "api/app/verification.py — the single guarded writer of disc.status (verify/flag_dispute/resolve_dispute)"
  - "VerificationTransitionError domain exception mirroring DiscIdentityConflict's shape"
  - "LEGAL_TRANSITIONS frozenset encoding D-09 (disputed unreachable via the general table)"
affects: [01-02, 01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flat-function domain module (no service class, no FSM library) mirroring api/app/disc_identity.py house style"
    - "Domain exception carries structured attrs (disc_id/current_status/attempted_status) then calls super().__init__() with a human message"
    - "Idempotent bool-returning transition functions instead of raising for no-op states (Pitfall 4)"

key-files:
  created:
    - api/app/verification.py
    - api/tests/test_verification.py
  modified: []

key-decisions:
  - "verify() returns False (not an exception/400) when the disc is already verified — preserves the route layer's idempotent-200 contract (Pitfall 4)"
  - "Self-verification check lives inside verify() as a transition invariant (D-11), not in the route layer, so no future caller can bypass it"
  - "flag_dispute() is the ONLY function in the module permitted to write status=\"disputed\" — LEGAL_TRANSITIONS contains zero entries targeting disputed (D-09), closing the silent-flip bug (VERIFY-02 crit #4)"
  - "actor is accepted as a full User object everywhere, not a bare id, to lock in the Phase 2 confirmation-counting seam (D-12)"

patterns-established:
  - "Pattern: guarded state-machine modules take db: Session first, a full domain object (not an id), and a full actor object; they return bool for idempotent transitions and raise a domain exception for illegal ones."

requirements-completed: [VERIFY-02]

coverage:
  - id: D1
    description: "verify() promotes unverified→verified, is idempotent (returns False, no-op) on an already-verified disc, and raises VerificationTransitionError on self-verification"
    requirement: "VERIFY-02"
    verification:
      - kind: unit
        ref: "api/tests/test_verification.py::TestVerify"
        status: pass
    human_judgment: false
  - id: D2
    description: "flag_dispute() is the sole writer of status=\"disputed\" and refuses to touch an already-verified disc (closes the silent-flip bug)"
    requirement: "VERIFY-02"
    verification:
      - kind: unit
        ref: "api/tests/test_verification.py::TestFlagDispute"
        status: pass
    human_judgment: false
  - id: D3
    description: "resolve_dispute() supports verify/reject actions on a disputed disc, guarded by LEGAL_TRANSITIONS"
    requirement: "VERIFY-02"
    verification:
      - kind: unit
        ref: "api/tests/test_verification.py::TestResolveDispute"
        status: pass
    human_judgment: false
  - id: D4
    description: "LEGAL_TRANSITIONS has zero entries targeting \"disputed\" (D-09), structurally verified"
    requirement: "VERIFY-02"
    verification:
      - kind: unit
        ref: "api/tests/test_verification.py::TestLegalTransitions::test_no_transition_targets_disputed"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 01: Verification State Machine Summary

**Single guarded `api/app/verification.py` state machine (verify/flag_dispute/resolve_dispute) that consolidates the 5 inline `disc.status` mutations in routes/disc.py, closing the VERIFY-02 silent-flip bug where a dispute could overwrite a verified disc.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-05T18:31:25Z
- **Tasks:** 3 (RED / GREEN / REFACTOR)
- **Files modified:** 2 (1 new module, 1 new test file)

## Accomplishments

- `api/app/verification.py` created as a flat-function module (D-08) mirroring `api/app/disc_identity.py`'s exact house style: one-line docstring, module-level `LEGAL_TRANSITIONS` frozenset, `VerificationTransitionError` domain exception, no service class, no FSM library.
- `LEGAL_TRANSITIONS` encodes D-09 structurally: `{("unverified","verified"), ("disputed","verified"), ("disputed","unverified")}` — zero tuples target `"disputed"`, so `disputed` is reachable ONLY via `flag_dispute()`.
- `verify(db, disc, actor)` preserves the idempotent-200/no-edit contract (returns `False`, no write, no exception on an already-verified disc — Pitfall 4), raises `VerificationTransitionError` on self-verification (D-11) and on illegal transitions.
- `flag_dispute(db, disc, actor, reason)` is the sole writer of `status="disputed"` in the module and refuses to touch an already-`verified` disc, closing VERIFY-02 success criterion #4.
- `resolve_dispute(db, disc, actor, action)` absorbs the `routes/disc.py:240-246` resolve semantics (`action="verify"`→verified, `action="reject"`→unverified), guarded by `LEGAL_TRANSITIONS`.
- 11 unit tests in `api/tests/test_verification.py` cover every `<behavior>` bullet from the plan; none use snapshot assertions.

## Task Commits

Each task was committed atomically (TDD RED → GREEN → REFACTOR):

1. **Task 1 (RED): Write failing unit tests** - `eb49775` (test)
2. **Task 2 (GREEN): Implement api/app/verification.py** - `8093a9c` (feat)
3. **Task 3 (REFACTOR): Align conventions and lock the suite** - `95f54ba` (refactor)

_TDD gate sequence confirmed in git log: test(01-01) → feat(01-01) → refactor(01-01)._

## TDD Gate Compliance

- RED gate: `eb49775` — `test(01-01): add failing tests for verification state machine`. Verified failure was an import/collection error (`ModuleNotFoundError: No module named 'app.verification'`), not a false pass.
- GREEN gate: `8093a9c` — `feat(01-01): implement verification.py as sole disc.status writer`. All 11 tests passed after implementation.
- REFACTOR gate: `95f54ba` — `refactor(01-01): align verification.py with disc_identity.py conventions`. Tests remained green; no behavior change.

## Files Created/Modified

- `api/app/verification.py` - New module: `VerificationTransitionError`, `LEGAL_TRANSITIONS`, `verify()`, `flag_dispute()`, `resolve_dispute()`
- `api/tests/test_verification.py` - New unit test suite (11 tests) covering the full state-machine contract

## Decisions Made

- `verify()` on an already-verified disc returns `False` rather than raising or mapping to an HTTP 400 — Pitfall 4 explicitly forbids introducing a 400 for `verified→verify`; the route layer (Plan 03) is expected to translate `False` into its existing idempotent-200 response.
- The self-verification guard (D-11) is enforced inside `verify()` itself, not left to callers, so future call sites (route handlers, future Phase 2 confirmation logic) cannot accidentally bypass it.
- `flag_dispute()` was implemented as the textually sole writer of `status="disputed"` in the module; comment/docstring wording was adjusted during the REFACTOR task specifically so `grep -nE 'status\s*=\s*"disputed"' api/app/verification.py` returns exactly one hit (the actual assignment), matching the plan's acceptance criterion precisely rather than incidentally.
- Test discs are built directly via `Disc(...)` against the `db_session` fixture rather than going through the HTTP layer, since this is a pure domain-module unit test (per Task 1's `read_first` guidance to reuse `conftest.py` fixtures and avoid inventing a new harness).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] No local Python environment with API dependencies installed**
- **Found during:** Task 1 (RED verification)
- **Issue:** The project has no `.venv`/`venv` checked in and no system-wide install of `fastapi`/`pytest`/etc.; `python -m pytest` failed with `command not found: python` then `ModuleNotFoundError: No module named 'fastapi'` even after switching to `python3`.
- **Fix:** Created `api/.venv` (already covered by `.gitignore`) and installed dependencies exactly as CI does (`pip install -r requirements.txt` then `pip install pytest httpx`, per `.github/workflows/ci.yml`'s `api-tests` job) so `python -m pytest` inside the venv matches CI's install steps.
- **Files modified:** None tracked (venv is gitignored, not committed).
- **Verification:** RED test correctly failed with the expected `ModuleNotFoundError: No module named 'app.verification'`; GREEN/REFACTOR runs passed 11/11, and the full suite (246 tests) passed with the same venv.
- **Committed in:** N/A (no file changes; environment setup only, not tracked in git).

**2. [Rule 1 - Bug] Acceptance-criterion grep matched comment/docstring text, not just code**
- **Found during:** Task 3 (REFACTOR)
- **Issue:** The plan's acceptance criterion requires `grep -nE 'status\s*=\s*"disputed"' api/app/verification.py` to return exactly one line (the actual `flag_dispute` assignment). My first draft's module comment and docstring both contained the literal substring `status="disputed"` in prose, so the same grep returned 3 hits instead of 1.
- **Fix:** Reworded the comment and `flag_dispute` docstring to describe the invariant without using the exact `status="disputed"` substring (e.g., "the sole function that ever writes the disputed status").
- **Files modified:** `api/app/verification.py`
- **Verification:** `grep -nE 'status\s*=\s*"disputed"' api/app/verification.py` now returns exactly one line (line 65, the actual assignment inside `flag_dispute`).
- **Committed in:** `95f54ba` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking/environment, 1 bug/acceptance-criterion precision)
**Impact on plan:** Both fixes were necessary to actually run and verify the plan's own acceptance criteria as written. No scope creep — no behavior changes beyond what Task 3 already called for (convention alignment).

## Issues Encountered

- Full API suite (`cd api && python -m pytest tests/ -q`) passes 246/246 after this plan's changes, but emits pre-existing warnings from files this plan did not touch (`InsecureKeyLengthWarning` in `tests/test_auth.py`/`tests/test_auth_apple.py` from deliberately-short JWT test keys; a `StarletteDeprecationWarning` from the installed `httpx`/`starlette` version pairing in `fastapi/testclient.py`; a `DeprecationWarning` from `slowapi/extension.py`'s use of `asyncio.iscoroutinefunction`). These are out of this plan's file scope (`api/app/verification.py`, `api/tests/test_verification.py`) per the executor's SCOPE BOUNDARY rule and are logged in `.planning/phases/01-alias-layer-hardening-repo-hygiene/deferred-items.md` for triage in a repo-hygiene or dependency-bump plan rather than fixed here.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `api/app/verification.py` is ready for Plan 03 to wire into `routes/disc.py`, replacing the 5 inline `disc.status` mutations at `disc.py:241-245` (resolve), `disc.py:422-424` (auto-verify), `disc.py:444-445` (submit-dispute), and `disc.py:616-618` (verify_disc) with calls to `verify()`/`flag_dispute()`/`resolve_dispute()`.
- The route layer must translate `verify()`'s `False` return into its existing idempotent-200 "already verified" response body — no new HTTP status code is needed.
- `VerificationTransitionError` is ready to be caught at the route boundary and mapped to a `403`-style response (mirroring how `DiscIdentityConflict` is caught and converted via `_identity_conflict_response()`).
- No blockers for Plan 02 (IDENT-01/IDENT-02, which does not depend on this module).

---
*Phase: 01-alias-layer-hardening-repo-hygiene*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: api/app/verification.py
- FOUND: api/tests/test_verification.py
- FOUND: .planning/phases/01-alias-layer-hardening-repo-hygiene/01-01-SUMMARY.md
- FOUND commit: eb49775 (test)
- FOUND commit: 8093a9c (feat)
- FOUND commit: 95f54ba (refactor)
