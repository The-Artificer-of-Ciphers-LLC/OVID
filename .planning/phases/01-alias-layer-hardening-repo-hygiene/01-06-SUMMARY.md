---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 06
subsystem: infra
tags: [repo-hygiene, gitignore, vcs, cleanup]

# Dependency graph
requires: []
provides:
  - "Repo root free of disposable one-shot patch scripts (fix_test.py, fix_test2.py, test_script.py, verify_t11.py)"
  - "run_uat.py and create_uat_dirs.py relocated to scripts/ with history preserved (git mv)"
  - "uat_results.json and uat_dirs/ untracked (git rm --cached) and gitignored"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["git rm --cached + .gitignore pairing for untracking already-tracked generated artifacts"]

key-files:
  created: []
  modified:
    - .gitignore
    - scripts/run_uat.py
    - scripts/create_uat_dirs.py
    - .planning/phases/01-alias-layer-hardening-repo-hygiene/deferred-items.md

key-decisions:
  - "D-17: Delete fix_test.py, fix_test2.py, test_script.py, verify_t11.py — one-shot patch scripts whose edits are already applied, confirmed disposable and import-safe"
  - "D-18: Relocate run_uat.py/create_uat_dirs.py to scripts/ via git mv (not delete) since they remain useful UAT tooling"
  - "D-19: Untrack uat_results.json/uat_dirs/ via git rm --cached (gitignore alone does not untrack already-tracked files) and gitignore them so future regenerations stay untracked"

patterns-established:
  - "Repo-hygiene changes pair .gitignore additions with git rm --cached in the same commit — gitignore-only changes silently fail to untrack already-tracked paths"

requirements-completed: [CLEAN-01, CLEAN-02]

coverage:
  - id: D1
    description: "Four disposable one-shot patch scripts deleted from repo root (fix_test.py, fix_test2.py, test_script.py, verify_t11.py)"
    requirement: "CLEAN-01"
    verification:
      - kind: other
        ref: "test ! -e fix_test.py && test ! -e fix_test2.py && test ! -e test_script.py && test ! -e verify_t11.py (CLEAN01-OK)"
        status: pass
    human_judgment: false
  - id: D2
    description: "run_uat.py and create_uat_dirs.py relocated under scripts/ via git mv, still byte-compile and function unchanged"
    verification:
      - kind: other
        ref: "python -m py_compile scripts/run_uat.py scripts/create_uat_dirs.py (exit 0)"
        status: pass
    human_judgment: false
  - id: D3
    description: "uat_results.json and uat_dirs/ (21 tracked paths) untracked via git rm --cached and added to .gitignore"
    requirement: "CLEAN-02"
    verification:
      - kind: other
        ref: "git ls-files | grep -E '^(uat_results.json|uat_dirs/)' returns empty; git check-ignore uat_results.json uat_dirs/ returns both paths; files confirmed still present on disk"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full API test suite remains green after all deletions/relocations/untracking — nothing load-bearing removed"
    verification:
      - kind: integration
        ref: "api/.venv/bin/python -m pytest tests/ -q -> 252 passed, 22 warnings"
        status: pass
    human_judgment: false

duration: 3min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 06: Repo Hygiene — Disposable Script Cleanup Summary

**Deleted 4 already-applied one-shot patch scripts, relocated UAT tooling to scripts/ via git mv, and untracked+gitignored generated UAT fixture artifacts (21 tracked paths) with git rm --cached.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-07-05T15:05:00-04:00 (approx)
- **Completed:** 2026-07-05T15:08:12-04:00
- **Tasks:** 3 completed
- **Files modified:** 1 (.gitignore) + 4 deleted + 2 renamed + 20 untracked (uat_dirs/ fixtures) + 1 untracked (uat_results.json) + 1 (deferred-items.md)

## Accomplishments
- Deleted `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py` (D-17) — re-confirmed import-safety via `git grep` and filesystem grep across the whole tree before deletion; zero references found anywhere
- Relocated `run_uat.py` → `scripts/run_uat.py` and `create_uat_dirs.py` → `scripts/create_uat_dirs.py` via `git mv` (D-18), preserving git history; both byte-compile cleanly and use cwd-relative paths so no path fixes were needed
- Untracked `uat_results.json` and all 20 `uat_dirs/` fixture files via `git rm --cached`, paired with new `.gitignore` entries (D-19) in the same commit per RESEARCH Pitfall 5 — `git ls-files` now shows zero `uat_` paths tracked, while the files remain present on disk (regeneratable via the relocated `scripts/create_uat_dirs.py` + `scripts/run_uat.py`)
- Confirmed the full API test suite (252 tests) still passes after all changes — nothing load-bearing was removed

