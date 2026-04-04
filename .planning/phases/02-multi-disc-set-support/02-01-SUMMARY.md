---
phase: 02-multi-disc-set-support
plan: 01
subsystem: api
tags: [disc-sets, crud, api, phase-2]
dependency_graph:
  requires: []
  provides: [set-crud-api, disc-set-linking, sibling-nesting]
  affects: [api/app/routes/disc.py, api/app/schemas.py, api/app/models.py, api/app/sync.py]
tech_stack:
  added: []
  patterns: [eager-loading-siblings, implicit-set-creation, unique-constraint-enforcement]
key_files:
  created:
    - api/app/routes/set.py
    - api/alembic/versions/900000000004_add_disc_set_number_unique.py
    - api/tests/test_disc_sets.py
  modified:
    - api/app/schemas.py
    - api/app/models.py
    - api/app/routes/disc.py
    - api/app/sync.py
    - api/main.py
    - api/tests/conftest.py
    - api/tests/test_disc_submit.py
    - api/tests/test_disc_lookup.py
decisions:
  - Used inline imports in test files to work around post-write formatter stripping unused top-level imports
  - Chained migration 900000000004 from 900000000002 (not 900000000003 as plan stated, since 900000000003 does not exist)
metrics:
  duration: 12m
  completed: "2026-04-04T18:36:30Z"
  tasks: 3/3
  tests_added: 18
  tests_total: 246
  files_created: 3
  files_modified: 8
---

# Phase 02 Plan 01: Set CRUD API and Disc-Set Integration Summary

API layer for multi-disc set support: set CRUD routes (POST/GET/search), disc submission with implicit set creation and explicit set linking, disc lookup with sibling disc nesting, unique constraint migration, and sync feed extension.

## One-liner

Disc set CRUD API with implicit/explicit set linking, sibling nesting in lookup, and UniqueConstraint(disc_set_id, disc_number) enforcement.

## Task Results

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Set schemas, model constraint, migration, conftest helper | eefba86 | Done |
| 2 | Set CRUD routes, router registration, and tests (TDD) | e11ea26, c61d526 | Done |
| 3 | Extend disc submit/lookup for set integration (TDD) | cf2a63a, c04831c | Done |

## What Was Built

### Task 1: Schemas, Model, Migration, Helper
- Added 6 Pydantic schemas: `SiblingDiscSummary`, `DiscSetNested`, `DiscSetCreate`, `DiscSetResponse`, `DiscSetDetailResponse`, `DiscSetSearchResponse`
- Added `disc_set` field to `DiscLookupResponse` (null when not in a set)
- Added `disc_set_id` field to `DiscSubmitRequest` and `SyncDiffRecord`
- Added `UniqueConstraint("disc_set_id", "disc_number")` to Disc model
- Created Alembic migration `900000000004` for the unique constraint
- Added `seed_test_disc_set` helper to conftest.py

### Task 2: Set CRUD Routes (TDD)
- `POST /v1/set` -- creates disc set with auth, validates release_id, allocates seq_num
- `GET /v1/set/{set_id}` -- returns set with eager-loaded disc sibling summaries
- `GET /v1/set?q=` -- searches by release title (ilike) or edition name (ilike), paginated
- Registered `set_router` in `main.py`
- 10 tests covering auth, validation, search, and happy paths

### Task 3: Disc Submit/Lookup Set Integration (TDD)
- Implicit set creation: `total_discs > 1` with no `disc_set_id` auto-creates a `DiscSet`
- Explicit linking: `disc_set_id` in request links disc to existing set
- Validation: 422 when disc_number exceeds total_discs, 409 on duplicate disc_number, 404 on missing set
- Lookup: `disc_set` nested response includes sibling summaries (fingerprint, disc_number, format, main_title, duration, track_count)
- Backward compatible: `disc_set` is null for discs not in a set
- Sync: `build_sync_disc` includes `disc_set_id` field
- 8 new tests across submit and lookup

## Decisions Made

1. **Migration chaining**: Plan specified `down_revision: 900000000003` but that migration does not exist. Chained from `900000000002` instead.
2. **Inline imports in tests**: The post-write formatter strips unused top-level imports. Used function-level imports for `seed_test_disc_set`, `DiscSet`, `uuid` in test files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migration down_revision corrected**
- **Found during:** Task 1
- **Issue:** Plan referenced non-existent migration 900000000003 as down_revision
- **Fix:** Used 900000000002 (actual latest migration) as down_revision
- **Files modified:** api/alembic/versions/900000000004_add_disc_set_number_unique.py

**2. [Rule 3 - Blocking] Post-write formatter stripping imports**
- **Found during:** Tasks 2 and 3
- **Issue:** A post-write hook formatter strips unused imports from Python files, removing needed imports like DiscSet, uuid, seed_test_disc_set
- **Fix:** Used inline imports within functions/methods that need them
- **Files modified:** api/tests/conftest.py, api/tests/test_disc_submit.py, api/tests/test_disc_lookup.py

## Verification

- Full API test suite: 246 passed, 0 failed
- All 10 set CRUD tests pass
- All 8 disc submit/lookup set integration tests pass
- Backward compatibility verified: disc_set is null for existing disc lookups

## Self-Check: PASSED

- All 3 created files exist on disk
- All 5 task commits verified in git log
- 246/246 tests passing
