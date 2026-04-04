# Phase 3: Chapter Name Data - Context

**Gathered:** 2026-04-04
**Status:** Ready for planning

<domain>
## Phase Boundary

OVID stores and returns chapter-level metadata for disc titles. Chapters have an index, optional name, and optional start time. Blu-ray scans extract MPLS chapter timestamps and bdmt_*.xml disc/title names when present. DVD scans extract chapter timestamps from IFO PGC data. The web UI shows chapters on the detail page and accepts them in the submit form. The sync feed includes chapter data so mirrors receive it.

</domain>

<decisions>
## Implementation Decisions

### Chapter Data Model
- **D-01:** Chapter names are optional (nullable). Chapters can have just index + start_time_secs with no name. Blu-rays without bdmt still get timestamp-only chapters from MPLS marks.
- **D-02:** Single language per chapter name. Parse the primary bdmt file (matched to disc region), not all language variants. No language column in the chapter table.
- **D-03:** Start time stored as integer seconds (start_time_secs). Convert 45kHz ticks to seconds before storage. Matches duration_secs pattern used elsewhere.
- **D-04:** Chapters nested inside titles. Each TitleCreate gets an optional `chapters: list[ChapterCreate]` field. Mirrors how chapters belong to titles in the data model and matches the titles-to-tracks nesting pattern.
- **D-05:** Max 200 characters for chapter name. Chapter index is 1-based (matches how users think about chapters: "Chapter 1").
- **D-06:** Chapters inherit sync tracking from parent disc. No own seq_num column. When a disc's seq_num updates, chapters come along. Matches how titles/tracks sync today.

### Blu-ray Extraction
- **D-07:** Chapter data extracted during fingerprinting, not as a separate CLI step. MPLS chapter marks and bdmt names available in the submit wizard automatically.
- **D-08:** Missing bdmt_*.xml is a silent skip. No warning, no error. ~60% of Blu-rays lack bdmt. MPLS timestamps still extracted.
- **D-09:** bdmt file selection: match disc region to language variant. If no region match found, fall back to first bdmt_*.xml found.

### Web UI
- **D-10:** Chapters shown as expandable list under each title on disc detail page. Collapsed by default. Click to expand and see chapter index, name (if present), and start time.
- **D-11:** Submit form has expandable "Add chapters" section per title. Rows with auto-increment index, name text input, and start time formatted input. Add/remove buttons.

### DVD Chapter Handling
- **D-12:** DVD chapter timestamps extracted from IFO PGC data and stored as name-less chapters (index + start_time_secs, name=null). Gives DVD discs parity with Blu-ray timestamp data.

### Claude's Discretion
- IFO parser cell-time extraction implementation approach (PGC cell playback info parsing may be complex — Claude decides the technical approach)
- Exact chapter list expand/collapse animation and styling
- Start time display format on the web UI (e.g., "1:23:45" vs "1h 23m 45s")
- Chapter row editor interaction details (tab order, validation timing)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Chapter data and extraction
- `docs/disc-metadata-enrichment-research.md` -- Research on bdmt_*.xml structure, MPLS chapter marks, and extraction feasibility
- `ovid-client/src/ovid/mpls_parser.py` -- Existing MPLS parser with ChapterMark extraction (45kHz timestamps)
- `ovid-client/src/ovid/ifo_parser.py` -- DVD IFO parser with PGCInfo (chapter_count only, no per-chapter timestamps yet)
- `arm/identify_original.py` -- ARM's existing bdmt_eng.xml parser (reference implementation for XML structure)

### API and data model
- `api/app/models.py` -- DiscTitle model (has chapter_count column, relationship target for new disc_chapters table)
- `api/app/schemas.py` -- TitleCreate and TitleResponse schemas (extend with chapters list)
- `api/app/routes/disc.py` -- Disc submit and lookup routes (extend for chapter data)
- `api/app/sync.py` -- Sync feed builder (extend SyncTitleRecord for chapter data)

### Web UI
- `web/app/disc/[fingerprint]/page.tsx` -- Disc detail page (add chapter display under titles)
- `web/components/SubmitForm.tsx` -- Submit form (add chapter entry sections)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mpls_parser.py:ChapterMark` — Already extracts chapter timestamps from MPLS. Has mark_type, play_item_ref, timestamp (45kHz ticks), duration_seconds (float). Filter for mark_type=1 (entry marks = chapters).
- `ifo_parser.py:PGCInfo` — Has chapter_count per PGC. Cell playback time parsing needs to be added for DVD chapter timestamps.
- `arm/identify_original.py` — Reference for bdmt_eng.xml parsing. Uses ElementTree, extracts disc title from `<di:name>` tag.
- `SiblingDiscs.tsx` — Expandable UI pattern reference (can inform chapter list expand/collapse).

### Established Patterns
- Titles-to-tracks nesting: `TitleCreate.audio_tracks` and `TitleCreate.subtitle_tracks` are lists of `TrackCreate`. Chapters follow this same nesting pattern.
- Eager loading: Disc lookup uses `joinedload(Disc.titles).joinedload(DiscTitle.tracks)`. Chapters add another level: `joinedload(DiscTitle.chapters)`.
- Migration pattern: Sequential revision IDs (900000000004 is latest). Next is 900000000005.
- Sync feed: `SyncTitleRecord` already has a `tracks` list. Add a `chapters` list following the same pattern.

### Integration Points
- `ovid-client/src/ovid/bd_disc.py` — Blu-ray disc class where chapter data from MPLS + bdmt merges before fingerprint output
- `ovid-client/src/ovid/cli.py` — Submit wizard Step 3 where chapter entry would occur
- `api/main.py` — No new router needed (chapters are part of disc submission, not standalone)

</code_context>

<specifics>
## Specific Ideas

- bdmt region matching: Map disc region code to ISO 639-2 language codes for bdmt file selection (e.g., region A → eng, region B → varies by country). Need a simple mapping table.
- DVD chapter extraction is lower priority than Blu-ray — acceptable to implement with less precision if IFO cell-time parsing proves complex.

</specifics>

<deferred>
## Deferred Ideas

- Multi-language chapter names (all bdmt variants) — future phase if demand exists
- Chapter name editing in the web UI (post-submission corrections) — Phase 6 web completeness
- Bulk chapter paste in submit form — could add later if manual entry proves too slow
- Chapter search/filtering — not in scope for basic chapter display

</deferred>

---

*Phase: 03-chapter-name-data*
*Context gathered: 2026-04-04*
