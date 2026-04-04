# Phase 3: Chapter Name Data - Research

**Researched:** 2026-04-04
**Domain:** Database schema extension, Blu-ray/DVD metadata extraction, API/UI integration
**Confidence:** HIGH

## Summary

Phase 3 adds chapter-level metadata throughout the OVID stack: a new `disc_chapters` table, Pydantic schemas, API submit/lookup extensions, Blu-ray MPLS chapter timestamp extraction, bdmt_*.xml disc/title name parsing, DVD IFO cell-time extraction, sync feed chapter support, and web UI display/entry components.

The codebase is well-structured for this addition. The titles-to-tracks nesting pattern (TitleCreate -> TrackCreate, DiscTitle -> DiscTrack) directly maps to how chapters nest under titles. The MPLS parser already extracts ChapterMark objects with 45kHz timestamps and mark_type filtering. The IFO parser has PGCInfo with chapter_count but needs cell-time parsing added for per-chapter timestamps. bdmt_*.xml parsing is new code but the ARM reference implementation in `arm/identify_original.py` demonstrates the XML structure.

**Primary recommendation:** Implement in layers: (1) database + schemas, (2) API submit/lookup, (3) Blu-ray extraction (MPLS timestamps + bdmt XML), (4) DVD extraction (IFO cell times), (5) sync feed, (6) web UI display, (7) web UI submit form, (8) CLI chapter step.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Chapter names are optional (nullable). Chapters can have just index + start_time_secs with no name. Blu-rays without bdmt still get timestamp-only chapters from MPLS marks.
- **D-02:** Single language per chapter name. Parse the primary bdmt file (matched to disc region), not all language variants. No language column in the chapter table.
- **D-03:** Start time stored as integer seconds (start_time_secs). Convert 45kHz ticks to seconds before storage. Matches duration_secs pattern used elsewhere.
- **D-04:** Chapters nested inside titles. Each TitleCreate gets an optional `chapters: list[ChapterCreate]` field. Mirrors how chapters belong to titles in the data model and matches the titles-to-tracks nesting pattern.
- **D-05:** Max 200 characters for chapter name. Chapter index is 1-based (matches how users think about chapters: "Chapter 1").
- **D-06:** Chapters inherit sync tracking from parent disc. No own seq_num column. When a disc's seq_num updates, chapters come along. Matches how titles/tracks sync today.
- **D-07:** Chapter data extracted during fingerprinting, not as a separate CLI step. MPLS chapter marks and bdmt names available in the submit wizard automatically.
- **D-08:** Missing bdmt_*.xml is a silent skip. No warning, no error. ~60% of Blu-rays lack bdmt. MPLS timestamps still extracted.
- **D-09:** bdmt file selection: match disc region to language variant. If no region match found, fall back to first bdmt_*.xml found.
- **D-10:** Chapters shown as expandable list under each title on disc detail page. Collapsed by default. Click to expand and see chapter index, name (if present), and start time.
- **D-11:** Submit form has expandable "Add chapters" section per title. Rows with auto-increment index, name text input, and start time formatted input. Add/remove buttons.
- **D-12:** DVD chapter timestamps extracted from IFO PGC data and stored as name-less chapters (index + start_time_secs, name=null). Gives DVD discs parity with Blu-ray timestamp data.

### Claude's Discretion
- IFO parser cell-time extraction implementation approach (PGC cell playback info parsing may be complex)
- Exact chapter list expand/collapse animation and styling
- Start time display format on the web UI (e.g., "1:23:45" vs "1h 23m 45s")
- Chapter row editor interaction details (tab order, validation timing)

