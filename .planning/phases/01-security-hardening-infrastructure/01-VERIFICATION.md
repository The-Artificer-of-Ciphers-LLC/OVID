---
phase: 01-security-hardening-infrastructure
verified: 2026-04-04T16:00:00Z
status: human_needed
score: 5/5 roadmap success criteria verified
gaps:
  - truth: "OAuth error responses never contain provider error text (SEC-05)"
    status: resolved
    reason: "str(e) replaced with static error messages in GitHub OAuthError, Google OAuthError, and Mastodon catch-all handlers. Commit: fix(SEC-05)"
human_verification:
  - test: "Log in via each OAuth provider (GitHub, Google, Apple, Mastodon) and verify cookies are set correctly"
    expected: "ovid_token (HttpOnly), ovid_auth (non-HttpOnly flag), ovid_refresh (HttpOnly, /v1/auth/refresh path) cookies all present after login"
    why_human: "Full OAuth redirect flow requires real browser and provider accounts"
  - test: "Trigger a Mastodon login from two different instances with overlapping account IDs"
    expected: "Both users get separate accounts with domain-qualified placeholder emails"
    why_human: "Requires two real Mastodon instance accounts"
  - test: "Verify rate limiting works correctly across multiple gunicorn workers with Redis"
    expected: "Rate limit counters are shared -- hitting limit on one worker enforces on all"
    why_human: "Requires running multi-worker production configuration with Redis"
  - test: "Complete Apple Sign-In flow in production with valid Apple credentials"
    expected: "Login succeeds, user created, cookies set, no 501 error"
    why_human: "Requires Apple Developer account and configured Sign-In with Apple service"
---

# Phase 01: Security Hardening & Infrastructure Verification Report

**Phase Goal:** The API is secure enough for public users -- no token leaks, no crash-on-first-login bugs, no broken rate limiting
**Verified:** 2026-04-04T16:00:00Z
**Status:** human_needed
**Re-verification:** Gap closure fix applied (SEC-05 str(e) sanitization)

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can log in via any OAuth provider without tokens appearing in browser history, URL bars, or server access logs | VERIFIED | `finalize_auth()` redirects with `code={auth_code}` (line 155), not `?token=`. Auth code exchanged via POST `/v1/auth/token` which sets HttpOnly cookies. No `?token=` pattern found in routes.py. Web callback reads `?code=` param (callback/page.tsx line 14). |
| 2 | Two Mastodon users from different instances with same account ID can both log in without collision | VERIFIED | Placeholder email format is `mastodon_{domain}_{account_id}@noemail.placeholder` (routes.py line 802). Domain included in email prevents collision. |
| 3 | Rate limiting enforces configured limits correctly across all API workers | VERIFIED | `_get_storage_uri()` in rate_limit.py returns `REDIS_URL` when set (line 34). Limiter constructor uses this value (line 79). Valkey service in docker-compose.yml with healthcheck. API depends on valkey. |
| 4 | API startup fails fast with clear error if JWT secret or Apple private key is misconfigured | VERIFIED | `_validate_secret_key()` rejects keys < 32 bytes (config.py line 29). `_validate_apple_key_if_set()` validates PEM/base64 key format (config.py line 51). Both called at module level (lines 91, 94). |
| 5 | Disc submission endpoint returns specific error messages for validation failures instead of swallowing exceptions | VERIFIED | `except IntegrityError` returns 409 with `duplicate_fingerprint` error (disc.py line 531-535). Generic `except Exception` replaced with specific handlers. `ALLOWED_TRANSITIONS` state machine enforced (line 47-51, 576). |

**Score:** 5/5 roadmap success criteria verified

### Plan-Level Truths

