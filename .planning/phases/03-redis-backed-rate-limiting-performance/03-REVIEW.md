---
phase: 03-redis-backed-rate-limiting-performance
reviewed: 2026-07-06T00:00:00Z
depth: deep
files_reviewed: 15
files_reviewed_list:
  - api/app/rate_limit.py
  - api/app/routes/disc.py
  - api/scripts/seed.py
  - loadtest/locustfile.py
  - loadtest/requirements.txt
  - api/requirements.txt
  - api/tests/test_rate_limit_backend.py
  - api/tests/test_rate_limit_fallback.py
  - api/tests/test_startup_guard.py
  - api/tests/test_write_rate_limit.py
  - api/tests/test_seed.py
  - .github/workflows/loadtest.yml
  - docs/deployment.md
  - docs/self-hosting.md
  - docs/OVID-technical-spec.md
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: resolved
resolved: 2026-07-06
resolution: All 1 critical + 4 warnings fixed and verified (commits 68b7a32..65ef492). IN-01/IN-02 documented; IN-03 is an out-of-scope perf note (no correctness impact), acknowledged not fixed.
---

# Phase 3: Code Review Report

**Reviewed:** 2026-07-06
**Depth:** deep
**Files Reviewed:** 15
**Status:** issues_found

## Summary

This phase adds Redis-backed cross-worker rate limiting, a bounded fail-open outage
fallback, a fail-fast multi-worker boot guard, a stacked per-account write ceiling
on the three disc write routes (with a `shared_limit` scope fix on the
fingerprint-path resolve route), a bulk seed path, and a Locust p95 harness.

The rate-limiter core (`api/app/rate_limit.py`) and the write-ceiling decorator
wiring in `api/app/routes/disc.py` are correct: backend selection is env-driven,
the `shared_limit` scope pins the resolve route's per-user bucket across all
fingerprints, decorator stacking uses distinct limit strings so the two limits do
not collide in storage, and the test suite resets limiter state between cases
(`_reset_rate_limiter` autouse fixture) so the write-cap tests are isolated.

The headline defect is in the load-test harness: its own read workload will trip
the per-IP unauthenticated rate limit and blow the error-ratio budget, so the p95
gate cannot actually measure or prove the p95 ≤ 500ms target it exists to enforce.
Secondary findings concern fail-open weakening of the write ceiling during an
outage, the guard's reliance on a declarative env var rather than the real worker
count, and a false-green edge in the gate.

No structural findings block was provided.

## Critical Issues

### CR-01: Load-test read traffic trips the per-IP rate limit — the p95 gate can never pass

**File:** `loadtest/locustfile.py:124-134` (with `api/app/rate_limit.py:26,39-59,105-112`)

**Issue:** The harness drives ~90% of its traffic through two **unauthenticated**
GET tasks (`lookup` weight 70, `search` weight 20). Only the `submit` task sends a
`Bearer` token; the read tasks send no `Authorization` header, so
`_auth_aware_key` keys them by client IP. A headless Locust run (`-u 100 -r 10 -t
3m`) generates all traffic from a single source IP (`127.0.0.1` / the load-gen
host), so every read shares one bucket capped at `UNAUTH_LIMIT = "100/minute"`.

At 100 users with `wait_time = between(0.1, 0.5)` the run produces on the order of
10,000–18,000 reads/minute against a 100/minute cap — roughly 99% of reads return
429. Locust records a non-`catch_response` 429 as a failure (it calls
`response.raise_for_status()`), so `stats.fail_ratio` approaches ~0.99. The gate in
`_p95_gate` checks `fail_ratio > ERROR_RATIO_BUDGET` (0.01) **first** and sets
`environment.process_exit_code = 1` before p95 is ever considered.

Result: the job fails every scheduled run for the wrong reason (rate-limiter
rejection, not latency), and the deliverable — "prove API p95 ≤ 500ms against the
honest Redis-backed stack" — is not actually validated. The docstring carefully
handles write-path 429s via `catch_response` but never accounts for read-path 429s,
indicating the interaction was not considered. Even switching reads to the
authenticated 500/minute tier would still be exceeded by ~30x.

**Fix:** Make the read paths measurable under a single-source load generator. Options:
```python
# Option A: raise/disable the limiter for the load-test host only, via an env
# gate the app honors (e.g. OVID_RATE_LIMIT_DISABLED=1 in loadtest.yml), so the
# gate measures service latency rather than limiter rejection.

# Option B: mark the *expected* read 429s as an accepted throttle the same way
# submit does, AND assert a minimum successful-read throughput so the run is not
# reduced to measuring 429 latency:
@task(70)
def lookup(self) -> None:
    i = random.randrange(_SEED_COUNT)
    with self.client.get(
        f"/v1/disc/{BULK_FINGERPRINT_PREFIX}{i}",
        name="/v1/disc/[fp]", catch_response=True,
    ) as resp:
        if resp.status_code in (200, 429):
            resp.success()
        else:
            resp.failure(f"unexpected status {resp.status_code}")
```
Option A is preferred: with reads mostly 429-ing, the p95/throughput the gate
reports is not the p95 of the real read path, so marking 429s as success (Option B)
produces a green gate that still has not measured what it claims. Whichever path is
chosen, add a minimum-request / minimum-2xx assertion (see WR-03).

