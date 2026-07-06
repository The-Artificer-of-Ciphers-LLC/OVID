# Phase 3: Redis-Backed Rate Limiting & Performance - Research

**Researched:** 2026-07-06
**Domain:** Distributed rate limiting (slowapi + limits + Redis), multi-worker correctness, load testing (Locust)
**Confidence:** HIGH (core slowapi/limits behavior verified by reading the actual installed source at `api/.venv/lib/python3.14/site-packages/`)

## Summary

The entire slowapi/limits API surface this phase depends on was verified against the **actually-installed** versions — `slowapi 0.1.10` and `limits 5.8.0` — by reading their source, not from memory. Every locked decision (D-01 in-memory fallback, D-03 monkeypatch target, D-06 startup guard, D-07 stacked method-scoped write limit) maps cleanly onto native, present-and-verified library features. No custom storage code is required.

Three findings materially shape the plan: (1) the in-memory fallback is a **single global limit that replaces all per-route limits during a Redis outage** — not a per-route fallback — so the fallback cap must be chosen to also cover the read path; (2) slowapi lowercases `methods=` at registration, so `methods=["POST"]` is correct and works, and stacked `@limiter.limit` decorators **accumulate** (both are evaluated) because registration is keyed by `func.__module__.func.__name__` and preserved through `functools.wraps`; (3) `redis-py`'s `from_url` does **not** eagerly connect, so the D-03 outage test can construct a real redis-backed `Limiter` and monkeypatch `RedisStorage.incr` to raise `ConnectionError` **without any live Redis** — exactly matching the repo's fs-mock IO-failure convention.

Two compatibility guardrails: `limits 5.8.0` constrains its redis extra to `redis>3,<8.0.0`, but the current redis-py is **8.0.1** — an unpinned `redis` dependency would install 8.x and fall outside limits' supported range. Pin `redis>=5,<8`. And `api/scripts/seed.py` EXISTS and currently seeds exactly **one** disc; D-13's "low-thousands of rows" requires extending it (a Wave 0 gap, not creating the script from scratch).

**Primary recommendation:** Read `REDIS_URL` in `rate_limit.py`; when set, build the `Limiter` with `storage_uri=redis://…`, `swallow_errors=True`, `in_memory_fallback_enabled=True`, and a single conservative `in_memory_fallback=[FALLBACK_LIMIT]`; add a module-level fail-fast guard raising when `OVID_WORKERS > 1` and `REDIS_URL` is unset; stack `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` above the existing `@limiter.limit(_dynamic_limit)` on the three write routes; add `redis>=5,<8` to `api/requirements.txt` and a `redis:7-alpine` service to the prod+test compose files only; validate p95 with a Locust job gated via the `events.quitting` hook.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Shared cross-worker rate counters (INFRA-01) | Redis (storage) | API bootstrap (`rate_limit.py`) | Counters must be shared state across gunicorn workers; only an out-of-process store gives that |
| Outage degradation (INFRA-02) | API (slowapi in-memory fallback) | Redis (recovery probe) | Fallback is per-worker local; library self-heals when Redis returns |
| Write throttle (INFRA-04) | API (decorator, pre-handler) | Redis (counter) | Coarse volumetric ceiling enforced at the route boundary before business logic |
| Confirmation cooldown (Phase 2, NOT this phase) | Postgres (`anti_sybil.py`) | — | Semantic gate on verify-edits; worker-safe via `SELECT … FOR UPDATE`; must stay on Postgres (D-10) |
| p95 latency proof (INFRA-03) | Load harness (Locust) | CI (scheduled job) | External black-box measurement against the real gunicorn+Redis+Postgres stack |
| Backend selection + startup guard (D-05a/D-06) | API bootstrap (`rate_limit.py`/`main.py`) | Compose env | Env-driven config read once at import; fail-fast on misconfiguration |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `slowapi` | `0.1.10` (installed; pinned `>=0.1.9,<1.0`) | FastAPI rate-limit decorators + storage abstraction | Already the repo's limiter; native Redis + fallback support `[VERIFIED: read installed source]` |
| `limits` | `5.8.0` (transitive of slowapi) | Storage backends (`MemoryStorage`, `RedisStorage`), strategies | slowapi's engine; `RedisStorage` is the shared-counter backend `[VERIFIED: installed METADATA + source]` |
| `redis` (redis-py) | pin `>=5,<8` | Python Redis client that `limits.RedisStorage` wraps | Official client; `limits[redis]` requires `redis>3,<8.0.0` `[VERIFIED: limits 5.8.0 METADATA]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `locust` | `>=2.44,<3.0` (latest 2.44.4) | Load-test harness for INFRA-03 | Load-test job only — NOT an API runtime dep; lives in `loadtest/requirements.txt` `[VERIFIED: PyPI web]` |
| `redis:7-alpine` (Docker) | 7.x (8.x GA available) | Shared rate-limit store for prod/test compose | Multi-worker deployments only (prod + test); ephemeral counters, no volume needed `[ASSUMED]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Locust | k6 | k6's `thresholds: {http_req_duration: ['p(95)<500']}` is a zero-glue native gate, but adds JS as a third language (D-11 rejects on tooling-cohesion) |
| `redis:7-alpine` | `valkey` / `redis:8-alpine` | limits 5.8.0 natively supports `valkey://` scheme; redis:8 works but redis-py `<8` pin keeps client/limits aligned |
| In-memory fallback (D-01) | Fail-closed / pure fail-open | D-02 locks fallback: rate limiting is abuse-prevention, not authz; fail-closed would turn a Redis blip into a full lookup outage |

