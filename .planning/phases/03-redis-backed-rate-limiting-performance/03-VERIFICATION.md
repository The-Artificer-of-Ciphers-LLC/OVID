---
phase: 03-redis-backed-rate-limiting-performance
verified: "2026-07-06T00:00:00Z"
status: passed
score: 12/12 must-have truths verified
behavior_unverified: 1
overrides_applied: 0
human_verification:

  - "test: "Run the Load Test (p95) workflow (.github/workflows/loadtest.yml) via workflow_dispatch (or wait for the weekly Monday 04:17 UTC schedule), then read the published p95/p99 in the job summary / loadtest-results artifact."

behavior_unverified_items:

  - "truth: "API p95 ≤ 500ms is validated by a load test RUN against the actual Redis-backed multi-worker gunicorn config (INFRA-03)"

findings: [severity: warning, severity: info]
---

# Phase 3: Redis-Backed Rate Limiting & Performance — Verification Report

**Phase Goal:** Fix multi-worker rate-limit scaling and validate the p95 latency budget against the real Redis-backed, multi-worker deployment config.
**Verified:** 2026-07-06
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Per-Requirement Verdicts (INFRA-01..04)

| Req | Verdict | Evidence |
| --- | ------- | -------- |
| INFRA-01 | ✓ VERIFIED | Redis-backed slowapi storage + redis service in the two multi-worker compose files |
| INFRA-02 | ✓ VERIFIED | Fail-open/self-healing outage decision documented in 3 docs + a passing deterministic outage test (unchecked box in REQUIREMENTS.md is a tracking lag, not a gap) |
| INFRA-03 | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Harness + native p95 gate + honest-stack CI job all present and correct; the measured p95 number requires a workflow RUN (human/CI) |
| INFRA-04 | ✓ VERIFIED | Stacked `AUTH_WRITE_LIMIT` on all 3 write routes + passing 21st-POST-429 behavioral test |

### Observable Truths

| # | Truth | Status | Evidence |
| - | ----- | ------ | -------- |
| 1 | REDIS_URL set → shared RedisStorage; unset → memory:// (single-worker-correct) | ✓ VERIFIED | `rate_limit.py:83,105-112` — `storage_uri=REDIS_URL or "memory://"`; `redis>=5,<8` at `requirements.txt:12`; `test_rate_limit_backend.py` (3 tests pass) |
| 2 | Redis outage → 200 within FALLBACK_LIMIT per worker, 429 past cap (bounded fail-open) | ✓ VERIFIED (behavioral) | `rate_limit.py:36,109-111` (`FALLBACK_LIMIT="60/minute"`, `swallow_errors`/`in_memory_fallback_enabled=bool(REDIS_URL)`); `test_rate_limit_fallback.py` monkeypatches `RedisStorage.incr`→`ConnectionError`, asserts 200 up to cap then 429 — PASSES |
| 3 | Process refuses to boot when OVID_WORKERS>1 (or WEB_CONCURRENCY>1) and REDIS_URL unset | ✓ VERIFIED (behavioral) | `rate_limit.py:93-101` import-time `RuntimeError`; `test_startup_guard.py` (4 tests pass) |
| 4 | 21st authed POST /disc in a minute → 429; GET reads unaffected | ✓ VERIFIED (behavioral) | `disc.py:810-812` stacked `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])`; `test_write_rate_limit.py::test_write_limit_caps_disc_submissions_at_21st` + `test_reads_not_throttled_by_write_cap` PASS |
| 5 | POST /disc/register and POST /disc/{fp}/resolve carry the same write ceiling | ✓ VERIFIED | `disc.py:719-721` (register: `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])`); `disc.py:610-611` (resolve: `@limiter.shared_limit(AUTH_WRITE_LIMIT, scope="disc_write:resolve")`, POST-only route so no methods filter needed) |
| 6 | slowapi write limit counts ALL POSTs; anti_sybil cooldown fires independently (layered, D-10) | ✓ VERIFIED | `disc.py:323-331` D-10 seam comment; `evaluate_confirmation` (Postgres SELECT…FOR UPDATE) preserved at `disc.py:331`, not migrated to Redis |
| 7 | prod+test compose define internal redis:7-alpine + REDIS_URL + OVID_WORKERS=4; base compose unchanged | ✓ VERIFIED | `docker-compose.prod.yml:30-62`, `docker-compose.test.yml:28-59` (redis service, healthcheck, depends_on service_healthy, `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`, `REDIS_URL=redis://redis:6379/0`, `OVID_WORKERS=4`); prod redis has no published host port |
| 8 | .env.example documents REDIS_URL + OVID_WORKERS (when required vs optional) | ✓ VERIFIED | `.env.example:24-39` incl. the fail-fast guard note |
| 9 | Outage decision + when-Redis-required + fail-fast guard documented in 3 docs | ✓ VERIFIED | `docs/deployment.md:155-164`, `docs/self-hosting.md:142-144`, `docs/OVID-technical-spec.md:686-691` (fail-open, self-healing, D-01/D-02/D-04) |
| 10 | seed.py bulk-seeds low-thousands of unique deterministic discs via --count, keeps idempotent default | ✓ VERIFIED (behavioral) | `seed.py:49 bulk_seed`, `dvd1-seed-{i}`/`Seed Movie {i}`, `--count` CLI at `seed.py:359-364`; `test_seed.py` (3 tests pass) |
| 11 | locustfile drives 70/20/10 mix and fails run (exit≠0) on p95>500ms or error>1% | ✓ VERIFIED (harness) | `locustfile.py:124-153` (@task 70/20/10), `:156-180` native `events.quitting` gate sets `process_exit_code=1` on p95/error breach |
| 12 | Non-blocking CI job stands up Postgres+Redis+gunicorn -w 4, seeds, runs Locust, publishes p95 — never a PR gate | ✓ VERIFIED (harness) | `loadtest.yml:24-27` (workflow_dispatch + weekly cron only, no push/PR), `:44-62` postgres+redis services, `:123-127` gunicorn -w 4, `:140-147` Locust run, `:149-184` job-summary + upload-artifact |