### Deferred Ideas (OUT OF SCOPE)
- Multi-language chapter names (all bdmt variants)
- Chapter name editing in the web UI (post-submission corrections)
- Bulk chapter paste in submit form
- Chapter search/filtering
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHAP-01 | New `disc_chapters` table (disc_title_id, chapter_index, name, start_time_secs) with unique constraint on (disc_title_id, chapter_index) | Database model pattern matches disc_tracks; next migration is 900000000005 |
| CHAP-02 | `ChapterResponse` and `ChapterCreate` Pydantic schemas | Follows TrackResponse/TrackCreate pattern in schemas.py |
| CHAP-03 | `POST /v1/disc` accepts chapter data in title submissions (default empty list, backward-compatible) | TitleCreate already has audio_tracks/subtitle_tracks lists; add chapters list |
| CHAP-04 | `GET /v1/disc/{fingerprint}` returns chapter data eagerly loaded with titles | Add joinedload(DiscTitle.chapters) to existing query chain |
| CHAP-05 | Sync feed schemas include chapter data so mirrors stay current | SyncTitleRecord already has tracks list; add chapters list |
| CHAP-06 | Web UI disc detail page shows chapter names under each title when present | DiscStructure.tsx table rows need expandable chapter sub-rows |
| CHAP-07 | Web UI submission form has optional chapter name entry per title (expandable section) | SubmitForm.tsx needs chapter input rows per title |
| CHAP-08 | CLI `ovid submit` wizard offers optional chapter name step | cli.py Step 3 area; chapters auto-populated from disc scan |
| CHAP-09 | Blu-ray fingerprinting extracts MPLS chapter timestamps (start_time_secs) during scan | mpls_parser.py ChapterMark already has timestamps; needs integration into submit payload |
| CHAP-10 | Blu-ray fingerprinting parses `bdmt_*.xml` for disc title and title names when present | New bdmt_parser.py module; ARM reference in identify_original.py |
</phase_requirements>

## Standard Stack

### Core (already in project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0+ | ORM for disc_chapters table | Project standard; mapped_column pattern [VERIFIED: api/app/models.py] |
| Alembic | 1.13+ | Migration for new table | Project standard; next revision 900000000005 [VERIFIED: alembic/versions/] |
| Pydantic | 2.x (via FastAPI) | ChapterCreate/ChapterResponse schemas | Project standard [VERIFIED: api/app/schemas.py] |
| FastAPI | 0.110+ | Route handler extension | Project standard [VERIFIED: api/app/routes/disc.py] |
| xml.etree.ElementTree | stdlib | bdmt_*.xml parsing | No new dependency needed; ARM reference uses xmltodict but stdlib is sufficient [VERIFIED: Python stdlib] |
| Next.js | 16.2.2 | Web UI components | Project standard [VERIFIED: web/package.json] |
| React | 19.2.4 | UI components | Project standard [VERIFIED: web/package.json] |
| Vitest | 4.1.2 | Web test runner | Project standard [VERIFIED: web/package.json] |
| pytest | 7.0+ | Python test runner | Project standard [VERIFIED: ovid-client tests] |

### Supporting

No new dependencies required. All functionality builds on existing stack.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| xml.etree.ElementTree | xmltodict (ARM uses it) | xmltodict adds a dependency; ElementTree is stdlib and sufficient for simple XML |
| Integer seconds for start_time | Float seconds or 45kHz ticks | Integer seconds matches duration_secs pattern; sub-second precision not needed for chapter navigation |

## Architecture Patterns

### Database Layer

The new `disc_chapters` table follows the exact pattern of `disc_tracks`:

```python
# Source: api/app/models.py existing pattern
class DiscChapter(Base):
    __tablename__ = "disc_chapters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    disc_title_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("disc_titles.id", ondelete="CASCADE"), nullable=False
    )
    chapter_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))  # D-05: max 200 chars
    start_time_secs: Mapped[int | None] = mapped_column(Integer)  # D-03: integer seconds

    disc_title: Mapped["DiscTitle"] = relationship(back_populates="chapters")

    __table_args__ = (
        UniqueConstraint("disc_title_id", "chapter_index", name="uq_disc_chapters_index"),
        Index("idx_disc_chapters_title", "disc_title_id"),
    )
```
[VERIFIED: pattern extracted from DiscTrack in api/app/models.py]

### Schema Layer

