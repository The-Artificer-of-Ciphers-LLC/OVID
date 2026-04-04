# OVID — Open Video Disc Identification Database

## What This Is

OVID is an open, community-driven database that uniquely identifies physical DVD, Blu-ray, and 4K UHD discs by their structural fingerprint and maps them to rich release metadata — disc layout, title/chapter structure, audio/subtitle tracks, and edition information. It is to video discs what MusicBrainz is to audio CDs. The primary integration target is the Automatic Ripping Machine (ARM) and similar home media ripping tools.

## Core Value

When a disc is inserted into any optical drive, OVID identifies it by structure — not by unreliable disc labels — and returns the full disc layout so ripping tools know which title is the main feature, what edition it is, and what audio/subtitle tracks are available. If this doesn't work, nothing else matters.

## Requirements

### Validated

<!-- Shipped and confirmed working as of v0.2.0. -->

- ✓ DVD fingerprint (OVID-DVD-1) from IFO structure — v0.1.0
- ✓ Blu-ray fingerprint Tier 1 (AACS Disc ID) — v0.2.0
- ✓ Blu-ray fingerprint Tier 2 (BDMV/PLAYLIST structure hash) — v0.2.0
- ✓ Same disc always produces the same fingerprint on any drive/OS — validated in tests
- ✓ `GET /v1/disc/{fingerprint}` returns metadata or 404 — v0.1.0
- ✓ Response includes: title, year, edition, disc number, main feature index, format — v0.1.0
- ✓ Response includes: per-title metadata (duration, chapters, audio, subtitles) — v0.1.0
- ✓ Confidence field returned with each match — v0.1.0
- ✓ `POST /v1/disc` authenticated disc submission — v0.1.0
- ✓ Submitted entries marked `unverified` until second contributor confirms — v0.2.0
- ✓ UPC barcode field and lookup endpoint — v0.2.0
- ✓ 9-table PostgreSQL schema (Disc, Release, DiscTitle, DiscTrack, User, UserIdentity, DiscEdit, DiscSet, MastodonOAuthClient) — v0.1.0+
- ✓ Web UI: search by movie title — v0.2.0
- ✓ Web UI: view disc entry full structure — v0.2.0
- ✓ Web UI: submit disc via web form (JSON file upload) — v0.2.0
- ✓ GitHub OAuth login — v0.1.0
- ✓ Google OAuth login — v0.2.0
- ✓ Mastodon / ActivityPub federated login — v0.2.0
- ✓ IndieAuth decentralized login — v0.2.0
- ✓ Multiple OAuth providers linkable to one account — v0.2.0
- ✓ Account settings: view and remove linked providers — v0.2.0
- ✓ Email-match merge (prevent duplicate accounts) — v0.2.0
- ✓ Sync feed endpoints: `/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot` — v0.2.0
- ✓ `POST /v1/disc/register` fingerprint-only registration for ARM — v0.2.0
- ✓ Auto-submit disc to OVID on miss from ARM — v0.2.0
- ✓ Docker Compose dev environment — v0.1.0
- ✓ CI pipeline: lint, unit tests, fingerprint regression — v0.1.0
- ✓ Rate limiting (slowapi, per-IP) — v0.2.0
- ✓ Domain redirects: oviddb.com and oviddb.net → oviddb.org — done

### Active

<!-- Current scope: Milestone 0.3.0 — Beta to Public Launch. -->

**Bug Fixes & Security (P0 — fix before beta):**
- [ ] Fix Apple Sign-In (returns 501 in production — built but not tested end-to-end)
- [ ] Fix JWT token passed in URL redirect query params (should be POST body or auth code flow)
- [ ] Fix placeholder email collision for Mastodon users on different instances with same account_id
- [ ] Fix disc status transition allowing invalid state changes (no state machine validation)
- [ ] Fix race condition in Mastodon dynamic registration (concurrent requests cause 500)
- [ ] Fix broad exception handling in disc submission (catches bare Exception, swallows errors)
- [ ] Fix Apple private key parsing silent failure (should validate at startup)
- [ ] Fix JWT secret key not validated at startup (should check length/entropy)
- [ ] Fix Mastodon domain validation incomplete (DNS rebinding, instance blocklist)
- [ ] Fix OAuth client secrets potentially logged in error messages
- [ ] Fix in-memory rate limiting broken with multiple workers — migrate to Redis

