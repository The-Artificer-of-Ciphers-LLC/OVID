---
status: partial
phase: 01-security-hardening-infrastructure
source: [01-VERIFICATION.md]
started: 2026-04-04T16:30:00Z
updated: 2026-04-04T16:30:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. OAuth provider login with cookie verification
expected: ovid_token (HttpOnly), ovid_auth (non-HttpOnly flag), ovid_refresh (HttpOnly, /v1/auth/refresh path) cookies all present after login via each OAuth provider (GitHub, Google, Apple, Mastodon)
result: [pending]

### 2. Mastodon cross-instance account isolation
expected: Two users from different Mastodon instances with overlapping account IDs get separate accounts with domain-qualified placeholder emails
result: [pending]

### 3. Redis-backed rate limiting across workers
expected: Rate limit counters are shared across gunicorn workers — hitting limit on one worker enforces on all
result: [pending]

### 4. Apple Sign-In production flow
expected: Login succeeds, user created, cookies set, no 501 error
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
