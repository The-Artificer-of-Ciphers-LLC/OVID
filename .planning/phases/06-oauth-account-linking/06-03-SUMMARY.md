---
phase: 06-oauth-account-linking
plan: 03
subsystem: auth
tags: [config, env-var, fail-fast, indieauth, boot-guard, docker-compose, security]

# Dependency graph
requires:
  - phase: 06-oauth-account-linking
    provides: existing _require_env fail-fast pattern in api/app/auth/config.py
provides:
  - "OVID_ENV required env var with import-time boot assertion (development|production, no default)"
  - "config.ALLOW_LOCALHOST_BYPASS constant — single source of truth for the IndieAuth localhost bypass, False under production by construction"
  - "OVID_ENV declared across .env.example + all three compose files (production hardcoded)"
affects: [06-06-indieauth-router, 06-07-docs, self-hosting-upgrade]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Import-time fail-fast config assertion reused (not duplicated) via _require_env"
    - "Derived security constant with explicit invariant guard at module scope"

key-files:
  created:
    - api/tests/test_auth_config.py
  modified:
    - api/app/auth/config.py
    - api/tests/conftest.py
    - api/tests/test_startup_guard.py
    - api/tests/test_rate_limit_backend.py
    - .env.example
    - docker-compose.yml
    - docker-compose.test.yml
    - docker-compose.prod.yml

key-decisions:
  - "ALLOW_LOCALHOST_BYPASS derived solely from OVID_ENV (!= production), never recomputed/hardcoded — Plan 06 routes.py consumes this constant"
  - "Kept the OVID_ENV guard at module scope in config.py so it fires at import regardless of the IndieAuth router flag (Pitfall 6)"
  - "conftest.py setdefault('OVID_ENV','development') keeps the whole suite importable without any external env"
  - "Compose env blocks kept column-aligned (repo convention) rather than the plan's single-space verify grep; whitespace-tolerant grep confirms correctness"

patterns-established:
  - "Import-time boot-guard tests run each env case in a fresh subprocess (module-level constants persist across importlib.reload within one process)"

requirements-completed: [AUTH-10]

coverage:
  - id: D1
    description: "API refuses to boot (raises at import) when OVID_ENV is unset or not in {development, production}"
    requirement: "AUTH-10"
    verification:
      - kind: unit
        ref: "tests/test_auth_config.py#test_unset_ovid_env_refuses_boot"
        status: pass
      - kind: unit
        ref: "tests/test_auth_config.py#test_invalid_ovid_env_refuses_boot"
        status: pass
    human_judgment: false
  - id: D2
    description: "ALLOW_LOCALHOST_BYPASS is derived from OVID_ENV — True in development, False in production"
    requirement: "AUTH-10"
    verification:
      - kind: unit
        ref: "tests/test_auth_config.py#test_development_boot_enables_localhost_bypass"
        status: pass
      - kind: unit
        ref: "tests/test_auth_config.py#test_production_boot_disables_localhost_bypass"
        status: pass
    human_judgment: false
  - id: D3
    description: "OVID_ENV declared across .env.example + all three compose files; production hardcoded, dev/test defaulted"
    requirement: "AUTH-10"
    verification:
      - kind: other
        ref: "grep -q 'OVID_ENV=development' .env.example && grep -q 'OVID_ENV: *${OVID_ENV:-development}' docker-compose.yml docker-compose.test.yml && grep -Eq 'OVID_ENV:[[:space:]]*production' docker-compose.prod.yml"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full existing api suite still imports and passes with OVID_ENV now required (no ImportError)"
    verification:
      - kind: unit
        ref: "cd api && .venv/bin/python -m pytest tests/ -q (377 passed, warning-clean)"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-07-06
status: complete
---

# Phase 06 Plan 03: OVID_ENV Boot Assertion & Localhost-Bypass Hardening Summary

**Required `OVID_ENV` env var with an import-time fail-fast in `api/app/auth/config.py` that derives `ALLOW_LOCALHOST_BYPASS` (False under production), making the IndieAuth localhost bypass unreachable in production by construction (AUTH-10).**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-07-06T22:57:00-04:00
- **Completed:** 2026-07-06T23:04:00-04:00
- **Tasks:** 2
- **Files modified:** 9 (1 created, 8 modified)

## Accomplishments
- `OVID_ENV` is now a required env var (no default): `config.py` raises at import if unset or outside `{development, production}`, mirroring the existing `_require_env("OVID_SECRET_KEY")` fail-fast.
- `ALLOW_LOCALHOST_BYPASS: bool = OVID_ENV != "production"` is the single source of truth for the IndieAuth localhost bypass, with an explicit import-time production-safety invariant assertion (AUTH-10 / ROADMAP criterion 6).
- The guard lives at module scope, evaluated unconditionally at import — independent of the IndieAuth router flag (Pitfall 6 / threat T-06-10c).
- `conftest.py` sets `OVID_ENV=development` via `setdefault` before any app import, keeping the whole suite importable with zero external env.
- `OVID_ENV` declared across `.env.example` (with a REQUIRED / breaking-change / accepted-values comment) and all three compose files; production is hardcoded, dev/test default to development.
- New `test_auth_config.py` proves all four import-time cases via subprocess isolation.

