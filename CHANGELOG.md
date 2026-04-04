# Changelog

All notable changes to OVID are documented in this file.

This project uses [Semantic Versioning](https://semver.org/) in the form `0.MILESTONE.PATCH` during pre-release development. See the [product spec](docs/OVID-product-spec.md) for the versioning scheme.

## [0.1.1] — 2026-04-02

### Fixed
- CI/CD: Upgraded all GitHub Actions to Node 24 versions (checkout v6, setup-python v6, upload/download-artifact v6, Docker actions v4/v7)
- CI/CD: Fixed Docker image name casing for GHCR push (repository owner must be lowercase)
- CI/CD: Fixed artifact download pattern to exclude Docker build records

## [0.1.0] — 2026-04-02

**Foundation & Core Pipeline** — First release. Proves the end-to-end OVID pipeline: DVD fingerprinting from any source, REST API for disc metadata CRUD, OAuth authentication, and an interactive CLI with TMDB integration.

### Added

#### DVD Fingerprinting (`ovid-client`)
- OVID-DVD-1 fingerprint algorithm: SHA-256 of canonical structural string from IFO data
- Pure-Python IFO binary parser — no C dependencies required
- Three source readers: FolderReader (VIDEO_TS directories), ISOReader (ISO 9660 via pycdlib), DriveReader (auto-detect)
- `Disc.from_path()` API for programmatic fingerprinting
- Cross-source identity: folder and ISO of the same disc produce identical fingerprints
- `ovid fingerprint <path>` CLI command

#### REST API (`api/`)
- `GET /v1/disc/{fingerprint}` — disc lookup with nested release, titles, tracks, and confidence field
- `POST /v1/disc` — transactional disc submission with duplicate detection (409)
- `POST /v1/disc/{fingerprint}/verify` — idempotent status promotion (unverified → verified)
- `GET /v1/search?q=&type=&year=&page=` — paginated release search with filters
- `GET /health` — liveness endpoint
- X-Request-ID header on every response for request tracing
- 13 Pydantic request/response schemas with field-level validation

#### Authentication
- JWT token creation/validation (HS256, 30-day expiry)
- GitHub OAuth login/callback
- Apple Sign-In login/callback
- IndieAuth (W3C) login/callback with PKCE and endpoint discovery
- `GET /v1/auth/me` diagnostic endpoint
- Providers return 501 when not configured — API remains functional without OAuth credentials
- Shared `user_upsert` pattern across all providers via UserOAuthLink table

#### CLI Client
- `ovid lookup <fingerprint>` with Rich-formatted metadata display
- `ovid submit <path>` interactive wizard: fingerprint → TMDB search → pick release → edition/disc# → submit
- `OVIDClient` HTTP wrapper for programmatic API access
- TMDB integration with graceful degradation (manual entry fallback when API key absent)

#### Database
- 9-table PostgreSQL schema via Alembic migration: discs, releases, disc_releases, disc_titles, disc_tracks, disc_sets, users, user_oauth_links, disc_edits
- 25 indexes including partial indexes on nullable columns
- UUID primary keys, timezone-aware timestamps
- Idempotent seed script with Matrix (1999) test data

#### Infrastructure
- Docker Compose stack: PostgreSQL 16-alpine + FastAPI with hot-reload
- `.env.example` with all configuration variables
- Auto-generated API docs at `/docs` (Swagger) and `/redoc` (ReDoc)

#### Documentation
- OVID-DVD-1 fingerprint algorithm specification (`docs/fingerprint-spec.md`)
- API reference (`docs/api-reference.md`)
- CLI reference (`docs/cli-reference.md`)
- Developer getting-started guide (`docs/getting-started-dev.md`)
- Docker quick-start guide (`docs/docker-quickstart.md`)
- GitHub issue and PR templates

#### Testing
- 241 tests total across 3 test suites
- ovid-client: 113 passed + 9 skipped (real-disc tests gated by env var)
- API: 124 passed (69 auth-specific)
- E2E: 4 pipeline round-trip tests
- 8 synthetic disc fixture profiles with 100× determinism checks
- Cross-source identity proof (folder vs ISO)
- Fingerprint uniqueness proof (all fixtures produce different fingerprints)

### Known Limitations
- No Blu-ray fingerprinting yet (planned for v0.2.0)
- No web UI yet (planned for v0.2.0)
- No rate limiting (planned for v0.2.0)
- Apple Sign-In uses ID token decoding without JWKS verification — safe for direct HTTPS, needs hardening before production deployment
- Search uses SQL `ilike` — adequate at current scale, needs full-text search index at volume
- DriveReader on macOS requires a mounted volume or ISO — direct /dev/diskN not tested on real hardware
- Not published to PyPI yet (planned for v0.2.0)

## [0.2.0] — 2026-04-04

**Soft Launch** — oviddb.org is live. Adds Blu-ray/UHD fingerprinting, a Next.js web UI, five OAuth providers with account linking, sync/mirror protocol, rate limiting, dispute resolution, ARM integration, and public production deployment via Cloudflare.

### Added

#### Blu-ray & UHD Fingerprinting (`ovid-client`)
- OVID-BD-1 fingerprint algorithm: two-tier approach — AACS key file (Tier 1) with MPLS structure hash fallback (Tier 2)
- Pure-Python MPLS binary parser — no native dependencies required
- BD folder reader for BDMV directory structures with case-insensitive lookup
- 4K UHD disc support via `uhd1-aacs-*` / `uhd2-*` fingerprint prefixes
- Obfuscation playlist filtering — skips fake playlists (< 60 s) used as copy protection
- `ovid fingerprint /path/to/BDMV` CLI support with Tier metadata in JSON output
- AACS Tier 1 attempted before 60-second playlist filter — handles discs with all-short playlists

#### OAuth & Account Linking
- Google OAuth login/callback
- Mastodon OAuth login/callback with per-instance dynamic client registration
- Account linking: multiple OAuth providers per user, matched by email
- `GET /v1/auth/providers` — list linked OAuth providers for the current user
- `DELETE /v1/auth/providers/{provider}` — unlink a provider (cannot unlink the last one)
- Apple Sign-In JWKS verification — tokens validated against Apple's published JSON Web Key Set
- Shared `finalize_auth()` convergence point handling user upsert, linking, and JWT creation for all five providers

#### API Enhancements
- CORS middleware with configurable allowed origins via `CORS_ORIGINS` env var (positioned before SessionMiddleware)
- Community verification workflow: second contributor with matching fingerprint auto-promotes disc to verified
- Metadata conflict detection: conflicting submissions flagged as disputed, surfaced via `GET /v1/disc/disputed`
- `POST /v1/disc/{fingerprint}/resolve` — dispute resolution endpoint
- `GET /v1/disc/{fingerprint}/edits` — edit history endpoint
- `GET /v1/disc/upc/{upc}` — UPC barcode lookup endpoint
- `submitted_by` tracking on all disc submissions

#### Sync & Mirror Protocol
- `GET /v1/sync/head` — returns current global sequence number and timestamp
- `GET /v1/sync/diff?since={seq}` — returns all disc records since a given sequence
- `GET /v1/sync/snapshot` — full CC0 database snapshot dump
- `scripts/sync.py` polling daemon with upsert logic for mirror operators
- `GlobalSeq` single-row counter table with per-disc `seq_num` columns for incremental sync
- Mirror mode middleware (`OVID_MODE=mirror`) — read-only API that proxies writes to upstream

#### Rate Limiting
- Per-endpoint rate limits via `slowapi` decorator pattern (not SlowAPIMiddleware)
- Auth-aware thresholds: 100/min authenticated, 20/min anonymous
- Returns 429 with `Retry-After` header on limit breach

#### Next.js Web UI (`web/`)
- Server-rendered disc browsing and search via `GET /v1/search`
- Disc detail pages: full structure (titles, tracks, chapters) for DVD and Blu-ray
- All five OAuth provider login flows via the web UI (`/auth/callback` token handler)
- Fingerprint JSON file upload for disc submission
- Account settings page with linked provider management
- Dispute resolution UI at `/disputes`
- `Suspense` wrapper on all `useSearchParams()` usages (Next.js 16 App Router requirement)

#### ARM Integration (`arm/`)
- `arm/identify.py` shim: OVID-first fingerprint lookup with importlib delegation to original ARM identify
- `arm/identify_ovid.py`: never-raise wrapper — catches all exceptions, hard 5-second timeout on API calls
- `arm/entrypoint_wrapper.sh`: extracts original `identify.py` from Docker image before overlay mounts shadow it
- `arm/start_arm_container.sh`: bridge-primary / ovid_default-secondary dual-network setup for ARM
- `_ensure_mounted()` with retry loop (6× @ 2 s) and `findmnt -M` verification — handles optical drive spinup race condition

#### Production Deployment
- TLS certificates for oviddb.org and api.oviddb.org via Let's Encrypt (ECDSA, valid through 2026-06-30)
- Cloudflare proxy (orange cloud) routing to redshirt nginx via Full (strict) TLS
- redshirt nginx vhosts proxying to holodeck production stack (ports 3100/8100)
- `docker-compose.prod.yml` override with `!override` port replacement and source-mount removal
- All five OAuth providers configured with `https://api.oviddb.org` callback URLs
- oviddb.org is publicly accessible — soft launch

### Fixed
- CLI binary builds include Blu-ray module hidden imports for PyInstaller
- `arm/identify.py` mount race condition: retry loop + `findmnt` verification replaces single blind `mount` call
- Docker Compose override files use `ports: !override` to prevent base + override port merge
- `docker-compose.prod.yml` `OVID_API_URL` and web build arg gaps

### Known Limitations
- Search uses SQL `ilike` — adequate at current scale, needs full-text search index at volume
- DriveReader on macOS requires a mounted volume or ISO — direct `/dev/diskN` not tested on real hardware
- Google OAuth requires HTTPS; not available until M005 (production TLS) — now resolved
- Apple Sign-In not yet tested end-to-end in production (returns 501)

[0.2.0]: https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases/tag/v0.2.0
[0.1.2]: https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases/tag/v0.1.2
[0.1.1]: https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases/tag/v0.1.1
[0.1.0]: https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases/tag/v0.1.0
