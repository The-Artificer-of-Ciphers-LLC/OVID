---
phase: 7
slug: web-ui-production-readiness
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-07
validated: 2026-07-07
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

Two stacks — both already installed and configured in-repo. **No new test framework is added this phase**
(D-02: no new runtime deps).

| Property | Web (Vitest) | API (pytest) |
|----------|--------------|--------------|
| **Framework** | Vitest ^4.1.2 + @testing-library/react ^16.3.2 + jest-dom ^6.9.1 + user-event ^14.6.1 | pytest ≥7 against in-memory SQLite via FastAPI `TestClient` |
| **Config file** | `web/vitest.config.ts` (jsdom env, `@/` alias, `src/test-setup.ts`) | `api/tests/conftest.py` (patches `DATABASE_URL` before `app` import) |
| **Quick run command** | `cd web && npx vitest run src/__tests__/<file>` | `cd api && .venv/bin/python -m pytest tests/<module> -x` |
| **Full suite command** | `cd web && npm test` (`vitest run`) | `cd api && .venv/bin/python -m pytest tests/ -q` |
| **Estimated runtime** | ~2-5s per file · ~10s full (58+ tests) | ~<30s per module · ~30-60s full (~442 tests) |

---

## Sampling Rate

- **After every task commit:** Run the single affected web `npx vitest run src/__tests__/<file>` or the touched api `pytest tests/<module>` (< 30s feedback).
- **After every plan wave:** Run the full suite for the touched stack — `cd web && npm test` and/or `cd api && .venv/bin/python -m pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Both full suites (web + api) green; the D-06 staging smoke is a manual gate (07-08 Task 3).
- **Max feedback latency:** ~30 seconds (single-file / single-module run).

---

## Per-Task Verification Map

Keyed to the tasks that exist in the eight 07-NN plans. Per-task *secure behaviors* are specified in each
plan's `<threat_model>` (Threat Ref column links them). Pipes inside grep commands are escaped `\|`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Test Type | Automated Command | Test File | Status |
|---------|------|------|-------------|------------|-----------|-------------------|-----------|--------|
| 07-01-01 | 01 | 1 | D-02 token layer (WEBUI-01/02/03/04 foundation) | T-07-01-01 | static/grep | `cd web && grep -c 'color-accent' app/globals.css && grep -Ec 'Helvetica\|custom-variant' app/globals.css` | globals.css (source) | ⬜ pending |
| 07-01-02 | 01 | 1 | D-02 / D-03 primitives | T-07-01-02/03 | component | `cd web && npx vitest run src/__tests__/primitives.test.tsx` | primitives.test.tsx (new, authored 07-01-03) | ⬜ pending |
| 07-01-03 | 01 | 1 | D-03 a11y floor (primitive tests) | — | component | `cd web && npx vitest run src/__tests__/primitives.test.tsx` | primitives.test.tsx (new) | ⬜ pending |
| 07-02-01 | 02 | 1 | WEBUI-04 / D-04 merge redirect (RED) | T-07-02-01 | api (pytest) | `cd api && .venv/bin/python -m pytest tests/test_auth_merge_redirect.py -x` | test_auth_merge_redirect.py (new) | ⬜ pending |
| 07-02-02 | 02 | 1 | WEBUI-04 / D-04 + R-3 cleanup (GREEN) | T-07-02-01/02/03/04 | api (pytest) | `cd api && .venv/bin/python -m pytest tests/test_auth_merge_redirect.py -x` | test_auth_merge_redirect.py | ⬜ pending |
| 07-03-01 | 03 | 1 | WEBUI-02/03 / R-1 + R-2 (RED) | T-07-03-01/02 | api (pytest) | `cd api && .venv/bin/python -m pytest tests/test_set_redaction_and_limit.py -x` | test_set_redaction_and_limit.py (new) | ⬜ pending |
| 07-03-02 | 03 | 1 | WEBUI-02/03 / R-1 + R-2 (GREEN) | T-07-03-01/02 | api (pytest) | `cd api && .venv/bin/python -m pytest tests/test_set_redaction_and_limit.py -x` | test_set_redaction_and_limit.py | ⬜ pending |
| 07-04-01 | 04 | 2 | WEBUI-02 (alias render + withheld message) | T-07-04-01/03 | component | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | disc-detail.test.tsx (extend) | ⬜ pending |
| 07-04-02 | 04 | 2 | WEBUI-02 / D-01 R-4 parity | — | component + grep | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx && grep -c 'text-xs' web/components/SiblingDiscs.tsx web/components/ChapterList.tsx` | disc-detail.test.tsx | ⬜ pending |
| 07-04-03 | 04 | 2 | WEBUI-02 (alias/withheld tests) | — | component | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | disc-detail.test.tsx (extend) | ⬜ pending |
| 07-05-01 | 05 | 2 | WEBUI-01 (search anchor + primitives + AA contrast) | T-07-05-01 | component + grep | `cd web && npx vitest run src/__tests__/pages.test.tsx && grep -c 'text-neutral-400' web/app/page.tsx` | pages.test.tsx (extend) | ⬜ pending |
| 07-05-02 | 05 | 2 | WEBUI-01 (a11y/copy tests) | — | component | `cd web && npx vitest run src/__tests__/pages.test.tsx` | pages.test.tsx (extend) | ⬜ pending |
| 07-06-01 | 06 | 2 | WEBUI-03 (primitives + aria-live) | T-07-06-01 | component | `cd web && npx vitest run src/__tests__/submit.test.tsx` | submit.test.tsx (extend) | ⬜ pending |
| 07-06-02 | 06 | 2 | WEBUI-03 / D-01 R-4 parity | — | component + grep | `cd web && npx vitest run src/__tests__/submit.test.tsx && grep -c 'text-xs' web/components/SetSearchInput.tsx web/components/ChapterEditor.tsx` | submit.test.tsx | ⬜ pending |
| 07-06-03 | 06 | 2 | WEBUI-03 (a11y tests) | — | component | `cd web && npx vitest run src/__tests__/submit.test.tsx` | submit.test.tsx (extend) | ⬜ pending |
| 07-07-01 | 07 | 2 | WEBUI-04 (add-flow decision, Open Q1) | — | manual (decision) | — `checkpoint:decision` (see Manual-Only) | N/A | ⬜ pending |
| 07-07-02 | 07 | 2 | WEBUI-04 / D-05 merge banner (RED) | T-07-07-01 | component | `cd web && npx vitest run src/__tests__/settings.test.tsx` | settings.test.tsx (new) | ⬜ pending |
| 07-07-03 | 07 | 2 | WEBUI-04 / D-05 + ME-02 (GREEN) | T-07-07-01/02/03/04/05 | component | `cd web && npx vitest run src/__tests__/settings.test.tsx` | settings.test.tsx | ⬜ pending |
| 07-08-01 | 08 | 3 | WEBUI-01 / D-06 (staging env docs) | T-07-08-01 | docs/grep | `grep -c 'staging' docs/deployment.md && grep -Ec 'CORS_ORIGINS\|NEXT_PUBLIC_API_URL' .env.example` | deployment.md / .env.example | ⬜ pending |
| 07-08-02 | 08 | 3 | WEBUI-01 (phase gate — full suites) | — | integration | `cd web && npm test && cd ../api && .venv/bin/python -m pytest tests/ -q` | full web + api suites | ⬜ pending |
| 07-08-03 | 08 | 3 | D-06 / D-03 (staging + a11y sign-off) | T-07-08-01/03 | manual (human-verify) | — `checkpoint:human-verify` (see Manual-Only) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

