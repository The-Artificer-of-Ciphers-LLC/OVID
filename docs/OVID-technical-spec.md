# OVID — Open Video Disc Identification Database
## Technical Specification · v0.2 Draft

---

## 1. System Overview

OVID is a four-part system:

1. **`ovid-client`** — A Python library (with a CLI) that reads a mounted DVD or Blu-ray disc and generates a standardized disc fingerprint string.
2. **OVID API Server** — A REST API that accepts fingerprint lookups and disc submissions, backed by a relational database.
3. **OVID Web UI** — A browser-based interface for searching, browsing, and submitting disc entries. Also serves as the human review and moderation layer.
4. **Self-Hosted Node (optional)** — A full OVID stack that anyone can run locally or on a home server. Self-hosted nodes sync their database from the canonical server via a diff/patch feed, so they stay up to date without internet lookups on every disc rip.

### Deployment Topologies

**Topology A — Cloud lookup (default)**
Every disc lookup goes out to `api.oviddb.org`. Simple, no local setup required.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Computer                              │
│                                                                      │
│   ┌──────────────┐                            ┌──────────────────┐  │
│   │  ARM / other │◀──── metadata JSON ────────│   ovid-client    │  │
│   │  rip tool    │                            │   (Python lib)   │  │
│   └──────────────┘                            └────────┬─────────┘  │
│                                                        │            │
└────────────────────────────────────────────────────────┼────────────┘
                                                         │ HTTPS REST
                                              ┌──────────▼──────────┐
                                              │  CANONICAL SERVER    │
                                              │  api.oviddb.org      │
                                              │  (FastAPI + PG)      │
                                              └─────────────────────┘
```

**Topology B — Self-hosted node (offline-capable)**
A full OVID stack runs on the user's home network (e.g., a NAS or Raspberry Pi). It syncs from the canonical server on a schedule and serves all lookups locally — no internet required during ripping.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     User's Home Network                              │
│                                                                      │
│  ┌──────────────┐                           ┌──────────────────┐    │
│  │  ARM / other │◀─── metadata JSON ────────│   ovid-client    │    │
│  │  rip tool    │                           │  (local API URL) │    │
│  └──────────────┘                           └────────┬─────────┘    │
│                                                      │              │
│                                           ┌──────────▼──────────┐   │
│                                           │  SELF-HOSTED NODE    │   │
│                                           │  (Docker: FastAPI    │   │
│                                           │   + PostgreSQL)      │   │
│                                           └──────────┬──────────┘   │
│                                                      │ periodic     │
└──────────────────────────────────────────────────────┼──────────────┘
                                                       │ diff sync
                                             ┌─────────▼───────────┐
                                             │  CANONICAL SERVER    │
                                             │  api.oviddb.org      │
                                             │  (sync feed endpoint)│
                                             └─────────────────────┘
```

---

## 2. Disc Fingerprinting Specification

This is the most technically critical part of OVID. The fingerprint must be:
- **Deterministic** — the same disc always produces the same fingerprint
- **Stable** — unaffected by which drive, OS, or ripping library reads the disc
- **Unique** — different disc pressings/editions should produce different fingerprints
- **Collision-resistant** — two completely different discs should never share a fingerprint

### 2.1 DVD Fingerprint Algorithm

DVDs store structure in `.IFO` files inside the `VIDEO_TS/` directory. The fingerprint is derived from this structure, which is identical across all copies of the same pressing.

**Input data (read from disc):**

```
VIDEO_TS/
  VIDEO_TS.IFO      ← root info file
  VTS_01_0.IFO      ← title set 1 info
  VTS_02_0.IFO      ← title set 2 info
  ...               ← up to 99 title sets
```

**Algorithm:**

1. Read `VIDEO_TS.IFO` and extract: number of title sets (VTS count), total number of titles
2. For each title set `VTS_XX_0.IFO`, extract:
   - Number of programs (titles) in this set
   - For each program: total duration in seconds (from PGC playback time), number of chapters (cells)
3. Build a canonical string in this format:
   ```
   DVD|{num_title_sets}|{title_count}|{ts1_titles}:{t1_dur}:{t1_chaps},{t2_dur}:{t2_chaps},...|{ts2_titles}:...
   ```
   Example:
   ```
   DVD|3|8|1:7287:28|5:104:3,95:2,88:2,82:2,71:1|2:134:5,112:4
   ```
4. SHA-256 hash the canonical string → truncate to first 40 hex characters
5. Format: `dvd-{40_char_hex}`

**Why this works:** The number and duration of titles/chapters is determined at disc mastering time and is identical across all physical copies of the same pressing. Minor read errors (sub-second timing differences) are addressed by rounding durations to the nearest second.

**Known edge cases:**
- Some DVDs have malformed IFO files — the library should fall back to a best-effort parse and flag the fingerprint as `low_confidence`
- Region-locked content may present different title sets on different players — fingerprint should be based on raw IFO data, not playback behavior

---

### 2.2 Blu-ray Fingerprint Algorithm

