# Phase 3: Redis-Backed Rate Limiting & Performance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 3-Redis-Backed Rate Limiting & Performance
**Mode:** advisor (research-backed comparison tables; calibration tier `standard`; technical owner)
**Areas discussed:** Redis outage behavior, Redis as a dependency, Limit policy & values, Load-test methodology

---

## ① Redis outage behavior (INFRA-02)

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory fallback | swallow_errors + in_memory_fallback_enabled, conservative per-worker cap, auto-recovers to Redis | ✓ |
| Fail-open (silent) | swallow_errors=True, no fallback — no enforcement during outage | |
| Fail-closed (503) | Reject when Redis down — blip becomes full API outage | |
| Split reads/writes | Fail-open reads, fail-closed writes — two configs, doubled tests | |

**User's choice:** In-memory fallback.
**Notes:** Locked on the principle that rate limiting is abuse-prevention, not authZ (lookups anonymous, data CC0). Test deterministically by monkeypatching `limits.storage` Redis method to raise `ConnectionError` (repo fs-mock convention) — no container kill required. Route-split deferred.

---

## ② Redis as a dependency (INFRA-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Env-driven + startup guard | REDIS_URL → Redis else memory://; Redis only in prod+test compose; fail-fast boot assertion on multi-worker+memory:// | ✓ |
| Redis mandatory everywhere | Every deployment incl. single-worker self-host runs Redis | |
| Auto-detect workers | Select backend by detecting worker count — fragile | |

**User's choice:** Env-driven + startup guard.
**Notes:** Base docker-compose.yml is also the documented Pi/NAS self-host + mirror path (single worker) where memory:// is already correct — left unchanged. Redis scoped to the two files already running `gunicorn -w 4`. Guard uses an explicit worker-count env, not argv parsing. Preserves self-hosting-first philosophy.

---

## ③ Write-throttle policy & values (INFRA-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Stacked POST limit 20/min;300/hr | Second @limiter.limit(methods=['POST']) on write routes; reads untouched | ✓ |
| Cost-weighted single pool | Shared per-user budget, POST costs ~25x GET | |
| No slowapi write split | Rely only on Phase-2 Postgres cooldown | |

**User's choice:** Stacked method-scoped write limit, `AUTH_WRITE_LIMIT = "20/minute;300/hour"`.
**Notes:** Ground truth — POST /disc always requires auth (no anon write path). Anon-read 100/min and auth-read 500/min left untouched (ARM lookups ~1/166th of anon ceiling). Clean split from Phase 2's Postgres confirmation cooldown = defense-in-depth, not double-counting. "No split" rejected as failing INFRA-04 (fresh-fingerprint floods unthrottled).

---

## ④ Load-test tool + placement (INFRA-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Locust, non-blocking job | Python-native, reuses ovid-client + seed.py; workflow_dispatch/scheduled; 70/20/10 mix | ✓ |
| k6, non-blocking job | Declarative p(95)<500 gate, but adds JS as a third language | |
| Blocking per-PR gate | p95 assertion on every PR — flaky on noisy shared runners | |

**User's choice:** Locust, non-blocking (workflow_dispatch + scheduled) job.
**Notes:** k6 close runner-up (CI-native thresholds) but set aside for Python tooling cohesion. Placement locked non-blocking regardless of tool — absolute-ms p95 on shared runners would generate false failures the project treats as real defects. Validate the honest "actual config": Postgres + gunicorn -w 4 + live Redis limiter.

---

## Cross-cutting decision (D-00, locked without a separate question)

All four research agents flagged that ①②③ form **one backbone**: the Redis migration + fallback config + stacked write limit ship together (a tight write limit and any p95 claim are hollow under `memory://`), and ④'s load test runs *after* the backbone so it validates the real target config. Recorded as CONTEXT D-00.

## Claude's Discretion

- Exact in-memory fallback cap value.
- Startup-guard env-var name (`OVID_WORKERS` vs `WEB_CONCURRENCY`).
- Precise write-limit numbers (shape locked, values tunable).
- Load-test schedule cadence and seed row count.
- Whether `/resolve` and `/register` share the write limit value or differ.

## Deferred Ideas

- Route-type fail-open/fail-closed split (revisit if write-abuse proves distinct).
- Promoting p95 load test to a blocking per-PR gate (needs a dedicated self-hosted runner).
- k6 as the load-test tool (valid future switch).
- Reputation/edit-voting weighting beyond Phase 2's seed (v0.4.0).
