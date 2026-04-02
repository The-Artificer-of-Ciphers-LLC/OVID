# Getting Started — Developer Guide

Set up a complete OVID development environment with the API server, database, and ovid-client library.

## Prerequisites

- Python 3.9+ (3.12+ recommended)
- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- Git

## Repository Layout

```
OVID/
├── api/                    ← FastAPI server
│   ├── app/                ← Application code (models, routes, auth, schemas)
│   ├── alembic/            ← Database migrations
│   ├── scripts/            ← Seed script
│   └── tests/              ← API test suite (124 tests)
├── ovid-client/            ← Python fingerprinting library + CLI
│   ├── src/ovid/           ← Library source
│   └── tests/              ← Client test suite (113 tests)
├── tests/                  ← Cross-package E2E tests (4 tests)
├── docs/                   ← Documentation
├── docker-compose.yml      ← Local development stack
└── .env.example            ← Environment variable template
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID
```

### 2. Create a Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install ovid-client in development mode

```bash
cd ovid-client
pip install -e '.[dev]'
cd ..
```

This installs the `ovid` CLI command and all development dependencies (pytest, etc.).

### 4. Install API dependencies

```bash
pip install -r api/requirements.txt
pip install pytest httpx
```

### 5. Start the database (Docker)

```bash
cp .env.example .env
docker compose up -d db
```

### 6. Run database migrations

```bash
docker compose exec db psql -U ovid -c "SELECT 1"  # verify DB is up
cd api
DATABASE_URL=postgresql://ovid:ovidlocal@localhost:5432/ovid alembic upgrade head
cd ..
```

### 7. Start the API server (development mode)

Either via Docker:
```bash
docker compose up -d api
```

Or directly (for debugging):
```bash
cd api
DATABASE_URL=postgresql://ovid:ovidlocal@localhost:5432/ovid \
OVID_SECRET_KEY=dev-secret-change-in-production \
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Running Tests

### ovid-client tests (113 tests)

```bash
cd ovid-client
python -m pytest tests/ -v
```

### API tests (124 tests)

```bash
cd api
python -m pytest tests/ -v
```

Tests use an in-memory SQLite database — no Docker or PostgreSQL required.

### E2E pipeline tests (4 tests)

```bash
PYTHONPATH=api python -m pytest tests/ -v
```

These tests prove the full fingerprint → submit → lookup round-trip across ovid-client and the API.

### All tests at once

```bash
cd ovid-client && python -m pytest tests/ -v && cd ..
cd api && python -m pytest tests/ -v && cd ..
PYTHONPATH=api python -m pytest tests/ -v
```

## Using the CLI

### Fingerprint a DVD

```bash
# From a VIDEO_TS folder
ovid fingerprint /path/to/VIDEO_TS

# From an ISO image
ovid fingerprint /path/to/movie.iso
```

### Look up a disc

```bash
# Against the local API
ovid lookup dvd1-59863dd2519845852f991036aabe2a725fc5d751 --api-url http://localhost:8000
```

### Submit a disc (interactive wizard)

```bash
ovid submit /path/to/VIDEO_TS --api-url http://localhost:8000 --token YOUR_JWT
```

The submit wizard walks through: fingerprint → TMDB title search → pick release → edition/disc# → submit.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (required) | PostgreSQL connection string |
| `OVID_SECRET_KEY` | (required) | JWT signing key — any random string ≥32 chars |
| `OVID_API_URL` | `http://localhost:8000` | API base URL for ovid-client |
| `OVID_TOKEN` | (none) | JWT token for authenticated CLI operations |
| `TMDB_API_KEY` | (none) | TMDB API key for movie search during submit |
| `GITHUB_CLIENT_ID` | (none) | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | (none) | GitHub OAuth app client secret |
| `APPLE_CLIENT_ID` | (none) | Apple Sign-In service ID |
| `APPLE_TEAM_ID` | (none) | Apple Developer team ID |
| `APPLE_KEY_ID` | (none) | Apple Sign-In key ID |
| `APPLE_PRIVATE_KEY` | (none) | Apple Sign-In private key (PEM) |

OAuth providers are optional — the API starts without them and returns 501 for unconfigured provider endpoints.

## Architecture

```
┌─────────────────┐     ┌────────────────┐     ┌──────────────┐
│   ovid-client   │────▶│   FastAPI API   │────▶│  PostgreSQL  │
│  (Python lib +  │     │  (port 8000)   │     │  (port 5432) │
│   CLI)          │     └────────────────┘     └──────────────┘
└─────────────────┘
```

- **ovid-client** reads DVD structure from folders/ISOs/drives, computes fingerprints, and communicates with the API via HTTP.
- **FastAPI API** handles disc CRUD, search, and authentication. Uses SQLAlchemy ORM with Alembic migrations.
- **PostgreSQL** stores all disc metadata, user accounts, and audit history across 9 tables.

## Next Steps

- [API Reference](api-reference.md) — detailed endpoint documentation
- [CLI Reference](cli-reference.md) — full CLI command reference
- [Fingerprint Spec](fingerprint-spec.md) — OVID-DVD-1 algorithm specification
- [Docker Quick-Start](docker-quickstart.md) — fastest path to a running stack
