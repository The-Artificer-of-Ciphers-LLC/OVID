---
phase: 06-oauth-account-linking
plan: 06
subsystem: auth
tags: [oauth, apple-signin, indieauth, es256, jwt, fastapi, config-hardening]

# Dependency graph
requires:
  - phase: 06-03
    provides: config.ALLOW_LOCALHOST_BYPASS (derived from OVID_ENV, False in production) + OVID_ENV boot assertion
  - phase: 06-05
    provides: routes.py finalize_auth thin-wrapper over resolve_auth (nOAuth-safe callback wiring)
provides:
  - Apple ES256 client-secret shrunk to ~300s exp, regenerated per token exchange (AUTH-03 automated rotation)
  - IndieAuth routes split onto a separate indieauth_router, registered only when OVID_ENABLE_INDIEAUTH is truthy (default 404)
  - IndieAuth localhost bypass derived from config.ALLOW_LOCALHOST_BYPASS (provably unreachable in production, AUTH-10)
affects: [oauth, auth-hardening, phase-06-verification, deployment-config]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Security-relevant config (localhost bypass) consumed as a MODULE attribute read at call time — single source of truth, monkeypatchable in tests, never a hardcoded literal"
    - "Optional/non-headline auth provider gated behind an env flag via a dedicated APIRouter that main.py includes conditionally"
    - "Short-lived credential + per-use regeneration as the rotation mechanism (no long-lived secret at rest)"

key-files:
  created: []
  modified:
    - api/app/auth/routes.py
    - api/main.py
    - .env.example
    - api/tests/test_auth_apple.py
    - api/tests/test_auth_indieauth.py

key-decisions:
  - "Apple client-secret exp set to now+300 (~5min); per-exchange regeneration IS AUTH-03's automated rotation (D-10); ~5min tolerates clock skew/retries (D-11)"
  - "IndieAuth moved to a separate indieauth_router; main.py registers it only when OVID_ENABLE_INDIEAUTH in (1,true,yes) — default off returns 404 (D-08)"
  - "validate_url call site reads config.ALLOW_LOCALHOST_BYPASS as a module attribute (not a from-imported value, not a hardcoded True) so the bypass is provably unreachable under OVID_ENV=production (AUTH-10, D-09)"
  - "The OVID_ENABLE_INDIEAUTH router flag and the OVID_ENV production-safety guard are independent — disabling IndieAuth never disables the guard (Pitfall 6)"

patterns-established:
  - "Config-drift defense: derive the security-sensitive flag from one authoritative constant and consume it at call time; prove behavior by monkeypatching that constant"
  - "Enabled-path test fixture: register a default-off router at runtime (routes match dynamically per request) and restore the route table on teardown"

requirements-completed: [AUTH-03, AUTH-10]

coverage:
  - id: D1
    description: "Apple ES256 client_secret is short-lived (~300s exp - iat), not a multi-month lifetime"
    requirement: "AUTH-03"
    verification:
      - kind: unit
        ref: "api/tests/test_auth_apple.py::TestAppleClientSecret::test_client_secret_exp_is_short_lived"
        status: pass
    human_judgment: false
  - id: D2
    description: "Apple client_secret is independently regenerated per token exchange (rotation)"
    requirement: "AUTH-03"
    verification:
      - kind: unit
        ref: "api/tests/test_auth_apple.py::TestAppleClientSecret::test_client_secret_regenerated_per_exchange"
        status: pass
    human_judgment: false
  - id: D3
    description: "IndieAuth is disabled by default — login/callback return 404 when OVID_ENABLE_INDIEAUTH is unset"
    requirement: "AUTH-10"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_indieauth.py::TestIndieAuthGating::test_login_404_when_disabled"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_indieauth.py::TestIndieAuthGating::test_callback_404_when_disabled"
        status: pass
    human_judgment: false
  - id: D4
    description: "IndieAuth localhost bypass derived from config.ALLOW_LOCALHOST_BYPASS: rejected when False (production), accepted when True (development)"
    requirement: "AUTH-10"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_indieauth.py::TestIndieAuthLocalhostBypass::test_localhost_rejected_when_bypass_off"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_indieauth.py::TestIndieAuthLocalhostBypass::test_localhost_accepted_when_bypass_on"
        status: pass
    human_judgment: false

# Metrics
duration: 16min
completed: 2026-07-07
status: complete
---

# Phase 6 Plan 6: routes.py Security Hardening (Apple exp + IndieAuth gating) Summary

