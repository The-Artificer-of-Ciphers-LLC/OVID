---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 04
subsystem: api
tags: [fastapi, pydantic, sqlalchemy, nextjs, typescript]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene (plan 03)
    provides: verification wiring in routes/disc.py and race-safe disc-row inserts, which this plan's eager-load additions build on top of
provides:
  - "GET /v1/disc/{fp} exposes every known Disc Identity string via fingerprint_aliases: list[{fingerprint, method, is_primary}], primary-first then insertion order"
  - "Additive, backward-compatible read-side contract that Phase 7's disc-detail view (WEBUI-02) and Phase 5's promotion work can build on without a second breaking change"
affects: [phase-7-web-ui, phase-5-libdvdread-promotion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Derived (not stored) response fields: method is computed from the fingerprint prefix at serialization time, avoiding a schema/migration change for a purely presentational property"
    - "Deterministic relationship ordering via order_by=(created_at, id) tuple to break same-timestamp ties, applied at the ORM relationship rather than the serializer"

key-files:
  created: []
  modified:
    - api/app/schemas.py
    - api/app/models.py
    - api/app/routes/disc.py
    - web/lib/api.ts
    - api/tests/test_disc_lookup.py

key-decisions:
  - "method is derived from the fingerprint prefix (fp.split('-', 1)[0]) via a new _method_of() helper in routes/disc.py — no method column, no Alembic migration (D-04)"
  - "Deterministic alias ordering via order_by='DiscIdentityAlias.created_at, DiscIdentityAlias.id' on the Disc.identity_aliases relationship, not a second sort in the serializer (D-06) — id is a secondary tiebreaker only, created_at is the primary insertion-order signal"
  - "selectinload(Disc.identity_aliases) added at all three _disc_to_response call sites (lookup, lookup_disc_by_upc, list_disputed_discs) to avoid N+1 under the p95<=500ms budget"
  - "web/lib/api.ts fingerprint_aliases is an optional field (fingerprint_aliases?) so existing, unmodified callers keep compiling (D-07)"

requirements-completed: [IDENT-01]

coverage:
  - id: D1
    description: "GET /v1/disc/{fp} returns fingerprint_aliases as {fingerprint, method, is_primary} objects, primary-first, then remaining aliases in insertion order (not string-sorted)"
    requirement: "IDENT-01"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_lookup.py::TestDiscLookup::test_lookup_returns_fingerprint_aliases"
        status: pass
    human_judgment: false
  - id: D2
    description: "Top-level fingerprint field on DiscLookupResponse is unchanged; existing lookup/alias consumers keep passing unmodified"
    requirement: "IDENT-01"
    verification:
      - kind: integration
        ref: "api/tests/test_disc_identity_aliases.py (all 7 tests)"
        status: pass
      - kind: unit
        ref: "api/tests/ full suite (255 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "web/lib/api.ts DiscLookupResponse gains an optional fingerprint_aliases field; typecheck and existing web tests stay green"
    requirement: "IDENT-01"
    verification:
      - kind: other
        ref: "cd web && npx tsc --noEmit"
        status: pass
      - kind: unit
        ref: "cd web && npm test (3 files, 32 tests)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 04: Fingerprint Aliases Lookup Exposure Summary

**GET /v1/disc/{fp} now returns fingerprint_aliases — every known Disc Identity string for a pressing as {fingerprint, method, is_primary} objects, primary-first then insertion order, additive across API and web.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-05T19:37:00Z
- **Completed:** 2026-07-05T19:41:51Z
- **Tasks:** 3 completed (RED, GREEN, web type addition)
- **Files modified:** 5

## Accomplishments
- Added `FingerprintAliasResponse` Pydantic model and an additive `fingerprint_aliases` field on `DiscLookupResponse` in `api/app/schemas.py`
- Added deterministic `order_by=(created_at, id)` to `Disc.identity_aliases` in `api/app/models.py`, so exposed alias order is stable and reproducible (D-06) — never sorted by fingerprint string
- Added `_method_of()` helper and serializer wiring in `api/app/routes/disc.py`, deriving `method` from the fingerprint prefix with no new column and no Alembic migration
- Added `selectinload(Disc.identity_aliases)` at all three `_disc_to_response` call sites (`lookup_disc`, `lookup_disc_by_upc`, `list_disputed_discs`) to avoid N+1 query cost
- Added the optional `fingerprint_aliases?` field to the `DiscLookupResponse` TypeScript interface in `web/lib/api.ts` — strictly additive, existing callers unaffected

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Extend test_disc_lookup.py for the fingerprint_aliases shape** - `054628c` (test)
2. **Task 2 (GREEN): Add the schema model, deterministic ordering, serializer + eager-load** - `935b985` (feat)
3. **Task 3: Add the optional fingerprint_aliases field to the web DiscLookupResponse interface** - `b4116ba` (feat)

**Plan metadata:** (this commit) - docs

_TDD gate sequence confirmed: `test(01-04)` commit precedes `feat(01-04)` commit in git log._

## Files Created/Modified
- `api/app/schemas.py` - New `FingerprintAliasResponse` model; additive `fingerprint_aliases` field on `DiscLookupResponse`
- `api/app/models.py` - Deterministic `order_by` on the `Disc.identity_aliases` relationship
- `api/app/routes/disc.py` - New `_method_of()` helper; `_disc_to_response` builds `fingerprint_aliases`; `selectinload(Disc.identity_aliases)` at 3 call sites
- `web/lib/api.ts` - New `FingerprintAlias` interface; optional `fingerprint_aliases?` field on `DiscLookupResponse`
- `api/tests/test_disc_lookup.py` - New `test_lookup_returns_fingerprint_aliases` locking primary-first ordering, `is_primary` flags, insertion order, and derived `method`

## Decisions Made
- `method` derivation over a stored column: keeps this plan migration-free and matches RESEARCH Pattern 4 — the field is presentational, not a new identity concept.
- `order_by` on the relationship (not a second sort in the serializer): keeps the ordering contract in one place (the ORM), matching the existing `Disc.titles` analog.
- `(created_at, id)` composite ordering: `created_at` alone can tie under SQLite's default datetime resolution in fast test runs; `id` is a stable (if not insertion-meaningful) tiebreaker, per PATTERNS.md guidance — verified in the new test by giving each seeded alias an explicit, distinct `created_at`.
- Web field made optional (`fingerprint_aliases?`) rather than required, so TypeScript structural typing lets existing, unmodified response consumers keep compiling without any code change (D-07).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`web/node_modules/` was not present in the working tree at the start of this plan (dependencies never installed). Per the plan's technical note, ran `npm ci` before `npx tsc --noEmit` / `npm test` — both then passed cleanly. `node_modules/` remains gitignored and was not committed.

## Verification Results

- `cd api && ./.venv/bin/python -m pytest tests/test_disc_lookup.py tests/test_disc_identity_aliases.py -x` — 16 passed
- `cd api && ./.venv/bin/python -m pytest tests/ -q` — **255 passed** (full API suite, one new test added vs. prior plan's 254)
- `cd web && npx tsc --noEmit` — no errors
- `cd web && npm test` — 3 files, 32 tests passed
- `git status --porcelain api/alembic/versions/` — empty (no migration added, confirming D-04)

### Pre-existing warnings (confirmed out of scope, not fixed here)

Fifth consecutive plan in this phase to independently reconfirm the same
API-side warning trio (`InsecureKeyLengthWarning` in `test_auth.py`/
`test_auth_apple.py`, `StarletteDeprecationWarning` from `httpx`+
`TestClient`, `DeprecationWarning` from `slowapi`'s use of
`asyncio.iscoroutinefunction`) as pre-existing and untouched by this plan's
files. Additionally observed one new pre-existing warning on the web side
(`DEP0205: module.register() is deprecated`, emitted by Vitest's own loader
registration against the installed Node.js runtime) — unrelated to this
plan's type-only `web/lib/api.ts` diff. Full detail logged in
`.planning/phases/01-alias-layer-hardening-repo-hygiene/deferred-items.md`
under "Plan 01-04".

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

This is the final plan of Phase 01 (alias-layer-hardening-repo-hygiene). All
six plans (01-01 through 01-06) are now complete:

- Verification state machine (01-01), race-hardened alias writes (01-02),
  verification wiring + disc-row race safety (01-03), this plan's read-side
  alias exposure (01-04), the dvd1-* identity regression guardrail (01-05),
  and repo hygiene cleanup (01-06).

`fingerprint_aliases` is now available for Phase 7's disc-detail UI
(WEBUI-02) to render, and the `{method, is_primary}` object shape is
designed to survive Phase 5's libdvdread `dvdread1-*` promotion without a
second breaking change to the lookup contract. No blockers identified for
downstream phases.

## Self-Check: PASSED

All created/modified files confirmed present on disk; all three task commit
hashes (`054628c`, `935b985`, `b4116ba`) confirmed present in `git log`.