**Installation:**
```bash
# api/requirements.txt — add one line:
redis>=5,<8

# loadtest/requirements.txt (new file) — isolated from API runtime:
locust>=2.44,<3.0
```

**Version verification:** `slowapi 0.1.10` and `limits 5.8.0` confirmed via `importlib.metadata.version` in `api/.venv`. `redis 8.0.1` and `locust 2.44.4` are the current PyPI latest (web-verified); the `redis>=5,<8` upper bound is dictated by `limits 5.8.0`'s own extra constraint `redis!=4.5.2,!=4.5.3,<8.0.0,>3` `[VERIFIED: limits-5.8.0.dist-info/METADATA]`. In-sandbox `pip index versions` is network-blocked; confirm final pins during planning with `.venv/bin/pip index versions redis`.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `redis` | PyPI | ~13 yrs | ~40M+/wk | github.com/redis/redis-py (official) | OK | Approved — pin `>=5,<8` |
| `locust` | PyPI | ~14 yrs | ~2M+/wk | github.com/locustio/locust | OK | Approved — loadtest dep only |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Both are long-established, first-party official projects. Registry lookups were network-blocked in-sandbox; verdicts are based on well-known provenance (`redis/redis-py`, `locustio/locust`) and should be reconfirmed with `.venv/bin/pip index versions` during planning. No postinstall-script risk (pure Python wheels).

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────────┐
   HTTP request          │  gunicorn -w 4 (UvicornWorker)  [prod/test] │
   ──────────────▶       │                                             │
                         │   worker1   worker2   worker3   worker4     │
                         │      │         │         │         │        │
                         │      └────┬────┴────┬────┴────┬────┘        │
                         │           ▼         ▼         ▼             │
                         │   @limiter.limit(_dynamic_limit)  ← reads   │
                         │   @limiter.limit(AUTH_WRITE_LIMIT,          │
                         │                  methods=["POST"]) ← writes │
                         │           │                                 │
                         │           ▼  Limiter._check_request_limit   │
                         └───────────┼─────────────────────────────────┘
                                     │ storage.incr(key,expiry)
                    REDIS_URL set?   │
              ┌──────────yes─────────┼─────────no──────────┐
              ▼                      ▼                      ▼
      ┌───────────────┐    ConnectionError?         memory:// (single
      │ RedisStorage  │    ┌────────┴────────┐       worker / self-host —
      │ (shared,      │    │ swallow_errors  │       already correct;
      │  cross-worker)│    │ + fallback:     │       guard blocks -w>1)
      └───────┬───────┘    │ _storage_dead=  │
              │            │ True → per-      │
     correct N/window      │ worker Memory   │
     (INFRA-01)            │ Storage @        │
                           │ FALLBACK_LIMIT   │  auto-probe recovery on
                           │ (INFRA-02)       │  exp-backoff → switch back
                           └──────────────────┘

   ── separate: POST-that-is-a-confirmation also hits ──▶ anti_sybil.py
      (Postgres SELECT…FOR UPDATE cooldown) — layered, NOT redundant (D-10)

   INFRA-03: Locust job → real gunicorn-w4 + Redis + Postgres → p95 gate
