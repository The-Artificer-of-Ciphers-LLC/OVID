# OVID — Open Video Disc Identification Database
## Technical Specification · v0.3 Draft

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

### 2.0 Prior Art and Patent Status

**The Windows dvdid algorithm (US Patent 6,871,012 B1)** was the main existing approach for DVD disc identification. It computes a 64-bit CRC from file sizes, dates, and header data in the `VIDEO_TS/` directory using an irreducible polynomial. Key facts:

- **Owner:** Microsoft Technology Licensing LLC
- **Filed:** November 22, 2000
- **Expired:** September 3, 2023 (fee lapse) — **now in the public domain**
- **Implemented by:** `pydvdid` (Apache-2.0), `pydvdid-m` (GPL-3.0), `dvdid` (C, source available)

**OVID deliberately does not use this algorithm**, and not because of the now-expired patent. The fundamental problem is that the Windows algorithm incorporates **file system timestamps** (creation and modification dates) in its CRC inputs. Timestamps change whenever disc files are copied, ripped to ISO, or transferred between systems. An algorithm that produces different fingerprints for different copies of the same disc is unsuitable for a lookup database. OVID needs fingerprints derived purely from the disc's logical content structure — the same approach used by MusicBrainz's `libdiscid` for audio CDs (which hashes the Table of Contents, not file dates).

**`pydvdid-m` (GPL-3.0)** is referenced as the model for reading IFO files from ISOs and live disc drives using `pycdlib`. OVID will use the same disc-access layer but an independent structural hash algorithm.

---

### 2.1 DVD Fingerprint Algorithm (OVID-DVD-1)

DVDs store structure in `.IFO` files inside the `VIDEO_TS/` directory. The fingerprint is derived entirely from the **logical structure** of these files — title sets, program counts, durations, and chapter layout — not from timestamps or file metadata.

**Input data (read from disc or ISO):**

```
VIDEO_TS/
  VIDEO_TS.IFO      ← root info file (VMG — Video Manager)
  VTS_01_0.IFO      ← title set 1 info
  VTS_02_0.IFO      ← title set 2 info
  ...               ← up to 99 title sets
```

**Read using:** `libdvdread` (GPL-2.0+) or `pycdlib` (LGPL-2.1) for ISO/drive access. No file timestamps are read or used.

**Algorithm — OVID-DVD-1:**

1. From `VIDEO_TS.IFO`, extract:
   - Number of title sets (`VTS_count`)
   - Total number of titles (`title_count`)
2. For each title set `VTS_XX_0.IFO` (in order, `01` through `VTS_count`), extract:
   - Number of programs (titles) in this set
   - For each program in order: total duration in **whole seconds** (rounded from PGC playback time field), number of chapters (cell count)
   - Number of audio streams, and for each: language code (ISO 639-2), codec identifier
   - Number of subtitle streams, and for each: language code
3. Build a canonical UTF-8 string in this exact format (pipe-delimited, no spaces):
   ```
   OVID-DVD-1|{VTS_count}|{title_count}|{vts1_pgc_count}:{t1_dur}:{t1_chaps}:{t1_audio}:{t1_subs},...|{vts2...}
   ```
   Where `{t1_audio}` is comma-joined language codes (e.g. `en,fr,es`) and `{t1_subs}` similarly.

   Example (Fellowship of the Ring DVD):
   ```
   OVID-DVD-1|3|8|1:7287:28:en,fr,es:en,fr,es,pt|5:104:3:en:en,104:2:en:,88:2:en:,82:2:en:,71:1:en:|2:134:5:en,fr:en,fr,134:4:en:en
   ```
4. SHA-256 hash the canonical string → encode as lowercase hex
5. Take the first 40 characters of the hex string
6. Format: `dvd1-{40_char_hex}`

**Why this is stable:** Title counts, durations (in whole seconds), and chapter layouts are fixed at mastering time and are byte-for-byte identical across every physical copy of the same pressing. No filesystem metadata is used.

**Known edge cases and handling:**
- Malformed or truncated IFO files: fall back to best-effort parse; flag fingerprint confidence as `low`
- Durations that differ by <2 seconds across drives (rare IFO timing inconsistencies): round to nearest second before hashing
- Region coding does NOT affect IFO structure — fingerprint is region-agnostic by design (region is stored separately in the OVID record)

