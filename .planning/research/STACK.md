# Technology Stack Additions for OVID 0.3.0

**Project:** OVID - Open Video Disc Identification Database
**Researched:** 2026-04-04
**Scope:** New dependencies and tools for 0.3.0 milestone (additive to existing stack)

## Recommended Additions

### Redis Infrastructure

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Redis 7 (Alpine) | 7.4+ | Shared rate limit storage, future session/cache backend | Industry standard, tiny footprint, Docker `redis:7-alpine` image is 12MB. Already referenced in slowapi docs as the supported backend. | HIGH |
| redis-py | >=5.0,<6.0 | Python Redis client | Canonical client. Ships with async support (`redis.asyncio`) built-in since 4.2 (merged aioredis). slowapi uses `limits` library which accepts `redis://` URI and handles the connection internally -- no direct redis-py import needed for rate limiting, but useful for future caching. | HIGH |

**Implementation:** The migration is a one-line change. In `api/app/rate_limit.py` line 68, change `storage_uri="memory://"` to `storage_uri=os.environ.get("REDIS_URL", "memory://")`. slowapi's underlying `limits` library handles Redis connection pooling automatically. Add `redis` service to `docker-compose.yml` with healthcheck. Fallback to memory in dev (when REDIS_URL unset) keeps local dev frictionless.

**Docker Compose addition:**
```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 3s
    retries: 5
  volumes:
    - ovid_redis:/data
```

Add `depends_on: redis: condition: service_healthy` to the `api` service. Add `REDIS_URL: redis://redis:6379/0` to the api environment.

### Rate Limiting

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| slowapi | >=0.1.9,<1.0 (keep existing) | Rate limiting decorators | Already integrated. The Redis backend is a config change, not a library swap. Replacing slowapi with something else adds risk for zero gain. The CONCERNS.md note about "slowapi deprecated in favor of built-in" is inaccurate -- FastAPI has no built-in rate limiter as of 2026. | HIGH |

