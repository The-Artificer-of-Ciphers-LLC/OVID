# External Integrations

**Analysis Date:** 2026-07-05

## APIs & External Services

**Metadata Lookup:**
- TMDB (The Movie Database) - movie/release metadata lookup during disc submission workflow
  - SDK/Client: `tmdbv3api` (`ovid-client/src/ovid/tmdb.py`), used from CLI submit flow (`ovid-client/src/ovid/cli.py`)
  - Auth: TMDB API key (not found in `.env.example` — likely configured separately or via client-local config; verify before assuming unauthenticated)

**Mirror Sync (peer OVID nodes):**
- Canonical OVID server (`oviddb.org`) - source of truth for mirror-mode nodes to pull diffs from
  - Client: `httpx`, `api/app/sync.py`, `api/scripts/sync.py`
  - Config: `SYNC_SOURCE_URL` (default `https://api.oviddb.org`), `SYNC_INTERVAL_MINUTES`
  - Server-side endpoints exposed for downstream mirrors: `GET /v1/sync/head`, `GET /v1/sync/diff`, `GET /v1/sync/snapshot` — `api/app/routes/sync.py`

**Automatic Ripping Machine (ARM):**
- ARM disc-ripping pipeline integration — identifies discs during the ARM rip process
  - Entry points: `arm/identify.py`, `arm/identify_original.py`, `arm/identify_ovid.py`
  - Wrapper: `arm/entrypoint_wrapper.sh`, `arm/start_arm_container.sh`
  - Documented in `docs/arm-integration.md`

## Data Storage

**Databases:**
- PostgreSQL 16 (`postgres:16-alpine` image)
  - Connection: `DATABASE_URL` env var, default `postgresql://ovid:ovidlocal@localhost:5432/ovid`
  - Client/ORM: SQLAlchemy 2.x, `psycopg2-binary` driver — `api/app/database.py`, `api/app/models.py`
  - Migrations: Alembic — `api/alembic/`, `api/alembic/versions/`
  - Schema: 9 core tables — `discs`, `releases`, `disc_releases`, `disc_titles`, `disc_tracks`, `disc_sets`, `users`, `user_oauth_links`, `disc_edits`, plus `global_seq` (sync sequence counter) and `sync_state` (mirror tracking) — `api/app/models.py`

**File Storage:**
- Local filesystem only — no object storage (S3/GCS) integration detected. CC0 database dumps referenced via `/v1/sync/snapshot` metadata endpoint but dump hosting not verified in this pass.

**Caching:**
- None detected — no Redis/Memcached client in dependencies.

## Authentication & Identity

**Auth Providers (multi-provider, feature-gated by env presence):**
- GitHub OAuth - `api/app/auth/routes.py` (`/v1/auth/github/login`), configured via `authlib` OAuth registry, activated when `GITHUB_CLIENT_ID` is set
- Google OAuth (OIDC) - same file, uses `server_metadata_url=https://accounts.google.com/.well-known/openid-configuration`, activated when `GOOGLE_CLIENT_ID` is set
- Apple Sign-In - activated only when all four of `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` are set (`_APPLE_CONFIGURED` flag, `api/app/auth/routes.py`)
- IndieAuth - self-hosted identity protocol, `api/app/auth/indieauth.py` (endpoint discovery, PKCE flow)
- Mastodon OAuth - per-instance dynamic client registration (no static credentials needed), `api/app/auth/mastodon.py`
- Session state (OAuth CSRF protection): Starlette `SessionMiddleware`, keyed by `OVID_SECRET_KEY`

**Token issuance:**
- Application JWTs issued after any provider login, `api/app/auth/jwt.py` (PyJWT), lifetime controlled by `OVID_JWT_EXPIRY_DAYS` (default 30)
- Web client stores JWT in `localStorage` under `ovid_token`, `web/lib/auth.ts`

**Account linking:**
- Multiple OAuth identities can link to one user account — `user_oauth_links` table, tested in `api/tests/test_auth_linking.py`

## Monitoring & Observability

**Error Tracking:**
- None detected — no Sentry/Bugsnag SDK in dependencies.

**Logs:**
- Standard Python `logging` module, level controlled by `LOG_LEVEL` env var (default `info`), e.g. `api/app/routes/sync.py`
- Request ID tagging via custom `RequestIdMiddleware`, `api/app/middleware.py`

## CI/CD & Deployment

**Hosting:**
- Docker Compose-based self-hosting (`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`)
- Canonical production instance: `oviddb.org`
- Nginx reverse proxy config for canonical + mirror vhosts, `docs/nginx-oviddb-vhosts.conf`

**CI Pipeline:**
- GitHub Actions, `.github/workflows/ci.yml` — jobs: `ovid-client-tests`, `api-tests`, `e2e-tests` (depends on both)
- `.github/workflows/docs.yml` — mkdocs site build/publish
- `.github/workflows/release.yml` — release automation
- `.github/workflows/cc0-dump.yml` — automated CC0 public-domain database dump generation/publishing

## Environment Configuration

**Required env vars:**
- `OVID_SECRET_KEY` — required at API import time (`api/app/auth/config.py` raises `RuntimeError` if missing)
- `DATABASE_URL` (or component vars `OVID_DB_NAME`/`OVID_DB_USER`/`OVID_DB_PASSWORD`)

**Optional/feature-gated env vars:**
- `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`, `APPLE_CLIENT_ID`/`APPLE_TEAM_ID`/`APPLE_KEY_ID`/`APPLE_PRIVATE_KEY`
- `CORS_ORIGINS` (default `http://localhost:3000`)
- `OVID_MODE` (`standalone` | `mirror` | `canonical`) — gates write-endpoint availability via `MirrorModeMiddleware`, `api/app/middleware.py`
- `SYNC_SOURCE_URL`, `SYNC_INTERVAL_MINUTES` — mirror-mode only

**Secrets location:**
- `.env` (git-ignored, not read by this analysis per forbidden-files policy); `.env.example` documents the shape without values
- `.env.production.example` (referenced in `.env.example` comments) documents production-specific vars for `oviddb.org`

## Webhooks & Callbacks

**Incoming:**
- OAuth redirect/callback endpoints act as inbound webhooks from identity providers: `/v1/auth/github/callback`, `/v1/auth/google/callback` (implied by `authlib` registration pattern), Apple Sign-In POST callback, IndieAuth callback — all in `api/app/auth/routes.py`

**Outgoing:**
- None detected beyond OAuth token-exchange calls (GitHub/Google/Apple/Mastodon token endpoints) and mirror sync polling (`httpx` calls to `SYNC_SOURCE_URL`)

---

*Integration audit: 2026-07-05*
