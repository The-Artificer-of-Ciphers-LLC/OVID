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
- [ ] User account creation (email + password minimum)

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

*Document status: Draft v0.1 · Authors: Project founders · Last updated: 2026-03-31*
