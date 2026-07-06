---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 07
subsystem: infra
tags: [docker-compose, alembic, cutover-runbook, mirror-mode, ovid-mode, self-hosting]

# Dependency graph
requires:
  - phase: 05-adr-0001-completion-dvdread1-promotion (plan 05-06)
    provides: the 900000000006_promote_dvdread1_primary Alembic migration this wrapper drives
provides:
  - "scripts/promote_dvdread1.py — one-command D-04/D-05 cutover wrapper (toggle read-only -> alembic upgrade head -> toggle read-write)"
  - "docs/self-hosting.md cutover runbook section for standalone-mode self-hosters"
  - "docs/deployment.md cross-reference for the canonical-server (oviddb.org) audience"
affects: [phase-05-closeout, future-identity-method-migrations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Host-side operator script under scripts/ drives `docker compose exec`/`up -d` subprocess calls rather than importing app internals — mirrors scripts/dump_cc0.py convention"
    - "OVID_MODE capture-then-restore-in-finally, never a hardcoded default, so a canonical-mode operator's restore step can't silently leave the server on the wrong mode"

key-files:
  created:
    - scripts/promote_dvdread1.py
    - api/tests/test_promote_dvdread1_wrapper.py
  modified:
    - docs/self-hosting.md
    - docs/deployment.md

key-decisions:
  - "Wrapper never imports api/app internals — it drives docker compose subprocess calls exclusively, since MirrorModeMiddleware is wired at process-import time and can only be toggled by restarting the api container"
  - "Wrapper requires --compose-file/-f explicitly (repeatable, no default) plus an interactive y/N confirmation before mutating anything, per the wrong-deployment threat (T-05-16) this phase's research flagged"
  - "Restore-on-failure runs in a finally block covering both the mirror-toggle step and the alembic migration step, so a failure at either point still restores the captured original OVID_MODE"

requirements-completed: [IDENT-04]

coverage:
  - id: D1
    description: "scripts/promote_dvdread1.py captures the current OVID_MODE, prompts for explicit confirmation, and performs toggle-read-only -> alembic upgrade head -> restore-original-mode as one command"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_promote_dvdread1_wrapper.py#test_main_happy_path_toggles_mirror_then_restores_original_mode"
        status: pass
      - kind: unit
        ref: "api/tests/test_promote_dvdread1_wrapper.py#test_main_restores_original_mode_even_when_migration_fails"
        status: pass
    human_judgment: true
    rationale: "Unit tests mock every subprocess.run call; no automated test exercises a real docker compose / Postgres cutover end-to-end. Per 05-VALIDATION.md's Manual-Only Verifications table, a human must run the wrapper against a real dev deployment before relying on it for the actual oviddb.org cutover."
  - id: D2
    description: "docs/self-hosting.md documents the cutover runbook, explicitly stating the restart interrupts reads too (not just writes); docs/deployment.md cross-references it for the canonical-server audience"
    verification:
      - kind: other
        ref: "grep -c promote_dvdread1.py docs/self-hosting.md (2), docs/deployment.md (1); grep -ci 'interrupts reads' docs/self-hosting.md (1); mkdocs build --strict (pass)"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 07: dvdread1 Cutover Wrapper + Runbook Summary

**One-command `scripts/promote_dvdread1.py` wrapper drives `MirrorModeMiddleware`'s existing OVID_MODE toggle around the promotion migration, with a finally-guaranteed capture/restore of the operator's actual prior mode — plus matching self-hosting/deployment runbook sections that are explicit about the read interruption.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-06T23:36:00Z (approx, first commit d3e988e)
- **Completed:** 2026-07-06T23:41:02Z
- **Tasks:** 2 completed
- **Files modified:** 4 (1 new script, 1 new test, 2 docs)

## Accomplishments

- `scripts/promote_dvdread1.py`: captures the api service's live `OVID_MODE`, prints it plus the target compose files, requires an explicit `y`/`yes` confirmation, then toggles to `mirror` → runs `alembic upgrade head` → restores the captured original mode in a `finally` block regardless of success/failure. Zero new middleware code — reuses `MirrorModeMiddleware`'s existing conditional wiring in `api/main.py` exactly as-is.
- Never defaults to a specific compose file — `--compose-file`/`-f` is required and repeatable, mirroring `docker compose -f` semantics, directly mitigating the wrong-deployment threat (T-05-16) the phase research flagged.
- `docs/self-hosting.md` gained a "Promoting to dvdread1-* Primary (One-Time Cutover)" section that correctly splits the audience: mirror-mode operators are already permanently read-only and need no toggle (they just pick up the migration via their existing Updating step); standalone-mode operators need the wrapper, and the doc explicitly states the restart interrupts reads too — not just writes (Pitfall 3).
- `docs/deployment.md` gained a cross-reference in the Production "Run Database Migrations" section, framing the canonical server (`oviddb.org`, live writes, not already read-only like a mirror) as the audience that genuinely needs write-quiesce, with the prod-specific `-f docker-compose.yml -f docker-compose.prod.yml` invocation.

## Task Commits

Each task was committed atomically (TDD RED → GREEN for Task 1, since this project runs with `tdd_mode: true`):

1. **Task 1 (RED): failing tests for the cutover wrapper** — `d3e988e` (test)
2. **Task 1 (GREEN): cutover wrapper script** — `5a869fa` (feat)
3. **Task 2: docs — self-hosting.md runbook + deployment.md cross-reference** — `a8cd9fa` (docs)

_TDD note: this task wasn't marked `tdd="true"` in the plan XML, but the executor prompt's project-wide TDD mode (config.json `tdd_mode: true`) required a failing test first for the wrapper's behavior-bearing orchestration logic (mocked subprocess/alembic/confirmation) — see Deviations below._

## Files Created/Modified

- `scripts/promote_dvdread1.py` — the D-04/D-05 one-command cutover wrapper
- `api/tests/test_promote_dvdread1_wrapper.py` — 8 unit tests covering `_current_ovid_mode`'s capture/fallback behavior and `main()`'s decline/happy-path/migration-failure flows, all mocking `subprocess.run` and the confirmation prompt
- `docs/self-hosting.md` — new "Promoting to dvdread1-* Primary (One-Time Cutover)" section (after "Updating", before "Data Export (CC0 Dump)")
- `docs/deployment.md` — new "One-time dvdread1-* promotion cutover" subsection inside "3. Run Database Migrations"

## Decisions Made

- The wrapper drives `docker compose` subprocess calls exclusively rather than importing any `api/app` module — `MirrorModeMiddleware` is wired at process-import time (`api/main.py`), so the only way to actually flip it is restarting the `api` container, which the wrapper does via `docker compose ... up -d --no-deps api` with a mutated env, matching the RESEARCH.md sketch.
- Added an explicit `main(argv=None)` signature (rather than reading `sys.argv` directly) purely for testability — a minor, non-behavior-changing addition consistent with the plan's own acceptance criteria and not a deviation requiring a rule citation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added a unit test file for the wrapper's orchestration logic**
- **Found during:** Task 1
- **Issue:** The plan's `<files>` for Task 1 lists only `scripts/promote_dvdread1.py`; no test file was named. However, this project's `.planning/config.json` has `workflow.tdd_mode: true`, and the executor's TDD instructions for this plan explicitly call for a failing test first for the wrapper's behavior-bearing toggle/upgrade orchestration logic.
- **Fix:** Added `api/tests/test_promote_dvdread1_wrapper.py` (RED, `d3e988e`) before implementing the script (GREEN, `5a869fa`). The test imports the script directly from repo-root `scripts/` via a `sys.path` insertion (mirroring the existing sys.path-bootstrap convention in `api/tests/conftest.py`), so it runs under the standard `api-tests` CI job with zero CI config changes.
- **Files modified:** `api/tests/test_promote_dvdread1_wrapper.py` (new)
- **Verification:** `source api/.venv/bin/activate && cd api && pytest tests/test_promote_dvdread1_wrapper.py -v` — 8 passed. Full suite (`pytest tests/ -q`) — 359 passed, no regressions.
- **Committed in:** `d3e988e` (RED), `5a869fa` (GREEN)

**2. [Rule 1 - Bug] Fixed a repo-root path computation bug in the new test file itself**
- **Found during:** Task 1, while confirming RED → GREEN transition
- **Issue:** The test file's `sys.path` bootstrap computed `_repo_root` with `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` — only two `dirname()` calls from `api/tests/test_promote_dvdread1_wrapper.py`, which resolves to `api/`, not the true repo root. After creating `scripts/promote_dvdread1.py`, the test suite still failed with `ModuleNotFoundError: No module named 'promote_dvdread1'` because `scripts/` was never actually added to `sys.path`.
- **Fix:** Added a third `dirname()` call so `_repo_root` correctly resolves two levels above `api/tests/` (i.e., the actual repository root), matching where `scripts/` lives.
- **Files modified:** `api/tests/test_promote_dvdread1_wrapper.py`
- **Verification:** Re-ran the suite after the fix — all 8 tests in the file passed; confirmed by direct `python -c` path-resolution check before re-running pytest.
- **Committed in:** `5a869fa` (bundled with the GREEN implementation commit, since the test file only became genuinely correct once both files existed together)

---

**Total deviations:** 2 auto-fixed (1 missing-critical test coverage, 1 self-inflicted test bug caught before GREEN)
**Impact on plan:** Both auto-fixes are test-scaffolding corrections that made the plan's own acceptance criteria verifiable; no scope creep into application behavior beyond what the plan specified.

## Issues Encountered

- `mkdocs` was not installed in the ambient environment (only `docs/requirements.txt` — `mkdocs-material>=9.5` — is pinned for CI's `docs-build` job). Created a throwaway `uv venv` in the session scratchpad, installed `mkdocs-material` there, and ran `mkdocs build --strict` against it for local verification — no repo files changed by this; the generated `site/` output (already `.gitignore`d) was removed afterward. Confirmed the `docs/deployment.md` anchor link (`self-hosting.md#promoting-to-dvdread1-primary-one-time-cutover`) matches the exact heading slug MkDocs Material generates.

## User Setup Required

None — no external service configuration required. This wrapper is a local operator tool driven by `docker compose`; no environment variables or dashboard steps to configure beyond what self-hosting/deployment docs already specify.

## Next Phase Readiness

- This closes out Plan 05-07 and, with it, the D-05 cutover-operability deliverable from Phase 5's CONTEXT.md.
- Per the plan's own `<verification>` note, this wrapper's end-to-end behavior against a real Postgres-backed `docker compose` stack has NOT been exercised (CI/this environment cannot run real Docker Compose + Postgres) — flagged as `human_judgment: true` in the coverage block above. Recommend a manual dry run against a real dev deployment before the actual `oviddb.org` cutover.
- No blockers for phase closeout from this plan.

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created files verified present on disk; all referenced commit hashes (`d3e988e`, `5a869fa`, `a8cd9fa`, `56cef2b`) verified present in git log.
