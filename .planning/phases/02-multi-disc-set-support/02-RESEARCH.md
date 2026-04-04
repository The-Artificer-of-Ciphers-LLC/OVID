# Phase 2: Multi-Disc Set Support - Research

**Researched:** 2026-04-04
**Domain:** API routes, Pydantic schemas, SQLAlchemy queries, Next.js UI components, CLI wizard extension
**Confidence:** HIGH

## Summary

Phase 2 adds the API and UI surface for multi-disc set support. The foundational data model already exists: `disc_sets` table with `id`, `release_id`, `edition_name`, `total_discs`, `seq_num`, and `created_at` columns; `discs.disc_set_id` FK; and SQLAlchemy relationships (`Disc.disc_set`, `DiscSet.discs`). No migration is needed for the core linking. One migration IS needed: a unique constraint on `(disc_set_id, disc_number)` to enforce the D-08 decision that disc number conflicts return 409.

The work breaks into four layers: (1) new API routes in `api/app/routes/set.py` for `POST /v1/set`, `GET /v1/set/{set_id}`, and `GET /v1/set` search; (2) extensions to existing `POST /v1/disc` for implicit set creation and `disc_set_id` linking, and `GET /v1/disc/{fingerprint}` for sibling disc nesting; (3) web UI components for sibling display on disc detail and set toggle on submit form; (4) CLI wizard extension for set prompting.

**Primary recommendation:** Build API layer first (schemas + routes + tests), then extend existing endpoints, then web UI, then CLI. Each layer is independently testable.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Implicit set creation on first disc submit. When a user submits a disc with `total_discs > 1` and no `disc_set_id`, auto-create a set and link the disc to it.
- **D-02:** `POST /v1/set` also exists as a standalone endpoint for programmatic clients (ARM, CLI). Both paths -- explicit creation and implicit creation on disc submit.
- **D-03:** Nested set object in `DiscLookupResponse`. Add `disc_set: { id, edition_name, total_discs, siblings: [{ fingerprint, disc_number, format, main_title, duration }] }`. Null when disc is not in a set. One request gets everything.
- **D-04:** `GET /v1/set` endpoint with search support (query by release name/edition). Enables submit form search-as-you-type and future browse page. `GET /v1/set/{set_id}` returns set with all member discs.
- **D-05:** Inline card row on disc detail page. Below main disc info: "Part of: [Edition Name] (Disc 2 of 4)" header with horizontal row of compact sibling disc cards.
- **D-06:** Rich sibling cards showing disc number, format, main feature title, duration, and track count. Current disc highlighted. Fingerprint is the link target.
- **D-07:** Anyone authenticated can add discs to an existing set. Community-driven, matches OVID's open contribution model.
- **D-08:** Disc number conflicts rejected with 409 Conflict. First come, first served. Users can dispute via existing disc edit workflow.
- **D-09:** Orphan sets (0 discs linked) persist forever. They represent a real release even without discs.
- **D-10:** "Part of a multi-disc set?" toggle in web submit form. When on: shows disc number input + search-as-you-type for existing sets (by release name/edition). If no match, creates new set.
- **D-11:** Edition name field uses suggested common values (autocomplete) with free text allowed. Common suggestions: "Extended Edition", "Director's Cut", "Theatrical", "Criterion Collection", "Special Edition", "Ultimate Edition". No constrained enum.
- **D-12:** CLI `ovid submit` wizard prompts for set membership when disc_number metadata suggests multi-disc. "This looks like disc N. Part of a set? [Y/n]". If yes, search existing sets or create new.
- **D-13:** Keep 1:1 relationship between set and release (existing FK). A trilogy box set is one "release" (the box set product).
- **D-14:** Additive only -- all new fields optional. `disc_set_id` optional in `DiscSubmitRequest`. `disc_set` object nullable in `DiscLookupResponse`. Existing clients work unchanged.

### Claude's Discretion
- Exact autocomplete implementation for edition name suggestions (client-side list vs server endpoint)
- Set search pagination strategy and sort order
- Sibling card responsive layout breakpoints
- Alembic migration approach for any new columns/indexes
- Test fixture design for multi-disc set scenarios
- Error message wording for 409 disc_number conflicts

