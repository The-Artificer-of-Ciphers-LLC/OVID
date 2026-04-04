# Roadmap: OVID v0.3.0 — Beta to Public Launch

## Overview

OVID v0.3.0 takes the alpha (v0.2.0) to public beta and launch. The path is: fix all security and infrastructure bugs that would destroy trust on first contact, expand the data model with multi-disc sets and chapter names, harden the sync/mirror protocol so mirrors get complete data, ship the CLI scanner that seeds the database, complete the web UI so every feature is accessible, write the documentation that builds community trust, then validate under load and announce. Phases 2 and 3 (data model) can execute in parallel. Phases 4 and 5 (sync and CLI) can execute in parallel after the data model lands.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Security Hardening & Infrastructure** - Fix all P0 security bugs, auth flow, and rate limiting before any public exposure
- [ ] **Phase 2: Multi-Disc Set Support** - API and data model for box sets and multi-disc releases
- [ ] **Phase 3: Chapter Name Data** - Chapter metadata table, API surface, and Blu-ray extraction
- [ ] **Phase 4: Sync Protocol & Mirror Hardening** - Snapshot generation, integrity verification, and mirror bootstrap
- [ ] **Phase 5: CLI Scanner Tool** - Three-mode scanner for database seeding and PyPI publication
- [ ] **Phase 6: Web UI Completeness** - Surface all v0.3.0 features on www.oviddb.org
- [ ] **Phase 7: Documentation** - Self-hosting guide, sync spec, governance, and moderation docs
- [ ] **Phase 8: Load Testing & Launch** - Validate performance under load, seed database, announce publicly

## Phase Details

### Phase 1: Security Hardening & Infrastructure
**Goal**: The API is secure enough for public users — no token leaks, no crash-on-first-login bugs, no broken rate limiting
**Depends on**: Nothing (first phase)
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, BUG-01, BUG-02, BUG-03, BUG-04, BUG-05, INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):
  1. User can log in via any OAuth provider (GitHub, Google, Apple, Mastodon, IndieAuth) without tokens appearing in browser history, URL bars, or server access logs
  2. Two Mastodon users from different instances with the same account ID can both log in without collision
  3. Rate limiting enforces configured limits correctly across all API workers (not N times the limit)
  4. API startup fails fast with a clear error message if JWT secret or Apple private key is misconfigured
  5. Disc submission endpoint returns specific error messages for validation failures instead of swallowing exceptions
**Plans:** 3 plans

Plans:
- [x] 01-01-PLAN.md — Valkey/Redis infrastructure, rate limiting migration, startup validation
- [x] 01-02-PLAN.md — Mastodon hardening, bug fixes, error sanitization
- [x] 01-03-PLAN.md — Auth code exchange, cookie delivery, device flow, refresh rotation

### Phase 2: Multi-Disc Set Support
**Goal**: Users can group related discs (box sets, multi-disc releases) and see sibling discs when looking up any disc in a set
**Depends on**: Phase 1
**Requirements**: SET-01, SET-02, SET-03, SET-04, SET-05, SET-06, SET-07, SET-08
**Success Criteria** (what must be TRUE):
  1. API consumer can create a disc set and link discs to it, with disc_number validated against total_discs
  2. Looking up a disc that belongs to a set returns all sibling discs in the response
  3. Web UI disc detail page shows sibling discs when the disc is part of a set
  4. Web UI submission form allows specifying set membership with disc number
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Chapter Name Data
**Goal**: OVID stores and returns chapter-level metadata for disc titles, and Blu-ray scans extract chapter timestamps and disc titles automatically
**Depends on**: Phase 1
**Requirements**: CHAP-01, CHAP-02, CHAP-03, CHAP-04, CHAP-05, CHAP-06, CHAP-07, CHAP-08, CHAP-09, CHAP-10
**Success Criteria** (what must be TRUE):
  1. API consumer can submit chapter names and timestamps with a disc, and retrieve them on lookup
  2. Blu-ray fingerprinting extracts MPLS chapter timestamps and bdmt_*.xml disc/title names when present
  3. Sync feed includes chapter data so mirrors receive chapter metadata
  4. Web UI shows chapter names under each title on the disc detail page
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