**Apple ES256 client-secret shrunk from 6 months to ~300s with per-exchange rotation (AUTH-03), and IndieAuth split onto an opt-in router with its localhost bypass derived from config.ALLOW_LOCALHOST_BYPASS so it is provably unreachable in production (AUTH-10).**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-07T03:40:00Z
- **Completed:** 2026-07-07T03:56:00Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 5

## Accomplishments
- Apple `generate_apple_client_secret` `exp` offset reduced from `now + 86400*180` (6 months) to `now + 300` (~5 min); per-exchange regeneration is the automated rotation, collapsing the credential theft/replay window from months to minutes (AUTH-03, D-10/D-11).
- IndieAuth `login`/`callback` moved onto a dedicated `indieauth_router`; `main.py` registers it only when `OVID_ENABLE_INDIEAUTH` is truthy — disabled by default the endpoints return 404, shrinking the default auth surface to GitHub / Apple / Google / Mastodon (D-08).
- The IndieAuth `validate_url` call site now derives `allow_localhost=config.ALLOW_LOCALHOST_BYPASS` (read as a module attribute at call time) instead of the hardcoded `True`, making the dev-only localhost bypass provably unreachable under `OVID_ENV=production` (AUTH-10, D-09). No hardcoded `allow_localhost=True` remains in routes.py.
- `OVID_ENABLE_INDIEAUTH` documented in `.env.example`; the router flag is kept independent of the OVID_ENV production-safety guard (Pitfall 6).

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 (RED): Apple client-secret exp test** - `26d47a8` (test)
2. **Task 1 (GREEN): shrink Apple exp to ~300s** - `8730f50` (feat)
3. **Task 2 (RED): IndieAuth gating + localhost-bypass tests** - `e585a72` (test)
4. **Task 2 (GREEN): gate IndieAuth off by default + derive bypass from config** - `d10554d` (feat)

**Plan metadata:** committed separately (docs: complete plan)

## Files Created/Modified
- `api/app/auth/routes.py` - Apple `exp` now+300; `from app.auth import config`; new `indieauth_router`; IndieAuth routes moved onto it; `validate_url(allow_localhost=config.ALLOW_LOCALHOST_BYPASS)`.
- `api/main.py` - import `indieauth_router`; conditional `include_router` gated on `OVID_ENABLE_INDIEAUTH` (independent of the OVID_ENV guard).
- `.env.example` - documented `OVID_ENABLE_INDIEAUTH` (disabled by default, not a headline provider, truthy to enable).
- `api/tests/test_auth_apple.py` - `TestAppleClientSecret`: exp (~300s) + per-exchange rotation, deterministic claim assertions.
- `api/tests/test_auth_indieauth.py` - `indieauth_client` enabled-path fixture; `TestIndieAuthGating` (404-when-disabled); `TestIndieAuthLocalhostBypass` (AUTH-10 reject/accept); existing route tests migrated to the enabled-path fixture.

## Decisions Made
- Consume `config.ALLOW_LOCALHOST_BYPASS` as a module attribute at call time (not `from ... import ALLOW_LOCALHOST_BYPASS`) so tests can monkeypatch the single source of truth and the value is never captured by-value at import.
- Model the operator opt-in with a runtime `app.include_router(indieauth_router)` fixture (routes match dynamically per request) + route-table restore on teardown, rather than reconstructing a second FastAPI app with duplicated middleware. This keeps the existing IndieAuth route tests exercising the real app stack (SessionMiddleware, DB override).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The plan's Task-2 verify one-liner (`grep -v '^#' ... | grep -c 'config.ALLOW_LOCALHOST_BYPASS' | grep -qv '^0$'`) returned 0 through a piped `grep` reading stdin — an artifact of the environment's `rtk` grep wrapper mishandling piped stdin, not a code defect. The substance was verified deterministically: the sole non-comment occurrence is the `validate_url(..., allow_localhost=config.ALLOW_LOCALHOST_BYPASS)` call site (routes.py:491) and no `allow_localhost=True` literal remains. The behavioral tests (reject when False / accept when True) prove the derivation directly.

## User Setup Required
None - no external service configuration required. Operators who want IndieAuth must set `OVID_ENABLE_INDIEAUTH` to a truthy value (documented in `.env.example`); it is intentionally off by default.

## Next Phase Readiness
- routes.py security hardening for Phase 06 is complete; all four headline providers register by default, IndieAuth is opt-in, Apple secret exposure window is minimized.
- Full API suite green and warning-clean: 398 passed (392 baseline + 6 new).

## Self-Check: PASSED

All modified/created files present; all 4 task commits (26d47a8, 8730f50, e585a72, d10554d) exist in git history. Full API suite green and warning-clean (398 passed).

---
*Phase: 06-oauth-account-linking*
*Completed: 2026-07-07*