**Compatible open-source reading libraries:**

| Library | License | Language | Notes |
|---|---|---|---|
| `libdvdread` | GPL-2.0+ | C | Standard; ships with most Linux distros |
| `pydvdid-m` | GPL-3.0 | Python | ISO + drive access via pycdlib; use for disc reading layer only |
| `pycdlib` | LGPL-2.1 | Python | ISO image mounting without root |

---

### 2.2 Blu-ray and 4K UHD Fingerprint Algorithm

**UHD Blu-ray vs standard Blu-ray:** The BDMV logical structure is **identical** between standard BD and 4K UHD. Both use the same `BDMV/PLAYLIST/*.mpls` and `BDMV/CLIPINF/*.clpi` file formats. The version header in MPLS files differs (`0200` for BD, `0300` for UHD), which OVID uses to distinguish the format. Physically, UHD discs have higher-density layers and use AACS 2 encryption, but neither affects structure-based fingerprinting.

OVID uses a **two-tier approach** for Blu-ray fingerprinting, using whichever source is available:

#### Tier 1 — AACS Disc ID (preferred, when available)

The AACS protection system stores a file called `Unit_Keys_RO.inf` in the `AACS/` directory of every pressed Blu-ray and UHD disc. The **AACS Disc ID** is the SHA-1 hash of this file. It is:
- A **true industry identifier** — unique per disc pressing by design, assigned during disc mastering
- **20 bytes (160-bit SHA-1)** — effectively no collision risk
- **Already computed** by `libaacs` (LGPL-2.1) when the disc is being decrypted for playback or ripping
- Available to ARM users since they already need `libaacs` (or MakeMKV) for ripping

```
AACS/
  Unit_Keys_RO.inf    ← AACS CPS unit key file; SHA-1 of this = Disc ID
  ContentHash000.tbl  ← 8-byte content hashes per 96-sector chunk (Layer 0)
  ContentHash001.tbl  ← (dual-layer and above)
  MKB_RO.inf          ← Media Key Block
```

**OVID Tier 1 fingerprint format:**
```
bd1-aacs-{40_char_sha1_hex}    ← standard Blu-ray with AACS disc ID
uhd1-aacs-{40_char_sha1_hex}   ← 4K UHD with AACS disc ID
```

The SHA-1 hex is the existing AACS Disc ID — OVID does not compute a new hash, just formats it. This means OVID fingerprints are directly interoperable with any tool that already knows the AACS Disc ID of a disc.

**Source library:** `libaacs` (VideoLAN, LGPL-2.1). The `aacs_get_disc_id()` function returns the 20-byte disc ID. `libbluray` (LGPL-2.1) exposes this via `BLURAY_DISC_INFO.disc_id` when `libaacs` is present.

#### Tier 2 — BDMV Structure Hash (fallback)

When the AACS directory is unavailable or the disc is not yet decrypted, OVID falls back to hashing the BDMV playlist structure. This is a structural fingerprint only — weaker than Tier 1 but still useful for identification.

**Input data:**

```
BDMV/
  PLAYLIST/
    00001.mpls    ← binary playlist file
    00002.mpls
    ...
  CLIPINF/
    00001.clpi    ← clip info (stream metadata)
    ...
```

**Read using:** `libbluray` (LGPL-2.1), which provides full MPLS and CLPI parsing. In Python: `pympls` (MIT) for MPLS parsing, or Python bindings to `libbluray` via `PyBluRead` (GPL-2.0+).

**Algorithm — OVID-BD-2 (structure hash):**

1. Read all `.mpls` files from `BDMV/PLAYLIST/`
2. Detect format from MPLS version header: `0200` = BD, `0300` = UHD
3. For each playlist (sorted by filename numerically, not by duration — ordering must be deterministic):
   - Total playback duration in whole seconds
   - Number of PlayItems
   - Number of chapter marks
   - For each audio stream: language code (ISO 639-2), codec type
   - For each subtitle stream: language code
