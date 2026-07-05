# OVID — Open Video Disc Identification Database

## What This Is

OVID is an open, community-driven database that identifies physical DVD, Blu-ray, and 4K UHD discs by a stable structural fingerprint and maps them to rich release metadata (edition, disc layout, main-feature marker, per-title chapters, audio/subtitle tracks). It is "MusicBrainz for video discs," built primarily as a first-pass metadata provider for the Automatic Ripping Machine (ARM) and similar home-media ripping tools. It ships as a FastAPI + PostgreSQL service, a `ovid-client` Python library/CLI, and a Next.js web UI.

## Core Value

Given a disc in any drive, OVID returns the correct disc identity and structure — deterministically and reproducibly — so ripping tools can name, tag, and route content without manual correction.

## Current Milestone

**v0.2.0 — MVP (PRD Milestone 0.2).** This work cycle drives the existing codebase to the v0.2.0 exit criteria across four strands: disc-identity / libdvdread migration, Blu-ray/UHD fingerprinting, Web UI, and OAuth. Source of truth: `docs/OVID-product-spec.md` (Milestone 0.2 exit criteria) and `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`.

## Requirements

### Validated

<!-- Inferred from existing code — shipped in v0.1.0 and the v0.2.0 pieces already landed. -->

- ✓ OVID-DVD-1 structural fingerprinting, exposed as `dvd1-*` — existing (v0.1.0)
- ✓ `ovid-client` Python library + CLI: folder/ISO/drive readers, IFO/MPLS parsers, normalization to format-neutral disc structure, submission-payload builder — existing (v0.1.0)
- ✓ Lookup API `GET /v1/disc/{fingerprint}` (metadata or 404) and Submission API `POST /v1/disc` — existing (v0.1.0)
- ✓ PostgreSQL 16 schema with Alembic migrations (disc/release/title/track + global_seq) — existing (v0.1.0)
- ✓ Disc Identity module with libdvdread Phase 1: tries libdvdread `dvdread1-*`, silently falls back to OVID-DVD-1, `dvd1-*` stays primary — existing (ADR 0001 Phase 1)
- ✓ Disc identity Lookup Aliases modeled and carried through client submission — existing (ADR 0001 Phase 2, in progress)
- ✓ Normalized Disc Structure projection (titles, chapters, audio/subtitle tracks, source metadata) — existing
- ✓ ARM integration shim (`arm/identify_ovid.py`, file-swap pattern, non-blocking 5s timeout) — existing
- ✓ Multi-provider OAuth scaffolding (GitHub, Google, Apple, IndieAuth, Mastodon), env-gated — existing (partial; not verified end-to-end)
- ✓ Next.js web UI scaffolding: search, disc detail, submission wizard, disputes, settings, OAuth callbacks — existing (partial)
- ✓ Rate limiting via slowapi (in-memory) — existing (has multi-worker scaling defect, see Key Decisions)

### Active

<!-- Remaining v0.2.0 work. Hypotheses until shipped and validated at the v0.2.0 tag. -->

- [ ] Blu-ray fingerprinting to real parity with the DVD path: Tier 1 (AACS Disc ID) and Tier 2 (BDMV/PLAYLIST structure), plus 4K UHD, with parsers, normalization, tests, and fixtures
- [ ] libdvdread migration ADR Phase 2 completion: alias lookup + submission fully supported in API and database (multiple Disc Identity strings resolve to one physical pressing)
- [ ] libdvdread migration ADR Phase 3: promote `dvdread1-*` to primary DVD fingerprint once alias lookup + submission exist, keeping `dvd1-*` stable as an alias
- [ ] All four OAuth providers working end-to-end: GitHub, Google, Apple, Mastodon (instance discovery)
- [ ] Linked accounts: multiple providers connectable to one account; settings page add/remove with a minimum of one remaining; email-match merge offer on duplicate verified email
- [ ] Two-contributor verification workflow live (unverified → verified on independent fingerprint confirmation)
- [ ] Web UI production-ready: search, disc detail view, submit form live at `oviddb.org`
- [ ] Rate limiting corrected for multi-worker deployment (Redis-backed slowapi storage) and basic abuse prevention live
- [ ] API response time ≤500ms at p95 under load (validated with a load test)
- [ ] ARM integration PR merged or under active review with upstream
- [ ] Bulk-seed tooling + seed the database to ≥500 real disc entries
- [ ] `oviddb.com` and `oviddb.net` redirecting to `oviddb.org`
- [ ] Public announcement posted (GitHub, ARM forums, r/DataHoarder, Doom9)
- [ ] v0.2.0 documentation set per PRD Documentation Release Plan: fingerprint spec update (OVID-BD-2 Tier 1 & 2), Web UI user guide, submission guide, ARM integration guide, OAuth setup guide, CC0 data-license explainer, CHANGELOG

