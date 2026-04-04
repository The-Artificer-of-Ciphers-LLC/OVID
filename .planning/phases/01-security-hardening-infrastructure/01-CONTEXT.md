# Phase 1: Security Hardening & Infrastructure - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix all P0 security bugs, auth flow issues, and rate limiting before any public exposure. The API must be secure enough for public users — no token leaks, no crash-on-first-login bugs, no broken rate limiting. Covers SEC-01 through SEC-06, BUG-01 through BUG-05, and INFRA-01 through INFRA-04.

</domain>

<decisions>
## Implementation Decisions

### Auth Token Delivery (SEC-01)
- **D-01:** Replace JWT-in-URL redirect with OAuth2 authorization code exchange. Callback stores short-lived auth code in server-side session (Redis-backed), redirects to web. Web exchanges code for JWT via `POST /v1/auth/token`.
- **D-02:** Auth code is single-use with 60-second TTL. Deleted after first exchange to prevent replay attacks.
- **D-03:** Web client stores JWT in HttpOnly cookie (for SSR auth) + companion non-HttpOnly flag cookie (for client-side auth state detection). Replaces current localStorage-only approach.
- **D-04:** CLI/ARM clients authenticate via OAuth2 Device Authorization Flow (RFC 8628). CLI shows URL + code, user approves in browser, CLI polls for token.
- **D-05:** Keep current token lifetimes: 1-hour access token, 30-day refresh token.
- **D-06:** Separate session secret from JWT secret. New `SESSION_SECRET_KEY` env var for Starlette SessionMiddleware. JWT signing uses `OVID_SECRET_KEY`.

### Token Security
- **D-07:** Implement refresh token rotation with Redis-backed blacklist. When refresh token is used, old one is blacklisted. On compromise, revoke refresh token — access token expires in 1 hour max.
- **D-08:** Auth endpoint rate limits: 5 login attempts per IP per minute, 10 callback requests per IP per minute.
- **D-09:** CORS origins driven by `ALLOWED_ORIGINS` env var. Dev: `http://localhost:3000`. Prod: `https://oviddb.org`. Cookie domain set via `COOKIE_DOMAIN` env var.

### Mastodon Security (SEC-02, BUG-01, BUG-03, BUG-05)
- **D-10:** Harden domain validation: pin resolved IP to prevent DNS rebinding, add hardcoded instance blocklist (gab.com etc.), rate limit new domain registration (3/hour per IP).
- **D-11:** Mastodon OAuth client cache uses TTL + lazy cleanup. Add `expires_at` column (default 30 days). On lookup, if expired, re-register. No scheduler dependency.
- **D-12:** Fix placeholder email collision (BUG-01): format `mastodon_{domain}_{account_id}@noemail.placeholder`.
- **D-13:** Fix race condition (BUG-03): use PostgreSQL `INSERT ON CONFLICT` for Mastodon client registration.