### Deferred Ideas (OUT OF SCOPE)
- TV series episode-to-title mapping -- v0.4.0
- Browse/explore sets page -- Phase 6
- Set merge/split (combining duplicate sets) -- future moderation tool
- Set cover art/images -- not in v0.3.0

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SET-01 | `POST /v1/set` creates a disc set record (release_id, edition_name, total_discs) | New route in `api/app/routes/set.py`, new `DiscSetCreate`/`DiscSetResponse` schemas, auth required, seq_num allocation via `next_seq()` |
| SET-02 | `GET /v1/set/{set_id}` returns set with all member discs | New route, eager load `DiscSet.discs` with titles for main feature info, new `DiscSetDetailResponse` schema |
| SET-03 | `POST /v1/disc` accepts optional `disc_set_id`, validates disc_number <= total_discs | Extend `DiscSubmitRequest` schema with optional `disc_set_id`, add validation in `submit_disc()`, add unique constraint migration for `(disc_set_id, disc_number)` |
| SET-04 | `GET /v1/disc/{fingerprint}` includes sibling discs when part of a set | Extend `_disc_to_response()` helper, add `disc_set` nested field to `DiscLookupResponse`, eager load `Disc.disc_set` + `DiscSet.discs` |
| SET-05 | `disc_sets` table gets `seq_num` column for sync feed parity | Already done -- `seq_num` column exists in model and migration `900000000001` |
| SET-06 | Web UI disc detail page shows sibling discs in a set | New `SiblingDiscs` component, extend `disc/[fingerprint]/page.tsx`, add TypeScript interfaces |
| SET-07 | Web UI submission form has multi-disc toggle revealing disc number and set fields | Extend `SubmitForm.tsx` with toggle state, set search input, autocomplete for edition names |
| SET-08 | CLI `ovid submit` wizard prompts for set membership when disc_number > 1 | Extend `cli.py` submit command, add set search/create methods to `OVIDClient` |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Database:** PostgreSQL 16; all queries via SQLAlchemy ORM with parameterized statements
- **Auth:** JWT (1-hour access, 30-day refresh); write endpoints require Bearer token; read endpoints unauthenticated
- **API contract:** Read endpoints unauthenticated; write endpoints require Bearer token
- **Git strategy:** Gitflow model; conventional commits
- **Naming:** Python: snake_case, PascalCase models. TypeScript: PascalCase components, camelCase functions. Schemas: `*Response` for reads, `*Create` for writes, `*Request` for API inputs
- **Routes:** Organized by domain in `api/app/routes/`. Use `APIRouter` with prefix/tags
- **Rate limiting:** `@limiter.limit(_dynamic_limit)` decorator on all routes
- **Web:** Next.js App Router, async server components, Tailwind CSS, `@/` import alias
- **CLI:** Click-based, Rich for output formatting
- **Tests:** pytest for API, Vitest for web; SQLite in-memory for API tests
- **Logging:** `%-style` formatting, structured key=value pairs

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.110+ | API framework | Already in use, async route handlers |
| SQLAlchemy | 2.0+ | ORM with relationships | Already in use, eager loading patterns established |
| Pydantic | v2 | Schema validation | Already in use via FastAPI integration |
| Alembic | 1.13+ | Database migrations | Already in use for schema changes |
| Next.js | 16.2.2 | Web UI framework | Already in use |
| React | 19.2.4 | UI components | Already in use |
| Click | 8.0+ | CLI framework | Already in use |
| Rich | 13.0+ | CLI output formatting | Already in use |

No new dependencies required. This phase extends existing patterns only. [VERIFIED: codebase inspection]

## Architecture Patterns

### New File Structure
```
api/app/routes/set.py              # NEW — disc set CRUD routes
api/app/routes/disc.py             # MODIFY — extend submit + lookup
api/app/schemas.py                 # MODIFY — add set schemas
api/app/models.py                  # MODIFY — add unique constraint
api/app/sync.py                    # MODIFY — add build_sync_set()
api/alembic/versions/XXXXXX_*.py   # NEW — unique constraint migration
api/tests/test_disc_sets.py        # NEW — set route tests
api/tests/test_disc_submit.py      # MODIFY — add set integration tests
api/tests/conftest.py              # MODIFY — add set seed helpers
web/lib/api.ts                     # MODIFY — add set types + functions
web/components/SiblingDiscs.tsx     # NEW — sibling display component
web/components/SetSearchInput.tsx   # NEW — search-as-you-type for sets
web/app/disc/[fingerprint]/page.tsx # MODIFY — integrate SiblingDiscs
web/components/SubmitForm.tsx       # MODIFY — add set toggle section
ovid-client/src/ovid/client.py     # MODIFY — add set search/create
ovid-client/src/ovid/cli.py        # MODIFY — extend submit wizard
```