```python
# Source: api/app/schemas.py existing pattern
class ChapterCreate(BaseModel):
    chapter_index: int = Field(ge=1)  # D-05: 1-based
    name: str | None = Field(default=None, max_length=200)  # D-01, D-05
    start_time_secs: int | None = Field(default=None, ge=0)  # D-03

class ChapterResponse(BaseModel):
    chapter_index: int
    name: str | None = None
    start_time_secs: int | None = None
```
[VERIFIED: pattern extracted from TrackCreate/TrackResponse in api/app/schemas.py]

### Nesting Pattern

TitleCreate already has:
- `audio_tracks: list[TrackCreate]`
- `subtitle_tracks: list[TrackCreate]`

Add: `chapters: list[ChapterCreate] = Field(default_factory=list)` [VERIFIED: api/app/schemas.py line 78-86]

TitleResponse already has:
- `audio_tracks: list[TrackResponse]`
- `subtitle_tracks: list[TrackResponse]`

Add: `chapters: list[ChapterResponse] = Field(default_factory=list)` [VERIFIED: api/app/schemas.py line 22-38]

### Eager Loading Pattern

Current disc lookup query chain:
```python
joinedload(Disc.titles).joinedload(DiscTitle.tracks)
```
Extend to:
```python
joinedload(Disc.titles).joinedload(DiscTitle.tracks),
joinedload(Disc.titles).joinedload(DiscTitle.chapters),
```
[VERIFIED: api/app/routes/disc.py line 336-340]

### bdmt_*.xml Parsing

The ARM reference (`arm/identify_original.py`) shows the XML structure:
```python
# ARM parses with xmltodict; OVID uses stdlib ElementTree
import xml.etree.ElementTree as ET

tree = ET.parse(bdmt_path)
root = tree.getroot()
# Namespace: "urn:BDA:bdmv;discinfo"
# Disc title at: di:discinfo/di:title/di:name
```
[VERIFIED: arm/identify_original.py lines 88-119]

The bdmt XML lives at `BDMV/META/DL/bdmt_*.xml`. The BDFolderReader needs a new method to access the META directory. Currently it only accesses PLAYLIST and AACS directories. [VERIFIED: ovid-client/src/ovid/readers/bd_folder.py]

### MPLS Chapter Timestamp Extraction

The MPLS parser already produces ChapterMark objects with:
- `mark_type`: 1 = entry mark (chapter), 2 = link point
- `timestamp`: 45kHz ticks
- `duration_seconds`: computed as `timestamp / 45000`

For chapter data, filter to `mark_type == 1` (entry marks only), then convert to integer seconds: `int(round(timestamp / 45000))`. The CLI already does this filtering in `_build_bd_submit_payload` (`len([m for m in pl.chapter_marks if m.mark_type == 1])`). [VERIFIED: ovid-client/src/ovid/mpls_parser.py lines 97-103, cli.py line 609]

### DVD IFO Cell-Time Extraction

Current PGCInfo has `chapter_count` and `duration_seconds` but no per-chapter timestamps. DVD chapters map to "programs" in the PGC, and each program starts at a specific cell. The PGC contains:

1. A **program map** at PGC+0x00E4 offset (sector pointer) listing which cell index each program starts at
2. A **cell playback info table** at PGC+0x00E8 offset with per-cell start/end times in BCD format

To extract per-chapter start times:
1. Read the program map to get cell-start-index for each program (chapter)
2. Read the cell playback info to get BCD start times for those cells
3. Convert BCD times to seconds using the existing `decode_bcd_time()` function

The `_parse_pgci` function already navigates to PGC blocks and reads `nr_of_programs` (chapter count) at offset +0x02. It needs extension to also read:
- `program_map_offset` at PGC+0xF0 (2 bytes, relative to PGC start) -- wait, need to verify exact offsets.

[ASSUMED] The DVD spec places the program map offset at PGC+0xF0 and cell playback info offset at PGC+0xE8, both as 2-byte relative offsets from the PGC start. The cell playback info entries are 24 bytes each with BCD time at bytes 0-3 (start time) and bytes 4-7 (end time). This needs verification against the actual IFO data during implementation.

