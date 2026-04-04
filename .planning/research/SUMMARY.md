# Project Research Summary

**Project:** OVID -- Open Video Disc Identification Database
**Domain:** Community-driven physical disc metadata database (MusicBrainz-style registry)
**Researched:** 2026-04-04
**Confidence:** HIGH

## Executive Summary

OVID is a community disc identification database transitioning from alpha (v0.2.0) to public beta (v0.3.0). The comparable system is MusicBrainz, and the research confirms that OVID's existing architecture -- stateless FastAPI API, PostgreSQL, Next.js web UI, Python CLI -- is sound and needs targeted additions rather than rearchitecting. The primary stack additions are Redis (for broken rate limiting), pwdlib (for future email auth), and k6 (for load testing). The existing tech choices are correct; no replacements are needed.

The critical path to beta is a security hardening sprint followed by data model expansion (multi-disc sets, chapter names), sync protocol hardening, and the CLI scanner tool that will seed the database. Six critical pitfalls were identified in the codebase, all in existing code: JWT tokens leaked via URL query params, race conditions in Mastodon registration, DNS rebinding SSRF, swallowed exceptions in disc submission, completely broken rate limiting with multiple workers, and placeholder email collisions. Every one of these must be fixed before any public user touches the system. They are not theoretical -- they are bugs in shipped code that will cause failures at beta scale.

The recommended approach is to fix all P0 security and bug issues first (Phase 1), then build out the data model and API surface (Phase 2), harden the sync/mirror infrastructure (Phase 3), ship the CLI scanner for database seeding (Phase 4), build moderation tooling and documentation (Phase 5), and validate everything with load testing before announcement (Phase 6). Email+password auth is correctly deferred to post-beta. The overall research confidence is high: the stack choices are well-documented, the architecture follows proven MusicBrainz patterns, and the pitfalls are derived from direct codebase analysis.

## Key Findings

### Recommended Stack

No major technology replacements are needed. The existing FastAPI + PostgreSQL + Next.js stack is appropriate. Three additions are required for 0.3.0, all additive.

**Core additions:**
- **Redis 7 (Alpine)**: Shared rate limit storage across gunicorn workers -- one-line config change in slowapi, 12MB Docker image. Fallback to `memory://` in dev keeps local workflow frictionless.
- **k6 (Grafana)**: Load testing -- standalone Go binary, CI-native with threshold-based pass/fail, no Python dependency conflicts. Replaces the Locust suggestion in PROJECT.md.
- **pwdlib[argon2,bcrypt]**: Password hashing for P1 email auth -- replaces the unmaintained passlib. FastAPI's official recommendation as of 2026.

**Distribution decision (settled):** PyPI + platform-specific install docs. PyInstaller/Nuitka/cx_Freeze are wrong because they cannot bundle the C libraries (libdvdread, libbluray) that users need regardless. Homebrew formula is a nice-to-have for macOS.

**What NOT to change:** slowapi stays (Redis is a config change, not a library swap). passlib is replaced by pwdlib only when email auth ships. No new ORMs, no new frameworks, no new databases.

### Expected Features

**Must have (table stakes for beta credibility):**
- Multi-disc set grouping -- box sets are 20-30% of Blu-ray releases, data model already exists, needs API/UI surface
- Edit history / audit trail -- contributors must see who changed what; trust depends on transparency
- Database dumps (CC0 NDJSON) -- the social contract of open data; must be downloadable before announcement
- Sync feed hardening -- integrity checksums, snapshot bootstrap, error recovery for mirrors
- CLI scanner tool -- primary database seeding mechanism; three modes (auto, wizard, batch)
- Basic dispute mechanism -- flag, moderator resolves, audit trail; no voting system at this scale