**Features — CLI Scanner Tool (P0):**
- [ ] `ovid scan` command: insert disc → mount → fingerprint → check OVID → auto-submit if miss (minimal prompts)
- [ ] `ovid scan --wizard` mode: guided flow with TMDB match, edition name prompts
- [ ] `ovid scan --batch /path/to/isos` mode: scan folder of ISOs, submit all misses
- [ ] Mac and Linux binary distribution (require system libraries installed separately)

**Features — Multi-Disc Set Support (P0 — beta required):**
- [ ] `POST /v1/set` — create a disc set record
- [ ] `GET /v1/set/{set_id}` — retrieve set with all member discs
- [ ] Update `POST /v1/disc` to accept optional `disc_set_id`
- [ ] Update `GET /v1/disc/{fingerprint}` to include sibling discs when part of a set
- [ ] Add `seq_num` column to `disc_sets` table for sync feed parity
- [ ] Web UI: disc detail page shows sibling discs
- [ ] Web UI: submission form multi-disc toggle
- [ ] CLI: `ovid submit` wizard prompts for set membership

**Features — Chapter Name Data (P0 — beta required):**
- [ ] New `disc_chapters` table (disc_title_id, chapter_index, name, start_time_secs)
- [ ] `ChapterResponse` and `ChapterCreate` schemas
- [ ] Update `POST /v1/disc` to accept chapter data
- [ ] Update `GET /v1/disc/{fingerprint}` to return chapter data
- [ ] Update sync feed schemas to include chapters
- [ ] Web UI: show chapter names on disc detail page
- [ ] Web UI: optional chapter name entry in submission form
- [ ] CLI: optional chapter name step in submit wizard

**Features — Self-Hosted Node Hardening (P0):**
- [ ] Snapshot generation and hosting at snapshots.oviddb.org
- [ ] `docker compose --profile mirror up` fully documented and tested
- [ ] Sync protocol hardening (error recovery, partial sync resume, integrity checks)
- [ ] One-command self-hosted installer or setup script

**Features — PyPI Publication (P0 — before beta):**
- [ ] Publish `ovid-client` to PyPI as `ovid-client`
- [ ] `pip install ovid-client` works end-to-end

**Features — Email + Password Auth (P1 — post-beta):**
- [ ] Email + password account creation
- [ ] Password reset via email link
- [ ] Email verification flow

**Features — Web UI Functional Completeness (P0):**
- [ ] All features surfaced on www.oviddb.org (functional, not necessarily polished)
- [ ] Manual disc lookup by fingerprint
- [ ] Edit/correct existing disc entries
- [ ] Dispute resolution workflow
- [ ] Set management (create, view, link discs)
- [ ] Chapter name entry/display
- [ ] Provider linking/unlinking in account settings
- [ ] Full submission flow with all new fields

**Performance & Reliability:**
- [ ] Add Redis to Docker Compose stack for rate limiting
- [ ] Migrate slowapi to Redis-backed storage
- [ ] Load test suite (Locust or k6) confirming ≤500ms p95
- [ ] API performance verified under realistic load

**Documentation (all for 0.3.0):**
- [ ] Self-hosted getting-started guide (`docs/self-hosting.md`)
- [ ] Sync protocol specification (`docs/sync-spec.md`)
- [ ] Moderation guide (`docs/moderation.md`)
- [ ] Data dump format reference (`docs/dump-format.md`)
- [ ] Governance model (`docs/governance.md`)
- [ ] Data licensing explainer / CC0 FAQ (`docs/data-license.md`)
- [ ] Edit history and audit log documentation

