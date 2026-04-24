# OVID — MVP & Beta Launch Definition
**Status:** Updated 2026-04-04 — multi-disc support and chapter name data promoted to beta requirements
**Based on:** OVID-product-spec.md · OVID-technical-spec.md · fingerprint-spec.md · CHANGELOG.md
**Current version:** v0.2.0 "Soft Launch" — released 2026-04-04

---

## What the Spec Calls the MVP

The product spec defines **Milestone 0.2** as the MVP — the first version intended for public announcement and real community use. The spec's own summary: *"A usable product for the home archivist community. Publicly announced."*

This is distinct from the Foundation milestone (v0.1, just the fingerprinting library and raw API) — the MVP is the first thing a real user can actually sit down and use.

---

## What the Spec Says Must Work at MVP

These are the spec's formal "P0 — MVP cannot ship without these" requirements. Each one is marked with its current build status based on the v0.2.0 CHANGELOG.

### Disc Fingerprinting

| Requirement | Status |
|---|---|
| DVD fingerprint (OVID-DVD-1) from IFO structure | ✅ Done — v0.1.0 |
| Blu-ray fingerprint Tier 1 (AACS Disc ID) | ✅ Done — v0.2.0 |
| Blu-ray fingerprint Tier 2 (BDMV/PLAYLIST structure hash) | ✅ Done — v0.2.0 |
| Same disc always produces the same fingerprint on any drive/OS | ✅ Done — validated in tests |
| `ovid-client` Python library installable via `pip` | ⚠️ Built but **not yet published to PyPI** (noted in 0.1.0 known limitations) |

### Lookup API

| Requirement | Status |
|---|---|
| `GET /v1/disc/{fingerprint}` — returns metadata or 404 | ✅ Done — v0.1.0 |
| Response includes: title, year, edition, disc #, main feature index, format | ✅ Done |
| Response includes: per-title metadata (duration, chapters, audio, subtitles) | ✅ Done |
| `confidence` field returned with each match | ✅ Done |
| API responds in under 500ms at p95 | ⚠️ Not confirmed under load — needs verification |

### Submission API

| Requirement | Status |
|---|---|
| `POST /v1/disc` — authenticated disc submission | ✅ Done — v0.1.0 |
| Submitted entries marked `unverified` until second contributor confirms | ✅ Done — v0.2.0 |
| UPC barcode field on disc record | ✅ Done — UPC lookup endpoint added in v0.2.0 |

### Data Model

| Requirement | Status |
|---|---|
| Disc record (fingerprint, format, region, UPC, edition, verification status) | ✅ Done — 9-table PostgreSQL schema |
| Release record (links disc to movie — title, year, TMDB ID, IMDB ID) | ✅ Done |
| Title record (disc title index, type, duration, chapters) | ✅ Done |
| Track record (audio/subtitle/video tracks with language and codec) | ✅ Done |

### Web UI

| Requirement | Status |
|---|---|
| Search by movie title | ✅ Done — v0.2.0 Next.js UI |
| View a disc entry's full structure | ✅ Done |
| Submit a new disc entry via web form | ✅ Done (JSON file upload) |
| Email + password account creation | ❌ **Not built** — only OAuth login is available |
| GitHub OAuth login | ✅ Done — v0.1.0 |
| Google OAuth login | ✅ Done — v0.2.0 |
| Apple Sign-In | ⚠️ Built but **returns 501 in production** — not tested end-to-end |
| Mastodon / ActivityPub federated login | ✅ Done — v0.2.0 |
| Multiple OAuth providers linkable to one account | ✅ Done — v0.2.0 |
| Account settings: view and remove linked providers | ✅ Done — v0.2.0 |
| Email-match merge (prevent duplicate accounts) | ✅ Done — v0.2.0 |

---

## Gaps to Resolve Before Calling This "Beta"

These are items the spec requires for MVP exit that are either missing, unconfirmed, or carry known issues.

### 1. PyPI Publication
`ovid-client` is not yet published to PyPI. The spec says it must be installable via `pip`. Until it's published, developers and ARM integrators have to install from GitHub source — which is a real friction point for adoption.

**Question for you:** Should PyPI publication be a hard requirement before beta opens? Or is install-from-source acceptable for an initial beta audience of developers?