Blu-ray discs store structure in the `BDMV/` directory. The relevant files are:

```
BDMV/
  index.bdmv        ← disc index
  MovieObject.bdmv  ← navigation commands
  PLAYLIST/
    00001.mpls      ← playlist files (define playback order)
    00002.mpls
    ...
  CLIPINF/
    00001.clpi      ← clip info (metadata about each stream)
    00002.clpi
    ...
  STREAM/           ← actual video (not read for fingerprinting)
```

**Algorithm:**

1. Read all `.mpls` (playlist) files from `BDMV/PLAYLIST/`
2. For each playlist, extract:
   - Total playback duration (in seconds, from clip info)
   - Number of PlayItems (stream segments)
   - Number of chapters (marks)
   - Number of audio streams and their language codes
   - Number of subtitle streams and their language codes
3. Sort playlists by duration descending (the main feature is almost always the longest playlist)
4. Build canonical string:
   ```
   BD|{playlist_count}|{pl_id}:{dur}:{items}:{chaps}:{audio_langs}:{sub_langs}|...
   ```
   Example:
   ```
   BD|12|00001:8847:1:28:eng,fra,spa:eng,fra,spa,por|00002:8847:1:28:eng:eng|00003:312:1:0:eng:
   ```
5. SHA-256 hash → first 40 hex characters
6. Format: `bd-{40_char_hex}`

**Note on 4K UHD Blu-ray:** The BDMV structure is identical to standard Blu-ray. The fingerprint prefix will be `uhd-` to distinguish these, but the algorithm is the same.

---

### 2.3 Fingerprint String Format

All OVID fingerprints follow this format:

```
{format}-{40_char_sha256_hex}
```

Examples:
```
dvd-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a
bd-9f1e3c7b2a4d6e8f0a2c4e6b8d0f2a4c6e8b0d2
uhd-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0
```

---

## 3. Database Schema

### 3.1 Core Tables

