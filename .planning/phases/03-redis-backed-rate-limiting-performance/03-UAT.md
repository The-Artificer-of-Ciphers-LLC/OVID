---
status: testing
phase: 03-redis-backed-rate-limiting-performance
source: [03-VERIFICATION.md]
started: 2026-07-06T13:27:52Z
updated: 2026-07-06T13:27:52Z
---

## Current Test

number: 1
name: Load-test the real Redis-backed multi-worker stack and confirm p95 ≤ 500ms (INFRA-03)
expected: |
  Running the load-test harness against the ACTUAL Redis-backed, multi-worker
  gunicorn config (gunicorn -w 4 + Postgres + Redis) reports p95 ≤ 500ms and
  error ratio ≤ 1%. The harness gate (loadtest/locustfile.py) exits non-zero if
  either budget is breached, so a green run IS the pass signal.
awaiting: user response

## Tests

### 1. Load-test the real Redis-backed multi-worker stack and confirm p95 ≤ 500ms (INFRA-03)

expected: |
  API p95 ≤ 500ms and error ratio ≤ 1% against the real Redis-backed
  `gunicorn -w 4` stack (not the retiring `memory://` single-worker config, per D-14).

how to run (either path):
  - CI (recommended, honest stack): dispatch the non-blocking workflow —
    `gh workflow run loadtest.yml` (or the Actions UI "Run workflow" button).
    It stands up Postgres + Redis + `gunicorn -w 4`, seeds the bulk dataset,
    mints a JWT, runs the Locust gate, and publishes p95/p99 to the job
    summary + `results_stats.csv` artifact.
  - Local: bring up the multi-worker stack with Redis
    (`docker compose -f docker-compose.yml -f docker-compose.test.yml up`),
    seed with `python api/scripts/seed.py --count <N>`, then run
    `locust -f loadtest/locustfile.py --headless ...` against it.

pass criteria: published/observed p95 ≤ 500ms AND error ratio ≤ 1%.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
