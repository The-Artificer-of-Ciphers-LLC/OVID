---
phase: 03-redis-backed-rate-limiting-performance
plan: 02
subsystem: api
tags: [rate-limiting, slowapi, write-throttle, anti-sybil, fastapi, tdd]

# Dependency graph
requires:
  - phase: 03-redis-backed-rate-limiting-performance
    provides: AUTH_WRITE_LIMIT constant + Redis-backed shared limiter (api/app/rate_limit.py, Plan 01)
  - phase: 02-two-contributor-verification-workflow
    provides: anti_sybil.evaluate_confirmation Postgres cooldown + _handle_existing_disc confirmation branch
provides:
  - Method-scoped per-account POST write ceiling (AUTH_WRITE_LIMIT) on the three disc write routes (INFRA-04 / D-07)
  - D-09 novel-fingerprint flood is now capped even with zero confirmations
  - D-10 seam proven by test — slowapi write ceiling and anti_sybil cooldown are independent, layered, never double-counted
affects: [03-03 p95-load, 03-04 loadtest-harness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Stacked @limiter.limit decorators accumulate; each static limit gets its own storage namespace (no cross-decrement)"
    - "shared_limit(scope=...) pins a constant bucket scope for path-param routes where slowapi's default url key style would otherwise fragment the counter per distinct URL"

key-files:
  created:
    - api/tests/test_write_rate_limit.py
  modified:
    - api/app/routes/disc.py

key-decisions:
  - "submit_disc / register_disc use the plan's exact @limiter.limit(AUTH_WRITE_LIMIT, methods=[\"POST\"]) — their constant URLs bucket every POST from a key together under the default url key style"
  - "resolve_dispute_endpoint uses @limiter.shared_limit(AUTH_WRITE_LIMIT, scope=\"disc_write:resolve\") because its {fingerprint} path param would give each fingerprint its own counter under url key style (Rule 3 deviation — the plan's decorator form does not accumulate on a path-param route)"
  - "All three write routes keep the same AUTH_WRITE_LIMIT value initially (CONTEXT Claude's-discretion + RESEARCH Open Q1); each route has its own independent bucket"
  - "anti_sybil.evaluate_confirmation left entirely untouched — NOT migrated onto Redis/slowapi (D-10)"

patterns-established:
  - "For a rate-limited route carrying a path param, use shared_limit with an explicit constant scope, or the per-user ceiling silently never accumulates (default key_style='url' scopes the bucket by request PATH)"

requirements-completed: [INFRA-04]

coverage:
  - id: D1
    description: "21st valid authed POST /v1/disc within a minute returns 429; reads in the same window stay on the 500/min auth tier (D-07)"
    requirement: "INFRA-04"
    verification:
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_write_limit_caps_disc_submissions_at_21st"
        status: pass
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_reads_not_throttled_by_write_cap"
        status: pass
    human_judgment: false
  - id: D2
    description: "POST /disc/register and POST /disc/{fingerprint}/resolve enforce the same AUTH_WRITE_LIMIT ceiling"
    requirement: "INFRA-04"
    verification:
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_register_route_enforces_write_cap"
        status: pass
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_resolve_route_enforces_write_cap"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-10 seam: novel flood caps with zero verify edits (anti_sybil uninvolved); a confirmation records a verify edit AND consumes a write-limit slot — independent, layered"
    requirement: "INFRA-04"
    verification:
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_novel_flood_caps_with_zero_verify_edits"
        status: pass
      - kind: unit
        ref: "api/tests/test_write_rate_limit.py#test_confirmation_records_verify_edit_and_consumes_write_slot"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-07-06
status: complete
---

# Phase 03 Plan 02: Method-Scoped Per-Account Write Ceiling Summary

**A tighter `AUTH_WRITE_LIMIT` POST ceiling stacked on the three disc write routes (submit / register / resolve) — closing the D-09 novel-fingerprint flood gap the Phase-2 confirmation cooldown never covered, and proven independent of that cooldown (D-10 seam).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-06T12:36:19Z
- **Completed:** 2026-07-06T12:46:49Z
- **Tasks:** 2 (both TDD)
- **Files:** 2 (1 created, 1 modified)

## Accomplishments
- Stacked a second `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` above the existing `@limiter.limit(_dynamic_limit)` on `submit_disc` and `register_disc`, delivering the INFRA-04 per-account POST write ceiling (20/min;300/hour). The 21st valid authenticated POST in a minute now returns a structured 429; reads stay on the 500/min auth tier, untouched.
- Applied the same ceiling to `resolve_dispute_endpoint` via `@limiter.shared_limit(AUTH_WRITE_LIMIT, scope="disc_write:resolve")` — required because its `{fingerprint}` path param defeats slowapi's default `url` key style (see Deviations).
- Closed the D-09 gap: a flood of brand-new (never-confirmation) fingerprints is now capped by the volumetric ceiling, independent of the Phase-2 semantic cooldown which only fires on confirmations.
- Proved the D-10 seam by test: a novel flood trips the write ceiling with **zero** `verify` edits (anti_sybil uninvolved), while a true two-contributor confirmation records a Postgres `verify` edit **and** consumes a write-limit slot — layered defense-in-depth, never double-counted. `anti_sybil.py` is entirely unchanged.

## Task Commits

Each task committed atomically (TDD: test → feat/docs):

1. **Task 1: Stack the method-scoped write ceiling (INFRA-04 / D-07)** — `b8eab5c` (test, RED) → `9f7ecb0` (feat, GREEN)
2. **Task 2: Prove the D-10 seam** — `7f023ff` (test) → `1bab651` (docs, one-line seam note)

## Files Created/Modified
- `api/app/routes/disc.py` — `AUTH_WRITE_LIMIT` import; stacked write decorator on `submit_disc` / `register_disc` (`.limit(..., methods=["POST"])`) and `resolve_dispute_endpoint` (`.shared_limit(..., scope="disc_write:resolve")`); D-10 seam doc note at the `evaluate_confirmation` call.
- `api/tests/test_write_rate_limit.py` — 6 tests: the 21st-POST 429 across all three routes, read-not-throttled, and both directions of the D-10 seam.

## Decisions Made
- Followed the plan's `.limit(..., methods=["POST"])` form verbatim for the two constant-URL routes.
- Deviated to `shared_limit` for the path-param resolve route (documented below); same `AUTH_WRITE_LIMIT` value and independent per-route bucket, so the plan's intent is preserved.
- Left `anti_sybil.evaluate_confirmation` untouched (D-10) — the seam is proven, not restructured.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] resolve route needed `shared_limit` with a fixed scope instead of `.limit(methods=["POST"])`**
- **Found during:** Task 1 GREEN (the resolve test failed while submit/register passed).
- **Issue:** Under slowapi's default `key_style="url"`, `__evaluate_limits` uses the request PATH as the limit scope (`lim.scope or endpoint`, where `endpoint` is the URL when key style is `url`). `submit_disc` (`/v1/disc`) and `register_disc` (`/v1/disc/register`) have constant URLs, so every POST from a key shares one bucket and the ceiling accumulates. `resolve_dispute_endpoint` carries a `{fingerprint}` path param, so each distinct fingerprint produced its own bucket and the counter never reached the cap — empirically confirmed: 25 consecutive resolve POSTs all returned 403 with `hit()` keyed on the varying path (`/v1/disc/dvd-NOPE0-main/resolve`, `.../dvd-NOPE1-main/resolve`, …), each returning `True`.
- **Fix:** Used `@limiter.shared_limit(AUTH_WRITE_LIMIT, scope="disc_write:resolve")`, which pins an explicit constant scope so the ceiling is keyed per-user (`user:{id}`) across all fingerprints, independent of the other two routes' buckets. The `methods=["POST"]` filter is redundant here since the route is `@router.post`-only. A code comment explains the choice.
- **Files modified:** `api/app/routes/disc.py`
- **Commit:** `9f7ecb0`
- **Scope preserved:** Did NOT change the global limiter's `key_style` (that would alter bucket semantics for unrelated read routes — out of scope). The fix is confined to the one affected route.

## Issues Encountered
- **Pre-existing third-party deprecation warnings** (`asyncio.iscoroutinefunction` in slowapi 0.1.10 on the local Python 3.14 venv; `httpx`-in-TestClient in Starlette) surface across the suite. These originate in vendored library code, pre-date this plan, and were already root-caused and logged to `deferred-items.md` in Plan 01. This plan added no new warning types (the count scales only with the 6 added tests). The project's CI Python (3.12) does not fire the asyncio one.

## User Setup Required
None. The write ceiling is decorator-based (no middleware added) and needs no live Redis for tests. Operationally it shares Plan 01's env-driven backend: meaningful cross-worker enforcement requires `REDIS_URL` (single-worker `memory://` is correct for self-hosting).

## Next Phase Readiness
- INFRA-04 is live on all three write routes; Plan 03 (p95 load) and Plan 04 (loadtest harness) can now exercise the write path under the true multi-worker Redis config.
- No blockers introduced. Full API suite green: **324 passed** (up from 318; +6 write-limit tests). `anti_sybil` suite unchanged: 24 passed.

## Self-Check: PASSED

All created/modified files exist on disk; all 4 task commits present in git history.
