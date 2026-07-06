---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 02
subsystem: database
tags: [sqlalchemy, alembic, migration, sqlite, uuid, dvdread1]

# Dependency graph
requires:
  - phase: 05-01
    provides: FingerprintRegistry table + register_fingerprint() (WR-02 arbitration; untouched by promotion since disc_id doesn't change)
provides:
  - "promote_one_disc(connection, dvd1_fingerprint) -> bool — idempotent per-disc dvd1-* -> dvdread1-* promotion transform"
  - "promote_all_dvdread1_discs(connection) -> int — bulk driver, per-disc commit-as-you-go, resumable"
affects: [05-06 (Alembic promotion migration file — thin wrapper around promote_all_dvdread1_discs)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alembic-independent migration logic: plain functions taking a SQLAlchemy Connection, testable directly against the in-memory SQLite pytest harness with zero alembic import/invocation (Pitfall 5)"
    - "Raw text() SQL binds are untyped (NullType) and bypass the ORM UUID type decorator's bind/result processors — UUIDs must be passed as .hex strings to match SQLite's non-native hex-no-dash storage format"
    - "SQLAlchemy 2.0 commit-as-you-go: connection.commit() ends the current transaction segment; the next execute() auto-begins a new one — used for per-disc resumable commits in a bulk loop"

key-files:
  created:
    - api/app/migrations_support.py
    - api/tests/test_promote_dvdread1_migration.py
  modified: []

key-decisions:
  - "promote_one_disc/promote_all_dvdread1_discs import only sqlalchemy (text, Connection) — zero alembic imports — so the module and its tests import cleanly under pytest per Pitfall 5"
  - "UUIDs crossing the raw text() SQL boundary are represented as .hex (32-char, no dashes) rather than str(uuid) (36-char, dashed), matching the physical storage format the ORM's UUID type decorator uses under SQLite — a dashed str() would silently match zero rows instead of erroring"
  - "promote_all_dvdread1_discs does not touch fingerprint_registry (05-01's WR-02 table): the registry already has rows for both the dvd1-* and dvdread1-* strings pointing at the same disc_id, and promotion only moves which one is primary vs. alias — disc_id never changes, so no registry update is needed"

patterns-established:
  - "Task-level TDD for migration-support modules: write behavior tests importing the not-yet-existing function first (RED, confirmed via ImportError), then implement (GREEN), rather than writing the migration inline inside an Alembic upgrade() function"

requirements-completed: [IDENT-04]

coverage:
  - id: D1
    description: "promote_one_disc() promotes a disc with a dvdread1-* alias (deletes alias row, sets discs.fingerprint, inserts old dvd1-* as new alias), and is a safe no-op (idempotent, proven via double-invocation) for already-promoted discs or discs with no dvdread1-* alias"
    requirement: IDENT-04
    verification:
      - kind: unit
        ref: "api/tests/test_promote_dvdread1_migration.py::TestPromoteOneDisc (4 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "promote_all_dvdread1_discs() bulk-promotes only eligible discs, is fully idempotent on re-run, and durably commits each disc independently (per-disc commit-as-you-go, visible from a completely fresh Session)"
    requirement: IDENT-04
    verification:
      - kind: unit
        ref: "api/tests/test_promote_dvdread1_migration.py::TestPromoteAllDvdread1Discs (3 tests)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 2: D-01 Promotion Transform Summary

**Alembic-independent `promote_one_disc()`/`promote_all_dvdread1_discs()` in a new `api/app/migrations_support.py`, proving the dvd1-* -> dvdread1-* backfill idempotent and resumable via 7 unit tests against the in-memory SQLite harness — zero Alembic invocation anywhere.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-06T21:11:31Z
- **Completed:** 2026-07-06T21:21:40Z
- **Tasks:** 2 completed (TDD RED/GREEN cycle each)
- **Files modified:** 2 (1 new module, 1 new test file)

## Accomplishments
- `promote_one_disc(connection, dvd1_fingerprint) -> bool`: deletes the disc's `dvdread1-*` alias row, sets `discs.fingerprint` to that value, and inserts the old `dvd1-*` value as a new alias row with a fresh `created_at` (preserving D-06 primary-first-by-`(created_at, id)` ordering) — idempotent via a `WHERE discs.fingerprint = <old dvd1 value>` guard, proven safe on double-invocation.
- `promote_all_dvdread1_discs(connection) -> int`: enumerates `dvd1-*` discs, calls `promote_one_disc` per candidate, commits after every candidate (SQLAlchemy 2.0 commit-as-you-go), and returns the promoted count — proven fully idempotent on re-run and durably committed per-disc (visible from a completely fresh `Session`, not just the in-flight transaction).
- Both functions import only `sqlalchemy` — zero Alembic imports — confirmed importable and directly pytest-testable per Pitfall 5; Plan 05-06's Alembic migration file can call `promote_all_dvdread1_discs()` as a thin wrapper with no additional logic.

## Task Commits

Each task followed the TDD RED -> GREEN cycle:

1. **Task 1: promote_one_disc() — RED** - `6855c69` (test) - 4 failing tests + module scaffold
2. **Task 1: promote_one_disc() — GREEN** - `159815b` (feat) - implementation, all 4 green
3. **Task 2: promote_all_dvdread1_discs() — RED** - `7c4149a` (test) - 3 failing tests
4. **Task 2: promote_all_dvdread1_discs() — GREEN** - `2174f31` (feat) - implementation, all 7 green

_No refactor commit needed — implementation matched the RESEARCH.md sketch cleanly on first GREEN pass (aside from the UUID-binding fix, folded into the GREEN commit as part of making the tests pass)._

## Files Created/Modified
- `api/app/migrations_support.py` - New module: `promote_one_disc()`, `promote_all_dvdread1_discs()`, both Alembic-independent
- `api/tests/test_promote_dvdread1_migration.py` - New test file: 7 tests (4 for `promote_one_disc`, 3 for `promote_all_dvdread1_discs`), no Alembic invocation

## Decisions Made
- Raw `text()` SQL binds are untyped (`NullType`) and bypass the ORM's `postgresql.UUID(as_uuid=True)` type decorator entirely — a bare `uuid.UUID` object fails to bind against the sqlite3 DBAPI with `ProgrammingError: type 'UUID' is not supported`. Fixed by using `.hex` (32-char, no dashes) everywhere a UUID crosses the raw-SQL boundary, matching the exact string format SQLite's non-native UUID storage physically holds — a dashed `str(uuid)` would not error, it would silently match zero rows (discovered live via a failing `AttributeError: 'NoneType' object has no attribute 'fingerprint'` on the first GREEN attempt, then root-caused by inspecting the raw stored format directly).
- `promote_all_dvdread1_discs()` intentionally does not touch `fingerprint_registry` (05-01's WR-02 table): that table only records which `disc_id` owns a given fingerprint string, and both the `dvd1-*` and `dvdread1-*` strings for a promoted disc already have registry rows pointing at the same `disc_id` before and after promotion — only which column (`discs.fingerprint` vs. `disc_identity_aliases`) holds which string changes.

## Deviations from Plan

None — plan executed exactly as written. The UUID `.hex`-binding fix was corrective work discovered while making the RED tests pass on the very first implementation attempt (Rule 1 - Bug: raw SQL bind failure), not a deviation from the plan's design; it does not change either function's public signature or the SQL/idempotency logic specified in RESEARCH.md's Example 1 sketch.

## Issues Encountered
- First GREEN attempt for Task 1 failed with `sqlite3.ProgrammingError: type 'UUID' is not supported` when binding a raw `uuid.uuid4()` object into the `INSERT` statement, then (after switching to `str()`) failed again with a silent `NoneType` assertion failure because `str(uuid)` (dashed) didn't match the hex-no-dash format the column physically stores under SQLite. Root-caused by directly querying the stored representation (`db.execute(text("SELECT id, fingerprint FROM discs")).first()` against a throwaway disc), which showed the stored value as a 32-char hex string — confirmed `.hex` as the correct format for both the module and its test fixtures, resolved on the next run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `promote_one_disc()` and `promote_all_dvdread1_discs()` are ready to be wrapped by Plan 05-06's Alembic migration `upgrade()` function with no additional logic — the migration file only needs to call `op.get_bind()` and pass the resulting connection through.
- Full `api` test suite green (342 tests) after this plan's additions.

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*
