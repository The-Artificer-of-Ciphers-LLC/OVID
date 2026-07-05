# Technology Stack

**Analysis Date:** 2026-07-05

## Languages

**Primary:**
- Python 3.12 (CI), `>=3.9` supported — API server (`api/`) and disc-fingerprinting client (`ovid-client/`)
- TypeScript — web frontend (`web/`), Next.js 16 App Router

**Secondary:**
- Shell scripts — `arm/entrypoint_wrapper.sh`, `arm/start_arm_container.sh` (Automatic Ripping Machine integration)
- Bash/YAML — CI workflows in `.github/workflows/`

## Runtime

**Environment:**
- Python 3.12 (`api/Dockerfile`, `.github/workflows/ci.yml`), `ovid-client` declares `requires-python = ">=3.9"` in `ovid-client/pyproject.toml`
- Node.js (version implied by Next.js 16 / React 19 requirements, no `.nvmrc` present) for `web/`

**Package Manager:**
- pip for both Python projects (`api/requirements.txt`, `ovid-client/pyproject.toml`)
- npm for `web/` (`web/package-lock.json` present)
- Lockfile: present for web (`package-lock.json`); Python projects use unpinned/range-pinned `requirements.txt` (no `requirements.lock` or `poetry.lock`)

## Frameworks

**Core:**
- FastAPI `>=0.110,<1.0` — API server, `api/main.py`
- SQLAlchemy `>=2.0,<3.0` (asyncio extra) — ORM, `api/app/models.py`, `api/app/database.py`
- Alembic `>=1.13,<2.0` — DB migrations, `api/alembic/`
- Next.js `16.2.2` + React `19.2.4` — web frontend, `web/app/`
- Tailwind CSS `^4` — styling, `web/postcss.config.mjs`

**Testing:**
- pytest `>=7.0` — both `api/tests/` and `ovid-client/tests/`
- Vitest `^4.1.2` + Testing Library (`@testing-library/react`, `jest-dom`, `user-event`) — `web/src/__tests__/`, config in `web/vitest.config.ts`

**Build/Dev:**
- uvicorn `[standard] >=0.29,<1.0` — ASGI dev server for API, invoked via `docker-compose.yml`
- gunicorn `>=21.2,<24.0` — production ASGI process manager, `api/Dockerfile`
- ESLint `^9` with `eslint-config-next` — `web/eslint.config.mjs`
- mkdocs — documentation site, `mkdocs.yml`, `docs/`

## Key Dependencies

**Critical:**
- `authlib >=1.3,<2.0` — OAuth client (GitHub, Google) and Apple Sign-In JWT handling, `api/app/auth/routes.py`
- `PyJWT >=2.8,<3.0` — JWT issuance/verification, `api/app/auth/jwt.py`
- `itsdangerous >=2.1,<3.0` — signed session/token support (used by Starlette `SessionMiddleware`)
- `slowapi >=0.1.9,<1.0` — rate limiting, `api/app/rate_limit.py`
- `httpx >=0.27,<1.0` — outbound HTTP (OAuth token exchange, mirror sync), `api/app/sync.py`
- `pycdlib >=1.14` — DVD/Blu-ray filesystem parsing, `ovid-client/src/ovid/`
- `tmdbv3api >=1.9` — TMDB metadata lookup during disc submission, `ovid-client/src/ovid/tmdb.py`
- `click >=8.0`, `rich >=13.0` — CLI framework and terminal UI, `ovid-client/src/ovid/cli.py`

**Infrastructure:**
- `psycopg2-binary >=2.9,<3.0` — PostgreSQL driver, `api/app/database.py`
- `postgres:16-alpine` (Docker image) — primary datastore, `docker-compose.yml`

## Configuration

**Environment:**
- `.env` (git-ignored) copied from `.env.example`; loaded via `docker-compose` env interpolation and `os.environ` in Python
- Key vars: `OVID_DB_NAME`, `OVID_DB_USER`, `OVID_DB_PASSWORD`, `DATABASE_URL`, `OVID_SECRET_KEY`, `OVID_API_URL`, `LOG_LEVEL`, `CORS_ORIGINS`, `OVID_MODE` (standalone/mirror/canonical), `SYNC_SOURCE_URL`, `SYNC_INTERVAL_MINUTES`
- OAuth provider vars (all optional, feature-gated on presence): `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`, `APPLE_CLIENT_ID`/`APPLE_TEAM_ID`/`APPLE_KEY_ID`/`APPLE_PRIVATE_KEY`, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` — validated in `api/app/auth/config.py` and `api/app/auth/routes.py`
- `api/app/auth/config._require_env` raises at import time if `OVID_SECRET_KEY` is missing — fail-fast pattern for required secrets
- `.env.production.example` referenced (for `oviddb.org` canonical deployment) — not read directly per forbidden-files policy

**Build:**
- `web/next.config.ts`, `web/tsconfig.json`, `web/postcss.config.mjs` — frontend build config
- `api/alembic.ini` + `api/alembic/env.py` — migration runner config
- `docker-compose.yml` (dev), `docker-compose.test.yml`, `docker-compose.prod.yml` — three environment-specific compose stacks

## Platform Requirements

**Development:**
- Docker + Docker Compose (primary dev workflow: `docker-compose up`)
- Local Python 3.12 + Node.js for running services outside Docker
- Optional: real DVD/Blu-ray disc or fixture files for `ovid-client` disc-reading tests (`OVID_TEST_DISC_PATH` env var, `real_disc` pytest marker)

**Production:**
- Docker-based deployment (`api/Dockerfile`, `web/Dockerfile`, `docker-compose.prod.yml`)
- PostgreSQL 16
- Canonical server at `oviddb.org`; self-hosted mirror/standalone instances supported per `docs/self-hosting.md`, `docs/deployment.md`
- ARM (Automatic Ripping Machine) integration for disc identification pipeline, `arm/`

---

*Stack analysis: 2026-07-05*
