# External Integrations

**Analysis Date:** 2026-04-04

## APIs & External Services

**OAuth 2.0 Identity Providers:**
- GitHub OAuth
  - SDK/Client: authlib 1.3+
  - Config: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`
  - Implementation: `api/app/auth/routes.py` (lines 47-56, 130-193)
  - Callback: `GET /v1/auth/github/callback`
  - Scope: `user:email read:user`

- Google OAuth (OpenID Connect)
  - SDK/Client: authlib 1.3+ with OIDC discovery
  - Config: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
  - Implementation: `api/app/auth/routes.py` (lines 58-65, 509-563)
  - Callback: `GET /v1/auth/google/callback`
  - Discovery: `https://accounts.google.com/.well-known/openid-configuration`

- Apple Sign-In
  - SDK/Client: PyJWT 2.8+ for ES256 signing, httpx for token exchange
  - Config: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (all required)
  - Implementation: `api/app/auth/routes.py` (lines 216-381)
  - Token URL: `https://appleid.apple.com/auth/token`
  - Auth URL: `https://appleid.apple.com/auth/authorize`
  - JWKS validation: `https://appleid.apple.com/auth/keys`

- IndieAuth (Decentralized)
  - SDK/Client: httpx for endpoint discovery and token exchange
  - Config: None (uses discovered endpoints)
  - Implementation: `api/app/auth/indieauth.py`, `api/app/auth/routes.py` (lines 388-504)
  - PKCE support: Yes (S256 code challenge)
  - Discovery timeout: 10 seconds

- Mastodon OAuth (Fediverse)
  - SDK/Client: httpx for dynamic client registration and token exchange
  - Config: No static credentials (per-instance dynamic registration)
  - Implementation: `api/app/auth/mastodon.py`, `api/app/auth/routes.py` (lines 572-704)
  - Uses: User-provided Mastodon instance domain
  - Endpoints: `/oauth/authorize`, `/oauth/token`, `/api/v1/accounts/verify_credentials`
  - Validation: DNS lookups to prevent spoofing

**Metadata & Content APIs:**
- TMDB (The Movie Database)
  - SDK/Client: tmdbv3api 1.9+
  - Purpose: Movie/TV metadata lookups for disc releases
  - Implementation: `ovid-client/src/` (used in CLI tools)
  - Used by: ARM ripping integration for metadata enrichment

## Data Storage

**Databases:**
- PostgreSQL 16
  - Connection: `DATABASE_URL` env var (format: `postgresql://user:pass@host:port/db`)
  - Client: SQLAlchemy 2.0+ async session factory
  - ORM: Declarative base at `api/app/database.py`
  - Connection pool: pre-ping enabled (`pool_pre_ping=True`)

**Migrations:**
- Alembic 1.13+
  - Location: `api/alembic/versions/`
  - Config: `api/alembic.ini` (sqlalchemy.url from env at runtime)
  - Current migrations:
    - `7ffb31fc807f_initial_schema.py` - Core schema (User, Disc, Release, etc.)
    - `800000000000_mastodon_oauth_clients.py` - Mastodon client registration table
    - `900000000001_add_sync_seq_numbers.py` - Global sequence tracking for mirrors
    - `900000000002_add_sync_state.py` - Sync state management

**File Storage:**
- Not used. All data is in PostgreSQL.
- Disc fingerprints computed locally (ISO parsing, no external file storage).

**Caching:**
- Not explicitly used. Session middleware uses Starlette's in-memory session store.
- No Redis or memcached integration.

## Authentication & Identity

**Auth Strategy:**
- OAuth 2.0 delegation (GitHub, Google, Apple, Mastodon, IndieAuth)
- Custom user upsert logic: `api/app/auth/users.py`
- JWT token generation and validation: `api/app/auth/jwt.py`

**Implementation Details:**
- Session storage: Starlette `SessionMiddleware` (encrypted via `SECRET_KEY`)
- JWT signing: HS256 algorithm, configurable expiry (default 30 days via `OVID_JWT_EXPIRY_DAYS`)
- Token verification: `api/app/auth/deps.py` → `get_current_user()` dependency
- Account linking: Multiple OAuth providers to a single user account
  - Implicit linking: Same email across providers
  - Explicit linking: Authenticated user linking additional providers
  - Conflict resolution: Email conflicts return 409 with pending_link flow

## Monitoring & Observability

**Error Tracking:**
- None. Errors logged to stderr via `logging` module.
- Log level: `LOG_LEVEL` env var (default: info)

