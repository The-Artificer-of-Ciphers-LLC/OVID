# Architecture Patterns

**Domain:** Disc identification database (MusicBrainz-style community registry)
**Researched:** 2026-04-04

## Current Architecture Baseline

OVID is a three-tier stateless architecture: Python CLI (fingerprinting + submission), FastAPI API (disc registry + auth + sync), Next.js web UI (search + submit + settings). PostgreSQL is the sole data store. Docker Compose orchestrates all services.

The API is stateless by design -- no session affinity, no in-process caches that affect correctness. The one exception is rate limiting, which uses `storage_uri="memory://"` in slowapi, making it per-worker and broken under gunicorn's 4-worker production config. This is the primary driver for adding Redis.

---

## Recommended Architecture for 0.3.0

### Component Map

```
                    Internet
                       |
              [Reverse Proxy / redshirt]
                  /          \
            :8100              :3100
              |                  |
         +--------+        +--------+
         |  API   |        |  Web   |
         | FastAPI|        | Next.js|
         +--------+        +--------+
           |    |               |
           |    |          (API_URL=http://api:8000)
           |    |
      +----+  +----+
      |  PG  | | Redis |
      +------+ +-------+

         +----------+
         | CLI      |
         | ovid-cli | -----> API (https://api.oviddb.org)
         +----------+
              |
         [local disc]
```

### Component Boundaries

| Component | Responsibility | Communicates With | Stateless? |
|-----------|---------------|-------------------|------------|
| **API (FastAPI)** | Disc CRUD, auth, sync feed, rate limiting | PostgreSQL (ORM), Redis (rate limits) | Yes |
| **Web UI (Next.js)** | Search, submit, settings, OAuth callbacks | API (HTTP) | Yes |
| **CLI (ovid-client)** | Fingerprint, lookup, submit, scan modes | Local disc (libdvdread/libbluray), API (HTTP), TMDB (HTTP) | Yes |
| **PostgreSQL** | Disc registry, user accounts, sync state, edit history | API only | N/A |
| **Redis** | Rate limit counters, future: response cache | API only | N/A (ephemeral) |
| **Sync daemon** | Mirror polling loop | API (sync endpoints), PostgreSQL (local writes) | Yes (single instance) |

### Key Principle: Redis is Infrastructure, Not Architecture

Redis enters the stack as a **backing service for rate limiting** -- nothing more in 0.3.0. Do not use it for session storage, job queues, pub/sub, or caching in this milestone. The API must remain functional (degraded, not broken) if Redis is unavailable. This means:

- Rate limiting falls back to permissive (allow all) if Redis connection fails at startup or drops mid-request
- No feature logic depends on Redis state
- Redis is optional in dev (`docker-compose.yml`) -- the `memory://` backend still works for single-worker dev mode
- Redis is required in prod (`docker-compose.prod.yml`) where gunicorn runs multiple workers

---

## Architecture Evolution: Component by Component

### 1. Redis Integration for Rate Limiting

**Current state:** `slowapi` with `storage_uri="memory://"` -- each gunicorn worker has independent counters, so effective rate limits are 4x the nominal value in production.

**Target state:** `slowapi` with `storage_uri="redis://redis:6379/0"` in production.

**How slowapi handles Redis:** slowapi wraps the `limits` library (pypi: `limits`). The `limits` library supports Redis natively via `storage_uri="redis://host:port/db"`. It requires `redis` (or `redis[hiredis]`) as a pip dependency. No code changes to rate_limit.py beyond swapping the URI.

**Implementation pattern:**

```python
# rate_limit.py — change one line
import os

_RATE_LIMIT_STORAGE = os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri=_RATE_LIMIT_STORAGE,
)
```

**Docker Compose addition:**

```yaml
# docker-compose.yml (dev — optional, memory:// is fine)
redis:
  image: redis:7-alpine
  restart: unless-stopped
  ports:
    - "6379:6379"
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 5

# docker-compose.prod.yml (required)
redis:
  container_name: ovid-prod-redis
  ports: !reset []
  volumes:
    - ovid_redis:/data
  command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
```

