# Deploying OVID

This runbook covers deploying the OVID stack (API, web UI, PostgreSQL) in both development and production environments.

## Environments

| Environment | API URL | Web URL | Host | Notes |
|---|---|---|---|---|
| Development | `http://localhost:8000` | `http://localhost:3000` | holodeck (LAN) | Direct port access, hot-reload |
| Production | `https://api.oviddb.org` | `https://oviddb.org` | holodeck → redshirt → Cloudflare | Reverse-proxied, TLS via Cloudflare |
| Test | `http://holodeck.nomorestars.com:8200` | `http://holodeck.nomorestars.com:3200` | holodeck (`~/OVID-test/`) | Isolated OAuth/UI testing |
| Staging | `https://api.staging.oviddb.org` | `https://staging.oviddb.org` | holodeck → redshirt → Cloudflare | Reverse-proxied, TLS; non-apex D-06 preview deploy — Phase 8 owns the public `oviddb.org` apex cutover + DB seeding |

All environments run on **holodeck.nomorestars.com**, but on different port ranges to avoid conflicts:

| Service | Dev ports | Prod ports | Test ports | Staging ports |
|---|---|---|---|---|
| PostgreSQL | 5432 (exposed) | not exposed | 5434 (exposed) | not exposed |
| API | 8000 | 8100 → 8000 (internal) | 8200 → 8000 (internal) | 8300 → 8000 (internal) |
| Web | 3000 | 3100 → 3000 (internal) | 3200 → 3000 (internal) | 3300 → 3000 (internal) |

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