### Pattern 1: New Route Module (set.py)
**What:** Follow the existing `disc.py` pattern -- `APIRouter(prefix="/v1", tags=["set"])`, helper functions prefixed with `_`, Depends injection for db and auth.
**When to use:** All new set endpoints.
**Example:**
```python
# Source: existing pattern in api/app/routes/disc.py
router = APIRouter(prefix="/v1", tags=["set"])

@router.post("/set", response_model=DiscSetResponse, status_code=201)
@limiter.limit(_dynamic_limit)
def create_disc_set(
    body: DiscSetCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    ...
```
[VERIFIED: codebase pattern in disc.py]

### Pattern 2: Nested Response Extension
**What:** Add optional `disc_set` field to `DiscLookupResponse`. When disc has a set, populate with set metadata and sibling disc summaries. When no set, field is `None`.
**When to use:** Extending existing response shapes additively (D-14).
**Example:**
```python
# New schemas in api/app/schemas.py
class SiblingDiscSummary(BaseModel):
    fingerprint: str
    disc_number: int
    format: str
    main_title: str | None = None
    duration_secs: int | None = None

class DiscSetNested(BaseModel):
    id: str
    edition_name: str | None = None
    total_discs: int
    siblings: list[SiblingDiscSummary] = Field(default_factory=list)

class DiscLookupResponse(BaseModel):
    # ... existing fields ...
    disc_set: DiscSetNested | None = None  # NEW — null when not in a set
```
[VERIFIED: follows existing schema patterns in schemas.py]

### Pattern 3: Implicit Set Creation in submit_disc()
**What:** When `POST /v1/disc` receives `total_discs > 1` and no `disc_set_id`, auto-create a DiscSet and link the disc.
**When to use:** D-01 -- implicit set creation flow.
**Example:**
```python
# Inside submit_disc() in disc.py, after release creation
if body.total_discs > 1 and body.disc_set_id is None:
    disc_set = DiscSet(
        release_id=release.id,
        edition_name=body.edition_name,
        total_discs=body.total_discs,
        seq_num=next_seq(db),
    )
    db.add(disc_set)
    db.flush()
    disc.disc_set_id = disc_set.id
elif body.disc_set_id is not None:
    # Validate set exists and disc_number not taken
    existing_set = db.query(DiscSet).filter(DiscSet.id == body.disc_set_id).first()
    if existing_set is None:
        return _error_response(request_id, "not_found", "Disc set not found", 404)
    if body.disc_number > existing_set.total_discs:
        return _error_response(request_id, "validation_error",
            f"disc_number {body.disc_number} exceeds total_discs {existing_set.total_discs}", 422)
    disc.disc_set_id = body.disc_set_id
```
[VERIFIED: follows existing submit_disc() transaction pattern]

### Pattern 4: Eager Loading for Siblings
**What:** When loading a disc for lookup, eager load `disc_set` relationship and the set's `discs` collection.
**When to use:** `GET /v1/disc/{fingerprint}` response building.
**Example:**
```python
disc = (
    db.query(Disc)
    .options(
        joinedload(Disc.titles).joinedload(DiscTitle.tracks),
        selectinload(Disc.releases),
        joinedload(Disc.disc_set).selectinload(DiscSet.discs)
            .joinedload(Disc.titles),  # for main_title extraction
    )
    .filter(Disc.fingerprint == fingerprint)
    .first()
)
```
[VERIFIED: follows existing eager loading pattern in disc.py]

### Pattern 5: Client-Side Edition Autocomplete
**What:** Store common edition suggestions as a static array in the web component. No server endpoint needed.
**When to use:** D-11 edition name autocomplete.
**Rationale:** The suggestion list is small (6 items), static, and shared in CONTEXT.md. A server endpoint adds latency and complexity for no benefit. Free text is always allowed.
```typescript
const EDITION_SUGGESTIONS = [
  "Extended Edition",
  "Director's Cut",
  "Theatrical",
  "Criterion Collection",
  "Special Edition",
  "Ultimate Edition",
];
```
[ASSUMED — discretion area, choosing simplest approach]