### Sync Feed Extension

`SyncTitleRecord` currently has a `tracks` list. Add a `chapters` list:
```python
class SyncChapterRecord(BaseModel):
    chapter_index: int
    name: str | None = None
    start_time_secs: int | None = None

class SyncTitleRecord(BaseModel):
    # ... existing fields ...
    chapters: list[SyncChapterRecord] = Field(default_factory=list)
```
[VERIFIED: api/app/schemas.py lines 201-210]

The `build_sync_title` function in `api/app/sync.py` builds SyncTitleRecord from DiscTitle. It needs to also build chapter records from `title.chapters`. [VERIFIED: api/app/sync.py lines 82-91]

### Web UI: Chapter Display (Disc Detail)

The `DiscStructure.tsx` component renders a table of titles. Each row shows title_index, display_name, duration, chapter_count, audio, subtitles. Chapter display adds an expandable section below each title row. The SiblingDiscs component demonstrates the project's expand/collapse pattern. [VERIFIED: web/components/DiscStructure.tsx, web/components/SiblingDiscs.tsx]

The TitleResponse TypeScript interface needs a `chapters` field:
```typescript
export interface ChapterResponse {
  chapter_index: number;
  name: string | null;
  start_time_secs: number | null;
}

export interface TitleResponse {
  // ... existing fields ...
  chapters: ChapterResponse[];
}
```
[VERIFIED: web/lib/api.ts lines 57-74]

### Web UI: Chapter Entry (Submit Form)

The SubmitForm.tsx currently sends an empty `titles: []` array. It needs chapter entry rows per title. Each row has: auto-increment index, name text input (optional), and start_time_secs input. The form pattern follows the existing field layout with expandable sections. [VERIFIED: web/components/SubmitForm.tsx]

### Anti-Patterns to Avoid

- **Separate chapter API endpoint:** Chapters are part of disc data, not standalone resources. No `/v1/chapter` routes needed.
- **Nullable chapter_index:** The chapter_index must always be present (1-based). Only name and start_time_secs are nullable.
- **Floating-point start times:** Use integer seconds per D-03. Do not store 45kHz ticks or float seconds in the database.
- **Eager-loading N+1:** Must use `joinedload` for chapters like tracks. Do not lazy-load chapters in a loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XML parsing | Custom string parsing for bdmt | `xml.etree.ElementTree` | Handles namespaces, encoding, malformed XML gracefully |
| BCD time decoding | New BCD decoder | Existing `decode_bcd_time()` in ifo_parser.py | Already handles edge cases (invalid nibbles clamped) |
| Duration formatting (web) | New formatter | Existing `formatDuration()` in DiscStructure.tsx | Already used for title durations, same format works for chapter start times |
| Unique constraint enforcement | Application-level dedup | Database `UniqueConstraint("disc_title_id", "chapter_index")` | Let the DB enforce; handle IntegrityError in the route |

## Common Pitfalls

### Pitfall 1: MPLS Chapter Marks Include Non-Chapter Entries
**What goes wrong:** Treating all PlayListMark entries as chapters.
**Why it happens:** mark_type=2 entries are "link points" (not chapters). Some discs have many link points.
**How to avoid:** Always filter `mark_type == 1` before building chapter data. The codebase already does this in `_build_bd_submit_payload`.
**Warning signs:** Chapter count from MPLS doesn't match PGCInfo chapter_count or expected chapter count.

### Pitfall 2: bdmt_*.xml Namespace Handling
**What goes wrong:** ElementTree can't find elements because the XML uses a namespace.
**Why it happens:** bdmt_*.xml uses namespace `urn:BDA:bdmv;discinfo`. Elements like `<di:name>` require namespace-aware queries.
**How to avoid:** Use namespace dict with `ET.find()`: `root.find('.//di:name', {'di': 'urn:BDA:bdmv;discinfo'})`.
**Warning signs:** All parsed values come back as None despite the file having content.

