---
phase: 01-security-hardening-infrastructure
plan: 03
subsystem: auth
tags: [auth-code-exchange, httponly-cookies, refresh-tokens, device-flow, security]
dependency_graph:
  requires: [redis-connection-pool]
  provides: [auth-code-exchange, cookie-auth, refresh-token-rotation, device-authorization-flow]
  affects: [api/app/auth/routes.py, api/app/auth/jwt.py, api/app/auth/deps.py, web/lib/auth.ts, web/lib/api.ts]
tech_stack:
  added: []
  patterns: [auth-code-exchange, httponly-cookie-delivery, refresh-token-rotation, rfc8628-device-flow]
key_files:
  created:
    - api/app/auth/device_flow.py
    - api/tests/test_auth_code_exchange.py
    - api/tests/test_refresh_tokens.py
    - api/tests/test_device_flow.py
  modified:
    - api/app/auth/jwt.py
    - api/app/auth/routes.py
    - api/app/auth/deps.py
    - api/main.py
    - api/tests/test_auth.py
    - api/tests/test_auth_github.py
    - web/lib/auth.ts
    - web/lib/api.ts
    - web/app/auth/callback/page.tsx
    - web/components/SubmitForm.tsx
    - web/components/DisputeResolver.tsx
    - web/app/settings/page.tsx
    - web/src/__tests__/auth.test.ts
    - web/src/__tests__/submit.test.tsx
decisions:
  - "Auth codes stored in Redis with 60s TTL; graceful fallback redirects with code=redis_unavailable when Redis down"
  - "Access tokens 1-hour expiry (down from 30 days); refresh tokens 30-day with rotation"
  - "Cookie auth checked first in get_current_user, Bearer header as fallback for CLI/API compat"
  - "Device flow user_code uses 8-char alphanumeric alphabet excluding ambiguous chars (0/O/1/I)"
  - "Web API functions no longer accept token params; credentials: include handles cookie sending"
metrics:
  duration: 1053s
  completed: "2026-04-04T15:30:00Z"
  tasks: 2/2
  tests_added: 29
  tests_total: 294
  files_changed: 18
---

# Phase 01 Plan 03: Auth Code Exchange & Device Flow Summary

JWT-in-URL auth replaced with OAuth2 authorization code exchange stored in Redis, HttpOnly cookie token delivery with flag cookie for JS visibility, refresh token rotation with Redis-backed blacklist, RFC 8628 device authorization flow for CLI/ARM clients, and web client migrated from localStorage to cookie-based auth.

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Auth code exchange, cookie delivery, refresh tokens | 856d40c (RED), 19587e7 (GREEN) | jwt.py, routes.py, deps.py, test_auth_code_exchange.py, test_refresh_tokens.py |
| 2 | Device authorization flow and web client migration | 7a45786 (RED), a8c75e3 (GREEN) | device_flow.py, main.py, auth.ts, api.ts, callback/page.tsx, test_device_flow.py |

## What Was Built

### Auth Code Exchange (api/app/auth/routes.py)
- `finalize_auth()` generates a `secrets.token_urlsafe(32)` auth code stored in Redis with 60s TTL
- OAuth callbacks redirect with `?code=` instead of `?token=` (eliminates JWT-in-URL leakage)
- `POST /v1/auth/token` exchanges auth code for three cookies:
  - `ovid_token`: HttpOnly, access JWT (1h max_age)
  - `ovid_auth`: non-HttpOnly flag cookie ("1") for JS auth detection
  - `ovid_refresh`: HttpOnly, restricted to `/v1/auth/refresh` path (30d max_age)
- Auth code deleted from Redis on first use (single-use guarantee)
- Rate limited: 5/min on /token, 5/min on /refresh, 10/min on OAuth callbacks

### JWT Token Changes (api/app/auth/jwt.py)
- Access tokens: 1-hour expiry (was 30 days), `type: access`, `jti` UUID claim
- Refresh tokens: 30-day expiry, `type: refresh`, `jti` UUID claim
- `create_refresh_token()`, `decode_refresh_token()` with type validation
- `blacklist_refresh_token()`: Redis SETNX with 30-day TTL on `refresh_blacklist:{jti}`
- `is_refresh_token_blacklisted()`: Redis GET check, returns False if Redis unavailable (D-17)

### Token Refresh (api/app/auth/routes.py)
- `POST /v1/auth/refresh` reads `ovid_refresh` cookie, validates refresh token type
- Checks blacklist before issuing new tokens
- Blacklists old refresh token, issues new access + refresh pair
- Sets same three cookies as /token endpoint