## Task Commits

1. **Task 1 (RED): failing boot-guard tests** - `aeeeb38` (test)
2. **Task 1 (GREEN): OVID_ENV assertion + ALLOW_LOCALHOST_BYPASS + conftest + collateral test-env fixes** - `ef480e4` (feat)
3. **Task 2: declare OVID_ENV across .env.example + compose files** - `90ecd5c` (chore)

_TDD task 1 produced test → feat commits (no refactor needed)._

## Files Created/Modified
- `api/app/auth/config.py` - Added `OVID_ENV` (via `_require_env`), value validation, `ALLOW_LOCALHOST_BYPASS`, and the production-safety invariant guard.
- `api/tests/test_auth_config.py` (new) - Four subprocess-based import-time boot-guard tests.
- `api/tests/conftest.py` - `setdefault("OVID_ENV", "development")` before app import (load-bearing).
- `api/tests/test_startup_guard.py` - Added `OVID_ENV` to the subprocess boot env dict.
- `api/tests/test_rate_limit_backend.py` - Added `OVID_ENV` to both subprocess boot env dicts.
- `.env.example` - `OVID_ENV=development` with required/breaking-change comment.
- `docker-compose.yml` / `docker-compose.test.yml` - `OVID_ENV: ${OVID_ENV:-development}`.
- `docker-compose.prod.yml` - `OVID_ENV: production` (hardcoded).

## Decisions Made
- Reused `_require_env` rather than writing a second helper (PATTERNS.md shared-pattern directive).
- Subprocess isolation (not `importlib.reload`) for the boot-guard tests, because module-level constants persist across reloads within one process (RESEARCH.md Wave 0 Gaps).
- Kept compose env blocks column-aligned to match the sibling `OVID_MODE:`/`OVID_SECRET_KEY:` lines and the repo convention (CLAUDE.md: follow codebase style); see Deviations for the verify-grep spacing note.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two existing subprocess-based test files broke when OVID_ENV became required**
- **Found during:** Task 1 (GREEN verification, full-suite run)
- **Issue:** `test_startup_guard.py` and `test_rate_limit_backend.py` spawn child interpreters with minimal controlled env dicts (`DATABASE_URL`, `OVID_SECRET_KEY`, `PATH`) to probe `app.rate_limit`/`main` import behavior. Making `OVID_ENV` required caused those child imports to raise `RuntimeError: Required environment variable OVID_ENV is not set`, failing 9 tests.
- **Fix:** Added `"OVID_ENV": "development"` to the three base boot env dicts — the correct boot env now includes it, exactly as it already included `OVID_SECRET_KEY`. Per-test `env_overrides` still compose on top unchanged.
- **Files modified:** api/tests/test_startup_guard.py, api/tests/test_rate_limit_backend.py
- **Verification:** Full suite 377 passed, warning-clean.
- **Committed in:** `ef480e4` (Task 1 GREEN commit)

### Non-issue nuance (documented, not a code change)

- The plan's Task 2 `<verify>` grep for `docker-compose.yml`/`.test.yml` uses a single-space pattern (`OVID_ENV: ${OVID_ENV:-development}`). This repo's compose env blocks are column-aligned (the existing `OVID_MODE:`/`OVID_SECRET_KEY:` lines align values to the widest key), so the literal single-space grep does not match. The semantic acceptance criteria are fully met; a whitespace-tolerant grep (`OVID_ENV: *${OVID_ENV:-development}`) returns `COMPOSE_OK`. Chose codebase-consistent alignment over the grep's incidental spacing.

---

**Total deviations:** 1 auto-fixed (1 blocking) + 1 documented spacing nuance
**Impact on plan:** The auto-fix was necessary to keep the existing suite green under the new required var — no scope creep. The spacing nuance is cosmetic and does not affect behavior.

## Issues Encountered
None beyond the Rule 3 auto-fix above.

## User Setup Required
None for this plan directly. Note: `OVID_ENV` is a BREAKING change for existing self-hosted instances — they must set it on upgrade (surfaced in docs by Plan 07). The `.env.example` comment states this explicitly.

## Next Phase Readiness
- `config.ALLOW_LOCALHOST_BYPASS` and `config.OVID_ENV` are ready for Plan 06's `routes.py` IndieAuth `validate_url(url, allow_localhost=config.ALLOW_LOCALHOST_BYPASS)` call site.
- No blockers.

---
*Phase: 06-oauth-account-linking*
*Completed: 2026-07-06*
