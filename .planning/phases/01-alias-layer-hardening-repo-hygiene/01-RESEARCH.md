# Phase 1: Alias-Layer Hardening & Repo Hygiene - Research

**Researched:** 2026-07-05
**Domain:** Concurrency-safe SQLAlchemy write paths, verification state-machine consolidation, additive API-contract evolution, pytest regression guardrails (FastAPI + SQLAlchemy 2.x + Postgres 16 / in-memory SQLite test harness)
**Confidence:** HIGH — every finding is grounded in the live tree (real file paths, symbol names, and the actual passing tests); no new external dependency is introduced.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** IDENT-02 race fix = **unique-constraint + catch-`IntegrityError`** (equiv. `ON CONFLICT DO NOTHING`), then re-resolve to the winning `Disc`/alias. Chosen over advisory locks, `SELECT … FOR UPDATE`, SERIALIZABLE+retry.
- **D-02:** This is the ONLY option regression-testable against the in-memory SQLite harness (SQLite raises `IntegrityError` on UNIQUE violation exactly like Postgres). Alternatives are Postgres-only semantics SQLite silently no-ops.
- **D-03:** Restructure resolution from "check, then unconditionally `add()`" → "add, catch conflict, re-query the winner." Wrap each alias insert in a **savepoint / nested transaction** so one alias losing the race does not roll back the whole submission; clean up a partial `Disc` insert if a sibling alias insert then collides.
- **D-04:** IDENT-01 aliases returned as **objects** carrying a method label — strictly **additive** field `fingerprint_aliases: list[{fingerprint: str, method: str, is_primary: bool}]`.
- **D-05:** Keep top-level `fingerprint: str` **unchanged** (primary). Include the primary in the array flagged `is_primary: true`.
- **D-06:** Ordering = primary-first, then remaining aliases in **insertion order**. Do NOT sort by string.
- **D-07:** Strictly additive — `ovid-client`, ARM shim, and `web/lib/api.ts` keep working unmodified. New Pydantic model (e.g. `FingerprintAliasResponse`).
- **D-08:** VERIFY-02 = new `api/app/verification.py` as **flat module-level functions + explicit transition table** (module-level `frozenset`/dict), matching `disc_identity.py`/`sync.py` convention. NO service class, NO FSM library.
- **D-09:** General transition table has **zero** entries targeting `"disputed"`. `disputed` reachable ONLY via a separate `flag_dispute(db, disc, actor, reason)` — the single grep-able writer of that status.
- **D-10:** Raise a domain exception `VerificationTransitionError` (carrying `current_status`/`attempted_status`/`disc_id`), caught at the route boundary → structured JSON error envelope, same as `DiscIdentityConflict`.
- **D-11:** Move "cannot verify your own submission" INTO the verification function (transition invariant). Keep coarse role/authz at the route layer.
- **D-12:** Function signatures accept a full `actor` (not a bare id) + structured exception, so Phase 2 can wrap them. Do NOT implement confirmation-counting / confirmations table / rate-limit state now.
- **D-13:** IDENT-05 = golden ORM-seeded record asserted through `GET /v1/disc`. Reuse `seed_test_disc`/`conftest.py`. NO synthetic row, NO golden-JSON snapshot.
- **D-14:** Assert resolution AND frozen structure vs. a **hardcoded expected dict kept independent of the seed call**.
- **D-15:** Plain **unmarked** pytest (e.g. `api/tests/test_disc_identity_regression.py`). CI runs full `pytest` with no marker exclusions. Must NOT depend on `real_disc`.
- **D-16:** Assert on **stable disc identity** (persisted `disc_id`/release) + normalized structure looked up by the fixed `dvd1-*` string — NOT on `dvd1-*` literally being `response["fingerprint"]` (survives Phase 5 promotion).
- **D-17:** Delete `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py`.
- **D-18:** Relocate still-useful dev/UAT tooling (`run_uat.py`, `create_uat_dirs.py`) under `scripts/` rather than delete. Planner confirms obsolete vs. used.
- **D-19:** Gitignore `uat_results.json` and `uat_dirs/`.

### Claude's Discretion
- Exact concurrency-control code structure (savepoint mechanics, where the catch/re-resolve loop sits) — within D-01/D-03.
- Precise Pydantic model naming and field types for the alias objects — within D-04–D-07.
- Final disposition of each individual root script (delete vs. relocate) once obsolescence confirmed — within D-17/D-18.

### Deferred Ideas (OUT OF SCOPE)
- Two-contributor confirmation + anti-Sybil weighting → Phase 2 (VERIFY-01/03/04). Phase 1 builds only the `verification.py` module Phase 2 consumes.
- `dvdread1-*` promotion / dual-string submission → Phase 5 (IDENT-03/04).
- Rate-limiting / Redis multi-worker fix → Phase 3 (INFRA-01..04).
- ARM shim versioned interface (ARM-02) → Phase 8.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-01 | Lookup response exposes all `fingerprint_aliases` for a disc | `Disc.identity_aliases` relationship already exists (`models.py:109`); add `FingerprintAliasResponse` to `schemas.py` + build it in `_disc_to_response` (`routes/disc.py:123`). Additive-only. See §Architecture Pattern 4. |
| IDENT-02 [guardrail] | Alias check-then-insert write path race-safe under concurrent gunicorn workers | UNIQUE constraints already live on both `discs.fingerprint` and `disc_identity_aliases.fingerprint` (migrations `7ffb31fc807f:91`, `900000000003:33`). Only the check-then-`add()` in `disc_identity.py` needs the catch-and-reresolve restructure. See §Architecture Pattern 1 + §Pitfall 1/2. |
| IDENT-05 [guardrail] | Permanent CI regression proving a `dvd1-*` still resolves | CI runs `python -m pytest tests/` in `api/` on every push/PR to main+develop with no marker exclusions. New unmarked test file. See §Architecture Pattern 3. |
| VERIFY-02 | Verification transitions consolidated into one guarded module | 5 inline status mutations today (`routes/disc.py:241,245,422,444,616`); no existing transition helper. New `verification.py`. See §Architecture Pattern 2 + §Pitfall 3 (behavior-change conflict). |
| CLEAN-01 | Remove/relocate root ad-hoc scripts | All 7 targets confirmed present & git-tracked. See §Runtime State Inventory. |
| CLEAN-02 | Gitignore UAT artifacts | `uat_results.json` + `uat_dirs/` tracked; require `git rm --cached` + `.gitignore` entries. See §Runtime State Inventory. |
</phase_requirements>