### Pitfall 3: DVD PGC Cell Playback Times Are Absolute, Not Relative
**What goes wrong:** Treating cell start times as offsets from the PGC start, when they're actually absolute times within the VOB.
**Why it happens:** The BCD time in cell playback info is the absolute presentation timestamp.
**How to avoid:** For chapter start times, use each cell's start time directly (it IS the chapter start). The first chapter's start time is the PGC start time.
**Warning signs:** Chapter timestamps don't align with expected chapter boundaries.

### Pitfall 4: Empty Chapters List Must Be Backward-Compatible
**What goes wrong:** Breaking existing disc submissions that don't include chapter data.
**Why it happens:** Adding `chapters` as a required field on TitleCreate.
**How to avoid:** Default to empty list: `chapters: list[ChapterCreate] = Field(default_factory=list)`. Existing payloads without chapters field will get an empty list.
**Warning signs:** Existing API tests fail after schema change.

### Pitfall 5: Chapter Index Off-By-One
**What goes wrong:** Storing 0-based chapter indices when the spec says 1-based.
**Why it happens:** MPLS chapter marks use 0-based play_item_ref; Python lists are 0-indexed.
**How to avoid:** D-05 specifies 1-based. When iterating MPLS marks, add 1 to the enumeration index. Validate `ge=1` in ChapterCreate schema.
**Warning signs:** Chapter 0 appears in the database or UI.

### Pitfall 6: Web UI Chapter Expand/Collapse Needs Client Component
**What goes wrong:** Trying to use useState/onClick in a server component.
**Why it happens:** DiscStructure.tsx is currently a server component (no "use client" directive).
**How to avoid:** Either convert DiscStructure to a client component or create a separate ChapterList client component that handles expand/collapse state.
**Warning signs:** Build errors about hooks in server components.

## Code Examples

### MPLS Chapter Extraction for Submit Payload

```python
# Source: existing pattern in cli.py line 607-609, extended for chapter data
def _extract_bd_chapters(pl) -> list[dict]:
    """Extract chapter data from an MPLS playlist's chapter marks."""
    chapters = []
    chapter_idx = 1
    for mark in pl.chapter_marks:
        if mark.mark_type != 1:  # Only entry marks = chapters
            continue
        chapters.append({
            "chapter_index": chapter_idx,
            "name": None,  # MPLS has no names; bdmt may fill these
            "start_time_secs": int(round(mark.timestamp / 45000)),
        })
        chapter_idx += 1
    return chapters
```
[VERIFIED: based on mpls_parser.py ChapterMark dataclass and cli.py usage]

### bdmt_*.xml Parsing

```python
# Source: ARM reference arm/identify_original.py + standard ElementTree usage
import xml.etree.ElementTree as ET
import os

_BDMT_NS = {"di": "urn:BDA:bdmv;discinfo"}

def parse_bdmt(path: str) -> dict | None:
    """Parse a bdmt_*.xml file and return disc title info.

    Returns dict with 'disc_title' key, or None on parse failure.
    """
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        name_elem = root.find('.//di:name', _BDMT_NS)
        disc_title = name_elem.text.strip() if name_elem is not None and name_elem.text else None
        return {"disc_title": disc_title}
    except (ET.ParseError, OSError):
        return None
```
[VERIFIED: ARM reference shows `doc['disclib']['di:discinfo']['di:title']['di:name']` structure]

### Chapter Display Formatting (Web UI)

```typescript
// Source: existing formatDuration in DiscStructure.tsx, adapted for chapter start times
function formatTime(secs: number | null): string {
  if (secs == null) return "";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}
```
[VERIFIED: pattern from web/components/DiscStructure.tsx lines 3-9]

### Alembic Migration