## Warnings

### WR-01: Redis-outage fallback silently loosens the 20/min write ceiling to ≥60/min per worker

**File:** `api/app/rate_limit.py:32-36,105-112`

**Issue:** `in_memory_fallback=[FALLBACK_LIMIT]` installs a single `60/minute`
fallback, and the module's own docstring states "slowapi replaces all per-route
limits with the fallback during an outage." By that stated semantics, during a
Redis outage the per-account write ceiling (`AUTH_WRITE_LIMIT = "20/minute;300/hour"`)
is replaced by the looser `60/minute` fallback. Because the fallback is
**per-worker**, the effective write-abuse headroom during an outage becomes
`60 × N_workers` per minute — e.g. 240/min across `gunicorn -w 4`, a ~12x increase
over the intended 20/min. This is a fail-open weakening of the write-abuse control
precisely when the shared store is unavailable. The read-path fail-open is a
documented, defensible decision, but the *write-ceiling* loosening is not called
out anywhere and the prompt specifically flags fail-open vs fail-closed on the
write ceiling. (If the docstring's "replaces all limits" claim is wrong, then the
docstring is itself a documentation defect describing behavior the operator will
rely on.)

**Fix:** Decide explicitly and document it. Either accept read fail-open while
keeping writes fail-closed during an outage (per-route split — deferred as D-04,
but the write ceiling is the case that matters), or set the fallback cap no looser
than the write ceiling it can replace, or state in the docstring/deploy docs that
the write cap intentionally relaxes to `60/min × workers` during a Redis outage so
operators are not surprised.

### WR-02: Multi-worker guard trusts a declarative env var, not the real `-w` — the "impossible" misconfig is still possible

**File:** `api/app/rate_limit.py:93-101` (docs: `docs/self-hosting.md`, `docs/deployment.md`)