### Anti-Patterns to Avoid
- **Separate API call for siblings:** D-03 specifies one request gets everything. Do NOT require a second fetch for sibling data.
- **Blocking set creation on release existence:** D-09 allows orphan sets. The `release_id` FK on `disc_sets` is NOT NULL in the model, so set creation always needs a release. This is fine -- the `POST /v1/set` endpoint requires `release_id`.
- **Modifying fingerprint algorithm:** Fingerprints are immutable. Set membership is metadata layered on top.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Disc number uniqueness within set | Application-level check only | DB unique constraint `(disc_set_id, disc_number) WHERE disc_set_id IS NOT NULL` | Race conditions between concurrent submits |
| Set search pagination | Custom offset logic | Reuse existing `PAGE_SIZE` pattern from `search_releases()` | Consistency, already tested |
| Debounced search-as-you-type | Custom timer logic | `setTimeout` with cleanup in `useEffect` (standard React pattern) | Well-understood, no library needed for single input |

## Common Pitfalls

### Pitfall 1: N+1 Queries on Sibling Loading
**What goes wrong:** Loading siblings triggers separate queries per sibling disc's titles/tracks.
**Why it happens:** Default lazy loading on `Disc.titles` when iterating `disc_set.discs`.
**How to avoid:** Use `selectinload(DiscSet.discs).joinedload(Disc.titles)` in the initial query. Only load what's needed for `SiblingDiscSummary` (main feature title name and duration).
**Warning signs:** Slow responses on disc lookup, visible in SQL query log.

### Pitfall 2: Unique Constraint on SQLite Tests
**What goes wrong:** PostgreSQL partial unique indexes (`WHERE disc_set_id IS NOT NULL`) have different syntax than SQLite.
**Why it happens:** Test suite uses in-memory SQLite.
**How to avoid:** Use a regular `UniqueConstraint("disc_set_id", "disc_number", name="uq_disc_set_number")` in the model's `__table_args__`. For discs NOT in a set, `disc_set_id` is NULL and SQL unique constraints ignore NULLs by default (both PostgreSQL and SQLite).
**Warning signs:** Tests pass but production fails, or vice versa.

### Pitfall 3: Implicit Set Creation Race Condition
**What goes wrong:** Two users submit disc 1 and disc 2 of the same set simultaneously, each with `total_discs=2` and no `disc_set_id`. Two separate sets get created.
**Why it happens:** No way to detect "same intended set" from two independent submissions without a shared identifier.
**How to avoid:** This is acceptable behavior per D-07/D-09. Users can link discs to existing sets later. The `GET /v1/set` search endpoint helps users find and use existing sets. Document this as expected behavior.
**Warning signs:** Duplicate sets for the same release -- this is a feature management concern, not a bug.

### Pitfall 4: Breaking Existing Clients with Response Shape Change
**What goes wrong:** Adding `disc_set` field breaks clients that do strict schema validation.
**Why it happens:** Field added to existing response.
**How to avoid:** D-14 says additive only. `disc_set: DiscSetNested | None = None` defaults to `None`. Existing clients ignore unknown fields. Both Pydantic and JSON parsers handle this gracefully.
**Warning signs:** Client-side parsing errors after deployment.

### Pitfall 5: Sync Feed Missing disc_set Records
**What goes wrong:** Mirrors don't receive disc set data because sync diff only tracks disc records.
**Why it happens:** The sync diff currently only queries `Disc` records by `seq_num`.
**How to avoid:** Add a `type: "disc_set"` variant to `SyncDiffRecord` or extend the diff query to include `DiscSet` records. SET-05 notes `seq_num` already exists on `disc_sets`. The sync route needs to query both tables.
**Warning signs:** Mirrors missing set data after sync.

## Code Examples

