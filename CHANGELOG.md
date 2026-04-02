# Changelog

All notable changes to OVID are documented in this file.

This project uses [Semantic Versioning](https://semver.org/) in the form `0.MILESTONE.PATCH` during pre-release development. See the [product spec](docs/OVID-product-spec.md) for the versioning scheme.

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

[0.1.0]: https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases/tag/v0.1.0