```sql
-- A disc fingerprint — one row per unique physical disc pressing
CREATE TABLE discs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint     VARCHAR(50) UNIQUE NOT NULL,  -- e.g. dvd-a3f92c1b...
    format          VARCHAR(10) NOT NULL,          -- 'DVD', 'BD', 'UHD'
    region_code     VARCHAR(10),                   -- 'A', 'B', 'C', '1'-'6', 'FREE'
    upc             VARCHAR(20),                   -- barcode from disc case
    disc_label      VARCHAR(100),                  -- raw label from disc filesystem
    disc_number     SMALLINT DEFAULT 1,            -- for multi-disc sets
    total_discs     SMALLINT DEFAULT 1,
    edition_name    VARCHAR(200),                  -- e.g. "Director's Cut", "Collector's Edition"
    status          VARCHAR(20) DEFAULT 'unverified', -- 'unverified', 'verified', 'disputed'
    submitted_by    UUID REFERENCES users(id),
    verified_by     UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- A canonical movie or TV release (linked to TMDB/IMDB)
CREATE TABLE releases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    year            SMALLINT,
    content_type    VARCHAR(20) NOT NULL,  -- 'movie', 'tv_series', 'special'
    tmdb_id         INTEGER,
    imdb_id         VARCHAR(20),           -- tt-prefixed IMDB ID
    original_language VARCHAR(10),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Join: a disc contains a release (or part of one)
CREATE TABLE disc_releases (
    disc_id         UUID REFERENCES discs(id) ON DELETE CASCADE,
    release_id      UUID REFERENCES releases(id),
    PRIMARY KEY (disc_id, release_id)
);

-- A single playback title/program on a disc
CREATE TABLE disc_titles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disc_id         UUID REFERENCES discs(id) ON DELETE CASCADE,
    title_index     SMALLINT NOT NULL,    -- index as it appears on disc (1-based)
    title_type      VARCHAR(30),          -- 'main_feature', 'bonus', 'trailer', 'menu', 'unknown'
    duration_secs   INTEGER,
    chapter_count   SMALLINT,
    is_main_feature BOOLEAN DEFAULT FALSE,
    display_name    VARCHAR(200),         -- human-readable e.g. "Director's Commentary"
    sort_order      SMALLINT
);

-- Audio and subtitle tracks for each disc title
CREATE TABLE disc_tracks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disc_title_id   UUID REFERENCES disc_titles(id) ON DELETE CASCADE,
    track_type      VARCHAR(10) NOT NULL,  -- 'audio', 'subtitle', 'video'
    track_index     SMALLINT NOT NULL,
    language_code   VARCHAR(10),           -- ISO 639-1/2, e.g. 'en', 'fr', 'es'
    codec           VARCHAR(30),           -- 'AC3', 'DTS', 'TrueHD', 'PGS', 'SRT', 'H264', etc.
    channels        SMALLINT,              -- for audio: 2, 6, 8
    is_default      BOOLEAN DEFAULT FALSE,
    description     VARCHAR(200)           -- e.g. "English 5.1 DTS-HD Master Audio"
);

-- User accounts
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    email_verified  BOOLEAN DEFAULT FALSE,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) DEFAULT 'contributor',  -- 'contributor', 'editor', 'admin'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    submission_count INTEGER DEFAULT 0,
    verification_count INTEGER DEFAULT 0
);

-- Edit history (all changes are logged)
CREATE TABLE disc_edits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disc_id         UUID REFERENCES discs(id),
    user_id         UUID REFERENCES users(id),
    edit_type       VARCHAR(30),    -- 'create', 'update', 'verify', 'dispute'
    field_changed   VARCHAR(100),
    old_value       TEXT,
    new_value       TEXT,
    edit_note       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.2 Indexes

```sql
CREATE INDEX idx_discs_fingerprint    ON discs(fingerprint);
CREATE INDEX idx_discs_upc            ON discs(upc) WHERE upc IS NOT NULL;
CREATE INDEX idx_discs_label          ON discs(disc_label) WHERE disc_label IS NOT NULL;
CREATE INDEX idx_discs_status         ON discs(status);
CREATE INDEX idx_releases_tmdb        ON releases(tmdb_id) WHERE tmdb_id IS NOT NULL;
CREATE INDEX idx_releases_imdb        ON releases(imdb_id) WHERE imdb_id IS NOT NULL;
CREATE INDEX idx_disc_titles_disc     ON disc_titles(disc_id);
CREATE INDEX idx_disc_tracks_title    ON disc_tracks(disc_title_id);
CREATE UNIQUE INDEX idx_disc_titles_index ON disc_titles(disc_id, title_index);
```

---

## 4. API Design

### 4.1 Base URL and Versioning

```
https://api.oviddb.org/v1/
```

All endpoints return JSON. All responses include a `request_id` for debugging.

### 4.2 Authentication

- Read endpoints (GET) are **unauthenticated** — no API key needed for lookups
- Write endpoints (POST, PATCH) require a **Bearer token** (JWT issued at login)
- Rate limiting: 100 requests/minute unauthenticated, 500/minute authenticated

---

### 4.3 Endpoint Reference

#### Look Up a Disc by Fingerprint

```
GET /v1/disc/{fingerprint}
```

**Parameters:**
- `fingerprint` (path) — a valid OVID fingerprint string (e.g., `dvd-a3f92c...`)

**Response 200 — disc found:**

```json
{
  "request_id": "req_abc123",
  "fingerprint": "dvd-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a",
  "format": "DVD",
  "status": "verified",
  "confidence": "high",
  "region_code": "1",
  "upc": "786936246100",
  "edition_name": "Special Edition",
  "disc_number": 1,
  "total_discs": 2,
  "release": {
    "title": "The Lord of the Rings: The Fellowship of the Ring",
    "year": 2001,
    "content_type": "movie",
    "tmdb_id": 120,
    "imdb_id": "tt0120737"
  },
  "titles": [
    {
      "title_index": 1,
      "is_main_feature": true,
      "title_type": "main_feature",
      "display_name": "The Fellowship of the Ring (Theatrical Cut)",
      "duration_secs": 10800,
      "chapter_count": 43,
      "audio_tracks": [
        { "index": 1, "language": "en", "codec": "DTS", "channels": 6, "is_default": true },
        { "index": 2, "language": "fr", "codec": "AC3", "channels": 6, "is_default": false }
      ],
      "subtitle_tracks": [
        { "index": 1, "language": "en", "codec": "DVD_SUB", "is_default": false },
        { "index": 2, "language": "fr", "codec": "DVD_SUB", "is_default": false }
      ]
    },
    {
      "title_index": 9,
      "is_main_feature": false,
      "title_type": "trailer",
      "display_name": "Theatrical Trailer",
      "duration_secs": 152,
      "chapter_count": 1,
      "audio_tracks": [],
      "subtitle_tracks": []
    }
  ]
}
```

**Response 404 — disc not found:**
```json
{
  "request_id": "req_abc124",
  "error": "disc_not_found",
  "message": "No disc found matching fingerprint dvd-a3f92c...",
  "fingerprint": "dvd-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a"
}
```

**Confidence field values:**
- `high` — fingerprint matched a verified entry; multiple contributors confirmed
- `medium` — fingerprint matched an unverified entry (single submission)
- `low` — fingerprint matched via fuzzy/fallback matching (edge case)

---

#### Look Up a Disc by UPC Barcode

```
GET /v1/disc/upc/{upc}
```

Returns an array of matching disc entries (multiple editions can share a UPC or a UPC can appear on multi-disc sets).

---

#### Look Up by Disc Label (Fuzzy Fallback)

```
GET /v1/disc/label/{label}
```

Returns an array of candidate matches, ordered by confidence. Used as a last resort when fingerprint lookup fails.

---

#### Submit a New Disc

```
POST /v1/disc
Authorization: Bearer {token}
Content-Type: application/json
```

**Request body:**

```json
{
  "fingerprint": "dvd-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a",
  "format": "DVD",
  "region_code": "1",
  "upc": "786936246100",
  "disc_label": "LOTR_FELLOWSHIP",
  "edition_name": "Special Edition",
  "disc_number": 1,
  "total_discs": 2,
  "release": {
    "tmdb_id": 120
  },
  "titles": [
    {
      "title_index": 1,
      "is_main_feature": true,
      "title_type": "main_feature",
      "duration_secs": 10800,
      "chapter_count": 43,
      "audio_tracks": [
        { "index": 1, "language": "en", "codec": "DTS", "channels": 6 }
      ],
      "subtitle_tracks": [
        { "index": 1, "language": "en", "codec": "DVD_SUB" }
      ]
    }
  ]
}
```

**Response 201 — created:**
```json
{
  "disc_id": "uuid-here",
  "fingerprint": "dvd-a3f92c...",
  "status": "unverified",
  "message": "Disc submitted. Awaiting verification from a second contributor."
}
```

---

#### Verify an Existing Disc

```
POST /v1/disc/{fingerprint}/verify
Authorization: Bearer {token}
```

A second contributor who owns the same disc submits their fingerprint. If it matches the existing entry, the disc is promoted to `verified` status.

---

#### Search Releases

```
GET /v1/search?q={query}&type={movie|tv}&year={year}&page={n}
```

Returns an array of releases with their associated disc count.

---

### 4.4 Error Codes

| HTTP Status | Error Code | Meaning |
|---|---|---|
| 400 | `invalid_fingerprint` | Fingerprint format is malformed |
| 400 | `invalid_submission` | Required fields missing in POST body |
| 401 | `auth_required` | Write endpoint called without auth token |
| 403 | `insufficient_role` | User lacks permission for this action |
| 404 | `disc_not_found` | No disc matches the given fingerprint/UPC |
| 409 | `duplicate_fingerprint` | A disc with this fingerprint already exists |
| 429 | `rate_limited` | Too many requests |
| 500 | `server_error` | Unexpected internal error |

---

## 5. `ovid-client` Python Library

### 5.1 Installation

```bash
pip install ovid-client
```

### 5.2 Usage

```python
from ovid import Disc, OVIDClient