### 2. Apple Sign-In Returns 501 in Production
Apple Sign-In was fully built and the JWKS verification was hardened in v0.2.0, but the production instance returns 501. The known limitations note it is "not yet tested end-to-end in production."

**Question for you:** Is Apple Sign-In required at beta launch? It's in the spec as a P0 requirement. If it's broken in production, that's a gap — but it may not be blocking if your expected beta users are more likely to use GitHub, Google, or Mastodon.

### 3. Email + Password Login Not Built
The product spec lists "User account creation via email + password **or** any supported OAuth provider" as a P0 requirement. The current system is OAuth-only.

**Question for you:** Is email/password login needed for beta, or are the four working OAuth options (GitHub, Google, Mastodon, IndieAuth) sufficient to cover your early user base? This is a meaningful scope decision — adding email/password auth also adds password reset, email verification, and security surface area.

### 4. Database Seeded to ≥500 Disc Entries
The spec's exit criteria require 500 disc entries at MVP. At the end of v0.1.0, the database had 20 test entries. The v0.2.0 release log doesn't mention seeding to 500.

**Question for you:** Where does the database stand today? If you're below 500, this is something to address before the public announcement — a mostly-empty database makes a poor first impression for new visitors.

### 5. API Performance Under Load Not Verified
The spec requires ≤500ms at p95 under realistic load. This was flagged in v0.1.0 as needing attention; v0.2.0 doesn't confirm it was tested.

**Question for you:** Has any load testing been done? This may be fine at current traffic levels, but it's worth confirming before a public announcement drives a spike.

### 6. Domain Redirects (oviddb.com / oviddb.net)
The spec says `oviddb.com` and `oviddb.net` should redirect to `oviddb.org` at MVP. Not confirmed done.

**Question for you:** Are these domains registered and set up? This is a quick win to check off.

### 7. Public Announcement Not Yet Made
The v0.2.0 release is described as "Soft Launch" — the spec requires a public announcement to GitHub, ARM forums, r/DataHoarder, and Doom9 to officially close the MVP milestone.

**Question for you:** Is the plan to do a quiet beta first (limited audience, no announcement) and then do the public announcement later? That's a completely valid approach — it just means the current state is "private beta" rather than "public MVP."

---

## Recommended Beta Launch Checklist

Based on the spec and the current state of v0.2.0, here is a suggested minimum bar for opening to beta users:

**Hard requirements (must be done):**
- [ ] Confirm Apple Sign-In works in production, or explicitly mark it as "coming soon" in the UI
- [ ] Confirm database has ≥500 real disc entries (or seed it before announcement)
- [ ] Verify `oviddb.com` and `oviddb.net` redirect to `oviddb.org`

**Important but can follow shortly after beta opens:**
- [ ] Publish `ovid-client` to PyPI
- [ ] Decide and document email/password login status (build it or explicitly defer to P1)
- [ ] Run basic load test to confirm 500ms p95 threshold

**For the announcement:**
- [ ] Draft announcement post covering: what OVID is, how to submit a disc, how to integrate with ARM, and how to self-host
- [ ] Post to ARM GitHub Discussions, r/DataHoarder, and Doom9

---

## Beta-Required: Multi-Disc Set Support

Originally a P1/P2 item in the spec — **promoted to beta requirement**.

### What Already Exists (no new work needed)

The data model is largely ready. The database already has:
- `disc_number` and `total_discs` columns on every disc record
- A `disc_sets` table with `release_id`, `edition_name`, and `total_discs`
- A `disc_set_id` foreign key on `discs` linking a disc to its set
- `disc_number` and `total_discs` are already accepted in `POST /v1/disc` and returned in `GET /v1/disc/{fingerprint}`

A single-disc movie already works. The gaps are entirely in the API surface and web UI — the plumbing is there, it just has no controls yet.

### What Needs to Be Built

**API — 3 new or modified endpoints:**

1. `POST /v1/set` — create a disc set record
   - Body: `{ release_id, edition_name, total_discs }`
   - Returns: the new set's UUID
   - Auth: required

2. `GET /v1/set/{set_id}` — retrieve a disc set with all its member discs
   - Returns: edition name, total disc count, list of member discs (fingerprint, disc number, format, status, title info)
   - Auth: none (public read)