### Schema Definitions (api/app/schemas.py)
```python
# Source: extending existing patterns in schemas.py

class DiscSetCreate(BaseModel):
    release_id: str = Field(min_length=1)
    edition_name: str | None = None
    total_discs: int = Field(ge=1)

class DiscSetResponse(BaseModel):
    request_id: str
    id: str
    release_id: str
    edition_name: str | None = None
    total_discs: int
    created_at: str

class SiblingDiscSummary(BaseModel):
    fingerprint: str
    disc_number: int
    format: str
    main_title: str | None = None
    duration_secs: int | None = None

class DiscSetNested(BaseModel):
    id: str
    edition_name: str | None = None
    total_discs: int
    siblings: list[SiblingDiscSummary] = Field(default_factory=list)

class DiscSetDetailResponse(BaseModel):
    request_id: str
    id: str
    release_id: str
    edition_name: str | None = None
    total_discs: int
    discs: list[SiblingDiscSummary] = Field(default_factory=list)

class DiscSetSearchResponse(BaseModel):
    request_id: str
    results: list[DiscSetDetailResponse] = Field(default_factory=list)
    page: int = 1
    total_pages: int = 0
    total_results: int = 0
```
[VERIFIED: follows naming conventions from existing schemas.py]

### Unique Constraint Migration
```python
# Alembic migration for disc_number uniqueness within a set
def upgrade():
    op.create_unique_constraint(
        "uq_disc_set_disc_number",
        "discs",
        ["disc_set_id", "disc_number"],
    )

def downgrade():
    op.drop_constraint("uq_disc_set_disc_number", "discs")
```
[VERIFIED: SQLAlchemy/Alembic pattern; NULL values excluded from unique checks by SQL standard]

### TypeScript Interfaces (web/lib/api.ts)
```typescript
// Source: extending existing interface patterns in api.ts

export interface SiblingDiscSummary {
  fingerprint: string;
  disc_number: number;
  format: string;
  main_title: string | null;
  duration_secs: number | null;
}

export interface DiscSetNested {
  id: string;
  edition_name: string | null;
  total_discs: number;
  siblings: SiblingDiscSummary[];
}

// Extend existing DiscLookupResponse
export interface DiscLookupResponse {
  // ... existing fields ...
  disc_set: DiscSetNested | null;  // NEW
}
```
[VERIFIED: follows existing TypeScript interface patterns in api.ts]

