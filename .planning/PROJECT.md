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
- ✓ Two-contributor verification workflow live (unverified → verified on independent fingerprint confirmation), rate-limited + anti-Sybil weighted — Phase 2 complete; VERIFY-01, VERIFY-03, VERIFY-04 validated end-to-end, including adversarial-review remediation (see `02-VERIFICATION.md`, `02-REVIEW-FIX.md`)
- ✓ INFRA-01: Rate limiting corrected for multi-worker deployment — env-driven Redis-backed slowapi storage (`REDIS_URL` selects shared `RedisStorage`), `redis:7-alpine` wired into prod + test compose (internal-only, ephemeral); single-worker self-host stays on `memory://` — Phase 3
- ✓ INFRA-02: Redis-outage behavior is a documented, tested fail-open decision — bounded, self-healing in-memory fallback (`FALLBACK_LIMIT`) proven by injected-`ConnectionError` tests, with a fail-fast boot guard refusing multi-worker startup without `REDIS_URL` — Phase 3
- ✓ INFRA-03: API response time ≤500ms at p95 under load, validated against the honest Redis-backed `gunicorn -w 4` + Postgres stack (never `memory://`) via a non-blocking scheduled Locust job — measured p95 270ms — Phase 3
- ✓ INFRA-04: Per-account write ceiling (`AUTH_WRITE_LIMIT`) live on all three disc write routes (submit/register/resolve), closing the novel-fingerprint flood gap independent of the anti-Sybil confirmation cooldown — Phase 3

### Active

<!-- Remaining v0.2.0 work. Hypotheses until shipped and validated at the v0.2.0 tag. -->

- [ ] Blu-ray fingerprinting to real parity with the DVD path: Tier 1 (AACS Disc ID) and Tier 2 (BDMV/PLAYLIST structure), plus 4K UHD, with parsers, normalization, tests, and fixtures
- [ ] libdvdread migration ADR Phase 2 completion: alias lookup + submission fully supported in API and database (multiple Disc Identity strings resolve to one physical pressing)
- [ ] libdvdread migration ADR Phase 3: promote `dvdread1-*` to primary DVD fingerprint once alias lookup + submission exist, keeping `dvd1-*` stable as an alias
- [ ] All four OAuth providers working end-to-end: GitHub, Google, Apple, Mastodon (instance discovery)
- [ ] Linked accounts: multiple providers connectable to one account; settings page add/remove with a minimum of one remaining; email-match merge offer on duplicate verified email
- [ ] Web UI production-ready: search, disc detail view, submit form live at `oviddb.org`
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

- Brownfield: v0.1.0 shipped (DVD fingerprinting, API, CLI, schema). v0.2.0 is partially built — OAuth, Web UI, disc-identity aliasing, and the libdvdread Phase 1 fallback have landed but are not all verified end-to-end. Phase 2 (two-contributor verification workflow) is complete and independently verified end-to-end, including a deep adversarial code review and full remediation of the bypasses it found (see `02-VERIFICATION.md`, `02-REVIEW-FIX.md`). Phase 3 (Redis-backed rate limiting & performance) is complete: multi-worker rate limiting, the fail-open outage decision, the per-account write ceiling, and the p95 ≤500ms load-test proof are all live and verified (see `03-VERIFICATION.md`).
- The libdvdread migration is deliberately staged (ADR 0001) to avoid fragmenting existing lookups, submissions, tests, docs, and database records: `dvd1-*` stays the public fingerprint until aliases and dual submission exist.
- Disc Identity (which exact pressing) and Normalized Disc Structure (playable titles/chapters/tracks) are separate concepts and stay separate.
- Known code concerns to fold into this milestone: the ARM file-swap shim has no versioned interface; the IndieAuth localhost bypass must never be enabled in production; `api/disc.py` and `api/auth/routes.py` are large and growing. (Resolved: in-memory rate-limit counters not scaling across gunicorn workers — Phase 3; ad-hoc root scripts and ungitignored `uat_results.json` — Phase 1.)
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
| Move rate limiting to Redis-backed slowapi storage | In-memory counters multiply the effective limit by the gunicorn worker count — incorrect under prod deployment | ✓ Good — Phase 3 |
| Keep Disc Identity and Normalized Disc Structure as separate concepts | Identity answers "which pressing"; structure answers "what plays" — different lifecycles (ADR 0001) | ✓ Good |
| D-00: Sequence the Redis backbone, write throttle, and load test so the load test runs LAST | A tight write limit and any p95 claim are hollow under `memory://` (worker-inflated); the load test must validate the real Redis-backed target config, not the retiring single-worker one | ✓ Good — Phase 3 |
| D-01: Redis outage degrades to a bounded, self-healing in-memory fallback (`FALLBACK_LIMIT`) rather than failing closed | Never block the read-heavy ARM lookup path on a transient Redis outage; proven by injected `ConnectionError` on `RedisStorage.incr` | ✓ Good — Phase 3 |
| D-06: Fail-fast import-time guard refuses to boot when `OVID_WORKERS`/`WEB_CONCURRENCY` > 1 without `REDIS_URL` | Turns silent per-worker rate-limit Nx inflation into a loud, immediate boot failure instead of a quiet multi-worker correctness bug | ✓ Good — Phase 3 |
| CR-01: Made `UNAUTH_LIMIT`/`AUTH_LIMIT` env-configurable (`OVID_UNAUTH_LIMIT`/`OVID_AUTH_LIMIT`), same hardcoded defaults | The load-test harness needed to raise the read-tier limits so measured p95 reflects real handler latency, not limiter 429s | ✓ Good — Phase 3 |

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
*Last updated: 2026-07-06 after Phase 3*