**Should have (differentiators unique to OVID):**
- Chapter name data -- no other public database stores video disc chapter names; novel value
- Structural fingerprinting (already shipped) -- the core differentiator; protect algorithm stability
- ARM-native integration (already shipped) -- makes OVID the default disc database for the largest open-source ripper
- Two-contributor verification (already shipped) -- simpler than MusicBrainz voting, appropriate for small community

**Defer past beta:**
- Email+password auth -- OAuth covers the ARM/DataHoarder audience; ship post-beta as P1
- TV series episode-to-title mapping -- data model complexity is too high for 0.3.0
- MusicBrainz-style edit voting -- no quorum at <100 contributors; counterproductive
- Gamification / reputation -- incentivizes quantity over quality at small scale
- Federated node mode (local writes + upstream) -- distributed consensus is out of scope

### Architecture Approach

The architecture remains a three-tier stateless design. Redis enters strictly as a rate-limiting backing service, not as a general-purpose cache or session store. The API must degrade gracefully (permit all requests) if Redis goes down. Every new user-contributed table (disc_chapters, disc_sets) gets a `seq_num` column and inclusion in the sync feed -- missing a table from sync means mirrors have incomplete data permanently. The CLI scanner follows a pipeline pattern (mount, fingerprint, lookup, enrich, submit) with three modes composed from shared functions, not class hierarchies.

**Major components:**
1. **API (FastAPI)** -- disc CRUD, auth, sync feed, rate limiting; stateless, Redis for shared counters
2. **Web UI (Next.js)** -- search, submit, settings, edit history; consumes API only
3. **CLI (ovid-client)** -- fingerprint, lookup, submit, scan modes; calls local disc libraries + API
4. **PostgreSQL** -- sole source of truth for all disc, user, and sync data
5. **Redis** -- rate limit counters only in 0.3.0; optional in dev, required in prod
6. **Sync daemon** -- mirror polling loop with snapshot bootstrap and incremental diff

### Critical Pitfalls

The six critical pitfalls are all in existing shipped code. They are not edge cases -- they are bugs that will fire under normal beta usage patterns.

1. **JWT tokens leaked via URL query params** -- 30-day tokens in browser history, Referer headers, access logs. Replace with authorization code exchange or HttpOnly cookie. P0 security.
2. **In-memory rate limiting is broken** -- 4 gunicorn workers means effective limit is 4x configured value (400/min instead of 100/min). Zero protection against abuse. Migrate to Redis. P0 infrastructure.
3. **Mastodon placeholder email collisions** -- account IDs are per-instance, not global. Two users with the same ID on different instances collide. Include domain in placeholder. P0 bug fix.
4. **DNS rebinding bypasses SSRF protection** -- Mastodon domain validation resolves DNS separately from the HTTP request. Pin resolved IP and pass to httpx. P0 security.
5. **Mastodon dynamic registration race condition** -- concurrent first-time users from the same instance cause 500 errors. Use advisory lock or ON CONFLICT. P0 bug fix.
6. **Bare exception handler in disc submission** -- swallows all errors including data integrity failures. Catch specific exceptions, let unexpected ones propagate. P0 bug fix.

## Implications for Roadmap

### Phase 1: Security Hardening and Infrastructure

**Rationale:** Everything else is worthless if the auth flow leaks tokens, rate limiting is broken, and Mastodon login crashes on first use. These are interconnected -- fixing one without the others leaves gaps. Redis must land here because rate limiting depends on it.

**Delivers:** Secure auth flow, working rate limiting, fixed Mastodon registration, validated startup checks, proper error handling in submission endpoint.

**Addresses features:** Redis migration, all 11 P0 bug fixes from PROJECT.md.

**Avoids pitfalls:** 1 (JWT leak), 2 (Mastodon race), 3 (DNS rebinding), 4 (bare exception), 5 (rate limiting), 6 (email collision), 10 (OAuth secret leakage), 11 (status state machine).

### Phase 2: Data Model Expansion