### Phase 4: Sync Protocol & Mirror Hardening
**Goal**: Self-hosted mirrors can bootstrap from a snapshot and stay current with integrity-verified incremental syncs
**Depends on**: Phase 2, Phase 3
**Requirements**: SYNC-01, SYNC-02, SYNC-03, SYNC-04, SYNC-05, SYNC-06, SYNC-07, SYNC-08
**Success Criteria** (what must be TRUE):
  1. A new mirror can bootstrap from a snapshot file (NDJSON + gzip) downloaded from snapshots.oviddb.org, then catch up via incremental diffs
  2. Diff sync rejects out-of-order sequence numbers and retries transient failures with exponential backoff
  3. All sync-tracked tables (including disc_sets and disc_chapters) have seq_num columns and appear in the sync feed
  4. Monthly CC0 database dump is published and downloadable
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: CLI Scanner Tool
**Goal**: Users can scan physical discs or ISOs from the command line, automatically submitting new discs to OVID, and install via pip
**Depends on**: Phase 1
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06
**Success Criteria** (what must be TRUE):
  1. `pip install ovid-client && ovid scan /dev/sr0` fingerprints an inserted disc, checks OVID, and auto-submits if unknown
  2. `ovid scan --wizard` prompts for TMDB match, edition name, and disc number before submission
  3. `ovid scan --batch /path/to/isos` processes a folder of ISOs and submits all misses in one run
  4. Auto mode extracts bdmt_*.xml disc title and MPLS chapter timestamps when scanning Blu-rays
  5. Platform-specific install docs exist for macOS (Homebrew deps) and Linux (apt/dnf deps)
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Web UI Completeness
**Goal**: Every v0.3.0 feature is accessible through www.oviddb.org — functional, not polished
**Depends on**: Phase 2, Phase 3
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07, WEB-08, WEB-09
**Success Criteria** (what must be TRUE):
  1. User can look up a disc by fingerprint or title search and see full structure including sets, chapters, and edit history
  2. Authenticated user can edit/correct existing disc entries with changes tracked in visible edit history
  3. User can flag a disc entry for dispute, and a moderator can resolve it with an audit trail
  4. User can create and manage disc sets, submit discs with all new fields (set membership, chapters, bdmt metadata), and link/unlink OAuth providers in account settings
**Plans**: TBD
**UI hint**: yes

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD
- [ ] 06-03: TBD

### Phase 7: Documentation
**Goal**: Community-facing documentation exists for self-hosting, sync protocol, moderation, data licensing, and governance
**Depends on**: Phase 4, Phase 6
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06
**Success Criteria** (what must be TRUE):
  1. A new operator can follow docs/self-hosting.md to stand up a working OVID mirror using Docker Compose
  2. A developer can read docs/sync-spec.md and understand the snapshot + diff sync protocol without reading source code
  3. docs/governance.md, docs/moderation.md, docs/data-license.md, and docs/dump-format.md exist and are linked from the repository README or web UI
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

### Phase 8: Load Testing & Launch
**Goal**: The system is validated under realistic load, the database has critical mass, and OVID is publicly announced
**Depends on**: Phase 4, Phase 5, Phase 6, Phase 7
**Requirements**: PERF-01, PERF-02, PERF-03, LAUNCH-01, LAUNCH-02, LAUNCH-03
**Success Criteria** (what must be TRUE):
  1. k6 load test suite exists in the repository with smoke, load, and stress scenarios
  2. API responds at p95 under 500ms with 100 concurrent users
  3. Database contains 500 or more real disc entries
  4. Public announcement is posted to GitHub, ARM forums, r/DataHoarder, and Doom9
**Plans**: TBD

Plans:
- [ ] 08-01: TBD
- [ ] 08-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8
Phases 2 and 3 can execute in parallel (both data model, no mutual deps).
Phases 4 and 5 can execute in parallel (sync and CLI have no mutual deps).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Security Hardening & Infrastructure | 0/3 | Planned | - |
| 2. Multi-Disc Set Support | 0/2 | Not started | - |
| 3. Chapter Name Data | 0/2 | Not started | - |
| 4. Sync Protocol & Mirror Hardening | 0/2 | Not started | - |
| 5. CLI Scanner Tool | 0/2 | Not started | - |
| 6. Web UI Completeness | 0/3 | Not started | - |
| 7. Documentation | 0/1 | Not started | - |
| 8. Load Testing & Launch | 0/2 | Not started | - |
