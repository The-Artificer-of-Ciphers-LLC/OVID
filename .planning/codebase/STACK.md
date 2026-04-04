# Technology Stack

**Analysis Date:** 2026-04-04

## Languages

**Primary:**
- Python 3.12 - API backend, CLI tools, database migrations (FastAPI + SQLAlchemy)
- TypeScript 5 - Web frontend (Next.js 16.2.2)
- JavaScript - Node.js runtime for web layer

**Secondary:**
- Shell/Bash - Container entrypoints, deployment scripts

## Runtime

**Environment:**
- Python 3.12 (via Docker: `python:3.12-slim`)
- Node.js 24 Alpine (via Docker: `node:24-alpine`)

**Package Managers:**
- pip (Python)
  - Lockfile: `requirements.txt` (pinned versions in `api/`)
- npm (Node.js)
  - Lockfile: `package-lock.json` (committed in `web/`)

## Frameworks

**Core:**
- FastAPI 0.110+ - Async web API framework with automatic Swagger/ReDoc docs
- Starlette - ASGI middleware layer (includes CORSMiddleware, SessionMiddleware)
- Next.js 16.2.2 - React full-stack framework with server/client rendering
- React 19.2.4 - UI component library

**Database:**
- SQLAlchemy 2.0+ - ORM with async support
- Alembic 1.13+ - Database migration tool
- PostgreSQL 16 - Relational database (Docker: `postgres:16-alpine`)

**Testing:**
- Vitest 4.1.2 - Test runner (web)
- Testing Library - React component testing
  - @testing-library/react 16.3.2
  - @testing-library/user-event 14.6.1
  - @testing-library/jest-dom 6.9.1
- pytest 7.0+ - Python test framework (optional dependency in ovid-client)
- jsdom 29.0.1 - DOM simulation for Node.js tests

**Build/Dev:**
- TypeScript 5 - Type checking (web)
- Tailwind CSS 4 - Utility CSS framework
- ESLint 9 - JavaScript linting
- eslint-config-next 16.2.2 - Next.js ESLint rules
- Vitest 4.1.2 - Vite-powered test runner

## Key Dependencies

**Critical:**
- authlib 1.3+ - OAuth 2.0 provider integration (GitHub, Google, Apple) via Starlette
- PyJWT 2.8+ - JWT token creation/verification (ES256 for Apple, HS256 for standard)
- httpx 0.27+ - Async HTTP client (IndieAuth discovery, Mastodon API, Apple token exchange)
- psycopg2-binary 2.9+ - PostgreSQL database adapter
- slowapi 0.1.9+ - Rate limiting (decorator-based via `@limiter.limit()`)
- gunicorn 21.2-24 - Production WSGI server with uvicorn worker
- uvicorn[standard] 0.29+ - ASGI server (development and worker mode)
- itsdangerous 2.1+ - Secure token generation (session signing)

**CLI/Client:**
- pycdlib 1.14+ - ISO 9660 CD/DVD metadata parser (disc fingerprinting)
- click 8.0+ - CLI argument/option parsing
- requests 2.28+ - HTTP client for ARM integration
- rich 13.0+ - Terminal formatting and logging
- tmdbv3api 1.9+ - TMDB metadata lookups for disc releases

**Frontend HTTP:**
- Next.js built-in `fetch()` - Native browser/Node.js fetch API (no external HTTP library)

## Configuration

**Environment:**
- Environment variables only (no config files)
- Loaded at startup via `os.environ.get()`
- Validation at import time for required vars (e.g., `OVID_SECRET_KEY` via `_require_env()`)

**Key Config Files:**
- `api/alembic.ini` - Alembic migration config (sqlalchemy.url loaded from `DATABASE_URL` env var at runtime)
- `.env.example` - Development environment template
- `.env.production.example` - Production environment template
- `docker-compose.yml` - Base compose config (dev/standalone)
- `docker-compose.prod.yml` - Production overrides (gunicorn, no volumes, exposed ports)
- `docker-compose.test.yml` - Test environment overrides (holodeck test server)
- `web/next.config.ts` - Next.js config (output: "standalone" for Docker)
- `web/tsconfig.json` - TypeScript config with path alias `@/*`
- `api/requirements.txt` - Python production dependencies
- `ovid-client/pyproject.toml` - Setuptools-based package config (source layout: `src/`)

**Build Arguments:**
- `NEXT_PUBLIC_API_URL` - Baked into Next.js client bundles at build time via Docker ARG

## Platform Requirements

**Development:**
- Docker & Docker Compose v2 (for full stack)
- Python 3.12 (local development without containers)
- Node.js 24 (local web development without containers)
- PostgreSQL 16 (or via container)

**Production:**
- Docker (images: `python:3.12-slim`, `node:24-alpine`, `postgres:16-alpine`)
- Docker Compose v2 with profile support (`--profile mirror` for sync mode)
- Environment variables for all secrets
- Reverse proxy (redshirt mentioned in compose comments) for HTTPS

**Deployment Target:**
- Currently: holodeck (internal test server) via docker-compose
- Production: Canonical oviddb.org instance
- Self-hosted: Any platform supporting Docker
- Mirror nodes: Syncing read-only copies of the canonical database

---

*Stack analysis: 2026-04-04*
