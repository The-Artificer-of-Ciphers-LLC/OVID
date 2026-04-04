---
phase: 01-security-hardening-infrastructure
plan: 02
subsystem: api-auth-disc
tags: [security, mastodon, oauth, state-machine, error-handling]
dependency_graph:
  requires: []
  provides: [mastodon-hardened-auth, disc-state-machine, sanitized-errors]
  affects: [api-auth-routes, api-disc-routes, mastodon-oauth-model]
tech_stack:
  added: []
  patterns: [state-machine-validation, lazy-cache-expiry, error-sanitization]
key_files:
  created:
    - api/alembic/versions/900000000003_add_mastodon_expires_at.py
  modified:
    - api/app/auth/mastodon.py
    - api/app/auth/routes.py
    - api/app/models.py
    - api/app/routes/disc.py
    - api/tests/test_auth_mastodon.py
    - api/tests/test_disc_verify.py
    - api/tests/test_disc_submit.py
decisions:
  - "IndieAuth str(e) in error responses kept -- these are user-input validation messages, not provider secrets"
  - "Mastodon client expiry uses delete-and-reinsert rather than UPDATE for SQLite compatibility"
  - "pending_identification added to ALLOWED_TRANSITIONS to support ARM register flow"
metrics:
  duration: 636s
  completed: 2026-04-04T15:05:20Z
  tasks: 2/2
  files: 8
---

# Phase 01 Plan 02: Bug Fixes and Mastodon Hardening Summary

Mastodon OAuth hardened with DNS blocklist, domain-qualified emails, 30-day client cache TTL with lazy expiry, and race-condition-safe registration. Disc status transitions enforce state machine with verified as terminal. OAuth error responses sanitized to never leak provider error text.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Harden Mastodon OAuth | 1d6afc6 (test), 35552ef (impl) | mastodon.py, routes.py, models.py, migration |
| 2 | Disc status state machine and submission exception handling | 0bf9dff (test), 8fd1914 (impl) | disc.py, test_disc_verify.py, test_disc_submit.py |

## Changes Made

### Task 1: Mastodon OAuth Hardening

**Security (SEC-02, SEC-05):**
- Added `_BLOCKED_INSTANCES` frozenset blocking gab.com, truthsocial.com, spinster.xyz
- Added domain registration rate limiting (3 new domains/hour per IP)
- Sanitized all OAuth error responses -- replaced `str(e)` with static error messages in GitHub, Google, and Mastodon callback handlers
- Exception details logged server-side only via `logger.warning()`

**Bug Fixes (BUG-01, BUG-03, BUG-05):**
- BUG-01: Placeholder email now includes domain: `mastodon_{domain}_{account_id}@noemail.placeholder`
- BUG-03: Client registration wrapped in try/except for race condition safety (rollback and re-query on conflict)
- BUG-05: Added `expires_at` column to MastodonOAuthClient with 30-day TTL; NULL (legacy) treated as expired

**Migration:** `900000000003_add_mastodon_expires_at.py` adds nullable `expires_at` column

### Task 2: Disc Status State Machine and Exception Handling

**Bug Fixes (BUG-02, BUG-04):**
- BUG-02: Added `ALLOWED_TRANSITIONS` dict -- verified is terminal state, unverified/disputed can transition to verified
- BUG-02: `_validate_status_transition()` called before status change in verify endpoint
- BUG-04: Replaced bare `except Exception` with specific `except IntegrityError` returning 409 with `duplicate_fingerprint` error
- BUG-04: Generic exception handler returns sanitized "An unexpected error occurred" message

## Test Coverage

- `test_auth_mastodon.py`: 16 tests (blocked instances, email collision, cache expiry, upsert, error sanitization)
- `test_disc_verify.py`: 11 tests (state machine transitions, basic verify, self-verify rejection)
- `test_disc_submit.py`: 14 tests (submission, exception handling, auto-verify/dispute)
- Full suite: 243 tests passing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite timezone-naive datetime comparison**
- Found during: Task 1 GREEN phase
- Issue: SQLite returns naive datetimes from `DateTime(timezone=True)` columns, causing `TypeError` when compared with `datetime.now(timezone.utc)`
- Fix: Added `tzinfo` check in `expires_at` comparison -- naive datetimes treated as UTC
- Files modified: `api/app/auth/mastodon.py`

**2. [Rule 3 - Blocking] Formatter removing IntegrityError import**
- Found during: Task 2 GREEN phase
- Issue: Code formatter removed unused-looking `IntegrityError` import
- Fix: Added `# noqa: F401` to preserve import
- Files modified: `api/app/routes/disc.py`

## Known Stubs

None -- all features fully wired.

## Self-Check: PASSED