**New pip dependency:** `redis[hiredis]>=5.0,<6.0` (hiredis for C-optimized parser).

**Graceful degradation:** slowapi raises `ConnectionError` on Redis failure. Wrap the limiter initialization to catch connection failures and log a warning. In production, a Redis outage should not take down the API -- it should permit all requests and log alerts.

**Confidence:** HIGH -- slowapi/limits Redis support is well-documented and the existing code already has a comment about this upgrade path.

### 2. Self-Hosted Sync Protocol Hardening

**Current state:** Three sync endpoints exist (`/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot`). The diff endpoint paginates by seq_num. The snapshot endpoint reads metadata from the `sync_state` table but no snapshot generation tooling exists yet.

**Architecture additions needed:**

**A. Snapshot Generation (offline script)**

A new script `scripts/generate_snapshot.py` that:
1. Queries all discs with seq_num IS NOT NULL, ordered by seq_num
2. Serializes to NDJSON (one JSON object per line -- same schema as sync diff records)
3. Compresses with gzip
4. Computes SHA-256 of the compressed file
5. Uploads to `snapshots.oviddb.org` (static file hosting -- S3, or a simple nginx container serving a volume)
6. Updates `sync_state` table with URL, seq, size, record_count, sha256

**Why NDJSON:** Streaming-friendly, each line is independently parseable, no need to load entire file into memory. Same format MusicBrainz uses for data dumps.

**B. Diff Resumption (mirror-side robustness)**

The sync daemon (`scripts/sync.py`) needs:
- Persist `last_applied_seq` in local `sync_state` table after each batch
- On startup, read `last_applied_seq` and resume from there
- If `last_applied_seq` is 0 and a snapshot exists, download snapshot first, then diff from snapshot's seq
- Implement retry with exponential backoff on HTTP failures (max 5 retries per batch)

**C. Integrity Verification**

- Snapshot: verify SHA-256 after download, before applying
- Diff: the API already returns seq_num per record -- the mirror should verify that received seq_nums are monotonically increasing and contiguous within each batch
- Add an optional `GET /v1/sync/verify?seq=N` endpoint that returns the SHA-256 of all records up to seq N (computed on-the-fly or cached). Mirrors can spot-check their local state.

**Data flow for a new mirror:**

```
Mirror starts (empty DB)
  |
  GET /v1/sync/snapshot
  |
  Download .ndjson.gz from snapshot URL
  |
  Verify SHA-256
  |
  Bulk-insert all records (seq 1..snapshot_seq)
  |
  Store last_applied_seq = snapshot_seq
  |
  Loop:
    GET /v1/sync/head -> current_seq
    if current_seq > last_applied_seq:
      GET /v1/sync/diff?since=last_applied_seq&limit=1000
      Apply records
      last_applied_seq = next_since
    else:
      Sleep SYNC_INTERVAL_MINUTES
```

**Confidence:** MEDIUM -- the sync feed architecture is sound, but snapshot generation and hosting infrastructure needs implementation from scratch. The NDJSON format and SHA-256 verification are standard patterns.

### 3. CLI Scanner Architecture

**Current state:** The CLI has three commands: `fingerprint`, `lookup`, `submit`. The `submit` command is a wizard that requires interactive input at every step (TMDB search, edition name, disc number).

**Target state:** A new `scan` command with three modes that compose from shared building blocks.

**Architecture: Pipeline Pattern**

The scan operation is a pipeline with optional stages:

```
[Mount/Open Disc] -> [Fingerprint] -> [API Lookup] -> [Enrich] -> [Submit]
     ^                                     |              ^
     |                                     |              |
  required                           branch point     optional
                                     (hit vs miss)
```

**Mode composition:**