```

### Component Responsibilities
| File | Change |
|------|--------|
| `api/app/rate_limit.py` | Read `REDIS_URL` → `storage_uri`; add fallback flags; add `AUTH_WRITE_LIMIT` constant; module-level worker/redis fail-fast guard |
| `api/main.py` | (Alternative guard location) app-bootstrap assertion; no other change — limiter wiring already correct |
| `api/app/routes/disc.py` | Stack second `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` on `submit_disc` (POST /disc), register (POST /disc/register), `resolve_dispute_endpoint` (POST /disc/{fingerprint}/resolve) |
| `api/requirements.txt` | `redis>=5,<8` |
| `docker-compose.prod.yml`, `docker-compose.test.yml` | `redis:7-alpine` service + `REDIS_URL` + `OVID_WORKERS=4` env; `docker-compose.yml` UNCHANGED |
| `api/scripts/seed.py` | Extend for bulk low-thousands seeding (D-13) — Wave 0 gap (exists, modify) |
| `loadtest/` (new) | Locustfile + `requirements.txt` + p95 gate |
| `.github/workflows/loadtest.yml` (new) | `workflow_dispatch` + `schedule`, non-blocking |

### Pattern 1: Env-driven backend selection with fallback (D-05a/D-01)
**What:** `rate_limit.py` picks storage from `REDIS_URL`, wiring the native fallback.
**When to use:** At module import, where the `Limiter` is already constructed.
```python
# Source: VERIFIED against slowapi/extension.py Limiter.__init__ (installed 0.1.10)
import os

UNAUTH_LIMIT = "100/minute"
AUTH_LIMIT = "500/minute"
AUTH_WRITE_LIMIT = "20/minute;300/hour"   # D-07/D-08 — named, tunable
FALLBACK_LIMIT = "60/minute"              # D-01 conservative per-worker cap (Claude's discretion)

_redis_url = os.environ.get("REDIS_URL")
_storage_uri = _redis_url or "memory://"

limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri=_storage_uri,
    swallow_errors=bool(_redis_url),                 # only meaningful with Redis
    in_memory_fallback_enabled=bool(_redis_url),
    in_memory_fallback=[FALLBACK_LIMIT] if _redis_url else [],
)
```
**Verified behavior:** `Limiter.__init__` signature includes `swallow_errors`, `in_memory_fallback`, `in_memory_fallback_enabled` (all present in 0.1.10). Passing `in_memory_fallback=[...]` auto-sets `_in_memory_fallback_enabled=True` and constructs a `MemoryStorage`-backed `_fallback_limiter`. `redis.from_url` (called inside `RedisStorage.__init__`) does **not** connect eagerly, so import never blocks on Redis availability.

### Pattern 2: Fail-fast startup guard (D-06)
**What:** Refuse to boot when multi-worker + `memory://`.
**When to use:** Module-level in `rate_limit.py` (cohesive with the `REDIS_URL` read) — mirrors the existing fail-fast `_require_env` pattern in `api/app/auth/config.py`.
```python
# Explicit env var (D-06) — NOT argv parsing
_workers = int(os.environ.get("OVID_WORKERS", os.environ.get("WEB_CONCURRENCY", "1")))
if _workers > 1 and not _redis_url:
    raise RuntimeError(
        "OVID_WORKERS=%d requires REDIS_URL — memory:// gives each worker an "
        "independent counter (Nx rate-limit inflation). Set REDIS_URL or run 1 worker."
        % _workers
    )
```
Add `OVID_WORKERS: 4` (or reuse `WEB_CONCURRENCY`) to the prod+test compose `api` env alongside the existing `-w 4`.