### Redis / Valkey Infrastructure (INFRA-01 through INFRA-04)
- **D-14:** Use Valkey 8 Alpine (`valkey/valkey:8-alpine`) as Redis-compatible key-value store. Drop-in replacement — `redis-py` connects without changes.
- **D-15:** Required in production (`REDIS_URL` env var must be set). Optional in development — fall back to in-memory storage with startup warning when `REDIS_URL` is unset.
- **D-16:** Use `redis-py` built-in ConnectionPool with `max_connections=10`.
- **D-17:** On Redis/Valkey failure in production: permit all requests (rate limiting degrades to no-limit, token blacklist check skipped). Log warning. Matches INFRA-03 requirement.
- **D-18:** Redis serves three purposes: rate limiting storage, refresh token blacklist, and server-side session storage (replacing Starlette's cookie-based sessions).

### Startup Validation (SEC-03, SEC-04)
- **D-19:** Fail fast on all critical config. App refuses to start if JWT secret is weak (<32 bytes), Apple key is invalid, or DATABASE_URL is missing.
- **D-20:** Validate everything that's configured in `.env`. If `APPLE_PRIVATE_KEY` is set but malformed, fail with clear error. If unset, that's fine — provider just won't appear. Catches typos and misconfigurations early.

### Bug Fixes (scoped by requirements, no ambiguity)
- **D-21:** Disc status state machine (BUG-02): enforce allowed transitions (unverified→verified, unverified→disputed, disputed→verified, disputed→unverified). Reject invalid transitions with 400.
- **D-22:** Disc submission exception handling (BUG-04): catch specific exceptions (IntegrityError, ValidationError) instead of bare Exception. Log with full context, ensure rollback on all paths.
- **D-23:** OAuth client secrets (SEC-05): never include external service error text in API responses. Log to server logs only, return sanitized error to client.
- **D-24:** Apple Sign-In (SEC-06): validate private key at startup, test end-to-end in production. Current 501 response indicates key loading or token exchange failure.

### Claude's Discretion
- Exact implementation of DNS rebinding prevention (IP pinning vs dual-resolution check)
- Mastodon instance blocklist contents (initial set of known-problematic instances)
- Redis connection retry backoff strategy
- Alembic migration ordering for new columns
- Test fixture design for OAuth provider mocking

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Auth flow
- `api/app/auth/routes.py` — Current OAuth callback handlers, JWT-in-URL pattern (lines 109-115), Apple Sign-In (lines 216-234, 309-313)
- `api/app/auth/config.py` — JWT secret loading, no validation currently
- `api/app/auth/users.py` — User creation, placeholder email logic (lines 74-82)
- `api/app/auth/mastodon.py` — Domain validation (lines 15-40), dynamic registration (lines 43-97), race condition

### Rate limiting
- `api/app/rate_limit.py` — Current in-memory limiter, `_auth_aware_key()` function, `storage_uri="memory://"` (line 68)

### Disc routes
- `api/app/routes/disc.py` — Disc submission (lines 338-506), bare Exception catch (line 501), status transitions (lines 221-227)

### Models and schemas
- `api/app/models.py` — All ORM models including User, Disc, MastodonOAuthClient (line 375-386)
- `api/app/schemas.py` — Pydantic schemas for request/response validation

### Infrastructure
- `docker-compose.yml` — Base compose config (needs Valkey service added)
- `docker-compose.prod.yml` — Production overrides
- `.env.example` — Dev environment template (needs new env vars)
- `.env.production.example` — Production template

### Codebase analysis
- `.planning/codebase/CONCERNS.md` — Full bug/security/tech-debt analysis with line numbers

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/app/auth/routes.py`: OAuth flow infrastructure (GitHub, Google, Apple, Mastodon, IndieAuth) — all share `finalize_auth()` helper for user upsert
- `api/app/rate_limit.py`: slowapi limiter setup with `_dynamic_limit()` and `_auth_aware_key()` — needs Redis storage swap, structure stays
- `api/app/middleware.py`: MirrorModeMiddleware pattern — similar middleware pattern can be used for Redis health check
- Starlette `SessionMiddleware` already configured — needs secret key separation and Redis backend swap

### Established Patterns
- FastAPI dependency injection via `Depends()` — used throughout for auth, DB session
- HTTPException with structured `detail={"error": "code"}` — consistent error shape
- Alembic migrations for schema changes — new columns go through migration
- Docker Compose service pattern with health checks

### Integration Points
- `finalize_auth()` in `api/app/auth/routes.py` — all OAuth callbacks converge here; auth code exchange intercepts before this point
- `docker-compose.yml` — Valkey service added alongside existing postgres service
- `.env.example` / `.env.production.example` — new env vars (REDIS_URL, SESSION_SECRET_KEY, ALLOWED_ORIGINS, COOKIE_DOMAIN)
- `api/requirements.txt` — add `redis` package

</code_context>

<specifics>
## Specific Ideas

- Auth code exchange should store codes in Redis (not database) with automatic TTL expiry — no cleanup needed
- Device authorization flow for CLI should reuse the same JWT issuance path as web auth code exchange
- Valkey chosen over Redis for future-proofing against Redis license changes — identical wire protocol
- Session storage in Redis enables server-side session invalidation (e.g., "log out all devices")

</specifics>

<deferred>
## Deferred Ideas

- JWT token revocation beyond refresh rotation (full access token blacklist) — add if 1-hour TTL proves insufficient
- Rate limiting on non-auth API endpoints — already exists via slowapi, just needs Redis migration
- Audit trail for auth events (login, logout, provider linking) — future phase
- Circuit breaker for Mastodon instance health — nice-to-have, not P0

</deferred>

---

*Phase: 01-security-hardening-infrastructure*
*Context gathered: 2026-04-04*