| Stage | `scan` (default) | `scan --wizard` | `scan --batch` |
|-------|-------------------|-----------------|----------------|
| Open disc | Auto-detect drive/path | Auto-detect drive/path | Iterate folder of ISOs |
| Fingerprint | Always | Always | Always |
| API lookup | Always | Always | Always |
| On hit | Print result, exit | Print result, exit | Skip, next ISO |
| On miss: TMDB | Skip (auto-submit fingerprint-only via `/v1/disc/register`) | Interactive TMDB search | Auto-search by filename heuristic |
| On miss: Edition | Skip | Interactive prompt | Skip (default edition) |
| On miss: Submit | `POST /v1/disc/register` (fingerprint + structure only) | `POST /v1/disc` (full metadata) | `POST /v1/disc/register` per miss |
| Auth required | Yes (JWT) | Yes (JWT) | Yes (JWT) |

**Implementation: Command Factory, not Inheritance**

```python
@main.command()
@click.argument("path", default=None, required=False)
@click.option("--wizard", is_flag=True, help="Guided submission with TMDB matching")
@click.option("--batch", type=click.Path(exists=True), help="Scan folder of ISOs")
@click.option("--api-url", default=None)
@click.option("--token", default=None)
def scan(path, wizard, batch, api_url, token):
    """Insert disc, fingerprint, check OVID, auto-submit if miss."""
    client = OVIDClient(base_url=api_url, token=token)

    if batch:
        _scan_batch(batch, client)
    elif wizard:
        _scan_wizard(path or _detect_drive(), client)
    else:
        _scan_auto(path or _detect_drive(), client)
```

**Shared building blocks** (functions, not classes):
- `_open_disc(path)` -- already exists
- `_detect_drive()` -- new: find mounted optical drive (platform-specific)
- `_fingerprint_and_lookup(disc, client)` -- fingerprint + API call, returns (disc, hit_or_none)
- `_auto_submit_register(disc, client)` -- POST /v1/disc/register with structure
- `_wizard_submit(disc, client)` -- existing submit wizard flow, extracted from `submit` command