## Summary

Phase 1 is entirely an **in-house-pattern hardening** phase: no new libraries, no new dependencies, and — critically — **no new Alembic migration is required**. The database-level guarantees the whole phase leans on are already live: `discs.fingerprint` is `UNIQUE` (initial schema migration `7ffb31fc807f`, line 91) and `disc_identity_aliases.fingerprint` is `UNIQUE` (migration `900000000003`, line 33). Both constraints are re-created for the SQLite test harness by `Base.metadata.create_all` in `conftest.py`, so the exact `IntegrityError`-on-conflict behaviour the IDENT-02 fix relies on is reproducible in tests. Production runs `gunicorn -w 4` (`docker-compose.prod.yml:34`, `docker-compose.test.yml:33`), so the 4-worker race IDENT-02 guards against is real.

Two findings materially change the plan versus the CONTEXT.md's assumptions and MUST be surfaced to the planner:

1. **There is no `_validate_status_transition` helper.** The CONTEXT.md's canonical-refs pointed at `_validate_status_transition (~line 68)`; it does not exist. Verification-status writes are **five inline mutations** scattered across `routes/disc.py` (lines 241, 245, 422, 444, 616). `verification.py` must consolidate all five, not one helper.

2. **VERIFY-02 is a behavior CHANGE, not pure consolidation, and two existing passing tests encode the bug.** `seed_test_disc` seeds discs with `status="verified"` (`conftest.py:154`). `test_submit_duplicate_fingerprint_conflicting_metadata` (`test_disc_submit.py:115`) and `test_duplicate_conflicting_metadata_disputes` (`test_disc_submit.py:198`) both drive a conflicting second submission against an already-**verified** seeded disc and assert it flips to `disputed`. That flip is *exactly* the silent-flip VERIFY-02 success-criterion #4 forbids. Implementing D-09's guard will break both tests; the plan must update them (seed `unverified` to keep exercising the dispute path, and add a test asserting a verified disc stays verified on a mismatched submission). This is a deliberate, documented behavior change — not "no behavior drift."

**Primary recommendation:** Restructure `disc_identity.py`'s alias/disc inserts to insert-first-catch-`IntegrityError`-then-re-resolve inside `db.begin_nested()` savepoints (IDENT-02); extract all five status mutations into a flat-function `verification.py` with an explicit transition `frozenset` plus a single `flag_dispute` chokepoint that refuses to touch an already-`verified` disc (VERIFY-02); add an additive `fingerprint_aliases` object array to `DiscLookupResponse` sourced from the existing `Disc.identity_aliases` relationship with explicit insertion ordering (IDENT-01); add one unmarked golden `dvd1-*` regression test (IDENT-05); and delete/relocate the root scripts + gitignore the UAT artifacts with `git rm --cached` (CLEAN-01/02).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Race-safe alias/disc insert (IDENT-02) | Database (UNIQUE constraint) | API domain service (`disc_identity.py`) | Correctness under 4 concurrent gunicorn workers can only be guaranteed by the DB's atomic constraint enforcement; the service layer's job is to *catch* the violation and converge, never to prevent the race by reading first. |
| Verification state machine (VERIFY-02) | API domain service (`verification.py`) | API route layer (thin handlers) | Transition legality is domain logic, not transport; house style already isolates such logic outside `routes/` (`disc_identity.py`, `sync.py`). |
| Alias exposure (IDENT-01) | API schema + serializer | Web/client consumers (opt-in) | Response shaping lives in `schemas.py` + `_disc_to_response`; consumers stay untouched because the field is additive. |
| Anti-fragmentation guardrail (IDENT-05) | Test suite / CI | — | A permanent regression test is a CI-tier artifact; it exercises the API tier but owns no runtime code. |
| Repo hygiene (CLEAN-01/02) | Repo / VCS | — | Pure version-control hygiene; no runtime tier. |

## Standard Stack

**No new packages.** This phase is implemented entirely with the already-installed stack. Verified against `api/requirements.txt`:

| Library | Version (constraint) | Purpose in this phase | Why standard |
|---------|----------------------|-----------------------|--------------|
| SQLAlchemy | `>=2.0,<3.0` (asyncio extra) | ORM, `Session.begin_nested()` savepoints, `IntegrityError` catch | Already the project ORM (`api/app/database.py`) [VERIFIED: api/requirements.txt] |
| FastAPI | `>=0.110,<1.0` | Route handlers, response models | Already the API framework [VERIFIED: api/requirements.txt] |
| Pydantic | v2 (via FastAPI) | New `FingerprintAliasResponse` model | All schemas already Pydantic v2 (`schemas.py`) [VERIFIED: api/app/schemas.py] |
| Alembic | `>=1.13,<2.0` | (none needed — constraints already exist) | — [VERIFIED: api/requirements.txt] |
| pytest + httpx | (CI-installed) | Regression + behavior tests | Existing harness (`api/tests/conftest.py`) [VERIFIED: .github/workflows/ci.yml] |
| gunicorn | `>=21.2,<24.0`, run `-w 4` | The multi-worker prod runtime IDENT-02 protects | [VERIFIED: docker-compose.prod.yml:34] |

**Installation:** none. `git rm --cached` (CLEAN-02) is the only tooling command.

## Package Legitimacy Audit

**Not applicable — this phase installs no external packages.** All work uses the already-vendored stack above. No `SLOP`/`SUS`/`OK` verdicts to record; no `checkpoint:human-verify` install gates needed.

## Architecture Patterns

### System Architecture Diagram (write path, post-Phase-1)