**Existing infrastructure covers all phase requirements.** Vitest (web) and pytest (api) are already
installed and configured — no new test framework is required, so there is no framework-install Wave 0.

There is also no *separate* test-scaffold wave: each plan creates or extends its own test file test-first
within its own tasks (a RED / extend task precedes the GREEN implementation in the same plan), so no
`<automated>` verify references a test file that some earlier wave must create. Where each NEW test file
is authored:

- `web/src/__tests__/primitives.test.tsx` → 07-01 Task 3 (RED partner to Task 2)
- `api/tests/test_auth_merge_redirect.py` → 07-02 Task 1 (RED)
- `api/tests/test_set_redaction_and_limit.py` → 07-03 Task 1 (RED)
- `web/src/__tests__/settings.test.tsx` → 07-07 Task 2 (RED)

Existing test files extended in-plan (already present in repo): `disc-detail.test.tsx` (07-04),
`pages.test.tsx` (07-05), `submit.test.tsx` (07-06).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Staging deploy end-to-end over TLS (07-08 Task 3, blocking) | WEBUI-01 / D-06 | Real external infra (redshirt TLS, DNS, staging CORS_ORIGINS) — not automatable in CI | On the live staging HTTPS URL walk the 5 checks: (1) search anchor + AA-contrast empty state in both themes; (2) disc-detail `data-testid="fingerprint-aliases"` lists ALL identity strings + primary badge, and the unverified "Structure withheld…" message; (3) submit preview + success with keyboard-operable fields/set-toggle; (4) settings "Link a provider" add flow, unlink min-one guard, styled enumeration-safe merge banner (no email/user-id); (5) the D-03 a11y floor |
| D-03 accessibility sign-off (07-08 Task 3, blocking) | D-03 | Visible focus rings + WCAG-AA contrast + keyboard operability in BOTH themes need human judgement | Tab through every interactive element on all four surfaces (visible `:focus-visible` ring); Escape dismisses any dropdown/dialog; verify WCAG AA (4.5:1 text, 3:1 UI) in light AND dark |
| Add-provider browser-flow mechanism (07-07 Task 1) | WEBUI-04 (research Open Q1) | Design decision (`checkpoint:decision`), not a behavioral test — chooses the backend-vs-frontend link flow | Select option-b (frontend-only, default) or option-a (backend signed-token); record the choice in 07-07-SUMMARY before Task 3 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — every code/test task carries an automated command; the only two non-automated tasks are legitimate gates (07-07 Task 1 `checkpoint:decision`, 07-08 Task 3 `checkpoint:human-verify`), recorded in Manual-Only Verifications
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — the two manual gate tasks are isolated (07-07 Task 1 is followed by automated 07-07 Tasks 2-3; 07-08 Task 3 is the terminal task after automated 07-08 Tasks 1-2)
- [x] Wave 0 covers all MISSING references — existing Vitest + pytest infra covers everything; new test files are authored test-first within their owning plans (no dangling MISSING)
- [x] No watch-mode flags — all web commands use `vitest run` (not watch); all api commands use plain `pytest` (no `-f`/watch)
- [x] Feedback latency < 30s — per-task single-file (web) / single-module (api) runs complete in < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-07
