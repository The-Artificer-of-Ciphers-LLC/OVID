# Phase 3: Redis-Backed Rate Limiting & Performance - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 11 (7 modify, 4 create)
**Analogs found:** 9 / 11 (2 create-net-new with partial/no analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `api/app/rate_limit.py` (MODIFY) | config | request-response | itself (existing `Limiter` setup) + `api/app/auth/config.py` (fail-fast env) | exact |
| `api/main.py` (MODIFY) | config/bootstrap | request-response | itself (existing limiter wiring, lines 45-50) | exact |
| `api/app/routes/disc.py` (MODIFY) | route | request-response (writes) | existing `@limiter.limit(_dynamic_limit)` decorators on same routes | exact |
| `api/requirements.txt` (MODIFY) | config | — | existing pinned deps in same file | exact |
| `docker-compose.prod.yml` (MODIFY) | config | — | base `db` (postgres) service in `docker-compose.yml` | exact (healthcheck shape) |
| `docker-compose.test.yml` (MODIFY) | config | — | base `db` service + existing `api` service env block | exact |
| `api/scripts/seed.py` (MODIFY — exists, seeds one disc) | utility | batch / file-I/O | `api/tests/conftest.py::seed_test_disc` (line 131) | role-match (no standalone script analog) |
| `api/tests/test_rate_limit_fallback.py` (CREATE) | test | request-response | `api/tests/test_rate_limit.py` + CLAUDE.md fs-mock IO-failure convention | role-match |
| `api/tests/test_write_rate_limit.py` (CREATE) | test | request-response | `api/tests/test_rate_limit.py` (line 24 auth pattern) + `conftest.matrix_matching_submit_payload` | exact |
| `api/tests/test_startup_guard.py` (CREATE) | test | — | `api/tests/test_rate_limit.py` (import-time behavior) | role-match |
| `loadtest/locustfile.py` + `loadtest/requirements.txt` (CREATE) | test/harness | request-response | RESEARCH.md §Code Examples only — **no in-repo analog** | none |
| `.github/workflows/loadtest.yml` (CREATE) | config/CI | — | `.github/workflows/ci.yml` (job/step shape) | role-match |

## Pattern Assignments

### `api/app/rate_limit.py` (config, request-response)

**Analog:** itself — the existing `Limiter` construction (lines 65-69) plus the fail-fast env pattern from `api/app/auth/config.py` (lines 6-18).

**Existing Limiter construction to modify** (`api/app/rate_limit.py` lines 65-69):
```python
limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri="memory://",
)
```

**Existing named-constant style to extend** (lines 22-23) — add `AUTH_WRITE_LIMIT` / `FALLBACK_LIMIT` here in the same `UPPER_SNAKE_CASE` block:
```python
UNAUTH_LIMIT = "100/minute"
AUTH_LIMIT = "500/minute"
```

**Fail-fast env pattern to copy** (`api/app/auth/config.py` lines 6-18) — the module-level `raise RuntimeError(...)` at import time is the exact convention the D-06 guard must follow:
```python
def _require_env(name: str) -> str:
    """Return an env var or raise with a clear message at import time."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"Set it in .env or export it before starting the API."
        )
    return value
```

**Target shape** (per RESEARCH.md Pattern 1 + 2, verified against slowapi 0.1.10): read `REDIS_URL` → `storage_uri`; add `swallow_errors=bool(_redis_url)`, `in_memory_fallback_enabled=bool(_redis_url)`, `in_memory_fallback=[FALLBACK_LIMIT] if _redis_url else []`; add module-level guard `if int(os.environ.get("OVID_WORKERS", os.environ.get("WEB_CONCURRENCY","1"))) > 1 and not _redis_url: raise RuntimeError(...)`. The 429 handler (lines 72-96) stays unchanged — reuse its structured JSON envelope for any new output.

---

### `api/main.py` (config/bootstrap, request-response)

**Analog:** itself — existing limiter wiring (lines 45-50). No `SlowAPIMiddleware`; enforcement is decorator-based (`auto_check=True`).

**Existing wiring** (lines 49-50) — the guard (D-06) is preferred in `rate_limit.py` at import; if placed here instead, it goes near this block:
```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```
Note: `main.py` imports `from app.rate_limit import UNAUTH_LIMIT, limiter, rate_limit_exceeded_handler` (line 14) — a module-level guard in `rate_limit.py` fires on this import automatically, so `main.py` likely needs **no change** (RESEARCH.md Component Map).

---

### `api/app/routes/disc.py` (route, request-response — writes)

**Analog:** the existing single decorator already on each write route.

**Existing pattern** (`api/app/routes/disc.py` lines 789-796) — the stacked write limit adds ONE line above the existing decorator:
```python
@router.post("/disc", response_model=DiscSubmitResponse, status_code=201)
@limiter.limit(_dynamic_limit)
def submit_disc(
    body: DiscSubmitRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
```

**Target** (D-07, verified stacking in RESEARCH.md Pattern 3):
```python
@router.post("/disc", response_model=DiscSubmitResponse, status_code=201)
@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])   # NEW — tighter write ceiling
@limiter.limit(_dynamic_limit)                        # existing
def submit_disc(...):
```

**Three write routes to throttle** (all already carry `@limiter.limit(_dynamic_limit)`):
- `POST /disc` → `submit_disc` (line 789) — always `Depends(get_current_user)` (line 794)
- `POST /disc/register` → line 699
- `POST /disc/{fingerprint}/resolve` → `resolve_dispute_endpoint` (line 590)

**D-10 seam (do NOT double-count):** `_handle_existing_disc` (line 268) calls `evaluate_confirmation(db, existing, current_user, request)` (line 322), which writes a `disc_edits` row with `edit_type="verify"` (line 367). The slowapi write limit is a coarse pre-handler request-rate ceiling; `anti_sybil.evaluate_confirmation` (`CONFIRMATION_MAX_PER_WINDOW=5`, `CONFIRMATION_MAX_PER_DAY=20`, `anti_sybil.py` lines 56-57) is a narrower semantic gate inside the handler. Add a one-line doc note distinguishing them; do NOT migrate anti_sybil onto Redis.

---

### `api/requirements.txt` (config)

**Analog:** existing pinned/range deps in the same file. Add one line: `redis>=5,<8` (RESEARCH.md Pitfall 5 — unpinned pulls 8.x, outside `limits 5.8.0`'s `<8.0.0` range). Keep the existing `>=X,<Y` range-pin style.

---

### `docker-compose.prod.yml` / `docker-compose.test.yml` (config)

**Analog:** the base `db` (postgres) service in `docker-compose.yml` (lines 3-19) — copy its healthcheck/restart shape.

**Base `db` service to mirror** (`docker-compose.yml` lines 3-19):
```yaml
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${OVID_DB_USER:-ovid}"]
      interval: 5s
      timeout: 5s
      retries: 5
```

**Existing `api` service in the two override files** already runs `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` (test file line ~33, prod line ~36) with a `depends_on: db: condition: service_healthy` and an `environment:` block. Add:
- a `redis` service (`redis:7-alpine`, `command: ["redis-server","--save","","--appendonly","no"]`, `redis-cli ping` healthcheck — RESEARCH.md §Compose redis service),
- `redis: { condition: service_healthy }` under the api `depends_on`,
- `REDIS_URL: redis://redis:6379/0` and `OVID_WORKERS: "4"` to the api `environment:` block.

Prod: do NOT publish a host port for redis (internal-only, matching prod `db`'s `ports: !reset []`, prod line 24). **`docker-compose.yml` (base, single uvicorn `--reload` worker, line 37) stays UNCHANGED** (D-05a).

---

### `api/scripts/seed.py` (utility, batch) — **EXISTS, seeds one disc today**

**Analog:** `api/tests/conftest.py::seed_test_disc` (line 131) — the only other existing disc-seeding routine (Matrix pattern: disc + release + titles + tracks). `api/scripts/seed.py` already exists and idempotently seeds exactly one disc (keyed on `FINGERPRINT = "dvd1-matrix-1999-r1-us"`); this is a **MODIFY** (extend to bulk seed), not a create.

**Pattern to reuse** (`conftest.py` line 131):
```python
def seed_test_disc(
    db: Session,
    submitted_by_id: uuid.UUID | None = None,
    status: str = "verified",
) -> dict[str, uuid.UUID]:
    """Seed a disc + release + titles + tracks matching the Matrix pattern."""
```
Extend `api/scripts/seed.py` (which already opens a real Postgres session via `app.database` / `DATABASE_URL`, like `api/scripts/sync.py`) with a bulk mode that loops this insert shape low-thousands of times with varied fingerprints (D-13).

---

### `api/tests/test_write_rate_limit.py` (test) — CREATE

**Analog:** `api/tests/test_rate_limit.py` (auth-loop pattern) + `conftest.matrix_matching_submit_payload` (line 220) + `auth_header` fixture (line 304).

**Auth-loop pattern to copy** (`test_rate_limit.py` lines 24-34):
```python
def test_auth_rate_limit_higher_threshold(client, auth_header) -> None:
    for i in range(101):
        resp = client.get("/v1/sync/head", headers=auth_header)
        assert resp.status_code == 200
```

**Critical (RESEARCH.md Pitfall 2):** the 21st POST must use an **auth'd, schema-valid** body via `matrix_matching_submit_payload()` — an invalid body 422s before the limiter runs and never trips 429. Assert GET unaffected; assert `20/minute` trips before `_dynamic_limit`.

---

### `api/tests/test_rate_limit_fallback.py` (test) — CREATE

**Analog:** `test_rate_limit.py` structure + CLAUDE.md fs-mock IO-failure convention (save original → override to raise → assert → restore in `finally`).

**Convention (D-03 / RESEARCH.md Pitfall 3 & 4):** the app limiter is `memory://` in tests (`conftest` never sets `REDIS_URL`), so build a **local** `Limiter(storage_uri="redis://localhost:6379", swallow_errors=True, in_memory_fallback_enabled=True, in_memory_fallback=[SMALL_CAP])` on a minimal FastAPI app + `TestClient`. Monkeypatch `limits.storage.RedisStorage.incr` to raise `redis.exceptions.ConnectionError` (the method `FixedWindowRateLimiter.hit()` actually calls — NOT `.get`). Assert 200 within cap, 429 once exceeded, restore in `finally`. `redis.from_url` does not connect eagerly, so no live Redis needed.

**Reset fixture to be aware of** (`conftest.py` lines 93-104) — autouse `_reset_rate_limiter` calls `limiter.reset()` on the app limiter; your local limiter is separate and unaffected.

---

### `api/tests/test_startup_guard.py` (test) — CREATE

**Analog:** import-time-behavior testing. Set `OVID_WORKERS=2` with `REDIS_URL` unset in a subprocess/`importlib.reload` and assert `RuntimeError` (mirrors `auth/config.py::_require_env` fail-fast). Restore env in `finally`.

---

### `loadtest/locustfile.py` + `loadtest/requirements.txt` (harness) — CREATE, **NO IN-REPO ANALOG**

**Analog:** none in-repo. Use RESEARCH.md §Code Examples (Locust `HttpUser` + `@task` weights + `events.quitting` p95 gate). Workload mix per D-13: 70% `GET /v1/disc/{fp}`, 20% `GET /v1/search`, 10% `POST /v1/disc`. `loadtest/requirements.txt` isolated from API runtime: `locust>=2.44,<3.0`. Reuse `ovid-client`'s httpx/auth helpers (`ovid-client/src/ovid/client.py`) for the submit token (D-11).

---

### `.github/workflows/loadtest.yml` (CI) — CREATE

**Analog:** `.github/workflows/ci.yml` — copy the `runs-on: ubuntu-latest`, `actions/checkout@v6`, `actions/setup-python@v6` (python 3.12), `pip install -r requirements.txt` step shape.

**Existing job shape to mirror** (`ci.yml` `api-tests` job):
```yaml
  api-tests:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: api
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
```

**Divergence (D-12):** trigger on `workflow_dispatch` + `schedule` (NOT `push`/`pull_request`); non-blocking. Use GitHub Actions `services: {postgres, redis}`, launch `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` in background, seed via extended `api/scripts/seed.py`, run Locust, publish `results_stats.csv` as artifact (RESEARCH.md Open Q2).

---

## Shared Patterns

### Structured JSON error envelope + `request_id`
**Source:** `api/app/rate_limit.py` lines 88-96 (429 handler)
**Apply to:** any new 503/guard output must reuse this shape.
```python
return JSONResponse(
    status_code=429,
    content={"error": "rate_limited", "message": f"Rate limit exceeded: {exc.detail}", "retry_after": int(retry_after)},
    headers={"Retry-After": str(retry_after)},
)
```

### Named `UPPER_SNAKE_CASE` tunable constants
**Source:** `api/app/rate_limit.py` lines 22-23; `api/app/anti_sybil.py` lines 56-57
**Apply to:** `AUTH_WRITE_LIMIT`, `FALLBACK_LIMIT` — module-level, documented as launch-safe tunable defaults, never magic numbers.

### Fail-fast at import time
**Source:** `api/app/auth/config.py` lines 6-18 (`_require_env` → `raise RuntimeError`)
**Apply to:** the D-06 multi-worker + `memory://` startup guard in `rate_limit.py`.

### Decorator-based limit enforcement (no middleware)
**Source:** `api/main.py` lines 45-50 comment; every route decorator in `routes/disc.py`
**Apply to:** the stacked `methods=["POST"]` write limit — follow the per-route decorator style, do NOT add `SlowAPIMiddleware`.

### Cross-platform IO-failure test via method monkeypatch + restore-in-finally
**Source:** CLAUDE.md convention (no fs analog needed — pattern is save/override-to-raise/assert/restore)
**Apply to:** `test_rate_limit_fallback.py` (patch `limits.storage.RedisStorage.incr` → `ConnectionError`).

### Auth-aware rate-limit key (already keys writes `user:{id}`)
**Source:** `api/app/rate_limit.py` lines 26-46 (`_auth_aware_key`)
**Apply to:** unchanged — every write is already `Depends(get_current_user)` (D-09), so `AUTH_WRITE_LIMIT` inherits `user:{id}` keying for free.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `loadtest/locustfile.py` | harness | request-response | No load-test tooling exists in-repo; use RESEARCH.md §Code Examples |
| `loadtest/requirements.txt` | config | — | New isolated dep set; no analog |

## Discovered Discrepancies (planner must reconcile)

- **`api/scripts/seed.py` EXISTS** and currently seeds one disc, matching CONTEXT (D-13, canonical_refs) and RESEARCH. Planner should treat this as a **MODIFY** (extend to bulk seed, Wave 0), reusing the `conftest.seed_test_disc` shape and `api/scripts/sync.py`'s DB-session bootstrap.
- **`main.py` likely needs no code change** — it imports `rate_limit` at module load, so a module-level guard there fires automatically. Confirm during planning whether the guard lives in `rate_limit.py` (recommended, cohesive with `REDIS_URL` read) vs. `main.py`.

## Metadata

**Analog search scope:** `api/app/`, `api/tests/`, `api/scripts/`, `.github/workflows/`, compose files (repo root)
**Files scanned:** rate_limit.py, main.py, routes/disc.py, auth/config.py, anti_sybil.py, tests/test_rate_limit.py, tests/conftest.py, docker-compose{,.prod,.test}.yml, .github/workflows/ci.yml, api/scripts/ listing
**Pattern extraction date:** 2026-07-06
</content>
</invoke>
