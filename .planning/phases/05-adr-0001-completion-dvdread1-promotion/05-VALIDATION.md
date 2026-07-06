---
phase: 5
slug: adr-0001-completion-dvdread1-promotion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. Per-task map and Wave 0
> requirements are finalized by the planner/executor.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (API against in-memory SQLite via FastAPI TestClient; `ovid-client` with `real_disc` hardware markers) |
| **Config file** | `api/tests/conftest.py` (patches `DATABASE_URL` before app import; SQLite/UUID shim) |
| **Quick run command** | `pytest api/tests -q` |
| **Full suite command** | `pytest api/tests ovid-client/tests -q` |
| **Estimated runtime** | ~TBD seconds (planner to confirm) |

---

## Sampling Rate

- **After every task commit:** Run `pytest api/tests -q`
- **After every plan wave:** Run the full suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** TBD seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _populated by planner_ | | | IDENT-03 / IDENT-04 / IDENT-05 / WR-02 | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fingerprint-registry model + cross-table-race regression test scaffolding (WR-02)
- [ ] Alembic-independent promotion function extracted for SQLite-testable coverage (D-01 / IDENT-04)
- [ ] Mixed-fleet regression: old client cannot demote `dvdread1-*` → `dvd1-*` (D-03 / IDENT-04)

*Planner finalizes against 05-RESEARCH.md § Validation Architecture. If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Quiesce→`alembic upgrade head`→resume runbook against real Postgres | IDENT-04 / D-04 / D-05 | CI never runs `alembic upgrade head` against Postgres; middleware toggle needs a service restart | Run the one-command wrapper against a Postgres instance per `docs/self-hosting.md`; confirm `dvdread1-*` promoted and `dvd1-*` still resolves |

*Planner may add/remove rows against 05-RESEARCH.md.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < TBDs
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
