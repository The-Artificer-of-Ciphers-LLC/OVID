---
phase: 1
slug: security-hardening-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already configured) |
| **Config file** | api/tests/conftest.py (in-memory SQLite, dependency overrides) |
| **Quick run command** | `cd api && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd api && python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd api && python -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd api && python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | SEC-01 | T-1-01 | Auth code exchange replaces JWT-in-URL | integration | `pytest tests/test_auth_code_exchange.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | SEC-02 | T-1-02 | Mastodon DNS rebinding prevention | unit | `pytest tests/test_auth_mastodon.py -x` | ✅ (extend) | ⬜ pending |
| 01-01-03 | 01 | 1 | SEC-03 | T-1-07 | JWT secret validation at startup | unit | `pytest tests/test_startup_validation.py -x` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | SEC-04 | — | Apple key validation at startup | unit | `pytest tests/test_startup_validation.py -x` | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 1 | SEC-05 | T-1-06 | No secrets in error responses | integration | `pytest tests/test_auth.py -x` | ✅ (extend) | ⬜ pending |
| 01-01-06 | 01 | 1 | SEC-06 | — | Apple Sign-In end-to-end | integration | `pytest tests/test_auth_apple.py -x` | ✅ (extend) | ⬜ pending |
| 01-02-01 | 02 | 1 | BUG-01 | — | Mastodon placeholder email format | unit | `pytest tests/test_auth_mastodon.py -x` | ✅ (extend) | ⬜ pending |
| 01-02-02 | 02 | 1 | BUG-02 | — | Disc status state machine | unit | `pytest tests/test_disc_verify.py -x` | ✅ (extend) | ⬜ pending |
| 01-02-03 | 02 | 1 | BUG-03 | T-1-05 | Mastodon registration race condition | unit | `pytest tests/test_auth_mastodon.py -x` | ✅ (extend) | ⬜ pending |
| 01-02-04 | 02 | 1 | BUG-04 | — | Disc submission specific exceptions | unit | `pytest tests/test_disc_submit.py -x` | ✅ (extend) | ⬜ pending |
| 01-02-05 | 02 | 1 | BUG-05 | — | Mastodon client cache expiry | unit | `pytest tests/test_auth_mastodon.py -x` | ✅ (extend) | ⬜ pending |
| 01-03-01 | 03 | 1 | INFRA-01 | — | Valkey in Docker Compose | smoke | `docker compose config --quiet` | N/A | ⬜ pending |
| 01-03-02 | 03 | 1 | INFRA-02 | T-1-04 | Rate limiting uses Redis storage | integration | `pytest tests/test_rate_limit.py -x` | ✅ (extend) | ⬜ pending |
| 01-03-03 | 03 | 1 | INFRA-03 | — | Graceful degradation on Redis failure | integration | `pytest tests/test_redis_fallback.py -x` | ❌ W0 | ⬜ pending |
| 01-03-04 | 03 | 1 | INFRA-04 | — | Redis optional in development | unit | `pytest tests/test_redis_fallback.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_auth_code_exchange.py` — stubs for SEC-01 auth code exchange flow
- [ ] `api/tests/test_startup_validation.py` — stubs for SEC-03, SEC-04 startup validation
- [ ] `api/tests/test_redis_fallback.py` — stubs for INFRA-03, INFRA-04 Redis fallback
- [ ] `api/tests/test_device_flow.py` — stubs for D-04 device authorization flow
- [ ] `api/tests/test_refresh_tokens.py` — stubs for D-07 refresh token rotation

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Valkey in Docker Compose | INFRA-01 | Requires Docker runtime | Run `docker compose config --quiet` and verify valkey service exists |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