**Batch mode specifics:**
- Walk directory for `.iso` files (and optionally `VIDEO_TS`/`BDMV` folders)
- Process each sequentially (disc I/O is the bottleneck, not CPU)
- Print summary table at end: N scanned, N hits, N submitted, N errors
- Continue on error (log and skip, don't abort batch)

**Drive detection** (`_detect_drive()`):
- Linux: check `/dev/sr0`, `/dev/cdrom`, or parse `/proc/sys/dev/cdrom/info`
- macOS: parse `diskutil list` output for optical media
- Falls back to error message asking user to provide path

**Confidence:** HIGH -- the existing CLI code is well-structured. The scan command is a composition of existing primitives with a new entry point. The `/v1/disc/register` endpoint already exists.

### 4. Multi-Disc Set API/UI Surface

**Current state:** `disc_sets` table exists with `release_id`, `edition_name`, `total_discs`, `seq_num`. Discs have `disc_set_id` FK. No API routes or UI for sets.

**Architecture additions:**

**API routes (new file: `api/app/routes/sets.py`):**

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/v1/set` | POST | Required | Create a disc set (release_id, edition_name, total_discs) |
| `/v1/set/{set_id}` | GET | None | Return set with all member discs (eager-loaded) |

**Data flow for set creation:**
1. User creates a set (links to a Release, names the edition, declares disc count)
2. User submits individual discs with `disc_set_id` in the payload
3. `GET /v1/disc/{fingerprint}` response includes `disc_set` object with sibling fingerprints

**Sync feed impact:**
- Add `seq_num` column to `disc_sets` (already exists in model)
- Include disc sets in sync diff/snapshot records
- New sync record type: `"type": "disc_set"` alongside existing `"type": "disc"`

**No breaking changes:** The `disc_set_id` field on disc submission is optional. Existing clients that don't send it continue working.

**Confidence:** HIGH -- the data model is already in place. This is API route + schema work.

### 5. Chapter Name Data Model

**New table: `disc_chapters`**

```sql
CREATE TABLE disc_chapters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disc_title_id UUID NOT NULL REFERENCES disc_titles(id) ON DELETE CASCADE,
    chapter_index SMALLINT NOT NULL,
    name VARCHAR(200),
    start_time_secs INTEGER,
    UNIQUE (disc_title_id, chapter_index)
);
CREATE INDEX idx_disc_chapters_title ON disc_chapters(disc_title_id);
```

**ORM model:** `DiscChapter` with relationship to `DiscTitle.chapters` (one-to-many, cascade delete).

**Integration points:**
- `POST /v1/disc` schema gains optional `chapters` array per title
- `GET /v1/disc/{fingerprint}` response includes chapters per title
- Sync diff/snapshot includes chapters nested under titles
- Web UI disc detail page renders chapter names
- Web UI submit form has optional chapter entry
- CLI wizard has optional chapter name step

**Build dependency:** Chapter data depends on `disc_titles` existing. No dependency on disc sets or auth changes.

**Confidence:** HIGH -- straightforward schema addition following the existing DiscTitle -> DiscTrack pattern.

### 6. Email + Password Auth Alongside OAuth

**Current state:** OAuth-only via authlib. Users table has no `password_hash` column (explicitly removed per design decision R005). The `user_upsert()` function creates users via OAuth provider links.

**Architecture for adding email auth without breaking OAuth:**

**Schema change:**
```sql
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(255);
ALTER TABLE users ADD COLUMN email_verification_expires TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(255);
ALTER TABLE users ADD COLUMN password_reset_expires TIMESTAMP WITH TIME ZONE;
```

All five columns are nullable -- existing OAuth users have NULL password_hash and continue working unchanged.

**New auth module: `api/app/auth/email.py`**

Handles:
- Registration: create User with password_hash (bcrypt via `passlib[bcrypt]`), send verification email
- Login: verify email + password, return JWT (same `create_access_token()` as OAuth)
- Password reset: generate token, send email, verify token + set new password
- Email verification: verify token, set `email_verified=True`

**Email sending:** Use `aiosmtplib` for async SMTP. Configure via environment variables (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`). For dev, use `SMTP_HOST=mailhog` with a MailHog container.

**New API routes (added to auth_router):**

| Route | Method | Purpose |
|-------|--------|---------|
| `/v1/auth/register` | POST | Email + password registration |
| `/v1/auth/login` | POST | Email + password login -> JWT |
| `/v1/auth/verify-email` | POST | Verify email with token |
| `/v1/auth/forgot-password` | POST | Request password reset email |
| `/v1/auth/reset-password` | POST | Reset password with token |

**Convergence with OAuth:** Both paths produce the same JWT. The `get_current_user` dependency (`auth/deps.py`) already works purely from JWTs -- it doesn't care how the JWT was created. No changes needed to any protected route.

**Account linking:** An OAuth user who later adds email+password gets a `password_hash` set on their existing User row. An email user who later links OAuth gets a UserOAuthLink row. Same user, same JWT, same permissions.

**Confidence:** MEDIUM -- the architecture is clean, but email sending infrastructure (SMTP config, verification flows, rate limiting registration) adds operational surface area. This is correctly marked P1 (post-beta).

### 7. Load Testing Infrastructure

**Tool: k6** (over Locust). k6 runs as a standalone binary, writes results to stdout or InfluxDB, and doesn't require a Python environment that might conflict with the API's.

**Architecture:**
- New directory: `tests/load/`
- k6 scripts targeting key endpoints: fingerprint lookup (GET), disc submission (POST), sync diff pagination (GET), auth callback simulation
- Docker Compose profile `--profile loadtest` adds k6 container pointed at the API
- Threshold: p95 <= 500ms for all read endpoints under 100 concurrent users

**No architectural impact** on the API itself -- load testing is external observation.

**Confidence:** HIGH -- standard practice, no design ambiguity.

---

## Patterns to Follow

