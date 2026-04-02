# OVID — Open Video Disc Identification Database

[![CI](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/actions/workflows/ci.yml/badge.svg)](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/The-Artificer-of-Ciphers-LLC/OVID?include_prereleases)](https://github.com/The-Artificer-of-Ciphers-LLC/OVID/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](LICENSE)
[![Data: CC0](https://img.shields.io/badge/data-CC0--1.0-green.svg)](https://creativecommons.org/publicdomain/zero/1.0/)

> *A community-driven, open standard for fingerprinting physical video discs — DVD, Blu-ray, and 4K UHD — to enable accurate, automated cataloging of home media libraries.*

---

## What Is OVID?

The name is a quiet nod to [Publius Ovidius Naso](https://en.wikipedia.org/wiki/Ovid) — the Roman poet who spent his life cataloguing everything worth preserving. His *Metamorphoses* assembled 250 myths into a single, structured work so nothing would be lost. His *Fasti* catalogued the Roman calendar, month by month, entry by entry. Ovid believed that if something existed, it deserved to be recorded precisely and permanently.

That felt like the right spirit for a project about preserving physical media.

OVID (**O**pen **Vi**deo **D**isc identification database) is an open-source project to build the video disc equivalent of [MusicBrainz](https://musicbrainz.org).

When you rip a music CD today, software like MusicBrainz Picard reads the disc's Table of Contents, generates a fingerprint, and looks it up in a community database — giving you the album title, track names, artwork, and release year automatically. This works because MusicBrainz spent years building an open, structured database of disc fingerprints contributed by thousands of people who own physical media.

**No equivalent exists for DVD and Blu-ray.**

Tools like the [Automatic Ripping Machine (ARM)](https://github.com/automatic-ripping-machine/automatic-ripping-machine) do their best: they read whatever label string is embedded in the disc (often something like `GODZILLA_2014` or `DISC_1_OF_3`) and try to match it against [TMDB](https://www.themoviedb.org) or [OMDb](https://www.omdbapi.com). This works reasonably well for mainstream titles, but it cannot tell you:

- Which title index on the disc is the actual main feature (vs. trailers, bonus content, or menus)
- Whether this is the theatrical cut, director's cut, or extended edition
- Which language tracks and subtitle tracks are present
- Whether this is a US Region 1 pressing or a UK Region 2 pressing with different bonus content
- How many chapters the main feature has

OVID is built to answer all of those questions.

---

## The Core Idea

A DVD's IFO files and a Blu-ray's BDMV/PLAYLIST structure are fixed at disc mastering time. Every physical copy of the same pressing is structurally identical — the number of titles, their durations, chapter counts, and track layouts are the same on every copy that came off the same press run.

This structural data can be hashed into a **stable, deterministic fingerprint** that uniquely identifies a specific disc pressing — similar to how `libdiscid` computes a fingerprint from an audio CD's track layout for MusicBrainz.

OVID defines:

1. **A fingerprint specification** — a documented, open algorithm for computing a disc fingerprint from DVD IFO or Blu-ray BDMV structure
2. **A community database** — an open, CC0-licensed database mapping fingerprints to rich release metadata
3. **A client library** (`ovid-client`) — a Python library and CLI tool that generates fingerprints and queries the database
4. **A REST API** — a simple, free-to-use API that any ripping tool can call

---

## Why This Matters for Home Archivists

People building personal media libraries from their owned disc collections face a tedious problem: ripping tools can identify *movies*, but they cannot identify *disc releases*. The result is:

- Bonus discs misidentified as the main film
- Different editions mixed up in the same library folder
- Multi-disc TV sets requiring manual episode mapping
- Obscure or foreign films that metadata APIs don't know well left untagged

OVID treats the physical disc — not just the movie title — as a first-class citizen. Like a book's ISBN or a music CD's catalog number, a disc pressing deserves its own stable identifier and structured metadata.

---

## Relationship to Existing Databases

OVID is **not** a replacement for TMDB, TVDB, or OMDb. It is complementary infrastructure that sits *in front of* those databases.

The lookup chain works like this:

```
Physical disc inserted
        ↓
OVID fingerprint generated (from disc structure)
        ↓
OVID database lookup → returns: edition, disc layout, title index of main feature,
                                track list, confidence score, + TMDB/IMDB IDs
        ↓
TMDB / TVDB lookup (using IDs from OVID) → returns: plot, cast, poster, ratings
        ↓
Complete metadata applied to ripped file
```

OVID handles the **disc identity** problem. TMDB and TVDB handle **movie/TV show metadata**. Together they provide a complete picture.

### Database Attribution

OVID integrates with:

- **[The Movie Database (TMDB)](https://www.themoviedb.org)** — TMDB IDs are stored as cross-references in OVID entries. Per TMDB's [API Terms of Use](https://www.themoviedb.org/api-terms-of-use), non-commercial open-source use is permitted with attribution. OVID will carry the required notice: *"This product uses the TMDB API but is not endorsed or certified by TMDB."*

- **[TheTVDB](https://thetvdb.com)** — TVDB IDs are stored as cross-references for TV series disc releases. Per TheTVDB's [API and Data Licensing terms](https://thetvdb.com/api-information), free open-source projects may use the API and data with attribution. OVID will carry the required notice: *"TV information and images are provided by TheTVDB.com, but we are not endorsed or certified by TheTVDB.com or its affiliates."*

OVID does **not** copy or mirror TMDB or TVDB content. It only stores cross-reference IDs (e.g., `tmdb_id: 120`) so that consuming applications can query those APIs directly.

---

## Inspired By

- **[MusicBrainz](https://musicbrainz.org)** — The gold standard for open music metadata. OVID follows MusicBrainz's community model, CC0 data licensing philosophy, and the principle that physical media deserves precise, structured identification.
- **[libdiscid](https://musicbrainz.org/doc/libdiscid)** — MusicBrainz's C library for generating stable disc fingerprints from audio CD TOC data. OVID's fingerprinting specification is directly inspired by this approach, adapted for the IFO and BDMV disc formats.
- **[dvdid](https://github.com/rdp/dvdid)** — An open-source implementation of Windows' `IDvdInfo2::GetDiscID()` method, demonstrating that stable DVD fingerprinting is technically achievable.
- **[Automatic Ripping Machine (ARM)](https://github.com/automatic-ripping-machine/automatic-ripping-machine)** — The primary integration target. OVID aims to become an optional metadata provider in ARM, improving identification accuracy for the home ripping community.

---

## Project Status

**Current version: v0.1.0** — Foundation & Core Pipeline complete.

OVID v0.1.0 delivers the end-to-end pipeline: fingerprint a DVD from any source, submit it to the API with TMDB-linked metadata via an interactive CLI wizard, and retrieve full disc structure (titles, tracks, chapters, confidence). OAuth authentication gates write access.

### What's Working

| Component | Status |
|-----------|--------|
| DVD fingerprinting (OVID-DVD-1) | ✅ Stable — 113 tests, 100× determinism verified |
| REST API (lookup, submit, verify, search) | ✅ Complete — 124 tests |
| OAuth (GitHub, Apple, IndieAuth) | ✅ Complete — 69 auth tests |
| CLI (`ovid fingerprint`, `ovid lookup`, `ovid submit`) | ✅ Complete |
| Docker Compose dev stack | ✅ Operational |
| PostgreSQL schema (9 tables, Alembic) | ✅ Deployed |
| Blu-ray fingerprinting | 🔜 Planned for v0.2.0 |
| Web UI | 🔜 Planned for v0.2.0 |
| PyPI publishing | 🔜 Planned for v0.2.0 |

### Quick Start

```bash
# Fingerprint a DVD
pip install -e ovid-client/
ovid fingerprint /path/to/VIDEO_TS

# Start the API
docker compose up -d
docker compose exec api alembic upgrade head

# Submit a disc
ovid submit /path/to/VIDEO_TS --api-url http://localhost:8000 --token YOUR_JWT
```

### Documentation

| Document | Description |
|---|---|
| [`docs/fingerprint-spec.md`](docs/fingerprint-spec.md) | OVID-DVD-1 fingerprint algorithm specification |
| [`docs/api-reference.md`](docs/api-reference.md) | REST API endpoint reference |
| [`docs/cli-reference.md`](docs/cli-reference.md) | CLI command reference |
| [`docs/getting-started-dev.md`](docs/getting-started-dev.md) | Developer setup guide |
| [`docs/docker-quickstart.md`](docs/docker-quickstart.md) | Docker Compose quick-start |
| [`docs/OVID-product-spec.md`](docs/OVID-product-spec.md) | Product requirements |
| [`docs/OVID-technical-spec.md`](docs/OVID-technical-spec.md) | Technical specification |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

---

## Roadmap

| Version | Milestone | Status |
|---------|-----------|--------|
| **v0.1.0** | Foundation & Core Pipeline — DVD fingerprinting, REST API, OAuth, CLI wizard | ✅ Released |
| v0.2.0 | Full Format Support & Web UI — Blu-ray fingerprinting, Next.js web UI, PyPI, cloud deployment | 🔜 Next |
| v0.3.0 | Distribution & Community — Sync feeds, self-hosted mirrors, moderation, data dumps | Planned |
| v1.0.0 | Stable — Public API contract, ≥10k disc entries, foundation formed | Future |

---

## Contributing

OVID is in pre-alpha. The most valuable contribution right now is **feedback on the specs** in the `docs/` folder. Open an issue if you:

- Spot technical problems with the proposed fingerprinting algorithm
- Have experience with `libdvdread`, `libbluray`, or disc structure parsing
- Have a large disc collection and want to help seed the database at launch
- Want to help build the ARM integration

---

## Data License

All disc metadata contributed to the OVID database is released under **[CC0 1.0 Universal (Public Domain)](https://creativecommons.org/publicdomain/zero/1.0/)** — no rights reserved, free to use for any purpose.

The OVID software (API server, client library, web UI) is licensed under the **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**.

---

## What OVID Is Not

- **Not a piracy tool.** OVID stores disc structure metadata — title counts, durations, chapter maps, track layouts. It does not store, distribute, or assist in obtaining disc encryption keys, AACS keys, CSS keys, or any content that constitutes circumvention under the DMCA or similar laws.
- **Not a replacement for TMDB or TVDB.** OVID solves disc identity. Those services solve movie/TV metadata. Both are needed.
- **Not affiliated with MusicBrainz or MetaBrainz.** OVID is an independent project inspired by their model.

---

*OVID — Open Video Disc Identification Database*
*Started 2026 · Licensed AGPL-3.0 (software) / CC0 (data)*