3. Update `POST /v1/disc` — add optional `disc_set_id` field to `DiscSubmitRequest`
   - When present, validates that the set exists and `disc_number` ≤ `total_discs`
   - Attaches the disc to the set

4. Update `GET /v1/disc/{fingerprint}` response — when a disc belongs to a set, include a `set` block:
   ```json
   "set": {
     "set_id": "...",
     "edition_name": "Extended Edition",
     "total_discs": 4,
     "siblings": [
       { "disc_number": 1, "fingerprint": "dvd1-abc...", "status": "verified" },
       { "disc_number": 3, "fingerprint": "dvd1-def...", "status": "unverified" }
     ]
   }
   ```

**Database — 1 new migration:**
- Add `seq_num` column to `disc_sets` (needed for sync feed parity — all tables tracked by sync should have it; `disc_sets` currently does not)

**Web UI:**
- Disc detail page: show sibling discs when a set is present
- Submission form: "Part of a multi-disc set?" toggle that reveals disc number + set fields
- New set creation flow (can be minimal — name + total disc count)

**CLI:**
- Update `ovid submit` wizard: if `disc_number > 1` or `total_discs > 1` is detected from fingerprint metadata, prompt for set membership

**Scope boundary:** This covers multi-disc MOVIE sets (e.g., 4-disc Lord of the Rings). TV series episode-to-title mapping stays deferred to v0.4.0 per the existing spec.

---

## Beta-Required: Chapter Name Data

Originally a P1 item in the spec — **promoted to beta requirement**.

### What Already Exists (no new work needed)

- `disc_titles.chapter_count` stores the integer count of chapters per title — this stays as-is and is authoritative
- `disc_titles.display_name` stores the title's own name (e.g., "The Fellowship of the Ring") — not affected

### What Needs to Be Built

Chapter names are optional community-contributed data. Many discs will never have them — that's fine. The goal is to make it *possible* to store and retrieve them where they exist.

**Database — 1 new table, 1 new migration:**

New table `disc_chapters`:
```
disc_chapters
  id              UUID PK
  disc_title_id   UUID FK → disc_titles.id  (CASCADE delete)
  chapter_index   SMALLINT NOT NULL   (1-based, matches disc chapter numbers)
  name            VARCHAR(200)         (nullable — some chapters have no name)
  start_time_secs INTEGER              (nullable — offset from title start)
```

Unique constraint on `(disc_title_id, chapter_index)`.

**API — schemas and route updates:**

1. New `ChapterResponse` schema:
   ```json
   { "chapter_index": 1, "name": "Opening Credits", "start_time_secs": 0 }
   ```

2. New `ChapterCreate` schema (for submission):
   ```json
   { "chapter_index": 1, "name": "Opening Credits", "start_time_secs": 0 }
   ```

3. Add `chapters: list[ChapterResponse]` to `TitleResponse` (default empty list — backward-compatible)

4. Add `chapters: list[ChapterCreate]` to `TitleCreate` (default empty list — backward-compatible, no breaking change to existing submissions)

5. Update `POST /v1/disc` route to write chapter rows when chapters are present in the payload

6. Update `GET /v1/disc/{fingerprint}` to load and return chapter data (eagerly loaded alongside tracks)

7. Update sync feed schemas (`SyncTitleRecord`) to include chapters so mirrors stay current

**No change to fingerprinting** — chapter names are community metadata, not structural disc data. They do not affect the fingerprint algorithm.

**Web UI:**
- Disc detail page: show chapter names inline under each title when present
- Submission form: optional chapter name entry per title (expandable section, not required)

**CLI:**
- `ovid submit` wizard: offer an optional step to enter chapter names after the main submission is confirmed

---

## What Is NOT Required at Beta (Remaining P1/P2 Items)

These remain deferred:

- Duplicate/alias detection between submissions
- Community voting on conflicting entries
- CC0 monthly database dump
- JavaScript/Node client library
- TV series episode-to-title mapping (multi-disc sets for movies are now covered above)
- UPC barcode lookup via `GET /disc/upc/{upc}` — actually already built in v0.2.0 (bonus!)
- Self-hosted node sync — already built in v0.2.0 (bonus!)

---

*Document prepared 2026-04-04 · Updated 2026-04-04: multi-disc sets and chapter names promoted to beta*