# Generate fingerprint from a mounted disc
disc = Disc.from_path("/dev/sr0")        # or Disc.from_path("/mnt/dvd") for a mount point
print(disc.fingerprint)                  # "dvd-a3f92c..."
print(disc.format)                       # "DVD"
print(disc.disc_label)                   # "LOTR_FELLOWSHIP"

# Look up the disc in OVID
client = OVIDClient()                    # uses https://api.oviddb.org by default
result = client.lookup(disc.fingerprint)

if result:
    print(result.release.title)          # "The Lord of the Rings: The Fellowship of the Ring"
    print(result.confidence)             # "high"
    main = result.main_feature_title
    print(main.title_index)              # 1
    print(main.duration_secs)            # 10800
else:
    print("Disc not in OVID database yet")

# Submit a disc (requires API token)
client = OVIDClient(api_key="your_token_here")
client.submit(disc, tmdb_id=120, edition_name="Special Edition")
```

### 5.3 CLI Tool

```bash
# Fingerprint a disc
$ ovid fingerprint /dev/sr0
dvd-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a

# Look up a disc
$ ovid lookup /dev/sr0
✓ Found: The Lord of the Rings: The Fellowship of the Ring (2001)
  Edition: Special Edition · Disc 1 of 2 · Confidence: high
  Main feature: Title 1 (3:00:00, 43 chapters)

# Submit a disc
$ ovid submit /dev/sr0 --tmdb-id 120 --edition "Special Edition" --disc 1 --total-discs 2
✓ Submitted. Status: unverified. Awaiting second confirmation.
```

### 5.4 ARM Integration

ARM's `identify.py` module would be extended with a new provider:

```python
# In ARM's metadata lookup chain:
def identify_disc(drive_path, settings):
    # 1. Try OVID first (disc-level fingerprint)
    if settings.get("OVID_ENABLED"):
        from ovid import Disc, OVIDClient
        disc = Disc.from_path(drive_path)
        client = OVIDClient(base_url=settings.get("OVID_API_URL", "https://api.oviddb.org"))
        result = client.lookup(disc.fingerprint)
        if result and result.confidence in ("high", "medium"):
            return build_arm_job_from_ovid(result)

    # 2. Fall back to existing TMDB/OMDb lookup
    return identify_via_tmdb(drive_path, settings)
