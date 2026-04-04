# Deploying OVID

This runbook covers deploying the OVID stack (API, web UI, PostgreSQL) in both development and production environments.

## Environments

| Environment | API URL | Web URL | Host | Notes |
|---|---|---|---|---|
| Development | `http://localhost:8000` | `http://localhost:3000` | holodeck (LAN) | Direct port access, hot-reload |
| Production | `https://api.oviddb.org` | `https://oviddb.org` | holodeck → redshirt → Cloudflare | Reverse-proxied, TLS via Cloudflare |
| Test | `http://holodeck.nomorestars.com:8200` | `http://holodeck.nomorestars.com:3200` | holodeck (`~/OVID-test/`) | Isolated OAuth/UI testing |

All environments run on **holodeck.nomorestars.com**, but on different port ranges to avoid conflicts:

| Service | Dev ports | Prod ports | Test ports |
|---|---|---|---|
| PostgreSQL | 5432 (exposed) | not exposed | 5434 (exposed) |
| API | 8000 | 8100 → 8000 (internal) | 8200 → 8000 (internal) |
| Web | 3000 | 3100 → 3000 (internal) | 3200 → 3000 (internal) |

---

## Development (holodeck, direct access)

### Prerequisites

| Requirement | Notes |
|---|---|
| Docker Engine | 24.0+ recommended |
| `docker compose` plugin | Use the **plugin** subcommand (`docker compose`), not the legacy hyphenated `docker-compose` binary. See [K006]. |

### Setup

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd ovid
cp .env.example .env
# Edit .env — set OVID_DB_PASSWORD and OVID_SECRET_KEY at minimum
```

### Run

```bash
docker compose up
```

Services are available directly on the LAN:

- **API:** `http://holodeck.nomorestars.com:8000`
- **Web:** `http://holodeck.nomorestars.com:3000`
- **DB:** `holodeck.nomorestars.com:5432` (for direct psql access)

The dev stack uses volume mounts and `--reload` for hot-reloading during development.

### Migrations

```bash
docker compose run --rm api alembic upgrade head
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
| `docker compose` plugin | v2 plugin subcommand |
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
docker compose pull

# Or build locally:
docker compose build
```

### 3. Run Database Migrations

**Run this before every deploy**, including the first one:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head
```

### 4. Start the Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production services start with container name prefixes (`ovid-prod-*`) and on separate ports from dev:

| Container | Host port | Internal port | Description |
|---|---|---|---|
| `ovid-prod-db` | — (not exposed) | 5432 | PostgreSQL 16 |
| `ovid-prod-api` | 8100 | 8000 | FastAPI + Gunicorn (4 workers) |
| `ovid-prod-web` | 3100 | 3000 | Next.js production server |

### 5. Configure Reverse Proxy (redshirt)

The prod stack listens on holodeck ports 8100 (API) and 3100 (web). The **redshirt** server (`64.98.89.233`) acts as the public-facing reverse proxy with TLS termination via Let's Encrypt.

Redshirt runs nginx inside Docker (`/root/compose/`). The vhost config is appended to `/root/compose/nginx/nginx.conf`. The reference copy lives in this repo at [`docs/nginx-oviddb-vhosts.conf`](nginx-oviddb-vhosts.conf).

```nginx
# --- oviddb.org — web UI ---

server {
    listen 80;
    server_name oviddb.org;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name oviddb.org;

    ssl_certificate     /etc/letsencrypt/live/oviddb.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/oviddb.org/privkey.pem;

    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    location / {
        proxy_pass http://192.168.0.28:3100;
    }
}

# --- api.oviddb.org — API ---

server {
    listen 80;
    server_name api.oviddb.org;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    http2 on;
    server_name api.oviddb.org;

    ssl_certificate     /etc/letsencrypt/live/oviddb.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/oviddb.org/privkey.pem;

    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    location / {
        proxy_pass http://192.168.0.28:8100;
    }
}
```

Key details:
- **TLS certs:** Let's Encrypt ECDSA SAN certificate at `/etc/letsencrypt/live/oviddb.org/` (covers both `oviddb.org` and `api.oviddb.org`)
- **ACME challenges:** Port-80 blocks serve `/.well-known/acme-challenge/` from `/var/www/certbot` for certbot renewal
- **Proxy targets:** holodeck at `192.168.0.28` (LAN IP) — web UI on port 3100, API on port 8100
- **HTTP/2:** Enabled on port-443 blocks

### 6. TLS Certificate Renewal

Certs are issued by Let's Encrypt via certbot running as a Docker service (`certbot_www`) on redshirt. A **weekly cron job** already handles automatic renewal:

```
# root crontab on redshirt — runs every Sunday at midnight
0 0 * * 0 /root/compose/renewcert.sh > /var/log/renewcert.log 2>&1
```

The renewal script (`/root/compose/renewcert.sh`):

```bash
#!/bin/sh
cd ~/compose
/usr/bin/docker compose run certbot_www renew --quiet
/usr/bin/docker system prune
```

To manually trigger a renewal or dry-run:

```bash
# Dry-run (test only, no cert changes)
ssh trekkie@redshirt.nomorestars.com 'sudo docker compose -f /root/compose/compose.yaml run --rm certbot_www renew --dry-run'

