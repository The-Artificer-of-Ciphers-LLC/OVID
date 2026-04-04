# Phase 2: Multi-Disc Set Support - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

API and data model surface for box sets and multi-disc releases. Users can group related discs into sets, see sibling discs when looking up any disc in a set, and submit discs as part of sets via the web UI and CLI. The `disc_sets` table and `disc_set_id` FK already exist in the schema — this phase adds API routes, response shapes, web UI components, and CLI workflow.

Scope boundary: This covers multi-disc MOVIE sets (e.g., 4-disc Lord of the Rings extended). TV series episode-to-title mapping is deferred to v0.4.0.

</domain>

<decisions>
## Implementation Decisions

### Set Creation Flow
- **D-01:** Implicit set creation on first disc submit. When a user submits a disc with `total_discs > 1` and no `disc_set_id`, auto-create a set and link the disc to it.
- **D-02:** `POST /v1/set` also exists as a standalone endpoint for programmatic clients (ARM, CLI). Both paths — explicit creation and implicit creation on disc submit.

### API Response Shape
- **D-03:** Nested set object in `DiscLookupResponse`. Add `disc_set: { id, edition_name, total_discs, siblings: [{ fingerprint, disc_number, format, main_title, duration }] }`. Null when disc is not in a set. One request gets everything.
- **D-04:** `GET /v1/set` endpoint with search support (query by release name/edition). Enables submit form search-as-you-type and future browse page. `GET /v1/set/{set_id}` returns set with all member discs.

### Sibling Disc Display
- **D-05:** Inline card row on disc detail page. Below main disc info: "Part of: [Edition Name] (Disc 2 of 4)" header with horizontal row of compact sibling disc cards.
- **D-06:** Rich sibling cards showing disc number, format, main feature title, duration, and track count. Current disc highlighted. Fingerprint is the link target.

### Set Ownership & Editing
- **D-07:** Anyone authenticated can add discs to an existing set. Community-driven, matches OVID's open contribution model.
- **D-08:** Disc number conflicts rejected with 409 Conflict. First come, first served. Users can dispute via existing disc edit workflow.
- **D-09:** Orphan sets (0 discs linked) persist forever. They represent a real release even without discs. Users can find and link discs later.

### Submit Form UX
- **D-10:** "Part of a multi-disc set?" toggle in web submit form. When on: shows disc number input + search-as-you-type for existing sets (by release name/edition). If no match, creates new set.
- **D-11:** Edition name field uses suggested common values (autocomplete) with free text allowed. Common suggestions: "Extended Edition", "Director's Cut", "Theatrical", "Criterion Collection", "Special Edition", "Ultimate Edition". No constrained enum.

### CLI Set Workflow
- **D-12:** CLI `ovid submit` wizard prompts for set membership when disc_number metadata suggests multi-disc. "This looks like disc N. Part of a set? [Y/n]". If yes, search existing sets or create new.

### Set + Release Relationship
- **D-13:** Keep 1:1 relationship between set and release (existing FK). A trilogy box set is one "release" (the box set product). Individual movies are separate releases linked via disc_releases. Matches MusicBrainz medium/release model.

### Backward Compatibility
- **D-14:** Additive only — all new fields optional. `disc_set_id` optional in `DiscSubmitRequest`. `disc_set` object nullable in `DiscLookupResponse`. Existing clients work unchanged. `disc_number` validation only applies when `disc_set_id` is provided.

### Claude's Discretion
- Exact autocomplete implementation for edition name suggestions (client-side list vs server endpoint)
- Set search pagination strategy and sort order
- Sibling card responsive layout breakpoints
- Alembic migration approach for any new columns/indexes
- Test fixture design for multi-disc set scenarios
- Error message wording for 409 disc_number conflicts

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Data model
- `api/app/models.py` — DiscSet model (line 245), Disc.disc_set_id FK (line 89), relationships
- `api/app/schemas.py` — Existing DiscSubmitRequest (line 112), DiscLookupResponse (line 47), naming conventions
- `api/alembic/versions/7ffb31fc807f_initial_schema.py` — Original disc_sets table creation
- `api/alembic/versions/900000000001_add_sync_seq_numbers.py` — seq_num columns on disc_sets

### Requirements
- `.planning/REQUIREMENTS.md` §Multi-Disc Sets — SET-01 through SET-08
- `docs/mvp-beta-definition.md` §Beta-Required: Multi-Disc Set Support — scope boundary, implementation steps

### Architecture
- `.planning/research/ARCHITECTURE.md` §4 — Multi-disc set API/UI surface analysis
- `.planning/research/FEATURES.md` — Multi-disc set prioritization rationale
- `docs/OVID-product-spec.md` — Multi-disc set product decisions

### Prior art
- MusicBrainz Release/Medium model — referenced in `.planning/research/FEATURES.md` line 129

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DiscSet` SQLAlchemy model with release_id, edition_name, total_discs, seq_num — fully defined, table exists
- `Disc.disc_set_id` FK already in schema — no migration needed for basic linking
- `api/scripts/seed.py` creates a sample DiscSet — can extend for test fixtures
- `api/app/sync.py:next_seq()` — seq_num allocation for sync feed, reuse for disc_sets
- Web disc detail page at `web/app/disc/[fingerprint]/page.tsx` — extend for sibling display
- Web submit form at `web/app/submit/page.tsx` — extend for set toggle
- `web/lib/api.ts` — fetch wrapper with credentials: include (cookie auth from Phase 1)

### Established Patterns
- Pydantic schemas: `*Response` for reads, `*Create` for writes, `*Request` for API inputs
- Routes organized by domain: `api/app/routes/disc.py` — add set routes in new `api/app/routes/set.py`
- Eager loading via `joinedload`/`selectinload` in disc queries — extend for set+siblings
- `@limiter.limit()` decorator on all routes
- Web components use Tailwind CSS, Next.js App Router with async server components

### Integration Points
- `POST /v1/disc` (disc submission) — extend to handle disc_set_id + implicit set creation
- `GET /v1/disc/{fingerprint}` — extend response with disc_set nested object
- Sync feed — disc_sets need to appear as a new record type in sync diff
- CLI `ovid submit` wizard in `ovid-client/src/ovid/cli.py` — extend with set prompting

</code_context>

<specifics>
## Specific Ideas

- Sibling cards should feel like a "related items" row — similar to how streaming services show "other discs in this collection"
- The search-as-you-type for existing sets in the submit form should match on release title and edition name
- MusicBrainz's concept of "medium" within a "release" maps well to OVID's disc-within-set model

</specifics>

<deferred>
## Deferred Ideas

- TV series episode-to-title mapping — v0.4.0 per product spec
- Browse/explore sets page — Phase 6 (Web UI Completeness)
- Set merge/split (combining duplicate sets) — future moderation tool
- Set cover art/images — not in v0.3.0 scope

</deferred>

---

*Phase: 02-multi-disc-set-support*
*Context gathered: 2026-04-04*