**Issue:** The guard reads `OVID_WORKERS`/`WEB_CONCURRENCY`, not gunicorn's actual
`-w` value (a deliberate "never scrape argv" choice). The prod/test compose files
hardcode `-w 4` and `OVID_WORKERS=4` as two independent literals that must be kept
in sync by hand. The guard therefore does not protect the most likely hand-rolled
misconfiguration: an operator who runs `gunicorn -w 4` (or `-w 8`) **without**
setting `OVID_WORKERS`/`WEB_CONCURRENCY` and without `REDIS_URL`. In that case
`_worker_count` defaults to `1`, the guard does not fire, and every rate limit
silently inflates up to Nx — the exact failure the guard claims to prevent.
`docs/self-hosting.md` overstates this ("To make that mistake impossible, the API
refuses to boot…"); it is not impossible, only caught when the operator remembers a
second env var.

**Fix:** Either derive the worker count from the actual server (e.g. read
`gunicorn.arbiter`/`server.cfg.workers` in a `post_fork`/`when_ready` hook, or a
FastAPI startup check), or soften the docs to state the guard only fires when
`OVID_WORKERS`/`WEB_CONCURRENCY` is set, and make the prod/test entrypoint derive
`-w` from `OVID_WORKERS` (single source of truth) so the two can never drift:
```yaml
command: >-
  gunicorn -w "${OVID_WORKERS:-1}" -k uvicorn.workers.UvicornWorker main:app ...
```

### WR-03: p95 gate reports PASS (exit 0) on a zero-request run — no minimum-throughput floor

**File:** `loadtest/locustfile.py:156-181`

**Issue:** `_p95_gate` reads `p95 = stats.get_response_time_percentile(0.95)` (which
returns `0` when no samples exist) and `fail_ratio` (`0` with no requests). If a run
records zero requests — e.g. wrong `--host`, all tasks short-circuited, or a
misconfigured invocation — both branches are skipped and the `else` sets
`process_exit_code = 0`, logging "LOAD TEST PASS". A latency gate that reports PASS
having measured nothing is a silent false-green that would mask a broken harness.

**Fix:** Assert a minimum sample count before evaluating the budget:
```python
if stats.num_requests < MIN_EXPECTED_REQUESTS:
    logging.error("LOAD TEST FAIL: only %d requests recorded — harness did not "
                  "generate load", stats.num_requests)
    environment.process_exit_code = 1
    return
```

### WR-04: `int(os.environ.get("OVID_WORKERS", ...))` is unguarded — non-numeric value crashes boot with an opaque traceback

**File:** `api/app/rate_limit.py:93`

**Issue:** `int(os.environ.get("OVID_WORKERS", os.environ.get("WEB_CONCURRENCY", "1")))`
assumes the env var is a valid integer. A present-but-empty (`OVID_WORKERS=""`) or
non-numeric value raises `ValueError: invalid literal for int() with base 10` at
import time — an opaque traceback rather than the deliberate, actionable
`RuntimeError` this module otherwise uses for misconfiguration. An empty-string env
var is a common shell/compose artifact.

**Fix:** Parse defensively and route bad values into the same fail-fast style:
```python
_raw = os.environ.get("OVID_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1"
try:
    _worker_count = int(_raw)
except ValueError:
    raise RuntimeError(
        f"OVID_WORKERS/WEB_CONCURRENCY must be an integer, got {_raw!r}."
    )
```

## Info

### IN-01: "Bounded" outage fallback bounds the per-key rate, not the number of keys

**File:** `api/app/rate_limit.py:6-8,33-36`

**Issue:** The docstrings describe the in-memory outage fallback as "bounded." The
bound is on the request rate per key (`60/minute`), not on the number of distinct
keys retained. During a sustained outage with many distinct client IPs/users, the
fallback `MemoryStorage` accumulates one entry per key. The `limits` library
performs lazy expiry on access, so this is not a hard leak, but the "bounded"
wording could be read as bounding total memory. Consider clarifying the comment to
"bounded per-key rate" to avoid over-claiming.

### IN-02: Per-IP limiting correctness depends on proxy forwarded-IP config (default collapses external users)

**File:** `api/app/rate_limit.py:46-59` (config: `docker-compose.prod.yml` `--forwarded-allow-ips`)

**Issue:** `_auth_aware_key` falls back to `request.client.host` for unauthenticated
callers. In prod the API runs behind the cross-host `redshirt` reverse proxy, and
uvicorn only honors `X-Forwarded-For` from peers listed in `--forwarded-allow-ips`
(default `${OVID_FORWARDED_ALLOW_IPS:-127.0.0.1}`). If `OVID_FORWARDED_ALLOW_IPS`
is not set to the proxy/docker-gateway source, `request.client.host` is the proxy's
IP for every external request, collapsing all unauthenticated users into a single
100/min bucket — undermining the per-IP correctness this phase's Redis backend
exists to make cross-worker-consistent. The forwarded-allow-ips line is pre-existing
and configurable, so this is informational, but it is a required companion setting
for the new shared-counter design to behave as intended in prod.

### IN-03: `bulk_seed` retains all ORM objects in the session for the whole batch

**File:** `api/scripts/seed.py:84-153`

**Issue:** The `--count N` loop flushes per row (and every 500) but never expunges
or clears the session, so all inserted `Disc`/`Release`/`DiscTitle`/`DiscTrack`
objects remain identity-mapped for the entire run. Correctness is fine (single
commit at the end); this is only a memory note for very large `N`. Performance is
out of v1 scope, so this is informational — if seeding tens of thousands ever
becomes a need, periodically `db.expunge_all()` after a batch flush.

---

## Resolution (2026-07-06)

All actionable findings were fixed inline during phase execution and independently verified (full API suite 327 → **331 passed**, no new warnings; both merged compose stacks parse; `docker compose config` confirms `gunicorn -w "4"` resolves in lock-step with `OVID_WORKERS=4`).

| Finding | Fix | Commit(s) |
|---|---|---|
| CR-01 (critical) | Read limits (`UNAUTH_LIMIT`/`AUTH_LIMIT`) made env-configurable with **identical defaults**; `loadtest.yml` raises them for the CI run so the gate measures handler p95, not limiter 429s | 68b7a32, 8e93831, 1af57d6 |
| WR-04 | Empty `OVID_WORKERS` treated as unset; non-numeric raises the module's actionable `RuntimeError` instead of a bare `ValueError` | 05f371d, ecb638e |
| WR-02 | Both gunicorn `-w` and the `OVID_WORKERS` env entry interpolate the same `${OVID_WORKERS:-4}` (single source, cannot drift); `self-hosting.md` "impossible" claim softened. *(Brief's literal snippet would have regressed — Compose interpolates `command:` from host/`.env`, not sibling `environment:`; corrected.)* | bb485e5 |
| WR-03 | `_p95_gate` fails loud on a zero/too-few-request run (min-throughput floor as the first check) | 11a4665 |
| WR-01 / IN-01 / IN-02 | Documented: outage relaxes the write ceiling to ~60/min × workers (fail-open on writes during a Redis outage, per deferred D-04); "bounded" clarified to per-key rate; `OVID_FORWARDED_ALLOW_IPS` companion setting noted | 65ef492 |
| IN-03 (info) | Out-of-scope perf note (session retention for very large seed `N`); correctness unaffected — acknowledged, not changed | — |

_Reviewed: 2026-07-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
