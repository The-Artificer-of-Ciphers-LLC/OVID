# OVID — Open Video Disc Identification Database
## Product Requirements Document (PRD) · v0.1 Draft

---

## Overview

**OVID** (Open Video Disc Identification Database) is an open, community-driven database that uniquely identifies physical DVD and Blu-ray discs by their structural fingerprint and maps them to rich release metadata — including disc layout, title/chapter structure, audio/subtitle tracks, and edition information. It is to video discs what MusicBrainz is to audio CDs.

**Target integration:** The [Automatic Ripping Machine (ARM)](https://github.com/automatic-ripping-machine/automatic-ripping-machine) and similar home media ripping tools.

---

## Problem Statement

When a user rips a DVD or Blu-ray disc using tools like ARM, the software must identify *what disc this is* before it can name files, apply metadata, or route content to the right media library folder. Today, ARM attempts this by reading an embedded disc label (often a cryptic abbreviation like `GODZILLA_2014` or `DISC_1`) and querying TMDB or OMDb with that string. This approach has three core failures:

1. **Disc labels are unreliable.** DVD labels are freeform, frequently abbreviated, and contain no standardized structure. Blu-ray labels are slightly better but still inconsistent across regions and pressings.
2. **No disc-level specificity.** TMDB and OMDb know about *movies*, not about *specific disc releases*. They cannot tell you which titles are the main feature vs. bonus content, how many chapters a title has, what audio tracks are present, or whether this is the theatrical cut or director's cut.
3. **Edition and region blindness.** The 2003 standard release, the 2014 director's cut remaster, and the UK collector's edition are all "The Lord of the Rings" to TMDB. For a local rip library, these differences matter.

The cost of not solving this: users manually correct misidentified rips, mislabeled files end up in media libraries, bonus content gets confused with main features, and multi-disc TV sets require tedious manual intervention.

---

## Goals

1. **Reliable disc identification:** Given a disc inserted into any optical drive, OVID can identify it with ≥95% accuracy without user intervention for discs in the database.
2. **Disc-layout awareness:** OVID stores not just movie titles but the full disc structure — which title numbers are the main feature, extras, trailers, and bonus content.
3. **Edition and region resolution:** OVID distinguishes between different pressings of the same film (e.g., theatrical vs. director's cut, US vs. UK, standard vs. collector's edition).
4. **ARM integration:** OVID provides a clean API that ARM can call as a first-pass metadata provider, falling back to TMDB/OMDb for supplemental movie details.
5. **Open and community-owned:** All data is contributed and verified by the community under a public domain or CC0 license, with no single commercial entity controlling access.

---

## Non-Goals

| Non-Goal | Rationale |
|---|---|
| Storing actual video content or disc images | Legal liability; this is a metadata database, not a piracy tool |
| Replacing TMDB/OMDb for movie metadata (plot, cast, ratings) | OVID handles disc identity and structure; existing APIs handle movie details |
| Supporting LaserDisc, VHS, or HD-DVD in v1 | Small audience; focus first on the dominant formats |
| A consumer-facing movie browsing UI | OVID is infrastructure for tools like ARM, not a streaming guide |
| Real-time pricing, availability, or streaming links | Out of scope; other services handle this well |
| DRM circumvention or decryption key storage | Explicitly out of scope for legal reasons |

---

## Target Users

### Primary: The Home Media Archivist
A person building a personal media library by ripping their owned disc collection to a NAS or home server. They use Plex, Jellyfin, or Emby. They value accuracy and organization but do not want to spend hours manually tagging files. They run ARM or similar automation. They are comfortable with self-hosted software but are not necessarily software developers.

### Secondary: The ARM / Ripping Tool Developer
A developer building or maintaining software that rips optical discs. They need a reliable, programmatic way to identify discs and retrieve structured metadata. They want a well-documented REST API, an open data format, and a stable lookup contract.

### Tertiary: The Community Contributor
A person who has contributed metadata to MusicBrainz, TMDB, or similar community databases. They understand the value of open data and are willing to submit disc entries, verify fingerprints, and correct errors. They are motivated by completeness and accuracy.

---

## User Stories

### Home Media Archivist

- **As a home media archivist**, I want the ripping tool to automatically identify the disc I insert so that I do not have to manually look up and type in the movie title.
- **As a home media archivist**, I want the tool to know which title on the disc is the main feature (vs. trailers and bonus features) so that my media library only shows the actual movie.
- **As a home media archivist**, I want disc identification to work even for older or obscure DVDs that TMDB doesn't know well so that my whole collection gets properly tagged.
- **As a home media archivist**, I want to know when the ripped file is from a specific edition (e.g., director's cut, remastered) so that I can distinguish it from other versions in my library.
- **As a home media archivist**, when OVID doesn't recognize a disc, I want a simple way to submit the disc's information so that the next person benefits.

### ARM / Ripping Tool Developer

- **As a developer integrating with OVID**, I want a REST API endpoint that accepts a disc fingerprint and returns disc metadata in JSON so that I can integrate OVID as a metadata provider without changing my tool's architecture.
- **As a developer**, I want the API to clearly indicate when a disc is not in the database (vs. a server error) so that my tool can gracefully fall back to other metadata sources.
- **As a developer**, I want the API to return a confidence score with each identification so that my tool can decide whether to prompt the user for confirmation.
- **As a developer**, I want a client library (Python, at minimum) that handles fingerprint generation and API calls so that integration is a few lines of code rather than a custom implementation.

### Community Contributor

- **As a contributor**, I want to submit a new disc entry using data my ripping tool already collected so that I don't have to re-enter information I already have.
- **As a contributor**, I want to see when a disc entry has conflicting or unverified data so that I can help resolve discrepancies.
- **As a contributor**, I want to bulk-import a set of discs I own so that I can contribute my whole collection at once rather than one at a time.
- **As a contributor**, I want the database schema to track which edition/pressing I own separately from the movie itself so that regional differences are captured accurately.

### All Authenticated Users (Account & Identity)

- **As a user**, I want to sign in with my GitHub account so that I don't have to create and remember a new password for yet another service.
- **As a user**, I want to sign in with my Google or Apple account so that I have familiar, trusted login options.
- **As a Mastodon user**, I want to log in with my Mastodon account (on any instance, e.g. `fosstodon.org` or `mastodon.social`) so that I can participate without creating a corporate account.
- **As a user who signed up with email**, I want to later link my GitHub account so that I can use either method to log in.
- **As a user with multiple linked providers**, I want to see all of them in my account settings and be able to remove any one that I no longer want, as long as at least one remains.
- **As a user**, if I try to sign in with a new provider that has the same verified email as an existing account, I want OVID to offer to link them rather than creating a duplicate account.

---

## Requirements

### Must-Have — P0 (MVP cannot ship without these)

**Disc Fingerprinting**

- [ ] The system MUST generate a stable, deterministic fingerprint from DVD IFO file structure (number of title sets, title durations, chapter counts)
- [ ] The system MUST generate a stable, deterministic fingerprint from Blu-ray BDMV/PLAYLIST structure (playlist files, clip durations, stream counts)
- [ ] The same disc must always produce the same fingerprint regardless of what drive or OS reads it
- [ ] A Python fingerprinting library (`ovid-client`) must be installable via `pip` and produce fingerprints as a standard string

**Lookup API**

- [ ] `GET /disc/{fingerprint}` — returns disc metadata if known, `404` if not found
- [ ] Response includes: movie title, year, edition name, disc number (for multi-disc sets), main feature title index, format (DVD/BD/4K UHD)
- [ ] Response includes: per-title metadata (duration, chapter count, audio tracks with language/codec, subtitle tracks with language)
- [ ] API returns a `confidence` field (high / medium / low) with each match
- [ ] API must respond in under 500ms at p95

**Submission API**

- [ ] `POST /disc` — accepts a disc fingerprint plus metadata and creates a new entry (requires account)
- [ ] Submitted entries are marked as `unverified` until a second contributor independently confirms the fingerprint
- [ ] UPC barcode field (optional) for cross-referencing with retail product databases

**Data Model (core)**

- [ ] Disc record: fingerprint, format, region code, UPC, edition name, language, submission date, verification status
- [ ] Release record: links disc to a canonical movie/TV release (title, year, TMDB ID, IMDB ID)
- [ ] Title record: disc title index, type (main feature / bonus / trailer / menu), duration, chapter count
- [ ] Track record: title reference, track type (audio/subtitle/video), language code, codec

**Web UI (minimal)**

- [ ] Search by movie title to find known disc releases
- [ ] View a disc entry's full structure
- [ ] Submit a new disc entry via a web form
- [ ] User account creation via email + password **or** any supported OAuth provider
- [ ] OAuth login at launch: **GitHub**, **Google**, **Apple**
- [ ] Federated login via **Mastodon / ActivityPub** — user provides their instance URL (e.g. `fosstodon.org`); OVID performs OAuth2 against that instance
- [ ] Multiple providers linkable to a single OVID account — any linked provider can be used to log in
- [ ] Account settings page shows all linked providers; any can be added or removed (minimum one must remain)
- [ ] Email-match merge: if a new OAuth login carries a verified email matching an existing account, OVID offers to link rather than create a duplicate

---

### Nice-to-Have — P1

- [ ] UPC barcode lookup: `GET /disc/upc/{upc}` returns matching disc entries
- [ ] Disc label lookup: `GET /disc/label/{label}` for rough matching as a fallback
- [ ] ARM configuration wizard: a settings screen in ARM to enable OVID as a metadata provider
- [ ] Chapter name data (e.g., "Opening Credits", "Chapter 1: The Shire") where available
- [ ] Duplicate/alias detection: flag when two submissions appear to be the same disc pressing
- [ ] Community voting on conflicting entries (similar to MusicBrainz edit voting)
- [ ] Export of full database as a CC0 data dump (monthly)
- [ ] JavaScript/Node client library in addition to Python

---

### Future Considerations — P2

- [ ] 4K UHD Blu-ray support (technically similar to BD, but different encryption layer — handle separately)
- [ ] TV series multi-disc set support with episode-to-title mapping
- [ ] Integration with Jellyfin, Plex, and Emby plugins (not just ARM)
- [ ] Mobile barcode scanning app to submit UPC + fingerprint from a phone
- [ ] Relationship data: "this disc is the same film as X but a different cut"
- [ ] LaserDisc or HD-DVD support
- [ ] ISRC / EIDR (Entertainment Identifier Registry) cross-referencing

---

## Success Metrics

### Leading Indicators (first 30–90 days)

| Metric | Target | Measurement |
|---|---|---|
| Discs in database at launch | ≥500 unique disc fingerprints | Database row count |
| API lookup success rate (disc found / lookup attempted) | ≥60% for discs submitted by contributors | API response logs |
| Fingerprint generation success rate | ≥99% (disc readable and mounted) | `ovid-client` error rate |
| ARM integration adoption | ARM PR merged; ≥50 GitHub stars on OVID repo within 60 days | GitHub metrics |
| Contributor submissions (first month) | ≥100 new disc entries per week | Submission logs |

### Lagging Indicators (3–12 months)

| Metric | Target | Measurement |
|---|---|---|
| Database coverage | ≥10,000 unique disc fingerprints at 6 months | DB count |
| API lookup hit rate | ≥85% for home media archivists | API logs, user survey |
| False identification rate | <2% of matched discs are wrong | Community error reports |
| Community health | ≥3 active contributors submitting weekly | Contributor activity dashboard |
| ARM user satisfaction | Users report <5% manual correction rate | ARM GitHub discussions, survey |

---

## Open Questions

| Question | Owner | Blocking? |
|---|---|---|
| What is the exact algorithm for generating a DVD fingerprint from IFO files? Does `dvdid` produce stable enough output, or do we need a new spec? | Engineering | **Yes — blocks all disc ID work** |
| How should we handle multi-disc sets (e.g., 3-disc Lord of the Rings extended edition)? One entry per disc, or one entry per set with child discs? | Product + Community | Yes — affects data model |
| Should OVID store any data that could be considered a DRM circumvention aid (e.g., disc key hashes)? | Legal review | **Yes — must be explicit in ToS** |
| What license should the database use? CC0 (fully public domain, no restrictions) vs. ODbL (open but requires attribution)? MusicBrainz uses CC0. | Project governance | Yes — affects downstream use |
| Who hosts the infrastructure initially? A foundation, a sponsor, or volunteer hosting? | Project governance | No — can defer to beta |
| How do we prevent spam or malicious submissions that corrupt the database? | Engineering + Community | No — address in v1.1 |
| Should fingerprints be stable across different ripping software (e.g., MakeMKV vs. libdvdread)? This requires a fingerprinting spec, not just a library. | Engineering | **Yes — blocks interoperability** |

---

## Timeline Considerations

This is a greenfield open-source project. There are no contractual deadlines, but a suggested phasing based on dependencies:

**Phase 0 — Foundation (Months 1–2)**
- Define and publish the disc fingerprinting specification
- Build and publish `ovid-client` Python library
- Stand up basic API (lookup + submit endpoints)
- Seed the database with ~500 discs from contributors' own collections

**Phase 1 — MVP (Months 3–4)**
- Web UI for search, browse, and submit
- ARM pull request / integration guide
- Community moderation tooling (unverified → verified workflow)
- Public data dump

**Phase 2 — Growth (Months 5–8)**
- UPC barcode lookup
- Community voting / edit history (MusicBrainz-style)
- Expanded client libraries
- TV series support

---

## Git Strategy

OVID follows a simplified **Gitflow** model. All development happens on branches; nothing is committed directly to `main`.

### Branch Types

```
main                        ← production-ready only; tagged releases live here
├── develop                 ← integration branch; all feature work merges here first
│   ├── feature/fingerprint-dvd-algo
│   ├── feature/oauth-mastodon
│   ├── feature/sync-diff-endpoint
│   └── ...
├── release/0.1.0           ← cut from develop when a milestone is ready for testing
│   └── (only bug fixes committed here; no new features)
└── hotfix/0.0.1            ← cut from main to patch a live production issue
```

### Branch Rules

| Branch | Who can push | Merge target | Notes |
|---|---|---|---|
| `main` | Maintainers only (via PR) | — | Protected; requires passing CI + one review |
| `develop` | Maintainers via PR | `main` (via release branch) | Integration branch; always deployable to staging |
| `feature/*` | Any contributor | `develop` | Named `feature/{short-description}`; squash merge preferred |
| `release/*` | Maintainers | `main` + back-merge to `develop` | Named `release/{version}`; bug fixes only; triggers beta deploy |
| `hotfix/*` | Maintainers | `main` + back-merge to `develop` | Named `hotfix/{version}`; emergency production patches |

### Workflow: Normal Feature

```
1. Branch from develop:       git checkout -b feature/oauth-github develop
2. Work and commit locally
3. Open PR → develop
4. CI runs (tests, lint, fingerprint stability check)
5. One maintainer review → squash merge into develop
6. Branch deleted after merge
```

### Workflow: Cutting a Release

```
1. Branch from develop:       git checkout -b release/0.2.0 develop
2. Update version strings and CHANGELOG
3. Deploy to staging; run integration tests against real disc images
4. Bug fixes committed directly to release/0.2.0
5. Back-merge any fixes to develop:  git merge release/0.2.0 → develop
6. When stable, PR release/0.2.0 → main
7. Merge + tag:               git tag -a v0.2.0 -m "Release 0.2.0"
8. Deploy to production; delete release branch
```

### Workflow: Hotfix

```
1. Branch from main:          git checkout -b hotfix/0.1.1 main
2. Fix the issue; bump patch version; update CHANGELOG
3. PR → main (expedited review)
4. Merge + tag:               git tag -a v0.1.1
5. Back-merge to develop:     git merge hotfix/0.1.1 → develop
```

### Commit Message Convention

OVID follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>

[optional body]

[optional footer: Co-Authored-By, Closes #issue]
```

| Type | When to use |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `spec` | Changes to specification documents only |
| `docs` | README, guides, in-code documentation |
| `refactor` | Code change with no behavior change |
| `test` | Adding or updating tests |
| `chore` | Build system, CI, dependency updates |
| `release` | Version bump + changelog update commits |

Examples:
```
feat(fingerprint): implement OVID-DVD-1 structural hash algorithm
fix(sync): handle empty diff response when node is already at head
spec(auth): add Mastodon OAuth instance discovery flow
release: bump version to 0.2.0
```

---

## Version Scheme and Development Milestones

OVID uses **semantic versioning** in the form `0.MILESTONE.PATCH` during pre-release development:

- **0** — major version fixed at zero until the project reaches a stable public API and ≥10,000 disc entries (signals pre-release / active development)
- **MILESTONE** — increments with each named phase completion (Phase 0 → 0.1, Phase 1 → 0.2, etc.)
- **PATCH** — increments for bug fixes, security patches, and documentation corrections within a milestone; resets to 0 on each new milestone

```
0.1.0   Phase 0 complete — fingerprint spec + ovid-client published
0.1.1   Bug fix (e.g. IFO parser edge case on malformed disc)
0.1.2   Bug fix (e.g. pycdlib ISO mount failure on macOS)
0.2.0   Phase 1 complete — MVP API + Web UI + ARM integration
0.2.1   Bug fix
...
0.3.0   Phase 2 complete — sync / self-hosted / community moderation
1.0.0   Stable public API declared; ≥10,000 disc entries; foundation formed
```

No features are added in patch releases — only fixes to the preceding milestone's scope. If a fix requires a new behaviour, it targets the next milestone instead.

### Milestone 0.1 — Foundation

**Goal:** A working disc fingerprint algorithm and client library. No server required.

**Exit criteria (all must be true to tag `v0.1.0`):**
- [ ] `OVID-DVD-1` fingerprint algorithm spec published as a standalone document in `docs/`
- [ ] `ovid-client` generates DVD fingerprints from a live drive and from an ISO
- [ ] Fingerprint stability validated: same disc produces identical fingerprint across ≥3 different drives on Linux and macOS
- [ ] `ovid-client` published to PyPI under the name `ovid-client`
- [ ] Basic PostgreSQL schema deployed (migrations passing via Alembic)
- [ ] `GET /v1/disc/{fingerprint}` and `POST /v1/disc` endpoints live on `api.oviddb.org`
- [ ] Docker Compose dev stack documented and tested (`docker compose up` → working local API)
- [ ] Database seeded with ≥20 real disc entries contributed by founders
- [ ] CI pipeline running on GitHub Actions: lint, unit tests, fingerprint regression tests

**Patch window:** `0.1.1` – `0.1.x` addresses bugs in the above before Phase 1 begins.

---

### Milestone 0.2 — MVP

**Goal:** A usable product for the home archivist community. Publicly announced.

**Exit criteria (all must be true to tag `v0.2.0`):**
- [ ] Web UI live at `oviddb.org`: search, disc detail view, submit form
- [ ] All four OAuth providers working: GitHub, Google, Apple, Mastodon
- [ ] Linked accounts: multiple providers connectable to one account
- [ ] Two-contributor verification workflow live (unverified → verified)
- [ ] `ovid-client` Blu-ray Tier 1 (AACS Disc ID) and Tier 2 (BDMV structure) both working
- [ ] ARM integration PR merged or under active review
- [ ] Database seeded to ≥500 disc entries
- [ ] API response time ≤500ms at p95 under load
- [ ] Rate limiting and basic abuse prevention live
- [ ] `oviddb.com` and `oviddb.net` redirecting to `oviddb.org`
- [ ] Public announcement posted (GitHub, ARM forums, r/DataHoarder, Doom9)

**Patch window:** `0.2.1` – `0.2.x` addresses issues found after public launch.

---

### Milestone 0.3 — Self-Hosted and Community

**Goal:** Anyone can run their own OVID node. Community governance tooling in place.

**Exit criteria (all must be true to tag `v0.3.0`):**
- [ ] Sync feed endpoints live: `/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot`
- [ ] `docker compose --profile mirror up` launches a self-hosted mirror node
- [ ] Daily snapshot generation and hosting at `snapshots.oviddb.org`
- [ ] Self-hosted getting-started guide published
- [ ] Edit history and audit log visible in Web UI
- [ ] UPC barcode lookup endpoint live
- [ ] Community dispute flagging live
- [ ] Monthly CC0 database dump published
- [ ] Database at ≥5,000 disc entries

**Patch window:** `0.3.1` – `0.3.x`.

---

### Milestone 0.4 — TV Series and Scale

**Goal:** TV series multi-disc sets fully supported. Database meaningfully large.

**Exit criteria (all must be true to tag `v0.4.0`):**
- [ ] TV series disc entries with episode-to-title mapping
- [ ] Community voting on conflicting disc entries (MusicBrainz edit-voting model)
- [ ] `ovid-client` JavaScript/Node library published to npm
- [ ] Database at ≥10,000 disc entries
- [ ] Federated node mode (local writes + upstream submission) — design complete and v1 shipped

**Patch window:** `0.4.1` – `0.4.x`.

---

### Milestone 1.0 — Stable

**Goal:** Stable public API contract declared. No breaking changes without a major version bump.

**Exit criteria:**
- [ ] All Open Questions from the product spec resolved or explicitly deferred with rationale
- [ ] API versioning policy documented (`/v1/` frozen; new features go to `/v2/`)
- [ ] Non-profit foundation or fiscal sponsorship in place
- [ ] Database at ≥10,000 disc entries
- [ ] `ovid-client` at 1.0 on PyPI with stable API

---

## Documentation Release Plan

Each milestone ships documentation alongside the software. Documentation is never a trailing deliverable — it ships with the code that enables it, as a condition of the milestone exit criteria.

### Phase 0 → v0.1.0

| Document | Location | Audience | Status at release |
|---|---|---|---|
| Fingerprint Algorithm Spec (OVID-DVD-1) | `docs/fingerprint-spec.md` | Developers, implementers | Final |
| `ovid-client` API reference | PyPI / README | Developers | Final |
| Getting Started (developer) | `docs/getting-started-dev.md` | Contributors | Final |
| Docker Compose quick-start | `docs/docker-quickstart.md` | Contributors | Final |
| CHANGELOG | `CHANGELOG.md` | All | Initiated |
| GitHub issue templates | `.github/ISSUE_TEMPLATE/` | Contributors | Final |
| GitHub PR template | `.github/PULL_REQUEST_TEMPLATE.md` | Contributors | Final |

---

### Phase 1 → v0.2.0

| Document | Location | Audience | Status at release |
|---|---|---|---|
| Fingerprint Algorithm Spec (OVID-BD-2, Tier 1 & 2) | `docs/fingerprint-spec.md` (update) | Developers | Final |
| Web UI user guide | `oviddb.org/docs/guide` | Home archivists | Final |
| Disc submission guide | `oviddb.org/docs/submit` | Community contributors | Final |
| ARM integration guide | `docs/arm-integration.md` + ARM wiki | ARM users | Final |
| OAuth setup guide (for self-deployed instances) | `docs/auth-setup.md` | Operators | Final |
| Community Code of Conduct | `CODE_OF_CONDUCT.md` | All | Final |
| Contributing guide | `CONTRIBUTING.md` | Contributors | Final |
| Data licensing explainer (CC0 FAQ) | `docs/data-license.md` | All | Final |
| Press / announcement post | `oviddb.org/blog/announcing-ovid` | Public | Publish at launch |
| CHANGELOG | `CHANGELOG.md` | All | Updated |

---

### Phase 2 → v0.3.0

| Document | Location | Audience | Status at release |
|---|---|---|---|
| Self-hosted getting-started guide | `docs/self-hosting.md` | Home server operators | Final |
| Sync protocol specification | `docs/sync-spec.md` | Developers, implementers | Final |
| Moderation guide | `docs/moderation.md` | Editors, admins | Final |
| Data dump format reference | `docs/dump-format.md` | Developers | Final |
| Governance model | `docs/governance.md` | Community | Final |
| CHANGELOG | `CHANGELOG.md` | All | Updated |

---

### Phase 3 → v0.4.0

| Document | Location | Audience | Status at release |
|---|---|---|---|
| TV series disc entry guide | `docs/tv-series.md` | Contributors | Final |
| `ovid-client` Node.js API reference | npm / README | Developers | Final |
| Federated node operator guide | `docs/federation.md` | Node operators | Final |
| CHANGELOG | `CHANGELOG.md` | All | Updated |

---

### Stable → v1.0.0

| Document | Location | Audience | Status at release |
|---|---|---|---|
| API stability and versioning policy | `docs/api-versioning.md` | Developers | Final |
| Foundation / governance announcement | `oviddb.org/blog/` | Public | Publish at launch |
| Full API reference (OpenAPI / Swagger) | `api.oviddb.org/docs` | Developers | Final (auto-generated) |
| Migration guide: pre-1.0 → 1.0 | `docs/migration-1.0.md` | All existing users | Final |
| CHANGELOG | `CHANGELOG.md` | All | Updated |

---

## Competitive Landscape

| Service | Open? | Disc Fingerprint? | Layout Data? | Status |
|---|---|---|---|---|
| MusicBrainz | Yes (CC0) | Yes (audio CD TOC) | Yes (track listing) | Active |
| TMDB | Partial (free API) | No | No | Active |
| GD3 / GetDigitalData | No (commercial) | Unknown | Partial | Active (proprietary) |
| DVDFab Meta Info | No (proprietary) | Unknown | Partial | Limited |
| dvdid | Yes (open source) | Yes (DVD only) | No database | Unmaintained |
| **OVID** | **Yes (target: CC0)** | **Yes (DVD + BD)** | **Yes** | **Proposed** |

---

*Document status: Draft v0.3 · Authors: Project founders · Last updated: 2026-04-01*