**`OVID_ENV` is required** — the API refuses to boot without it. Set
`OVID_ENV=development` for this environment; `docker-compose.yml` already
supplies this default, so a plain `docker compose up` works as-is. This only
matters if you're setting up `.env` by hand or running the API outside the
provided compose files. See [`auth-setup.md`](auth-setup.md#the-ovid_env-requirement-required)
for the full `OVID_ENV`/OAuth reference, and for configuring OAuth providers.

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

- `OVID_ENV` — **required**, must be `production` here. The API refuses to
  boot without it (or with any value other than `development`/`production`).
  `docker-compose.prod.yml` already hardcodes `OVID_ENV=production`, so this
  only matters if you're assembling `.env` by hand for a non-standard deploy.
  Setting `production` also disables the localhost/loopback bypass in OAuth
  redirect validation.
- `OVID_DB_PASSWORD` — strong random password
- `OVID_SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- OAuth credentials for each provider (GitHub, Apple, Google) — see
  [`auth-setup.md`](auth-setup.md) for the authoritative per-provider setup reference

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

#### One-time dvdread1-* promotion cutover

The `900000000006_promote_dvdread1_primary` migration (part of ADR 0001's
staged libdvdread identity migration) promotes any disc that already
carries a `dvdread1-*` alias to have that value as its primary
fingerprint. Unlike a self-hosted mirror (which is already permanently
read-only and just picks this up via its normal update routine — see
[Promoting to dvdread1-* Primary](self-hosting.md#promoting-to-dvdread1-primary-one-time-cutover)
in the self-hosting runbook), **the canonical server accepts live writes
and genuinely needs write-quiesce for this migration** — it is not
already read-only the way a mirror is.

Use the same one-command wrapper, with the prod-specific compose files:

```bash
python scripts/promote_dvdread1.py -f docker-compose.yml -f docker-compose.prod.yml
```

This captures the server's current `OVID_MODE` (`canonical`), toggles it
to `mirror` (read-only) for the migration, and restores `canonical`
afterward — even if the migration step fails. As documented in the
self-hosting runbook, this **also briefly interrupts reads**, not just
writes, during each of the two `api` service restarts it performs — plan
for a short window of full API unavailability, not just a write-only
quiesce.

### 4. Start the Stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The production services start with container name prefixes (`ovid-prod-*`) and on separate ports from dev:

| Container | Host port | Internal port | Description |
|---|---|---|---|
| `ovid-prod-db` | — (not exposed) | 5432 | PostgreSQL 16 |
| `ovid-prod-redis` | — (not exposed) | 6379 | Redis 7 — shared rate-limit store |
| `ovid-prod-api` | 8100 | 8000 | FastAPI + Gunicorn (4 workers) |
| `ovid-prod-web` | 3100 | 3000 | Next.js production server |

The `redis` service is defined in `docker-compose.prod.yml` (and
`docker-compose.test.yml`) and is **internal-only** — it publishes no host port,
mirroring the prod `db`. It is ephemeral by design (`--save "" --appendonly no`,
no volume): rate-limit counters are short-window and disposable, so there is
nothing to persist across restarts. See **Rate Limiting Backend (Redis)** below
for why it exists and how it behaves.

### Rate Limiting Backend (Redis)

The prod and test stacks run the API under `gunicorn -w 4` (four workers). The
API rate limiter (`slowapi`) needs a **shared** counter store so a limit like
"100 requests/minute" is enforced across all four workers rather than per-worker.

- **Env-driven backend selection.** The limiter reads `REDIS_URL`:
  - **set** (prod/test: `redis://redis:6379/0`) → shared `RedisStorage`;
    counters are correct across every worker.
  - **unset** (single-worker dev/mirror/self-host) → per-worker `memory://`,
    which is correct only at one worker. This is why the base
    `docker-compose.yml` has no `redis` service and needs none.
- **When Redis is required.** Whenever `OVID_WORKERS` (or `WEB_CONCURRENCY`) > 1.
  On `memory://` each worker keeps an independent counter, so N workers inflate
  every rate limit up to Nx.
- **Fail-fast guard.** The API **refuses to boot** if `OVID_WORKERS` > 1 while
  `REDIS_URL` is unset — a loud startup `RuntimeError` instead of silently
  serving inflated limits. The prod/test compose files always pass
  `OVID_WORKERS=4` and `REDIS_URL` together, so a correct deploy never trips it;
  the guard exists to catch a misconfigured hand-rolled deploy.
- **Redis outage behavior (fail-open, self-healing — the documented decision).**
  On a Redis outage the limiter does **not** fail closed. It degrades to a
  bounded per-worker in-memory fallback (a single conservative global cap per
  worker while Redis is down) and automatically probes Redis and switches back
  when it recovers. This is a deliberate choice: OVID's rate limiting is
  **abuse-prevention over public/CC0 data, not an authorization boundary**, so a
  transient Redis blip must never take down the read-heavy, ARM-facing lookup
  path over a newly introduced dependency. Pure fail-open (dropping all
  protection) was rejected because the library ships this self-healing middle
  path for free. A per-route-type fail-open/fail-closed split is deferred
  (D-04) — revisit only if write-path abuse becomes a materially distinct threat.
- **Write-ceiling outage loosening.** The write ceiling (`AUTH_WRITE_LIMIT`,
  20/minute per account) is not exempt from the fallback above — during a
  Redis outage it also collapses to the shared `FALLBACK_LIMIT` (60/minute)
  **per worker**, so across the 4-worker prod/test stacks the effective write
  ceiling loosens to roughly 60/minute × running workers (≈240/minute) for the
  outage's duration. This is the same intentional fail-open-on-writes choice
  described above (per-route-type split deferred, D-04) — called out
  separately here because it's easy to miss that the write path is affected too.
- **Reverse-proxy IP requirement.** Per-IP unauthenticated rate limiting is
  only correct if `OVID_FORWARDED_ALLOW_IPS` is set to the actual proxy/
  Docker-gateway source the `api` container observes — see **Trusted proxy
  IP** under "Configure Reverse Proxy" below. Left at its default, every
  external visitor collapses into a single "client IP" bucket for both rate
  limiting and anti-Sybil IP-diversity checks.

If you ever expose Redis beyond the compose network, switch to `rediss://` with
AUTH; the current internal-only, no-published-port setup needs neither. A p95
≤ 500 ms load test against this exact Redis-backed multi-worker config is run by
the load-test harness (INFRA-03) — see `docs/OVID-technical-spec.md`.

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

**Trusted proxy IP (required for accurate rate limiting / anti-Sybil signals):** nginx above sets `X-Real-IP`/`X-Forwarded-For` to the real visitor's IP, but the API only honors those headers from a connection it trusts. Set `OVID_FORWARDED_ALLOW_IPS` in `.env` on holodeck to the IP address the `api` container actually observes as the connecting peer for the proxied request — this is passed to gunicorn as `--forwarded-allow-ips` (see `docker-compose.prod.yml`). With this reverse-proxy chain (redshirt → holodeck's published Docker port), that peer address is whatever Docker's bridge networking presents to the container, which is **not necessarily** `192.168.0.28` or redshirt's own IP — confirm the actual value from the API container's access log (or a temporary debug request) rather than assuming it. If `OVID_FORWARDED_ALLOW_IPS` is left at its default (`127.0.0.1`) and that never matches, the app silently falls back to treating every request as coming from the proxy hop — rate limiting and anti-Sybil IP-diversity (see `api/app/anti_sybil.py`) then see one constant "client IP" for all traffic instead of real visitor IPs.

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

