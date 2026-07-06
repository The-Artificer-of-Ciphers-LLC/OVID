# Phase 3: Redis-Backed Rate Limiting & Performance - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Make rate limiting **correct under the real multi-worker gunicorn deployment** and prove the API meets its **p95 ≤ 500ms** budget against that same configuration. Today `slowapi` uses `storage_uri="memory://"`, so each of the 4 prod/test gunicorn workers keeps independent counters and the effective limit is inflated ~Nx (documented as a defect in `rate_limit.py`'s own docstring). This phase:

1. Moves the general slowapi limiter to a **Redis-backed shared store** so limits are correct across workers (INFRA-01).
2. Makes **Redis-outage behavior an explicit, documented, tested decision** (INFRA-02).
3. Adds a **tighter per-account write throttle** on submission/write endpoints, live in prod (INFRA-04).
4. Validates **p95 ≤ 500ms** with a load test against the ACTUAL Redis-backed, multi-worker config (INFRA-03).

**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04.

**Independent of the identity/verification work** — no dependency on Phases 1/2/4/5; parallel-safe (ROADMAP Wave A).

**Explicitly NOT this phase (owned elsewhere):**
- The **per-account confirmation cooldown** (trust-model proof-of-independence) — already built in Phase 2 as `api/app/anti_sybil.py`, **Postgres-backed and worker-safe by construction**. It stays on Postgres; do NOT migrate it onto Redis/slowapi or treat it as redundant with the general limiter (Phase 2 D-13/D-14).
- Cross-table fingerprint-registry arbitration (WR-02) → Phase 5.
- Any web-UI surface → Phase 7.
</domain>

<decisions>
## Implementation Decisions

### Sequencing (locked — the backbone)
- **D-00:** INFRA-01, INFRA-02, and INFRA-04 land as **one coherent backbone change**: the Redis `storage_uri` swap + `in_memory_fallback` config + the stacked write limit ship together. Rationale: a tight write limit and any p95 claim are *hollow* under `memory://` (worker-inflated), so the write throttle (D-05) and the load test (D-07) are only meaningful once Redis is the shared store. INFRA-03's load test (D-07) runs **after** the backbone lands, so it validates the real target config, not the retiring `memory://` one. All four research agents independently flagged this coupling.

### Redis outage behavior (INFRA-02)
- **D-01:** **In-memory fallback**, not fail-open or fail-closed. Use `swallow_errors=True` + `in_memory_fallback_enabled=True` with a **conservative per-worker fallback limit** (native `limits`/`slowapi` feature — no custom storage code). On a Redis outage each worker degrades to a bounded local counter and the library **auto-probes Redis on exponential backoff and switches back** when it recovers.
- **D-02:** Rationale that locks this: OVID's rate limiting is **abuse-prevention, not an authorization boundary** — lookups are already anonymous and the data is public/CC0. So fail-closed (turning a Redis blip into a full outage of the read-heavy, ARM-facing lookup path over a *newly introduced* dependency) is the wrong trade; pure fail-open needlessly throws away all protection when the library ships a self-healing middle path for free.
- **D-03 (test method — locked):** Simulate the outage **deterministically** by monkeypatching the underlying `limits.storage` Redis method (e.g. `incr`/`get`) to raise `redis.exceptions.ConnectionError`, drive a request through FastAPI `TestClient`, assert the fallback behavior (200 with fallback limiting active; 429 once the fallback cap is exceeded), and restore in `finally`. This matches the repo's cross-platform fs-mock IO-failure convention — **no real Redis container needs to be killed** for the required test. An optional docker-compose integration test that stops the `redis` service may supplement as a secondary, non-blocking recovery check.
- **D-04:** Route-type split (fail-open reads / fail-closed writes) is **deferred** — architecturally "most correct" but speculative complexity (two limiter configs, doubled test matrix) with marginal gain unless write-path abuse is later shown to be a materially distinct threat.

