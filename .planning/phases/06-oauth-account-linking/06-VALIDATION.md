---
phase: 6
slug: oauth-account-linking
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Populated from 06-RESEARCH.md § Validation Architecture; per-task map filled by the planner.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (API — `api/tests/`, in-memory SQLite via FastAPI TestClient) |
| **Config file** | `api/` project-local venv (each Python subtree runs under its own venv — bare `python`/`pytest` is wrong) |
| **Quick run command** | `api/.venv/bin/python -m pytest tests/test_auth_*.py -q` (run from `api/`) |
| **Full suite command** | `api/.venv/bin/python -m pytest -q` (run from `api/`) |
| **Estimated runtime** | ~30–60 seconds |

> Note: confirm the exact venv path from the repo's api test setup during Wave 0; the planner
> pins the precise invocation. Existing auth tests use plain `unittest.mock` (no respx) — new
> tests follow that pattern.

---

## Sampling Rate

- **After every task commit:** Run the quick command (`test_auth_*.py`)
- **After every plan wave:** Run the full API suite
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-XX-XX | XX | X | AUTH-08 | nOAuth merge takeover | Merge requires re-auth of existing account via already-linked provider; unverified/unauthenticated merge rejected | unit | `pytest tests/test_auth_linking.py -q` | ❌ W0 | ⬜ pending |
| 6-XX-XX | XX | X | AUTH-09 | — | finalize_auth isolated: verified-email merge success / unverified-email rejection / merge-without-reauth rejection | unit | `pytest tests/test_finalize_auth.py -q` | ❌ W0 | ⬜ pending |
| 6-XX-XX | XX | X | AUTH-10 | localhost SSRF bypass in prod | App refuses to boot when localhost bypass reachable under `OVID_ENV=production` | unit | `pytest tests/test_auth_boot_guard.py -q` | ❌ W0 | ⬜ pending |
| 6-XX-XX | XX | X | AUTH-05 | Mastodon SSRF | Reserved-IP/hostname rejected; IPv6 covered; no redirect-following on outbound requests | unit | `pytest tests/test_auth_mastodon.py -q` | ✅ | ⬜ pending |

*Planner replaces these seed rows with the concrete per-task map. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_finalize_auth.py` — new isolated unit-test file for `finalize_auth` (AUTH-09)
- [ ] `api/tests/test_auth_boot_guard.py` — new test for the `OVID_ENV` import-time boot assertion (AUTH-10)
- [ ] PendingAccountLink flow tests folded into `api/tests/test_auth_linking.py` (AUTH-06/07/08)
- [ ] Existing `api/tests/conftest.py` fixtures cover the new table (SQLite/Postgres UUID shim already present)

*Existing auth test infrastructure (`test_auth_*.py`, `conftest.py`) covers most phase requirements; the three files above are the net-new additions.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live sign-in round-trip with real provider credentials | AUTH-01/02/03/04 | Requires real GitHub/Google/Apple/Mastodon app registrations + browser redirect | Follow `docs/auth-setup.md` per-provider steps against a configured instance; confirm callback issues a JWT |

*Automated tests mock provider token exchange; a real end-to-end sign-in is a pre-release manual check.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
