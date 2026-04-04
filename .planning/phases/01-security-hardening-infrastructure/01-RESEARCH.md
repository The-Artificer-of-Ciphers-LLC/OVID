# Phase 1: Security Hardening & Infrastructure - Research

**Researched:** 2026-04-04
**Domain:** OAuth security, Redis/Valkey infrastructure, FastAPI rate limiting, startup validation
**Confidence:** HIGH

## Summary

Phase 1 replaces the JWT-in-URL auth pattern with an authorization code exchange, adds Valkey 8 as a Redis-compatible key-value store for rate limiting / session / token blacklist, hardens Mastodon OAuth flows, adds startup validation for secrets, and fixes five tracked bugs. The existing codebase has a well-structured auth layer with all five OAuth providers already working -- the core work is replacing the token delivery mechanism (currently `finalize_auth()` appends `?token=JWT` to redirect URLs on line 114 of `auth/routes.py`) and wiring Redis into three subsystems.

The standard stack is `redis-py` 7.4 for Valkey connectivity (wire-compatible), `slowapi` with `storage_uri="redis://..."` for shared rate limiting, and a custom lightweight Redis-backed session implementation (the only maintained option `starlette-session` 0.4.3 is unmaintained since 2022). No exotic libraries needed -- the changes are primarily architectural rewiring of existing patterns.

