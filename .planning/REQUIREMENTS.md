# Requirements: OVID v0.3.0 — Beta to Public Launch

**Defined:** 2026-04-04
**Core Value:** When a disc is inserted, OVID identifies it by structure and returns the full disc layout so ripping tools know what's on the disc.

## v1 Requirements

Requirements for the 0.3.0 milestone. Each maps to roadmap phases.

### Security Hardening

- [ ] **SEC-01**: Auth flow uses authorization code exchange or HttpOnly cookie instead of JWT in URL query params
- [ ] **SEC-02**: Mastodon domain validation prevents DNS rebinding attacks (pin resolved IP)
- [ ] **SEC-03**: JWT secret key validated at startup (length ≥32 bytes, entropy check)
- [ ] **SEC-04**: Apple Sign-In private key validated at startup with clear error on misconfiguration
- [ ] **SEC-05**: OAuth client secrets never included in API error responses
- [ ] **SEC-06**: Apple Sign-In works end-to-end in production (fix 501)

### Bug Fixes

- [ ] **BUG-01**: Mastodon placeholder email includes instance domain to prevent collision (format: `mastodon_{domain}_{account_id}@noemail.placeholder`)
- [ ] **BUG-02**: Disc status transitions validated against allowed state machine (unverified→verified, unverified→disputed, disputed→verified, disputed→unverified)
- [ ] **BUG-03**: Mastodon dynamic registration uses ON CONFLICT or advisory lock to prevent race condition
- [ ] **BUG-04**: Disc submission catches specific exceptions (IntegrityError, ValidationError) instead of bare Exception
- [ ] **BUG-05**: Mastodon OAuth client cache has expiry mechanism (expires_at + cleanup job)

### Infrastructure