### Out of Scope

<!-- Explicit boundaries with reasoning. -->

- Sync feed / self-hosted mirror nodes, edit history/audit UI, community dispute flagging, UPC barcode lookup, monthly CC0 dumps — deferred to v0.3.0 (Milestone 0.3)
- TV-series multi-disc episode mapping, community edit-voting, JavaScript/Node client, federated node mode — deferred to v0.4.0
- LaserDisc, VHS, HD-DVD support — PRD non-goal (small audience)
- Storing video content or disc images — legal non-goal (metadata database only)
- DRM circumvention, decryption/disc-key storage — legal non-goal
- Replacing TMDB/OMDb for movie metadata (plot, cast, ratings) — non-goal; OVID owns disc identity/structure only
- Consumer-facing movie-browsing/streaming UI — non-goal; OVID is infrastructure for ripping tools

## Context

- Brownfield: v0.1.0 shipped (DVD fingerprinting, API, CLI, schema). v0.2.0 is partially built — OAuth, Web UI, disc-identity aliasing, and the libdvdread Phase 1 fallback have landed but are not all verified end-to-end.
- The libdvdread migration is deliberately staged (ADR 0001) to avoid fragmenting existing lookups, submissions, tests, docs, and database records: `dvd1-*` stays the public fingerprint until aliases and dual submission exist.
- Disc Identity (which exact pressing) and Normalized Disc Structure (playable titles/chapters/tracks) are separate concepts and stay separate.
- Known code concerns to fold into this milestone: in-memory rate-limit counters don't scale across gunicorn workers; ad-hoc root scripts (`fix_test.py`, `test_script.py`, `verify_t11.py`) should be removed or moved under `scripts/`; the ARM file-swap shim has no versioned interface; the IndieAuth localhost bypass must never be enabled in production; `api/disc.py` and `api/auth/routes.py` are large and growing; UAT scripts are not CI-integrated and `uat_results.json` should be gitignored.
- External integrations: TMDB (metadata lookup), canonical OVID at `oviddb.org` (upstream for mirror sync — a v0.3 concern), ARM.

## Constraints

- **Tech stack**: Python 3.12 + FastAPI + PostgreSQL 16 + SQLAlchemy 2.x/Alembic (API); Python `ovid-client` (click/rich CLI); Next.js 16 + React 19 + Tailwind 4 (web); Docker Compose (uvicorn dev, gunicorn prod) — established, do not re-platform
- **Compatibility**: `dvd1-*` (OVID-DVD-1) public fingerprint MUST remain stable and resolvable — no lookup/submission fragmentation during the libdvdread migration (ADR 0001)
- **Performance**: API p95 ≤ 500ms under load
- **Data license**: CC0 (public domain), no single commercial gatekeeper
- **Legal**: no DRM circumvention, no decryption-key storage, no video content/disc images
- **Git**: simplified Gitflow — `feature/*` → `develop` → `release/0.2.0` → `main`; Conventional Commits; nothing committed directly to `main`
- **Testing**: pytest (API against in-memory SQLite via TestClient; `ovid-client` with `real_disc` hardware markers), Vitest (web)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Stage the libdvdread disc-identity migration (dvd1 primary → aliases → dvdread1 primary) | Avoid fragmenting existing lookups, submissions, tests, docs, and DB records (ADR 0001) | ✓ Good — Phases 1–2 landing |
| Include non-code v0.2.0 exit items (DNS redirects, announcement, ≥500-entry seeding) as roadmap tasks | User wants the full milestone exit tracked and driven, not just engineering | — Pending |
| Move rate limiting to Redis-backed slowapi storage | In-memory counters multiply the effective limit by the gunicorn worker count — incorrect under prod deployment | — Pending |
| Keep Disc Identity and Normalized Disc Structure as separate concepts | Identity answers "which pressing"; structure answers "what plays" — different lifecycles (ADR 0001) | ✓ Good |

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
*Last updated: 2026-07-05 after initialization*
