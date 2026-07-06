---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 06
subsystem: database
tags: [alembic, migration, sqlalchemy, sqlite, uuid, fingerprint-registry, dvdread1]

# Dependency graph
requires:
  - phase: 05-01
    provides: "FingerprintRegistry ORM model (WR-02 arbitration table) — this plan's DDL matches it exactly"
  - phase: 05-02
    provides: "promote_one_disc()/promote_all_dvdread1_discs() (D-01 promotion transform) — this plan's rev 900000000006 is a thin wrapper around it"
provides:
  - "backfill_fingerprint_registry(connection) -> (int, int) — one-time, dedupe-aware D-02 registry backfill from discs + disc_identity_aliases"
  - "api/alembic/versions/900000000005_add_fingerprint_registry.py — creates + backfills fingerprint_registry, chained after 900000000004"
  - "api/alembic/versions/900000000006_promote_dvdread1_primary.py — wraps promote_all_dvdread1_discs(), chained after 900000000005, single head"
affects: [05-07 (cutover wrapper/runbook — depends on both migrations existing and chaining cleanly to a single head)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Alembic revision-chain sequencing: rev 900000000005 (registry create+backfill) strictly before rev 900000000006 (promotion), matching the phase's locked D-02-before-D-01-runtime sequencing"
    - "Alembic-independent migration logic (Pitfall 5): both migration files call a plain, Connection-taking function from api/app/migrations_support.py, never containing transform logic inline — importable and unit-testable with zero Alembic invocation"
    - "sqlite3.register_adapter(datetime, ...) at module import time to unify raw-text()-SQL datetime storage format with SQLAlchemy's own ORM DateTime bind_processor format — no effect on PostgreSQL/psycopg2"

key-files:
  created:
    - api/app/migrations_support.py (backfill_fingerprint_registry() added; existing promote_one_disc/promote_all_dvdread1_discs untouched in logic)
    - api/tests/test_fingerprint_registry_migration.py
    - api/alembic/versions/900000000005_add_fingerprint_registry.py
    - api/alembic/versions/900000000006_promote_dvdread1_primary.py
  modified:
    - api/app/migrations_support.py (sqlite3 datetime-adapter registration; see Deviations)

key-decisions:
  - "backfill_fingerprint_registry() deduplicates by fingerprint value across discs and disc_identity_aliases (discs win ties) before insert — a fingerprint could theoretically already exist in both source tables (the exact pre-existing cross-table gap WR-02 closes going forward), which would otherwise violate the registry's global UNIQUE and crash the migration"
  - "Registered a sqlite3 datetime adapter (matching SQLAlchemy's own DATETIME bind_processor format) in migrations_support.py rather than converting raw datetime binds to formatted strings inline — keeps promote_one_disc's existing bind values (actual datetime objects) correct and portable for PostgreSQL while eliminating a genuine tz-aware/tz-naive read-back inconsistency under SQLite (see Deviations)"
  - "rev 900000000006's downgrade() is an explicit documented no-op (single pass statement) per D-03 immutability — never NotImplementedError"

requirements-completed: [IDENT-04]

coverage:
  - id: D1
    description: "backfill_fingerprint_registry() backfills fingerprint_registry from BOTH discs.fingerprint and disc_identity_aliases.fingerprint in one pass, returning (count_from_discs, count_from_aliases), dialect-portable via Python-generated uuid.uuid4() ids"
    requirement: IDENT-04
    verification:
      - kind: unit
        ref: "api/tests/test_fingerprint_registry_migration.py::TestBackfillFingerprintRegistry (2 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Revision 900000000005 creates fingerprint_registry matching the ORM model exactly and backfills it inside the same migration transaction; revision 900000000006 chains strictly after it and wraps promote_all_dvdread1_discs() with a documented no-op downgrade; single linear head 900000000006 confirmed via alembic heads"
    requirement: IDENT-04
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_regression.py, test_promote_dvdread1_migration.py, test_fingerprint_registry.py, test_fingerprint_registry_migration.py (14 tests, all pass)"
        status: pass
      - kind: manual
        ref: "alembic upgrade head against a scratch SQLite DB — full chain 7ffb31fc807f -> 900000000006 runs cleanly, fingerprint_registry table created, single head confirmed"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 6: Fingerprint Registry + dvdread1 Promotion Migrations Summary

**Two chained Alembic migrations (900000000005 create+backfill fingerprint_registry, 900000000006 promote dvd1-* to dvdread1-* primary) landing ADR 0001 Phase 3, plus a dedupe-aware backfill helper and a real tz-aware/tz-naive datetime read-back bug fixed at the root while verifying the migrations.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-06T22:50:00Z
- **Completed:** 2026-07-06T23:10:00Z
- **Tasks:** 3 completed (Task 1 TDD RED/GREEN; Tasks 2-3 straight implementation + verification)
- **Files modified:** 4 (1 module edit, 1 new test file, 2 new migration files)

## Accomplishments

- `backfill_fingerprint_registry(connection) -> tuple[int, int]` added to `api/app/migrations_support.py`: reads all `discs` and `disc_identity_aliases` rows, inserts one `fingerprint_registry` row per source row (Python-generated `uuid.uuid4()` ids — dialect-portable, no DB-side UUID function), deduplicating by fingerprint value across the two source tables so a pre-existing cross-table collision can't crash the migration on the registry's global `UNIQUE(fingerprint)`.
- `api/alembic/versions/900000000005_add_fingerprint_registry.py`: creates `fingerprint_registry` (`String(50)` unique fingerprint, UUID `disc_id` FK, `disc_id` index) matching Plan 05-01's ORM model exactly, then backfills it via `backfill_fingerprint_registry()` inside the same migration transaction. Chains after `900000000004` (the confirmed current head).
- `api/alembic/versions/900000000006_promote_dvdread1_primary.py`: thin wrapper calling `promote_all_dvdread1_discs()` (Plan 05-02); explicit documented no-op `downgrade()` (a mass-promotion reversal is not sanctioned per D-03 immutability). Chains after `900000000005`.
- Verified via `alembic heads`/`alembic history` that the chain is strictly linear with a single head `900000000006` — no branches — and confirmed by a real `alembic upgrade head` dry-run against a scratch SQLite DB running the full chain from base to head cleanly.
- `api/tests/test_disc_identity_regression.py` (IDENT-05 guardrail) is untouched (`git diff --stat` shows zero changes) and passes unmodified.

## Task Commits

1. **Task 1 — RED** — `9570f92` (test) — failing test for `backfill_fingerprint_registry()` (ImportError, function didn't exist yet)
2. **Task 1 — GREEN** — `be47ccc` (feat) — implementation, both tests green
3. **Task 2** — `93809d9` (feat) — rev `900000000005` migration file (fingerprint_registry create + backfill)
4. **Task 3** — `7eb37bc` (feat) — rev `900000000006` migration file (dvdread1 promotion wrapper), plus the datetime-adapter bug fix in `migrations_support.py` and `deferred-items.md`

## Files Created/Modified

- `api/app/migrations_support.py` — added `backfill_fingerprint_registry()` and a `sqlite3.register_adapter(datetime, ...)` registration (see Deviations)
- `api/tests/test_fingerprint_registry_migration.py` — new, 2 tests
- `api/alembic/versions/900000000005_add_fingerprint_registry.py` — new
- `api/alembic/versions/900000000006_promote_dvdread1_primary.py` — new
- `.planning/phases/05-adr-0001-completion-dvdread1-promotion/deferred-items.md` — new, logs two unrelated pre-existing warnings

## Decisions Made

- **Dedupe on backfill:** `discs.fingerprint` and `disc_identity_aliases.fingerprint` are each independently `UNIQUE` within their own table but not across tables prior to this phase (the exact WR-02 gap). `backfill_fingerprint_registry()` tracks fingerprints already inserted and skips a second occurrence (discs processed first, so they win any tie), so pre-existing production data with a cross-table collision doesn't crash the migration on the registry's global `UNIQUE`.
- **sqlite3 datetime adapter registration, not inline string formatting:** rather than pre-formatting `_utcnow()` into a string before binding (which risks ambiguous-timezone parsing if the same string were ever bound against a PostgreSQL `timestamptz` column depending on session timezone), a `sqlite3.register_adapter(datetime, ...)` is registered once at module import — this only affects the stdlib `sqlite3` driver (used by the test harness), is fully inert under PostgreSQL/psycopg2 in production, and produces byte-identical output to SQLAlchemy's own `DATETIME` bind_processor format.
- rev `900000000006`'s `downgrade()` is an explicit `pass` with a comment, never `NotImplementedError` — reversing a mass promotion is not a sanctioned operation (D-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] tz-aware/tz-naive datetime read-back inconsistency in `migrations_support.py`**

- **Found during:** Task 3 verification (running the full test suite + a real `alembic upgrade head` dry-run surfaced a `DeprecationWarning` from the stdlib `sqlite3` driver on Python 3.12+; root-causing the warning source revealed a real correctness issue, not just noise).
- **Issue:** Raw `text()` SQL binds are untyped (`NullType`) and bypass the ORM's `DateTime` type decorator's bind processor entirely (documented and expected for this module — see the UUID `.hex` gotcha from Plan 05-02). Under SQLite, this meant a raw-bound `datetime.datetime` object (from `_utcnow()`, tz-aware UTC) fell through to the stdlib `sqlite3` module's own **deprecated default adapter**, which stores `str(datetime)` verbatim — INCLUDING the `+00:00` tzinfo suffix. ORM-driven inserts into the exact same `created_at` column use SQLAlchemy's own bind_processor, which strips `tzinfo` before storing. The result: reading the same column back via the ORM returned **tz-aware** `datetime` objects for raw-SQL-inserted rows (e.g. `promote_one_disc`'s demoted-alias insert, Plan 05-02) and **tz-naive** ones for ORM-inserted rows — comparing or sorting the two together raises `TypeError: can't compare offset-naive and offset-aware datetimes`, directly relevant to D-06's `(created_at, id)` alias ordering guarantee.
- **Fix:** Registered a `sqlite3.register_adapter(datetime, ...)` at `migrations_support.py` import time, producing the exact same string format SQLAlchemy's own `DATETIME` bind_processor uses (naive, space-separated, microsecond-precision). This unifies both insert paths on identical physical storage and eliminates the deprecation warning at its root (the custom adapter, not the deprecated default, now handles the conversion). No effect on PostgreSQL — this only configures the stdlib `sqlite3` module's process-global adapter registry, entirely separate from `psycopg2`.
- **Files modified:** `api/app/migrations_support.py`
- **Commit:** `7eb37bc`

## Threat Flags

None — this plan's DDL and backfill logic operate solely on the deployment's own existing DB state (operator-triggered `alembic upgrade head`), matching the threat model's stated trust boundary. No new network-facing surface introduced.

## Issues Encountered

None beyond the Rule 1 fix documented above.

## User Setup Required

None — no external service configuration required. The one-command cutover wrapper (D-05) and `docs/self-hosting.md` runbook section are out of this plan's scope (a later plan in this phase).

## Next Phase Readiness

- Both migrations exist, are correctly chained (`900000000005` before `900000000006`), and a single linear head (`900000000006`) is confirmed via `alembic heads`.
- `backfill_fingerprint_registry()` and `promote_all_dvdread1_discs()` are both proven correct against the in-memory SQLite harness (Pitfall 5 — CI never runs a real `alembic upgrade head` against Postgres) and additionally verified via a real dry-run `alembic upgrade head` against a scratch SQLite DB.
- The IDENT-05 guardrail (`test_disc_identity_regression.py`) passes completely unmodified.
- Ready for the next plan in this phase: the D-05 one-command cutover wrapper (toggle read-only → `alembic upgrade head` → toggle read-write) and its `docs/self-hosting.md` runbook section.
- Full `api` test suite green (351 tests) after this plan's additions.

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: api/app/migrations_support.py
- FOUND: api/tests/test_fingerprint_registry_migration.py
- FOUND: api/alembic/versions/900000000005_add_fingerprint_registry.py
- FOUND: api/alembic/versions/900000000006_promote_dvdread1_primary.py
- FOUND: .planning/phases/05-adr-0001-completion-dvdread1-promotion/deferred-items.md
- FOUND: .planning/phases/05-adr-0001-completion-dvdread1-promotion/05-06-SUMMARY.md
- FOUND commit: 9570f92 (test - RED)
- FOUND commit: be47ccc (feat - GREEN)
- FOUND commit: 93809d9 (feat - rev 900000000005)
- FOUND commit: 7eb37bc (feat - rev 900000000006 + tz bug fix)
