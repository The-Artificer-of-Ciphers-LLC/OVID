---
phase: 06-oauth-account-linking
plan: 01
subsystem: api-data-model
status: complete
tags: [oauth, account-linking, orm, alembic, security, noauth]
requires: []
provides:
  - PendingAccountLink ORM model (table pending_account_links)
  - Alembic migration 900000000007 (head)
affects:
  - api/app/models.py
  - api/alembic/versions/
tech-stack:
  added: []
  patterns:
    - "UUID-PK + _utcnow default + ForeignKey(ondelete=CASCADE) ORM convention (mirrors UserOAuthLink)"
    - "Single-use enforced by nullable consumed_at column, not a DB UniqueConstraint"
key-files:
  created:
    - api/alembic/versions/900000000007_pending_account_links.py
  modified:
    - api/app/models.py
decisions:
  - "D-01: merge state is a durable DB row keyed by existing_user_id, not session state — removes the nOAuth 'next login in this session merges anywhere' vector (T-06-01)"
  - "No UniqueConstraint on (existing_user_id, new_provider, new_provider_id): multiple pending offers over time are valid; single-use is the consumed_at marker"
metrics:
  duration: 3m
  completed: 2026-07-07
  tasks: 2
  files: 2
---

# Phase 06 Plan 01: PendingAccountLink Model & Migration Summary

Added the `PendingAccountLink` ORM model and Alembic migration `900000000007`, giving the confirm-gated OAuth merge a durable, single-use, TTL-bearing, auditable server-side state row keyed by `existing_user_id` (D-01) — the Wave 1 foundation for Plan 04 (merge logic) and Plan 05 (route wiring).

## What Was Built

- **`PendingAccountLink(Base)`** in `api/app/models.py`, table `pending_account_links`, columns: `id` (UUID PK, `default=uuid.uuid4`), `existing_user_id` (UUID FK → `users.id` `ondelete=CASCADE`, non-null), `new_provider` (`String(30)`), `new_provider_id` (`String(255)`), `created_at` (`DateTime(timezone=True)`, `default=_utcnow`), `expires_at` (`DateTime(timezone=True)`, non-null, caller-set TTL), `consumed_at` (`DateTime(timezone=True)`, nullable single-use marker). `__table_args__` declares `Index("idx_pending_account_links_existing_user", "existing_user_id")`. No `UniqueConstraint`. Reused existing top-of-file imports — no new imports added.
- **Migration `900000000007_pending_account_links.py`** — `create_table` matching the ORM column-for-column with `sa.ForeignKeyConstraint([...], ['users.id'], ondelete='CASCADE')` + `sa.PrimaryKeyConstraint('id')`, then `create_index`. `down_revision = '900000000006'`; `downgrade()` drops the index then the table. Brand-new empty table — no backfill, no SQLite/Postgres shim.

## Verification

- Task 1 model round-trip on in-memory SQLite (create user + pending link, `consumed_at is None`, FK matches, table registered in `Base.metadata`): **OK**.
- Task 2 Alembic chain: single head `['900000000007']`, `down_revision == '900000000006'`, linear (no branch): **OK**. (Plan's verify expression asserted an exact `tuple` but `ScriptDirectory.get_heads()` returns a `list` — the underlying head value is correct; re-checked with a list comparison.)
- Full existing API suite: **362 passed** (`cd api && .venv/bin/python -m pytest tests/ -q`).

## Threat Mitigations Applied

- **T-06-01 (Spoofing/Elevation, high):** merge state lives in a DB row keyed by `existing_user_id` (this plan), not session — removing the nOAuth vector. The ownership check that *consumes* the row is Plan 04.
- **T-06-02 (Information disclosure, low):** `existing_user_id` FK uses `ondelete=CASCADE`, so pending offers cannot outlive a deleted account (enforced at both ORM and migration layers).

## Deviations from Plan

None affecting implementation — the plan was executed exactly as written. One test-expression note (not a code change): the Task 2 verify snippet asserted `heads==('900000000007',)` (tuple), but `get_heads()` returns a list; the head value itself is correct and singular, confirmed via a corrected list comparison.

## Deferred Issues (out of scope — logged, not fixed)

Three pre-existing warnings surfaced by the API suite, provably invariant to this plan's two-file diff (none reference `pending_account_links`). Logged to `.planning/phases/06-oauth-account-linking/deferred-items.md`:
- `fastapi/testclient.py:1` StarletteDeprecationWarning (httpx→httpx2 test-infra migration).
- `slowapi/extension.py:720` DeprecationWarning (`asyncio.iscoroutinefunction`, third-party internal).
- `tests/test_promote_dvdread1_migration.py:279` SAWarning (pre-existing test for the prior 900000000006 migration).

## For the Next Plan

- The table + model are available for merge CRUD helpers (Plan 04 `merge.py`) and route wiring (Plan 05). Load rows by `id` / `existing_user_id` via explicit queries — no `relationship`/`back_populates` was added, by design.
- Alembic head is now `900000000007`; any subsequent Phase 06 migration must chain from it.

## Commits

- `20b5b66` feat(06-01): add PendingAccountLink ORM model
- `2961564` feat(06-01): add migration 900000000007 pending_account_links

## Self-Check: PASSED
- `api/app/models.py` — FOUND (PendingAccountLink class present, verified via import round-trip)
- `api/alembic/versions/900000000007_pending_account_links.py` — FOUND
- Commit `20b5b66` — FOUND
- Commit `2961564` — FOUND