**Logs:**
- Python logging to stderr
- Request ID injection via `RequestIdMiddleware` for tracing
- Structured logs in auth routes (provider-specific details for debugging)
- ARM integration logs to stderr: `arm.identify_ovid` module

## CI/CD & Deployment

**Hosting:**
- Docker Compose (local/test/prod)
- Docker images:
  - API: `python:3.12-slim` (Dockerfile at `api/Dockerfile`)
  - Web: `node:24-alpine` multi-stage build (Dockerfile at `web/Dockerfile`)
  - DB: `postgres:16-alpine` (standard image)

**Deployment Modes:**
- **Standalone**: Single instance, no sync (default, good for dev/self-hosted)
- **Mirror**: Read-only replica syncing from canonical server
  - Docker Compose profile: `mirror`
  - Sync sidecar: Runs `python scripts/sync.py --daemon`
  - Sync source: `SYNC_SOURCE_URL` (default: `https://api.oviddb.org`)
  - Sync interval: `SYNC_INTERVAL_MINUTES` (default: 60)
- **Canonical**: Main production server at oviddb.org
  - Uses gunicorn with 4 uvicorn workers
  - Reverse proxied via redshirt on ports 8100/3100

**Port Mapping:**
- Dev: API 8000, Web 3000, DB 5432
- Test: API 8200, Web 3200, DB 5434
- Prod: API 8100, Web 3100, DB internal only

**Production Configuration:**
- Gunicorn: 4 workers, uvicorn worker class
- Environment mode: `OVID_MODE=canonical`
- CORS: Limited to `https://oviddb.org`
- API URL override: `OVID_API_URL=https://api.oviddb.org`

## Environment Configuration

**Required env vars:**
- `OVID_SECRET_KEY` - JWT signing key (minimum 32 chars)
- `DATABASE_URL` - PostgreSQL connection string
- `OVID_API_URL` - Public API URL (for OAuth redirect URIs)
- `OVID_MODE` - `standalone`, `mirror`, or `canonical`

**Optional OAuth credentials:**
- `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`
- Mastodon: None (dynamic registration per instance)
- IndieAuth: None (decentralized)

**Network Configuration:**
- `CORS_ORIGINS` - Comma-separated allowed origins (default: `http://localhost:3000`)
- `NEXT_PUBLIC_API_URL` - Web frontend API URL (baked at build time)
- `API_URL` - Internal Docker network API URL (for SSR)

**Logging:**
- `LOG_LEVEL` - `debug`, `info`, `warning`, `error` (default: info)

**Database:**
- `OVID_DB_NAME` - Database name (default: ovid)
- `OVID_DB_USER` - Database user (default: ovid)
- `OVID_DB_PASSWORD` - Database password

**Mirror/Sync:**
- `SYNC_SOURCE_URL` - Canonical server URL for mirror sync (default: `https://api.oviddb.org`)
- `SYNC_INTERVAL_MINUTES` - Sync poll interval (default: 60)

**Secrets location:**
- Environment variables only
- `.env` file (not committed, local development)
- `.env.example` and `.env.production.example` provide templates

## Webhooks & Callbacks

**Incoming Webhooks:**
- OAuth callbacks (no true webhooks, just redirect URIs):
  - `GET /v1/auth/github/callback`
  - `GET /v1/auth/google/callback`
  - `GET /v1/auth/apple/callback`
  - `GET /v1/auth/mastodon/callback`
  - `GET /v1/auth/indieauth/callback`

**Outgoing Webhooks:**
- None. OVID is read-only for external systems.

## External System Integration

**Automatic Ripping Machine (ARM):**
- Python CLI integration: `arm/identify_ovid.py`
- Purpose: Fingerprint-based disc lookup during ripping
- Transport: HTTP requests to OVID API
- Timeout: Hard 5-second limit (never blocks ripping pipeline)
- Method: `requests` library for sync HTTP
- Returns: Structured result dict (title, year, etc.) or None on miss/error

**Sync Feed (Mirror Protocol):**
- Three unauthenticated endpoints for downstream mirrors:
  - `GET /v1/sync/head` - Current sequence number and timestamp
  - `GET /v1/sync/diff` - Paginated changes since sequence N (max 1000 records/page)
  - `GET /v1/sync/snapshot` - Metadata for latest CC0 database dump
- Rate limited: Dynamic limit based on auth status
- Protocol: Stateless, pull-based (mirrors poll for changes)

---

*Integration audit: 2026-04-04*