```

---

## 6. Technology Stack

### Recommended Stack (v1)

| Component | Technology | Rationale |
|---|---|---|
| API Server | Python + FastAPI | Familiar to existing ARM contributors; excellent async performance; automatic OpenAPI docs |
| Database | PostgreSQL 16 | Relational data fits this schema well; excellent indexing; widely hosted |
| Database Migrations | Alembic | Standard Python migration tool |
| Auth | JWT (PyJWT) + bcrypt | Simple, stateless, no external service dependency |
| Web UI | Plain HTML + HTMX or React | HTMX: simpler to maintain for a small team; React: better for interactive editor UIs |
| Hosting (initial) | Railway, Fly.io, or Render | Low-ops, cheap for early traffic; migrate to VPS or cloud as traffic grows |
| CDN / Rate Limiting | Cloudflare (free tier) | Rate limiting, DDoS protection, caching for read-heavy API |
| `ovid-client` | Pure Python (3.9+) | Uses `libdvdread` bindings (Python wrapper: `python-dvdread`) and `libbluray` |

### Dependencies for `ovid-client`

```
libdvdread    — read DVD IFO files (C library, widely packaged)
libbluray     — read Blu-ray BDMV/PLAYLIST files (C library, VideoLAN project)
python-dvdread — Python bindings for libdvdread (or ctypes wrapper)
requests      — HTTP client for API calls
click         — CLI framework
```

**Note:** These C libraries are already installed on most ARM setups. `ovid-client` should detect and use them if present and raise a clear error if not.

---

## 7. Scale and Reliability

### Load Estimates (v1)

OVID is expected to serve a small, enthusiast community initially. Conservative estimates:

| Metric | Estimate |
|---|---|
| Database size at launch | ~500 discs → ~10KB per disc record → ~5MB total |
| Database size at 1 year | ~50,000 discs → ~500MB total |
| API requests at launch | <100 req/day |
| API requests at 1 year | ~10,000 req/day (ARM community is ~10k+ active users) |
| Peak load | Burst around software releases or community events |

At this scale, a single server (2 vCPU, 4GB RAM) running FastAPI + PostgreSQL handles load comfortably. No distributed architecture needed for v1.

### Reliability

- **Database backups:** Automated daily backups to S3-compatible storage (Backblaze B2 is low-cost)
- **Uptime target:** 99.5% (allows ~3.6 hours downtime/month) — appropriate for a community project
- **Read caching:** Cache frequently-looked-up disc records in memory (simple Python `lru_cache` or Redis for v1.1) — lookup is read-heavy
- **API is non-blocking:** If OVID is down, ARM falls back gracefully to TMDB/OMDb. OVID failure should never block a rip.

---

## 8. Security Considerations

| Risk | Mitigation |
|---|---|
| Spam / garbage submissions | Email verification required; new accounts limited to 10 submissions/day; flagging system for community moderation |
| Fingerprint collision attacks | Fingerprints are read-only computed values, not user-supplied; SHA-256 hash space makes collisions negligible |
| SQL injection | All queries use parameterized statements (SQLAlchemy ORM) |
| Auth token leakage | Tokens expire after 30 days; refresh token rotation |
| DRM-related legal risk | API and schema explicitly do NOT store encryption keys, CSS keys, AACS keys, or any data that constitutes circumvention under DMCA/similar laws. ToS must be explicit about this. |
| Data poisoning (malicious disc entries) | Two-contributor verification model; edit history; admin override |

---

## 9. Data Licensing and Governance

- All submitted disc metadata is licensed **CC0 (Creative Commons Zero)** — fully public domain
- Monthly database dumps published as compressed SQL + JSON at no cost
- The fingerprinting algorithm specification is published as an open standard so third parties can implement compatible clients
- Project governance: initially a single maintainer + core contributors; target: form a small non-profit foundation at 10,000+ disc entries (similar to MetaBrainz Foundation model)

---

## 10. Open Technical Questions

| Question | Notes |
|---|---|
| Can `libdvdread` be called from Python without requiring user to install C headers? | May need to ship a ctypes-based fallback or bundle compiled binaries for common platforms (Linux/macOS) |
| How should we handle encrypted Blu-ray discs that require `libaacs` to mount? | ARM users typically already have decryption set up. OVID fingerprinting can operate on already-mounted/decrypted disc data. |
| What happens if two different disc pressings produce identical fingerprints? (hash collision or structurally identical discs) | The two-contributor verification model should surface this — contributors can flag fingerprint conflicts |
| Should the fingerprint algorithm be versioned? | Yes — prefix format includes version: `dvd2-...` for algorithm v2, allowing migration |
| Should OVID store the disc label as a searchable fallback? | Yes, but with low confidence weighting — labels are unreliable but better than nothing |

---

## 11. Docker Development Environment

Every contributor and self-hoster runs the identical stack via Docker Compose. There is no "works on my machine" problem — if Docker is installed, the full OVID server is one command away.

### 11.1 Repository Layout

```
ovid/
├── docker-compose.yml          ← full local stack
├── docker-compose.prod.yml     ← production overrides (no dev volumes, etc.)
├── .env.example                ← copy to .env and fill in secrets
├── api/
│   ├── Dockerfile
│   ├── main.py                 ← FastAPI app entry point
│   ├── requirements.txt
│   └── alembic/                ← database migrations
├── web/
│   ├── Dockerfile
│   └── ...                     ← web UI source
└── scripts/
    ├── seed.py                 ← load test disc data into local DB
    └── sync.py                 ← pull diff from canonical server
