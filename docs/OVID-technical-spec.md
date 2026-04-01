# OVID — Open Video Disc Identification Database
## Technical Specification · v0.1 Draft

---

## 1. System Overview

OVID is a three-part system:

1. **`ovid-client`** — A Python library (with a CLI) that reads a mounted DVD or Blu-ray disc and generates a standardized disc fingerprint string.
2. **OVID API Server** — A REST API that accepts fingerprint lookups and disc submissions, backed by a relational database.
3. **OVID Web UI** — A browser-based interface for searching, browsing, and submitting disc entries. Also serves as the human review and moderation layer.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Computer                              │
│                                                                      │
│   ┌──────────────┐     disc fingerprint      ┌──────────────────┐   │
│   │  ARM / other │ ─────────────────────────▶│   ovid-client    │   │
│   │  rip tool    │◀─ metadata JSON ─────────  │   (Python lib)   │   │
│   └──────────────┘                            └────────┬─────────┘   │
│                                                        │             │
└────────────────────────────────────────────────────────┼────────────┘
                                                         │ HTTPS REST
                                              ┌──────────▼──────────┐
                                              │    OVID API Server   │
                                              │   (Python / Flask    │
                                              │    or FastAPI)       │
                                              └──────────┬──────────┘
                                                         │
                                              ┌──────────▼──────────┐
                                              │  PostgreSQL Database │
                                              └─────────────────────┘
                                              ┌─────────────────────┐
                                              │   OVID Web UI        │
                                              │   (React or plain    │
                                              │    HTML/JS)          │
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

## 11. Phased Delivery Plan

### Phase 0 — Spec and Scaffolding (Weeks 1–6)

- [ ] Finalize and publish disc fingerprinting algorithm spec as a standalone document
- [ ] Prototype `ovid-client` that reads DVD IFO files and generates fingerprints
- [ ] Validate fingerprint stability: test same disc on 3+ different drives
- [ ] Stand up PostgreSQL schema (migrations via Alembic)
- [ ] Basic FastAPI server with `/v1/disc/{fingerprint}` GET and POST endpoints
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

### Phase 2 — Community Features (Weeks 15–26)

- [ ] Edit history and audit log
- [ ] UPC barcode lookup endpoint
- [ ] Community dispute flagging
- [ ] Monthly public database dump
- [ ] Rate limiting and abuse prevention
- [ ] Documentation site

---

*Document status: Draft v0.1 · Authors: Project founders · Last updated: 2026-03-31*
