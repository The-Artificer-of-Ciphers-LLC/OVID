---
phase: 2
slug: multi-disc-set-support
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (API), vitest 4.1.2 (web), pytest (ovid-client) |
| **Config file** | `api/pytest.ini` or inline, `web/vitest.config.ts` |
| **Quick run command** | `cd api && python -m pytest tests/test_disc_sets.py -x -q` / `cd web && npx vitest run src/__tests__/disc-detail.test.tsx --reporter=verbose` |
| **Full suite command** | `cd api && python -m pytest tests/ -x -q` / `cd web && npx vitest run` / `cd ovid-client && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds (API) / ~10 seconds (web) / ~5 seconds (ovid-client) |

---

## Sampling Rate

- **After every task commit:** Run quick run command for the affected layer (API or web)
- **After every plan wave:** Run full suite for both layers
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SET-01 | T-02-01 | Pydantic validates input, auth required | unit | `pytest tests/test_disc_sets.py::test_create_set` | W0 | pending |
| 02-01-02 | 01 | 1 | SET-02 | T-02-03 | N/A (public read) | unit | `pytest tests/test_disc_sets.py::test_get_set_detail` | W0 | pending |
| 02-01-03 | 01 | 1 | SET-03 | T-02-02 | disc_number validated against total_discs | unit | `pytest tests/test_disc_submit.py::test_submit_with_set` | W0 | pending |
| 02-01-04 | 01 | 1 | SET-04 | — | N/A | unit | `pytest tests/test_disc_lookup.py::test_lookup_with_set` | W0 | pending |
| 02-01-05 | 01 | 1 | SET-05 | — | seq_num incremented on set changes | unit | `pytest tests/test_disc_sets.py::test_set_seq_num` | W0 | pending |
| 02-02-01 | 02 | 2 | SET-06 | — | N/A | unit | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | W0 | pending |
| 02-02-02 | 02 | 2 | SET-07 | — | N/A | unit | `cd web && npx vitest run src/__tests__/submit.test.tsx` | Exists (extend) | pending |
| 02-03-01 | 03 | 2 | SET-08 | T-02-10 | Bearer token in Authorization header | unit | `cd ovid-client && python -m pytest tests/test_client_sets.py -x` | W0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_disc_sets.py` — stubs for SET-01, SET-02, SET-05
- [ ] Extend `api/tests/test_disc_submit.py` — stubs for SET-03
- [ ] Extend `api/tests/test_disc_lookup.py` — stubs for SET-04
- [ ] `web/src/__tests__/disc-detail.test.tsx` — stubs for SET-06
- [ ] Extend `web/src/__tests__/submit.test.tsx` — stubs for SET-07
- [ ] `ovid-client/tests/test_client_sets.py` — stubs for SET-08

*Existing test infrastructure covers framework setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sibling card visual layout | SET-06 | Visual alignment and responsive behavior | Open disc detail for a disc in a set, verify horizontal card row renders correctly |
| Search-as-you-type UX | SET-07 | Interactive timing/debounce behavior | Type in set search field on submit form, verify suggestions appear |
| CLI wizard prompts | SET-08 | Interactive Rich prompts require terminal | Run `ovid submit` with a multi-disc source, verify set prompting flow |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
