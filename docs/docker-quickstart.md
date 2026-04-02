# Docker Compose Quick-Start

Get the full OVID stack running locally in under 5 minutes.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose (v2.0+)
- Git

## Steps

### 1. Clone and configure

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID
cp .env.example .env
```

The defaults in `.env.example` work for local development — no edits required.

### 2. Start the stack

```bash
docker compose up -d
```

This starts two services:
- **db** — PostgreSQL 16 (port 5432)
- **api** — FastAPI server (port 8000) with hot-reload

Wait for both containers to be healthy:

```bash
docker compose ps
```

### 3. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

This creates all 9 tables: `discs`, `releases`, `disc_releases`, `disc_titles`, `disc_tracks`, `disc_sets`, `users`, `user_oauth_links`, `disc_edits`.

### 4. Seed test data (optional)

```bash
docker compose exec api python scripts/seed.py
```

Populates the database with a sample disc entry (The Matrix, 1999) including titles, tracks, and a test user.

### 5. Verify

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok"}

# Look up the seeded disc
curl http://localhost:8000/v1/disc/dvd1-matrix-1999-r1-us
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Liveness check |
| GET | `/v1/disc/{fingerprint}` | No | Look up disc metadata |
| POST | `/v1/disc` | Yes | Submit a new disc |
| POST | `/v1/disc/{fingerprint}/verify` | Yes | Verify an existing disc |
| GET | `/v1/search?q=` | No | Search releases by title |
| GET | `/v1/auth/github/login` | No | Start GitHub OAuth flow |
| GET | `/v1/auth/me` | Yes | Current user info |

Auto-generated API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI) and [http://localhost:8000/redoc](http://localhost:8000/redoc) (ReDoc).

## Stopping

```bash
docker compose down        # stop containers, keep data
docker compose down -v     # stop containers AND delete database volume
```

## Connecting a Database Tool

PostgreSQL is exposed on `localhost:5432`:

| Setting | Value |
|---------|-------|
| Host | `localhost` |
| Port | `5432` |
| Database | `ovid` |
| User | `ovid` |
| Password | `ovidlocal` (default from .env.example) |

## Next Steps

- [Getting Started (Developer)](getting-started-dev.md) — full dev setup with tests and ovid-client
- [API Reference](api-reference.md) — detailed endpoint documentation
- [CLI Reference](cli-reference.md) — ovid-client command-line usage
