---
phase: 3
slug: redis-backed-rate-limiting-performance
status: draft
nyquist_compliant: true
wave_0_complete: true
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

*Populated from the four executed plans (03-01..03-04). Every INFRA requirement maps to at least one automated signal:*

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|--------------------|--------|
| 03-01-01 | 03-01 | 1 | INFRA-01 (dep groundwork) | dependency check | `cd api && .venv/bin/python -c "import redis, limits.storage; from importlib.metadata import version; v=version('redis'); assert tuple(int(x) for x in v.split('.')[:1]) < (8,), v"` | ⬜ pending |
| 03-01-02 | 03-01 | 1 | INFRA-01, INFRA-02 | unit (tdd) | `cd api && .venv/bin/python -m pytest tests/test_rate_limit_backend.py tests/test_rate_limit_fallback.py -x` | ⬜ pending |
| 03-01-03 | 03-01 | 1 | INFRA-01 (D-06 fail-fast guard) | unit (tdd) | `cd api && .venv/bin/python -m pytest tests/test_startup_guard.py -x` | ⬜ pending |
| 03-02-01 | 03-02 | 2 | INFRA-04 | unit (tdd) | `cd api && .venv/bin/python -m pytest tests/test_write_rate_limit.py -x` | ⬜ pending |
| 03-02-02 | 03-02 | 2 | INFRA-04 (D-10 seam, no double-count) | unit (tdd) | `cd api && .venv/bin/python -m pytest tests/test_write_rate_limit.py -x && .venv/bin/python -m pytest tests/test_anti_sybil.py -q` | ⬜ pending |
| 03-03-01 | 03-03 | 2 | INFRA-01 (compose wiring) | config validation | `docker compose -f docker-compose.test.yml config >/dev/null && docker compose -f docker-compose.prod.yml config >/dev/null` (plus redis-service/base-unchanged assertions) | ⬜ pending |
| 03-03-02 | 03-03 | 2 | INFRA-02 (documentation) | doc grep | `grep -q 'REDIS_URL' .env.example && grep -q 'OVID_WORKERS' .env.example && grep -qi 'fallback' docs/self-hosting.md docs/deployment.md && grep -qi 'redis' docs/OVID-technical-spec.md` | ⬜ pending |
| 03-04-01 | 03-04 | 3 | INFRA-03 (D-13 dataset) | unit | `cd api && .venv/bin/python -m py_compile scripts/seed.py && .venv/bin/python -m pytest tests/test_seed.py -x` | ⬜ pending |
| 03-04-02 | 03-04 | 3 | INFRA-03 (harness) | static check | `python3 -m py_compile loadtest/locustfile.py && grep -q 'get_response_time_percentile' loadtest/locustfile.py && grep -q 'process_exit_code' loadtest/locustfile.py && grep -Eq 'locust>=2\.44,<3' loadtest/requirements.txt` | ⬜ pending |
| 03-04-03 | 03-04 | 3 | INFRA-03 (CI wiring, D-12/D-14) | config validation | `python3 -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/loadtest.yml')); on=d.get('on') or d.get(True); assert 'workflow_dispatch' in on and 'schedule' in on; assert 'push' not in on and 'pull_request' not in on"` | ⬜ pending |
| — | 03-04 | 3 (out-of-band) | INFRA-03 (p95 gate) | load test | `locust -f loadtest/locustfile.py --headless -u 100 -r 10 -t 3m --host http://localhost:8000 --csv loadtest/results` (manual/scheduled, not per-commit) | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `redis` python client dependency pinned `>=5,<8` in `api/requirements.txt` (limits 5.8.0 caps `<8.0.0`)
- [ ] `redis` service in `docker-compose.prod.yml` + `docker-compose.test.yml`
- [ ] `loadtest/` Locust harness + p95 gate wrapper
- [ ] Extend `api/scripts/seed.py` (seeds only 1 disc today) to seed low-thousands for a representative load-test dataset
- [ ] `api/tests/test_rate_limit.py` — outage-fallback + stacked-write-limit + multi-worker-correctness tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| p95 ≤ 500ms on production-shaped hardware | INFRA-03 | CI shared-runner jitter makes an absolute-ms gate flaky (D-12); authoritative measurement is the documented pre-release manual run | Bring up Postgres + `gunicorn -w 4` + Redis, seed dataset, run `locust -f loadtest/locustfile.py --headless ...`, read p95 from CSV summary |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-06