**Rationale:** New tables and API routes must be finalized before sync hardening (Phase 3) so the sync protocol includes all entity types in one format change, not two. Multi-disc sets and chapter names are the two data model additions for 0.3.0.

**Delivers:** Set CRUD API, disc-to-set linking, chapter name table and API, updated disc lookup responses with sibling discs and chapters, web UI for sets and chapters.

**Addresses features:** Multi-disc set support, chapter name data, edit history exposure.

**Avoids pitfalls:** 7 (sync protocol must include new entities from the start), 11 (status state machine validation for new edit flows).

### Phase 3: Sync Protocol and Mirror Hardening

**Rationale:** Depends on Phase 2 (data model must be stable so sync includes all entity types). Mirrors are a core promise of the CC0 model. The sync feed works but lacks integrity verification and snapshot generation.

**Delivers:** Snapshot generation script, SHA-256 integrity verification on diff and snapshot, snapshot-first bootstrap for new mirrors, retry with exponential backoff, `/v1/sync/verify` endpoint, hosted snapshots at snapshots.oviddb.org, monthly CC0 dumps.

**Addresses features:** Self-hosted node hardening, database dumps, sync feed hardening, self-hosting documentation.

**Avoids pitfalls:** 7 (no integrity verification), 12 (snapshot 404 UX).

### Phase 4: CLI Scanner Tool

**Rationale:** Can be built in parallel with Phase 3 since it uses existing API endpoints (`/v1/disc/register` already exists). This is how the database gets seeded to 500+ entries. Without the CLI, the founder cannot batch-import their collection and ARM users cannot contribute actively.

**Delivers:** `ovid scan` (auto mode), `ovid scan --wizard` (guided TMDB match), `ovid scan --batch` (folder of ISOs), PyPI publication of `ovid-client`, platform-specific install docs.

**Addresses features:** CLI scanner tool, PyPI publication, binary distribution.

**Avoids pitfalls:** 8 (distribution strategy -- use PyPI, not PyInstaller), 14 (register PyPI name immediately), 15 (seed data before announcement).

### Phase 5: Moderation, Web UI, and Documentation

**Rationale:** Moderation tooling must exist before the public announcement. The web UI must surface all features (functional, not polished). Documentation builds community trust.

**Delivers:** Admin panel (view submissions, ban users, revert edits), dispute resolution workflow, report button, submission rate limits per user, complete web UI for all 0.3.0 features, governance doc, moderation guide, sync spec, data license FAQ.

**Addresses features:** Dispute resolution, web UI functional completeness, documentation suite, moderation tooling.

**Avoids pitfalls:** 9 (no moderation tooling before announcement), 15 (first impression quality).

### Phase 6: Load Testing and Launch Preparation

**Rationale:** Validates everything built in Phases 1-5 under realistic load. All endpoints must exist before testing. Database must be seeded before announcement.

**Delivers:** k6 test suite (smoke, load, stress), verified p95 under 500ms at 100 concurrent users, database seeded to 500+ entries, public announcement drafted.

**Addresses features:** Load testing, performance verification, database seeding milestone, public announcement.

**Avoids pitfalls:** 13 (global sequence bottleneck -- monitor under load), 15 (insufficient seed data).

### Phase Ordering Rationale

- **Security first** because a single leaked token or 500 error on first login destroys trust permanently. There is no recovery from a bad security reputation in a community project.
- **Data model before sync** because adding tables to the sync format after mirrors are running requires coordinated upgrades. Get the schema right once.
- **CLI before moderation** because the CLI seeds the database, and moderation tools are only useful once there is data and users to moderate.
- **Load testing last** because it validates the complete system. Testing partial systems wastes effort.
- **Phases 3 and 4 can overlap** -- sync hardening and CLI scanner have no mutual dependencies.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Security Hardening):** The auth code exchange flow replacing JWT-in-URL needs careful design. The DNS rebinding fix requires choosing between IP pinning and custom transport approaches. Worth a focused research spike.
- **Phase 3 (Sync Hardening):** Snapshot hosting infrastructure (Caddy vs nginx, static file serving setup) and the integrity verification scheme (simple SHA-256 vs Merkle chain) need implementation decisions.
- **Phase 5 (Moderation):** Admin panel implementation approach (server-side rendered in Next.js vs. dedicated admin route in FastAPI) is an open question.