### Cookie Auth (api/app/auth/deps.py)
- `get_current_user()` checks `ovid_token` cookie first
- Falls back to `Authorization: Bearer` header for CLI/API backward compatibility
- No longer uses Header dependency injection (uses Request object directly)

### Device Authorization Flow (api/app/auth/device_flow.py)
- `POST /v1/auth/device/authorize`: generates 32-byte device_code, 8-char user_code, stores in Redis with 15min TTL
- `POST /v1/auth/device/token`: polls for approval status (428 pending, 429 slow_down < 4.5s, 200 approved, 401 expired)
- `POST /v1/auth/device/approve`: authenticated user approves device by user_code, sets status=approved with user_id
- User code alphabet excludes ambiguous characters (0/O/1/I)
- All endpoints rate limited

### Web Client Migration
- `web/lib/auth.ts`: removed localStorage (getToken/setToken/clearToken), added `isAuthenticated()` cookie check, `exchangeAuthCode()` POST, `clearAuth()` cookie deletion
- `web/lib/api.ts`: all requests use `credentials: "include"`, removed token parameters from API functions
- `web/app/auth/callback/page.tsx`: reads `?code=` from URL, calls `exchangeAuthCode()`, shows error on failure
- Components updated to use `user` from `useAuth()` instead of `token`

## Test Coverage

- `test_auth_code_exchange.py`: 10 tests (redirect with code, exchange flow, single-use, cookie auth, Apple no-501)
- `test_refresh_tokens.py`: 10 tests (1h access expiry, type claims, jti, rotation, blacklist)
- `test_device_flow.py`: 9 tests (authorize, pending/approved/expired/slow_down, approve)
- `auth.test.ts`: 8 tests (cookie helpers, exchangeAuthCode, useAuth hook)
- Full API suite: 294 tests passing
- Full web suite: 34 tests passing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test expected 30-day access token expiry**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_auth.py::test_expiry_is_approximately_30_days` asserted 29-31 day range for access tokens
- **Fix:** Updated test to `test_expiry_is_approximately_1_hour` with correct assertion range
- **Files modified:** api/tests/test_auth.py
- **Commit:** 19587e7

**2. [Rule 1 - Bug] GitHub redirect test expected token= in URL**
- **Found during:** Task 1 GREEN phase
- **Issue:** `test_auth_github.py::test_login_stores_redirect_and_callback_returns_302` asserted `token=` in redirect location
- **Fix:** Updated to assert `code=` in location, mock Redis for auth code storage, assert `token=` NOT in location
- **Files modified:** api/tests/test_auth_github.py
- **Commit:** 19587e7

**3. [Rule 1 - Bug] Mastodon placeholder email missing domain**
- **Found during:** Task 1 GREEN phase
- **Issue:** When rewriting routes.py, placeholder email format regressed to `mastodon_{account_id}@noemail.placeholder` (missing domain from Wave 2 BUG-01 fix)
- **Fix:** Restored domain-qualified format: `mastodon_{domain}_{account_id}@noemail.placeholder`
- **Files modified:** api/app/auth/routes.py
- **Commit:** 19587e7

**4. [Rule 1 - Bug] Web components passed token to API functions**
- **Found during:** Task 2 GREEN phase
- **Issue:** SubmitForm, DisputeResolver, settings page passed `token` parameter to API functions that no longer accept it
- **Fix:** Updated all components to omit token params (cookies handle auth automatically) and use `user` instead of `token` from `useAuth()`
- **Files modified:** web/components/SubmitForm.tsx, web/components/DisputeResolver.tsx, web/app/settings/page.tsx
- **Commit:** a8c75e3

## Threat Model Verification

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-1-14 | JWT-in-URL eliminated; auth code exchange replaces ?token= | Implemented |
| T-1-15 | Auth code single-use: Redis DELETE on first exchange | Implemented |
| T-1-16 | Refresh token rotation with Redis SETNX blacklist | Implemented |
| T-1-17 | Device flow poll interval enforcement (429 if < 4.5s) | Implemented |
| T-1-18 | 32-byte device_code (256-bit entropy), 15min expiry, rate limited | Implemented |
| T-1-19 | Cookie Secure flag when HTTPS, SameSite=Lax | Implemented |
| T-1-20 | HttpOnly cookie replaces localStorage token | Implemented |
| T-1-21 | Rate limits: 5/min auth endpoints, 10/min callbacks | Implemented |

## Known Stubs

None -- all features fully wired.

## Self-Check: PASSED

All 4 created files verified present. All 4 commit hashes verified in git log.