**Score:** 12/12 truths verified (harness/wiring/behavior). 1 requirement-level item (INFRA-03 measured p95) is present-but-behavior-unverified — routed to human verification.

### Required Artifacts

| Artifact | Status | Details |
| -------- | ------ | ------- |
| `api/app/rate_limit.py` | ✓ VERIFIED | env-driven `storage_uri`, fallback flags, `AUTH_WRITE_LIMIT`, `FALLBACK_LIMIT`, import-time D-06 guard |
| `api/requirements.txt` | ✓ VERIFIED | `redis>=5,<8` (line 12) |
| `api/app/routes/disc.py` | ✓ VERIFIED | stacked write decorators on all 3 write routes + D-10 seam doc |
| `api/scripts/seed.py` | ✓ VERIFIED | `bulk_seed(db, count)` + `--count` CLI, idempotent single-disc default preserved |
| `loadtest/locustfile.py` | ✓ VERIFIED | 70/20/10 mix, native p95 exit-code gate |
| `loadtest/requirements.txt` | ✓ VERIFIED | `locust>=2.44,<3.0`, isolated from api runtime deps |
| `.github/workflows/loadtest.yml` | ✓ VERIFIED | non-blocking honest-stack p95 job |
| compose prod/test | ✓ VERIFIED | redis service + env + healthcheck; base compose untouched |
| `.env.example` | ✓ VERIFIED | REDIS_URL + OVID_WORKERS documented |
| docs (3) | ✓ VERIFIED | outage decision + guard documented |
| Tests (5 files) | ✓ VERIFIED | 17 tests pass (see below) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase-3 rate-limit + seed tests | `.venv/bin/python -m pytest tests/test_rate_limit_backend.py test_rate_limit_fallback.py test_startup_guard.py test_write_rate_limit.py test_seed.py` | 17 passed in 2.06s (exit 0) | ✓ PASS |
| Redis-outage bounded fail-open | `test_rate_limit_fallback::test_redis_outage_falls_back_to_bounded_cap` | pass (200 to cap, then 429) | ✓ PASS |
| Write ceiling 21st-POST-429 + reads unaffected | `test_write_rate_limit` (6 tests) | pass | ✓ PASS |
| D-06 boot guard | `test_startup_guard` (4 tests) | pass | ✓ PASS |
| INFRA-03 measured p95 | (requires `loadtest.yml` run) | not executed | ? SKIP → human |