# Real renewal
ssh trekkie@redshirt.nomorestars.com 'sudo docker compose -f /root/compose/compose.yaml run --rm certbot_www renew'

# Check renewal log
ssh trekkie@redshirt.nomorestars.com 'sudo cat /var/log/renewcert.log'
```

After renewal, nginx picks up the new certs automatically (certbot stores them as symlinks that point to the latest version).

### 7. Configure Cloudflare DNS

In the Cloudflare dashboard for the `oviddb.org` zone:

| Type | Name | Content | Proxy |
|---|---|---|---|
| A | `oviddb.org` | `64.98.89.233` (redshirt) | Proxied (orange cloud) |
| A | `api.oviddb.org` | `64.98.89.233` (redshirt) | Proxied (orange cloud) |

Cloudflare SSL/TLS mode must be set to **Full (strict)** — Cloudflare will validate the Let's Encrypt origin cert on redshirt.

---

## Test Stack (holodeck, isolated OAuth/UI testing)

The test stack runs in an isolated directory (`~/OVID-test/`) on holodeck with its own ports, database volume, and environment. It is used for testing OAuth flows, UI changes, and integration work without affecting dev or production data.

### Purpose

- Test OAuth provider configurations (GitHub, Apple, Google) against real callback URLs
- Validate UI changes with real API data in an isolated environment
- Run integration tests against a stable stack that won't be disrupted by dev hot-reloading

### Ports

| Service | Host Port | Internal Port | Container |
|---|---|---|---|
| PostgreSQL | 5434 | 5432 | `ovid-test-db` |
| API | 8200 | 8000 | `ovid-test-api` |
| Web | 3200 | 3000 | `ovid-test-web` |

### Deploy

```bash
# Clone (first time only)
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git ~/OVID-test
cd ~/OVID-test

# Or pull latest (subsequent deploys)
cd ~/OVID-test && git pull

# Copy .env.test from your local machine (it's gitignored)
# From your dev machine:
#   scp .env.test holodeck.nomorestars.com:~/OVID-test/.env.test

# Generate OVID_SECRET_KEY if not set
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Paste the output into .env.test as OVID_SECRET_KEY=<value>

# Build images (bakes NEXT_PUBLIC_API_URL into web client)
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test build

# Start DB and run migrations
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test up -d db
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test run --rm api alembic upgrade head

# Start all services
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test up -d
```

### Verify

```bash
# All containers running
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test ps

# API health
curl http://holodeck.nomorestars.com:8200/health
# Expected: {"status":"ok"}

# Sync head (empty DB returns seq 0)
curl http://holodeck.nomorestars.com:8200/v1/sync/head

# Web returns 200
curl -o /dev/null -w "%{http_code}" http://holodeck.nomorestars.com:3200
```

### Logs & Troubleshooting

```bash
# All services
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test logs -f

# Single service
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test logs -f api

# Check for port conflicts
ss -tlnp | grep -E '(5434|8200|3200)'
```

### Teardown

```bash
# Stop without removing data
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test down

# Stop and remove data volume
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test down -v
```

---

## Running All Stacks Simultaneously

The dev, prod, and test stacks can run side-by-side on holodeck because they use different ports, container names, and (for test) a separate project directory:

```bash
# Dev stack (ports 8000/3000/5432) — from ~/ovid/
docker compose up -d

# Prod stack (ports 8100/3100, DB not exposed) — from ~/ovid/
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Test stack (ports 8200/3200/5434) — from ~/OVID-test/
cd ~/OVID-test
docker compose -f docker-compose.yml -f docker-compose.test.yml --env-file .env.test -p ovid-test up -d
```

Note: dev and prod use the same `docker-compose.yml` base directory, but the prod override sets `name: ovid-prod` to ensure separate Docker volumes (`ovid-prod_ovid_pgdata` vs `ovid_ovid_pgdata`). The test stack uses a separate directory (`~/OVID-test/`) with its own volume, ensuring full data isolation across all three environments.

---

## Health Check

```bash
# Dev
curl http://localhost:8000/health

# Prod (from holodeck)
curl http://localhost:8100/health

# Prod (from internet)
curl https://api.oviddb.org/health

# Test
curl http://holodeck.nomorestars.com:8200/health
```

Expected: `{"status": "ok"}`

---

## Updating

To deploy a new version to production:

```bash
# Pull latest images
docker compose pull

# Run any new migrations
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic upgrade head

# Restart with production overrides
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## Troubleshooting

### Check Logs

```bash
# All services (prod)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

# Single service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api
```

### Database Connection Issues

If the API can't reach PostgreSQL, check:

1. The `db` healthcheck is passing: `docker compose ps`
2. `OVID_DB_PASSWORD` in `.env` matches what PostgreSQL was initialised with
3. If the password was changed after first run, delete the volume: `docker compose down -v` (⚠️ destroys data)

### Migration Failures

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic current
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm api alembic history
```
