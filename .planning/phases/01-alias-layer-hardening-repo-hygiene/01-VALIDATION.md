---
phase: 1
slug: alias-layer-hardening-repo-hygiene
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (API, against in-memory SQLite via FastAPI TestClient) |
| **Config file** | `api/` (pytest invoked as `pytest tests/` from `api/`) |
| **Quick run command** | `cd api && pytest tests/ -q` |
| **Full suite command** | `cd api && pytest tests/` |
| **Estimated runtime** | ~{N} seconds (confirm on first run) |

---

## Sampling Rate

- **After every task commit:** Run `cd api && pytest tests/ -q`
- **After every plan wave:** Run `cd api && pytest tests/`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** {N} seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | REQ-{XX} | T-{N}-01 / — | {expected secure behavior or "N/A"} | unit | `{command}` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*(Planner populates this map from the finalized PLAN.md task IDs — one row per task, tying each requirement to its automated `pytest` command.)*

---

## Wave 0 Requirements

- [ ] Existing infrastructure covers all phase requirements — confirm at plan time.

*Note (from 01-RESEARCH.md): the API suite already runs `pytest tests/` on every PR with no marker exclusions, and `api/tests/conftest.py` provides the `seed_test_disc` fixture. VERIFY-02 requires UPDATING existing tests (`test_disc_submit.py`, `test_dispute.py`) that currently assert the old silent verified→disputed flip, plus a new "verified stays verified" test. IDENT-05 needs a new `dvd1-`-prefixed golden-fixture seeder.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-worker concurrent-submission race safety (IDENT-02) | IDENT-02 | True concurrency needs real Postgres + parallel gunicorn workers; SQLite TestClient is single-threaded | Deferred: document a deterministic IntegrityError-path unit test (savepoint retry) as the automated proxy; note real-concurrency check as manual/load. |

*Automated proxy preferred wherever possible — see planner tasks.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < {N}s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
