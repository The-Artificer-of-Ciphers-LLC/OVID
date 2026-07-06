---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 01
subsystem: database
tags: [sqlalchemy, postgres, sqlite, fingerprint, concurrency, race-condition]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene
    provides: "The insert-first/IntegrityError-catch/re-resolve SAVEPOINT convergence idiom in attach_lookup_aliases (IDENT-02, D-01/D-03) — this plan reuses that exact pattern, not a new one."
provides:
  - "FingerprintRegistry ORM model — a global write-only cross-table fingerprint registry"
  - "register_fingerprint(db, fingerprint, disc_id) helper wired into attach_lookup_aliases's SAVEPOINT"
  - "WR-02 cross-table race regression test proving a new-disc-claims-F vs. alias-attach-F-to-a-different-disc race converges atomically"
affects: [05-05, 05-06]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Cross-table UNIQUE-constraint arbitration reusing an existing insert-first/IntegrityError/re-resolve SAVEPOINT idiom rather than introducing a second (pessimistic) locking strategy"]

key-files:
  created:
    - api/tests/test_fingerprint_registry.py
  modified:
    - api/app/models.py
    - api/app/disc_identity.py

key-decisions:
  - "FingerprintRegistry copies DiscIdentityAlias's exact column shape (UUID PK, String(50) unique fingerprint, disc_id FK, created_at) with only a disc_id index — no separate fingerprint index, since unique=True already gets an implicit unique index and the table is write-only (D-02)"
  - "register_fingerprint() is a bare db.add() with no flush/commit of its own — caller (attach_lookup_aliases) is contractually required to invoke it inside its own db.begin_nested() savepoint so a registry UNIQUE violation surfaces through the same existing except IntegrityError: re-resolve/converge path"
  - "No back_populates relationship added from Disc to FingerprintRegistry — nothing in this phase queries the registry from the Disc side; it is write-only per D-02/T-05-02"

patterns-established:
  - "Cross-table race arbitration via a shared registry table with a single global UNIQUE(fingerprint) column, wired into the same SAVEPOINT as the domain-table insert it accompanies — reused for any future identity-adjacent table that could otherwise race against discs/disc_identity_aliases"

requirements-completed: [IDENT-04]

coverage:
  - id: D1
    description: "FingerprintRegistry model with global UNIQUE(fingerprint) constraint, disc_id FK, and disc_id index"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_fingerprint_registry.py::TestRegisterFingerprintArbitration::test_fresh_fingerprint_registers_successfully"
        status: pass
    human_judgment: false
  - id: D2
    description: "Cross-table WR-02 race (new-disc-claims-F vs. alias-attach-F-to-different-disc) is arbitrated atomically — exactly one side wins, the other raises IntegrityError/DiscIdentityConflict, never a silent split"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_fingerprint_registry.py::TestRegisterFingerprintArbitration::test_cross_table_race_is_caught_by_registry"
        status: pass
      - kind: unit
        ref: "api/tests/test_fingerprint_registry.py::TestAttachLookupAliasesRegistryIntegration::test_cross_disc_alias_collision_still_raises_conflict_and_registry_unchanged"
        status: pass
    human_judgment: false
  - id: D3
    description: "register_fingerprint() wired into attach_lookup_aliases's existing SAVEPOINT — every new Lookup Alias fingerprint is also registered in fingerprint_registry inside the same flush"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_fingerprint_registry.py::TestAttachLookupAliasesRegistryIntegration::test_new_alias_is_registered_exactly_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "Pre-existing IDENT-02 same-table race regressions (4 test classes in test_disc_identity_race.py) remain green after the registry wiring"
    requirement: "IDENT-04"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_race.py (all 4 classes)"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 1: FingerprintRegistry + register_fingerprint() Summary