## Staging (staging.oviddb.org / api.staging.oviddb.org — D-06 preview deploy)

Phase 7 (WEBUI-01) scopes "verifiably deployable + live" to a **staging preview URL**, not the public
`oviddb.org` apex. The public apex cutover, domain redirects (`.com`/`.net`), and DB seeding (500+ discs)
are **Phase 8** — see `.planning/phases/07-web-ui-production-readiness/07-CONTEXT.md` (D-06). Staging
exercises the real prod-shaped container + TLS + env-wiring path (not just a local build) before that
cutover, without exposing a near-empty catalog at the public domain (T-07-08-02).

### Chosen staging hosts

| Service | Host | Redshirt target | Notes |
|---|---|---|---|
| Web | `https://staging.oviddb.org` | `holodeck:3300` → container `:3000` | Its own `NEXT_PUBLIC_API_URL` build (Pitfall 3) |
| API | `https://api.staging.oviddb.org` | `holodeck:8300` → container `:8000` | Own DB — a near-empty catalog is expected pre-Phase-8 seeding |
| DB | not exposed | — | mirrors prod (`db.ports: !reset []`) |

The `x300` port bracket extends the existing dev (`x000`) / prod (`x100`) / test (`x200`) convention
without colliding with any stack that may be running simultaneously.

### Prerequisites (external host infra — not automatable)

1. **DNS:** add `staging.oviddb.org` and `api.staging.oviddb.org` A records in Cloudflare (proxied),
   pointing at redshirt (`64.98.89.233`) — same pattern as [Configure Cloudflare DNS](#7-configure-cloudflare-dns) above.
2. **TLS + routing:** extend the redshirt nginx vhost config (`docs/nginx-oviddb-vhosts.conf`) with
   `server_name staging.oviddb.org` / `server_name api.staging.oviddb.org` blocks proxying to
   `holodeck:3300` / `holodeck:8300` — same shape as the prod vhost blocks under
   [Configure Reverse Proxy](#5-configure-reverse-proxy-redshirt) above. The existing Let's Encrypt cert
   only covers `oviddb.org`/`api.oviddb.org`; extend it to a SAN cert covering the staging hostnames (or
   issue a separate cert).

### Required env wiring

1. **`CORS_ORIGINS` must include the staging web origin** (Pitfall 2 / threat T-07-08-01), or
   `_validate_web_redirect_uri` (`api/app/auth/routes.py:83-112`) fails **CLOSED** and every login — plus
   the D-04 account-merge redirect — 400s with `invalid_redirect_uri`. Set
   `CORS_ORIGINS=https://staging.oviddb.org` on the staging API (no wildcard, no comma-appended prod
   origin — see the commented example in `.env.example`).
2. **`NEXT_PUBLIC_API_URL` is a distinct BUILD-time arg** (Pitfall 3, `web/Dockerfile:12-15`) — it is
   baked into the client JS bundle at image-build time and is **not** runtime-overridable. The staging web
   image must be built with its own `--build-arg NEXT_PUBLIC_API_URL=https://api.staging.oviddb.org`,
   separate from the prod image's `https://api.oviddb.org`. The server-side `API_URL` env var (used for
   server-component/route-handler fetches) still points at the internal Docker service URL
   (`http://api:8000`), matching the prod/test pattern.
3. **`OVID_ENV` stays `production` on staging**, not a third value — the API only accepts
   `development`/`production` and refuses to boot otherwise (see `.env.example`). Staging is a public
   HTTPS deployment, so it needs the same `production` security posture as real prod (disables the
   localhost auth bypass); "staging" is a DNS/hostname distinction, not a third `OVID_ENV` value.
4. **Cross-origin session cookie for the add-provider flow (07-07 Option B).** Settings' "Link a
   provider" CTA does a credentialed `fetch(POST /v1/auth/link/{provider}, {credentials:"include"})` from
   the web origin to the API origin, then a top-level `window.location.assign()` navigation to the API's
   own `/login` route (`linkProvider`, `web/lib/api.ts`). This needs no staging-specific code change, but
   the mechanism only works because:
   - CORS already sends `Access-Control-Allow-Credentials: true` with the **exact** requesting origin
     (never `*`) — `CORSMiddleware` in `api/main.py` builds this from the same `CORS_ORIGINS` list, so
     wiring #1 above also satisfies this requirement.
   - The session cookie set by that fetch (`starlette.middleware.sessions.SessionMiddleware`, `api/main.py`)
     uses its default `SameSite=Lax`, `HttpOnly=True`, and no explicit `Domain` — scoped to the API host
     only, by design, since the OAuth round-trip returns the JWT via a `web_redirect_uri` query param, not
     a cookie the web origin reads, so no shared-domain cookie is needed. `SameSite=Lax` cookies ARE sent
     on the subsequent **top-level** cross-site navigation to the API's `/login` route (Lax only blocks
     cross-site use on subresource/fetch requests, not top-level GET navigations), so the round-trip
     succeeds without any `SameSite=None` or shared-`Domain` change.