### CLI Set Search (ovid-client/src/ovid/client.py)
```python
# Extend OVIDClient with set operations

def search_sets(self, query: str, page: int = 1) -> dict | None:
    """GET /v1/set?q={query}&page={page}."""
    url = f"{self.base_url}/v1/set"
    resp = self._session.get(url, params={"q": query, "page": page})
    if resp.status_code == 200:
        return resp.json()
    self._raise_for_status(resp, "search_sets")

def create_set(self, payload: dict) -> dict:
    """POST /v1/set with Bearer token header."""
    headers: dict[str, str] = {}
    if self.token:
        headers["Authorization"] = f"Bearer {self.token}"
    url = f"{self.base_url}/v1/set"
    resp = self._session.post(url, json=payload, headers=headers)
    if resp.status_code == 201:
        return resp.json()
    self._raise_for_status(resp, "create_set")
```
[VERIFIED: follows existing OVIDClient method patterns]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (API), Vitest 4.1.2 (Web) |
| Config file | `api/tests/conftest.py`, `web/vitest.config.ts` |
| Quick run command | `cd api && python -m pytest tests/test_disc_sets.py -x` |
| Full suite command | `cd api && python -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SET-01 | POST /v1/set creates set | unit | `pytest tests/test_disc_sets.py::test_create_set -x` | Wave 0 |
| SET-02 | GET /v1/set/{id} returns set+discs | unit | `pytest tests/test_disc_sets.py::test_get_set_detail -x` | Wave 0 |
| SET-03 | POST /v1/disc validates disc_set_id+disc_number | unit | `pytest tests/test_disc_submit.py::test_submit_with_set -x` | Wave 0 |
| SET-04 | GET /v1/disc/{fp} includes siblings | unit | `pytest tests/test_disc_lookup.py::test_lookup_with_set -x` | Wave 0 |
| SET-05 | disc_sets seq_num column | unit | `pytest tests/test_disc_sets.py::test_set_seq_num -x` | Wave 0 |
| SET-06 | Web disc detail shows siblings | unit | `cd web && npx vitest run src/__tests__/disc-detail.test.tsx` | Wave 0 |
| SET-07 | Web submit form set toggle | unit | `cd web && npx vitest run src/__tests__/submit.test.tsx` | Exists (extend) |
| SET-08 | CLI prompts for set membership | manual-only | Manual -- requires interactive Rich prompts | N/A |

### Wave 0 Gaps
- [ ] `api/tests/test_disc_sets.py` -- covers SET-01, SET-02, SET-05
- [ ] Extend `api/tests/test_disc_submit.py` -- covers SET-03
- [ ] Extend `api/tests/test_disc_lookup.py` -- covers SET-04
- [ ] `web/src/__tests__/disc-detail.test.tsx` -- covers SET-06
- [ ] Extend `web/src/__tests__/submit.test.tsx` -- covers SET-07
- [ ] Extend `api/tests/conftest.py` -- add `seed_test_disc_set()` helper

### Sampling Rate
- **Per task commit:** `cd api && python -m pytest tests/test_disc_sets.py -x`
- **Per wave merge:** `cd api && python -m pytest tests/ -x && cd web && npx vitest run`
- **Phase gate:** Full suite green before `/gsd-verify-work`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing JWT auth via `get_current_user` Depends -- reuse for write endpoints |
| V3 Session Management | no | No new session state introduced |
| V4 Access Control | yes | Write endpoints require authenticated user; read endpoints public (per API contract) |
| V5 Input Validation | yes | Pydantic schema validation on all request bodies; `Field(ge=1)` for disc_number/total_discs |
| V6 Cryptography | no | No new crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Disc number squatting (claiming all slots in a set) | Denial of Service | Rate limiting via `@limiter.limit(_dynamic_limit)` on POST /v1/set and disc submit |
| UUID parameter injection in disc_set_id | Tampering | Pydantic UUID validation; FK constraint prevents linking to non-existent sets |
| Search query injection via set search | Tampering | SQLAlchemy ORM `.ilike()` with parameterized queries (same as existing search) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Client-side static list is sufficient for edition autocomplete (vs server endpoint) | Architecture Patterns, Pattern 5 | Minor UX difference; easy to add server endpoint later |
| A2 | Set search pagination uses same PAGE_SIZE (20) as release search | Architecture Patterns | Trivial to change |
| A3 | Sync feed extension for disc_sets is in scope for this phase | Pitfalls, Pitfall 5 | If deferred to Phase 4, mirrors will lack set data temporarily |

## Open Questions

1. **Sync feed scope for disc_sets**
   - What we know: SET-05 says `disc_sets` gets `seq_num` (already done). The sync diff route currently only queries `Disc` records.
   - What's unclear: Should this phase extend the sync diff to include `disc_set` records, or defer to Phase 4 (Sync and Mirror Hardening)?
   - Recommendation: Add minimal sync support (include `disc_set_id` in disc sync records) but defer full `disc_set` record syncing to Phase 4. This keeps Phase 2 focused while ensuring disc-to-set links are visible in the sync feed.

2. **Set search query scope**
   - What we know: D-04 says search by release name/edition.
   - What's unclear: Should set search join through to the release table to search by release title, or only search `edition_name` directly on `disc_sets`?
   - Recommendation: Join to `releases` table and search both `Release.title` and `DiscSet.edition_name` with `ilike`. This matches the submit form UX where users think in terms of movie titles.

## Sources

### Primary (HIGH confidence)
- `api/app/models.py` -- DiscSet model definition, Disc.disc_set_id FK, relationships
- `api/app/schemas.py` -- existing schema naming conventions and patterns
- `api/app/routes/disc.py` -- route patterns, helper functions, eager loading
- `api/app/routes/sync.py` -- sync feed patterns
- `api/app/sync.py` -- next_seq() usage pattern
- `api/tests/conftest.py` -- test fixture patterns, SQLite compatibility
- `web/lib/api.ts` -- TypeScript interface patterns, apiFetch wrapper
- `web/components/SubmitForm.tsx` -- existing form patterns
- `web/app/disc/[fingerprint]/page.tsx` -- existing disc detail layout
- `ovid-client/src/ovid/cli.py` -- CLI wizard patterns, Rich prompt usage
- `ovid-client/src/ovid/client.py` -- OVIDClient method patterns

### Secondary (MEDIUM confidence)
- `.planning/phases/02-multi-disc-set-support/02-CONTEXT.md` -- all D-01 through D-14 decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all patterns verified in codebase
- Architecture: HIGH -- extending well-established patterns in existing code
- Pitfalls: HIGH -- identified from direct code inspection of query patterns and test infrastructure

**Research date:** 2026-04-04
**Valid until:** 2026-05-04 (stable -- no external dependency changes expected)
