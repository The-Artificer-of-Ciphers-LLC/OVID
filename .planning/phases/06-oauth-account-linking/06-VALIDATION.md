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
| 6-05 | 05 | 3 | AUTH-08 | nOAuth merge takeover | Old session-carried implicit-merge path removed; merge requires re-auth via already-linked provider; GitHub email read from verified `/user/emails` | unit | `.venv/bin/python -m pytest tests/test_auth_linking.py -q` | ❌ W0 | ⬜ pending |
| 6-04 | 04 | 2 | AUTH-09 | nOAuth merge takeover | `resolve_auth` (merge.py) isolated: verified-email merge success / unverified-email rejection / merge-without-reauth rejection | unit | `.venv/bin/python -m pytest tests/test_auth_merge.py -q` | ❌ W0 | ⬜ pending |
| 6-03 | 03 | 1 | AUTH-10 | config-drift bypass | App refuses to boot when localhost bypass reachable under `OVID_ENV=production` | unit | `.venv/bin/python -m pytest tests/test_auth_config.py -q` | ❌ W0 | ⬜ pending |
| 6-02 | 02 | 1 | AUTH-05 | Mastodon SSRF | Reserved-IP/hostname rejected; IPv6 (dual-stack getaddrinfo) covered; no redirect-following/no raw reflection on outbound requests | unit | `.venv/bin/python -m pytest tests/test_auth_mastodon.py -q` | ✅ | ⬜ pending |

*Seed map aligned to the committed plan set (06-01..06-07); the executor marks Status/File Exists as tasks land. Run all commands from `api/`. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_auth_merge.py` — new isolated unit-test file for `merge.py::resolve_auth` (AUTH-08/09, Plan 04)
- [ ] `api/tests/test_auth_config.py` — new test for the `OVID_ENV` import-time boot assertion / `ALLOW_LOCALHOST_BYPASS` (AUTH-10, Plan 03)
- [ ] `api/tests/conftest.py` — add `OVID_ENV` default so all test imports survive the new boot assertion (Plan 03)
- [ ] PendingAccountLink re-auth flow tests folded into `api/tests/test_auth_linking.py` (AUTH-06/07/08, Plan 05)
- [ ] Existing `conftest.py` SQLite/Postgres UUID shim covers the new `PendingAccountLink` table (Plan 01)

*Existing auth test infrastructure (`test_auth_*.py`, `conftest.py`) covers most phase requirements; `test_auth_merge.py` and `test_auth_config.py` are the net-new additions (plain `unittest.mock`, no respx — following `test_auth_linking.py`).*

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
