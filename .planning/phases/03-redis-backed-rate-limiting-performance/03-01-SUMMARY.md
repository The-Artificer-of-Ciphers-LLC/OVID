---
phase: 03-redis-backed-rate-limiting-performance
plan: 01
subsystem: infra
tags: [rate-limiting, slowapi, redis, limits, fastapi, multi-worker, fail-fast]

# Dependency graph
requires:
  - phase: 02-two-contributor-verification-workflow
    provides: slowapi limiter with auth-aware key + structured 429 handler (api/app/rate_limit.py)
provides:
  - Env-driven rate-limit backend — REDIS_URL selects shared RedisStorage (cross-worker-correct), unset keeps memory:// default
  - Bounded, self-healing in-memory outage fallback (FALLBACK_LIMIT) that fails open on the read path during a Redis outage
  - Fail-fast import-time guard refusing to boot on OVID_WORKERS>1 without REDIS_URL (loud Nx-inflation failure)
  - AUTH_WRITE_LIMIT constant (consumed by Plan 02) and FALLBACK_LIMIT constant (outage tuning)
  - redis>=5,<8 dependency pin
affects: [03-02 write-throttle, 03-03 p95-load, 03-04 loadtest-harness]

# Tech tracking
tech-stack:
  added: [redis>=5<8 (redis-py client, first-party, enables limits.storage.RedisStorage)]
  patterns:
    - "Env-driven backend selection read once at import (REDIS_URL) gating native slowapi flags on bool(REDIS_URL)"
    - "Import-time fail-fast guard mirroring auth/config._require_env (raise RuntimeError on misconfiguration)"
    - "Subprocess-isolated tests for import-time / module-global behavior (avoids polluting the shared app limiter)"
    - "Deterministic IO-failure injection: save→override→assert→restore-in-finally on RedisStorage.incr (CLAUDE.md convention)"

key-files:
  created:
    - api/tests/test_rate_limit_backend.py
    - api/tests/test_rate_limit_fallback.py
    - api/tests/test_startup_guard.py
  modified:
    - api/app/rate_limit.py
    - api/requirements.txt

key-decisions:
  - "REDIS_URL read once at import; storage_uri = REDIS_URL or memory://; swallow_errors/in_memory_fallback_enabled/in_memory_fallback all gate on bool(REDIS_URL) so the unset default stays pure memory:// (D-05a)"
  - "FALLBACK_LIMIT=60/minute — a single GLOBAL per-worker cap that slowapi applies to every route during an outage, deliberately conservative to still protect the read path (D-01, Pitfall 1)"
  - "AUTH_WRITE_LIMIT=20/minute;300/hour lives in rate_limit.py now for Plan 02 (D-08)"
  - "D-06 guard uses explicit OVID_WORKERS (fallback WEB_CONCURRENCY) env var, never gunicorn argv scraping"
  - "main.py unchanged — the guard fires via its existing 'from app.rate_limit import ...' at line 14 (PATTERNS discrepancy #2 confirmed)"

patterns-established:
  - "Rate-limit key functions MUST name their parameter `request` — slowapi inspects the signature and only injects the Request when the param is literally `request` (root cause of the fallback path, discovered empirically)"
  - "Import-time module behavior is tested in subprocess isolation, not importlib.reload, because the app limiter is a module global"

requirements-completed: [INFRA-01, INFRA-02]

coverage:
  - id: D1
    description: "REDIS_URL selects a shared RedisStorage backend; unset preserves the memory:// single-worker default (INFRA-01)"
    requirement: "INFRA-01"
    verification:
      - kind: unit
        ref: "api/tests/test_rate_limit_backend.py#test_redis_url_selects_redis_storage"
        status: pass
      - kind: unit
        ref: "api/tests/test_rate_limit_backend.py#test_no_redis_url_selects_memory_storage"
        status: pass
    human_judgment: false
  - id: D2
    description: "Redis outage (injected ConnectionError on RedisStorage.incr) degrades to a bounded per-worker in-memory fallback — 200 within FALLBACK_LIMIT then 429 — never fail-closed on the read path (INFRA-02, D-01/D-02/D-03)"
    requirement: "INFRA-02"
    verification:
      - kind: unit
        ref: "api/tests/test_rate_limit_fallback.py#test_redis_outage_falls_back_to_bounded_cap"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fail-fast boot guard: import raises RuntimeError on OVID_WORKERS>1 (or WEB_CONCURRENCY>1) without REDIS_URL; boots clean when REDIS_URL is set or workers <= 1 (D-06)"
    requirement: "INFRA-01"
    verification:
      - kind: unit
        ref: "api/tests/test_startup_guard.py#test_multiworker_without_redis_refuses_to_boot"
        status: pass
      - kind: unit
        ref: "api/tests/test_startup_guard.py#test_multiworker_with_redis_boots_clean"
        status: pass
      - kind: unit
        ref: "api/tests/test_startup_guard.py#test_single_worker_boots_clean_without_redis"
        status: pass
      - kind: unit
        ref: "api/tests/test_startup_guard.py#test_web_concurrency_fallback_env_is_honored"
        status: pass
    human_judgment: false
  - id: D4
    description: "AUTH_WRITE_LIMIT and FALLBACK_LIMIT exist as named tunable constants; redis>=5,<8 pinned"
    verification:
      - kind: unit
        ref: "api/tests/test_rate_limit_backend.py#test_tunable_constants_defined"
        status: pass
      - kind: other
        ref: "cd api && .venv/bin/python -c 'import redis, limits.storage; ... RedisStorage constructable'"
        status: pass
    human_judgment: false