**New `fingerprint_registry` table with a global UNIQUE(fingerprint) constraint, wired into `attach_lookup_aliases`'s existing SAVEPOINT, closing the WR-02 cross-table fingerprint race carried forward from the Phase 1 code review.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-06T21:01:30Z
- **Completed:** 2026-07-06T21:05:43Z
- **Tasks:** 2 completed
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments
- Added `FingerprintRegistry` ORM model (`api/app/models.py`) with a global `UNIQUE(fingerprint)` column, `disc_id` FK, and a `disc_id` index — copies `DiscIdentityAlias`'s exact shape.
- Added `register_fingerprint(db, fingerprint, disc_id)` helper (`api/app/disc_identity.py`), documented as requiring the caller to invoke it inside the same `db.begin_nested()` savepoint as the accompanying `Disc`/`DiscIdentityAlias` insert.
- Wired `register_fingerprint()` into `attach_lookup_aliases()`'s existing SAVEPOINT (single insertion point, same flush, same `except IntegrityError:` re-resolve/converge path) — closing the WR-02 cross-table race: a "new disc claims F" vs. "attach F as an alias of a different disc" collision now atomically arbitrates to exactly one winner.
- Added `api/tests/test_fingerprint_registry.py` (4 tests): direct `register_fingerprint()` arbitration (fresh registration + cross-disc collision), and the `attach_lookup_aliases()` integration proof (new alias registered exactly once + cross-disc alias collision still raises `DiscIdentityConflict` with the registry unchanged).
- Verified the 4 pre-existing `test_disc_identity_race.py` classes (IDENT-02 same-table races) remain green — the registry wiring does not change `attach_lookup_aliases`'s existing behavior. Full `api/` test suite (335 tests) passes with zero regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: FingerprintRegistry model + register_fingerprint() helper (primitives, no wiring yet)** - `a87fc94` (feat)
2. **Task 2: Wire register_fingerprint() into attach_lookup_aliases's SAVEPOINT + WR-02 regression test** - `babfe1b` (test, RED) → `1a095e5` (feat, GREEN)

_TDD gate sequence confirmed: `babfe1b` (test) precedes `1a095e5` (feat) in git log — RED then GREEN. No REFACTOR commit was needed._

## Files Created/Modified
- `api/app/models.py` - Added `FingerprintRegistry` class directly below `DiscIdentityAlias`
- `api/app/disc_identity.py` - Added `import uuid`, added `FingerprintRegistry` to the `app.models` import, added `register_fingerprint()` helper after `attach_lookup_aliases`, wired one `register_fingerprint(db, alias, disc.id)` call inside the existing SAVEPOINT
- `api/tests/test_fingerprint_registry.py` (new) - WR-02 cross-table race regression tests

## Decisions Made
- `FingerprintRegistry` gets only a `disc_id` index in `__table_args__`, deliberately omitting a separate fingerprint index — `unique=True` already provides an implicit unique index and the table is write-only, so no fingerprint-keyed read path ever needs one (per plan spec and D-02).
- No `back_populates` relationship from `Disc` to `FingerprintRegistry` — nothing in this phase (or planned for Wave 2) queries the registry from the `Disc` side.
- `register_fingerprint()` performs no flush/commit of its own — it is a bare `db.add()`, relying entirely on the caller's savepoint/flush to surface any UNIQUE violation. This keeps the arbitration semantics identical to the existing `DiscIdentityAlias` insert it accompanies.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. `pytest` is not on `PATH` directly in this environment (project uses a `.venv` at `api/.venv`) — activated the venv for all verification runs; no code or plan changes resulted from this environment note.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `FingerprintRegistry` and `register_fingerprint()` are now available as the concurrency foundation for Wave 2 plans (05-05, 05-06), which wire `register_fingerprint()` into the new-disc insert paths in `api/app/routes/disc.py` (per 05-PATTERNS.md's `_select_primary` / `register_disc` / `submit_disc` savepoint wiring notes).
- No blockers. The registry is intentionally write-only in this plan — no migration was added (SQLite in-memory test harness creates the table via `Base.metadata.create_all`); a real Alembic migration to create `fingerprint_registry` in Postgres and backfill it from existing `discs`/`disc_identity_aliases` rows (D-02) is expected to land in a subsequent Wave 1/2 plan per 05-PATTERNS.md's migration-file plan (`<rev-A>_add_fingerprint_registry.py`).

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*

## Self-Check: PASSED

All created/modified files confirmed present; all 3 task commit hashes (`a87fc94`, `babfe1b`, `1a095e5`) confirmed in git log.