```
                        POST /v1/disc  |  /v1/disc/register  |  /v1/disc/{fp}/verify  |  /v1/disc/{fp}/resolve
                                  │
                                  ▼
        ┌───────────────────────────────────────────────────────────┐
        │  routes/disc.py  (thin handlers — authz + HTTP shaping)     │
        │   • coarse role check (trusted/editor/admin) stays here     │
        │   • catches DiscIdentityConflict + VerificationTransitionError│
        └───────────────┬───────────────────────────┬───────────────┘
                        │                           │
             identity write path            verification transition
                        │                           │
                        ▼                           ▼
     ┌────────────────────────────┐   ┌────────────────────────────────┐
     │ disc_identity.py            │   │ verification.py  (NEW)          │
     │  resolve_existing_…()       │   │  LEGAL_TRANSITIONS: frozenset   │
     │  attach_lookup_aliases()    │   │  verify(db, disc, actor)        │
     │  ── insert-first,           │   │  flag_dispute(db, disc, actor,  │
     │     catch IntegrityError,   │   │      reason)  ← ONLY writer of  │
     │     re-resolve winner       │   │      status="disputed"          │
     │     inside begin_nested()   │   │  reject/resolve helpers         │
     └──────────────┬─────────────┘   └────────────────┬───────────────┘
                    │                                   │
                    ▼                                   ▼
        ┌─────────────────────────────────────────────────────────┐
        │  PostgreSQL 16 (prod, gunicorn -w 4)  /  SQLite (tests)   │
        │   UNIQUE(discs.fingerprint)            ← already live      │
        │   UNIQUE(disc_identity_aliases.fingerprint) ← already live │
        │   ← atomic conflict enforcement is the real race guard     │
        └─────────────────────────────────────────────────────────┘

         GET /v1/disc/{fp}  →  resolve_disc_identity()  →  _disc_to_response()
                                                              │
                                                              ▼  (IDENT-01, additive)
                          DiscLookupResponse.fingerprint_aliases:
                            [ {fingerprint, method, is_primary=true},   ← primary first
                              {fingerprint, method, is_primary=false}, … ] ← insertion order
```

### Component Responsibilities

| File | Change | Requirement |
|------|--------|-------------|
| `api/app/disc_identity.py` | Restructure `attach_lookup_aliases` (lines 115-128) and the disc-insert flow to insert-first/catch-`IntegrityError`/re-resolve inside savepoints | IDENT-02 |
| `api/app/routes/disc.py` | Two submission call sites (`submit_disc` ~466-501, `register_disc` ~347-362) wrap disc+alias inserts; replace 5 inline status mutations with `verification.py` calls; add `selectinload(Disc.identity_aliases)` to lookup; catch `VerificationTransitionError` | IDENT-02, VERIFY-02, IDENT-01 |
| `api/app/verification.py` (NEW) | Flat functions `verify`, `flag_dispute`, `resolve_dispute` + `LEGAL_TRANSITIONS` frozenset + `VerificationTransitionError` | VERIFY-02 |
| `api/app/schemas.py` | Add `FingerprintAliasResponse`; add optional `fingerprint_aliases` field to `DiscLookupResponse` (line 49) | IDENT-01 |
| `api/app/models.py` | Add deterministic `order_by` to `Disc.identity_aliases` relationship (line 109) OR sort in serializer | IDENT-01 (D-06) |
| `web/lib/api.ts` | Add optional `fingerprint_aliases?` to the `DiscLookupResponse` interface (line 83) | IDENT-01 (D-07, additive) |
| `api/tests/test_disc_identity_regression.py` (NEW) | Unmarked golden `dvd1-*` test | IDENT-05 |
| `api/tests/test_disc_submit.py` | Update lines 115 & 198 tests to new guarded dispute behavior | VERIFY-02 |
| repo root | Delete/relocate scripts; `.gitignore` + `git rm --cached` | CLEAN-01/02 |

### Pattern 1: Insert-first / catch-`IntegrityError` / re-resolve (IDENT-02)

**What:** The race-safe replacement for `disc_identity.py`'s current TOCTOU pattern.

**Current racing code** (`api/app/disc_identity.py:115-128`) — check-then-`add()`:
```python
def attach_lookup_aliases(db, disc, primary_fingerprint, aliases):
    for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
        resolution = resolve_disc_identity(db, alias)   # ← read (T0)
        if resolution is None:
            db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))  # ← insert (T1); worker B inserted between T0 and T1
            continue
        if resolution.disc.id != disc.id:
            raise DiscIdentityConflict(alias, resolution.disc)
```

**Recommended structure** (D-01/D-03) — insert inside a savepoint, catch the UNIQUE violation, re-resolve to the winner:
```python
from sqlalchemy.exc import IntegrityError

def attach_lookup_aliases(db, disc, primary_fingerprint, aliases):
    for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
        try:
            with db.begin_nested():                       # SAVEPOINT — isolates this insert
                db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))
                db.flush()                                # forces the INSERT now, raising here on conflict
        except IntegrityError:
            db.expire_all()                               # discard stale identity map after rollback-to-savepoint
            winner = resolve_disc_identity(db, alias)     # who actually holds it now?
            if winner is None:
                raise                                     # genuinely unexpected — re-raise
            if winner.disc.id != disc.id:
                raise DiscIdentityConflict(alias, winner.disc)  # legitimate cross-disc conflict → 409
            # else: our own disc already owns this alias → idempotent no-op
```

- `db.begin_nested()` issues a real `SAVEPOINT` on both Postgres and SQLite; on `IntegrityError` only that savepoint rolls back, so a sibling alias that already committed within the same submission survives (D-03). [CITED: docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint]
- The same shape wraps the **disc row** insert in `submit_disc`/`register_disc`: two workers racing the *same new primary* both attempt `INSERT discs(fingerprint=…)`; the loser catches `IntegrityError`, re-resolves, and proceeds as the "duplicate submission" branch (auto-verify / conflict) instead of creating a split row.

**Why not the alternatives** (research focus item 1, for the record):
| Option | Holds under 4 Postgres workers? | Testable on SQLite harness? | Verdict |
|--------|-------------------------------|-----------------------------|---------|
| (a) UNIQUE + catch `IntegrityError` / `ON CONFLICT DO NOTHING` | Yes — constraint is atomic | **Yes** — SQLite raises `IntegrityError` on UNIQUE violation identically | **CHOSEN (D-01)** |
| (b) `SELECT … FOR UPDATE` row lock | Yes | No — SQLite silently ignores `FOR UPDATE`; test would falsely pass | Rejected |
| (c) `pg_advisory_xact_lock(hashtext(fp))` | Yes | No — no SQLite equivalent; Postgres-only | Rejected |

