# Self-Hosting OVID

Run your own OVID mirror node on a home NAS or server. A mirror keeps a local read-only copy of the community database and serves disc lookups to [ARM](arm-integration.md) or other tools — no outbound internet calls required during ripping.

---

## How Mirror Mode Works

OVID supports three operating modes:

| Mode | Local writes | Syncs from canonical | Description |
|------|:------------:|:--------------------:|-------------|
| `standalone` | ✅ | ❌ | Fully private instance — no connection to the community database. Good for development. |
| `mirror` | ❌ | ✅ | Read-only copy that syncs from `api.oviddb.org` on a schedule. **Best for self-hosting.** |
| `federated` | ✅ | ✅ | *(Planned for Phase 2)* Bi-directional sync with upstream submissions. |

In **mirror** mode:

- A sync sidecar container polls the canonical OVID server for changes on a configurable interval (default: every 60 minutes).
- All write endpoints (`POST`, `PUT`, `DELETE`, `PATCH`) return `405 Method Not Allowed`.
- Read endpoints (`GET /v1/disc/{fingerprint}`, `GET /v1/search`, etc.) work normally against your local database.

---

## Prerequisites

| Requirement | Minimum version | Notes |
|-------------|-----------------|-------|
| [Docker](https://docs.docker.com/get-docker/) | 24.0+ | Docker Desktop or Docker Engine |
| Docker Compose | v2.0+ | Included with Docker Desktop; install separately on Linux |
| Git | any | To clone the repository |
| Disk space | ~1 GB | Database grows slowly (~10 KB per disc record) |

Mirror mode is lightweight — a Raspberry Pi 4 or any NAS with Docker support is sufficient.

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID
cp .env.example .env
```

### 2. Configure for mirror mode

Edit `.env` and set the following:

```bash
# Switch from standalone (default) to mirror
OVID_MODE=mirror

# Canonical server to sync from (default is correct for most users)
SYNC_SOURCE_URL=https://api.oviddb.org

# How often to pull updates (in minutes)
SYNC_INTERVAL_MINUTES=60

# Database credentials (change the password for security)
OVID_DB_PASSWORD=change_me_to_something_secure
```

### 3. Start the mirror stack

```bash
docker compose --profile mirror up -d
```

The `--profile mirror` flag starts the sync sidecar alongside the API and database. This launches three services:

| Service | Port | Description |
|---------|------|-------------|
| `db` | 5432 | PostgreSQL 16 database |
| `api` | 8000 | OVID API server (read-only in mirror mode) |
| `sync` | — | Background sync worker (no exposed port) |

### 4. Run database migrations

```bash
docker compose exec api alembic upgrade head
```

### 5. Verify

```bash
# Health check
curl http://localhost:8000/health
# → {"status":"ok"}

# Check sync logs
docker compose logs sync
```

The first sync may take a few minutes depending on the size of the community database. Subsequent syncs only pull changes since the last successful run.

---

## Configuration Reference

All mirror-relevant environment variables from `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OVID_MODE` | `standalone` | Set to `mirror` for self-hosting |
| `SYNC_SOURCE_URL` | `https://api.oviddb.org` | Canonical server URL to sync from |
| `SYNC_INTERVAL_MINUTES` | `60` | Minutes between sync polls |
| `OVID_DB_NAME` | `ovid` | PostgreSQL database name |
| `OVID_DB_USER` | `ovid` | PostgreSQL username |
| `OVID_DB_PASSWORD` | `change_me_in_production` | PostgreSQL password — **change this** |
| `LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`) |

OAuth variables (`GITHUB_CLIENT_ID`, `APPLE_CLIENT_ID`, etc.) are **not required** for mirror mode — authentication is only needed on instances that accept submissions.

---

## Using with ARM

Once your mirror is running, point ARM at your local OVID instance instead of the public API. This gives you:

- **Offline ripping** — no internet required during disc identification
- **Faster lookups** — local network latency instead of round-trip to `api.oviddb.org`
- **Privacy** — your disc lookups never leave your network

See the [ARM Integration Guide](arm-integration.md) for configuration details. The key settings are:

```
OVID_ENABLED=true
OVID_API_URL=http://<your-server-ip>:8000
```

Replace `<your-server-ip>` with the IP address or hostname of the machine running your OVID mirror.

---

## Updating

Pull the latest changes and restart:

```bash
cd OVID
git pull
docker compose --profile mirror down
docker compose --profile mirror up -d --build
docker compose exec api alembic upgrade head
```

The sync worker will automatically pick up any schema changes after the migration runs.

---

## Data Export (CC0 Dump)

OVID's community-contributed disc metadata is licensed under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) — you can export the entire database as NDJSON:

```bash
# Export all disc records
python scripts/dump_cc0.py --output ovid-dump.ndjson.gz

# Inspect the output
zcat ovid-dump.ndjson.gz | head -5
```

You can also fetch a snapshot via the API:

```bash
curl http://localhost:8000/v1/sync/snapshot
```

---

## Troubleshooting

### Sync not running

Verify the sync container is up:

```bash
docker compose --profile mirror ps
```

If the `sync` service is missing, make sure you included `--profile mirror` in your `docker compose up` command. Without it, only the `db` and `api` services start.

### Sync errors in logs

```bash
docker compose logs sync --tail 50
```

Common issues:

- **Connection refused to `SYNC_SOURCE_URL`** — check that the canonical server is reachable from your network. Verify with `curl https://api.oviddb.org/health`.
- **Database connection errors** — ensure the `db` container is healthy: `docker compose ps`. If it's restarting, check `OVID_DB_PASSWORD` matches between your `.env` and the volume's initial password (delete the volume to reset: `docker compose down -v`).

### Write endpoints return 405

This is expected in mirror mode. All `POST`, `PUT`, `DELETE`, and `PATCH` requests are rejected. To submit discs, use the canonical server at `https://api.oviddb.org` or switch to `OVID_MODE=standalone`.

### Database connection issues

If the API can't reach PostgreSQL:

1. Check the `db` healthcheck: `docker compose ps`
2. Verify `OVID_DB_PASSWORD` in `.env` matches the password the database was initialised with
3. If the password was changed after first run, reset the volume: `docker compose down -v` (**⚠️ destroys data** — the sync worker will re-populate from canonical on next run)

### Checking sync progress

```bash
# View recent sync activity
docker compose logs sync --tail 20

# Check current database state
docker compose exec db psql -U ovid -c "SELECT COUNT(*) FROM discs;"
```

### Port conflicts

If port 8000 or 5432 is already in use, edit `docker-compose.yml` to change the host port mappings:

```yaml
# Change API from 8000 to 8080
ports:
  - "8080:8000"
```

Then update your ARM configuration to point to the new port.

---

## System Requirements

| Use case | CPU | RAM | Disk | Notes |
|----------|-----|-----|------|-------|
| Small mirror (<10k discs) | 1 core | 512 MB | 500 MB | Raspberry Pi 4 works |
| Medium mirror (<100k discs) | 2 cores | 1 GB | 2 GB | Any modern NAS |
| Full mirror | 2 cores | 2 GB | 5 GB | Commodity hardware |

The database grows at approximately 10 KB per disc record. At 100,000 discs the database is roughly 1 GB.

---

## Next Steps

- [ARM Integration Guide](arm-integration.md) — configure ARM to use your local mirror
- [Docker Quick-Start](docker-quickstart.md) — standalone development setup
- [API Reference](api-reference.md) — full endpoint documentation
- [Contributing](contributing.md) — help grow the community database