4. Filter out playlists shorter than 60 seconds (trailers, menus, samples) to reduce noise from obfuscation playlists
5. Build canonical string:
   ```
   OVID-BD-2|{mpls_version}|{playlist_count_after_filter}|{pl_id}:{dur}:{items}:{chaps}:{audio}:{subs}|...
   ```
   Where `{audio}` and `{subs}` are `codec:lang` pairs, comma-joined; playlists sorted by filename.

6. SHA-256 hash → first 40 hex chars
7. Format: `bd2-{40_char_hex}` or `uhd2-{40_char_hex}`

**The obfuscation playlist problem:** Modern BD and UHD discs (particularly from major US studios) include hundreds of decoy playlists to defeat ripping tools. Some discs have 800+ MPLS files where only 1–2 are the actual feature. The 60-second filter removes most noise; the structural approach (durations, chapter counts, stream counts) remains meaningful because even among hundreds of fake playlists, the real feature has a unique combination of duration, chapters, and track layout.

**Compatible open-source libraries:**

| Library | License | Language | Notes |
|---|---|---|---|
| `libbluray` | LGPL-2.1 | C | Full MPLS + CLPI parsing; the reference implementation |
| `libaacs` | LGPL-2.1 | C | Provides AACS Disc ID (Tier 1) |
| `pympls` | MIT | Python | Lightweight MPLS parser; last active 2021 |
| `BDInfo` / forks | LGPL-2.1 | C# | Full BD/UHD analysis; Jellyfin fork actively maintained |
| `bluray_info` | GPL-2.0 | C | Linux CLI tools built on libbluray |
| `PyBluRead` | GPL-2.0+ | Python | Python bindings for libbluray |

---

### 2.3 Fingerprint String Format and Tier Selection

```
{format}{tier}-{source}-{hash}   (Tier 1, AACS)
{format}{tier}-{hash}            (Tier 2, structure)
```

| Fingerprint prefix | Meaning |
|---|---|
| `dvd1-` | DVD, OVID structural algorithm v1 |
| `bd1-aacs-` | Standard Blu-ray, AACS Disc ID (Tier 1) |
| `bd2-` | Standard Blu-ray, BDMV structure hash (Tier 2) |
| `uhd1-aacs-` | 4K UHD, AACS Disc ID (Tier 1) |
| `uhd2-` | 4K UHD, BDMV structure hash (Tier 2) |

**Examples:**
```
dvd1-a3f92c1b4e8d7f6a2c9e0b1d3f5a8c2e4f6b8d0a
bd1-aacs-9f1e3c7b2a4d6e8f0a2c4e6b8d0f2a4c6e8b0d2
bd2-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1
uhd1-aacs-c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1
uhd2-d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3
```

**`ovid-client` tier selection logic:**
```python
def compute_fingerprint(disc_path):
    disc = Disc.from_path(disc_path)

    if disc.format in ("BD", "UHD"):
        aacs_id = disc.aacs_disc_id()      # returns None if libaacs unavailable
        if aacs_id:
            prefix = "bd1-aacs" if disc.format == "BD" else "uhd1-aacs"
            return f"{prefix}-{aacs_id.hex()[:40]}"
        else:
            # Fall back to structure hash
            return compute_bdmv_structure_hash(disc)
    elif disc.format == "DVD":
        return compute_dvd_structure_hash(disc)
```

A single disc entry in the OVID database can hold **both** a Tier 1 and a Tier 2 fingerprint — whichever contributors have submitted — allowing lookup by either. When a Tier 2 fingerprint is later matched to a Tier 1, the entry is upgraded.

### 2.4 Licensing Summary

All libraries used to implement OVID disc fingerprinting are compatible with OVID's AGPL-3.0 license:

| Library | License | Compatibility with AGPL-3.0 |
|---|---|---|
| `libdvdread` | GPL-2.0+ | Compatible (GPL family) |
| `libbluray` | LGPL-2.1 | Compatible (LGPL can link into AGPL; must be dynamically linked) |
| `libaacs` | LGPL-2.1 | Compatible (same as above) |
| `pydvdid-m` (disc reading layer only) | GPL-3.0 | Compatible (GPL-3.0 ⊂ AGPL-3.0 family) |
| `pympls` | MIT | Compatible (permissive) |
| `pycdlib` | LGPL-2.1 | Compatible |
| `BDInfo` forks | LGPL-2.1 | Compatible |
| `bluray_info` | GPL-2.0 | Compatible |

