---
phase: 05-adr-0001-completion-dvdread1-promotion
reviewed: 2026-07-06T00:00:00Z
depth: deep
files_reviewed: 24
files_reviewed_list:
  - .github/workflows/ci.yml
  - api/alembic/versions/900000000005_add_fingerprint_registry.py
  - api/alembic/versions/900000000006_promote_dvdread1_primary.py
  - api/app/disc_identity.py
  - api/app/migrations_support.py
  - api/app/models.py
  - api/app/routes/disc.py
  - api/tests/test_disc_identity_aliases.py
  - api/tests/test_disc_submit.py
  - api/tests/test_fingerprint_registry.py
  - api/tests/test_fingerprint_registry_migration.py
  - api/tests/test_promote_dvdread1_migration.py
  - api/tests/test_promote_dvdread1_wrapper.py
  - arm/identify.py
  - arm/identify_ovid.py
  - arm/tests/__init__.py
  - arm/tests/test_identify.py
  - arm/tests/test_identify_ovid.py
  - docs/deployment.md
  - docs/self-hosting.md
  - ovid-client/src/ovid/disc_identity.py
  - ovid-client/tests/test_disc_identity.py
  - scripts/promote_dvdread1.py
  - .planning/phases/05-adr-0001-completion-dvdread1-promotion/05-CONTEXT.md
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-07-06
**Depth:** deep (cross-file: model↔migration, client↔server contract, call-chain arbitration)
**Files Reviewed:** 24
**Status:** issues_found

## Summary

Reviewed the ADR-0001 completion phase against its five correctness-critical
surfaces: (1) cross-table registry arbitration, (2) mixed-fleet zero-fragmentation,
(3) the two Alembic migrations, (4) the ARM never-raise contract, and (5) the cutover
wrapper.

The core invariants are **sound and well-tested**:

- **Arbitration converges.** `register_fingerprint()` is correctly wired inside the
  same `db.begin_nested()` savepoint as the accompanying `Disc`/`DiscIdentityAlias`
  insert on every write path (`disc_identity.py:145-148`, `routes/disc.py:782-804`,
  `885-925`). Both cross-table race orderings ("new disc claims F" vs. "attach F as
  alias of a different disc") collapse to the single `IntegrityError → expire_all →
  re-resolve → converge/conflict` shape. `test_fingerprint_registry.py` exercises both
  the raw-helper and the `attach_lookup_aliases`-integration paths. No half-committed
  savepoint or deadlock path found.
- **The mixed-fleet demotion invariant holds.** `_select_primary()` is only reached on
  the new-disc creation branch; every existing-disc path (`_handle_existing_disc`,
  `_identify_existing_disc`, `_handle_existing_registered_disc`) leaves
  `existing.fingerprint` immutable and only attaches the client's declared `dvd1-*` as
  an alias. The `dvd1-*` value stays resolvable via the alias table. The client flip in
  `identify_dvd()` correctly returns `dvd1` primary / zero aliases on `LibdvdreadError`
  or `ValueError`. `test_old_client_resubmit_cannot_demote_promoted_disc` locks this in.
- **Migrations are correct.** down_revision chain is right (…005→…004, …006→…005);
  raw `text()` binds correctly use `.hex` (32-char) for UUID round-tripping under
  SQLite non-native storage and Postgres hex-literal acceptance; the registry backfill
  dedupes a fingerprint appearing as both a primary and an alias (discs win ties);
  per-disc `promote_one_disc` is idempotent via the `WHERE discs.fingerprint =
  <old dvd1>` guard; ordering (DELETE alias → UPDATE primary → INSERT demoted alias
  with fresh `created_at`) preserves D-06.
- **ARM never-raise is preserved** on every new path: `fingerprint_disc_with_identity`
  is called only inside `try/except` guards, and `_load_original`'s degrade returns
  `None` cleanly.

The findings below are quality/robustness defects, not invariant breaks: one
model↔migration schema drift, one operability hazard in the cutover wrapper that
contradicts its own documented guarantee, and three minor items.

## Warnings

### WR-01: `fingerprint_registry.created_at` nullability drifts between ORM and migration

**File:** `api/alembic/versions/900000000005_add_fingerprint_registry.py:43` vs. `api/app/models.py:180-182`
**Issue:** The migration declares `created_at` as `nullable=True`:
```python
sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
```
but the ORM model types it as non-optional (`Mapped[datetime]`), which SQLAlchemy 2.0
renders as `NOT NULL`:
```python
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
```
The pytest suite builds its schema from the ORM via `create_all` (CI never runs
`alembic upgrade` — confirmed in `migrations_support.py` docstring and `ci.yml`), so the
**test DB gets `NOT NULL` while a real Postgres deployment gets `NULLABLE`**. The two
schemas disagree on this column. Functional impact is low today because both the ORM
`default=_utcnow` and the raw backfill (`:now`) always populate the value, so no NULL
rows arise — but this is exactly the class of drift that (a) makes future
`alembic revision --autogenerate` emit spurious `alter_column` noise and (b) lets a
future non-defaulted insert path write a NULL that the ORM's own DDL would have
rejected.
**Fix:** Make the migration match the model (every other `created_at` in `models.py` is
non-nullable):
```python
sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
```

### WR-02: cutover wrapper silently falls back to a hardcoded `standalone` mode, contradicting its own guarantee

**File:** `scripts/promote_dvdread1.py:53,56-73,153-155`
**Issue:** The module docstring promises the restore step "restores that captured value
(**never a hardcoded default**) … so a canonical-mode operator's restore step can never
silently leave the server on the wrong mode." But `_current_ovid_mode()` returns the
hardcoded `_DEFAULT_MODE = "standalone"` on *three* failure paths — `OSError`, non-zero
exit, and empty output:
```python
except OSError:
    return _DEFAULT_MODE
if result.returncode != 0:
    return _DEFAULT_MODE
return result.stdout.strip() or _DEFAULT_MODE
```
`original_mode` is then what the `finally` block restores. Concrete failure scenario:
an operator runs the cutover against a **mirror** deployment (D-01 requires each mirror
to run `alembic upgrade head` locally). If the `docker compose exec api printenv
OVID_MODE` capture transiently fails (container mid-recreate, daemon hiccup),
`original_mode` becomes `"standalone"`, and the `finally` restarts the api with
`OVID_MODE=standalone` — **silently converting a read-only mirror into a read-write
standalone node.** That violates the project's mirror-read-only architectural invariant
and lets the node accept writes that can never sync upstream (divergent data). This is
the exact "wrong mode" outcome the docstring claims is impossible.

Relatedly, the restore call itself uses `check=True`; if the *restore* step fails after
the flip-to-mirror succeeded, the deployment is stranded read-only and the reassuring
"NOT stranded read-only" message never prints — the wrapper guards against migration
failure but not against restore failure.
**Fix:** Do not invent a mode on capture failure. Either abort before any mutation when
the current mode cannot be positively determined, or persist the captured raw
value and refuse to proceed if capture was a fallback:
```python
def _current_ovid_mode(compose_args):
    result = subprocess.run([...], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("cannot determine current OVID_MODE; aborting before any change")
    return result.stdout.strip()  # "" is a valid, restorable value (unset)
```
and wrap the `finally` restore so a restore failure emits an explicit "DEPLOYMENT MAY BE
STRANDED READ-ONLY — set OVID_MODE=<original> and restart api manually" message.

## Info

### IN-01: unreachable dead-code `return` in the registry backfill

**File:** `api/app/migrations_support.py:259-261`
**Issue:** There are two `return` statements; the second is unreachable:
```python
    return discs_inserted, aliases_inserted

    return len(disc_rows), len(alias_rows)
```
Beyond being dead code, the orphaned line returns the *pre-dedupe* row counts — the
wrong values — so if a later edit ever made it reachable it would silently misreport
the backfill counts the migration prints.
**Fix:** Delete line 261.

### IN-02: `promote_one_disc` docstring claims "Never raises" but has no exception guard

**File:** `api/app/migrations_support.py:92,105-132`
**Issue:** The docstring asserts "Never raises. Returns `True` if a promotion occurred,
`False` otherwise." The three `connection.execute()` calls (DELETE/UPDATE/INSERT) have
no `try/except` and can raise (`IntegrityError`, `OperationalError`, etc.). The atomic
per-disc commit in `promote_all_dvdread1_discs` means a raised exception leaves no
half-promotion persisted (alembic rolls the segment back), so this is a documentation
inaccuracy rather than a data bug — but "Never raises" is relied on as a contract word
elsewhere in this codebase (ARM), so the false claim is worth correcting.
**Fix:** Change the docstring to "Returns `True`/`False`; propagates DB errors to the
caller, which commits per-disc so an interrupted run leaves no partial promotion."

### IN-03: `fingerprint_registry` FK to `discs.id` has no `ON DELETE`, and no cascade from `Disc`

**File:** `api/app/models.py:177-179`, `api/alembic/versions/900000000005_add_fingerprint_registry.py:44`
**Issue:** The registry's `disc_id` FK is created with the default `RESTRICT`, and unlike
`identity_aliases`/`titles` the registry is not attached to any `Disc` relationship with
`cascade="all, delete-orphan"`. No disc-deletion path exists in this phase, so there is
no current defect — but the moment a future feature deletes a `Disc`, the delete will
fail on the orphaned registry FK (the registry is documented as "write-only, never
deleted"). Worth a deliberate decision now rather than a surprise later.
**Fix:** Either add `ondelete="CASCADE"` to the FK (registry entry dies with its disc)
or add an explicit comment that discs are permanently non-deletable and the registry FK
intentionally enforces that.

---

_Reviewed: 2026-07-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