`insert().on_conflict_do_nothing()` exists as a Postgres-dialect construct in SQLAlchemy 2.x, but D-01 deliberately uses the dialect-neutral **catch-`IntegrityError`** form so one code path serves both Postgres and the SQLite test harness. [CITED: docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert]

### Pattern 2: Flat-function verification module with an explicit transition table (VERIFY-02)

**What:** `api/app/verification.py` mirroring the `disc_identity.py` house style (module-level functions + a domain exception, no service class — D-08).

**The five inline mutations to absorb** (all in `routes/disc.py`):
| Line | Path | Transition | Notes |
|------|------|-----------|-------|
| 241 | `resolve_dispute` action="verify" | `disputed → verified` | trusted/editor/admin only |
| 245 | `resolve_dispute` action="reject" | `disputed → unverified` | |
| 422 | `submit_disc` metadata match | `unverified → verified` (auto-verify) | different user (same-user 409 already returned at line 412); creates a `verify` DiscEdit + returns "auto-verified" |
| 444 | `submit_disc` metadata mismatch | `→ disputed` **UNCONDITIONALLY** | **THE BUG** — fires even when `existing.status == "verified"` |
| 616 | `verify_disc` | `unverified → verified`; `verified → verified` is idempotent 200, **no edit** | self-verify 403 (line 600) — move into `verify()` per D-11 |

**Recommended module shape:**
```python
# api/app/verification.py
"""Guarded verification state machine — the single writer of disc.status."""
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("unverified", "verified"),
    ("disputed",   "verified"),   # via resolve only
    ("disputed",   "unverified"), # via resolve only
    # NOTE: no ("*", "disputed") entry — disputed is reached ONLY through flag_dispute (D-09)
})

class VerificationTransitionError(Exception):
    def __init__(self, disc_id, current_status, attempted_status): ...

def verify(db, disc, actor) -> bool:
    """unverified→verified (idempotent). Returns True if a transition occurred.
    Raises VerificationTransitionError on self-verify or illegal source state (D-11)."""
    if disc.submitted_by is not None and str(disc.submitted_by) == str(actor.id):
        raise VerificationTransitionError(disc.id, disc.status, "verified")  # → 403 at route
    if disc.status == "verified":
        return False                                    # idempotent no-op, caller emits "already verified", NO edit
    if (disc.status, "verified") not in LEGAL_TRANSITIONS:
        raise VerificationTransitionError(disc.id, disc.status, "verified")
    disc.status = "verified"; disc.verified_by = actor.id
    return True

def flag_dispute(db, disc, actor, reason) -> bool:
    """The ONLY writer of status='disputed'. Refuses to touch a verified disc (VERIFY-02 crit #4)."""
    if disc.status == "verified":
        return False                                    # do NOT silently flip a verified disc
    disc.status = "disputed"
    return True
```

- `verify()` returns a **bool** so callers keep their distinct messaging/DiscEdit behavior (the endpoint's idempotent "already verified" no-edit path vs. the auto-verify path's "auto-verified" + edit). This preserves every current test in `test_disc_verify.py` (esp. `test_verify_already_verified_idempotent:71` and `test_verify_already_verified_no_extra_edit:82`, which require **200 + no DiscEdit** — see §Pitfall 4).
- Self-verify moves inside `verify()` (D-11); the route maps `VerificationTransitionError` with `attempted="verified"` and a verified→self condition to 403, others to 409/400. Keep the coarse `role not in (...)` check at the route (D-11).
- `actor` is the full `User` object, not an id (D-12 seam for Phase 2).

### Pattern 3: Permanent unmarked golden `dvd1-*` regression (IDENT-05)

**What:** `api/tests/test_disc_identity_regression.py` — an unmarked pytest that seeds a real `dvd1-*` pressing and asserts it still resolves with frozen structure through `GET /v1/disc`.

- **Guaranteed to run every PR:** `.github/workflows/ci.yml` `api-tests` job runs `python -m pytest tests/ -v --tb=short` in `api/` with **no `-m` marker filter** on every `push`/`pull_request` to `main` and `develop`. An unmarked test in `api/tests/` is therefore unconditionally collected. There is no `pytest.ini`/`[tool.pytest]` markers config in `api/` (the `real_disc` marker lives in `ovid-client`), so nothing can gate it out (D-15). [VERIFIED: .github/workflows/ci.yml]
- **Use a `dvd1-*` fingerprint, not the fixture's:** `seed_test_disc` seeds `fingerprint="dvd-ABC123-main"` (`conftest.py:150`) — **not** a `dvd1-*` string. The regression test must seed a `dvd1-`-prefixed primary (e.g. `dvd1-<hash>`) to represent a real pre-migration OVID-DVD-1 identity. Write a dedicated golden seeder (or parametrize `seed_test_disc`) rather than reusing the Matrix fixture verbatim.
- **Frozen structure via independent expected dict (D-14):** assert the resolved title/chapter/track/release fields against a **hardcoded literal dict** written into the test, NOT re-read from the seed inputs (else tautological). IDENT-05 catches silent data drift, not just a 200.
- **Phase-5-survivable assertions (D-16):** assert on the persisted `disc_id`/release identity and the normalized structure returned when looking up **by the fixed `dvd1-*` string** — do NOT assert `response["fingerprint"] == "dvd1-…"`. Mirror the tolerance in `test_disc_identity_aliases.py:106-108`, where a lookup by one string legitimately returns a different primary in `fingerprint`. After Phase 5, `dvd1-*` becomes an alias to a `dvdread1-*` primary; the assertion must still pass.
- Add a `# guardrail: IDENT-05` docstring for discoverability (D-15).

### Pattern 4: Additive alias-object exposure (IDENT-01)

**What:** Add `fingerprint_aliases` to `DiscLookupResponse` sourced from the existing `Disc.identity_aliases` relationship (`models.py:109`).

```python
# schemas.py — new model
class FingerprintAliasResponse(BaseModel):
    fingerprint: str
    method: str          # derived from prefix, NOT stored (see below)
    is_primary: bool = False

class DiscLookupResponse(BaseModel):
    ...
    titles: list[TitleResponse] = Field(default_factory=list)
    fingerprint_aliases: list[FingerprintAliasResponse] = Field(default_factory=list)  # additive
```