### Pattern 3: Stacked method-scoped write limit (D-07)
**What:** Add a second decorator; both accumulate and are evaluated.
```python
# Source: VERIFIED against slowapi/extension.py __limit_decorator + __evaluate_limits
@router.post("/disc", response_model=DiscSubmitResponse, status_code=201)
@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])   # NEW — tighter write ceiling
@limiter.limit(_dynamic_limit)                        # existing — read/write tier
async def submit_disc(request: Request, ...): ...
```
**Verified stacking semantics:**
- Registration keys on `f"{func.__module__}.{func.__name__}"`; `functools.wraps` preserves the name through both wrappers, so both limits register under the **same** endpoint key and are combined (`route_limits = limits + dynamic_limits`) — **both are evaluated**, not overwritten.
- `_check_request_limit` runs once per request (guarded by `request.state._rate_limiting_complete`); the single call evaluates all accumulated limits and `break`s on the first exceeded one → `RateLimitExceeded`. The stricter `20/minute` trips first.
- `methods=["POST"]` is lowercased at `LimitGroup` construction (`wrappers.py:89`), then matched via `request.method.lower() not in lim.methods` — so `["POST"]` correctly matches POST. (Documenting because the raw comparison looks case-mismatched but is safe due to the normalization.)
- Both limits share `_auth_aware_key` → key `user:{id}`; each limit item has its own storage namespace, so no cross-decrement.

### Anti-Patterns to Avoid
- **Migrating the Phase-2 confirmation cooldown onto Redis/slowapi** — D-10 explicitly forbids it; `anti_sybil.py` stays Postgres-backed. They layer (slowapi = raw request rate; anti-Sybil = count of verify-edits).
- **Auto-detecting worker count from gunicorn argv** — D-06 rejects fragile argv scraping; use an explicit env var.
- **Adding `redis` to the base `docker-compose.yml`** — that's the single-worker self-host/mirror path where `memory://` is correct; forcing Redis there breaks the Pi/NAS low-friction story (D-05a).
- **Unpinned `redis`** — pip would resolve 8.0.1, outside limits 5.8.0's `<8.0.0` supported range.
- **Persisting Redis rate-limit data** — counters are short-window ephemeral; no volume, optionally `--save ""`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Redis-outage degradation | Custom try/except around every limit + manual fallback store | `swallow_errors=True` + `in_memory_fallback_enabled=True` + `in_memory_fallback=[...]` | Native; includes exp-backoff auto-recovery (`__should_check_backend`) `[VERIFIED]` |
| Cross-worker counters | Custom Postgres/Redis counter for the general limiter | `storage_uri="redis://…"` | One-line swap; `RedisStorage` handles atomicity |
| p95 threshold gate | Custom CSV parser | `events.quitting` + `stats.total.get_response_time_percentile(0.95)` + `process_exit_code` | Native exit-code gate; no glue `[CITED: Locust docs]` |
| Method-scoped limiting | Manual `if request.method == "POST"` branches | `@limiter.limit(..., methods=["POST"])` | Native param, evaluated in `__evaluate_limits` |

**Key insight:** Every INFRA-01/02/04 mechanism is a present, verified slowapi/limits feature. The only new code is configuration wiring, one guard, one constant, three decorators, and the (separate) load harness.

## Common Pitfalls