### Pattern 1: Environment-Driven Configuration
**What:** All infrastructure connection strings come from environment variables with sensible defaults.
**When:** Any new backing service (Redis, SMTP).
**Why:** Keeps dev simple (`memory://` for rate limiting, no Redis needed) while prod gets proper shared state.

```python
_RATE_LIMIT_STORAGE = os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://")
_SMTP_HOST = os.environ.get("SMTP_HOST", "")  # Empty = email disabled
```

### Pattern 2: Optional Feature Gates
**What:** Features that require infrastructure (email auth needs SMTP, rate limiting needs Redis) degrade gracefully when infrastructure is absent.
**When:** Adding Redis, SMTP, or any external dependency.
**Why:** A self-hosted mirror operator shouldn't need Redis or SMTP configured.

### Pattern 3: Sync Feed Inclusion for New Entities
**What:** Every new table that holds user-contributed data gets a `seq_num` column and inclusion in the sync diff/snapshot format.
**When:** Adding `disc_chapters`, surfacing `disc_sets`.
**Why:** Self-hosted mirrors must receive all data. Missing a table from sync means mirrors have incomplete data forever.

### Pattern 4: CLI Command Composition via Shared Functions
**What:** CLI commands share building-block functions rather than inheriting from base classes. Each mode is a thin orchestrator calling shared functions.
**When:** Adding `scan` command with multiple modes.
**Why:** Click commands don't compose well via OOP. Function composition keeps each mode readable and testable.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Redis for Everything
**What:** Using Redis for session storage, caching, job queues, and rate limiting simultaneously.
**Why bad:** Creates a hard dependency on Redis uptime. A Redis outage takes down unrelated features. Operational complexity grows nonlinearly.
**Instead:** Redis is for rate limiting only in 0.3.0. If caching is needed later, evaluate whether PostgreSQL's built-in caching (shared_buffers) or application-level HTTP caching (ETags) suffice first.

### Anti-Pattern 2: Separate Auth Systems with Separate User Tables
**What:** Creating a parallel `email_users` table or separate auth middleware for email auth.
**Why bad:** Two user populations that can't link accounts. Permissions diverge. Every protected route needs to handle both.
**Instead:** One `users` table, one JWT format, one `get_current_user` dependency. Email auth adds columns to the existing User model and new routes to the existing auth_router.

### Anti-Pattern 3: Sync Protocol Versioning via URL
**What:** `/v2/sync/diff` when the sync format changes.
**Why bad:** Mirrors need to support multiple protocol versions. Upgrade coordination becomes a distributed systems problem.
**Instead:** The sync diff record is extensible -- new fields are additive. Old mirrors ignore fields they don't recognize. Only break the URL if the pagination model changes fundamentally.

### Anti-Pattern 4: Interactive-Only CLI
**What:** Making every CLI operation require user input (prompts, confirmations).
**Why bad:** Breaks automation (ARM integration, cron jobs, batch processing).
**Instead:** Default `scan` mode requires zero interaction. `--wizard` is opt-in interactive. All commands accept `--yes` or equivalent for CI/automation contexts.

---

## Data Flow Summary

### Write Path (disc submission)

```
User (CLI/Web)
  |
  POST /v1/disc (JWT auth, Redis rate limit)
  |
  Pydantic validation
  |
  SQLAlchemy transaction:
    - Find-or-create Release (by tmdb_id or title+year)
    - Create Disc (fingerprint, format, status=unverified)
    - Create DiscRelease join
    - Create DiscTitle rows (per title)
    - Create DiscTrack rows (per track per title)
    - [NEW] Create DiscChapter rows (per chapter per title, optional)
    - [NEW] Link to DiscSet (if disc_set_id provided)
    - next_seq() -> stamp all rows
  |
  Commit
  |
  Return 201 {fingerprint, status}
```

### Read Path (disc lookup)

```
User (CLI/Web/ARM)
  |
  GET /v1/disc/{fingerprint} (Redis rate limit, no auth)
  |
  SQLAlchemy query with eager-load:
    Disc -> DiscTitle -> DiscTrack
                      -> [NEW] DiscChapter
         -> Release (via disc_releases)
         -> [NEW] DiscSet (if member, with sibling fingerprints)
  |
  Return 200 {disc structure}
```

