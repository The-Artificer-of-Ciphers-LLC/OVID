---
phase: 03-redis-backed-rate-limiting-performance
plan: 03
subsystem: deployment-infra
tags: [redis, rate-limiting, docker-compose, deployment, documentation, infra-01, infra-02]
requires:
  - "03-01: env-driven Redis backend in api/app/rate_limit.py (REDIS_URL / OVID_WORKERS / WEB_CONCURRENCY)"
provides:
  - "redis:7-alpine service in prod + test compose stacks (internal-only, ephemeral)"
  - "REDIS_URL + OVID_WORKERS wired to the gunicorn -w 4 api service in prod + test"
  - "Documented env-driven backend, when-Redis-required rule, D-06 fail-fast guard, and D-01/D-02 fail-open outage decision"
affects:
  - "docker-compose.prod.yml"
  - "docker-compose.test.yml"
  - ".env.example"
  - "docs/self-hosting.md"
  - "docs/deployment.md"
  - "docs/OVID-technical-spec.md"
tech-stack:
  added:
    - "redis:7-alpine (compose service, prod + test only)"
  patterns:
    - "Docker Compose override merge: depends_on maps merge with base (db + redis)"
    - "Ephemeral Redis (--save \"\" --appendonly no, no volume) for disposable rate-limit counters"
    - "Internal-only service (no published host port) mirroring the prod db"
key-files:
  created: []
  modified:
    - "docker-compose.prod.yml — redis service + REDIS_URL/OVID_WORKERS env + depends_on healthcheck"
    - "docker-compose.test.yml — redis service + REDIS_URL/OVID_WORKERS env + depends_on healthcheck"
    - ".env.example — REDIS_URL + OVID_WORKERS entries with when-required guidance"
    - "docs/self-hosting.md — 'Rate Limiting & Redis (you don't need it)' section"
    - "docs/deployment.md — ovid-prod-redis table row + 'Rate Limiting Backend (Redis)' section"
    - "docs/OVID-technical-spec.md — fail-open/fail-closed decision + INFRA-03 harness reference"
decisions:
  - "Kept base docker-compose.yml unchanged — single-worker self-host/mirror path keeps memory:// (D-05a)"
  - "redis:7-alpine chosen over 8-alpine/valkey (conservative image pick; client pinned redis<8 in Plan 01)"
  - "Test redis also internal-only (no host port) — only prod was mandated internal, but test needs no debug port for an ephemeral counter store"
  - "Documented the D-01/D-02 fail-open outage decision + D-06 guard across three docs; noted D-04 route-split deferral as a one-liner"
metrics:
  tasks_completed: 2
  files_modified: 6
  commits: 2
  completed_date: 2026-07-06
status: complete
requirements: [INFRA-01, INFRA-02]
---

# Phase 3 Plan 3: Redis Deployment Wiring & Documentation Summary

Wired a real `redis:7-alpine` service into the two multi-worker (`gunicorn -w 4`) compose stacks and documented the env-driven Redis rate-limit backend end-to-end, so the Plan 01 code has a shared store to talk to in prod/test while the single-worker self-host story stays untouched (D-05a).

## What Was Built

### Task 1 — Redis service in prod + test compose (INFRA-01) — commit `a78f6d5`

Added an internal-only, ephemeral `redis` service to **both** `docker-compose.prod.yml` and `docker-compose.test.yml`:

- `image: redis:7-alpine`, `restart: unless-stopped`
- `command: ["redis-server", "--save", "", "--appendonly", "no"]` — no RDB/AOF persistence, no volume (rate-limit counters are short-window and disposable)
- Healthcheck `["CMD", "redis-cli", "ping"]` (interval 5s, timeout 3s, retries 5), mirroring the base `db` healthcheck shape
- `api` service gains `depends_on: redis: {condition: service_healthy}` (merges with the base `db` healthcheck dependency) and `REDIS_URL: redis://redis:6379/0` + `OVID_WORKERS: "4"` in its `environment` block (matching the existing `-w 4`)
- Prod redis publishes **no host port** (internal-only, mirroring the prod `db`'s reset ports); test redis is likewise internal-only
- Base `docker-compose.yml` left completely unchanged (single uvicorn `--reload` worker keeps `memory://`, already correct — D-05a)

### Task 2 — Documentation + .env.example (INFRA-02) — commit `11ef995`

- **`.env.example`**: new `REDIS_URL` + `OVID_WORKERS` block documenting when Redis is required (multi-worker) vs optional (single-worker → leave unset → `memory://`), plus the fail-fast guard note. Both keys are commented-out (single-worker is the `.env.example` default).
- **`docs/self-hosting.md`**: "Rate Limiting & Redis (you don't need it)" section — reassures Pi/NAS self-hosters that the single-worker stack needs no Redis, while fully documenting the env-driven backend, the D-06 boot guard, and the D-01/D-02 fail-open outage behavior.
- **`docs/deployment.md`**: added an `ovid-prod-redis` row (internal-only, port 6379) to the prod container table and a "Rate Limiting Backend (Redis)" section covering backend selection, the when-required rule, the D-06 fail-fast guard, and the D-01/D-02 fail-open decision (with the D-04 route-split deferral as a one-liner).
- **`docs/OVID-technical-spec.md`** (§~676): recorded the fail-open/fail-closed decision beside the existing Phase-3 limiter mention and referenced the INFRA-03 load-test harness (validates p95 ≤ 500ms against the real Redis-backed multi-worker config, not the retiring `memory://` one).

## Verification

- `docker compose -f docker-compose.yml -f docker-compose.test.yml config` and `... -f docker-compose.prod.yml config` both validate (exit 0). The only output is the standard "variable not set, defaulting to blank" warnings for OAuth/secret placeholders — pre-existing `docker compose config` behavior when no `.env` is present, unrelated to this change (those values come from `.env`/`.env.production.example` at deploy time).
- Merged-config assertions confirmed: `redis:7-alpine` present in both overrides; `REDIS_URL` + `OVID_WORKERS` present on `api` in both; base compose has **no** redis service (D-05a preserved).
- Prod redis block in the merged config has no `ports:`/`published:` key — internal-only confirmed programmatically.
- Docs+env grep gate passes: `.env.example` has `REDIS_URL` + `OVID_WORKERS`; `docs/self-hosting.md` and `docs/deployment.md` both document the outage `fallback` and the boot guard; `docs/OVID-technical-spec.md` records the Redis decision and references the load-test harness / p95.

## TDD Gate Compliance

Both tasks are deployment-config / documentation only (compose YAML, `.env.example`, `.md` docs) — `is_behavior_adding = false` (no executable source files, no `<behavior>` blocks). Per the plan's `<tdd_note>` these are exempt from the RED→GREEN cycle. Executable rate-limit behavior was already proven by Plan 01's tests; this plan is deployment wiring + written decision only. Compose validity was used as the Self-Check evidence in lieu of unit tests.

## Deviations from Plan

None — plan executed as written. Two minor discretionary choices within the plan's latitude:
1. The plan's `<verify>` used `python3 -c "import yaml..."`, but system `python3` has no `pyyaml`. Substituted the equivalent (and stronger) check of grepping the fully-resolved `docker compose config` output, which the plan already mandated as the primary gate. No behavior change — same assertions, more authoritative source (the merged/validated config rather than a raw file parse).
2. Made the **test** redis internal-only too (the plan only mandated prod be internal-only). An ephemeral counter store needs no host-port debug access in test, and it keeps the two stacks symmetric.

## Out of Scope / Untouched

- `.planning/phases/02-two-contributor-verification-workflow/02-PATTERNS.md` (untracked) and `.planning/config.json` (modified) were already present in the working tree at plan start — Phase-2 / pre-existing, left untouched.
- No code or test changes (Plan 01 owns the `rate_limit.py` behavior + tests; Plan 04 owns the load-test harness).

## Self-Check: PASSED

All 6 modified files + the SUMMARY.md exist on disk; both task commits (`a78f6d5`, `11ef995`) are present in git history.
