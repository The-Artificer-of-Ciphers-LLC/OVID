---
phase: 01-alias-layer-hardening-repo-hygiene
reviewed: 2026-07-05T00:00:00Z
depth: deep
files_reviewed: 13
files_reviewed_list:
  - api/app/verification.py
  - api/app/disc_identity.py
  - api/app/routes/disc.py
  - api/app/schemas.py
  - api/app/models.py
  - web/lib/api.ts
  - api/tests/conftest.py
  - api/tests/test_verification.py
  - api/tests/test_disc_identity_race.py
  - api/tests/test_disc_identity_regression.py
  - api/tests/test_disc_submit.py
  - api/tests/test_dispute.py
  - api/tests/test_disc_lookup.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-07-05T00:00:00Z
**Depth:** deep
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Reviewed the disc-identity/alias hardening (IDENT-02), the guarded verification
state machine (VERIFY-02), and the additive `fingerprint_aliases` response
contract, tracing call chains across `disc_identity.py` → `routes/disc.py` →
`verification.py` and their respective test files.

The `register_disc` SAVEPOINT+retry pattern is correctly scoped and matches
the documented design: the disc-row insert is the *only* statement inside
`db.begin_nested()`, so a losing race auto-rolls-back cleanly via
SQLAlchemy's nested-transaction semantics, and the `IntegrityError` recovery
path (`db.expire_all()` + re-resolve) is sound. `attach_lookup_aliases`'s
per-alias SAVEPOINT is also correctly scoped, and the race/regression tests
for it are deterministic (no threading/sleep) and exercise genuine collision
states via monkeypatching, restored in `finally`, per house style. The
`fingerprint_aliases` additive contract (primary-first, insertion order via
`selectinload` + the relationship's `order_by`) is implemented correctly and
is N+1-safe everywhere `_disc_to_response` is called.

However, `submit_disc` copies the SAVEPOINT+retry *pattern* but not its
*scope*: the `except IntegrityError` at the function level wraps far more
code than the actual SAVEPOINT block, including the titles/tracks insert
loop that runs completely unprotected. On PostgreSQL this turns any
unrelated constraint violation (e.g. duplicate `title_index`) into an
unhandled 500 that breaks the project's standard JSON error envelope,
because the recovery code assumes it is always dealing with a
savepoint-scoped failure — it is not. There is also a real (if narrow)
ordering bug in `verify()`'s self-submission guard, and a same-table only
uniqueness arbitration gap when a fingerprint races between the "new
primary" and "attach as alias to existing disc" code paths.

## Critical Issues

### CR-01: `submit_disc`'s `except IntegrityError` scope extends past the SAVEPOINT, breaking recovery and the error envelope on PostgreSQL

**File:** `api/app/routes/disc.py:607-731`

**Issue:**
The single `try:` at line 607 wraps the SAVEPOINT-scoped release/disc insert
(`with db.begin_nested(): ...`, lines 613-640) *and* everything after it up
through `db.commit()` (line 701) — including `attach_lookup_aliases` (642),
the raw `DiscRelease` link insert (645-649), and the per-title/per-track
insert loop (652-685), each of which calls `db.flush()` outside any
savepoint. The `except IntegrityError:` handler at line 712 is written on
the assumption that *any* `IntegrityError` caught here means "another
worker won the disc-fingerprint race inside the savepoint we just took",
and reacts by calling `db.expire_all()` (718) and re-querying via
`resolve_existing_disc_for_identities` (720-722) — with **no
`db.rollback()`** anywhere in this handler.

That reaction is correct only for the genuine case (an `IntegrityError`
raised *inside* `with db.begin_nested()`), because SQLAlchemy auto-rolls-back
just that savepoint when an exception propagates out of the `with` block,
leaving the outer transaction healthy. It is wrong for any `IntegrityError`
raised by the unprotected code that runs after that block:

- `db.query(DiscTitle)`'s unique constraint `uq_disc_titles_index`
  (`disc_id`, `title_index`) is not validated by `DiscSubmitRequest` /
  `TitleCreate` in `schemas.py` — nothing stops a client (or a buggy ARM
  pipeline) from POSTing two `titles` entries with the same
  `title_index`. The second `db.flush()` in the loop (line 663) then
  raises `IntegrityError` **outside any savepoint**.
- On PostgreSQL, that failure aborts the entire outer transaction at the
  connection level ("current transaction is aborted, commands ignored
  until end of transaction block"). `db.expire_all()` does not clear that
  state. The very next statement — the `SELECT`s inside
  `resolve_existing_disc_for_identities` (720-722) — immediately raises a
  *different* exception (`sqlalchemy.exc.InternalError` /
  `psycopg2.errors.InFailedSqlTransaction`), which is **not**
  `IntegrityError` and is **not** `DiscIdentityConflict`.
- Because that new exception is raised from *inside* the `except
  IntegrityError:` handler (not from the guarded `try` body), Python does
  not route it to the sibling `except DiscIdentityConflict` (732) or
  `except Exception:` (735) clauses of the same `try` statement — it
  propagates straight out of `submit_disc` as an unhandled exception,
  producing a raw FastAPI 500 that bypasses `_error_response`'s
  `{request_id, error, message}` envelope entirely (violating the
  project's stated error-envelope convention), and masking the real,
  client-fixable problem (duplicate `title_index`) behind a confusing
  crash.

This is untested because the in-memory SQLite harness does not abort the
whole transaction on a single failed statement the way PostgreSQL does, so
`api/tests/test_disc_submit.py` cannot surface it — this is exactly the
class of PostgreSQL-only failure mode the project's own cross-platform
testing conventions warn about hiding.

**Fix:** Narrow the SAVEPOINT-recovery `except IntegrityError` to only wrap
the disc/release insert, mirroring `register_disc`'s correctly-scoped
pattern, and let genuinely later failures (titles/tracks/link-table) fall
through to the existing `except Exception:` handler (which already calls
`db.rollback()` and returns the proper `internal_error` envelope):

```python
try:
    with db.begin_nested():
        release = Release(...)
        db.add(release)
        db.flush()
        disc = Disc(...)
        db.add(disc)
        db.flush()
except IntegrityError:
    db.expire_all()
    try:
        winner_resolution = resolve_existing_disc_for_identities(
            db, body.fingerprint, body.fingerprint_aliases
        )
    except DiscIdentityConflict as exc:
        return _identity_conflict_response(request_id, exc.fingerprint)
    if winner_resolution is None:
        raise
    return _handle_existing_disc(
        db, winner_resolution.disc, body, current_user, request_id
    )

try:
    attach_lookup_aliases(db, disc, body.fingerprint, body.fingerprint_aliases)
    db.execute(DiscRelease.__table__.insert().values(disc_id=disc.id, release_id=release.id))
    for tc in body.titles:
        ...
    seq = next_seq(db)
    ...
    db.commit()
    return DiscSubmitResponse(...)
except DiscIdentityConflict as exc:
    db.rollback()
    return _identity_conflict_response(request_id, exc.fingerprint)
except Exception:
    db.rollback()
    logger.exception("disc_submit_failed fingerprint=%s", body.fingerprint)
    return _error_response(request_id, "internal_error", "Failed to submit disc", 500)
```
Additionally consider adding a `title_index` uniqueness check in
`DiscSubmitRequest` validation so this fails as a clean 422 rather than a
DB constraint violation at all.

## Warnings

### WR-01: `verify()`'s self-submission guard fires before the idempotency check, turning a no-op into a spurious 403

**File:** `api/app/verification.py:46-53`, `api/app/routes/disc.py:767-774`

**Issue:** `verify()` checks self-submission unconditionally, before
checking whether the disc is already verified:

```python
def verify(db: Session, disc: Disc, actor: User) -> bool:
    if disc.submitted_by is not None and str(disc.submitted_by) == str(actor.id):
        raise VerificationTransitionError(disc.id, disc.status, "verified")

    if disc.status == "verified":
        return False
    ...
```

Scenario: contributor A submits a disc (`submitted_by = A`, `status =
unverified`). Contributor B later submits matching metadata and the disc
auto-verifies (`status = verified`) via `_handle_existing_disc` /
`verify()`. If A subsequently calls `POST /v1/disc/{fp}/verify` (e.g. the
UI still shows a "verify" affordance, or A calls the endpoint idempotently
a second time), `verify()` raises `VerificationTransitionError` from the
self-submission branch — **before** ever reaching the `disc.status ==
"verified"` idempotency check — and `verify_disc` in `routes/disc.py` maps
that to `403 forbidden "Cannot verify your own submission"` instead of the
expected idempotent `200 "already verified"` response every other caller
gets for the same state. The error message is also misleading: A isn't
attempting to verify their own *pending* submission, the disc is already
verified by someone else.

`test_verification.py::TestVerify` only exercises
`test_verify_self_submission_raises` against an `"unverified"` disc — the
`status == "verified"` + self-submitted combination is untested, so this
regression path has no coverage.

**Fix:** Check idempotency first:
```python
def verify(db: Session, disc: Disc, actor: User) -> bool:
    if disc.status == "verified":
        return False
    if disc.submitted_by is not None and str(disc.submitted_by) == str(actor.id):
        raise VerificationTransitionError(disc.id, disc.status, "verified")
    if (disc.status, "verified") not in LEGAL_TRANSITIONS:
        raise VerificationTransitionError(disc.id, disc.status, "verified")
    disc.status = "verified"
    disc.verified_by = actor.id
    return True
```
Add a test asserting `verify()` on an already-verified, self-submitted disc
returns `False` (not an exception).

### WR-02: Fingerprint uniqueness is only arbitrated within a single table — a "new disc" vs. "alias of an existing disc" race is unguarded

**File:** `api/app/disc_identity.py:32-160`, `api/app/routes/disc.py:524-731`

**Issue:** `discs.fingerprint` (models.py:70-72) and
`disc_identity_aliases.fingerprint` (models.py:139-141) each carry their own
independent `UNIQUE` constraint, but there is no constraint spanning both
tables. `resolve_disc_identity` (disc_identity.py:50-88) checks `Disc.fingerprint`
first, falling back to `DiscIdentityAlias` — so it always resolves
deterministically once both rows exist — but nothing stops both rows from
being *created* concurrently for the same fingerprint string in the first
place:

- Worker 1 (submitting fingerprint `F` as a brand-new disc, via
  `submit_disc`/`register_disc`) runs its pre-flight
  `resolve_existing_disc_for_identities` and finds nothing for `F`.
- Worker 2 (submitting a different fingerprint that resolves to an
  *existing* disc `D`, with `F` listed in `fingerprint_aliases`) also runs
  its pre-flight check concurrently and also finds nothing pre-existing
  for `F`.
- Both proceed: Worker 1 inserts `Disc.fingerprint = F` (own table, own
  UNIQUE constraint, succeeds). Worker 2's `attach_lookup_aliases` inserts
  `DiscIdentityAlias.fingerprint = F` pointed at disc `D` (a *different*
  table, a *different* UNIQUE constraint — also succeeds, since neither
  constraint knows about the other table).

The SAVEPOINT+UNIQUE convergence dance documented throughout
`disc_identity.py` only arbitrates races *within* one table (two workers
racing to insert into `discs`, or two workers racing to insert into
`disc_identity_aliases`) — this is exactly what the deterministic tests in
`test_disc_identity_race.py` exercise and what they prove works. A race
*between* the two tables for the identical fingerprint string is not
covered by either constraint or by any test, and produces a silent split:
`F` permanently resolves to disc `X` (primary lookup always wins), while
`disc_identity_aliases` retains a dead row claiming `F` belongs to disc
`D` — the exact "split/duplicate pressing" outcome IDENT-02 was written to
prevent, just via the untouched cross-table path.

**Fix:** Either (a) have `attach_lookup_aliases` re-check
`Disc.fingerprint == alias` for a collision inside the same savepoint
before/after the alias insert (so a colliding primary created concurrently
is caught), or (b) enforce this at the DB layer with a
`CHECK`/trigger-backed exclusion, or (c) at minimum add a regression test
documenting the current behavior so a future contributor doesn't assume
the existing race tests cover this path too.

### WR-03: Same-submitter 409 guard and the dispute path don't account for `pending_identification` registrations

**File:** `api/app/routes/disc.py:121-158` (`_handle_existing_disc`), `api/app/verification.py:60-70` (`flag_dispute`)

**Issue:** `register_disc`'s documented workflow (schemas.py:149-155,
routes/disc.py:499-503) is: an ARM-style client registers a bare disc
(`status="pending_identification"`, `submitted_by=<that account>`, no
`Release` attached), and "a human must later attach release metadata via
the web UI, CLI, or `POST /v1/disc`." But `_handle_existing_disc` decides
between the "same user" 409 and the auto-verify/dispute branches purely on
`existing.submitted_by == current_user.id`, with no awareness of
`existing.status`. If the *same account* that ran `register_disc` later
calls `submit_disc` with the full metadata (a very plausible single-user /
self-hosted setup, or the same ARM service account performing both
steps), it hits the "same user" branch (line 151) and gets a bare `409
"Disc already submitted by this user"` — the documented follow-up
workflow is blocked for that account.

Separately, if a *different* user is the one attaching the first real
metadata to a `pending_identification` disc, `_releases_match` (101-118)
unconditionally returns `False` when the disc has no linked `Release` at
all (line 111-112, `existing_release is None`), so the first metadata
attachment for any ARM-registered disc always takes the `flag_dispute`
path (`disputed`) instead of being treated as an initial identification —
`flag_dispute` doesn't distinguish "genuinely conflicting second opinion"
from "first metadata ever attached to a bare registration."

**Fix:** In `_handle_existing_disc`, special-case
`existing.status == "pending_identification"` (no release yet) as an
"attach initial metadata" flow distinct from both the same-user-conflict
and the dispute paths, regardless of which account performed the
`register_disc` call.

## Info

### IN-01: Unused parameters in `app.verification`'s transition functions

**File:** `api/app/verification.py:39,60,73`

**Issue:** `verify(db, disc, actor)` never uses `db`; `flag_dispute(db, disc,
actor, reason)` never uses `db`, `actor`, or `reason`; `resolve_dispute(db,
disc, actor, action)` never uses `db`. All mutation happens in-memory on
`disc`, committed later by the caller. This may be a deliberate
"reserved for future audit logging inside the module" signature, but as
written it's dead parameter surface that static analysis / linting would
flag, and a reader has to check call sites to know `reason` is silently
discarded rather than persisted anywhere.

**Fix:** Either use `db`/`reason` (e.g. write the audit `DiscEdit` here
instead of at each call site, centralizing the "sole writer" guarantee
further), or drop the unused parameters and note in the docstring that the
caller is responsible for persistence/audit.

### IN-02: `_sqlite_uuid_compat`'s docstring doesn't match its implementation

**File:** `api/tests/conftest.py:34-48`

**Issue:** The section banner (34-40) and the function's own docstring
claim this hook exists "to make uuid.UUID <-> str transparent" for SQLite,
but the implementation only sets `PRAGMA journal_mode=WAL` on connect —
there is no UUID conversion code here at all. UUID round-tripping is
actually provided automatically by
`sqlalchemy.dialects.postgresql.UUID(as_uuid=True)`'s own
`bind_processor`/`result_processor`, independent of dialect, so this event
hook does nothing related to its namesake. It's also arguably a no-op in
its own right: `PRAGMA journal_mode=WAL` has no effect on an in-memory
(`sqlite://`) database, which cannot use WAL (no backing file for the
shared-memory WAL log).

**Fix:** Rename the function/remove the misleading comment (e.g.
`_sqlite_connect_tuning`), or delete it if the WAL pragma isn't actually
buying anything for an in-memory `StaticPool` engine — either way, stop
attributing UUID compatibility to code that doesn't provide it, so a
future contributor doesn't remove the *real* UUID handling (the column
type) while "preserving" this hook.

### IN-03: `web/lib/api.ts`'s `DiscSubmitRequest` is missing `fingerprint_aliases`

**File:** `web/lib/api.ts:138-149`

**Issue:** The backend `DiscSubmitRequest` (schemas.py:128-139) and
`DiscRegisterRequest` (schemas.py:149-160) both gained a
`fingerprint_aliases: list[FingerprintString]` field this phase, and the
response-side `FingerprintAlias`/`fingerprint_aliases` was added to the TS
`DiscLookupResponse` (api.ts:85-107) to match. The request-side TS
`DiscSubmitRequest` interface was not updated to expose the same field, so
there is currently no typed way for `web/` to submit lookup aliases through
`submitDisc()`, even though the server accepts them (defaulting to `[]`
when absent, so nothing breaks — it's a contract-completeness gap, not a
runtime bug).

**Fix:** Add `fingerprint_aliases?: string[];` to the TS
`DiscSubmitRequest` interface for parity, once/if the web submission UI is
meant to support it.

---

_Reviewed: 2026-07-05T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