### Mirror Sync Path (enhanced for 0.3.0)

```
Mirror daemon starts
  |
  Read local sync_state.last_applied_seq
  |
  If last_applied_seq == 0:
    GET /v1/sync/snapshot
    Download .ndjson.gz
    Verify SHA-256
    Bulk insert
    Store last_applied_seq = snapshot_seq
  |
  Loop:
    GET /v1/sync/head -> {seq, timestamp}
    |
    If seq > last_applied_seq:
      While has_more:
        GET /v1/sync/diff?since=last_applied_seq&limit=1000
        Apply records (disc + [NEW] disc_set + [NEW] chapters)
        last_applied_seq = next_since
        Persist to sync_state
    |
    Sleep SYNC_INTERVAL_MINUTES
```

---

## Suggested Build Order (Dependency-Driven)

The components have clear dependencies that dictate build sequence:

```
Phase 1: Redis + Rate Limit Migration
  (no dependencies, unblocks load testing)
      |
Phase 2: Data Model (chapters + sets API surface)
  (no dependencies, pure additive schema + routes)
      |
Phase 3: Sync Protocol Hardening
  (depends on: chapter/set data model finalized, so sync includes them)
      |
Phase 4: CLI Scanner
  (depends on: /v1/disc/register existing [done], stable API)
      |
Phase 5: Email Auth
  (P1, depends on: nothing, but adds SMTP infrastructure)
      |
Phase 6: Load Testing
  (depends on: Redis in place, all new endpoints exist)
```

**Rationale for ordering:**
- Redis first because it is infrastructure with zero feature dependencies and unblocks accurate load testing later
- Data model (chapters, sets) before sync hardening because sync must include all entity types to avoid a second sync format change
- CLI scanner can be built in parallel with sync hardening since it uses existing API endpoints
- Email auth is explicitly P1 (post-beta) so it goes late
- Load testing validates everything, so it goes last

---

## Scalability Considerations

| Concern | Now (<500 discs) | At 10K discs | At 100K discs |
|---------|-------------------|--------------|---------------|
| Fingerprint lookup | Index scan, sub-ms | Index scan, sub-ms | Index scan, sub-ms |
| Sync diff pagination | Sequential scan on seq_num index | Same, fast | Consider snapshot-first for new mirrors |
| Rate limiting (Redis) | Single Redis instance | Single Redis instance | Still single instance (rate limit data is tiny) |
| Snapshot generation | Seconds | Minutes | Add incremental snapshots (delta since last snapshot) |
| Database size | ~10MB | ~500MB | ~5GB, consider read replicas if API load warrants |
| API workers | 4 (gunicorn) | 4 | 8-16, still stateless |

At OVID's current and projected scale (target: 500 discs for launch, optimistically 10K within a year), a single PostgreSQL instance and a single Redis instance handle all load. Horizontal scaling of the API tier is already supported by the stateless design. No architectural changes are needed for the foreseeable future.

---

## Sources

- OVID codebase: `api/app/rate_limit.py` (slowapi config with `memory://` storage and Redis upgrade comment)
- OVID codebase: `api/app/sync.py` and `api/app/routes/sync.py` (sync feed implementation)
- OVID codebase: `api/app/auth/` (OAuth flow, JWT creation, user upsert)
- OVID codebase: `api/app/models.py` (full ORM schema including DiscSet with seq_num)
- OVID codebase: `docker-compose.yml` and `docker-compose.prod.yml` (deployment topology)
- slowapi documentation: `storage_uri` parameter accepts any URI supported by the `limits` library, including `redis://` (HIGH confidence -- this is documented in the existing code comments)
- `limits` library: Redis storage backend via `redis://host:port/db` URI scheme (HIGH confidence -- standard pattern)

*Architecture analysis: 2026-04-04*
