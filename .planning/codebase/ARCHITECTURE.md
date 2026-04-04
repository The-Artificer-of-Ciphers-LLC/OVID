# Architecture

**Analysis Date:** 2026-04-04

## Pattern Overview

**Overall:** Three-tier service architecture with specialized, independent tiers:

1. **Fingerprinting tier** (Python CLI client) — local disc parsing and hash computation
2. **API tier** (FastAPI + PostgreSQL) — centralized disc metadata repository with sync capabilities
3. **Web UI tier** (Next.js 16) — public search, detail viewing, and authenticated submission frontend

**Key Characteristics:**
- Stateless API (horizontal scalability)
- Disc-centric data model with precise schema for structure metadata
- Community contribution + verification workflow (OAuth multi-provider)
- Sync feed for downstream mirrors (monotonic sequence numbers, CC0 snapshots)
- Mirror mode capability (read-only deployment variant)

---

## Layers

**Fingerprinting Layer:**
- Purpose: Parse physical disc formats (DVD, Blu-ray, UHD) and compute stable hash fingerprints
- Location: `ovid-client/src/ovid/`
- Contains: Disc readers (folder, ISO, drive), IFO/MPLS parsers, fingerprint algorithms
- Depends on: `libdvdread`/`libbluray` (system libraries)
- Used by: CLI (`ovid fingerprint`), web submit UI, ARM integration

**API Layer:**
- Purpose: Repository for disc fingerprints, metadata, community verification, and mirroring
- Location: `api/app/`
- Contains: ORM models, route handlers, auth, rate limiting, sync state management
- Depends on: FastAPI, SQLAlchemy, PostgreSQL, Authlib (OAuth)
- Used by: Web UI, CLI lookup/submit, mobile apps, ARM, downstream mirrors

**Web UI Layer:**
- Purpose: Search, discover, and submit disc metadata through interactive interface
- Location: `web/`
- Contains: Next.js App Router pages, components, API client wrapper
- Depends on: Next.js 16, React 19, Tailwind CSS
- Used by: End users, contributors, verifiers

**Data Layer:**
- Purpose: Persistent storage for disc registry, user accounts, edit history, sync state
- Location: `api/alembic/` (migrations)
- Schema: 9 core tables + 3 supporting tables
- Primary keys: UUID v4 throughout

---

## Data Flow

**Fingerprint → Lookup → Enrich:**

1. User runs `ovid fingerprint /path/to/VIDEO_TS` (or submits via web)
2. Client parses IFO/MPLS structure, builds canonical string, hashes to fingerprint
3. Fingerprint queried against `/v1/disc/{fingerprint}` API
4. If found: returns full disc structure (titles, tracks, release metadata, confidence)
5. If not found: user prompted to submit via wizard (requires OAuth login on web)
6. Submission includes: fingerprint, parsed structure, TMDB/IMDB IDs
7. Disc enters "unverified" status, awaits community verification
8. Verified by second contributor → status becomes "verified"

**Submission Write Path:**

```
User submits disc
  ↓
POST /v1/disc (JWT auth, rate limited)
  ↓
Create Disc row (status=unverified, submitted_by=user_id)
Create Release (or link existing)
Create DiscRelease join row
Create DiscTitle rows (one per title)
Create DiscTrack rows (audio/subtitle per title)
Call next_seq() → increment global_seq counter
Stamp all rows with seq_num
  ↓
Return 201 with fingerprint
```

**Mirror Sync Path:**

```
Downstream mirror polls /v1/sync/head
  ↓
Gets current seq_num and timestamp
  ↓
If seq_num > local cache:
  Loop: GET /v1/sync/diff?since=N&limit=1000
    ↓
    Returns paginated disc records with nested titles/tracks/release
    ↓
    Until has_more=false
  ↓
  Incrementally insert/update local mirror database
```

**State Management:**

- **Disc lifecycle:** unverified → disputed → verified (or rejected)
- **Sync state:** Stored in `sync_state` key-value table (snapshot metadata, last_sync timestamp)
- **OAuth state:** Stored in `request.session` (CSRF protection via SessionMiddleware)
- **Rate limit state:** In-memory per-IP counter (slowapi, reset between requests)

---

## Key Abstractions

**Disc:**
- Purpose: Represents a unique physical disc pressing (structural identity)
- Examples: `api/app/models.py:Disc`, `ovid-client/src/ovid/disc.py:Disc`
- Pattern: Immutable once created; inherent structure never changes (DVD pressing is fixed)
- Fingerprint: Deterministic, stable hash of title/chapter/track layout