**What NOT to use:**
- `fastapi-limiter`: Requires manual Redis connection management, less mature than slowapi, no dynamic limit support.
- `pyrate-limiter`: Good library but would require rewriting all `@limiter.limit()` decorators. Not worth the migration cost.
- Custom middleware: Reinventing what slowapi already does well. The token bucket / sliding window algorithms in `limits` (slowapi's backend) are battle-tested.

### Password Hashing (for P1 Email+Password Auth)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pwdlib[argon2,bcrypt] | >=0.2.0,<1.0 | Password hashing | FastAPI's official tutorial now recommends pwdlib over passlib. passlib is unmaintained (last release 2022, incompatible with recent bcrypt versions). pwdlib is from the FastAPI Users maintainer, supports Argon2 (OWASP recommended) and bcrypt. Clean API: `PasswordHash.hash()` / `PasswordHash.verify()`. | MEDIUM |
| argon2-cffi | (transitive via pwdlib) | Argon2id implementation | OWASP 2024 recommends Argon2id as the primary password hashing algorithm. Comes as a pwdlib optional dependency. | HIGH |

**What NOT to use:**
- `passlib`: Unmaintained since 2022. Breaks with bcrypt>=4.1. FastAPI docs are actively migrating away from it (PR #13917).
- Raw `bcrypt`: No algorithm versioning, no automatic rehashing on parameter changes. pwdlib handles this.

### CLI Binary Distribution

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PyPI + pip/pipx (primary) | N/A | Standard Python distribution | `pip install ovid-client` is the canonical path. Users who need disc fingerprinting already have Python (ARM is Python). PyPI is already in the 0.3.0 plan. System C libraries (libdvdread, libbluray) must be installed separately regardless of distribution method. | HIGH |
| Homebrew formula (Mac) | N/A | Mac binary distribution | Homebrew can declare `depends_on "libdvdread"` and `depends_on "libbluray"`, pulling C deps automatically. A formula that `pip install`s ovid-client into a virtualenv is the standard pattern for Python CLI tools with C deps. | MEDIUM |
| Platform install scripts | N/A | Linux binary distribution | Shell script that checks for / installs system deps via apt/dnf/pacman then pip-installs ovid-client. Simpler than fighting PyInstaller. | MEDIUM |

**What NOT to use:**
- `PyInstaller` / `Nuitka` / `cx_Freeze`: These bundle Python into a standalone binary but CANNOT bundle system C libraries (libdvdread, libbluray, libaacs) that ovid-client calls via subprocess (`dvdread` CLI) or ctypes. The C libraries must exist on the host system regardless. Freezing adds enormous build complexity (cross-compilation per platform, CI matrix for Mac ARM/x86 + Linux x86) for no actual benefit since the user still needs `brew install libdvdread` or `apt install libdvdread-dev`. PyPI + platform instructions is the right answer.
- `snapcraft` / `flatpak`: Overkill for a CLI tool. Would need to bundle libdvdread inside the snap, which has licensing implications and version pinning headaches.
- `conda`: Wrong audience. ARM/DataHoarder users use pip, not conda.

**Distribution strategy:** Publish to PyPI. Provide platform-specific install docs:
- **macOS:** `brew install libdvdread libbluray && pip install ovid-client`
- **Debian/Ubuntu:** `sudo apt install libdvdread-dev libbluray-dev && pip install ovid-client`
- **Fedora:** `sudo dnf install libdvdread-devel libbluray-devel && pip install ovid-client`
- **Arch:** `sudo pacman -S libdvdread libbluray && pip install ovid-client`

Optionally, provide a `scripts/install.sh` that detects the OS and runs the appropriate commands.

### Database Snapshot and Sync Hardening

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pg_dump (already available) | PostgreSQL 16 | Full database dump for snapshots | Already in the PostgreSQL container. The existing `dump_cc0.py` script produces NDJSON which is the right format for CC0 data consumers. For the actual snapshot hosting, pg_dump is overkill -- the NDJSON format is more portable and schema-independent. | HIGH |
| hashlib (stdlib) | Python 3.12 | SHA-256 integrity verification | Already used in `dump_cc0.py`. No external dependency needed. | HIGH |
| cron / systemd timer | N/A | Monthly dump scheduling | Run `dump_cc0.py` on a cron schedule on holodeck. Docker exec into the API container or run standalone with DATABASE_URL. Simpler than APScheduler or Celery for a monthly job. | HIGH |
| Caddy or nginx (static file serving) | N/A | Serve snapshots at snapshots.oviddb.org | Static file server for the .ndjson.gz dump files. Caddy preferred (auto-HTTPS, zero config). The snapshot endpoint already returns URL metadata -- just point it at the hosted file. | MEDIUM |

**Sync protocol hardening (no new deps, code changes only):**
- Add `X-OVID-Checksum` header to `/v1/sync/diff` responses (SHA-256 of response body) for integrity verification
- Add retry with exponential backoff in sync.py (partially exists, needs improvement for partial page failures)
- Add `--bootstrap` mode to sync.py that downloads the snapshot first, then catches up with diff (avoids syncing from seq 0 via paginated API)
- Add `last_sync_error` and `last_sync_success` keys to sync_state for observability
- Stream large snapshot responses instead of loading all discs into memory (use SQLAlchemy `yield_per()`)

**MusicBrainz reference model:** MusicBrainz publishes PostgreSQL dumps (mbdump.tar.bz2) and JSON dumps weekly. OVID's NDJSON approach is better for the use case -- mirrors don't need a full PostgreSQL instance, they just need to load records via the API. Monthly frequency is appropriate for current data volume (<500 discs).

### Load Testing

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| k6 | 1.0+ (Grafana k6) | Load testing FastAPI + PostgreSQL | JavaScript test scripts, built-in thresholds (p95 < 500ms), native HTTP/2, outputs to stdout/JSON/InfluxDB. Single Go binary -- no Python dependency conflicts. Better for CI integration than Locust (exit code reflects pass/fail based on thresholds). Docker image available: `grafana/k6`. | HIGH |

**Why k6 over Locust:**
- **CI-native:** k6 returns non-zero exit code when thresholds fail. Locust requires parsing output to determine pass/fail.
- **No Python conflicts:** Locust is Python and would share the Python environment with the API, risking dependency conflicts. k6 is a standalone Go binary.
- **Lower resource overhead:** k6 uses goroutines (thousands of VUs on a single core). Locust uses gevent which has higher per-VU memory.
- **Threshold syntax:** `http_req_duration{p(95)}<500` is declarative and CI-friendly.
- **Grafana ecosystem:** If OVID adds monitoring later, k6 results feed directly into Grafana dashboards.

**What NOT to use:**
- `Locust`: Good tool, but Python ecosystem overlap with the API creates dep management headaches. No built-in threshold pass/fail for CI.
- `JMeter`: XML-based, heavyweight, designed for QA teams not developers. Wrong tool for a small project.
- `Artillery`: Node.js based, YAML config is limiting for complex scenarios, commercial features gated.
- `wrk` / `hey`: HTTP benchmarking tools, not load testing tools. No scenario modeling, no thresholds, no ramp-up patterns.

**k6 test structure:**
```
tests/
  load/
    smoke.js          # 1 VU, 30s -- sanity check
    load.js           # 50 VU ramp, 5min -- target scenario
    stress.js         # 200 VU ramp, 10min -- breaking point
    helpers/
      auth.js         # JWT token generation helper
      disc.js         # Disc lookup/submit helpers
```

**Run via Docker Compose:**
```yaml
k6:
  image: grafana/k6
  profiles:
    - loadtest
  volumes:
    - ./tests/load:/scripts
  command: run /scripts/load.js
  environment:
    K6_API_BASE: http://api:8000
```

### Email Service (for P1 Email+Password Auth)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Resend or SMTP (via `email` stdlib + `aiosmtplib`) | N/A | Email verification, password reset | For a single-server deployment, SMTP via a transactional provider (Resend, Postmark, or even self-hosted Postfix) is simplest. `aiosmtplib` for async sending. Resend has a free tier (100 emails/day) and a Python SDK. Decision deferred to P1 implementation. | LOW |

### Supporting Libraries (new requirements.txt additions)

| Library | Version | Purpose | When to Add | Confidence |
|---------|---------|---------|-------------|------------|
| redis | >=5.0,<6.0 | Redis client (for future use beyond rate limiting) | Phase 1 (Redis migration) | HIGH |
| pwdlib[argon2,bcrypt] | >=0.2.0,<1.0 | Password hashing | P1 (email auth) | MEDIUM |
| aiosmtplib | >=2.0,<3.0 | Async SMTP client | P1 (email auth) | LOW |

**Note:** For the rate limiting migration specifically, `redis` pip package is NOT required as a direct dependency. slowapi's `limits` library auto-discovers and uses `redis` if `storage_uri` starts with `redis://`. However, adding it explicitly is good practice for version pinning and for direct Redis use later (caching, session store).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Rate limit backend | slowapi + Redis | fastapi-limiter | Would require rewriting all rate limit decorators; slowapi already works with Redis via config change |
| Rate limit backend | slowapi + Redis | Custom middleware | Reinventing sliding window / token bucket algorithms that `limits` already implements correctly |
| Password hashing | pwdlib (Argon2) | passlib (bcrypt) | passlib unmaintained since 2022, breaks with modern bcrypt versions |
| Binary distribution | PyPI + platform docs | PyInstaller | Cannot bundle system C libraries (libdvdread, libbluray); user still needs them installed |
| Binary distribution | PyPI + platform docs | Nuitka | Same C library limitation; adds massive build complexity for no benefit |
| Binary distribution | PyPI + platform docs | Homebrew tap only | Excludes Linux users; PyPI covers both platforms |
| Load testing | k6 | Locust | Python dep conflicts with API; no built-in CI threshold pass/fail |
| Load testing | k6 | Artillery | Commercial features gated; YAML config limiting for complex scenarios |
| Snapshot format | NDJSON (existing) | pg_dump SQL | NDJSON is schema-independent, loadable without PostgreSQL, matches MusicBrainz JSON dump model |
| Snapshot hosting | Static file server (Caddy) | S3/R2 object storage | Overkill for monthly dumps of <10MB; holodeck already has disk space |

## Installation Commands

### API additions (requirements.txt)
```bash
# Add to api/requirements.txt
redis>=5.0,<6.0

# P1 additions (when email auth is implemented)
pwdlib[argon2,bcrypt]>=0.2.0,<1.0
aiosmtplib>=2.0,<3.0
```

### Load testing (local install)
```bash
# macOS
brew install k6

# Linux (Debian/Ubuntu)
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D68
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6

# Docker (preferred for CI)
docker run --rm -i grafana/k6 run - <tests/load/smoke.js
```

### Docker Compose additions
```bash
# Redis is automatic via docker-compose up
# k6 via profile: docker compose --profile loadtest run k6
```

## Version Verification

| Package | Claimed Version | Verification Method | Verified |
|---------|----------------|---------------------|----------|
| Redis | 7.4+ | Docker Hub `redis:7-alpine` tag list | Training data (MEDIUM confidence) |
| redis-py | 5.x | PyPI page shows 5.2.1 as latest stable | Training data (MEDIUM confidence) |
| slowapi | 0.1.9+ | Already in requirements.txt, Redis support confirmed in official docs | HIGH |
| pwdlib | 0.2.x | PyPI, FastAPI PR #13917 references it | MEDIUM |
| k6 | 1.0+ | GitHub releases page shows 2026-02 release | Brave search (HIGH) |
| Caddy | 2.x | Standard, well-known | HIGH |

## Sources

- slowapi Redis examples: https://slowapi.readthedocs.io/en/latest/examples/
- slowapi GitHub: https://github.com/laurentS/slowapi
- redis-py docs: https://redis.readthedocs.io/en/stable/
- FastAPI security tutorial (pwdlib): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- pwdlib introduction: https://www.francoisvoron.com/blog/introducing-pwdlib-a-modern-password-hash-helper-for-python
- FastAPI pwdlib migration PR: https://github.com/fastapi/fastapi/pull/13917
- k6 documentation: https://grafana.com/docs/k6/latest/
- k6 releases: https://github.com/grafana/k6/releases
- MusicBrainz dump format: https://musicbrainz.org/doc/MusicBrainz_Database/Download
- PyInstaller docs (C library limitations): https://pyinstaller.org/en/stable/