**Attribution required:** All GPL/LGPL libraries must be credited in OVID's documentation and source. The LGPL libraries (`libbluray`, `libaacs`, `pycdlib`) must be dynamically linked, not statically compiled into the `ovid-client` binary, to preserve end-user rights to swap library versions.

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

-- User accounts (canonical identity — one row per person)
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username            VARCHAR(50) UNIQUE NOT NULL,
    email               VARCHAR(255) UNIQUE,           -- nullable: not required if OAuth-only
    email_verified      BOOLEAN DEFAULT FALSE,
    password_hash       VARCHAR(255),                  -- nullable: not required if OAuth-only
    role                VARCHAR(20) DEFAULT 'contributor',  -- 'contributor', 'editor', 'admin'
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    submission_count    INTEGER DEFAULT 0,
    verification_count  INTEGER DEFAULT 0,
    CONSTRAINT must_have_auth CHECK (
        password_hash IS NOT NULL OR
        EXISTS (SELECT 1 FROM user_identities WHERE user_id = id)
    )
);

-- Linked OAuth / federated identities (many per user)
-- One row per provider linked to an account
CREATE TABLE user_identities (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider         VARCHAR(30) NOT NULL,   -- 'github' | 'google' | 'apple' | 'mastodon' | 'email'
    provider_uid     VARCHAR(255) NOT NULL,  -- provider's stable user ID (e.g. GitHub numeric ID)
    provider_handle  VARCHAR(255),           -- display handle (e.g. '@user@fosstodon.org', 'user@gmail.com')
    instance_url     VARCHAR(255),           -- Mastodon only: e.g. 'https://fosstodon.org'
    access_token     TEXT,                   -- encrypted at rest (AES-256)
    refresh_token    TEXT,                   -- encrypted at rest
    token_expires_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    last_used_at     TIMESTAMPTZ,
    UNIQUE (provider, provider_uid)          -- one account per provider UID globally
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
CREATE INDEX idx_user_identities_user     ON user_identities(user_id);
CREATE INDEX idx_user_identities_provider ON user_identities(provider, provider_uid);
CREATE INDEX idx_users_email              ON users(email) WHERE email IS NOT NULL;

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

**Read endpoints (GET) are unauthenticated** — no API key needed for lookups.

**Write endpoints (POST, PATCH) require a Bearer token** (JWT) issued after login via any supported provider.

**Supported identity providers at launch:**

| Provider | Protocol | Notes |
|---|---|---|
| Email + password | Credential | Bcrypt hashed; optional if OAuth provider is linked |
| GitHub | OAuth 2.0 | Ideal for the developer/enthusiast audience |
| Google | OAuth 2.0 | Broad coverage |
| Apple | OAuth 2.0 (Sign in with Apple) | Required by App Store rules if ever shipping an iOS client |
| Mastodon / ActivityPub instances | OAuth 2.0 (per-instance) | On-brand for an open-source community project; see below |

**Rate limiting:** 100 requests/minute unauthenticated, 500/minute authenticated.

#### Linked Accounts Flow

Multiple providers can be linked to a single OVID account. Logging in with any linked provider issues a JWT for the same underlying account.

```
User signs up with GitHub
        ↓
OVID creates users row + user_identities row (provider='github')
        ↓
User later clicks "Link Google account" in settings
        ↓
OVID adds second user_identities row (provider='google') → same user_id
        ↓
Either GitHub or Google login now reaches the same account
```

**Email-match merge:** When a new OAuth login presents a verified email that already exists on another account, OVID presents a merge prompt rather than creating a duplicate:

```
"An account with email user@example.com already exists.
 Link this GitHub login to that account? [Link] [Create new account]"
```

Merging requires the user to authenticate the existing account (prove they own it) before linking completes.

**Minimum identity rule:** A user must always retain at least one linked provider or an active password. The UI prevents removing the last auth method. The database enforces this via a `CHECK` constraint on the `users` table.

#### Mastodon / ActivityPub Federation

Mastodon uses standard OAuth 2.0 but each instance is its own authorization server. The login flow differs slightly from fixed-endpoint providers:

```
1. User enters their instance URL (e.g. "fosstodon.org")
2. OVID fetches https://fosstodon.org/.well-known/oauth-authorization-server
   to discover the token and authorization endpoints
3. OVID redirects user to that instance's OAuth authorize URL
4. Instance redirects back with auth code → OVID exchanges for access token
5. OVID fetches the user's profile from the instance API (username, display name)
6. provider_uid stored as "{username}@{instance_host}" (e.g. "alice@fosstodon.org")
   provider_handle stored identically for display
   instance_url stored as "https://fosstodon.org"
```

This makes OVID compatible with any Mastodon-compatible software (Mastodon, Pleroma, Akkoma, Pixelfed, etc.) without needing to whitelist specific instances.

**Note on Mastodon token longevity:** Mastodon access tokens do not expire by default. OVID stores them encrypted but does not rely on them for ongoing access — they are only used at login time to verify identity. The OVID JWT is what governs session duration.

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
| Auth — sessions | JWT (PyJWT) | Short-lived access tokens (1 hour) + refresh tokens (30 days); stateless |
| Auth — passwords | bcrypt | For email+password accounts; intentionally slow hashing |
| Auth — OAuth | Authlib (Python) | Handles OAuth 2.0 flows for GitHub, Google, Apple, and dynamic Mastodon instances |
| Auth — tokens at rest | AES-256-GCM (cryptography lib) | OAuth access/refresh tokens encrypted before storing in DB |
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
| Auth token leakage | OVID JWTs expire after 1 hour; refresh tokens expire after 30 days with rotation on each use; OAuth provider tokens encrypted at rest with AES-256-GCM |
| OAuth account takeover | Email-match merge requires re-authentication of the existing account before linking; provider_uid (not email) is the stable identity key — email is only used as a merge hint |
| Malicious OAuth provider (Mastodon) | Instance URL validated against `/.well-known/oauth-authorization-server` before redirect; redirect URIs strictly allowlisted; instance_url stored and checked on token exchange |
| Account lockout (last auth method removed) | DB CHECK constraint + UI guard both prevent removing the last linked provider or password |
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

## 13. CI/CD Pipeline

Every push to any branch triggers the CI pipeline. No code reaches `develop` or `main` without passing all checks.

### Pipeline Stages

```
Push / PR opened
      │
      ▼
┌─────────────┐   fail → block merge
│  Lint        │   ruff (Python), markdownlint (docs)
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐   fail → block merge
│  Unit Tests  │   pytest; fingerprint algorithm unit tests
└──────┬──────┘
       │ pass
       ▼
┌──────────────────────┐   fail → block merge
│  Fingerprint          │   Regression suite: pre-computed fingerprints
│  Regression Tests     │   for 20 known disc ISOs; any change = fail
└──────┬───────────────┘
       │ pass
       ▼
┌─────────────┐   fail → block merge (main only)
│  DB Migration│   alembic upgrade head on clean test DB
│  Check       │
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐   runs on develop / release / main only
│  Integration │   docker compose up; seed 5 test discs;
│  Tests       │   run API smoke tests against live containers
└──────┬──────┘
       │ pass
       ▼
┌─────────────┐   main branch + tagged release only
│  Deploy      │   tag v0.x.y → deploy to production
└─────────────┘
```

### GitHub Actions Triggers

| Trigger | Pipeline stages run |
|---|---|
| PR → `develop` | Lint, Unit, Fingerprint regression |
| Push to `develop` | All stages except Deploy |
| PR → `main` (release branch) | All stages except Deploy |
| Push to `main` | All stages + Deploy to production |
| Tag `v*` | Publish `ovid-client` to PyPI + Docker Hub |

### Fingerprint Regression Test Suite

This is the most critical CI check. A corpus of 20 disc ISOs (stored in a private S3 bucket, not the public repo) has pre-computed expected fingerprints for each. Any change to the fingerprinting code that alters even one expected output **fails the build immediately**, even if the change seems intentional. Algorithm changes require a version bump (`dvd2-` prefix) rather than modifying existing expected outputs.

---

## 14. Phased Delivery Plan

Phases map directly to version milestones defined in the product spec. Each phase targets a specific `0.x.0` release. Bug-fix patch releases (`0.x.y`) may be cut at any point within a phase without advancing the milestone number.

### Phase 0 → v0.1.0 — Spec and Scaffolding (Weeks 1–6)

- [ ] Finalize and publish `OVID-DVD-1` fingerprint algorithm as `docs/fingerprint-spec.md`
- [ ] Prototype `ovid-client`: DVD IFO fingerprinting from live drive and ISO
- [ ] Validate fingerprint stability: same disc → identical output on ≥3 drives, Linux + macOS
- [ ] PostgreSQL schema with global sequence numbers (Alembic migrations)
- [ ] FastAPI server: `GET /v1/disc/{fingerprint}` and `POST /v1/disc`
- [ ] Docker Compose dev environment (`docker compose up` → working local API)
- [ ] `.env.example`, developer getting-started doc
- [ ] GitHub Actions CI: lint + unit tests + fingerprint regression suite
- [ ] Seed: ≥20 real disc entries from founders
- [ ] **Tag `v0.1.0`, publish `ovid-client` to PyPI**

*Patch releases `0.1.1`–`0.1.x`: IFO parser edge cases, pycdlib compatibility, CI fixes.*

---

### Phase 1 → v0.2.0 — MVP (Weeks 7–14)

- [ ] `ovid-client` Blu-ray: Tier 1 AACS Disc ID + Tier 2 BDMV structure hash
- [ ] `ovid-client` 4K UHD: same algorithm, `uhd1-aacs-` / `uhd2-` prefixes
- [ ] Web UI live at `oviddb.org`: search, disc detail, submit form
- [ ] Auth: email+password, GitHub, Google, Apple OAuth; Mastodon federated login
- [ ] Linked accounts + email-match merge flow
- [ ] Two-contributor verification workflow
- [ ] ARM pull request merged or under active maintainer review
- [ ] Deploy to cloud host (Railway or Fly.io); `api.oviddb.org` live
- [ ] `oviddb.com` / `oviddb.net` → `oviddb.org` redirects live (Cloudflare)
- [ ] Sync feed endpoints: `/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot`
- [ ] Mirror mode: `docker compose --profile mirror up` + `sync.py` daemon
- [ ] Database: ≥500 disc entries
- [ ] Rate limiting and basic spam prevention
- [ ] Integration CI pipeline running against staging
- [ ] **Tag `v0.2.0`; public announcement (GitHub, ARM forums, r/DataHoarder, Doom9)**

*Patch releases `0.2.1`–`0.2.x`: post-launch bug fixes, OAuth edge cases, performance.*

---

### Phase 2 → v0.3.0 — Self-Hosted and Community (Weeks 15–26)

- [ ] Edit history and full audit log in Web UI
- [ ] UPC barcode lookup endpoint
- [ ] Community dispute flagging and resolution workflow
- [ ] Monthly CC0 database dump published to `snapshots.oviddb.org`
- [ ] Self-hosted getting-started guide and one-command installer
- [ ] `docs/sync-spec.md`: formal sync protocol specification
- [ ] Governance model published (`docs/governance.md`)
- [ ] Database: ≥5,000 disc entries
- [ ] **Tag `v0.3.0`**

*Patch releases `0.3.1`–`0.3.x`.*

---

### Phase 3 → v0.4.0 — TV Series and Scale (Weeks 27–40)

- [ ] TV series disc entries with episode-to-title mapping
- [ ] Community voting on conflicting disc entries
- [ ] `ovid-client` Node.js library published to npm
- [ ] Federated node mode: local writes + upstream submission
- [ ] Database: ≥10,000 disc entries
- [ ] **Tag `v0.4.0`**

*Patch releases `0.4.1`–`0.4.x`.*

---

### Stable → v1.0.0

- [ ] All blocking Open Questions resolved
- [ ] API versioning policy frozen (`/v1/` stable; breaking changes go to `/v2/`)
- [ ] Non-profit foundation or fiscal sponsorship in place
- [ ] Full OpenAPI reference auto-generated at `api.oviddb.org/docs`
- [ ] Migration guide for any pre-1.0 API changes
- [ ] **Tag `v1.0.0`; foundation announcement**

---

*Document status: Draft v0.5 · Authors: Project founders · Last updated: 2026-04-01*