- [ ] **INFRA-01**: Redis 7 added to Docker Compose stack
- [ ] **INFRA-02**: Rate limiting migrated from in-memory to Redis-backed storage (slowapi storage_uri)
- [ ] **INFRA-03**: Rate limiting degrades gracefully (permit all requests) if Redis is unavailable
- [ ] **INFRA-04**: Redis not required in development (fallback to memory:// when REDIS_URL unset)

### Multi-Disc Sets

- [ ] **SET-01**: `POST /v1/set` creates a disc set record (release_id, edition_name, total_discs)
- [ ] **SET-02**: `GET /v1/set/{set_id}` returns set with all member discs
- [ ] **SET-03**: `POST /v1/disc` accepts optional `disc_set_id`, validates disc_number ≤ total_discs
- [ ] **SET-04**: `GET /v1/disc/{fingerprint}` includes sibling discs when part of a set
- [ ] **SET-05**: `disc_sets` table gets `seq_num` column for sync feed parity
- [ ] **SET-06**: Web UI disc detail page shows sibling discs in a set
- [ ] **SET-07**: Web UI submission form has multi-disc toggle revealing disc number and set fields
- [ ] **SET-08**: CLI `ovid submit` wizard prompts for set membership when disc_number > 1

### Chapter Names

- [ ] **CHAP-01**: New `disc_chapters` table (disc_title_id, chapter_index, name, start_time_secs) with unique constraint on (disc_title_id, chapter_index)
- [ ] **CHAP-02**: `ChapterResponse` and `ChapterCreate` Pydantic schemas
- [ ] **CHAP-03**: `POST /v1/disc` accepts chapter data in title submissions (default empty list, backward-compatible)
- [ ] **CHAP-04**: `GET /v1/disc/{fingerprint}` returns chapter data eagerly loaded with titles
- [ ] **CHAP-05**: Sync feed schemas include chapter data so mirrors stay current
- [ ] **CHAP-06**: Web UI disc detail page shows chapter names under each title when present
- [ ] **CHAP-07**: Web UI submission form has optional chapter name entry per title (expandable section)
- [ ] **CHAP-08**: CLI `ovid submit` wizard offers optional chapter name step
- [ ] **CHAP-09**: Blu-ray fingerprinting extracts MPLS chapter timestamps (start_time_secs) during scan
- [ ] **CHAP-10**: Blu-ray fingerprinting parses `bdmt_*.xml` for disc title and title names when present

### Sync and Mirror Hardening

- [ ] **SYNC-01**: Snapshot generation script produces NDJSON + gzip + SHA-256 checksum file
- [ ] **SYNC-02**: `/v1/sync/snapshot` returns URL to latest snapshot with metadata (seq, size, record_count, sha256)
- [ ] **SYNC-03**: New mirrors bootstrap from snapshot before pulling diffs
- [ ] **SYNC-04**: Diff sync verifies monotonic sequence numbers and rejects out-of-order records
- [ ] **SYNC-05**: Sync daemon retries with exponential backoff on transient failures
- [ ] **SYNC-06**: All sync-tracked tables (including disc_sets, disc_chapters) have seq_num columns
- [ ] **SYNC-07**: Snapshots hosted at snapshots.oviddb.org (static file serving)
- [ ] **SYNC-08**: Monthly CC0 database dump published (PostgreSQL dump + NDJSON)

### CLI Scanner Tool

- [ ] **CLI-01**: `ovid scan /dev/sr0` (or mount path) — auto mode: mount, fingerprint, check OVID, auto-submit structure if miss
- [ ] **CLI-02**: `ovid scan --wizard /dev/sr0` — guided mode: prompt for TMDB match, edition name, disc number before submit
- [ ] **CLI-03**: `ovid scan --batch /path/to/isos` — batch mode: scan folder of ISOs, submit all misses in one run
- [ ] **CLI-04**: Auto mode extracts bdmt_*.xml disc title and MPLS chapter timestamps when available
- [ ] **CLI-05**: `ovid-client` published to PyPI under the name `ovid-client`
- [ ] **CLI-06**: Platform-specific install docs for macOS (Homebrew deps) and Linux (apt/dnf deps)

### Web UI Completeness

- [ ] **WEB-01**: All features surfaced on www.oviddb.org (functional, not polished)
- [ ] **WEB-02**: Manual disc lookup by fingerprint or title search
- [ ] **WEB-03**: Edit/correct existing disc entries (authenticated)
- [ ] **WEB-04**: Dispute resolution: flag a disc entry, moderator resolves with audit trail
- [ ] **WEB-05**: Set management: create set, view set, link discs to set
- [ ] **WEB-06**: Chapter name display and entry
- [ ] **WEB-07**: Provider linking/unlinking in account settings
- [ ] **WEB-08**: Full submission flow with all new fields (set membership, chapters, bdmt metadata)
- [ ] **WEB-09**: Edit history visible on disc detail page (who changed what, when)

### Performance

- [ ] **PERF-01**: k6 load test suite (smoke, load, stress scenarios) in repository
- [ ] **PERF-02**: API responds ≤500ms at p95 under 100 concurrent users
- [ ] **PERF-03**: Load test integrated into release checklist (manual or CI)

### Documentation

- [ ] **DOC-01**: Self-hosted getting-started guide (`docs/self-hosting.md`)
- [ ] **DOC-02**: Sync protocol specification (`docs/sync-spec.md`)
- [ ] **DOC-03**: Moderation guide (`docs/moderation.md`)
- [ ] **DOC-04**: Data dump format reference (`docs/dump-format.md`)
- [ ] **DOC-05**: Governance model (`docs/governance.md`)
- [ ] **DOC-06**: Data licensing explainer / CC0 FAQ (`docs/data-license.md`)

### Launch

- [ ] **LAUNCH-01**: Database seeded to ≥500 real disc entries
- [ ] **LAUNCH-02**: Public announcement drafted for GitHub, ARM forums, r/DataHoarder, Doom9
- [ ] **LAUNCH-03**: Announcement posted to all channels

## v2 Requirements

Deferred to v0.4.0 or later. Tracked but not in current roadmap.

### Community Governance

- **GOV-01**: Community voting on conflicting disc entries (MusicBrainz edit-voting model)
- **GOV-02**: Trusted contributor tier with elevated permissions
- **GOV-03**: Gamification / reputation system

### Extended Format Support

- **FMT-01**: TV series disc entries with episode-to-title mapping
- **FMT-02**: JavaScript/Node client library published to npm
- **FMT-03**: Federated node mode (local writes + upstream submission)

### Auth Expansion

- **AUTH-01**: Email + password account creation
- **AUTH-02**: Password reset via email link
- **AUTH-03**: Email verification flow

### Advanced Enrichment

- **ENRICH-01**: PGS/VobSub AI OCR community tool for chapter name extraction
- **ENRICH-02**: DVD menu capture via libdvdnav for chapter names (power users)
- **ENRICH-03**: HandBrake --scan --json integration for ARM pre-population

## Out of Scope

| Feature | Reason |
|---------|--------|
| Storing video content or disc images | Legal liability; metadata database only |
| Replacing TMDB/OMDb for movie metadata | OVID handles disc identity; existing APIs handle movie details |
| LaserDisc, VHS, HD-DVD support | Small audience; focus on DVD/BD/UHD first |
| Consumer movie browsing UI | OVID is infrastructure for tools like ARM |
| DRM circumvention or key storage | Explicitly excluded for legal reasons |
| Visual UI polish for 0.3.0 | Functional completeness first; polish in 0.4.0+ |
| PyInstaller/Nuitka binary distribution | C library deps (libdvdread, libbluray) can't be bundled; PyPI is correct path |
| BD-J menu capture for chapter names | Requires Java runtime; not automatable |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SEC-01 | Phase 1 | Pending |
| SEC-02 | Phase 1 | Pending |
| SEC-03 | Phase 1 | Pending |
| SEC-04 | Phase 1 | Pending |
| SEC-05 | Phase 1 | Pending |
| SEC-06 | Phase 1 | Pending |
| BUG-01 | Phase 1 | Pending |
| BUG-02 | Phase 1 | Pending |
| BUG-03 | Phase 1 | Pending |
| BUG-04 | Phase 1 | Pending |
| BUG-05 | Phase 1 | Pending |
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| SET-01 | Phase 2 | Pending |
| SET-02 | Phase 2 | Pending |
| SET-03 | Phase 2 | Pending |
| SET-04 | Phase 2 | Pending |
| SET-05 | Phase 2 | Pending |
| SET-06 | Phase 2 | Pending |
| SET-07 | Phase 2 | Pending |
| SET-08 | Phase 2 | Pending |
| CHAP-01 | Phase 2 | Pending |
| CHAP-02 | Phase 2 | Pending |
| CHAP-03 | Phase 2 | Pending |
| CHAP-04 | Phase 2 | Pending |
| CHAP-05 | Phase 2 | Pending |
| CHAP-06 | Phase 2 | Pending |
| CHAP-07 | Phase 2 | Pending |
| CHAP-08 | Phase 2 | Pending |
| CHAP-09 | Phase 2 | Pending |
| CHAP-10 | Phase 2 | Pending |
| SYNC-01 | Phase 3 | Pending |
| SYNC-02 | Phase 3 | Pending |
| SYNC-03 | Phase 3 | Pending |
| SYNC-04 | Phase 3 | Pending |
| SYNC-05 | Phase 3 | Pending |
| SYNC-06 | Phase 3 | Pending |
| SYNC-07 | Phase 3 | Pending |
| SYNC-08 | Phase 3 | Pending |
| CLI-01 | Phase 4 | Pending |
| CLI-02 | Phase 4 | Pending |
| CLI-03 | Phase 4 | Pending |
| CLI-04 | Phase 4 | Pending |
| CLI-05 | Phase 4 | Pending |
| CLI-06 | Phase 4 | Pending |
| WEB-01 | Phase 5 | Pending |
| WEB-02 | Phase 5 | Pending |
| WEB-03 | Phase 5 | Pending |
| WEB-04 | Phase 5 | Pending |
| WEB-05 | Phase 5 | Pending |
| WEB-06 | Phase 5 | Pending |
| WEB-07 | Phase 5 | Pending |
| WEB-08 | Phase 5 | Pending |
| WEB-09 | Phase 5 | Pending |
| DOC-01 | Phase 5 | Pending |
| DOC-02 | Phase 5 | Pending |
| DOC-03 | Phase 5 | Pending |
| DOC-04 | Phase 5 | Pending |
| DOC-05 | Phase 5 | Pending |
| DOC-06 | Phase 5 | Pending |
| PERF-01 | Phase 6 | Pending |
| PERF-02 | Phase 6 | Pending |
| PERF-03 | Phase 6 | Pending |
| LAUNCH-01 | Phase 6 | Pending |
| LAUNCH-02 | Phase 6 | Pending |
| LAUNCH-03 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 62 total
- Mapped to phases: 62
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after initial definition*
