---
phase: 3
slug: chapter-name-data
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (API)** | pytest 7.0+ |
| **Framework (Web)** | Vitest 4.1.2 |
| **Framework (Client)** | pytest 7.0+ |
| **Config file (API)** | api/tests/conftest.py |
| **Config file (Web)** | web/vitest.config.ts |
| **Config file (Client)** | ovid-client/tests/conftest.py |
| **Quick run (API)** | `cd api && python -m pytest tests/ -x --tb=short` |
| **Quick run (Web)** | `cd web && npx vitest run --reporter=verbose` |
| **Quick run (Client)** | `cd ovid-client && python -m pytest tests/ -x --tb=short` |
| **Full suite command** | `cd api && python -m pytest tests/ -x --tb=short && cd ../web && npx vitest run --reporter=verbose && cd ../ovid-client && python -m pytest tests/ -x --tb=short` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run for affected component
- **After every plan wave:** Run full suite command (all three components)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CHAP-01 | — | N/A | unit | `cd api && python -m pytest tests/test_disc_submit.py -x` | ✅ extend | ⬜ pending |
| 03-01-02 | 01 | 1 | CHAP-02 | — | Pydantic max_length=200, ge=1 | unit | `cd api && python -m pytest tests/test_disc_submit.py -x` | ✅ extend | ⬜ pending |
| 03-01-03 | 01 | 1 | CHAP-03 | T-oversized-list | Max chapters per title validated | integration | `cd api && python -m pytest tests/test_disc_submit.py::test_submit_with_chapters -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | CHAP-04 | — | N/A | integration | `cd api && python -m pytest tests/test_disc_lookup.py::test_lookup_includes_chapters -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | CHAP-05 | — | N/A | integration | `cd api && python -m pytest tests/test_sync.py::test_sync_diff_includes_chapters -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | CHAP-09 | — | N/A | unit | `cd ovid-client && python -m pytest tests/test_mpls_parser.py -x` | ✅ extend | ⬜ pending |
| 03-02-02 | 02 | 2 | CHAP-10 | T-xml-entity | ElementTree no external entity expansion | unit | `cd ovid-client && python -m pytest tests/test_bdmt_parser.py -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | CHAP-08 | — | N/A | unit | `cd ovid-client && python -m pytest tests/test_cli_submit.py -x` | ✅ extend | ⬜ pending |
| 03-03-01 | 03 | 3 | CHAP-06 | T-xss | React auto-escapes chapter names | component | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | ✅ extend | ⬜ pending |
| 03-03-02 | 03 | 3 | CHAP-07 | — | N/A | component | `cd web && npx vitest run src/__tests__/submit.test.tsx` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_disc_submit.py` — extend with chapter submission tests (CHAP-03)
- [ ] `api/tests/test_disc_lookup.py` — extend with chapter lookup tests (CHAP-04)
- [ ] `api/tests/test_sync.py` — extend with chapter sync tests (CHAP-05)
- [ ] `ovid-client/tests/test_bdmt_parser.py` — new file for bdmt XML parsing (CHAP-10)
- [ ] `ovid-client/tests/test_ifo_parser.py` — extend with cell-time extraction tests (CHAP-12/D-12)
- [ ] `web/src/__tests__/disc-detail.test.tsx` — extend with chapter display tests (CHAP-06)
- [ ] `web/src/__tests__/submit.test.tsx` — extend with chapter entry tests (CHAP-07)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chapter expand/collapse animation is smooth | CHAP-06 (D-10) | Visual animation quality | Open disc detail page, click chapter expand, verify no janky transitions |
| Chapter entry tab order feels natural | CHAP-07 (D-11) | UX interaction quality | Open submit form, add chapter rows, tab between fields |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