**Primary recommendation:** Structure work in three waves: (1) Valkey infrastructure + Redis connectivity layer with graceful fallback, (2) auth flow rewrite (code exchange, cookies, device flow, refresh rotation), (3) bug fixes and startup validation. Each wave is independently testable.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Replace JWT-in-URL redirect with OAuth2 authorization code exchange. Callback stores short-lived auth code in server-side session (Redis-backed), redirects to web. Web exchanges code for JWT via `POST /v1/auth/token`.
- **D-02:** Auth code is single-use with 60-second TTL. Deleted after first exchange to prevent replay attacks.
- **D-03:** Web client stores JWT in HttpOnly cookie (for SSR auth) + companion non-HttpOnly flag cookie (for client-side auth state detection). Replaces current localStorage-only approach.
- **D-04:** CLI/ARM clients authenticate via OAuth2 Device Authorization Flow (RFC 8628). CLI shows URL + code, user approves in browser, CLI polls for token.
- **D-05:** Keep current token lifetimes: 1-hour access token, 30-day refresh token.
- **D-06:** Separate session secret from JWT secret. New `SESSION_SECRET_KEY` env var for Starlette SessionMiddleware. JWT signing uses `OVID_SECRET_KEY`.
- **D-07:** Implement refresh token rotation with Redis-backed blacklist. When refresh token is used, old one is blacklisted. On compromise, revoke refresh token -- access token expires in 1 hour max.
- **D-08:** Auth endpoint rate limits: 5 login attempts per IP per minute, 10 callback requests per IP per minute.
- **D-09:** CORS origins driven by `ALLOWED_ORIGINS` env var. Dev: `http://localhost:3000`. Prod: `https://oviddb.org`. Cookie domain set via `COOKIE_DOMAIN` env var.
- **D-10:** Harden domain validation: pin resolved IP to prevent DNS rebinding, add hardcoded instance blocklist (gab.com etc.), rate limit new domain registration (3/hour per IP).
- **D-11:** Mastodon OAuth client cache uses TTL + lazy cleanup. Add `expires_at` column (default 30 days). On lookup, if expired, re-register. No scheduler dependency.
- **D-12:** Fix placeholder email collision (BUG-01): format `mastodon_{domain}_{account_id}@noemail.placeholder`.
- **D-13:** Fix race condition (BUG-03): use PostgreSQL `INSERT ON CONFLICT` for Mastodon client registration.
- **D-14:** Use Valkey 8 Alpine (`valkey/valkey:8-alpine`) as Redis-compatible key-value store. Drop-in replacement -- `redis-py` connects without changes.
- **D-15:** Required in production (`REDIS_URL` env var must be set). Optional in development -- fall back to in-memory storage with startup warning when `REDIS_URL` is unset.
- **D-16:** Use `redis-py` built-in ConnectionPool with `max_connections=10`.
- **D-17:** On Redis/Valkey failure in production: permit all requests (rate limiting degrades to no-limit, token blacklist check skipped). Log warning. Matches INFRA-03 requirement.
- **D-18:** Redis serves three purposes: rate limiting storage, refresh token blacklist, and server-side session storage (replacing Starlette's cookie-based sessions).
- **D-19:** Fail fast on all critical config. App refuses to start if JWT secret is weak (<32 bytes), Apple key is invalid, or DATABASE_URL is missing.
- **D-20:** Validate everything that's configured in `.env`. If `APPLE_PRIVATE_KEY` is set but malformed, fail with clear error. If unset, that's fine -- provider just won't appear.
- **D-21:** Disc status state machine (BUG-02): enforce allowed transitions (unverified->verified, unverified->disputed, disputed->verified, disputed->unverified). Reject invalid transitions with 400.
- **D-22:** Disc submission exception handling (BUG-04): catch specific exceptions (IntegrityError, ValidationError) instead of bare Exception. Log with full context, ensure rollback on all paths.
- **D-23:** OAuth client secrets (SEC-05): never include external service error text in API responses. Log to server logs only, return sanitized error to client.
- **D-24:** Apple Sign-In (SEC-06): validate private key at startup, test end-to-end in production.

### Claude's Discretion
- Exact implementation of DNS rebinding prevention (IP pinning vs dual-resolution check)
- Mastodon instance blocklist contents (initial set of known-problematic instances)
- Redis connection retry backoff strategy
- Alembic migration ordering for new columns
- Test fixture design for OAuth provider mocking

### Deferred Ideas (OUT OF SCOPE)
- JWT token revocation beyond refresh rotation (full access token blacklist)
- Rate limiting on non-auth API endpoints (already exists via slowapi, just needs Redis migration)
- Audit trail for auth events (login, logout, provider linking)
- Circuit breaker for Mastodon instance health

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEC-01 | Auth flow uses authorization code exchange or HttpOnly cookie instead of JWT in URL query params | D-01 through D-09 cover the full replacement. `finalize_auth()` in routes.py line 114 is the exact injection point. |
| SEC-02 | Mastodon domain validation prevents DNS rebinding attacks (pin resolved IP) | D-10 covers this. Current `validate_mastodon_domain()` in mastodon.py resolves IP but doesn't pin it for subsequent connections. |
| SEC-03 | JWT secret key validated at startup (length >=32 bytes, entropy check) | D-19 covers this. Current `auth/config.py` only checks if OVID_SECRET_KEY is set, not its strength. |
| SEC-04 | Apple Sign-In private key validated at startup with clear error | D-20 and D-24 cover this. Current `_load_apple_private_key()` in routes.py returns None on failure -- no startup validation. |
| SEC-05 | OAuth client secrets never included in API error responses | D-23 covers this. Several exception handlers in routes.py pass `str(e)` through. |
| SEC-06 | Apple Sign-In works end-to-end in production | D-24 covers this. The 501 response is likely a key loading failure at runtime. |
| BUG-01 | Mastodon placeholder email includes instance domain | D-12 covers this. Line 695 in routes.py currently uses `mastodon_{account_id}@noemail.placeholder` -- missing domain. |
| BUG-02 | Disc status transitions validated against allowed state machine | D-21 covers this. Current verify/dispute endpoints don't validate source state. |
| BUG-03 | Mastodon dynamic registration uses ON CONFLICT to prevent race condition | D-13 covers this. Current mastodon.py line 93 does plain `db.add()` + `db.commit()`. |
| BUG-04 | Disc submission catches specific exceptions instead of bare Exception | D-22 covers this. Line 501 of disc.py has `except Exception:`. |
| BUG-05 | Mastodon OAuth client cache has expiry mechanism | D-11 covers this. Current MastodonOAuthClient model has no expires_at column. |
| INFRA-01 | Redis added to Docker Compose stack | D-14 covers this. Valkey 8 Alpine as drop-in replacement. |
| INFRA-02 | Rate limiting migrated from in-memory to Redis-backed storage | D-15/D-16 cover this. Current `storage_uri="memory://"` on line 68 of rate_limit.py. |
| INFRA-03 | Rate limiting degrades gracefully if Redis is unavailable | D-17 covers this. Needs custom error handling around slowapi storage calls. |
| INFRA-04 | Redis not required in development | D-15 covers this. Conditional `storage_uri` based on REDIS_URL presence. |

</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis (redis-py) | 7.4.0 | Valkey/Redis client for Python | Official Redis client, wire-compatible with Valkey 8; ConnectionPool built-in [VERIFIED: pypi.org/project/redis, released 2026-03-24] |
| slowapi | 0.1.9+ | Rate limiting with Redis backend | Already in use; `storage_uri="redis://..."` switches from memory to Redis [VERIFIED: slowapi docs, uses `limits` library under the hood] |
| valkey/valkey:8-alpine | 8.1.6 | Redis-compatible key-value store in Docker | Wire-compatible with redis-py, actively maintained, lighter Alpine image [VERIFIED: Docker Hub valkey/valkey tags] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| cryptography | (already installed) | Apple ES256 key validation at startup | Used by `_load_apple_private_key()` -- add startup validation call |
| PyJWT | 2.8+ (already installed) | JWT creation/verification, refresh tokens | Extend for refresh token pair (access + refresh) |
| itsdangerous | 2.1+ (already installed) | Secure token signing for auth codes | Auth code generation with TTL |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Redis session | starlette-session 0.4.3 | Unmaintained since 2022; custom implementation is ~50 lines and safer [VERIFIED: pypi.org/project/starlette-session] |
| Valkey | Redis 7 | Redis re-licensed (non-OSS); Valkey is the community fork, identical wire protocol [ASSUMED] |
| itsdangerous for auth codes | Redis-only TTL keys | itsdangerous adds cryptographic signing; Redis TTL handles expiry. Use Redis directly for auth codes -- simpler. |

**Installation:**
```bash
# Add to api/requirements.txt
redis>=5.0,<8.0
```

**Version verification:** redis-py 7.4.0 released 2026-03-24 [VERIFIED: pypi.org]. slowapi 0.1.9 already pinned in requirements.txt [VERIFIED: codebase]. Valkey 8.1.6-alpine available on Docker Hub [VERIFIED: hub.docker.com/r/valkey/valkey].

## Architecture Patterns

### Recommended Project Structure (new/modified files)
```
api/
 app/
   redis.py              # NEW: Redis connection pool, health check, graceful fallback
   auth/
     config.py           # MODIFIED: startup validation for all secrets
     routes.py           # MODIFIED: auth code exchange, cookie delivery, device flow
     jwt.py              # MODIFIED: refresh token support, token types
     mastodon.py         # MODIFIED: DNS rebinding fix, ON CONFLICT, TTL expiry
     session.py          # NEW: Redis-backed server-side session middleware
     device_flow.py      # NEW: RFC 8628 Device Authorization Grant endpoints
   rate_limit.py         # MODIFIED: Redis storage_uri, graceful fallback
   routes/
     disc.py             # MODIFIED: state machine validation, specific exception handling
   middleware.py         # EXISTING: no changes needed
 alembic/versions/
   xxx_add_mastodon_expires_at.py   # NEW: MastodonOAuthClient.expires_at column
 tests/
   test_auth_code_exchange.py       # NEW
   test_device_flow.py              # NEW
   test_refresh_tokens.py           # NEW
   test_redis_fallback.py           # NEW
   test_startup_validation.py       # NEW
docker-compose.yml                  # MODIFIED: add valkey service
.env.example                        # MODIFIED: new env vars
.env.production.example             # MODIFIED: new env vars
```

### Pattern 1: Redis Connection with Graceful Fallback

**What:** Centralized Redis client that degrades to no-op on connection failure.
**When to use:** Every Redis interaction (rate limiting, session, blacklist).

```python
# Source: project decision D-15, D-17
# api/app/redis.py
import logging
import os
from typing import Optional

from redis import ConnectionPool, Redis
from redis.exceptions import ConnectionError, TimeoutError

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None

def init_redis() -> Optional[Redis]:
    """Initialize Redis connection pool. Returns None if REDIS_URL unset."""
    global _pool, _client
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.warning("redis_not_configured REDIS_URL not set, using in-memory fallback")
        return None
    _pool = ConnectionPool.from_url(redis_url, max_connections=10)
    _client = Redis(connection_pool=_pool)
    # Verify connectivity
    try:
        _client.ping()
        logger.info("redis_connected url=%s", redis_url.split("@")[-1])  # log host only
    except (ConnectionError, TimeoutError) as e:
        logger.warning("redis_connect_failed detail=%s", str(e))
        _client = None
    return _client

def get_redis() -> Optional[Redis]:
    """Return the Redis client, or None if unavailable."""
    return _client
```

### Pattern 2: Auth Code Exchange Flow

**What:** Replace JWT-in-URL with server-side auth code stored in Redis.
**When to use:** All OAuth callback handlers.

```python
# Source: project decisions D-01, D-02
# Modified finalize_auth() pattern
import secrets

def finalize_auth(request, db, provider, provider_id, email, display_name):
    # ... user upsert (unchanged) ...
    user = user_upsert(db, ...)

    jwt_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    web_redirect_uri = request.session.pop("web_redirect_uri", "")
    if web_redirect_uri:
        # Generate single-use auth code, store in Redis with 60s TTL
        auth_code = secrets.token_urlsafe(32)
        redis = get_redis()
        if redis:
            redis.setex(f"authcode:{auth_code}", 60, f"{jwt_token}:{refresh_token}")
        # Redirect with code (NOT token) in URL
        redirect_url = f"{web_redirect_uri}?code={auth_code}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # API-only response (non-web clients)
    return {"token": jwt_token, "refresh_token": refresh_token}
```

### Pattern 3: Startup Validation

**What:** Validate all configured secrets at import time; fail fast with clear messages.
**When to use:** `auth/config.py` module load.

```python
# Source: project decisions D-19, D-20
def _validate_secret_key(key: str) -> str:
    if len(key) < 32:
        raise RuntimeError(
            f"OVID_SECRET_KEY is too short ({len(key)} bytes). "
            "Must be at least 32 bytes for HS256 signing security."
        )
    return key

def _validate_apple_key_if_set() -> None:
    raw = os.environ.get("APPLE_PRIVATE_KEY", "")
    if not raw:
        return  # Not configured -- fine
    # Try loading it
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    import base64
    if "BEGIN" not in raw:
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            raise RuntimeError(
                "APPLE_PRIVATE_KEY is set but is not valid base64 or PEM. "
                "Provide the ES256 private key as PEM text or base64-encoded PEM."
            )
    try:
        load_pem_private_key(raw.encode("utf-8"), password=None)
    except Exception as e:
        raise RuntimeError(
            f"APPLE_PRIVATE_KEY is set but cannot be loaded as an EC private key: {e}"
        )
```

### Pattern 4: Mastodon ON CONFLICT Registration

**What:** Use PostgreSQL upsert to prevent race conditions on concurrent registrations.
**When to use:** `get_or_register_client()` in mastodon.py.

```python
# Source: project decision D-13
from sqlalchemy.dialects.postgresql import insert as pg_insert

stmt = pg_insert(MastodonOAuthClient).values(
    domain=domain,
    client_id=client_id,
    client_secret=client_secret,
).on_conflict_do_nothing(index_elements=["domain"])
db.execute(stmt)
db.commit()
# Re-fetch to handle the race (another process may have won)
client = db.query(MastodonOAuthClient).filter_by(domain=domain).first()
```

**Note:** Tests use SQLite, and `on_conflict_do_nothing` with `index_elements` requires PostgreSQL dialect. The test conftest patches the DB to SQLite -- this upsert needs a dialect-aware wrapper or the test needs to mock this specific path.

### Anti-Patterns to Avoid
- **Passing exception text to client:** Lines like `"reason": str(e)` in several error handlers leak provider internals. Always return a static error message and log the detail server-side.
- **Bare except clauses:** `except Exception:` in disc submission (line 501) masks specific failures. Catch `IntegrityError`, `ValidationError` explicitly.
- **Session secret reuse:** Current `main.py` line 37 uses `SECRET_KEY` (the JWT secret) for SessionMiddleware. This must be separated per D-06.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rate limit storage | Custom Redis counter logic | slowapi `storage_uri="redis://..."` | slowapi delegates to `limits` library which handles sliding window, fixed window, and token bucket algorithms with atomic Redis operations |
| Redis connection pooling | Manual connection management | `redis.ConnectionPool.from_url()` | Handles reconnection, connection reuse, max connections, health checks |
| JWT signing/verification | Custom crypto | PyJWT with HS256 | Battle-tested, handles clock skew, expiry, issuer validation |
| PKCE for OAuth | Manual SHA256 + base64url | Already implemented in `indieauth.py` `generate_pkce_pair()` | Reuse existing implementation pattern |
| Docker health checks | Custom scripts | Built-in Docker `healthcheck` with `CMD` | Compose restart policies depend on health status |

**Key insight:** The auth code exchange pattern is simple enough to implement directly (Redis `SETEX` + `GET` + `DEL`). No library needed -- it's three Redis commands.

## Common Pitfalls

### Pitfall 1: SQLite vs PostgreSQL Dialect in Tests
**What goes wrong:** `INSERT ... ON CONFLICT DO NOTHING` with `index_elements` is PostgreSQL-specific. Tests using SQLite in conftest.py will fail.
**Why it happens:** The test suite uses in-memory SQLite for speed (conftest.py line 14).
**How to avoid:** Use `try/except IntegrityError` as a fallback path for SQLite, or mock the upsert function in tests. The simplest approach: wrap the upsert in a function that catches IntegrityError and re-queries.
**Warning signs:** Tests pass locally but fail to catch race conditions in production.

### Pitfall 2: Cookie Domain Configuration
**What goes wrong:** HttpOnly cookies set with wrong domain won't be sent by the browser. SameSite attribute conflicts with OAuth redirects.
**Why it happens:** OAuth callbacks come from external domains (github.com, appleid.apple.com), which triggers SameSite restrictions.
**How to avoid:** Set `SameSite=Lax` (not `Strict`) for auth cookies. The OAuth redirect back to your domain is a top-level navigation, which Lax permits. Set `COOKIE_DOMAIN` to the bare domain (e.g., `.oviddb.org`).
**Warning signs:** Login works in dev (same origin) but fails in production (cross-origin OAuth redirect).

### Pitfall 3: Rate Limiter Storage URI Format
**What goes wrong:** slowapi uses the `limits` library under the hood. The Redis URL format must be `redis://host:port/db` -- not the general `redis://user:pass@host:port/db` that redis-py accepts.
**Why it happens:** `limits` has its own storage URI parser.
**How to avoid:** Pass `REDIS_URL` to both redis-py (for direct use) and slowapi. Test with the actual URL format. The `limits` library does accept `redis://password@host:port/db` format.
**Warning signs:** Redis connects fine for sessions but slowapi silently falls back to memory.

### Pitfall 4: Refresh Token Rotation Blacklist Race
**What goes wrong:** If two requests hit the refresh endpoint simultaneously with the same refresh token, both could succeed before the blacklist check completes.
**Why it happens:** Redis `GET` + `SET` is not atomic by default.
**How to avoid:** Use a Redis transaction (pipeline with `WATCH`) or Lua script for atomic check-and-blacklist. Alternatively, use `SETNX` on the blacklist key -- first writer wins, second gets rejected.
**Warning signs:** Intermittent "token already used" errors under load.

### Pitfall 5: Device Flow Polling Abuse
**What goes wrong:** CLI polls `/v1/auth/device/token` too frequently, generating excessive load.
**Why it happens:** RFC 8628 specifies a `slow_down` response but clients may ignore it.
**How to avoid:** Enforce server-side: track last poll time per device_code in Redis. Return 429 if polled faster than `interval` (default 5 seconds). Include `interval` in the device code response.
**Warning signs:** High request volume to the device token endpoint.

### Pitfall 6: Starlette SessionMiddleware Secret Separation
**What goes wrong:** Changing the session secret invalidates all existing sessions, logging everyone out.
**Why it happens:** Current code (main.py line 37) uses `SECRET_KEY` for sessions. D-06 introduces `SESSION_SECRET_KEY`.
**How to avoid:** Deploy the new `SESSION_SECRET_KEY` support first, defaulting to `SECRET_KEY` if unset. Then in a follow-up deploy, set the new env var. All sessions will be new anyway after the auth flow change, so a clean cut is acceptable here.
**Warning signs:** 500 errors from session deserialization after deploy.

## Code Examples

### Redis-Backed Rate Limiting (slowapi)

```python
# Source: slowapi docs (https://slowapi.readthedocs.io/en/latest/examples/)
import os
from slowapi import Limiter

redis_url = os.environ.get("REDIS_URL")
storage = redis_url if redis_url else "memory://"

limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri=storage,
)
```

### Auth Code Token Exchange Endpoint

```python
# Source: project decision D-01, D-02
# New endpoint: POST /v1/auth/token
@auth_router.post("/token")
async def exchange_auth_code(code: str = Body(...), request: Request = None):
    """Exchange a single-use auth code for JWT tokens."""
    redis = get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

    key = f"authcode:{code}"
    value = redis.get(key)
    if not value:
        raise HTTPException(status_code=401, detail={"error": "invalid_code"})

    # Delete immediately (single-use)
    redis.delete(key)

    jwt_token, refresh_token = value.decode().split(":", 1)

    response = JSONResponse(content={"user": "..."})
    response.set_cookie(
        key="ovid_token",
        value=jwt_token,
        httponly=True,
        secure=True,  # HTTPS only in production
        samesite="lax",
        max_age=3600,  # 1 hour
        domain=os.environ.get("COOKIE_DOMAIN"),
    )
    response.set_cookie(
        key="ovid_auth",  # Flag cookie (non-HttpOnly, no token value)
        value="1",
        httponly=False,
        secure=True,
        samesite="lax",
        max_age=3600,
    )
    return response
```

### Device Authorization Flow (RFC 8628)

```python
# Source: RFC 8628 (https://datatracker.ietf.org/doc/html/rfc8628)
# New endpoint: POST /v1/auth/device/authorize
@auth_router.post("/device/authorize")
async def device_authorize():
    """Issue device code + user code for CLI/ARM authentication."""
    device_code = secrets.token_urlsafe(32)
    user_code = _generate_user_code()  # 8-char alphanumeric, easy to type

    redis = get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

    # Store pending device code (expires in 15 minutes)
    redis.setex(f"device:{device_code}", 900, json.dumps({
        "user_code": user_code,
        "status": "pending",  # pending | approved | denied
    }))
    # Reverse lookup: user_code -> device_code
    redis.setex(f"usercode:{user_code}", 900, device_code)

    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": f"{os.environ.get('OVID_WEB_URL', 'http://localhost:3000')}/device",
        "expires_in": 900,
        "interval": 5,
    }
```

### Disc Status State Machine

```python
# Source: project decision D-21
ALLOWED_TRANSITIONS = {
    "unverified": {"verified", "disputed"},
    "disputed": {"verified", "unverified"},
    "verified": set(),  # terminal state (for now)
}

def validate_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JWT in URL query params | Auth code exchange + HttpOnly cookie | Industry standard since ~2020 | Prevents token leakage in browser history, server logs, Referer headers |
| In-memory rate limiting | Redis-backed shared storage | Standard for multi-worker deployments | Rate limits enforced correctly across all gunicorn workers |
| Redis (BSD) | Valkey (BSD) | 2024 (Redis re-licensed to SSPL) | Community fork, identical protocol, OVID is AGPL so OSS alignment matters |
| Cookie-based sessions (Starlette default) | Server-side sessions (Redis) | Security best practice | Server can invalidate sessions; session data not exposed to client |

**Deprecated/outdated:**
- `starlette-session` 0.4.3: Last release 2022. Do not adopt -- implement the ~50 lines of Redis session middleware directly. [VERIFIED: pypi.org]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Valkey 8 is wire-compatible with redis-py 7.4 with zero code changes | Standard Stack | LOW -- Valkey is an exact fork of Redis 7.2; redis-py has been tested with Valkey by multiple projects |
| A2 | slowapi's `limits` library accepts the same Redis URL format as redis-py | Pitfalls | MEDIUM -- if formats differ, rate limiting silently falls back to memory. Must verify during implementation. |
| A3 | SameSite=Lax cookies are sent on OAuth redirect back to the app | Pitfalls | LOW -- Lax explicitly permits top-level navigations, which is what OAuth redirects are |
| A4 | The existing `conftest.py` SQLite setup will need dialect-aware handling for ON CONFLICT | Pitfalls | HIGH -- confirmed by codebase inspection; SQLite supports ON CONFLICT but with different syntax than PostgreSQL |

## Open Questions

1. **Redis session implementation scope**
   - What we know: Starlette's built-in SessionMiddleware stores data in signed cookies (client-side). D-18 requires Redis-backed sessions.
   - What's unclear: Whether to subclass Starlette's SessionMiddleware or write a standalone ASGI middleware.
   - Recommendation: Write a standalone ~50-line middleware that stores session dict in Redis keyed by a signed cookie value. Starlette's SessionMiddleware interface is simple enough to replicate.

2. **Device flow web UI page**
   - What we know: RFC 8628 requires a `verification_uri` where users enter the code.
   - What's unclear: Whether the web UI page (`/device`) is in scope for Phase 1 or Phase 6 (Web UI Completeness).
   - Recommendation: Build a minimal `/device` page in Phase 1 (just a form that accepts the code). Polish it in Phase 6.

3. **Token lifetime change**
   - What we know: D-05 says "1-hour access token, 30-day refresh token" but current `auth/config.py` has `JWT_EXPIRY_DAYS = 30` (a single long-lived token, no refresh).
   - What's unclear: This is a breaking change for existing tokens -- all current 30-day tokens become invalid when access token lifetime drops to 1 hour.
   - Recommendation: Accept the breaking change. Phase 1 is pre-public-launch, so no external users are affected.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Valkey container | Assumed on holodeck | -- | -- |
| Docker Compose v2 | Service orchestration | Assumed on holodeck | -- | -- |
| PostgreSQL 16 | Database (existing) | Yes (via Docker) | 16-alpine | -- |
| Valkey 8 | Rate limiting, sessions, blacklist | Not yet added | Will be 8-alpine | In-memory fallback (D-15) |
| Python 3.12 | API runtime | Yes (via Docker) | 3.12-slim | -- |
| redis-py | Valkey client | Not yet installed | Will be 7.4.0 | -- |

**Missing dependencies with no fallback:**
- None. All new dependencies have development fallbacks per D-15.

**Missing dependencies with fallback:**
- Valkey: Falls back to in-memory storage in development (D-15).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already configured) |
| Config file | api/tests/conftest.py (in-memory SQLite, dependency overrides) |
| Quick run command | `cd api && python -m pytest tests/ -x -q` |
| Full suite command | `cd api && python -m pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEC-01 | Auth code exchange replaces JWT-in-URL | integration | `pytest tests/test_auth_code_exchange.py -x` | Wave 0 |
| SEC-02 | Mastodon DNS rebinding prevention | unit | `pytest tests/test_auth_mastodon.py -x` | Exists (extend) |
| SEC-03 | JWT secret validation at startup | unit | `pytest tests/test_startup_validation.py -x` | Wave 0 |
| SEC-04 | Apple key validation at startup | unit | `pytest tests/test_startup_validation.py -x` | Wave 0 |
| SEC-05 | No secrets in error responses | integration | `pytest tests/test_auth.py -x` | Exists (extend) |
| SEC-06 | Apple Sign-In end-to-end | integration | `pytest tests/test_auth_apple.py -x` | Exists (extend) |
| BUG-01 | Mastodon placeholder email format | unit | `pytest tests/test_auth_mastodon.py -x` | Exists (extend) |
| BUG-02 | Disc status state machine | unit | `pytest tests/test_disc_verify.py -x` | Exists (extend) |
| BUG-03 | Mastodon registration race condition | unit | `pytest tests/test_auth_mastodon.py -x` | Exists (extend) |
| BUG-04 | Disc submission specific exceptions | unit | `pytest tests/test_disc_submit.py -x` | Exists (extend) |
| BUG-05 | Mastodon client cache expiry | unit | `pytest tests/test_auth_mastodon.py -x` | Exists (extend) |
| INFRA-01 | Valkey in Docker Compose | smoke | `docker compose config --quiet` | manual-only |
| INFRA-02 | Rate limiting uses Redis storage | integration | `pytest tests/test_rate_limit.py -x` | Exists (extend) |
| INFRA-03 | Graceful degradation on Redis failure | integration | `pytest tests/test_redis_fallback.py -x` | Wave 0 |
| INFRA-04 | Redis optional in development | unit | `pytest tests/test_redis_fallback.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd api && python -m pytest tests/ -x -q`
- **Per wave merge:** `cd api && python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `api/tests/test_auth_code_exchange.py` -- covers SEC-01 auth code exchange flow
- [ ] `api/tests/test_startup_validation.py` -- covers SEC-03, SEC-04 startup validation
- [ ] `api/tests/test_redis_fallback.py` -- covers INFRA-03, INFRA-04 Redis fallback
- [ ] `api/tests/test_device_flow.py` -- covers D-04 device authorization flow
- [ ] `api/tests/test_refresh_tokens.py` -- covers D-07 refresh token rotation

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | OAuth2 authorization code exchange, HttpOnly cookies, Device Authorization Grant (RFC 8628) |
| V3 Session Management | yes | Server-side Redis sessions, session secret separation, cookie SameSite=Lax |
| V4 Access Control | yes | Rate limiting per-IP and per-user, auth endpoint throttling (D-08) |
| V5 Input Validation | yes | Mastodon domain validation (DNS rebinding), startup secret validation, disc status state machine |
| V6 Cryptography | yes | HS256 JWT signing (>=32 byte key), ES256 Apple Sign-In, AES-256-GCM OAuth token encryption |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JWT in URL leakage (browser history, logs, Referer) | Information Disclosure | Auth code exchange + HttpOnly cookie (SEC-01) |
| DNS rebinding on Mastodon domain validation | Spoofing | Pin resolved IP, validate before each request (SEC-02) |
| Refresh token theft | Elevation of Privilege | Rotation with blacklist, 1-hour access TTL (D-07) |
| Rate limit bypass via multiple workers | Denial of Service | Shared Redis storage for rate counters (INFRA-02) |
| Mastodon registration race condition | Tampering | PostgreSQL ON CONFLICT upsert (BUG-03) |
| Provider error text in responses | Information Disclosure | Sanitized errors, server-side logging only (SEC-05) |
| Weak JWT secret | Tampering | Startup validation, minimum 32 bytes (SEC-03) |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `api/app/auth/routes.py`, `api/app/rate_limit.py`, `api/app/auth/mastodon.py`, `api/app/auth/config.py`, `api/app/auth/jwt.py`, `api/main.py`, `api/tests/conftest.py`
- [pypi.org/project/redis](https://pypi.org/project/redis/) - redis-py 7.4.0, released 2026-03-24
- [hub.docker.com/r/valkey/valkey](https://hub.docker.com/r/valkey/valkey/) - Valkey 8.1.6-alpine confirmed available
- [slowapi.readthedocs.io/en/latest/examples](https://slowapi.readthedocs.io/en/latest/examples/) - Redis storage_uri format confirmed
- [RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628) - OAuth 2.0 Device Authorization Grant

### Secondary (MEDIUM confidence)
- [pypi.org/project/starlette-session](https://pypi.org/project/starlette-session/) - Confirmed unmaintained (last release 2022-10-29)
- [starlette.dev/middleware](https://starlette.dev/middleware/) - SessionMiddleware configuration reference

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries verified against PyPI/Docker Hub with current versions
- Architecture: HIGH - patterns derived from locked decisions in CONTEXT.md and verified against existing codebase
- Pitfalls: HIGH - identified from codebase inspection (SQLite test dialect, cookie SameSite behavior, rate limiter storage format)

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable domain, 30-day validity)