## Task Commits

Each task was committed atomically:

1. **Task 1 (CLEAN-01): Delete one-shot patch scripts, relocate UAT tooling** - `d39d7e5` (chore)
2. **Task 2 (CLEAN-02): Untrack UAT artifacts and gitignore them** - `8c51d58` (chore)
3. **Task 3: Confirm suite green after hygiene changes** - `7f5370e` (docs)

**Plan metadata:** (see final commit below)

## Files Created/Modified
- `.gitignore` - Added `uat_results.json` and `uat_dirs/` entries
- `scripts/run_uat.py` - Relocated from repo root (git mv), unchanged content
- `scripts/create_uat_dirs.py` - Relocated from repo root (git mv), unchanged content
- `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py` - Deleted (one-shot patch scripts, already applied)
- `uat_results.json`, `uat_dirs/*` (20 files) - Untracked via `git rm --cached`; still on disk, now gitignored
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/deferred-items.md` - Logged pre-existing (unrelated) test-suite warnings observed during Task 3's verification run

## Decisions Made
- D-17/D-18/D-19 executed exactly as planned; no architectural deviations
- Re-verified import-safety independently (git grep + filesystem grep) rather than trusting the plan's prior claim, per the no-wave-off/safety-gate requirement — confirmed zero references before deleting any script
- Used `api/.venv/bin/python -m pytest` (the project's own virtualenv) for Task 3's verification since the system `python3` (3.14, Homebrew) lacked pytest installed

## Deviations from Plan

None - plan executed exactly as written. All three tasks, acceptance criteria, and verification commands passed on the first attempt.

## Issues Encountered

- The plan's literal verify command `cd api && python -m pytest tests/ -q` silently produced no output under the system Python (module not found, no error surfaced audibly). Diagnosed by redirecting output to a file and inspecting it, which revealed `No module named pytest`. Resolved by using the project's `api/.venv/bin/python`, which is the correct/intended interpreter for this project's test suite (confirmed working: 252 passed). This is not a plan defect — it's an environment-invocation detail, and using the project's own venv is the correct behavior per repo conventions (Python 3.12/uv-managed venvs per CLAUDE.md tech stack).
- Test suite run surfaced 22 warnings (`InsecureKeyLengthWarning` in JWT edge-case tests, `StarletteDeprecationWarning` re: httpx/TestClient, `asyncio.iscoroutinefunction DeprecationWarning` in slowapi). These are identical to warnings already logged as pre-existing and out-of-scope under Plans 01-01 and 01-02 in `deferred-items.md`. This plan touches zero `api/` source or test files, so these warnings could not have been introduced by this diff — confirmed pre-existing via cross-reference with prior plans' independent observations of the same warnings, and logged as the third such confirmation in `deferred-items.md` rather than fixed here (out of this plan's declared file scope).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Repo root is clean of disposable debug/patch scripts (CLEAN-01 satisfied)
- UAT tooling (`scripts/run_uat.py`, `scripts/create_uat_dirs.py`) remains available and functional for future BD/UHD fingerprinting UAT cycles
- Generated UAT fixture data (`uat_results.json`, `uat_dirs/`) is untracked and will not reappear in future `git status`/`git diff` noise
- No blockers for subsequent Phase 01 plans or later phases (BD fingerprinting, promotion, OAuth work per CONCERNS.md)

---
*Phase: 01-alias-layer-hardening-repo-hygiene*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: scripts/run_uat.py
- FOUND: scripts/create_uat_dirs.py
- CONFIRMED-DELETED: fix_test.py, fix_test2.py, test_script.py, verify_t11.py (all `test ! -e` checks pass)
- FOUND: .planning/phases/01-alias-layer-hardening-repo-hygiene/01-06-SUMMARY.md
- FOUND commits: d39d7e5, 8c51d58, 7f5370e