### Pitfall 1: In-memory fallback replaces ALL per-route limits, globally
**What goes wrong:** Assuming each route keeps its own limit during a Redis outage.
**Why it happens:** When `_storage_dead=True`, `_check_request_limit` uses `all_limits = list(itertools.chain(*self._in_memory_fallback))` — the route's `_dynamic_limit`/`AUTH_WRITE_LIMIT` are **ignored** and the single `FALLBACK_LIMIT` applies to every endpoint, per worker.
**How to avoid:** Choose `FALLBACK_LIMIT` conservatively enough to protect the read path too (proposed `60/minute` per worker — with 4 workers that's ~240/min aggregate during an outage, well under normal ceilings but non-zero protection). Document that during an outage all routes share this one cap.
**Warning signs:** Load-test or outage test shows reads throttled at an unexpected rate while Redis is down.

### Pitfall 2: FastAPI body validation short-circuits before the rate-limit check
**What goes wrong:** A write-limit test firing 21 POSTs with an **invalid** body never trips 429.
**Why it happens:** The slowapi decorator wraps the endpoint function, but FastAPI resolves/validates the Pydantic body **before** invoking the (wrapped) endpoint. A 422 returns before `_check_request_limit` runs, so it doesn't consume the counter.
**How to avoid:** The INFRA-04 test must send **auth'd, schema-valid** payloads (reuse `matrix_matching_submit_payload()` from `conftest.py`) so the rate-limit gate is actually reached. Each valid POST counts (duplicates return 2xx `disputed`/duplicate — still counted).
**Warning signs:** Test sends 21 requests, all 422, no 429.

### Pitfall 3: D-03 outage test needs a Redis-configured limiter, but the app limiter is `memory://` in tests
**What goes wrong:** `REDIS_URL` is unset in the pytest env → the app's `limiter` is pure `memory://` with no fallback wiring, so monkeypatching `RedisStorage.incr` does nothing.
**Why it happens:** `conftest.py` sets `DATABASE_URL=sqlite://` and never sets `REDIS_URL`; the autouse `_reset_rate_limiter` resets the app limiter.
**How to avoid:** The D-03 test constructs its **own** `Limiter(storage_uri="redis://localhost:6379", swallow_errors=True, in_memory_fallback_enabled=True, in_memory_fallback=[SMALL_CAP])`, mounts it on a minimal FastAPI app + `TestClient`, monkeypatches `limits.storage.RedisStorage.incr` (and `.check`) to raise `redis.exceptions.ConnectionError`, asserts 200 within the fallback cap then 429 once exceeded, and **restores in `finally`**. No live Redis (see Pitfall 4). This is the exact fs-mock IO-failure shape from CLAUDE.md.
**Warning signs:** Patched method never called; limiter still hitting MemoryStorage.

### Pitfall 4: Monkeypatch target must be the storage method the strategy actually calls
**What goes wrong:** Patching `.get` when the default fixed-window strategy calls `.incr`.
**Why it happens:** slowapi default strategy is `fixed-window`; `FixedWindowRateLimiter.hit()` calls `self.storage.incr(key, expiry, amount=cost)` — verified in `limits/strategies.py`. `.get` is not on the hot path for `hit()`.
**How to avoid:** Patch `limits.storage.RedisStorage.incr` to raise `redis.exceptions.ConnectionError`. slowapi's `_check_request_limit` catches it (`except Exception`), sets `_storage_dead=True`, and retries against the fallback limiter. (If a non-default strategy is ever configured, re-check the method.)
**Warning signs:** ConnectionError raised but slowapi doesn't fall back (wrong method patched, exception bypasses the `hit` path).

### Pitfall 5: `redis` unpinned pulls 8.x, outside limits' supported range
**What goes wrong:** `pip install redis` grabs 8.0.1; `limits 5.8.0` supports `<8.0.0`.
**How to avoid:** Pin `redis>=5,<8` in `api/requirements.txt`.
**Warning signs:** Subtle RedisStorage behavior differences or resolver warnings.

## Runtime State Inventory

> This is a config/dependency phase (not a rename), but Redis introduces new runtime state.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Redis rate-limit counters (short-window, ephemeral) | None — do NOT persist; fresh Redis on restart is fine |
| Live service config | New `redis` service in prod+test compose; `REDIS_URL` env consumed at API import | Add service + env; base compose unchanged |
| OS-registered state | None | None — no schedulers/daemons beyond the existing `sync` profile |
| Secrets/env vars | `REDIS_URL` (internal, no auth on internal network); `OVID_WORKERS`/`WEB_CONCURRENCY` | Add to `.env.example`, prod+test compose; if Redis ever exposed externally, add `AUTH`/`rediss://` |
| Build artifacts | `redis` wheel added to the API image; `locust` isolated to `loadtest/` | Rebuild API image; load harness deps separate |

## Common Pitfalls → Validation crosswalk

See Validation Architecture below; each pitfall has a corresponding test/observation.

## Code Examples

### Locust harness with native p95 gate (INFRA-03)
```python
# Source: [CITED: Locust docs — running-without-web-ui.rst, via Context7]
# loadtest/locustfile.py
import logging
from locust import HttpUser, task, between, events

P95_BUDGET_MS = 500  # INFRA-03

class OvidUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(70)  # D-13: ~70% lookups
    def lookup(self):
        self.client.get(f"/v1/disc/{self._fp()}", name="/v1/disc/[fp]")

    @task(20)  # ~20% search
    def search(self):
        self.client.get("/v1/search?q=matrix", name="/v1/search")

    @task(10)  # ~10% submit (auth'd)
    def submit(self):
        self.client.post("/v1/disc", json=self._payload(),
                         headers=self._auth, name="/v1/disc[POST]")

@events.quitting.add_listener
def _gate(environment, **kw):
    p95 = environment.stats.total.get_response_time_percentile(0.95)
    if environment.stats.total.fail_ratio > 0.01:
        logging.error("FAIL: error ratio > 1%%"); environment.process_exit_code = 1
    elif p95 > P95_BUDGET_MS:
        logging.error("FAIL: p95 %dms > %dms", p95, P95_BUDGET_MS)
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0
```
Run: `locust -f loadtest/locustfile.py --headless -u 100 -r 10 -t 3m --host http://localhost:8000 --csv loadtest/results`. Publish `loadtest/results_stats.csv` as a CI artifact; the exit code gates the (non-blocking) job. Reuse `ovid-client`'s auth/httpx helpers (`client.py`) for the submit token (D-11).

### Compose redis service (prod + test only)
```yaml
# Source: [ASSUMED] — standard redis compose shape
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no"]  # ephemeral counters
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
  api:
    depends_on:
      db: { condition: service_healthy }
      redis: { condition: service_healthy }
    environment:
      REDIS_URL: redis://redis:6379/0
      OVID_WORKERS: "4"
```
Do **not** publish a host port for `redis` in prod (internal-only, like the prod `db`).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `storage_uri="memory://"` (per-worker) | `redis://` shared store with in-memory fallback | This phase | Correct cross-worker limits (INFRA-01) |
| redis-py 4.x `aioredis` split | redis-py unified (5.x+), RESP3 default in 8.x | redis-py 5→8 | Pin `<8` to stay within limits 5.8.0 range |
| Locust `TaskSet`/`Locust` base | `HttpUser` + `@task` weights + `events.quitting` gate | Locust 1.0+ | Modern class API; native exit-code p95 gate |

**Deprecated/outdated:** `aioredis` (folded into redis-py); Locust `Locust`/`TaskSet`-only style (use `HttpUser`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `redis:7-alpine` is the right image tag (vs 8-alpine/valkey) | Standard Stack | Low — both work; 7-alpine conservative |
| A2 | `FALLBACK_LIMIT = "60/minute"` per-worker is an appropriate conservative default | Pattern 1 / Pitfall 1 | Medium — too low throttles reads during outage; too high = weak protection. Tunable named constant; confirm with user |
| A3 | `locust>=2.44,<3.0` / `redis>=5,<8` exact pins | Standard Stack | Low — ranges web/METADATA-verified; reconfirm with `pip index versions` |
| A4 | Redis stays internal-only (no external port, no AUTH) | Runtime State / Security | Medium — if exposed, needs `rediss://`/AUTH |
| A5 | `OVID_WORKERS` (new) vs reusing `WEB_CONCURRENCY` | Pattern 2 | Low — D-06 leaves the name to Claude's discretion |
| A6 | Scheduled cadence nightly vs weekly for the load-test job | Validation | Low — D-12 leaves to planner |

## Open Questions

1. **Should the write throttle on `/disc/register` and `/disc/{fingerprint}/resolve` use the same value as `POST /disc`?**
   - What we know: D-07 lists all three; CONTEXT Claude's-Discretion says these two are lower-volume and the value is the planner's call.
   - Recommendation: Same `AUTH_WRITE_LIMIT` for all three initially (simplest, named constant); split only if usage data later warrants.
2. **Does the CI load-test job build the API image or run gunicorn directly with GitHub `services:` for redis/postgres?**
   - What we know: D-14 requires `gunicorn -w 4` + live Redis + Postgres (not SQLite/TestClient).
   - Recommendation: Use GitHub Actions `services: {postgres, redis}`, `pip install -r api/requirements.txt`, launch `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` in the background, seed via the extended `api/scripts/seed.py`, then run Locust. Avoids docker-compose-in-CI complexity while honoring D-14.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + Compose | prod/test stacks, self-host | ✓ (project standard) | — | — |
| PostgreSQL 16 | load test honest config (D-14) | ✓ | 16-alpine | — |
| gunicorn | multi-worker target | ✓ | `>=21.2,<24` (in requirements) | — |
| Redis | INFRA-01 shared store | ✗ (new) | add `redis:7-alpine` + `redis>=5,<8` | `memory://` at single worker only |
| `redis` (py client) | RedisStorage | ✗ (not in venv) | add `>=5,<8` | none — required for redis backend |
| Locust | INFRA-03 | ✗ (new) | `loadtest/requirements.txt` | none — required for load test |

**Missing dependencies with no fallback:** `redis` client + `locust` — must be installed (planner adds them).
**Missing dependencies with fallback:** Redis server — `memory://` remains correct for the single-worker base/self-host path.

## Validation Architecture

> Nyquist validation ENABLED for this phase.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=7` (API), in-memory SQLite via FastAPI `TestClient` |
| Config file | none detected — pytest defaults; fixtures in `api/tests/conftest.py` |
| Quick run command | `cd api && .venv/bin/python -m pytest tests/test_rate_limit.py -x` |
| Full suite command | `cd api && .venv/bin/python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `REDIS_URL` set → `limiter._storage` is `RedisStorage`; unset → `MemoryStorage` | unit | `pytest tests/test_rate_limit_backend.py -x` | ❌ Wave 0 |
| INFRA-01 | Cross-worker correctness: limit ≈ N not 4N under `gunicorn -w 4` + shared Redis | integration | load-test job assertion / optional compose test | ❌ Wave 0 (not unit-testable in single-process SQLite) |
| INFRA-02 | Redis outage → fallback active: 200 within `FALLBACK_LIMIT`, 429 once exceeded (monkeypatch `RedisStorage.incr`→`ConnectionError`, restore in finally) | unit | `pytest tests/test_rate_limit_fallback.py -x` | ❌ Wave 0 |
| INFRA-02 | (optional secondary) docker-compose stop-redis recovery probe | integration | manual / non-blocking | ❌ optional |
| INFRA-03 | p95 ≤ 500ms against real Redis+gunicorn-w4+Postgres | load test | `locust -f loadtest/locustfile.py --headless … ` (exit-code gated) | ❌ Wave 0 |
| INFRA-04 | 21st auth'd valid POST /disc within a minute → 429; GET unaffected; stacks over `_dynamic_limit` | unit | `pytest tests/test_write_rate_limit.py -x` | ❌ Wave 0 |
| INFRA-04 | Write limit does NOT double-count with anti_sybil cooldown (D-10 seam) | unit | assert both fire independently on a confirmation POST | ❌ Wave 0 |
| D-06 | Boot raises when `OVID_WORKERS>1` and `REDIS_URL` unset | unit | `pytest tests/test_startup_guard.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_rate_limit*.py tests/test_write_rate_limit.py tests/test_startup_guard.py -x`
- **Per wave merge:** full `pytest tests/` (must stay green — existing `test_rate_limit.py` relies on `memory://`, which the env-driven default preserves when `REDIS_URL` unset)
- **Phase gate:** full suite green + one manual/scheduled Locust run showing p95 ≤ 500ms before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `api/tests/test_rate_limit_backend.py` — backend-selection (INFRA-01 unit)
- [ ] `api/tests/test_rate_limit_fallback.py` — D-03 outage monkeypatch (INFRA-02)
- [ ] `api/tests/test_write_rate_limit.py` — stacked write limit + D-10 non-double-count (INFRA-04)
- [ ] `api/tests/test_startup_guard.py` — D-06 fail-fast
- [ ] `loadtest/locustfile.py` + `loadtest/requirements.txt` — INFRA-03
- [ ] `.github/workflows/loadtest.yml` — non-blocking scheduled job
- [ ] `api/scripts/seed.py` bulk-seed mode (low-thousands rows, D-13) — exists, currently seeds ONE disc
- [ ] Regression check: existing `test_rate_limit.py` still passes unchanged (env-driven default keeps `memory://` in test env)

## Security Domain

> `security_enforcement` assumed enabled (absent in config = enabled). Rate limiting IS the security control in scope.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Write path already `Depends(get_current_user)` — every write keyed `user:{id}` (D-09) |
| V4 Access Control | no | Rate limiting is abuse-prevention, NOT an authz boundary (D-02) — data is public/CC0 |
| V5 Input Validation | no (unchanged) | Existing Pydantic schemas |
| V7 Error Handling / Logging | yes | 429 keeps the structured JSON envelope + `request_id`; outage logs a warning, never leaks internals |
| V11/V13 Anti-automation (business logic / API abuse) | yes | slowapi general limiter (Redis) + stacked write throttle + Phase-2 Postgres cooldown (defense-in-depth) |

### Known Threat Patterns for FastAPI + Redis rate limiting
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Multi-worker counter inflation (current defect) | Tampering / DoS bypass | Redis shared store (INFRA-01) + fail-fast guard (D-06) |
| New dependency (Redis) as availability single-point | Denial of Service | In-memory fallback + auto-recovery (D-01/INFRA-02); never fail-closed on read path |
| Write flood of novel fingerprints (non-confirmations escape Phase-2 cooldown) | DoS / spam | Stacked `AUTH_WRITE_LIMIT` volumetric ceiling (INFRA-04/D-09) |
| Redis exposed on network | Information Disclosure / Tampering | Internal-only service, no host port in prod; `rediss://`+AUTH if ever external |
| Retry-After / limit info leakage | Information Disclosure | Existing handler exposes only limit string + retry_after (acceptable, unchanged) |

## Sources

### Primary (HIGH confidence)
- Installed source `api/.venv/.../slowapi/extension.py` (0.1.10) — `Limiter.__init__` params, `__evaluate_limits`, `_check_request_limit`, `__limit_decorator`, `__should_check_backend`, fallback wiring
- Installed source `api/.venv/.../slowapi/wrappers.py` — `methods` lowercasing (line 89)
- Installed source `api/.venv/.../limits/` — `RedisStorage.__init__` (lazy `from_url`), `FixedWindowRateLimiter.hit`→`incr`, storage class names
- `api/.venv/.../limits-5.8.0.dist-info/METADATA` — redis extra constraint `redis!=4.5.2,!=4.5.3,<8.0.0,>3`
- Repo code: `rate_limit.py`, `main.py`, `anti_sybil.py`, `routes/disc.py`, `conftest.py`, `test_rate_limit.py`, `api/scripts/seed.py`, compose files, `Dockerfile`, `03-CONTEXT.md`, `REQUIREMENTS.md`

### Secondary (MEDIUM confidence)
- Context7 `/locustio/locust` — headless/CSV, `@task` weights, `events.quitting` + `get_response_time_percentile(0.95)` + `process_exit_code`
- PyPI (web) — redis-py 8.0.1 latest (py>=3.10); Locust 2.44.4 latest (py 3.10–3.14)

### Tertiary (LOW confidence)
- Redis Docker image tag choice (`7-alpine` vs `8-alpine`) — assumed, not blocking

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions read from installed metadata; compatibility range from limits METADATA
- Architecture (fallback, stacking, guard): HIGH — verified by reading installed slowapi/limits source
- Pitfalls: HIGH — derived directly from source-level behavior (fallback-global-replacement, body-validation ordering, monkeypatch target)
- Load-test API: MEDIUM — Context7 + web; not executed in-session
- Redis/Locust exact pins: MEDIUM — web-verified, registry lookup network-blocked in-sandbox

**Research date:** 2026-07-06
**Valid until:** ~2026-08-06 (stable libraries; re-verify redis/locust pins if regenerated)
