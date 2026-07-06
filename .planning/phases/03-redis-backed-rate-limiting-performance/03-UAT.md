---
status: complete
phase: 03-redis-backed-rate-limiting-performance
source: [03-VERIFICATION.md]
started: 2026-07-06T13:27:52Z
updated: 2026-07-06T13:45:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Load-test the real Redis-backed multi-worker stack and confirm p95 ≤ 500ms (INFRA-03)

expected: |
  API p95 ≤ 500ms and error ratio ≤ 1% against the real Redis-backed
  `gunicorn -w 4` stack (not the retiring `memory://` single-worker config, per D-14).
result: pass
evidence: |
  Ran the Locust p95 gate against the honest stack (Postgres 16 + live Redis +
  `gunicorn -w 4`, real Redis-backed multi-worker limiter) on the holodeck test
  server, isolated on ports 18000/55432/56379 so the live dev/prod/test stacks
  were untouched. Locust gate exit code 0 (PASS).
  Aggregated: 43,536 requests, 0 failures (0.00% error ratio), median 75ms,
  **p95 = 270ms**, p99 = 390ms, max 610ms — comfortably inside the 500ms / 1%
  budget. Per-endpoint p95: lookup 190ms, submit 200ms, search 380ms.
  Confirms the CR-01 fix (raised read limits) — 43K requests with zero throttle
  failures, so the gate measured real handler latency rather than 429s.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
