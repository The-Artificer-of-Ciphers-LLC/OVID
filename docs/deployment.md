# Deploying OVID to Production

This runbook covers deploying the full OVID stack (API, web UI, PostgreSQL) to **holodeck.nomorestars.com** or any similar server.

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine | 24.0+ recommended |
| `docker-compose` binary | Use the **hyphenated** standalone binary, not `docker compose` plugin. See [K006]. |
| PostgreSQL | Provided by the `db` service in Compose, or use an external managed instance. |
| TLS termination | A reverse proxy (Caddy, nginx, Traefik) must sit in front of the Compose stack. |
| Domain DNS | `holodeck.nomorestars.com` pointed to the server IP. |

## Step-by-Step Deployment

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/ovid.git
cd ovid
```

### 2. Configure Environment Variables

```bash
cp .env.production.example .env
```

Open `.env` and fill in all values. At minimum:

- `OVID_DB_PASSWORD` — strong random password
- `OVID_SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- OAuth credentials for each provider you want to enable (GitHub, Apple, Google)

### 3. Pull or Build Images

```bash
# Pull pre-built images (if published to GHCR):
docker-compose pull

# Or build locally:
docker-compose build
```

### 4. Run Database Migrations

**Run this before every deploy**, including the first one:

```bash
docker-compose run --rm api alembic upgrade head
```

This applies all Alembic migrations to the PostgreSQL database.

### 5. Start the Stack

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The services will start:

| Service | Internal Port | Description |
|---|---|---|
| `db` | 5432 (not exposed) | PostgreSQL 16 |
| `api` | 8000 | FastAPI + Gunicorn (4 workers) |
| `web` | 3000 | Next.js production server |

### 6. Configure Reverse Proxy (HTTPS)

The Compose stack listens on `localhost:8000` (API) and `localhost:3000` (web) only. You need a reverse proxy in front for TLS termination and public access.

#### Caddy Example

```
holodeck.nomorestars.com {
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:3000
    }
}
```

#### nginx Example

```nginx
server {
    listen 443 ssl;
    server_name holodeck.nomorestars.com;

    ssl_certificate     /etc/letsencrypt/live/holodeck.nomorestars.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/holodeck.nomorestars.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Health Check

Verify the API is running:

```bash
curl https://holodeck.nomorestars.com/api/health
# Expected: {"status": "ok"}
```

## Updating

To deploy a new version:

```bash
# Pull latest images
docker-compose pull

# Run any new migrations
docker-compose run --rm api alembic upgrade head

# Restart with production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Troubleshooting

### Check Logs

```bash
# All services
docker-compose logs -f

# Single service
docker-compose logs -f api
docker-compose logs -f web
docker-compose logs -f db
```

### Database Connection Issues

If the API can't reach PostgreSQL, check:

1. The `db` healthcheck is passing: `docker-compose ps`
2. `OVID_DB_PASSWORD` in `.env` matches what PostgreSQL was initialised with
3. If the password was changed after first run, delete the volume: `docker-compose down -v` (⚠️ destroys data)

### Migration Failures

```bash
# Check current migration state
docker-compose run --rm api alembic current

# See migration history
docker-compose run --rm api alembic history
```