### Redis as a deployment dependency (INFRA-01, "relevant compose files")
- **D-05a:** **Env-driven backend selection.** `rate_limit.py` reads `REDIS_URL`: when set → `storage_uri=redis://…`; when unset → falls back to `memory://` (today's behavior, which is **already correct** at a single worker). Add a `redis` service **only** to `docker-compose.prod.yml` and `docker-compose.test.yml` — the two files that already run `gunicorn -w 4`. The base `docker-compose.yml` (single uvicorn worker, `--reload`) is **also the documented self-host / mirror path** (`docker compose --profile mirror up -d`, per `docs/self-hosting.md`), where `memory://` is correct — leave it unchanged. This keeps the Pi/NAS self-host story exactly as low-friction as today and scopes the fix to where the defect actually lives. Answers "which compose files are relevant": **prod + test only.**
- **D-06:** **Fail-fast startup guard** (a boot assertion that refuses to start, not just a log line) when the process is configured for multiple workers while `REDIS_URL` is unset — driven by an **explicit env var** (e.g. `OVID_WORKERS` / `WEB_CONCURRENCY` set alongside `-w 4` in those compose files), **not by parsing gunicorn's argv**. Turns a silent 4× inflation into an immediate, loud failure, consistent with OVID's explicit-error-handling convention. Auto-detecting worker count is rejected as a standalone approach (fragile argv/env scraping) but is acceptable as an *optional secondary* sanity check layered on top of the env var.

### Write-throttle policy & values (INFRA-04)
- **D-07:** **Stacked, method-scoped write limit.** Add a second `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` decorator (slowapi's native `methods=` param) on the write routes (`POST /disc`, `POST /disc/register`, `POST /disc/{fingerprint}/resolve`) **in addition to** the existing `@limiter.limit(_dynamic_limit)`. Reads are unaffected.
- **D-08 (starting values — tunable named constants, not magic numbers):** `AUTH_WRITE_LIMIT = "20/minute;300/hour"`. Leave `UNAUTH_LIMIT = "100/minute"` (anon reads) and `AUTH_LIMIT = "500/minute"` (auth reads) **untouched** — ARM's one-lookup-per-rip sits at ~1/166th of the anon ceiling, comfortably clear. The per-minute clause bounds human-paced disc-swap submission cadence; the hourly clause defeats a burst-then-idle gaming pattern. Values are launch-safe defaults, surfaced as named constants for easy tuning once real usage data exists.
- **D-09 (ground truth):** `POST /disc` (submit) **always** requires `Depends(get_current_user)` — there is **no anonymous write path** — so every write is already keyed `user:{id}`. Rejected: cost-weighted single pool (conflates read+write budgets, confusing 429s); status-quo/no-split (fails INFRA-04 — a flood of brand-new fingerprints that are never confirmations would get no write ceiling, since the Phase-2 cooldown only fires on the confirmation branch).
- **D-10 (clean split from Phase 2 — no double-counting):** The slowapi write limit is a **coarse volumetric request-rate ceiling** over ALL POST traffic from a key, enforced **at the decorator before the handler runs**. `anti_sybil.py`'s Postgres cooldown (`CONFIRMATION_MAX_PER_WINDOW=5/hr`, `CONFIRMATION_MAX_PER_DAY=20/day`) is a **narrower semantic gate** that fires **inside `_handle_existing_disc`** only when a resubmission resolves to an existing disc from a *different* submitter (a true confirmation, `edit_type="verify"`). When one POST *is* a confirmation, both apply in sequence (slowapi first, anti-Sybil second) = **defense-in-depth, not redundancy** — they measure different things (raw request rate vs. count of successful verify-edits), and a request rejected by the first never reaches the second. Add a one-line doc note distinguishing the two mechanisms.

### Load-test methodology (INFRA-03)
- **D-11 (tool):** **Locust** — pure Python, so the load script can reuse `ovid-client`'s httpx/auth helpers (`client.py`) and the existing `scripts/seed.py` seed helper rather than reimplementing them. The p95 pass/fail gate is a small (~20-line) wrapper parsing Locust's `--csv` stats / exit code. (k6 was the close runner-up — its declarative `thresholds: { http_req_duration: ['p(95)<500'] }` *is* the gate with zero glue — but it adds JS as a third language on an API side that has no JS tooling today; chosen against for tooling-cohesion.)
- **D-12 (placement — locked regardless of tool):** A **separate, non-blocking** GitHub Actions job triggered on `workflow_dispatch` **and/or a schedule** (nightly/weekly) — **NOT a per-PR merge gate**. An absolute `p95 ≤ 500ms` assertion on GitHub's noisy shared runners would produce intermittent failures, which this project's rules treat as real defects to root-cause every time — a bad trade for a perf gate. The job spins up the real stack (Postgres + `gunicorn -w 4` + Redis-backed limiter), seeds the dataset, runs the profile, and **publishes p95/p99 as a build summary/artifact**, plus a documented reproducible manual invocation for pre-release. (Promotable to a blocking gate later if OVID moves to a dedicated self-hosted runner.)
- **D-13 (workload & dataset):** Seed **low-thousands** of `disc`/`release` rows via `scripts/seed.py` (enough to defeat small-table query-plan/cache illusions; not a big-data problem for OVID's schema). Workload mix weighted to the documented dominant traffic: **~70% `GET /v1/disc/{fingerprint}` lookups, ~20% `GET /v1/search`, ~10% `POST /v1/disc` submissions** — reads dominate, writes present-but-light so the submission path's auth/identity-resolution cost is represented in p95 without swamping it.
- **D-14 (honest "actual config"):** The load test must NOT run against the retiring `memory://` limiter. Minimal honest bar: **Postgres (not SQLite/TestClient), `gunicorn -w 4` with the uvicorn worker class, and a live Redis-backed slowapi limiter.** This is why D-07 sequences the load test after the Redis backbone (D-00).

### Claude's Discretion
- Exact **fallback cap** value for the in-memory fallback (D-01) — propose a conservative launch default during research/planning.
- Exact **startup-guard env-var name** and whether to reuse `WEB_CONCURRENCY` vs. a new `OVID_WORKERS` (D-06) — implementation choice.
- Precise **write-limit numbers** (D-08) — the *shape* (stacked method-scoped, per-minute + per-hour clauses, named constants) is locked; the numbers are tunable starting points.
- **Load-test schedule cadence** (nightly vs weekly) and the exact seed row count (D-12/D-13).
- Whether the write throttle also covers `POST /disc/{fingerprint}/resolve` and `/register` at the same value or a different one — planner's call, given they're lower-volume.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & boundary
- `.planning/REQUIREMENTS.md` — INFRA-01, INFRA-02, INFRA-03, INFRA-04 (authoritative requirement text + phase mapping).
- `.planning/ROADMAP.md` §"Phase 3" — goal, the four success criteria, and the parallel-safe / Wave-A dependency note.
- `.planning/phases/02-two-contributor-verification-workflow/02-CONTEXT.md` §D-13/D-14 and §Deferred — the authoritative Phase 2↔3 boundary: the confirmation cooldown is Postgres-backed and independent; Phase 3 owns the general slowapi limiter only.

### Code touched by this phase
- `api/app/rate_limit.py` — the slowapi `Limiter`: `storage_uri="memory://"` (→ Redis), `_auth_aware_key()`, `_dynamic_limit()`, `UNAUTH_LIMIT`/`AUTH_LIMIT` constants, `rate_limit_exceeded_handler()`. The docstring already documents the multi-worker inflation defect and names Redis as the upgrade path.
- `api/main.py` — `app.state.limiter` registration + `RateLimitExceeded` exception handler wiring (no `SlowAPIMiddleware`; enforcement is decorator-based with `auto_check=True`). Startup guard (D-06) lands here or in app bootstrap.
- `api/app/routes/disc.py` — write routes to throttle: `POST /disc` (`submit_disc`, always authed), `POST /disc/register`, `POST /disc/{fingerprint}/resolve`; read routes `GET /disc/{fingerprint}`, `GET /search`, `GET /disc/upc/{upc}`, `GET /disc/disputed`, `GET /disc/{fingerprint}/edits`.
- `api/app/routes/sync.py` — `GET /sync/head|diff|snapshot` (also limited today; keep behavior).
- `api/app/anti_sybil.py` — Phase 2's Postgres confirmation cooldown (`evaluate_confirmation()`, `CONFIRMATION_*` constants, `SELECT ... FOR UPDATE`). **Read to preserve the D-10 split — do NOT move it onto Redis/slowapi.**
- `api/requirements.txt` — add the `redis` client dependency (none today).
- `docker-compose.prod.yml`, `docker-compose.test.yml` — add a `redis` service + `REDIS_URL`/worker env (both run `gunicorn -w 4`). `docker-compose.yml` (dev/self-host, single worker) stays unchanged.
- `scripts/seed.py` — referenced by `docs/OVID-technical-spec.md` §11.1; the load-test seed helper (D-13). Confirm it exists / build if planning requires.

### Docs to update
- `docs/self-hosting.md`, `docs/deployment.md` — document the env-driven Redis backend, when Redis is required (multi-worker) vs. optional (single-worker), and the fail-fast guard (D-05a/D-06).
- `docs/OVID-technical-spec.md` §~676 — describes the "general Redis-backed slowapi API rate limiter" as a Phase 3 deliverable; the INFRA-02 fail-open/fail-closed decision (D-01) and INFRA-03 harness (D-11..D-14) should be recorded here.
- `.env.example` — add `REDIS_URL` (and the worker-count env if used).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/app/rate_limit.py` slowapi `Limiter` with `_auth_aware_key()` (authed → `user:{id}` @ 500/min; anon → client IP @ 100/min) and a structured JSON 429 handler (`Retry-After`, `request_id`). Redis swap is a `storage_uri` change + `in_memory_fallback_*` flags — **native, no custom storage code**.
- `api/app/anti_sybil.py` proves the worker-safe-Postgres-counter pattern (`SELECT ... FOR UPDATE`) already exists and works — but it is a *separate* mechanism the general limiter must not absorb (D-10).
- `scripts/seed.py` (per technical-spec §11.1) — reusable to seed the load-test dataset (D-13).
- `docker-compose.test.yml` already runs `gunicorn -w 4` — extend it with a `redis` service to become the honest load-test target (D-14).

### Established Patterns
- Structured JSON error/response envelope with `request_id` + `x-request-id` header — the 429 handler already conforms; any new 503/guard output must too.
- Cross-platform IO-failure tests via `fs`/method monkeypatch + restore-in-`finally` (CLAUDE.md convention) — the D-03 Redis-outage test follows this exact shape (patch `limits.storage` Redis method to raise `ConnectionError`).
- Decorator-based limit enforcement (no `SlowAPIMiddleware`) — the stacked `methods=["POST"]` write limit (D-07) follows the established per-route decorator style.
- Named `UPPER_SNAKE_CASE` tunable constants for limits — `AUTH_WRITE_LIMIT` follows `UNAUTH_LIMIT`/`AUTH_LIMIT`.

### Integration Points
- `rate_limit.py` storage backend selection + startup guard (reads `REDIS_URL` / worker-count env).
- `main.py` app bootstrap for the fail-fast boot assertion (D-06).
- `POST` write routes in `routes/disc.py` gain the second stacked decorator (D-07).
- New `redis` service in `docker-compose.prod.yml` + `docker-compose.test.yml`; new `redis` dep in `requirements.txt`.
- New `loadtest/` harness (Locust) + a non-blocking GitHub Actions workflow (D-11/D-12).
</code_context>

<specifics>
## Specific Ideas

- Guiding framing from the discussion: **rate limiting is abuse-prevention, not authorization** — this single principle drove D-01 (in-memory fallback, never fail-closed) and the decision to leave the anon/auth read limits untouched.
- The **self-hosting-first philosophy** (no gatekeeper; Pi/NAS single-worker installs) drove D-05a: Redis is scoped to the multi-worker prod/test files, never forced on hobbyist single-worker deployments where `memory://` is already correct.
- Keep the perf gate **honest but not flaky**: validate the real Redis-backed multi-worker stack (D-14), but off the per-PR critical path (D-12) so shared-runner jitter never masquerades as a regression.
</specifics>

<deferred>
## Deferred Ideas

- **Route-type fail-open/fail-closed split** (fail-open reads, fail-closed writes) — deferred (D-04); revisit only if write-path abuse proves a materially distinct threat.
- **Promoting the p95 load test to a blocking per-PR gate** — deferred (D-12); becomes safe only on a dedicated self-hosted runner where CPU allocation is stable.
- **k6 as the load-test tool** — considered and set aside for Locust (D-11) on Python-tooling-cohesion grounds; a valid future switch if CI-native thresholds become worth a second scripting language.
- **Reputation / edit-voting weighting beyond Phase 2's seed** — v0.4.0 per PRD; not touched here.

</deferred>

---

*Phase: 3-Redis-Backed Rate Limiting & Performance*
*Context gathered: 2026-07-05*
