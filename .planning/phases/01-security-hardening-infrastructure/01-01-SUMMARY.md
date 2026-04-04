---
phase: 01-security-hardening-infrastructure
plan: 01
subsystem: infrastructure
tags: [redis, valkey, rate-limiting, sessions, startup-validation]
dependency_graph:
  requires: []
  provides: [redis-connection-pool, redis-session-middleware, startup-validation]
  affects: [api/main.py, api/app/rate_limit.py, docker-compose.yml]
tech_stack:
  added: [valkey/valkey:8-alpine, redis-py, cryptography]
  patterns: [graceful-fallback, cookie-mode-session-fallback, fail-fast-validation]
key_files:
  created:
    - api/app/redis.py
    - api/app/auth/session.py
    - .env.production.example
    - api/tests/test_redis_fallback.py
    - api/tests/test_startup_validation.py
  modified:
    - docker-compose.yml
    - docker-compose.prod.yml
    - api/requirements.txt
    - .env.example
    - .gitignore
    - api/app/rate_limit.py
    - api/main.py
    - api/app/auth/config.py
decisions:
  - "RedisSessionMiddleware uses cookie-mode fallback (signed session data in cookie) when Redis unavailable, preserving backward compatibility with existing OAuth flow tests"
  - "Session middleware accepts redis_getter callable for lazy resolution after lifespan init"
  - "ALLOWED_ORIGINS preferred over CORS_ORIGINS with fallback for backward compatibility"
metrics:
  duration: 9m
  completed: "2026-04-04T15:04:00Z"
  tasks: 3/3
  tests_added: 22
  tests_total: 250
  files_changed: 13
---

# Phase 01 Plan 01: Redis Infrastructure & Startup Validation Summary

Valkey 8 added to Docker Compose with redis-py connection pool, graceful fallback to in-memory when unavailable, Redis-backed session middleware with cookie-mode fallback, and fail-fast startup validation for JWT secret strength and Apple private key format.

## Task Results

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add Valkey to Docker Compose and install redis-py | 15738e5 | docker-compose.yml, docker-compose.prod.yml, api/requirements.txt, .env.example, .env.production.example |
| 2 | Create Redis connection module, migrate rate limiter, add session middleware | f16ed11 (RED), b616135 (GREEN) | api/app/redis.py, api/app/rate_limit.py, api/app/auth/session.py, api/main.py, api/tests/test_redis_fallback.py |
| 3 | Startup validation for JWT secret and Apple private key | 829cb31 (RED), b7c03f9 (GREEN) | api/app/auth/config.py, api/tests/test_startup_validation.py |

## What Was Built

### Redis Connection Module (api/app/redis.py)
- `init_redis()` reads REDIS_URL, creates ConnectionPool with max_connections=10, pings to verify
- Returns None when REDIS_URL unset (logs `redis_not_configured` warning)
- Returns None on connection failure (logs `redis_connect_failed` error)
- Logs only host portion of URL to avoid leaking passwords (T-1-02)
- `get_redis()` and `redis_available()` expose connection state

### Rate Limiter Migration (api/app/rate_limit.py)
- `_get_storage_uri()` returns REDIS_URL or `"memory://"` fallback
- Limiter constructor now uses `_get_storage_uri()` instead of hardcoded `"memory://"`
- Shared counters across gunicorn workers when Redis available

### Session Middleware (api/app/auth/session.py)
- `RedisSessionMiddleware` stores session data in Redis with signed cookie references
- Cookie flags: HttpOnly=True, SameSite=Lax, Secure configurable via COOKIE_SECURE env
- Cookie domain configurable via COOKIE_DOMAIN env
- Lazy Redis resolution via `redis_getter` callable (resolved after lifespan init)
- Cookie-mode fallback: when Redis unavailable, session data embedded in signed cookie (like Starlette SessionMiddleware)
- Separate SESSION_SECRET_KEY env var (falls back to OVID_SECRET_KEY as migration path, per D-06)

### Startup Validation (api/app/auth/config.py)
- `_validate_secret_key()`: rejects OVID_SECRET_KEY shorter than 32 bytes with actionable error message
- `_validate_apple_key_if_set()`: validates APPLE_PRIVATE_KEY as PEM or base64-encoded PEM using cryptography library
- Both run at module import time (fail-fast before any request handling)

### Docker Compose
- Valkey 8 Alpine service with healthcheck (valkey-cli ping), persistent volume, port 6379
- API service depends on valkey with service_healthy condition
- Production overrides: 256mb maxmemory with allkeys-lru eviction policy
- New env vars: REDIS_URL, SESSION_SECRET_KEY, ALLOWED_ORIGINS, COOKIE_DOMAIN

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Session middleware cookie-mode fallback**
- **Found during:** Task 2
- **Issue:** RedisSessionMiddleware with no Redis returned empty sessions on load, breaking OAuth state flow (GitHub login test failed because web_redirect_uri was lost between requests)
- **Fix:** Added cookie-mode fallback that embeds session data in the signed cookie when Redis is unavailable, preserving the same behavior as Starlette's built-in SessionMiddleware
- **Files modified:** api/app/auth/session.py
- **Commit:** b616135

**2. [Rule 3 - Blocking] Lazy Redis resolution for middleware**
- **Found during:** Task 2
- **Issue:** `get_redis()` returns None at middleware registration time (before lifespan runs init_redis()), so redis_client was always None
- **Fix:** Added `redis_getter` parameter to RedisSessionMiddleware and `_active_redis` property for lazy resolution
- **Files modified:** api/app/auth/session.py, api/main.py
- **Commit:** b616135

**3. [Rule 3 - Blocking] .gitignore excluded .env.production.example**
- **Found during:** Task 1
- **Issue:** `.env.*` pattern in .gitignore excluded the new .env.production.example file
- **Fix:** Added `!.env.production.example` exception to .gitignore
- **Files modified:** .gitignore
- **Commit:** 15738e5

**4. [Rule 2 - Missing functionality] Added cryptography dependency**
- **Found during:** Task 1
- **Issue:** Apple key validation requires `cryptography` library for `load_pem_private_key`, not in requirements.txt
- **Fix:** Added `cryptography>=42.0,<45.0` to api/requirements.txt
- **Files modified:** api/requirements.txt
- **Commit:** 15738e5

## Threat Model Verification

All mitigations from the plan's threat model were implemented:

| Threat ID | Mitigation | Status |
|-----------|-----------|--------|
| T-1-01 | Redis unavailable: graceful fallback to memory/cookie | Implemented |
| T-1-02 | Redis URL password masking in logs | Implemented (split on @) |
| T-1-03 | Weak JWT secret rejection at startup | Implemented (32-byte minimum) |
| T-1-04 | Apple key validation with safe error messages | Implemented |
| T-1-05 | Session cookie HttpOnly + SameSite=Lax | Implemented |
| T-1-06 | Separate SESSION_SECRET_KEY | Implemented (with OVID_SECRET_KEY fallback) |

## Self-Check: PASSED

All 5 created files verified present. All 5 commit hashes verified in git log.
