# Deploying OVID

This runbook covers deploying the OVID stack (API, web UI, PostgreSQL) in both development and production environments.

## Environments

| Environment | API URL | Web URL | Host | Notes |
|---|---|---|---|---|
| Development | `http://localhost:8000` | `http://localhost:3000` | holodeck (LAN) | Direct port access, hot-reload |
| Production | `https://api.oviddb.org` | `https://oviddb.org` | holodeck → redshirt → Cloudflare | Reverse-proxied, TLS via Cloudflare |

Both environments run on **holodeck.nomorestars.com**, but on different port ranges to avoid conflicts:

| Service | Dev ports | Prod ports |
|---|---|---|
| PostgreSQL | 5432 (exposed) | not exposed |
| API | 8000 | 8100 → 8000 (internal) |
| Web | 3000 | 3100 → 3000 (internal) |

---

## Development (holodeck, direct access)

### Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine | 24.0+ recommended |
| `docker-compose` binary | Use the **hyphenated** standalone binary, not `docker compose` plugin. See [K006]. |

### Setup

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd ovid
cp .env.example .env
# Edit .env — set OVID_DB_PASSWORD and OVID_SECRET_KEY at minimum
```

### Run

```bash
docker-compose up
```

Services are available directly on the LAN:

- **API:** `http://holodeck.nomorestars.com:8000`
- **Web:** `http://holodeck.nomorestars.com:3000`
- **DB:** `holodeck.nomorestars.com:5432` (for direct psql access)

The dev stack uses volume mounts and `--reload` for hot-reloading during development.

### Migrations

```bash
docker-compose run --rm api alembic upgrade head
```

---

## Production (api.oviddb.org / oviddb.org)

Production runs on holodeck using the prod Compose override, exposed to the internet via a reverse proxy chain:

```
Internet → Cloudflare → redshirt (reverse proxy) → holodeck:8100/3100
```

### Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine 24.0+ | On holodeck |
| `docker-compose` binary | Hyphenated standalone binary |
| SSH access to redshirt | For reverse proxy configuration |
| Cloudflare account | DNS management for oviddb.org |

### 1. Configure Environment

On holodeck:

```bash
cd /path/to/ovid
cp .env.production.example .env
```

Fill in all values in `.env`:

- `OVID_DB_PASSWORD` — strong random password
- `OVID_SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- OAuth credentials for each provider (GitHub, Apple, Google)

### 2. Pull or Build Images

```bash
# Pull pre-built images (if published to GHCR):
docker-compose pull

# Or build locally:
docker-compose build
```

### 3. Run Database Migrations

**Run this before every deploy**, including the first one:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### 4. Start the Stack

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production services start with container name prefixes (`ovid-prod-*`) and on separate ports from dev:

| Container | Host port | Internal port | Description |
|---|---|---|---|
| `ovid-prod-db` | — (not exposed) | 5432 | PostgreSQL 16 |
| `ovid-prod-api` | 8100 | 8000 | FastAPI + Gunicorn (4 workers) |
| `ovid-prod-web` | 3100 | 3000 | Next.js production server |

### 5. Configure Reverse Proxy (redshirt)

The prod stack listens on holodeck ports 8100 (API) and 3100 (web). The **redshirt** server acts as the public-facing reverse proxy with TLS termination.

SSH to redshirt and configure the reverse proxy:

#### Caddy (on redshirt)

```
api.oviddb.org {
    reverse_proxy holodeck.nomorestars.com:8100
}

oviddb.org {
    reverse_proxy holodeck.nomorestars.com:3100
}
```

#### nginx (on redshirt)

```nginx
server {
    listen 443 ssl;
    server_name api.oviddb.org;

    # TLS certs managed by Cloudflare Origin Certificates or Let's Encrypt
    ssl_certificate     /etc/ssl/oviddb/api.oviddb.org.pem;
    ssl_certificate_key /etc/ssl/oviddb/api.oviddb.org.key;

    location / {
        proxy_pass http://holodeck.nomorestars.com:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl;
    server_name oviddb.org;

    ssl_certificate     /etc/ssl/oviddb/oviddb.org.pem;
    ssl_certificate_key /etc/ssl/oviddb/oviddb.org.key;

    location / {
        proxy_pass http://holodeck.nomorestars.com:3100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6. Configure Cloudflare DNS

In the Cloudflare dashboard for the `oviddb.org` zone, create:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A (or CNAME) | `api.oviddb.org` | redshirt's public IP | Proxied (orange cloud) |
| A (or CNAME) | `oviddb.org` | redshirt's public IP | Proxied (orange cloud) |

If using Cloudflare Origin Certificates on redshirt, set SSL/TLS mode to **Full (strict)**.

---

## Running Both Stacks Simultaneously

The dev and prod stacks can run side-by-side on holodeck because they use different ports and container names:

```bash
# Dev stack (ports 8000/3000/5432)
docker-compose up -d

# Prod stack (ports 8100/3100, DB not exposed)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Note: they share the same `docker-compose.yml` base, so they share the same Docker volumes by default. For fully isolated data, use a separate project directory or `--project-name` flag.

---

## Health Check

```bash
# Dev
curl http://localhost:8000/health

# Prod (from holodeck)
curl http://localhost:8100/health

# Prod (from internet)
curl https://api.oviddb.org/health
```

Expected: `{"status": "ok"}`

---

## Updating

To deploy a new version to production:

```bash
# Pull latest images
docker-compose pull

# Run any new migrations
docker-compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head

# Restart with production overrides
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Troubleshooting

### Check Logs

```bash
# All services (prod)
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Single service
docker-compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
```

### Database Connection Issues

If the API can't reach PostgreSQL, check:

1. The `db` healthcheck is passing: `docker-compose ps`
2. `OVID_DB_PASSWORD` in `.env` matches what PostgreSQL was initialised with
3. If the password was changed after first run, delete the volume: `docker-compose down -v` (⚠️ destroys data)

### Migration Failures

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic current
docker-compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic history
```