**Operational:**
- [ ] Database seeded to ≥500 real disc entries (from founder's collection + ARM + CLI scanner)
- [ ] Monthly CC0 database dump published
- [ ] Public announcement drafted and posted (GitHub, ARM forums, r/DataHoarder, Doom9)

### Out of Scope

- Storing actual video content or disc images — legal liability; metadata only
- Replacing TMDB/OMDb for movie metadata (plot, cast, ratings) — OVID handles disc identity; existing APIs handle movie details
- LaserDisc, VHS, or HD-DVD support — small audience; focus on DVD/BD/UHD
- Consumer-facing movie browsing UI — OVID is infrastructure for tools like ARM
- Real-time pricing, availability, or streaming links — other services handle this
- DRM circumvention or decryption key storage — explicitly out of scope for legal reasons
- TV series episode-to-title mapping — deferred to v0.4.0
- Community voting on conflicting entries (MusicBrainz edit-voting) — deferred to v0.4.0
- JavaScript/Node client library — deferred to v0.4.0
- Federated node mode (local writes + upstream submission) — deferred to v0.4.0
- Mobile barcode scanning app — deferred to future
- Visual UI polish — functional completeness first, polish later

## Context

**Current state:** v0.2.0 "Soft Launch" released 2026-04-04. Three-tier architecture (ovid-client Python library, FastAPI API, Next.js web UI) with PostgreSQL. All running on Docker Compose. Deployed to holodeck.nomorestars.com.

**Existing codebase:** ~1,963 lines of codebase documentation in `.planning/codebase/`. The API has 9 core ORM models, OAuth for 5 providers (GitHub, Google, Apple, Mastodon, IndieAuth), sync feed endpoints, rate limiting, and full disc CRUD. The client library handles DVD and Blu-ray fingerprinting with multiple reader backends (folder, ISO, drive).

**Database:** Under 100 disc entries currently. Founder plans to seed from personal collection using ARM auto-submit and the new CLI scanner tool. Target: ≥500 before public announcement.

**Known technical debt:** 11 bugs/security issues identified in codebase concerns analysis. All targeted for fix before beta.

**ARM integration:** Auto-submit on miss feature already shipped. ARM PR is the primary adoption channel.

**Deployment:** holodeck.nomorestars.com is the dev/prod server with Docker, SSH, and sudo access.

## Constraints

- **License**: AGPL-3.0 for code; CC0 for all submitted disc metadata
- **Dependencies**: C libraries (libdvdread, libbluray, libaacs) required for disc reading — installed separately by users
- **Hosting**: Single server (holodeck.nomorestars.com) for now; no distributed architecture needed at current scale
- **Database**: PostgreSQL 16; all queries via SQLAlchemy ORM with parameterized statements
- **Auth**: JWT (1-hour access, 30-day refresh); OAuth tokens encrypted at rest (AES-256-GCM)
- **API contract**: Read endpoints unauthenticated; write endpoints require Bearer token
- **Fingerprint stability**: Algorithm changes require version bump (dvd2- prefix), never modify existing algorithm output
- **Git strategy**: Gitflow model (main, develop, feature/*, release/*, hotfix/*); conventional commits
- **Multi-language workspace**: Python (API, client), TypeScript (web UI), Swift/iOS (future). Match tooling to component language.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| OAuth-only auth at launch (no email/password) | Reduces security surface; target audience has GitHub/Google | — Pending (email auth deferred to P1) |
| IndieAuth instead of Mastodon-only for fediverse | Broader compatibility (Mastodon, Pleroma, Akkoma, Pixelfed) | ✓ Good |
| AGPL-3.0 license | Ensures self-hosted forks contribute back | ✓ Good |
| CC0 for data, not ODbL | Maximum downstream flexibility; matches MusicBrainz model | ✓ Good |
| Redis for rate limiting | In-memory rate limiting broken with multiple workers | — Pending |
| Structural fingerprint over timestamp-based | dvdid's timestamp approach breaks on copies/ISOs; OVID reads logical structure only | ✓ Good |
| Two-tier BD fingerprint (AACS preferred, BDMV fallback) | AACS is industry standard but requires libaacs; BDMV works without it | ✓ Good |
| Next.js for web UI over HTMX | Better for interactive editor UIs and future feature complexity | — Pending |
| Functional web UI over polished design | Surface all features first; visual polish is later | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-04 after initialization*