# Metrics
duration: 9min
completed: 2026-07-06
status: complete
---

# Phase 03 Plan 01: Redis-Backed Rate-Limiting Backbone Summary

**Env-driven slowapi backend — shared RedisStorage when REDIS_URL is set, a bounded self-healing in-memory fallback during a Redis outage, and an import-time fail-fast guard against silent multi-worker `memory://` Nx inflation.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-06T08:19:32-04:00
- **Completed:** 2026-07-06T12:29:02Z
- **Tasks:** 3
- **Files modified:** 5 (2 modified, 3 created)

## Accomplishments
- `api/app/rate_limit.py` now reads `REDIS_URL` once at import and selects a shared `limits` `RedisStorage` when set (cross-worker-correct counters, INFRA-01), preserving the historical single-worker `memory://` default when unset.
- During a Redis outage the limiter degrades to a bounded, self-healing in-memory fallback (`FALLBACK_LIMIT = 60/minute` per worker) — 200 within the cap, 429 beyond — never failing closed on the read-heavy ARM lookup path (INFRA-02, D-01/D-02/D-03). Proven by deterministic `ConnectionError` injection on `RedisStorage.incr`.
- Import-time guard refuses to boot with a clear `RuntimeError` when `OVID_WORKERS>1` (fallback `WEB_CONCURRENCY>1`) and `REDIS_URL` is unset, turning silent Nx inflation into a loud failure (D-06).
- Added tunable named constants `AUTH_WRITE_LIMIT` (Plan 02, D-08) and `FALLBACK_LIMIT` (outage tuning), plus the `redis>=5,<8` pin.

## Task Commits

Each task was committed atomically (TDD tasks are test→feat):

1. **Task 1: Pin and install the redis client dependency** - `88ef8f3` (chore)
2. **Task 2: Env-driven Redis backend + in-memory outage fallback** - `d97d068` (test, RED) → `f8983a1` (feat, GREEN)
3. **Task 3: Fail-fast startup guard against multi-worker memory://** - `53c11d6` (test, RED) → `586416d` (feat, GREEN)

## Files Created/Modified
- `api/app/rate_limit.py` - Env-driven `REDIS_URL` backend selection, native slowapi outage-fallback flags gated on `bool(REDIS_URL)`, `AUTH_WRITE_LIMIT`/`FALLBACK_LIMIT` constants, and the D-06 import-time multi-worker guard.
- `api/requirements.txt` - Added `redis>=5,<8` (upper bound required: `limits` constrains its redis extra to `<8.0.0`).
- `api/tests/test_rate_limit_backend.py` - Subprocess-isolated backend selection + constant existence.
- `api/tests/test_rate_limit_fallback.py` - Injected-outage bounded fallback (save→override→restore in finally).
- `api/tests/test_startup_guard.py` - Multi-worker fail-fast guard across OVID_WORKERS / WEB_CONCURRENCY / redis-set / single-worker cases.

## Decisions Made
- Followed the plan's locked decisions (D-01, D-05a, D-06, D-08). No architectural deviations.
- Empirically confirmed the exact resolvable pin: `limits 5.8.0` requires `redis<8.0.0,>3`; `redis>=5,<8` resolves to 7.4.1 (verified with `pip index versions`).
- Confirmed slowapi 0.1.10 exposes the active backend on the private `_storage` handle; used it for backend-selection assertions.

## Deviations from Plan

None - plan executed exactly as written. No deviation rules (1-4) were triggered; all three tasks matched the plan and their acceptance criteria.

## Issues Encountered
- **Fallback path initially returned 500, not the expected 200/429.** Root-caused (not waved off): slowapi's `__evaluate_limits` calls the key function as `key_func(request)` **only when the parameter is literally named `request`** (it does `"request" in inspect.signature(...).parameters`). An early probe used `lambda r:` which slowapi then called with zero args → `TypeError` swallowed by `swallow_errors` → `view_rate_limit` never set → 500. The real app works because `_auth_aware_key(request)` uses the right name. Fixed the test's key function to name its parameter `request`; documented this as an established pattern. This was a test-harness discovery, not a code bug — the shipped implementation was correct.
- **Two pre-existing third-party deprecation warnings** (`asyncio.iscoroutinefunction` in slowapi 0.1.10, httpx-in-TestClient in Starlette) surface across the whole suite. They originate in vendored library code, pre-date this plan (the unchanged `test_rate_limit.py`/`test_auth.py` emit them), and are unfixable without patching `.venv`. Logged to `deferred-items.md` for a future dependency bump; the project's CI Python (3.12) does not fire the asyncio one.

## User Setup Required
None for this plan's tests (they need no live Redis — `redis.from_url` does not connect eagerly and the outage is injected). Operationally, running the API with more than one worker now REQUIRES setting `REDIS_URL`; single-worker self-hosting is unchanged. `REDIS_URL`/`OVID_WORKERS` wiring into compose/env is downstream phase work.

## Next Phase Readiness
- `AUTH_WRITE_LIMIT` is exported and ready for Plan 02's write-path throttle.
- The real target config (shared Redis store) is now selectable, so Plan 03's p95 load validation and Plan 04's loadtest harness can exercise the true multi-worker path.
- No blockers introduced. Full API suite green (318 passed).

## Self-Check: PASSED

All 5 files created/modified exist on disk; all 5 task commits present in git history.

---
*Phase: 03-redis-backed-rate-limiting-performance*
*Completed: 2026-07-06*