**DiscTitle:**
- Purpose: A playback title/program on a disc (e.g., main feature, trailer, bonus feature)
- Examples: `api/app/models.py:DiscTitle`, `ovid-client/src/ovid/ifo_parser.py:VTSInfo`
- Contains: Title index, duration, chapter count, track list
- Relationship: 1..* from Disc

**DiscTrack:**
- Purpose: Audio, subtitle, or video stream within a title
- Examples: `api/app/models.py:DiscTrack`
- Metadata: Language, codec, channels, is_default flag
- Relationship: 1..* from DiscTitle

**Release:**
- Purpose: Canonical movie/TV show metadata (TMDB/IMDB linked)
- Examples: `api/app/models.py:Release`
- Pattern: Shared across discs (many-to-many join via `disc_releases`)
- Metadata: Title, year, content_type (movie/tv), TMDB/IMDB IDs

**DiscSet:**
- Purpose: Multi-disc grouping (e.g., "complete series", "box set")
- Examples: `api/app/models.py:DiscSet`
- Relationship: Many discs → 1 release through 1 DiscSet
- Fields: Edition name, total_discs count

**OVIDClient:**
- Purpose: Stateless HTTP wrapper for API calls from CLI and web
- Examples: `ovid-client/src/ovid/client.py:OVIDClient`
- Pattern: Dependency injection of base_url and token (OAuth JWT)
- Methods: lookup(), submit() with error translation to ClickException

---

## Entry Points

**CLI (ovid-client):**
- Location: `ovid-client/src/ovid/cli.py:main()`
- Triggers: `pip install -e ovid-client/ && ovid fingerprint <path>`
- Responsibilities:
  - `ovid fingerprint` — parse disc, output fingerprint
  - `ovid lookup` — query API by fingerprint, render disc structure
  - `ovid submit` — interactive wizard (fingerprint → TMDB search → edition → submit with JWT)

**API Server:**
- Location: `api/main.py:app` (FastAPI instance)
- Triggers: `uvicorn main:app` or `docker compose up api`
- Responsibilities:
  - Route HTTP requests to disc/auth/sync routers
  - Enforce rate limits via slowapi
  - Attach request_id middleware
  - Apply CORS, sessions, mirror-mode guards

**Web UI:**
- Location: `web/app/page.tsx` (Next.js root page)
- Triggers: `npm run dev` or deployed at `https://ovid.example.com`
- Responsibilities:
  - HomePage: Search releases by title/year/pagination
  - DiscPage: Show full disc structure, edit history, dispute form
  - SubmitPage: Upload disc or fingerprint, fill wizard, submit JWT-authenticated POST
  - SettingsPage: OAuth provider linking/unlinking
  - OAuth callback: `/auth/callback?code=...` → exchange for JWT → store in localStorage

---

## Error Handling

**Strategy:** Structured JSON error responses with request_id correlation

**Patterns:**

**API Responses:**
```python
# Success
{ "request_id": "uuid4", "fingerprint": "...", "status": "verified", "confidence": "high", "titles": [...] }

# Error
{ "request_id": "uuid4", "error": "not_found", "message": "No disc found for fingerprint: ..." }
{ "request_id": "uuid4", "error": "rate_limited", "message": "Rate limit exceeded (100 req/hour)" }
{ "request_id": "uuid4", "error": "auth_required", "message": "Missing Bearer token" }
```

**CLI Error Handling:**
- Use `click.ClickException` with structured error messages
- Exit code 1 on failure, 0 on success
- Client.submit() and Client.lookup() raise ClickException on HTTP errors

**Web Error Boundaries:**
- Catch fetch errors in async server components
- Display user-friendly error banner
- Include retry links where appropriate

---

## Cross-Cutting Concerns

**Logging:**
- Framework: Python `logging` (api), JavaScript console (web)
- Level: DEBUG (local), INFO (production)
- Key events: sync_seq_incremented, mirror_mode_blocked, sync_diff (paginated), rate limit hits
- Format: Structured (key=value pairs)

**Validation:**
- API: Pydantic schemas (`api/app/schemas.py`) — strict validation on POST bodies
- CLI: Click argument/option validation
- Web: Fetch error handling with typed response interfaces

**Authentication:**
- Provider: Multi-provider OAuth (GitHub, Apple, Google, Mastodon, IndieAuth)
- Token: JWT stored in localStorage (web) or env var (CLI)
- Flow: OAuth callback → exchange code for token → create/link user
- Scope: Read (lookup, search), Write (submit disc, verify, dispute resolve)

**Rate Limiting:**
- Library: slowapi (async rate limiter)
- Rules: Dynamic per IP/auth (see `_dynamic_limit()` in `app/rate_limit.py`)
- Endpoints: All routes wrapped with `@limiter.limit()`
- Response: 429 JSON with Retry-After header

---

*Architecture analysis: 2026-04-04*
