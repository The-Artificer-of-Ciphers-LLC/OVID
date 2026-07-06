---
phase: 03-redis-backed-rate-limiting-performance
plan: 04
subsystem: performance-validation
status: complete
tags: [loadtest, locust, ci, seed, p95, infra-03]
dependency_graph:
  requires: [03-01, 03-02, 03-03]
  provides:
    - "bulk_seed(db, count) + scripts/seed.py --count CLI (D-13 dataset builder)"
    - "loadtest/ Locust harness with native p95/error exit-code gate (INFRA-03)"
    - ".github/workflows/loadtest.yml non-blocking scheduled p95 job (D-12/D-14)"
  affects:
    - "api/scripts/seed.py (extended, single-Matrix default preserved)"
tech_stack:
  added:
    - "locust>=2.44,<3.0 (loadtest/requirements.txt, isolated from api runtime deps)"
  patterns:
    - "Locust HttpUser + weighted @task + events.quitting → process_exit_code gate"
    - "GitHub Actions services (postgres + redis) + background gunicorn -w 4 (honest stack, no docker-compose-in-CI)"
    - "catch_response marks Plan-02 write-cap 429s as non-failures (T-03-10)"
key_files:
  created:
    - api/tests/test_seed.py
    - loadtest/locustfile.py
    - loadtest/requirements.txt
    - .github/workflows/loadtest.yml
  modified:
    - api/scripts/seed.py
decisions:
  - "Weekly off-peak cron (Mon 04:17 UTC) for the scheduled load test (D-12/A6)"
  - "Seed dataset size 3000 rows (low-thousands, D-13); OVID_LOADTEST_SEED_COUNT keeps the locustfile lookup range in sync"
  - "Write-cap 429 handling: mark 429 as success via catch_response + novel unique fingerprints per POST (simplest of the three sanctioned options)"
  - "Load-test JWT minted at runtime for a seeded 'loadtester' contributor via app.auth.jwt.create_access_token, passed by OVID_LOADTEST_TOKEN (never committed)"
metrics:
  duration: 22min
  completed: 2026-07-06
  tasks: 3
  files: 5
---

# Phase 3 Plan 4: Load-Test Harness & p95 Validation Summary

Bulk-capable seed, a Locust p95 harness with a native exit-code gate, and a non-blocking scheduled CI job that proves API p95 ≤ 500ms against the honest Redis-backed `gunicorn -w 4` + Postgres stack (INFRA-03) — never the retiring `memory://` single-worker config.

## What Was Built

**Task 1 — bulk seed + unit test (TDD, D-13).** Extended `api/scripts/seed.py` with `bulk_seed(db, count)` and a `--count N` argparse CLI. `bulk_seed` inserts `count` verified discs with unique deterministic fingerprints (`dvd1-seed-{i}`), releases whose titles share the searchable token `Seed Movie {i}`, and a minimal-but-representative structure (one main-feature title + audio/subtitle track) so `GET /v1/disc/{fp}` exercises the real nested-read cost and `GET /v1/search?q=Seed` returns real hits. The session is caller-owned (commits the batch, does not close). The no-arg invocation still runs today's idempotent single-Matrix `seed()`. Followed RED→GREEN: a failing `api/tests/test_seed.py` (536285a) preceded the implementation (b7015d5). The test asserts the row count, unique fingerprints, a lookup-resolvable disc, a search hit, and the zero-count boundary.

**Task 2 — Locust harness (INFRA-03/D-11).** `loadtest/locustfile.py` runs the D-13 70/20/10 mix (lookup / search / authenticated submit) and gates via an `events.quitting` listener that reads `stats.total.get_response_time_percentile(0.95)` and sets `environment.process_exit_code = 1` on p95 > 500ms or `fail_ratio` > 1%. The submit task uses novel unique fingerprints and marks Plan-02 write-cap 429s as success via `catch_response` so throttles never inflate `fail_ratio`. `loadtest/requirements.txt` pins `locust>=2.44,<3.0`, isolated from `api/requirements.txt`.

**Task 3 — non-blocking scheduled CI job (D-12/D-14).** `.github/workflows/loadtest.yml` triggers only on `workflow_dispatch` + weekly `schedule` (never `push`/`pull_request`), so it is never a per-PR merge gate. It provisions `postgres:16-alpine` + `redis:7-alpine` services, runs Alembic migrations, seeds 3000 rows, mints a JWT for a seeded `loadtester` contributor, launches `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` with `REDIS_URL`/`OVID_WORKERS=4` (the honest config), runs the Locust gate, publishes p95/p99 to the job summary, and uploads `results_stats.csv` as an artifact.

## Verification

- `cd api && .venv/bin/python -m py_compile scripts/seed.py` — clean.
- `cd api && .venv/bin/python -m pytest tests/test_seed.py -x` — 3 passed.
- Full API suite `pytest tests/ -q` — **327 passed** (no regression; single-Matrix seed default preserved).
- `python -m py_compile loadtest/locustfile.py` — clean; `get_response_time_percentile` + `process_exit_code` present; `locust>=2.44,<3.0` pinned.
- `.github/workflows/loadtest.yml` — YAML parses; triggers are `workflow_dispatch` + `schedule` only (no `push`/`pull_request`); services include postgres + redis. Both inline Python heredocs (token mint, summary publisher) compile cleanly.
- Out-of-band (INFRA-03 authoritative evidence): one scheduled/manual Locust run against Postgres + `gunicorn -w 4` + Redis showing p95 ≤ 500ms, captured as the workflow artifact, before `/gsd-verify-work`.

## Deviations from Plan

None — plan executed exactly as written. The `read_first` note about reusing `ovid-client`'s auth helper is honored in spirit: the harness reproduces the same `Authorization: Bearer <token>` scheme rather than importing the `requests`-based client (Locust drives its own `HttpUser` client), and the token is minted server-side via `app.auth.jwt` per D-11.

## Deferred Issues

Two pre-existing third-party deprecation warnings surface during the API test run (already logged in `deferred-items.md` from Plan 03-01, present across the whole suite, unrelated to this plan's changes): the Starlette `httpx`/testclient deprecation and slowapi's `asyncio.iscoroutinefunction` deprecation under Python 3.14. Both originate in library code (not OVID source) and fall under the executor scope boundary. CI Python is 3.12, where the slowapi one does not fire.

## Threat Surface

No new surface beyond the plan's threat register. The workflow's `OVID_SECRET_KEY` is a synthetic, clearly-labeled CI-only value used solely to sign the ephemeral load-test JWT against a throwaway runner-internal DB — consistent with T-03-08 (token minted at runtime for a seeded test user, never a real credential; services bound to the runner, no public exposure). `locust` install matches T-03-09 (audited OK, pinned, isolated). Write-cap 429 handling matches T-03-10 (accepted, benign measurement artifact).

## Self-Check: PASSED

- Files: all 5 present (api/scripts/seed.py, api/tests/test_seed.py, loadtest/locustfile.py, loadtest/requirements.txt, .github/workflows/loadtest.yml).
- Commits: 536285a, b7015d5, a2b5a2f, 58e9e88 all present in history.

## TDD Gate Compliance

Task 1 (behavior-adding) followed the gate: `test(03-04)` RED commit (536285a) precedes the `feat(03-04)` GREEN commit (b7015d5); the RED run failed with `AttributeError: module 'seed' has no attribute 'bulk_seed'` (a genuine missing-behavior failure, not a collection error). Tasks 2 and 3 are new infra/config artifacts validated structurally (py_compile, grep, YAML parse) per the plan's `tdd_note`, not via artificial unit RED tests.