```

### 11.2 `docker-compose.yml`

```yaml
version: "3.9"

services:

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB:       ${OVID_DB_NAME:-ovid}
      POSTGRES_USER:     ${OVID_DB_USER:-ovid}
      POSTGRES_PASSWORD: ${OVID_DB_PASSWORD:-ovidlocal}
    volumes:
      - ovid_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${OVID_DB_USER:-ovid}"]
      interval: 5s
      timeout: 5s
      retries: 5
    ports:
      - "5432:5432"   # expose for local DB tools (TablePlus, DBeaver, etc.)

  api:
    build: ./api
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL:    postgresql://${OVID_DB_USER:-ovid}:${OVID_DB_PASSWORD:-ovidlocal}@db:5432/${OVID_DB_NAME:-ovid}
      SECRET_KEY:      ${OVID_SECRET_KEY:-dev-secret-change-in-production}
      OVID_MODE:       ${OVID_MODE:-standalone}   # 'standalone' | 'mirror' | 'canonical'
      SYNC_SOURCE_URL: ${SYNC_SOURCE_URL:-https://api.oviddb.org}
      LOG_LEVEL:       ${LOG_LEVEL:-info}
    ports:
      - "8000:8000"
    volumes:
      - ./api:/app   # hot-reload in development
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build: ./web
    restart: unless-stopped
    depends_on:
      - api
    ports:
      - "3000:3000"
    volumes:
      - ./web:/app   # hot-reload in development

  sync:
    build: ./api
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL:    postgresql://${OVID_DB_USER:-ovid}:${OVID_DB_PASSWORD:-ovidlocal}@db:5432/${OVID_DB_NAME:-ovid}
      SYNC_SOURCE_URL: ${SYNC_SOURCE_URL:-https://api.oviddb.org}
      SYNC_INTERVAL_MINUTES: ${SYNC_INTERVAL_MINUTES:-60}
    command: python scripts/sync.py --daemon
    profiles:
      - mirror   # only runs when: docker compose --profile mirror up

volumes:
  ovid_pgdata:
```

**Key design choices:**
- The `sync` service is in a Docker Compose **profile** called `mirror`. It only starts when you explicitly run `docker compose --profile mirror up`. A plain `docker compose up` starts a standalone local instance with no sync.
- The `api` container mounts `./api` as a volume so code changes reload instantly during development — no rebuild needed.
- The database port is exposed locally so developers can connect with standard DB tools.

### 11.3 `.env.example`

```bash
# Copy this file to .env and fill in values before running docker compose up

# Database
OVID_DB_NAME=ovid
OVID_DB_USER=ovid
OVID_DB_PASSWORD=change_me_in_production

# API
OVID_SECRET_KEY=change_me_to_a_long_random_string
LOG_LEVEL=info

# Node mode: standalone | mirror | canonical
# standalone = local-only, no sync (good for dev)
# mirror     = syncs from canonical server periodically (good for home NAS)
# canonical  = the main oviddb.org server (only used by project maintainers)
OVID_MODE=standalone

# Sync source (only used in mirror mode)
SYNC_SOURCE_URL=https://api.oviddb.org

# How often to pull diffs from canonical (minutes)
SYNC_INTERVAL_MINUTES=60
```

### 11.4 Getting Started (Developer)

```bash
# 1. Clone the repo
git clone https://github.com/The-Artificer-of-Ciphers-LLC/OVID.git
cd OVID

# 2. Configure environment
cp .env.example .env
# (edit .env if needed — defaults work for local dev)

# 3. Start the full stack
docker compose up

# 4. Run database migrations
docker compose exec api alembic upgrade head

# 5. Seed with test data (optional)
docker compose exec api python scripts/seed.py

# API is now running at http://localhost:8000
# Web UI is at http://localhost:3000
# API docs (auto-generated) at http://localhost:8000/docs
```

### 11.5 Getting Started (Self-Hosted Mirror)

```bash
# Same as above, but start with mirror profile to enable background sync
docker compose --profile mirror up -d

# Run migrations
docker compose exec api alembic upgrade head

# Trigger an immediate sync from canonical server
docker compose exec sync python scripts/sync.py --once

# Point ovid-client at your local server
export OVID_API_URL=http://localhost:8000
ovid lookup /dev/sr0
```

### 11.6 Production Deployment (`docker-compose.prod.yml`)

The production override file removes volume mounts (no live code reload), sets `--workers 4` on uvicorn, and expects secrets to come from environment variables rather than an `.env` file:

```yaml
# docker-compose.prod.yml — apply with:
# docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  api:
    command: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
    volumes: []   # no source mount in production
    restart: always

  web:
    volumes: []
    restart: always

  db:
    ports: []     # don't expose DB port externally in production
    restart: always
```

---

## 12. Self-Hosted and Distributed Sync Architecture

Self-hosted OVID nodes stay current by pulling **diffs** from the canonical server on a schedule. This is the same model used by Linux package mirrors, DNS zone transfers, and podcast feeds — it is battle-tested, simple to implement, and requires no persistent connection or special protocol.

### 12.1 Core Concept: The Sequence Number

Every write to the OVID database increments a global, monotonically increasing `sequence_number`. This number is stored on each record and never reused or decremented.

```sql
-- Added to the discs, releases, disc_titles, and disc_tracks tables:
ALTER TABLE discs      ADD COLUMN seq BIGSERIAL;
ALTER TABLE releases   ADD COLUMN seq BIGSERIAL;
ALTER TABLE disc_titles ADD COLUMN seq BIGSERIAL;
ALTER TABLE disc_tracks ADD COLUMN seq BIGSERIAL;

-- Global sequence counter (single source of truth)
CREATE SEQUENCE ovid_global_seq START 1;
```

Each self-hosted node stores one value in its local config: `last_synced_seq`. On each sync cycle it requests everything that has changed since that number, applies it locally, and advances its cursor.

### 12.2 Sync Feed API Endpoints

These endpoints are added to the canonical server specifically to support self-hosted nodes. They are read-only and unauthenticated (data is CC0 anyway).

#### Get the Current Sequence Number

```
GET /v1/sync/head
```

```json
{ "seq": 48291, "timestamp": "2026-03-31T21:00:00Z" }
```

Self-hosted nodes call this first to check whether they are behind before doing a full diff request.

#### Pull a Diff

```
GET /v1/sync/diff?since={seq}&limit={n}
```

| Parameter | Default | Notes |
|---|---|---|
| `since` | required | Return all records with `seq > since` |
| `limit` | 1000 | Max records per response. Paginate using `next_seq` cursor. |

**Response:**

```json
{
  "since_seq": 47000,
  "latest_seq": 48291,
  "next_seq": 48001,
  "has_more": true,
  "records": [
    {
      "type": "disc",
      "op": "upsert",
      "seq": 47001,
      "data": { ...full disc object... }
    },
    {
      "type": "release",
      "op": "upsert",
      "seq": 47002,
      "data": { ...full release object... }
    },
    {
      "type": "disc",
      "op": "delete",
      "seq": 47050,
      "data": { "fingerprint": "dvd-abc123..." }
    }
  ]
}
```

The `op` field is always `upsert` (create or update — the node doesn't need to know which) or `delete` (the record was removed, e.g., a spam submission). Self-hosted nodes apply each record using an `INSERT ... ON CONFLICT DO UPDATE` (PostgreSQL upsert), making the operation idempotent — safe to replay if a sync is interrupted.

#### Download a Full Snapshot (for initial setup)

```
GET /v1/sync/snapshot
```

Returns a URL to a compressed `.ndjson.gz` file (newline-delimited JSON, one record per line) containing the full database. Updated daily by the canonical server and hosted on a CDN. Used to initialize a fresh self-hosted node without having to replay thousands of individual diff records.

```json
{
  "snapshot_seq": 48200,
  "url": "https://snapshots.oviddb.org/ovid-snapshot-20260331.ndjson.gz",
  "size_bytes": 2400000,
  "record_count": 12400,
  "sha256": "a1b2c3..."
}
```

Initial setup workflow:
1. Download snapshot → import into local PostgreSQL
2. Set `last_synced_seq` to `snapshot_seq`
3. Pull diff from `snapshot_seq` to current head
4. Begin normal scheduled sync

### 12.3 Node Modes

| Mode | Accepts local writes? | Syncs from canonical? | Submits to canonical? |
|---|---|---|---|
| `standalone` | Yes | No | No |
| `mirror` | No | Yes (scheduled) | No |
| `federated` *(v2)* | Yes | Yes | Yes (upstream submissions) |

**Standalone** is for development and experimentation — a fully private OVID instance with no connection to the community.

**Mirror** is the primary self-hosted use case: a NAS or home server that keeps a local read-only copy of the community database and serves lookups to ARM without any outbound internet calls during ripping. Syncs on a configurable interval (default: every 60 minutes).

**Federated** (planned for Phase 2) allows a self-hosted node to both receive diffs from canonical *and* submit new disc entries upstream. This enables organizations (e.g., a library or film archive) to run their own OVID node, contribute their holdings to the community database, and stay in sync — while maintaining local control.

### 12.4 `sync.py` — The Sync Worker

The `sync` Docker service runs this script as a daemon:

```python
# scripts/sync.py (simplified pseudocode)
import time, requests, psycopg2, os

SYNC_URL  = os.environ["SYNC_SOURCE_URL"]
DB_URL    = os.environ["DATABASE_URL"]
INTERVAL  = int(os.environ.get("SYNC_INTERVAL_MINUTES", 60)) * 60

def get_last_seq(conn):
    cur = conn.cursor()
    cur.execute("SELECT value FROM sync_state WHERE key = 'last_seq'")
    row = cur.fetchone()
    return int(row[0]) if row else 0

def set_last_seq(conn, seq):
    conn.cursor().execute(
        "INSERT INTO sync_state (key, value) VALUES ('last_seq', %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (str(seq),)
    )
    conn.commit()

def apply_diff(conn, records):
    cur = conn.cursor()
    for rec in records:
        if rec["type"] == "disc" and rec["op"] == "upsert":
            cur.execute(
                "INSERT INTO discs (...) VALUES (...) "
                "ON CONFLICT (fingerprint) DO UPDATE SET ...",
                (rec["data"],)
            )
        elif rec["type"] == "disc" and rec["op"] == "delete":
            cur.execute(
                "DELETE FROM discs WHERE fingerprint = %s",
                (rec["data"]["fingerprint"],)
            )
        # ... handle releases, disc_titles, disc_tracks similarly
    conn.commit()

def sync_once(conn):
    last_seq = get_last_seq(conn)
    head = requests.get(f"{SYNC_URL}/v1/sync/head").json()
    if head["seq"] <= last_seq:
        print(f"Already up to date at seq {last_seq}")
        return

    next_seq = last_seq
    while True:
        resp = requests.get(f"{SYNC_URL}/v1/sync/diff",
                            params={"since": next_seq, "limit": 1000}).json()
        apply_diff(conn, resp["records"])
        next_seq = resp["latest_seq"]
        set_last_seq(conn, next_seq)
        if not resp["has_more"]:
            break
    print(f"Synced to seq {next_seq} ({head['seq'] - last_seq} new records)")

def run_daemon(conn):
    while True:
        try:
            sync_once(conn)
        except Exception as e:
            print(f"Sync error: {e}")
        time.sleep(INTERVAL)
```

### 12.5 Conflict and Consistency Model

OVID uses **last-write-wins** at the canonical server — the canonical database is the authoritative source of truth. Self-hosted mirror nodes are strictly read-only replicas and never introduce conflicts.

For the future **federated** mode, where local nodes can also accept submissions, the conflict model is:
- Local submissions are assigned a `local_` prefixed `source_node_id`
- When submitted upstream, the canonical server validates and may reject (e.g., if a verified entry for that fingerprint already exists with conflicting data)
- Rejected submissions are flagged locally for human review
- The canonical server's version always wins on the next sync — local overrides are not possible without re-submitting

This intentionally keeps the conflict resolution simple at the cost of some flexibility. It matches the way MusicBrainz handles edit conflicts: the community database is authoritative, and disagreements go through a moderation workflow rather than being resolved automatically.

### 12.6 Bandwidth and Storage Estimates

| Scenario | Data Volume |
|---|---|
| Initial snapshot at launch (~500 discs) | ~5MB compressed |
| Initial snapshot at 1 year (~50,000 discs) | ~250MB compressed |
| Daily diff at steady state (est. 200 new/updated records/day) | ~500KB/day |
| Monthly diff for a mirror that syncs infrequently | ~15MB/month |

These are tiny numbers. A self-hosted node on a home NAS with even a basic internet connection can stay fully in sync with negligible bandwidth cost.

---

## 13. Phased Delivery Plan

### Phase 0 — Spec and Scaffolding (Weeks 1–6)

- [ ] Finalize and publish disc fingerprinting algorithm spec as a standalone document
- [ ] Prototype `ovid-client` that reads DVD IFO files and generates fingerprints
- [ ] Validate fingerprint stability: test same disc on 3+ different drives
- [ ] Stand up PostgreSQL schema with sequence numbers (migrations via Alembic)
- [ ] Basic FastAPI server with `/v1/disc/{fingerprint}` GET and POST endpoints
- [ ] **Docker Compose dev environment** (`docker compose up` → working local stack)
- [ ] `.env.example` and developer getting-started documentation
- [ ] Seed with 20 test discs from contributor's own collection

### Phase 1 — MVP (Weeks 7–14)

- [ ] Complete `ovid-client` with Blu-ray BDMV support
- [ ] Publish `ovid-client` to PyPI
- [ ] Web UI: search, browse disc entry, submit form
- [ ] User accounts, JWT auth, email verification
- [ ] Two-contributor verification workflow
- [ ] ARM pull request: add OVID as optional metadata provider
- [ ] Deploy to cloud hosting (Railway or Fly.io)
- [ ] Seed database to ~500 discs
- [ ] **Sync feed endpoints** (`/v1/sync/head`, `/v1/sync/diff`) on canonical server
- [ ] **Mirror mode**: `sync.py` daemon + `docker compose --profile mirror up` workflow
- [ ] Daily snapshot generation and hosting (for fresh mirror installs)

### Phase 2 — Community Features (Weeks 15–26)

- [ ] Edit history and audit log
- [ ] UPC barcode lookup endpoint
- [ ] Community dispute flagging
- [ ] Monthly public database dump (replaces/supplements snapshot)
- [ ] Rate limiting and abuse prevention
- [ ] Documentation site
- [ ] **Federated mode** design and implementation (local writes + upstream submission)
- [ ] Self-hosted installer script (single-command deploy to a Raspberry Pi or NAS)

---

*Document status: Draft v0.2 · Authors: Project founders · Last updated: 2026-03-31*