### Requirements Coverage

| Requirement | Source Plan(s) | Status | Evidence |
| ----------- | -------------- | ------ | -------- |
| INFRA-01 | 03-01, 03-03 | ✓ SATISFIED | Truths 1,7,8; redis dep + compose services |
| INFRA-02 | 03-01, 03-03 | ✓ SATISFIED | Truths 2,3,9; documented decision + passing outage/guard tests |
| INFRA-03 | 03-04 | ? NEEDS HUMAN | Truths 10,11,12 (harness complete + correct); measured p95 needs a CI/human run |
| INFRA-04 | 03-02 | ✓ SATISFIED | Truths 4,5,6; passing write-cap tests |

All 4 phase requirement IDs are declared across the plan frontmatters (03-01: INFRA-01/02; 03-02: INFRA-04; 03-03: INFRA-01/02; 03-04: INFRA-03) and all 4 map to Phase 3 in REQUIREMENTS.md. **No orphaned requirements.**

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| `.planning/REQUIREMENTS.md:58` | INFRA-02 box `- [ ]` unchecked while traceability table says Complete | ⚠️ Warning | Tracking-lag only; INFRA-02 is genuinely delivered. Correct to `- [x]` at completion. |
| fastapi/starlette, slowapi (via test run) | Library `DeprecationWarning`s under local Python 3.14 | ℹ️ Info | Third-party, not OVID code; target is 3.12 (CI). Not a phase blocker. |

No debt markers (TBD/FIXME/XXX), stubs, empty implementations, or hollow data paths found in phase-3 source. The `_submit_payload`/`_register_payload` empty-ish defaults are test fixtures, not shipped stubs.

### Human Verification Required

**1. Produce the authoritative INFRA-03 p95 measurement**

- **Test:** Run the "Load Test (p95)" workflow (`.github/workflows/loadtest.yml`) via `workflow_dispatch`, or wait for the weekly Monday 04:17 UTC schedule. Read p95/p99 from the job summary and the `loadtest-results` artifact.
- **Expected:** p95 ≤ 500ms and error ratio ≤ 1% against the honest stack (Postgres + Redis + `gunicorn -w 4` + live Redis-backed slowapi limiter). Green run (exit 0) is the authoritative evidence.
- **Why human:** INFRA-03's requirement text is "validated by a load test RUN against the actual config." The harness, native gate, seed, and non-blocking CI job are verified present and correct, but the measured p95 is only produced by executing the workflow (deliberately off the per-PR path, per D-12). Harness correctness is proven automatically; the measurement needs a run.

### Gaps Summary

No blocking gaps. INFRA-01, INFRA-02, and INFRA-04 are fully achieved with passing behavioral tests. The multi-worker scaling half of the phase goal ("Fix multi-worker rate-limit scaling") is **complete and verified**: env-driven Redis backend, bounded self-healing outage fallback, fail-fast boot guard, stacked write throttle, and the redis service wired into both `-w 4` compose files.

The latency-budget half ("validate the p95 latency budget against the real config") is **built and correct but not yet measured**: the Locust harness, native p95 exit-code gate, bulk seed, and honest-stack non-blocking CI workflow are all in place and correctly wired to the real Redis-backed multi-worker config — but the authoritative p95 number requires running the workflow, which has not occurred in this session. This is a human/CI verification item, not an implementation gap.

Adjudication of the two flagged items:

- **INFRA-02 checkbox inconsistency:** RESOLVED as a tracking-lag defect. The fail-open/self-healing outage decision is documented in `docs/deployment.md`, `docs/self-hosting.md`, and `docs/OVID-technical-spec.md`, and is tested by `test_rate_limit_fallback.py` (bounded fallback) and `test_startup_guard.py` (guard). REQUIREMENTS.md line 58 should be checked to match the traceability table.
- **INFRA-03 harness-vs-measurement:** Classified as human_needed — the phase cannot be called fully done on the latency-budget clause until a load-test run produces the measured p95.

---

_Verified: 2026-07-06_
_Verifier: Claude (gsd-verifier)_