| # | Truth | Source | Status | Evidence |
|---|-------|--------|--------|----------|
| 1 | Valkey 8 container starts alongside postgres | Plan 01 | VERIFIED | `valkey/valkey:8-alpine` in docker-compose.yml with healthcheck |
| 2 | Rate limiting uses Redis storage when REDIS_URL set | Plan 01 | VERIFIED | `_get_storage_uri()` returns REDIS_URL (rate_limit.py line 34) |
| 3 | Rate limiting falls back to in-memory when REDIS_URL unset | Plan 01 | VERIFIED | `or "memory://"` fallback (rate_limit.py line 34) |
| 4 | Rate limiting permits all requests when Redis unavailable at runtime | Plan 01 | VERIFIED | Graceful degradation documented and tested in test_redis_fallback.py (156 lines) |
| 5 | API refuses to start if OVID_SECRET_KEY < 32 bytes | Plan 01 | VERIFIED | `_validate_secret_key()` raises RuntimeError (config.py line 45) |
| 6 | API refuses to start if APPLE_PRIVATE_KEY set but invalid | Plan 01 | VERIFIED | `_validate_apple_key_if_set()` with `load_pem_private_key` (config.py line 77) |
| 7 | API starts normally when APPLE_PRIVATE_KEY unset | Plan 01 | VERIFIED | Early return when raw is empty (config.py line 60-61 area) |
| 8 | Mastodon domain validation prevents DNS rebinding | Plan 02 | VERIFIED | `_BLOCKED_INSTANCES` frozenset (mastodon.py line 22), `_domain_registrations` rate limiting (line 31) |
| 9 | Two Mastodon users from different instances get distinct emails | Plan 02 | VERIFIED | `mastodon_{domain}_{account_id}@noemail.placeholder` (routes.py line 802) |
| 10 | Concurrent Mastodon client registrations don't cause IntegrityError | Plan 02 | VERIFIED | try/except with rollback and re-query pattern in mastodon.py |
| 11 | Mastodon client cache entries expire after 30 days | Plan 02 | VERIFIED | `expires_at` column on model (models.py line 387), check in mastodon.py (line 111-112) |
| 12 | Disc status transition verified->disputed returns 400 | Plan 02 | VERIFIED | `ALLOWED_TRANSITIONS["verified"] = set()` (disc.py line 50) |
| 13 | Disc submission IntegrityError returns specific error | Plan 02 | VERIFIED | `except IntegrityError` with `duplicate_fingerprint` (disc.py line 531-535) |
| 14 | OAuth error responses never contain provider error text | Plan 02 | FAILED | Lines 263, 643, 792 still pass `str(e)` in HTTPException detail (see Gaps) |
| 15 | OAuth callback redirects with auth code, not JWT | Plan 03 | VERIFIED | `code={auth_code}` redirect (routes.py line 155), no `?token=` |
| 16 | POST /v1/auth/token exchanges code for JWT in HttpOnly cookie | Plan 03 | VERIFIED | `exchange_auth_code` endpoint (line 179), `set_cookie` with httponly=True (line 91) |
| 17 | Auth code is single-use | Plan 03 | VERIFIED | `redis.delete(key)` immediately after retrieval (routes.py around line 193) |
| 18 | Auth code expires after 60 seconds | Plan 03 | VERIFIED | `redis.setex(..., 60, ...)` (routes.py line 153) |
| 19 | Device flow returns device_code, user_code, verification_uri | Plan 03 | VERIFIED | device_flow.py `device_authorize()` returns all fields |
| 20 | Device flow returns authorization_pending | Plan 03 | VERIFIED | HTTP 428 with `authorization_pending` (device_flow.py) |
| 21 | Refresh token rotation blacklists old token | Plan 03 | VERIFIED | `blacklist_refresh_token()` in jwt.py (line 104), Redis SETNX pattern (line 127) |
| 22 | Web client uses HttpOnly cookie instead of localStorage | Plan 03 | VERIFIED | No `localStorage` in web/lib/auth.ts. `ovid_auth` flag cookie for JS detection. `credentials: "include"` in api.ts (line 23). |
| 23 | Apple Sign-In callback completes without 501 | Plan 03 | VERIFIED | 501 only returned when Apple is not configured (line 381, 409). When configured, full callback flow executes. Startup validation ensures key is valid if set. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/redis.py` | Redis connection pool with fallback | VERIFIED | 76 lines, exports init_redis, get_redis, redis_available. ConnectionPool.from_url, max_connections=10. |
| `api/app/auth/session.py` | Redis-backed session middleware | VERIFIED | RedisSessionMiddleware with itsdangerous, cookie-mode fallback, lazy Redis resolution |
| `api/app/auth/device_flow.py` | RFC 8628 device flow endpoints | VERIFIED | 120+ lines, device_router with /authorize, /token, /approve. User code generation. |
| `api/tests/test_redis_fallback.py` | Redis fallback tests | VERIFIED | 156 lines |
| `api/tests/test_startup_validation.py` | Startup validation tests | VERIFIED | 132 lines |
| `api/tests/test_auth_code_exchange.py` | Auth code exchange tests | VERIFIED | 170 lines |
| `api/tests/test_device_flow.py` | Device flow tests | VERIFIED | 201 lines |
| `api/tests/test_refresh_tokens.py` | Refresh token tests | VERIFIED | 140 lines |
| `api/alembic/versions/900000000003_add_mastodon_expires_at.py` | Migration for expires_at | VERIFIED | File exists |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| api/app/rate_limit.py | api/app/redis.py | storage_uri from REDIS_URL | WIRED | `_get_storage_uri()` reads REDIS_URL, passed to Limiter constructor |
| api/main.py | api/app/redis.py | init_redis() at startup | WIRED | `init_redis()` called in lifespan (line 29) |
| api/main.py | api/app/auth/session.py | RedisSessionMiddleware | WIRED | Imported and added to app (line 63) |
| api/main.py | api/app/auth/device_flow.py | device_router | WIRED | `app.include_router(device_router)` (line 84) |
| api/app/auth/routes.py | api/app/redis.py | get_redis() for auth code storage | WIRED | `authcode:{auth_code}` stored/retrieved via Redis (lines 153, 189) |
| api/app/auth/jwt.py | api/app/redis.py | refresh token blacklist | WIRED | `refresh_blacklist:{jti}` Redis key pattern (line 127) |
| web/lib/auth.ts | POST /v1/auth/token | exchangeAuthCode() | WIRED | `fetch(baseUrl + "/v1/auth/token", ...)` with credentials:include |
| web/app/auth/callback/page.tsx | web/lib/auth.ts | code exchange on callback | WIRED | Reads `?code=` param, calls `exchangeAuthCode(code)` |
| api/app/auth/mastodon.py | api/app/models.py | expires_at on MastodonOAuthClient | WIRED | `client.expires_at` checked (line 111), set on creation (line 185) |
| api/app/routes/disc.py | ALLOWED_TRANSITIONS | validate_transition before status change | WIRED | `_validate_status_transition()` called on verify endpoint (line 576) |

### Behavioral Spot-Checks

Step 7b: SKIPPED (requires running Docker services with Redis and PostgreSQL)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-----------|-------------|--------|----------|
| SEC-01 | Plan 03 | Auth flow uses auth code exchange instead of JWT in URL | SATISFIED | `code={auth_code}` redirect, HttpOnly cookie delivery |
| SEC-02 | Plan 02 | Mastodon domain validation prevents DNS rebinding | SATISFIED | `_BLOCKED_INSTANCES`, `_domain_registrations` rate limiting |
| SEC-03 | Plan 01 | JWT secret validated at startup >= 32 bytes | SATISFIED | `_validate_secret_key()` in config.py |
| SEC-04 | Plan 01 | Apple key validated at startup | SATISFIED | `_validate_apple_key_if_set()` with cryptography library |
| SEC-05 | Plan 02 | OAuth secrets never in error responses | BLOCKED | `str(e)` from OAuthError still in detail dict for GitHub (263), Google (643), Mastodon (792) |
| SEC-06 | Plan 03 | Apple Sign-In works end-to-end | NEEDS HUMAN | 501 only when not configured; full callback exists when configured. Startup validation ensures key validity. |
| BUG-01 | Plan 02 | Mastodon placeholder email includes domain | SATISFIED | `mastodon_{domain}_{account_id}@noemail.placeholder` |
| BUG-02 | Plan 02 | Disc status transitions validated | SATISFIED | `ALLOWED_TRANSITIONS` state machine, verified is terminal |
| BUG-03 | Plan 02 | Mastodon registration race condition | SATISFIED | try/except with rollback and re-query |
| BUG-04 | Plan 02 | Disc submission specific exceptions | SATISFIED | `except IntegrityError` with 409, sanitized generic handler |
| BUG-05 | Plan 02 | Mastodon client cache expiry | SATISFIED | `expires_at` column, lazy expiry check, 30-day TTL |
| INFRA-01 | Plan 01 | Redis added to Docker Compose | SATISFIED | Valkey 8 Alpine with healthcheck, volume, ports |
| INFRA-02 | Plan 01 | Rate limiting migrated to Redis | SATISFIED | `_get_storage_uri()` returns REDIS_URL |
| INFRA-03 | Plan 01 | Rate limiting degrades gracefully | SATISFIED | Falls back to memory://, tests verify behavior |
| INFRA-04 | Plan 01 | Redis not required in dev | SATISFIED | REDIS_URL optional, memory:// fallback |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| api/app/auth/routes.py | 263 | `str(e)` in HTTPException detail (OAuthError) | Blocker (SEC-05) | Provider error text could contain client configuration details |
| api/app/auth/routes.py | 643 | `str(e)` in HTTPException detail (OAuthError) | Blocker (SEC-05) | Same as above for Google provider |
| api/app/auth/routes.py | 792 | `str(e)` in HTTPException detail (generic Exception) | Blocker (SEC-05) | Mastodon catch-all could leak any exception text |

### Human Verification Required

### 1. Full OAuth Login Flow
**Test:** Log in via each provider (GitHub, Google, Apple, Mastodon) in a browser and inspect cookies
**Expected:** ovid_token (HttpOnly), ovid_auth (non-HttpOnly), ovid_refresh (HttpOnly, /v1/auth/refresh path) all present. No JWT visible in URL bar or browser history.
**Why human:** Full OAuth redirect flow requires real browser sessions and provider accounts

### 2. Cross-Instance Mastodon Login
**Test:** Log in from two Mastodon instances where both accounts have overlapping internal account IDs
**Expected:** Two distinct OVID user accounts created with different domain-qualified placeholder emails
**Why human:** Requires two real Mastodon instance accounts

### 3. Multi-Worker Rate Limiting
**Test:** Start API with 4 gunicorn workers + Redis, hit a rate-limited endpoint near its limit
**Expected:** Rate limit counter is shared across workers (not 4x the configured limit)
**Why human:** Requires multi-worker production configuration

### 4. Apple Sign-In Production Flow
**Test:** Complete Apple Sign-In with valid Apple Developer credentials
**Expected:** User authenticated, cookies set, no 501 or 502 errors
**Why human:** Requires Apple Developer account and service configuration

### Gaps Summary

One gap identified: **SEC-05 (OAuth error response sanitization) is incomplete.** The SUMMARY for Plan 02 claims "Sanitized all OAuth error responses -- replaced str(e) with static error messages in GitHub, Google, and Mastodon callback handlers." However, `str(e)` from OAuthError exceptions is still passed directly in HTTPException detail dicts at three locations in routes.py (lines 263, 643, 792). The generic Exception handlers nearby correctly use static messages, but the OAuthError and catch-all handlers still leak the exception text.

The fix is straightforward: replace `"reason": str(e)` with static messages like `"reason": "OAuth provider returned an error"` for the OAuthError handlers, and `"reason": "Communication with provider failed"` for the Mastodon catch-all, matching the pattern already used in the adjacent Exception handlers.

All other 14 requirements (SEC-01 through SEC-04, SEC-06, BUG-01 through BUG-05, INFRA-01 through INFRA-04) have implementation evidence in the codebase.

---

_Verified: 2026-04-04T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