Phases with standard patterns (skip research-phase):
- **Phase 2 (Data Model):** Schema additions, API routes, Pydantic schemas -- well-documented FastAPI/SQLAlchemy patterns. The data model is already designed in ARCHITECTURE.md.
- **Phase 4 (CLI Scanner):** Pipeline composition from existing Click commands. The architecture is specified in detail in ARCHITECTURE.md.
- **Phase 6 (Load Testing):** k6 is well-documented. Test structure is defined in STACK.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations are additive to existing stack. Redis, k6, and pwdlib are mainstream tools with strong documentation. No risky bets. |
| Features | HIGH | Feature prioritization is grounded in MusicBrainz/Discogs precedent. Table stakes list matches what comparable systems ship. Chapter name data is novel (LOW confidence on community adoption patterns) but technically straightforward. |
| Architecture | HIGH | Architecture analysis was derived from direct codebase reading. Component boundaries, data flows, and build order are concrete. The existing stateless design scales well past OVID's projected needs. |
| Pitfalls | HIGH | Critical pitfalls are derived from line-level code analysis, not speculation. The JWT-in-URL, rate limiting, and Mastodon issues are verifiable bugs. Community/ecosystem pitfalls (moderation, seed data) draw on MusicBrainz precedent at MEDIUM confidence. |

**Overall confidence:** HIGH

### Gaps to Address

- **Email sending infrastructure (P1):** Resend vs. SMTP vs. self-hosted Postfix is an open decision. LOW confidence in STACK.md. Defer to Phase 5 or post-beta planning since email auth is P1.
- **Chapter name community adoption:** No comparable system stores video disc chapter names. The data model is straightforward but whether contributors will actually populate chapter data is unproven. Monitor after launch.
- **Snapshot hosting specifics:** Whether to use Caddy, nginx, or a simple Docker volume mount for `snapshots.oviddb.org` is unresolved. Small decision, make it during Phase 3 implementation.
- **Admin panel approach:** No research on whether to build moderation tools into the Next.js web UI or as a separate admin API surface. Decide during Phase 5 planning.
- **PyPI name reservation:** The `ovid-client` package name is not yet registered. This should happen immediately, before any phase begins, to prevent squatting.

## Sources

### Primary (HIGH confidence)
- OVID codebase analysis: `api/app/rate_limit.py`, `api/app/auth/`, `api/app/routes/sync.py`, `api/app/models.py`, `docker-compose.yml`
- slowapi documentation: https://slowapi.readthedocs.io/en/latest/examples/
- k6 documentation: https://grafana.com/docs/k6/latest/
- MusicBrainz Release/Edit/Replication docs: https://musicbrainz.org/doc/
- FastAPI security tutorial (pwdlib): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/

### Secondary (MEDIUM confidence)
- MusicBrainz Docker mirror setup: https://github.com/metabrainz/musicbrainz-docker
- pwdlib introduction: https://www.francoisvoron.com/blog/introducing-pwdlib-a-modern-password-hash-helper-for-python
- Discogs submission guidelines and contributor program: https://blog.discogs.com/en/database-submission-guidelines/
- OpenLibrary data dumps and self-hosting discussions: https://openlibrary.org/developers/dumps

### Tertiary (LOW confidence)
- Redis 7.4+ version specifics -- from training data, not live verification
- redis-py 5.x version -- from training data
- Email service recommendation (Resend vs SMTP) -- deferred decision, needs validation

---
*Research completed: 2026-04-04*
*Ready for roadmap: yes*
