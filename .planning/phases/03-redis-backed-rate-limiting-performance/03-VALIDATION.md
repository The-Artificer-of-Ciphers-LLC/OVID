---
phase: 3
slug: redis-backed-rate-limiting-performance
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Per-task map is populated after planning (tasks do not exist until PLAN.md files are written).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (API), Locust (load test — Wave 0 installs) |
| **Config file** | `api/` pytest (no dedicated ini); load test config new under `loadtest/` |
| **Quick run command** | `cd api && python -m pytest tests/test_rate_limit.py -q` |
| **Full suite command** | `cd api && python -m pytest -q` |
| **Estimated runtime** | ~30–60 seconds (unit/integration); load test runs out-of-band (non-blocking CI job) |

**Note:** Existing pytest runs against in-memory SQLite via TestClient. INFRA-01 (multi-worker correctness) and INFRA-02 (Redis-outage behavior) need integration-level validation beyond the SQLite/TestClient path — the outage test uses the deterministic monkeypatch of `limits.storage.RedisStorage.incr` → `ConnectionError` (no live Redis needed). INFRA-03's p95 gate is validated by the Locust load test against the real Postgres + `gunicorn -w 4` + Redis stack, run as a non-blocking `workflow_dispatch`/scheduled job, NOT per-PR.

---

## Sampling Rate

- **After every task commit:** Run the quick command for the touched area
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green; load-test p95 evidence captured out-of-band
- **Max feedback latency:** ~60 seconds (unit/integration); load test is asynchronous by design (D-12)

---

## Per-Task Verification Map

*Populated after planning — see PLAN.md task IDs. Every INFRA requirement maps to at least one automated signal:*

| Requirement | Secure/Correct Behavior | Test Type | Validation Signal |
|-------------|-------------------------|-----------|-------------------|
| INFRA-01 | One shared limit across 4 workers (no Nx inflation) | integration | Redis-backed counter shared across processes; assert limit enforced globally |
| INFRA-02 | Redis outage → in-memory fallback, self-heals | unit (injected) | Monkeypatch `RedisStorage.incr` → `ConnectionError`; assert fallback 200 then 429 at fallback cap; restore in `finally` |
| INFRA-03 | API p95 ≤ 500ms under real config | load (out-of-band) | Locust 70/20/10 mix vs Postgres + `-w 4` + Redis; p95 asserted via CSV/exit-code gate |
| INFRA-04 | Per-account write throttle live | integration | Stacked `methods=["POST"]` limit fires at 20/min; distinct from Phase-2 Postgres cooldown (no double-count) |

---

## Wave 0 Requirements

- [ ] `redis` python client dependency pinned `>=5,<8` in `api/requirements.txt` (limits 5.8.0 caps `<8.0.0`)
- [ ] `redis` service in `docker-compose.prod.yml` + `docker-compose.test.yml`
- [ ] `loadtest/` Locust harness + p95 gate wrapper
- [ ] Extend `scripts/seed.py` (seeds only 1 disc today) to seed low-thousands for a representative load-test dataset
- [ ] `api/tests/test_rate_limit.py` — outage-fallback + stacked-write-limit + multi-worker-correctness tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| p95 ≤ 500ms on production-shaped hardware | INFRA-03 | CI shared-runner jitter makes an absolute-ms gate flaky (D-12); authoritative measurement is the documented pre-release manual run | Bring up Postgres + `gunicorn -w 4` + Redis, seed dataset, run `locust -f loadtest/locustfile.py --headless ...`, read p95 from CSV summary |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