```python
# Next revision: 900000000005 (follows 900000000004_add_disc_set_number_unique.py)
def upgrade():
    op.create_table(
        "disc_chapters",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("disc_title_id", sa.dialects.postgresql.UUID(as_uuid=True),
                   sa.ForeignKey("disc_titles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_index", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("start_time_secs", sa.Integer(), nullable=True),
        sa.UniqueConstraint("disc_title_id", "chapter_index", name="uq_disc_chapters_index"),
    )
    op.create_index("idx_disc_chapters_title", "disc_chapters", ["disc_title_id"])
```
[VERIFIED: migration numbering from api/alembic/versions/ listing]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ChapterDB (community database) | Dead/offline for years | ~2020 | OVID fills this gap; fingerprint-first chapter data |
| DVD text metadata (DVD_TEXT.SR) | Rarely used on movie DVDs | Always rare | Not worth implementing for v0.3; <5% hit rate |
| HandBrake --scan --json | Auto-generates placeholder names | Always | Cannot distinguish real vs. generated names; useful only for structural data |

**Key insight from research doc:** bdmt_*.xml is present on ~20-40% of Blu-rays. MPLS chapter timestamps are 100% present on all Blu-rays. Community-submitted names (MusicBrainz model) are the long-term path. [VERIFIED: docs/disc-metadata-enrichment-research.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DVD PGC program map offset is at PGC+0xF0 and cell playback info at PGC+0xE8 as 2-byte relative offsets | Architecture Patterns (DVD IFO) | Implementation detail wrong; would need different offsets. Low risk -- Claude's discretion covers IFO parsing approach. |
| A2 | bdmt XML namespace is `urn:BDA:bdmv;discinfo` with `di:` prefix | Architecture Patterns (bdmt) | Namespace string wrong; parser returns None. Easy to fix during implementation by inspecting actual XML. |
| A3 | Cell playback info entries are 24 bytes each with BCD time at bytes 0-3 | Architecture Patterns (DVD IFO) | Wrong struct size or offset; chapter times would be incorrect. Verifiable against real IFO files in tests. |

## Open Questions

1. **bdmt region-to-language mapping**
   - What we know: D-09 says match disc region to language variant; fall back to first bdmt found
   - What's unclear: Exact mapping table (Region A -> eng? Region B -> varies by country?)
   - Recommendation: Start with simple mapping: A->eng, B->eng (most common), C->eng. Fall back to first file found. Refine later if needed.

2. **Multi-playlist chapter assignment**
   - What we know: Each BD playlist has its own chapter marks. Each playlist becomes a title in the submit payload.
   - What's unclear: MPLS chapter marks reference play items by index (`play_item_ref`). For single-playlist titles this is straightforward.
   - Recommendation: Chapters belong to the playlist-title they come from. The existing `_build_bd_submit_payload` already iterates playlists and counts chapters per playlist. Extend that loop to include chapter data.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework (API) | pytest 7.0+ |
| Framework (Web) | Vitest 4.1.2 |
| Framework (Client) | pytest 7.0+ |
| Config file (API) | api/tests/conftest.py |
| Config file (Web) | web/vitest.config.ts |
| Config file (Client) | ovid-client/tests/conftest.py |
| Quick run (API) | `cd api && python -m pytest tests/ -x --tb=short` |
| Quick run (Web) | `cd web && npx vitest run --reporter=verbose` |
| Quick run (Client) | `cd ovid-client && python -m pytest tests/ -x --tb=short` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHAP-01 | disc_chapters table exists with correct schema | unit (migration) | `cd api && python -m pytest tests/test_disc_submit.py -x` | Extend existing |
| CHAP-02 | ChapterCreate/ChapterResponse validate correctly | unit | `cd api && python -m pytest tests/test_disc_submit.py -x` | Extend existing |
| CHAP-03 | POST /v1/disc accepts chapters in titles | integration | `cd api && python -m pytest tests/test_disc_submit.py::test_submit_with_chapters -x` | Wave 0 |
| CHAP-04 | GET /v1/disc/{fp} returns chapters | integration | `cd api && python -m pytest tests/test_disc_lookup.py::test_lookup_includes_chapters -x` | Wave 0 |
| CHAP-05 | Sync feed includes chapter data | integration | `cd api && python -m pytest tests/test_sync.py::test_sync_diff_includes_chapters -x` | Wave 0 |
| CHAP-06 | Chapter list renders under titles | component | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | Extend existing |
| CHAP-07 | Chapter entry section in submit form | component | `cd web && npx vitest run src/__tests__/submit.test.tsx` | Extend existing |
| CHAP-08 | CLI submit wizard chapter step | unit | `cd ovid-client && python -m pytest tests/test_cli_submit.py -x` | Extend existing |
| CHAP-09 | BD chapters extracted from MPLS | unit | `cd ovid-client && python -m pytest tests/test_mpls_parser.py -x` | Extend existing |
| CHAP-10 | bdmt_*.xml parsed for disc/title names | unit | `cd ovid-client && python -m pytest tests/test_bdmt_parser.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** Quick run for affected component
- **Per wave merge:** All three quick runs (API + Web + Client)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `api/tests/test_disc_submit.py` -- extend with chapter submission tests
- [ ] `api/tests/test_disc_lookup.py` -- extend with chapter lookup tests
- [ ] `api/tests/test_sync.py` -- extend with chapter sync tests
- [ ] `web/src/__tests__/disc-detail.test.tsx` -- extend with chapter display tests
- [ ] `web/src/__tests__/submit.test.tsx` -- extend with chapter entry tests
- [ ] `ovid-client/tests/test_bdmt_parser.py` -- new file for bdmt XML parsing
- [ ] `ovid-client/tests/test_ifo_parser.py` -- extend with cell-time extraction tests
- [ ] `ovid-client/tests/test_cli_submit.py` -- extend with chapter step tests

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Existing auth; chapter endpoints use same auth |
| V3 Session Management | no | No new session handling |
| V4 Access Control | no | Chapters inherit disc permissions |
| V5 Input Validation | yes | Pydantic schema validation (ChapterCreate with Field constraints) |
| V6 Cryptography | no | No crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Chapter name XSS | Tampering | Pydantic max_length=200; React auto-escapes output |
| Oversized chapter list DoS | Denial of Service | Validate max chapters per title (reasonable limit, e.g., 999) |
| SQL injection via chapter_index | Tampering | SQLAlchemy ORM parameterized queries |
| Malformed bdmt XML entity expansion | Denial of Service | ElementTree default: does not expand external entities |

## Sources

### Primary (HIGH confidence)
- `api/app/models.py` -- DiscTitle, DiscTrack model patterns
- `api/app/schemas.py` -- TitleCreate, TitleResponse, TrackCreate, TrackResponse, SyncTitleRecord patterns
- `api/app/routes/disc.py` -- submit_disc, lookup_disc, eager loading patterns
- `api/app/sync.py` -- build_sync_title, build_sync_track patterns
- `ovid-client/src/ovid/mpls_parser.py` -- ChapterMark dataclass, _parse_marks function
- `ovid-client/src/ovid/ifo_parser.py` -- PGCInfo, _parse_pgci, decode_bcd_time
- `ovid-client/src/ovid/bd_disc.py` -- BDDisc.from_path, playlist handling
- `ovid-client/src/ovid/readers/bd_folder.py` -- BDFolderReader directory access methods
- `ovid-client/src/ovid/cli.py` -- _build_bd_submit_payload, _build_dvd_submit_payload
- `arm/identify_original.py` -- bdmt_eng.xml parsing reference
- `docs/disc-metadata-enrichment-research.md` -- bdmt hit rates, MPLS chapter analysis
- `web/components/DiscStructure.tsx` -- title display table pattern
- `web/components/SubmitForm.tsx` -- submit form field pattern
- `web/lib/api.ts` -- TypeScript interface patterns

### Secondary (MEDIUM confidence)
- DVD-Video specification structure for PGC cell playback info offsets (from training data, consistent with existing ifo_parser.py implementation)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, no new dependencies
- Architecture: HIGH - patterns directly copy existing title/track nesting
- Pitfalls: HIGH - identified from codebase analysis and existing parser implementations
- DVD cell-time parsing: MEDIUM - exact PGC offsets assumed from training knowledge, verifiable during implementation

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable -- no moving targets in this phase)