Build it in `_disc_to_response` (`routes/disc.py:123`), primary first then aliases in insertion order (D-06):
```python
aliases = [FingerprintAliasResponse(fingerprint=disc.fingerprint,
                                    method=_method_of(disc.fingerprint), is_primary=True)]
aliases += [FingerprintAliasResponse(fingerprint=a.fingerprint,
                                     method=_method_of(a.fingerprint), is_primary=False)
            for a in sorted(disc.identity_aliases, key=lambda a: (a.created_at, str(a.id)))]
```

- **`method` is DERIVED, not stored.** `DiscIdentityAlias` has no `method` column (`models.py:128-149`) — do NOT add one (no migration this phase). Derive from the fingerprint prefix (e.g. `fp.split("-", 1)[0]` → `"dvd1"`, `"dvdread1"`, `"bd1"`, `"bd2"`). D-07's "kept in sync with the alias ORM table" means the model list, not a method column.
- **Deterministic ordering (D-06):** the `identity_aliases` relationship has **no `order_by`** (`models.py:109-111`), so it returns rows in undefined order. Either add `order_by="DiscIdentityAlias.created_at, DiscIdentityAlias.id"` to the relationship or sort in the serializer as shown. Sort by `(created_at, id)` — `created_at` alone can tie under SQLite's second/sub-second resolution.
- **Eager-load to avoid N+1 / lazy-load surprises:** the lookup query (`routes/disc.py:277`) currently eager-loads only titles+releases. Add `selectinload(Disc.identity_aliases)`. `_disc_to_response` is also used by `lookup_disc_by_upc` (line 180) and `list_disputed_discs` (line 208) — either add the loader there too or accept an in-request lazy load (session is open, so it works but adds queries).
- **Additive-safe (D-07):** existing tests in `test_disc_lookup.py` assert specific keys but never assert the *absence* of extra keys, and `test_disc_identity_aliases.py` asserts `lookup.json()["fingerprint"]` (the unchanged primary) — all keep passing. `web/lib/api.ts` `DiscLookupResponse` (line 83) gets an optional `fingerprint_aliases?` field; TS structural typing means omission is harmless for existing callers.