### Build + run (local, uncommitted overlay — follows the prod/test pattern)

This repo does not ship a `docker-compose.staging.yml`: `docker-compose.prod.yml` and
`docker-compose.test.yml` both hardcode their own container names/ports/`NEXT_PUBLIC_API_URL` build arg
per environment, so staging needs the same per-environment treatment to avoid colliding with a
simultaneously-running prod stack (and to bake the *staging* API URL, not prod's, per Pitfall 3). Create a
local, gitignored `docker-compose.staging.yml` on the deploy host (mirrors `docker-compose.prod.yml`'s
shape, analogous to how `.env.test` is gitignored — do not commit it):

```yaml
# docker-compose.staging.yml — LOCAL ONLY, not committed. Merge with base:
#   docker compose -f docker-compose.yml -f docker-compose.staging.yml \
#     --env-file .env.staging -p ovid-staging up -d
name: ovid-staging

services:
  db:
    container_name: ovid-staging-db
    ports: !reset []

  redis:
    image: redis:7-alpine
    container_name: ovid-staging-redis
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    container_name: ovid-staging-api
    volumes: !reset []
    depends_on:
      redis:
        condition: service_healthy
    ports: !override
      - "8300:8000"
    command: >-
      gunicorn -w "${OVID_WORKERS:-4}" -k uvicorn.workers.UvicornWorker
      main:app --bind 0.0.0.0:8000
      --forwarded-allow-ips "${OVID_FORWARDED_ALLOW_IPS:-127.0.0.1}"
    environment:
      DATABASE_URL:          postgresql://${OVID_DB_USER:-ovid}:${OVID_DB_PASSWORD:-ovidlocal}@db:5432/${OVID_DB_NAME:-ovid}
      REDIS_URL:             redis://redis:6379/0
      OVID_WORKERS:          "${OVID_WORKERS:-4}"
      SECRET_KEY:            ${OVID_SECRET_KEY}
      OVID_MODE:             standalone
      OVID_ENV:              production
      LOG_LEVEL:             ${LOG_LEVEL:-info}
      CORS_ORIGINS:          ${CORS_ORIGINS:-https://staging.oviddb.org}
      OVID_API_URL:          https://api.staging.oviddb.org
      GITHUB_CLIENT_ID:      ${GITHUB_CLIENT_ID}
      GITHUB_CLIENT_SECRET:  ${GITHUB_CLIENT_SECRET}
      GOOGLE_CLIENT_ID:      ${GOOGLE_CLIENT_ID}
      GOOGLE_CLIENT_SECRET:  ${GOOGLE_CLIENT_SECRET}
      APPLE_CLIENT_ID:       ${APPLE_CLIENT_ID}
      APPLE_TEAM_ID:         ${APPLE_TEAM_ID}
      APPLE_KEY_ID:          ${APPLE_KEY_ID}
      APPLE_PRIVATE_KEY:     ${APPLE_PRIVATE_KEY}

  web:
    container_name: ovid-staging-web
    build:
      context: ./web
      args:
        NEXT_PUBLIC_API_URL: 'https://api.staging.oviddb.org'
    ports: !override
      - "3300:3000"
    environment:
      NEXT_PUBLIC_API_URL: https://api.staging.oviddb.org
      API_URL: http://api:8000
```

Then, from the repo root on holodeck:

```bash
cp .env.example .env.staging
# Edit .env.staging: OVID_DB_PASSWORD, OVID_SECRET_KEY, OAuth provider creds,
# and CORS_ORIGINS=https://staging.oviddb.org (see .env.example's staging example)

docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging -p ovid-staging build
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging -p ovid-staging up -d db
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging -p ovid-staging run --rm api alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.staging.yml --env-file .env.staging -p ovid-staging up -d
```

### Verified state (phase gate)

_Recorded by the 07-08 Task 2 phase gate — full `web` Vitest + `api` pytest suite results — see below._

### Human sign-off

The live TLS staging deploy + D-03 accessibility floor sign-off is a `checkpoint:human-verify` — see
`.planning/phases/07-web-ui-production-readiness/07-08-PLAN.md` Task 3 (search, disc detail + aliases,
submit, settings add/remove + merge redirect, keyboard operability/AA contrast in both themes).

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