### Anti-Patterns to Avoid
- **Reading before inserting to "prevent" the race (TOCTOU).** The current `resolve_disc_identity`-then-`add()` cannot be made safe by widening the read; the DB constraint is the only real guard. Never replace it with a "check more carefully" refactor.
- **A second writer of `status="disputed"`.** After VERIFY-02, `grep -rn 'status.*=.*"disputed"' api/app/` must return exactly one hit (inside `flag_dispute`). Any inline flip elsewhere reintroduces the bug.
- **Asserting `response["fingerprint"] == "dvd1-…"` in the IDENT-05 test.** Guarantees a false failure after Phase 5 promotion (D-16).
- **Adding a `method` column or an Alembic migration.** Unnecessary this phase; method is derived.
- **Catching bare `Exception` around the savepoint.** Catch `sqlalchemy.exc.IntegrityError` specifically so unrelated errors still surface (the project's no-wave-off rule).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Concurrency control on alias insert | Custom lock table / in-process mutex / retry-with-sleep | The existing UNIQUE constraint + `IntegrityError` catch | The DB already enforces atomicity across all 4 workers; a hand-rolled lock cannot span processes correctly and is untestable on SQLite (D-01/D-02). |
| Verification state machine | A third-party FSM library / a stateful `VerificationService` class | Flat functions + a module-level `frozenset` transition table | ~4 states; matches `disc_identity.py`/`sync.py` house style; introduces no new OOP-service or dependency (D-08). |
| Partial-rollback on multi-alias submit | Manual "delete what I inserted" cleanup | `db.begin_nested()` SAVEPOINT per insert | SQLAlchemy's savepoint gives exact, tested rollback scope (D-03). |
| Golden-record drift detection | JSON snapshot file + snapshot lib | Hardcoded expected dict inside the test | Snapshot files invite "just re-approve" that swallows the regression IDENT-05 exists to catch (D-13/D-14). |

**Key insight:** Every gap in this phase already has an in-tree, boring solution — the DB constraint, the flat-function domain-module convention, SQLAlchemy savepoints, and the existing fixture/CI harness. Introducing any library here would be a net loss.

## Runtime State Inventory

> Rename/hygiene component (CLEAN-01/02). Repo-root + VCS state only — no datastore/OS/secret state is touched by this phase.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified: this phase changes code + response shape + tests only; no data migration, no stored string is renamed. `dvd1-*` values in `discs`/`disc_identity_aliases` are read, never rewritten. | none |
| Live service config | None — verified: no external service (n8n/Datadog/etc.) is in scope; the only "config" is `docker-compose*.yml` gunicorn `-w 4` which is read for context, not changed. | none |
| OS-registered state | None — verified: no scheduler/daemon/unit references any of the target scripts. | none |
| Secrets/env vars | None — verified: no secret key or env var name changes. | none |
| Build artifacts / installed packages | None — the root scripts are not a packaged module; deleting them leaves no stale egg-info. Confirm no test imports them (below). | Verify no imports before delete |
| **VCS-tracked files to remove (CLEAN-01)** | Present AND git-tracked: `fix_test.py` (1.4K), `fix_test2.py` (338B), `test_script.py` (29B), `verify_t11.py` (1.2K) | `git rm` the four; relocate `run_uat.py` (5.8K) + `create_uat_dirs.py` (3.8K) under `scripts/` per D-18 (confirm still-used first) |
| **VCS-tracked artifacts to untrack (CLEAN-02)** | `uat_results.json` (1.8K) + entire `uat_dirs/` tree (20 tracked BDMV/VIDEO_TS fixture files) are **currently git-tracked** | `.gitignore` entries + `git rm --cached uat_results.json` and `git rm -r --cached uat_dirs/` (they are tracked — a plain `.gitignore` will NOT untrack them) |

**Import-safety check for the planner to run before deleting** (must be empty):
```bash
grep -rn "import fix_test\|import fix_test2\|import test_script\|import verify_t11\|from fix_test\|from test_script\|from verify_t11" . --include=*.py
```
CONTEXT.md CONCERNS.md states the scripts' edits are already applied, so they are one-shot cruft — but confirm no residual import before `git rm` (no-wave-off rule).

**`.gitignore` additions (CLEAN-02):**
```gitignore
uat_results.json
uat_dirs/
```

## Common Pitfalls

### Pitfall 1: SQLite test harness cannot reproduce a real thread race
**What goes wrong:** The IDENT-02 test tries to spin up concurrent requests and finds they all serialize.
**Why it happens:** `conftest.py` uses a single in-memory SQLite connection via `StaticPool` + `check_same_thread=False` (`conftest.py:56-60`); the `TestClient` drives requests synchronously. There is no true parallelism to race.
**How to avoid:** Test the **catch-and-re-resolve path deterministically**, not actual concurrency. Construct the losing-race state and assert convergence: e.g. (a) pre-insert the conflicting alias/disc row via `db_session` before driving the endpoint, or (b) monkeypatch `resolve_disc_identity` to return `None` on the first call (simulating a stale read) while the row already exists, then assert the endpoint catches `IntegrityError`, converges to a single disc (no duplicate/split), and returns the correct status. This matches the project's deterministic-injection philosophy (CLAUDE.md: inject the failure deterministically, restore in `finally` — override the symbol rather than rely on timing).
**Warning signs:** A test that calls `threading`/`asyncio.gather` and passes trivially — it proved nothing.

### Pitfall 2: SAVEPOINT rollback leaves stale ORM identity-map state
**What goes wrong:** After catching `IntegrityError`, `resolve_disc_identity` returns a cached/stale object or the session errors on the next flush.
**Why it happens:** A rolled-back savepoint invalidates pending objects; the Session's identity map may still hold the failed insert.
**How to avoid:** After the `except IntegrityError`, call `db.expire_all()` (or expire the specific object) before re-resolving, and perform the re-resolve as a fresh query. Ensure the `begin_nested()` block `flush()`es so the `IntegrityError` is raised **inside** the savepoint scope (not deferred to the outer commit).
**Warning signs:** `InvalidRequestError` / `PendingRollbackError` on the subsequent operation; the re-resolve returning the object you just failed to insert.

### Pitfall 3: VERIFY-02 guard breaks two existing "verified→disputed" tests (behavior change)
**What goes wrong:** After adding the `flag_dispute` guard (refuse to dispute a verified disc), `test_submit_duplicate_fingerprint_conflicting_metadata` (`test_disc_submit.py:115`) and `test_duplicate_conflicting_metadata_disputes` (`test_disc_submit.py:198`) fail — they seed a **verified** disc (`seed_test_disc` sets `status="verified"`, `conftest.py:154`) and assert a mismatched second submission returns `status="disputed"`.
**Why it happens:** Those tests encode the exact silent-flip the phase forbids. This is an intended behavior change, not drift.
**How to avoid:** The plan MUST include a task to update both tests: seed the disc as `unverified` to keep exercising the legitimate `unverified → disputed` path, AND add a new test asserting a genuinely **verified** disc stays `verified` (returns e.g. 200 with an unchanged/"already verified" or a distinct "cannot dispute verified" response) when a mismatched submission arrives. Also re-check `test_dispute.py::test_submit_stores_conflict_data` (`test_dispute.py:81`) which uses `seeded_disc_with_owner` (also verified) and asserts a `disputed` DiscEdit — same update needed. Decide the response contract for "mismatched submission against a verified disc" explicitly (recommended: keep it `verified`, record an audit `DiscEdit`, return 200 with a clear message — never 5xx).
**Warning signs:** Treating this as "no behavior drift" and leaving the tests asserting `disputed` — that would re-lock the bug.

### Pitfall 4: Collapsing `verified→verified` semantics loses the idempotent no-edit contract
**What goes wrong:** Consolidating verification makes an already-verified disc create a spurious `DiscEdit` or return the wrong message.
**Why it happens:** Two entry paths share the logical `verified→verified` transition but have different contracts: the `verify_disc` endpoint returns 200 `"already verified"` with **no** DiscEdit (`test_disc_verify.py:71,82`), while the submit auto-verify path returns `"auto-verified"` **with** an edit. The reconciliation flagged in CONTEXT.md's D-12 research-note is **resolved**: the live `test_disc_verify.py` contains NO `test_verified_to_verified_returns_400` — the authoritative behavior is **idempotent 200, no edit**. Do NOT introduce a 400 for verified→verify.
**How to avoid:** Make `verify()` return a bool (transition occurred?); callers create the `DiscEdit` and choose the message only when it returns `True`. Preserve `test_verify_already_verified_idempotent` and `test_verify_already_verified_no_extra_edit`.
**Warning signs:** `test_verify_already_verified_no_extra_edit` failing with `len(edits) == 1`.

### Pitfall 5: `git rm --cached` forgotten for already-tracked UAT artifacts
**What goes wrong:** Adding `uat_results.json`/`uat_dirs/` to `.gitignore` appears to satisfy CLEAN-02 but the files remain tracked and keep showing in `git status`/commits.
**Why it happens:** `.gitignore` only affects **untracked** files; these are already tracked (22 paths confirmed via `git ls-files`).
**How to avoid:** `git rm --cached uat_results.json && git rm -r --cached uat_dirs/` in the same change as the `.gitignore` edit. Success criterion #5 requires them gitignored (untracked), not merely ignored-in-name.
**Warning signs:** `git ls-files | grep uat_` still returns rows after the change.

## Code Examples

### Wrapping the disc-row insert in `submit_disc` (IDENT-02)
```python
# routes/disc.py submit_disc — the new-disc branch (~line 480), race-safe
try:
    with db.begin_nested():
        disc = Disc(fingerprint=body.fingerprint, format=body.format, status="unverified",
                    submitted_by=current_user.id, ...)
        db.add(disc); db.flush()          # raises IntegrityError here if another worker won
except IntegrityError:
    db.expire_all()
    winner = resolve_existing_disc_for_identities(db, body.fingerprint, body.fingerprint_aliases)
    # fall through to the existing "duplicate submission" branch (auto-verify / conflict)
    ...
```

### Route-boundary translation of `VerificationTransitionError` (VERIFY-02, mirrors `DiscIdentityConflict`)
```python
# routes/disc.py verify_disc
try:
    transitioned = verify(db, disc, current_user)
except VerificationTransitionError as exc:
    if exc.attempted_status == "verified" and str(disc.submitted_by) == str(current_user.id):
        return _error_response(request_id, "forbidden", "Cannot verify your own submission", 403)
    return _error_response(request_id, "invalid_state", str(exc), 409)
if not transitioned:                       # already verified → idempotent, no DiscEdit
    return JSONResponse(200, {"request_id": request_id, "fingerprint": disc.fingerprint,
                              "status": "verified", "message": "already verified"})
db.add(DiscEdit(disc_id=disc.id, user_id=current_user.id, edit_type="verify"))
disc.seq_num = next_seq(db); db.commit()
```

## State of the Art

| Old Approach (current code) | Current Approach (this phase) | When Changed | Impact |
|-----------------------------|-------------------------------|--------------|--------|
| `resolve_disc_identity` → `db.add()` (TOCTOU) | insert-first / catch `IntegrityError` / re-resolve in `begin_nested()` | Phase 1 | No duplicate/split pressings under 4 workers |
| 5 inline `disc.status = …` mutations | one `verification.py` service; `flag_dispute` sole `disputed` writer | Phase 1 | Silent-flip closed; grep-able chokepoint |
| Verified disc silently → disputed on mismatch | Verified disc stays verified; only `unverified → disputed` | Phase 1 | **Behavior change** — updates 2-3 existing tests |
| `DiscLookupResponse.fingerprint` only | + additive `fingerprint_aliases` object array | Phase 1 | Consumers opt in; survives Phase 5 |

**Deprecated/outdated:** nothing removed from the public contract (strictly additive, D-07). The four root debug scripts are removed as dead cruft.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `method` label for IDENT-01 aliases is derived from the fingerprint prefix (`fp.split("-",1)[0]`), not stored | Pattern 4 | Low — D-04 only requires *a* method string; planner may choose a richer mapping (`"dvd1"→"OVID-DVD-1"`). No migration either way. |
| A2 | The correct contract for "mismatched submission against an already-verified disc" is: stay `verified`, record an audit `DiscEdit`, return 200 | Pitfall 3 | Medium — this is a product decision. Confirm with discuss-phase/planner; alternative is a distinct 409 "cannot dispute verified". Both satisfy criterion #4. |
| A3 | `run_uat.py` / `create_uat_dirs.py` are still-useful and should be relocated (not deleted) per D-18 | Runtime State Inventory | Low — D-18 explicitly leaves final disposition to the planner after obsolescence check. |
| A4 | `db.begin_nested()` SAVEPOINT behaves identically enough on the SQLite `StaticPool`/WAL harness to exercise the `IntegrityError` path | Pattern 1 / Pitfall 2 | Low — SQLite supports SAVEPOINT and raises `IntegrityError` on UNIQUE violation; WAL is enabled (`conftest.py:48`). Verify empirically in the first test. |

## Open Questions (RESOLVED)

1. **Response contract for a mismatched submission against a verified disc (A2).**
   - What we know: criterion #4 forbids the silent flip; `flag_dispute` must refuse verified discs.
   - What's unclear: exact HTTP status/message and whether to still record a `DiscEdit`.
   - Recommendation: keep `verified`, add an audit `DiscEdit`, return 200 with an explicit message; encode in a new test. Confirm at plan time.
   - **RESOLVED:** stays `verified`, records an audit `DiscEdit`, returns 200 (see Plan 03).

2. **Should `list_disputed_discs` / `lookup_disc_by_upc` also eager-load `identity_aliases`?**
   - What we know: they share `_disc_to_response`, so they gain the field automatically; without a loader they lazy-load per disc.
   - What's unclear: whether the extra per-disc query matters for the disputed/UPC list sizes.
   - Recommendation: add `selectinload(Disc.identity_aliases)` to all three query sites for consistency and to avoid N+1 under the p95 ≤ 500ms budget.
   - **RESOLVED:** `selectinload` added at all 3 read sites (see Plan 04).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all API code/tests | ✓ (CI 3.12) | 3.12 | — |
| SQLAlchemy | savepoints, IntegrityError | ✓ | `>=2.0,<3.0` | — |
| pytest + httpx | tests | ✓ (CI-installed) | — | — |
| PostgreSQL 16 | prod runtime (race target) | n/a for unit tests (SQLite harness) | 16 | SQLite reproduces `IntegrityError` for tests |
| git | CLEAN-01/02 | ✓ | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — the phase is fully exercisable on the existing SQLite test harness (D-02).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (API), in-memory SQLite via FastAPI `TestClient` |
| Config file | none in `api/` (no `pytest.ini`/`[tool.pytest]`); fixtures in `api/tests/conftest.py` |
| Quick run command | `cd api && python -m pytest tests/test_disc_identity_aliases.py tests/test_disc_verify.py tests/test_disc_submit.py -x` |
| Full suite command | `cd api && python -m pytest tests/ -v --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDENT-02 | Losing-race insert catches IntegrityError, converges to one disc (no split) | unit (deterministic race sim) | `pytest tests/test_disc_identity_race.py -x` | ❌ Wave 0 |
| IDENT-02 | Second alias insert in same submission survives sibling conflict (savepoint scope) | unit | `pytest tests/test_disc_identity_race.py -x` | ❌ Wave 0 |
| IDENT-01 | `GET /v1/disc/{fp}` returns `fingerprint_aliases` (primary first, is_primary flags, insertion order) | integration | `pytest tests/test_disc_lookup.py -x` (extend) | ⚠ extend existing |
| IDENT-01 | Existing lookup keys unchanged (additive) | integration | `pytest tests/test_disc_lookup.py tests/test_disc_identity_aliases.py -x` | ✅ (must stay green) |
| VERIFY-02 | All status writes go through `verification.py`; single `disputed` writer | unit | `pytest tests/test_verification.py -x` | ❌ Wave 0 |
| VERIFY-02 | Verified disc NOT flipped to disputed by mismatched submission | integration | `pytest tests/test_disc_submit.py -x` (update 115,198 + add) | ⚠ update existing |
| VERIFY-02 | verified→verify idempotent 200, no extra DiscEdit; self-verify 403 | integration | `pytest tests/test_disc_verify.py -x` | ✅ (must stay green) |
| IDENT-05 | Golden `dvd1-*` resolves with frozen structure via GET | integration | `pytest tests/test_disc_identity_regression.py -x` | ❌ Wave 0 |
| CLEAN-01/02 | Root scripts gone; UAT artifacts untracked | manual/VCS | `git ls-files \| grep -E 'fix_test\|test_script\|verify_t11\|uat_'` returns empty | manual |

### Sampling Rate
- **Per task commit:** the relevant focused file(s) above with `-x`.
- **Per wave merge:** `cd api && python -m pytest tests/ -v` (full API suite — must be green; VERIFY-02 changes ripple into `test_disc_submit.py`/`test_dispute.py`).
- **Phase gate:** full API suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `api/tests/test_disc_identity_race.py` — covers IDENT-02 (deterministic losing-race sim + savepoint sibling-survival)
- [ ] `api/tests/test_verification.py` — covers VERIFY-02 transition table, `flag_dispute` guard, self-verify invariant
- [ ] `api/tests/test_disc_identity_regression.py` — covers IDENT-05 golden `dvd1-*`
- [ ] Update `api/tests/test_disc_submit.py` (lines 115, 198) and `api/tests/test_dispute.py` (line 81) for the guarded dispute behavior
- [ ] Extend `api/tests/test_disc_lookup.py` for the `fingerprint_aliases` shape
- Framework install: none (harness exists)

## Security Domain

> `security_enforcement` assumed enabled (not set `false` in config). This phase is primarily a data-integrity/access-control hardening.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Single guarded verification module (`verification.py`) as the sole state-transition authority (VERIFY-02) |
| V4 Access Control | yes | "Cannot verify own submission" invariant moved into `verify()` (D-11) so no caller bypasses it; coarse role check stays at route |
| V5 Input Validation | yes (existing) | Pydantic v2 request models unchanged; new response model is output-only |
| V11 Business Logic | yes | State-machine integrity: verified discs cannot be silently downgraded to disputed (criterion #4) — a business-logic integrity control |
| V6 Cryptography | no | none in scope |
| V2 Authentication | no (Phase 6) | — |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Concurrent double-submit creating split/duplicate pressings | Tampering / DoS-of-data-quality | DB UNIQUE constraint + catch-`IntegrityError` convergence (IDENT-02) |
| Silent status downgrade of a verified disc via crafted mismatched submission | Tampering / Repudiation | `flag_dispute` refuses verified discs; `disputed` reachable only via explicit resolve path (VERIFY-02) |
| Self-verification to fake a second contributor | Elevation / Repudiation | Self-verify invariant inside `verify()` (D-11); full two-contributor enforcement is Phase 2 |
| Data drift silently corrupting `dvd1-*` resolution during migration | Tampering | Permanent frozen-structure regression test (IDENT-05) |

## Sources

### Primary (HIGH confidence — live tree, verified this session)
- `api/app/disc_identity.py` — `attach_lookup_aliases` check-then-add race (lines 115-128); `DiscIdentityConflict` raise-and-catch template
- `api/app/routes/disc.py` — 5 inline status mutations (241,245,422,444,616); submission call sites; `_disc_to_response` (123); lookup eager-load (277-284)
- `api/app/models.py` — `Disc.fingerprint`/`DiscIdentityAlias.fingerprint` `unique=True` (70,137); `identity_aliases` relationship with no `order_by` (109)
- `api/app/schemas.py` — `DiscLookupResponse` (49); Pydantic v2 conventions
- `api/tests/conftest.py` — SQLite `StaticPool`+WAL harness (42-64); `seed_test_disc` seeds `dvd-ABC123-main`/`status="verified"` (150,154)
- `api/tests/test_disc_verify.py` — idempotent-200 / no-extra-edit contract (71,82); NO `verified→400` test (D-12 note resolved)
- `api/tests/test_disc_submit.py` — verified-disc→disputed tests that VERIFY-02 will change (115,198)
- `api/tests/test_dispute.py` — `test_submit_stores_conflict_data` also on a verified seed (81)
- `api/tests/test_disc_identity_aliases.py` — lookup-by-alias-returns-primary pattern IDENT-05 mirrors (106-108)
- `api/alembic/versions/7ffb31fc807f_initial_schema.py` — `UniqueConstraint('fingerprint')` on discs (91)
- `api/alembic/versions/900000000003_add_disc_identity_aliases.py` — `UniqueConstraint('fingerprint')` on aliases (33)
- `.github/workflows/ci.yml` — full `pytest tests/` on every push/PR to main+develop, no marker exclusions
- `docker-compose.prod.yml:34` / `docker-compose.test.yml:33` — `gunicorn -w 4` (the 4-worker race target)
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` — why `dvd1-*` must stay resolvable; staged migration
- `git ls-files` / `ls` — confirmed all 7 root scripts + `uat_results.json` + 20 `uat_dirs/` files are tracked

### Secondary (MEDIUM confidence — official docs)
- SQLAlchemy 2.x savepoints (`Session.begin_nested`) — docs.sqlalchemy.org/en/20/orm/session_transaction.html#using-savepoint
- SQLAlchemy 2.x Postgres `insert().on_conflict_do_nothing` (context for why the dialect-neutral catch form was chosen) — docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert

### Tertiary (LOW confidence)
- None — all load-bearing claims verified against the tree.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all versions read from `api/requirements.txt`.
- IDENT-02 mechanism: HIGH — constraints confirmed live in both migrations + models; SQLite `IntegrityError` parity is well-established.
- VERIFY-02 mechanism + behavior-change conflict: HIGH — all five mutation sites and the conflicting tests read directly.
- IDENT-01 shape: HIGH — relationship + serializer + consumer interface all located; ordering gap confirmed.
- IDENT-05 CI guarantee: HIGH — CI workflow read; no marker config in `api/`.
- CLEAN-01/02: HIGH — tracked state confirmed via `git ls-files`.
- Open questions A2 (verified-mismatch contract): MEDIUM — product decision pending.

**Research date:** 2026-07-05
**Valid until:** 2026-08-04 (stable — in-house code, no fast-moving external deps)
