# Phase 5: ADR 0001 Completion — dvdread1-* Promotion - Research

**Researched:** 2026-07-06
**Domain:** SQLAlchemy/Alembic data migration engineering, cross-table DB arbitration, FastAPI middleware-based write-quiesce, Python client-library identity selection
**Confidence:** HIGH (all findings grounded in direct codebase inspection; the two migration-mechanics claims are additionally cross-checked against official Alembic/SQLAlchemy docs)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Backfill mechanism — Alembic data migration**
Promote existing discs via a **versioned Alembic data migration**, not a standalone script and not lazy promote-on-access.
- Loop **per disc** (not a set-based `UPDATE ... WHERE fingerprint IN (...)`): for each disc that has a `dvdread1-*` alias, in its own explicitly-committed transaction — delete that `disc_identity_aliases` row, set `discs.fingerprint` to the `dvdread1-*` value, and insert the old `dvd1-*` value as a new alias row.
- **Idempotent / re-runnable / resumable:** guard each per-disc write on current state (e.g. `WHERE discs.fingerprint = <old dvd1 value>`) so an already-promoted disc is a safe no-op on re-run or after an interrupted pass.
- Reuse Phase 1's insert-first / catch `IntegrityError` / re-resolve defense so the migration is safe against concurrent `gunicorn -w 4` writers.
- **Rationale:** OVID's permanent self-hosted-mirror model makes deploy-pipeline coupling a *feature* — mirrors already run `alembic upgrade head`. The sync feed (`SyncDiffRecord`) carries only `disc.fingerprint`, **not** alias-table rows, so mirrors cannot learn the dvd1→dvdread1 promotion via sync; each mirror DB must promote locally regardless. Lazy promote-on-access was rejected — untouched long-tail discs would never promote, failing success criterion 2.

**D-02: WR-02 arbitration — shared fingerprint-registry table**
Close the cross-table race with a **new shared fingerprint-registry table** (a single table with a global `UNIQUE(fingerprint)`), into which BOTH the new-disc insert path and `attach_lookup_aliases` register the fingerprint first.
- This collapses the cross-table collision into the **same single-UNIQUE-violation shape** the code already handles: insert → catch `sqlalchemy.exc.IntegrityError` → `expire_all()` → re-resolve → converge. Reuses the exact idiom in `attach_lookup_aliases` (Phase 1 D-01/D-03), rather than introducing a second (pessimistic) arbitration strategy.
- **Dialect-portable:** a plain `UNIQUE` column works on SQLite, so the in-memory pytest TestClient suite exercises the *real* code path (must stay green). This is the decisive reason over the `pg_advisory_xact_lock` option, which has no SQLite equivalent and would leave the exact race this phase must close untested by the existing suite.
- **In-savepoint recheck was rejected as a sole fix** — it does not actually close the race (two independent constraints, no atomic backing); acceptable only as defense-in-depth on top of the registry.
- Requires a one-time migration that creates the registry table and **backfills it from every existing `discs.fingerprint` and `disc_identity_aliases.fingerprint` value**, inside a single migration transaction. Every current and future insert path must register first.

**D-03: Primary selection — Hybrid (server picks at first-insert)**
On a **new-disc** submission, the **server** chooses the primary among the submitted identity strings, preferring `dvdread1-*` when present; the client's declared primary is advisory.
- `Disc.fingerprint` is **immutable on the live write path** once the disc exists. A later submission from any client version (including old clients still sending `dvd1-*` primary) flows through the existing race-safe alias convergence and can only **add/confirm aliases — never demote** `dvdread1-*` back to `dvd1-*`. This is the "zero fragmentation" guarantee under a mixed client fleet (ovid-client upgrades independently via PyPI / ARM).
- A disc where no `dvdread1-*` string is present (libdvdread unavailable at read time) stays `dvd1-*` primary — satisfies success criterion 2's "stays permanently on dvd1-*".
- **Interaction with D-01 (resolved, not a conflict):** immutability governs the *live write path*. The one-time Alembic backfill (D-01) is the **single sanctioned mutation** of an existing `Disc.fingerprint`, run under the D-04 quiesce window — not on the live path.
- Client-authoritative was rejected (first client to touch a disc fixes its method forever → heterogeneous primaries, never converges). Full server re-normalization on every submission was rejected (mutates existing `Disc.fingerprint` on the hot path → collides with D-06 alias ordering + adds races).

**D-04: Cutover posture — write-quiesce via MirrorModeMiddleware**
Run the one-time backfill inside a **brief write-quiesce window**, reusing the existing, already-tested `MirrorModeMiddleware` read-only gate (405 on writes; GET/HEAD/OPTIONS pass through). Flip read-only → run backfill → flip back.
- Eliminates the backfill-vs-live-write race **by construction**, rather than making the first real cutover depend on WR-02 being perfect under live concurrent traffic.
- Near-zero cost given OVID's profile: low write volume (community submissions), reads are the hot path (ARM lookups) and stay up throughout, and the dataset is still small pre-launch. Trivially reversible if the backfill is interrupted mid-run.
- **Future note (not this phase):** once the table is large (post the ≥500-entry seeding phase), fully-online promotion — with the D-02 registry hardened and battle-proven — becomes the better posture for later identity-method migrations.

**D-05: Cutover operability — one-command wrapper + self-hosting runbook**
Ship a single operator entry point (script / make-target) that performs **toggle read-only → `alembic upgrade head` (promotion) → toggle read-write** as one step, plus a `docs/self-hosting.md` section documenting it.
- Directly mitigates the "operator forgets to flip writes back on" failure the research flagged, and gives self-hosted mirror operators a familiar, low-effort runbook (they already understand the mirror-mode toggle).

### Claude's Discretion
- Exact registry-table name/shape, migration file numbering, and the precise sequencing of the two migrations (registry-create+backfill first, then promotion) — planner/researcher to order. Cross-cut flagged below.
- Whether the WR-02 registry insert lives in `disc_identity.py` alongside the existing convergence helpers or a small new module.
- The precise mechanism of the read-only toggle inside the wrapper (env var vs. runtime flag) provided it reuses `MirrorModeMiddleware` semantics.

### Deferred Ideas (OUT OF SCOPE)
- **Fully-online promotion (no write-quiesce)** — deferred to a *future* identity-method migration once the table is large post-seeding and the D-02 registry is battle-proven. Not this phase (D-04).
- **matrix256 pressing-level alias (MATRIX-01)** — spike-first, single-source, unvalidated; deferred to v2 per REQUIREMENTS.md (already tracked in STATE.md deferred items).

None of the above expands this phase's scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IDENT-03 | The client submits all known Disc Identity strings (`dvd1-*`, `dvdread1-*`, BD tiers) on submission so the API can store them as aliases (ADR 0001 Phase 2 complete) | Verified end-to-end for the `ovid-client` CLI DVD path (§ "IDENT-03 Verification"). Found a real gap in the ARM auto-register path (`arm/identify_ovid.py:submit_to_ovid`) — see Common Pitfalls #1 and Open Questions #1. |
| IDENT-04 | `dvdread1-*` (libdvdread Disc ID) is promoted to the primary DVD fingerprint, with `dvd1-*` retained as a resolvable alias (ADR 0001 Phase 3) | D-01 backfill mechanics (§ Code Examples #1), D-03 server-side hybrid selection (§ Code Examples #3), D-04/D-05 cutover mechanism (§ Architecture Patterns, Pattern 3) |
| IDENT-05 [guardrail, carry-forward] | A permanent CI regression test proves an existing `dvd1-*` string still resolves to its disc after every migration step (anti-fragmentation guarantee) | Existing `test_disc_identity_regression.py` (D-16) already asserts identity/structure, not literal top-level fingerprint — confirmed it survives promotion unmodified (§ Common Pitfalls #4). Extend with a promotion-specific case only if the planner wants belt-and-suspenders coverage. |
| WR-02 [carry-forward, user-scoped to this phase] | Cross-table fingerprint arbitration so a "new disc F" vs. "attach F as an alias" race can no longer silently split identity | D-02 registry table mechanics, atomicity proof, and regression-test design (§ Architecture Patterns Pattern 2, § Code Examples #2) |
</phase_requirements>

## Summary

This phase is almost entirely a **data-migration and concurrency-control engineering problem** layered on top of an already-mature, well-tested identity-resolution codebase — it is not a "build new feature" phase. All five locked decisions (D-01 through D-05) are direct, well-scoped extensions of patterns Phase 1 already established (insert-first/IntegrityError/re-resolve convergence, SAVEPOINT-scoped writes, `MirrorModeMiddleware`). The research below confirms every one of those patterns is reusable as-is, identifies the exact 2-3 call sites each decision touches, and surfaces three findings that materially shape the plan: (1) `ovid-client`'s CLI submission path for DVDs **already** wires `_identity_set` end-to-end — IDENT-03 needs verification/tests, not new plumbing, for that path; (2) `arm/identify_ovid.py`'s bare-bones auto-register call sends **only** the primary fingerprint with no aliases at all, which is a genuine, in-scope gap for "the client submits every known Disc Identity string"; (3) the existing `MirrorModeMiddleware` is wired conditionally at **process startup** (not per-request), so any env-var-based toggle requires a full service restart, not merely flipping an in-memory flag — a real operational fact the D-05 runbook must document plainly rather than gloss over.

The two Alembic migrations this phase needs are architecturally very different in shape: the D-02 registry-table migration is a **simple, single-transaction, bulk `INSERT...SELECT`** backfill (no per-row logic needed, because the fingerprint strings involved do not change — only a new table is populated alongside the two that already exist). The D-01 promotion migration is the **complex one**: it must run inside Alembic's per-invocation transaction wrapper while still committing per-disc, which Context7-verified SQLAlchemy 2.0 "commit-as-you-go" semantics (`connection.execute(...); connection.commit()` — the connection auto-begins a new transaction segment on the next `execute()`) make straightforward and idiomatic. Both migrations should extract their core per-row logic into plain, Alembic-independent Python functions so they can be exercised directly by pytest against the in-memory SQLite harness — the project's CI never runs a real `alembic upgrade head` against Postgres, so an Alembic-only implementation would be **entirely untested by CI**.

**Primary recommendation:** Implement D-02 (registry) and D-01 (promotion) as two separate, revision-chained Alembic migrations (registry first) with the per-row promotion logic factored into a testable helper function; wire the registry insert into `attach_lookup_aliases` and the new-disc create branches in `disc_identity.py`/`routes/disc.py` reusing the exact existing SAVEPOINT/IntegrityError idiom (no new exception-handling shape needed); implement D-03 as a small `_select_primary()` helper called only at the two new-disc creation call sites (the existing-disc paths already never reassign `Disc.fingerprint`, so immutability is a **pre-existing invariant**, not new code); and implement D-04/D-05 as an env-var-based restart wrapper (simplest, matches the existing conditional-middleware-wiring exactly, and matches the "near-zero cost" framing in D-04's own rationale) rather than a live runtime-flag refactor of `MirrorModeMiddleware`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fingerprint identity computation (dvd1/dvdread1) | Client (ovid-client library) | — | Already fully implemented in `ovid-client/src/ovid/disc_identity.py`; this phase does not change fingerprinting math, only which computed string is treated as primary |
| Submission payload construction (which strings ride along) | Client (ovid-client library) | — | `build_submit_payload`/`_disc_identity_set` in `submission.py`/`cli.py`; verification/possible ARM fix only, no new plumbing for the CLI DVD path |
| Cross-table fingerprint arbitration (WR-02 registry) | API / Backend | Database / Storage | Registry table is a DB-layer construct but the arbitration decision (insert-first, catch, converge) is application-layer logic in `disc_identity.py`/`routes/disc.py` |
| New-disc primary selection (D-03 hybrid) | API / Backend | — | Server is explicitly authoritative per D-03; lives in the create branch of `submit_disc`/`register_disc` |
| Existing-disc immutability guarantee | API / Backend | — | Already structurally true (no code path reassigns `Disc.fingerprint` post-creation) — this phase must not introduce a violation, not construct the guarantee from scratch |
| One-time promotion backfill | Database / Storage | API / Backend (Alembic runs inside the API container) | Alembic migration; runs against whichever Postgres instance the deployment (canonical, mirror, standalone) owns locally — no cross-instance coordination |
| Write-quiesce cutover mechanism | API / Backend (middleware) | Database / Storage (migration must complete before write-mode is restored) | `MirrorModeMiddleware` already lives at the API tier; the wrapper script orchestrates process restarts + the migration run |
| Self-hosting operator runbook | Documentation | — | `docs/self-hosting.md`; note the audience mismatch flagged in Open Questions #2 |

## Standard Stack

### Core
| Library | Version (as pinned in repo) | Purpose | Why Standard |
|---------|------|---------|--------------|
| SQLAlchemy | `>=2.0,<3.0` [CITED: api/requirements.txt] | ORM + Core `Connection` used for the migration's raw per-row execute/commit loop | Already the project's ORM; SQLAlchemy 2.0's "commit as you go" `Connection.commit()` semantics are exactly what D-01 needs and are officially documented (verified via Context7 below) |
| Alembic | `>=1.13,<2.0` [CITED: api/requirements.txt] | Versioned schema + data migrations | Already the project's migration tool; every existing migration in `api/alembic/versions/` follows this style |
| pytest | `>=7.0` [CITED: api/requirements.txt] | Unit/integration tests for the new registry logic, `_select_primary()`, and promotion-loop function | Existing test framework for both `api/tests/` and `ovid-client/tests/` |

No new third-party packages are introduced by this phase — every capability (SAVEPOINT arbitration, migration commit control, middleware toggling) is achievable with the already-installed SQLAlchemy/Alembic/FastAPI/Starlette stack.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Starlette (via FastAPI dependency) | pinned transitively by `fastapi>=0.110,<1.0` [CITED: api/requirements.txt] | `BaseHTTPMiddleware` base class already used by `MirrorModeMiddleware` | No change needed — reused as-is per D-04 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Env-var + restart cutover toggle (recommended) | DB-backed runtime flag (e.g. new `sync_state` key, checked per-request in an always-mounted middleware) | Avoids any downtime (reads stay up), but adds a DB round-trip to every write-method request permanently, requires refactoring a security-relevant middleware, and is untested/unproven versus the existing exact code path. Revisit post-D-04's own "future note" once the registry/quiesce pattern is battle-proven at scale. |
| Two Alembic migrations, sequenced (recommended) | One combined migration doing both registry-create+backfill and promotion | Combining them couples an always-safe bulk `INSERT...SELECT` (registry) with a per-row, resumable, potentially-slow loop (promotion) in one revision — a failure partway through the combined migration is harder to reason about for resumability than two cleanly-separated revisions. |
| `_select_primary()` server-side helper (recommended) | Flip `identify_dvd()` to prefer dvdread1-as-primary client-side (see Common Pitfalls #1) | Not mutually exclusive — see Open Questions #1 for the recommended combination of both. |

**Installation:** No new packages — no `pip install` step required for this phase's core work.

**Version verification:** SQLAlchemy and Alembic versions above are read directly from `api/requirements.txt` (the pinned range already installed and in use across all prior phases); this phase does not change either pin. No registry lookup was performed since no new packages are introduced — see Package Legitimacy Audit below.

## Package Legitimacy Audit

**Not applicable — this phase introduces zero new external packages.** All work uses SQLAlchemy, Alembic, FastAPI/Starlette, and pytest, all already installed and pinned in `api/requirements.txt`/`ovid-client/pyproject.toml`. The Package Legitimacy Gate protocol is skipped per its own trigger condition ("whenever this phase installs external packages").

**Packages removed due to [SLOP] verdict:** none (N/A — no new packages)
**Packages flagged as suspicious [SUS]:** none (N/A — no new packages)

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────── ovid-client (DVD path) ───────────────────────────────┐
│  Disc.from_path()                                                                     │
│     └─> identify_dvd(path, canonical) ──> DiscIdentitySet(primary=dvd1, aliases=[     │
│              dvdread1 if libdvdread succeeded ])                                      │
│  cli.py: _disc_identity_set(disc) ──> build_submit_payload(structure, meta,           │
│              identity_set) ──> {fingerprint: dvd1-X, fingerprint_aliases: [dvdread1-Y]}│
└───────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ POST /v1/disc  (or /v1/disc/register)
                                         ▼
┌──────────────────────────────── api/app/routes/disc.py ──────────────────────────────┐
│  resolve_existing_disc_for_identities(db, body.fingerprint, body.fingerprint_aliases) │
│     ├─ existing disc found ──> _handle_existing_disc() / _handle_existing_registered  │
│     │      attach_lookup_aliases(existing, existing.fingerprint [IMMUTABLE], …)       │
│     │      (D-03: never reassigns Disc.fingerprint — pre-existing invariant)          │
│     │                                                                                 │
│     └─ no existing disc ──> NEW: _select_primary(body.fingerprint, aliases) [D-03]    │
│              ├─ prefers any "dvdread1-*" candidate                                    │
│              └─ SAVEPOINT: Disc(fingerprint=primary) + NEW: register_fingerprint()     │
│                    [D-02] into fingerprint_registry ── same savepoint, same flush     │
│              IntegrityError on EITHER insert ──> expire_all() ──> re-resolve ──>      │
│                    converge to _handle_existing_disc (existing single-table idiom)    │
└───────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ (existing/new alias attach)
                                         ▼
┌──────────────────────── api/app/disc_identity.py: attach_lookup_aliases ─────────────┐
│  for each alias fingerprint:                                                          │
│     SAVEPOINT: DiscIdentityAlias(disc_id, fingerprint) + NEW: register_fingerprint()  │
│        [D-02] into fingerprint_registry ── same savepoint                            │
│     IntegrityError (from EITHER unique constraint) ──> expire_all() ──> re-resolve    │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────── One-time cutover (D-04/D-05, operator-triggered) ────────────────┐
│  wrapper script:                                                                       │
│    1. read current OVID_MODE (canonical/standalone) from running deployment           │
│    2. restart api service with OVID_MODE=mirror ──> MirrorModeMiddleware now mounted  │
│         (writes 405; GET/HEAD/OPTIONS pass through — reads stay live)                 │
│    3. alembic upgrade head                                                            │
│         rev A (D-02): CREATE TABLE fingerprint_registry; bulk INSERT...SELECT from    │
│              discs.fingerprint AND disc_identity_aliases.fingerprint (single txn)     │
│         rev B (D-01): for each disc WHERE fingerprint = <its own recorded dvd1 value> │
│              AND a dvdread1 alias row exists:                                        │
│                delete alias row; set discs.fingerprint = dvdread1 value;              │
│                insert old dvd1 value as new alias row                                │
│                connection.commit()  ← per-disc commit (SQLAlchemy 2.0 commit-as-you-go)│
│    4. restart api service with the ORIGINAL OVID_MODE (captured in step 1)            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No new top-level directories. New/changed files, following existing conventions:

```
api/
├── alembic/versions/
│   ├── <rev-A>_add_fingerprint_registry.py     # D-02: create + bulk backfill
│   └── <rev-B>_promote_dvdread1_primary.py     # D-01: per-disc promotion loop
├── app/
│   ├── models.py                                # + FingerprintRegistry model
│   ├── disc_identity.py                          # + register_fingerprint() helper,
│   │                                              #   wired into attach_lookup_aliases
│   └── routes/disc.py                            # + _select_primary() helper (D-03),
│                                                   #   wired into submit_disc/register_disc
├── tests/
│   ├── test_fingerprint_registry.py              # WR-02 regression (new)
│   ├── test_disc_identity_race.py                # + cross-table race case (WR-02)
│   ├── test_disc_submit.py                       # + D-03 primary-selection cases
│   └── test_promote_dvdread1_migration.py        # D-01 logic, tested independent of Alembic
scripts/
└── promote_dvdread1.py                            # D-05: one-command cutover wrapper
docs/
└── self-hosting.md                                # + D-05 runbook section
arm/
└── identify_ovid.py                               # possible fix — see Open Questions #1
ovid-client/
└── src/ovid/disc_identity.py                      # possible identify_dvd() flip — Open Questions #1
```

### Pattern 1: D-03 Server-Side Hybrid Primary Selection

**What:** A pure function that inspects the full set of submitted identity strings on a NEW disc and picks the primary, preferring `dvdread1-*`.
**When to use:** Only at the two new-disc creation call sites in `submit_disc` and `register_disc` — never on the existing-disc paths, which are already structurally immutable.
**Verification of the "immutable on existing-disc paths" claim:** a full read of `api/app/routes/disc.py` (all 1113 lines) confirms `existing.fingerprint` is **never assigned** anywhere in `_handle_existing_disc`, `_identify_existing_disc`, or `_handle_existing_registered_disc` — only `existing.submitted_by`, `existing.seq_num`, `existing.status` (via `verify()`/`flag_dispute()`) are mutated. This means D-03's "old client can never demote dvdread1→dvd1" guarantee is **already true of the codebase as it exists today** — this phase's D-03 work is entirely about the *new-disc creation* branch's selection logic, not about adding a new immutability guard.

```python
# api/app/routes/disc.py — new helper, colocated with _method_of()
def _select_primary(fingerprint: str, aliases: list[str]) -> tuple[str, list[str]]:
    """Server-side primary selection for NEW discs only (D-03).

    Prefers any submitted dvdread1-* string as primary; the client's
    declared primary is advisory. Existing-disc paths never call this —
    Disc.fingerprint is immutable once a disc exists (see module docstring
    note above _handle_existing_disc).
    """
    candidates = [fingerprint, *aliases]
    preferred = next(
        (fp for fp in candidates if _method_of(fp) == "dvdread1"), None
    )
    if preferred is None:
        return fingerprint, aliases
    remaining = [fp for fp in candidates if fp != preferred]
    return preferred, remaining
```

Wiring (both `submit_disc` and `register_disc` create branches, only where `Disc(fingerprint=body.fingerprint, ...)` currently appears):

```python
primary_fp, alias_fps = _select_primary(body.fingerprint, body.fingerprint_aliases)
disc = Disc(fingerprint=primary_fp, ...)
db.add(disc)
db.flush()
# attach_lookup_aliases(db, disc, primary_fp, alias_fps) later in the same function
```

### Pattern 2: D-02 Cross-Table Registry Arbitration

**What:** A new `fingerprint_registry` table with a single global `UNIQUE(fingerprint)` column that both write paths insert into, inside the SAME savepoint as their existing table-specific insert, so a cross-table race surfaces as the identical `IntegrityError` shape the code already handles.
**When to use:** Every insert into `discs.fingerprint` (new disc) or `disc_identity_aliases.fingerprint` (new alias) must ALSO insert into this registry, in the same flush/savepoint.
**Why atomicity holds:** a single `db.flush()` inside one `db.begin_nested()` issues all pending `INSERT`s together; if any one violates a UNIQUE constraint, SQLAlchemy raises `IntegrityError` for the whole flush and the SAVEPOINT rolls back **both** pending inserts atomically — order of `db.add()` calls within the savepoint does not matter for this guarantee [VERIFIED: direct read of the existing `attach_lookup_aliases`/`submit_disc` SAVEPOINT pattern already relies on this same flush-atomicity].
**No lookup-path change needed:** `resolve_disc_identity()` continues to check only `Disc.fingerprint` then `DiscIdentityAlias.fingerprint` — the registry is a write-time arbitration backstop only, never queried for reads.

```python
# api/app/models.py — new table
class FingerprintRegistry(Base):
    """Cross-table UNIQUE arbitration for all Disc Identity strings (WR-02).

    Every fingerprint that becomes a Disc.fingerprint OR a
    DiscIdentityAlias.fingerprint is also registered here, in the SAME
    savepoint as that write. A plain UNIQUE constraint on `fingerprint`
    collapses a "new disc" vs. "new alias" cross-table race into the same
    IntegrityError shape the existing SAVEPOINT/re-resolve idiom already
    handles — no new arbitration strategy, no Postgres-only feature (works
    on SQLite, so the pytest TestClient suite exercises the real path).
    """
    __tablename__ = "fingerprint_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fingerprint: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    disc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discs.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    __table_args__ = (
        Index("idx_fingerprint_registry_disc_id", "disc_id"),
    )
```

```python
# api/app/disc_identity.py — new helper, called inside existing savepoints
def register_fingerprint(db: Session, fingerprint: str, disc_id: uuid.UUID) -> None:
    """Register a fingerprint into the cross-table arbitration registry.

    Caller MUST invoke this inside the same db.begin_nested() savepoint as
    the Disc/DiscIdentityAlias insert it accompanies, so both succeed or
    both roll back together (WR-02).
    """
    db.add(FingerprintRegistry(fingerprint=fingerprint, disc_id=disc_id))
```

Wiring inside `attach_lookup_aliases` (only the try block changes):

```python
try:
    with db.begin_nested():
        db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))
        register_fingerprint(db, alias, disc.id)  # NEW — same savepoint
        db.flush()
except IntegrityError:
    ...  # unchanged — same re-resolve/converge logic already handles this
```

Wiring inside `submit_disc`/`register_disc`'s new-disc savepoint (after `db.add(disc); db.flush()` — `disc.id` is a Python-side UUID default, available immediately, no need to wait for a second flush):

```python
with db.begin_nested():
    disc = Disc(fingerprint=primary_fp, ...)
    db.add(disc)
    db.flush()
    register_fingerprint(db, primary_fp, disc.id)  # NEW — same savepoint
    db.flush()
```

### Pattern 3: D-04/D-05 Write-Quiesce Cutover Mechanism

**What matters most here is an operational fact this research surfaced:** `MirrorModeMiddleware` is added to the FastAPI app **conditionally at process/import startup**, not evaluated per-request:

```python
# api/main.py (existing, unchanged)
if os.environ.get("OVID_MODE") == "mirror":
    app.add_middleware(MirrorModeMiddleware)
```

Under `gunicorn -w 4` (prod), each worker is a **separate OS process** that imports `main.py` once at boot. An external `export OVID_MODE=mirror` on the host has **zero effect** on an already-running worker's `os.environ` — flipping this env var requires **restarting every worker process** (i.e. restarting the `api` container/service), not just editing an env file. This is true for both candidate mechanisms the CONTEXT.md discretion note floats:

- **Option A — env var + restart (recommended):** simplest, reuses the exact existing conditional-wiring code path unchanged. Cost: a full service restart brackets the migration **twice**, during which **reads also drop briefly** (not just writes) — a materially larger blast radius than "write-only quiesce" if read on its own. This must be stated plainly in the D-05 runbook rather than implied to be write-only.
- **Option B — DB-backed runtime flag (not recommended for this phase):** refactor `MirrorModeMiddleware` to always mount, checking a per-request flag from a cross-worker-visible store (e.g. a new key in the already-existing `sync_state` table — chosen over Redis because Redis per Phase-3 D-05a is only wired in prod/test compose, not the base compose that Redis-less self-hosted single-worker instances use). Avoids any downtime (reads stay fully live) but adds a DB round-trip to a hot path permanently and requires modifying a security-relevant middleware — higher risk, unproven, and not what D-04's own rationale ("near-zero cost... trivially reversible") was written to justify. Flag as the natural follow-up once the "future note" in D-04 (fully-online promotion) becomes relevant.

**A key simplification found:** `docs/self-hosting.md`'s existing Quick Start already tells self-hosted mirror operators to run permanently with `OVID_MODE=mirror` (see its "How Mirror Mode Works" table: mirror mode = local writes ❌ always) and its existing Step 4 already says `docker compose exec api alembic upgrade head`. **Mirror-mode operators are therefore ALREADY always quiesced** — for them, this phase's D-01/D-02 migrations run as part of their existing, unchanged update routine; no toggle is needed at all. The write-quiesce wrapper (D-04/D-05) is only operationally necessary for **the canonical server** (`oviddb.org`, `OVID_MODE=canonical` per `docker-compose.prod.yml`) and any self-hosted **standalone**-mode instance that accepts local writes. See Open Questions #2 for the resulting doc-placement question.

**Wrapper script requirement:** the script MUST capture the CURRENT `OVID_MODE` value before flipping to `mirror`, and restore that captured value (not a hardcoded default) — otherwise a `canonical`-mode operator's restore step could silently leave the server on the wrong mode, which is the exact "operator forgets to flip writes back on" failure D-05's own rationale names, just relocated into a scripting bug instead of a manual-step omission.

```python
# scripts/promote_dvdread1.py — sketch (D-05), Python for consistency with
# existing scripts/dump_cc0.py convention (CLEAN-01: lives under scripts/,
# not repo root)
import subprocess
import sys

COMPOSE_FILES = ["-f", "docker-compose.yml"]  # extend with -f docker-compose.prod.yml as needed


def _current_ovid_mode() -> str:
    out = subprocess.run(
        ["docker", "compose", *COMPOSE_FILES, "exec", "api", "printenv", "OVID_MODE"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip() or "standalone"


def main() -> int:
    original_mode = _current_ovid_mode()
    print(f"Captured current OVID_MODE={original_mode!r} for restore.")
    try:
        subprocess.run(
            ["docker", "compose", *COMPOSE_FILES, "up", "-d", "--no-deps", "api"],
            env={"OVID_MODE": "mirror", **_inherit_env()}, check=True,
        )
        subprocess.run(
            ["docker", "compose", *COMPOSE_FILES, "exec", "api", "alembic", "upgrade", "head"],
            check=True,
        )
    finally:
        subprocess.run(
            ["docker", "compose", *COMPOSE_FILES, "up", "-d", "--no-deps", "api"],
            env={"OVID_MODE": original_mode, **_inherit_env()}, check=True,
        )
    return 0
```

*(`_inherit_env()` — pass through the rest of `os.environ`; sketch omits full env-merge boilerplate. The planner should decide the exact docker-compose invocation shape based on which compose files are in play for a given deployment — dev vs. prod vs. self-hosted mirror.)*

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-row committed transactions inside an Alembic migration | A custom "manual COMMIT" SQL string or a separate non-Alembic script | `connection = op.get_bind()`; loop; `connection.execute(...)`; `connection.commit()` — SQLAlchemy 2.0's officially documented "commit as you go" pattern [CITED: docs.sqlalchemy.org/en/20/core/connections.html] | The connection auto-begins a new transaction segment on the next `execute()` call after a `commit()` — this is the exact, supported mechanism for exactly this need; no custom transaction management required |
| Cross-table uniqueness arbitration (WR-02) | A `pg_advisory_xact_lock` pessimistic lock, or an app-level in-savepoint recheck query | The D-02 shared-registry UNIQUE table, reusing the existing insert-first/IntegrityError/re-resolve idiom | Advisory locks have no SQLite equivalent (breaks the pytest suite's real-path coverage); in-savepoint recheck alone doesn't close the race (two independent constraints, no atomic backing) — both were explicitly rejected in CONTEXT.md's own decision rationale |
| Write-quiescing during a migration | A custom feature-flag system, a new maintenance-mode table, or manual "tell everyone not to submit right now" | The existing, already-tested `MirrorModeMiddleware` (405 on write methods) | It already exists, is already tested, and self-hosted mirror operators already understand its semantics from the existing self-hosting runbook |
| Determining "which identity method a fingerprint belongs to" | A new `method` column + migration | `_method_of()` (fingerprint-prefix derivation, Phase 1 D-04) — already exists, reused as-is by `_select_primary()` | No schema change needed; this phase adds zero new columns to `discs`/`disc_identity_aliases` |

**Key insight:** every piece of infrastructure this phase needs (SAVEPOINT arbitration, IntegrityError convergence, method derivation, read-only middleware) was **already built in Phase 1**. The engineering discipline required here is *extending those exact patterns to a new table and two new call sites* without inventing a second arbitration philosophy — CONTEXT.md's own rationale for D-02 makes this explicit ("collapses into the same single-UNIQUE-violation shape ... rather than introducing a second (pessimistic) arbitration strategy").

## Runtime State Inventory

> Included because this phase performs a data migration that rewrites `discs.fingerprint` values across existing rows — the canonical trigger condition for this section.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | `discs.fingerprint` values for every disc that has a recorded `dvdread1-*` alias, across the **canonical Postgres DB and every independently-run mirror/standalone Postgres DB** (each deployment owns its own data — confirmed via `docker-compose.yml`/`docker-compose.prod.yml`, no shared DB). `disc_identity_aliases` rows for the demoted `dvd1-*` values. | Code edit (Alembic data migration, D-01) run **independently on every deployment** — this is precisely why `SyncDiffRecord` not carrying alias rows matters (D-01 rationale): sync cannot propagate the promotion, so each mirror's own `alembic upgrade head` run is the only path to consistency for that instance. |
| **Live service config** | Checked `arm/identify_ovid.py` for any local caching of `disc.fingerprint` outside the DB (e.g. a sidecar file/DB ARM itself maintains) — **none found**; ARM performs a live GET lookup by fingerprint on every disc and does not persist fingerprint values locally. | None — verified by direct read of `arm/identify_ovid.py` (`lookup_ovid`/`_extract_result` build an in-memory result dict only, no local storage). |
| **OS-registered state** | None applicable — this phase touches no OS-level task schedulers, process managers, or system services. | None. |
| **Secrets/env vars** | `OVID_MODE` env var (not a secret, but load-bearing runtime config) — the D-04/D-05 cutover wrapper must read-and-restore this value correctly per deployment (`canonical` on the production server, `standalone` or `mirror` on self-hosted instances); getting the restore value wrong is the single highest-risk operational mistake this phase's tooling can make (see Pattern 3 above). | Code: the wrapper script must capture the CURRENT value before flipping, not hardcode a default. |
| **Build artifacts / installed packages** | None — no package renames, no new dependencies, no changed entry points in this phase. | None. |

**Canonical question answered:** after every code file is updated, the runtime state that still needs to change is exactly: (a) each deployment's own Postgres rows (`discs.fingerprint`, `disc_identity_aliases`), handled by the D-01 Alembic migration run per-deployment, and (b) each deployment's own `OVID_MODE` runtime value during the brief cutover window, handled by the D-05 wrapper script's capture/restore logic. Nothing else (no caches, no OS registrations, no secrets renames, no stale build artifacts) carries the old identity state.

## Common Pitfalls

### Pitfall 1: ARM's auto-register path sends no `fingerprint_aliases` at all — a genuine IDENT-03 gap
**What goes wrong:** `arm/identify_ovid.py:submit_to_ovid()` builds its own minimal payload (`{"fingerprint": fingerprint, "format": fmt, "disc_label": ...}`) directly, **without** using `ovid.submission.build_submit_payload()` and **without** any `fingerprint_aliases` key. A disc auto-registered via ARM after a lookup miss will therefore be created via `register_disc` with only its `dvd1-*` (or whatever `disc.fingerprint` currently returns) string and zero aliases — even though `identify_dvd()` may have computed a `dvdread1-*` identity locally that is simply never transmitted.
**Why it happens:** ARM's identify script is a lightweight, standalone `requests`-based module (not a consumer of `ovid-client`'s `submission.py`), written for a narrow "register a bare fingerprint" use case before ADR 0001's alias model existed.
**How to avoid — two options, not mutually exclusive:**
1. Patch `arm/identify_ovid.py` to also read `disc._identity_set` (already available via the same `Disc`/`BDDisc` object `fingerprint_disc()` already constructs) and include `fingerprint_aliases` in the register payload.
2. **Flip `identify_dvd()`'s default** so `dvdread1-*` becomes `.primary` (and `dvd1-*` becomes the alias) whenever libdvdread succeeds — mirroring the Tier-2-primary/Tier-1-alias pattern Phase 4 already established for `identify_bd()`. This transitively fixes ARM's gap for free (since `disc.fingerprint`, which ARM sends as its sole identity string, would then already be `dvdread1-*` when available) **and** answers CONTEXT.md's own open question about whether `identify_dvd()` should flip. This does require updating `ovid-client/tests/test_disc_identity.py`'s existing dvd1-primary assertions as an intentional behavior change.
See Open Questions #1 for the recommended combination and scope call.
**Warning signs:** a promoted disc's alias table shows zero `dvdread1-*` rows for discs known to have been auto-registered by ARM, while CLI-submitted discs show the expected alias pair.

### Pitfall 2: Conflating the two migrations' shapes
**What goes wrong:** treating the D-02 registry-backfill migration as if it also needs the D-01 per-disc-commit complexity (or vice versa — treating D-01's promotion as safely doable via a single `UPDATE...WHERE fingerprint IN (...)`, which CONTEXT.md's D-01 explicitly rejects).
**Why it happens:** both are "data migrations" in the same phase, inviting a single mental model.
**How to avoid:** the registry backfill (D-02) is a straightforward, ordinary, single-transaction migration — two `INSERT INTO fingerprint_registry (fingerprint, disc_id) SELECT fingerprint, id FROM discs` / `SELECT fingerprint, disc_id FROM disc_identity_aliases` statements, no per-row loop, no idempotency guard beyond Alembic's own revision tracking (it only ever runs once). The promotion migration (D-01) is the one requiring the per-disc loop, explicit `connection.commit()` calls, and a `WHERE discs.fingerprint = <old dvd1 value>` idempotency guard for resumability. Keep them as two separate, revision-chained files (registry first).
**Warning signs:** a single combined migration file with both "bulk backfill" and "per-row loop" logic tangled together.

### Pitfall 3: Assuming toggling `OVID_MODE` is a live, in-process operation
**What goes wrong:** writing (or documenting) the D-05 wrapper as if `export OVID_MODE=mirror` alone takes effect on a running deployment — it does not, because `MirrorModeMiddleware` is conditionally mounted once at app/process startup (see Pattern 3 above). A wrapper that sets the env var but never restarts the service will silently fail to quiesce writes, defeating the entire purpose of D-04.
**Why it happens:** env vars "feel" like they should be dynamically readable; the actual code checks them exactly once, at import time.
**How to avoid:** the wrapper must explicitly restart/recreate the `api` service (e.g. `docker compose up -d --no-deps api` with the new env value) both to enter and to exit quiesce, and must clearly document in the runbook that this restart briefly interrupts reads too, not just writes.
**Warning signs:** a migration that "completed successfully" but a live write request succeeded during the window it was supposed to be blocked.

### Pitfall 4: Assuming the IDENT-05 regression test needs rewriting for this phase
**What goes wrong:** treating `test_disc_identity_regression.py`'s existing golden-disc test as something that must be updated to expect `dvdread1-*` as the top-level fingerprint after promotion.
**Why it happens:** it's easy to assume "the primary fingerprint changed" implies "the test that checks the primary fingerprint must change."
**How to avoid:** the existing test (Phase 1 D-16) was deliberately written to assert stable **identity/structure** via a DB-level lookup by the fixed `dvd1-*` string and a hardcoded structure dict — it explicitly excludes the top-level `fingerprint` response field from its assertions for exactly this reason (see the test's own docstring, lines 19-27 of `test_disc_identity_regression.py`). It should continue to pass **unmodified** after this phase ships. Do not touch it unless adding genuinely new coverage.
**Warning signs:** a diff to `test_disc_identity_regression.py` in this phase's plan that isn't purely additive.

### Pitfall 5: CI never runs `alembic upgrade head` against a real database
**What goes wrong:** implementing the D-01 promotion logic entirely inside the Alembic migration's `upgrade()` function, with no path to unit-test it, means CI (which only runs `pytest` against in-memory SQLite — confirmed no `alembic`/`migration` step exists in `.github/workflows/ci.yml`) will never actually exercise this migration's logic before it ships.
**Why it happens:** Alembic migrations are conventionally "run once in production," which makes them easy to treat as untestable by habit.
**How to avoid:** factor the per-disc promotion logic (delete alias row → set fingerprint → insert old value as alias, with the idempotency guard) into a plain function taking a SQLAlchemy `Connection` or `Session`, callable both from the migration's `upgrade()` and directly from a pytest test using the existing in-memory SQLite harness (`conftest.py`'s `db_session`/`_engine` fixtures). Same recommendation for the D-02 registry-insert logic and D-03's `_select_primary()` (the latter is already a pure function, trivially testable).
**Warning signs:** a plan that lists "write the migration" as a single task with no corresponding unit test task.

## Code Examples

### Example 1: D-01 Promotion Migration — Testable Core Logic + Alembic Wrapper

```python
# api/app/migrations_support.py (new, small module — or inline in the
# migration file if the planner prefers; factored out here so pytest can
# exercise it directly against the SQLite test engine per Pitfall 5)
from sqlalchemy.engine import Connection
from sqlalchemy import text


def promote_one_disc(connection: Connection, dvd1_fingerprint: str) -> bool:
    """Promote a single disc from dvd1-* primary to dvdread1-* primary.

    Idempotent: the WHERE clause guards on discs.fingerprint still equaling
    the OLD dvd1 value, so an already-promoted disc (or a disc with no
    dvdread1 alias) is a safe no-op. Returns True if a promotion occurred.
    """
    row = connection.execute(
        text(
            "SELECT d.id AS disc_id, a.id AS alias_id, a.fingerprint AS dvdread1_fp "
            "FROM discs d JOIN disc_identity_aliases a ON a.disc_id = d.id "
            "WHERE d.fingerprint = :dvd1_fp AND a.fingerprint LIKE 'dvdread1-%'"
        ),
        {"dvd1_fp": dvd1_fingerprint},
    ).first()
    if row is None:
        return False  # already promoted, or no dvdread1 alias — no-op

    connection.execute(
        text("DELETE FROM disc_identity_aliases WHERE id = :alias_id"),
        {"alias_id": row.alias_id},
    )
    connection.execute(
        text("UPDATE discs SET fingerprint = :new_fp WHERE id = :disc_id"),
        {"new_fp": row.dvdread1_fp, "disc_id": row.disc_id},
    )
    connection.execute(
        text(
            "INSERT INTO disc_identity_aliases (id, disc_id, fingerprint, created_at) "
            "VALUES (:id, :disc_id, :old_fp, :now)"
        ),
        {
            "id": _new_uuid(), "disc_id": row.disc_id,
            "old_fp": dvd1_fingerprint, "now": _utcnow(),
        },
    )
    return True
```

```python
# api/alembic/versions/<rev-B>_promote_dvdread1_primary.py
from alembic import op

from app.migrations_support import promote_one_disc

revision = "<rev-B>"
down_revision = "<rev-A>"  # the D-02 registry migration


def upgrade() -> None:
    connection = op.get_bind()
    dvd1_fingerprints = [
        r[0]
        for r in connection.execute(
            "SELECT fingerprint FROM discs WHERE fingerprint LIKE 'dvd1-%'"
        )
    ]
    promoted_count = 0
    for i, dvd1_fp in enumerate(dvd1_fingerprints, start=1):
        if promote_one_disc(connection, dvd1_fp):
            promoted_count += 1
        connection.commit()  # per-disc commit (SQLAlchemy 2.0 commit-as-you-go —
                              # [CITED: docs.sqlalchemy.org/en/20/core/connections.html] —
                              # the connection auto-begins a new transaction segment
                              # on the next execute() call)
        if i % 100 == 0:
            print(f"  ...promoted {promoted_count}/{i} discs processed")
    print(f"Promotion complete: {promoted_count} discs promoted to dvdread1-* primary")


def downgrade() -> None:
    # Explicit no-op documented: reversing a promotion en masse is not a
    # sanctioned operation per D-03 (Disc.fingerprint immutability); a
    # downgrade here would itself violate the anti-fragmentation guarantee.
    pass
```

*(Test the core function directly: `promote_one_disc(db_session.connection(), "dvd1-golden-...")` against the existing pytest SQLite harness — no Alembic invocation required for unit coverage, per Pitfall 5.)*

### Example 2: WR-02 Regression Test (mirrors existing `test_disc_identity_race.py` style)

```python
# api/tests/test_fingerprint_registry.py (new)
"""WR-02 regression: a cross-table race between "new disc F" and
"attach F as an alias of a different disc" must not silently split
identity. Deterministic injection, following the same style as
test_disc_identity_race.py (SQLite serializes real concurrency away, so
the losing-race state is constructed directly rather than threaded)."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.disc_identity import register_fingerprint
from app.models import Disc, FingerprintRegistry


def test_cross_table_race_is_caught_by_registry(db_session: Session) -> None:
    disc_a = Disc(fingerprint="dvd1-wr02-a", format="DVD", status="unverified")
    db_session.add(disc_a)
    db_session.flush()
    register_fingerprint(db_session, "dvd1-wr02-a", disc_a.id)
    db_session.commit()

    # Simulate "worker 2" independently registering the SAME fingerprint
    # string as an alias of a DIFFERENT disc — the exact WR-02 scenario.
    disc_b = Disc(fingerprint="dvd1-wr02-b", format="DVD", status="unverified")
    db_session.add(disc_b)
    db_session.flush()

    with db_session.begin_nested():
        try:
            register_fingerprint(db_session, "dvd1-wr02-a", disc_b.id)
            db_session.flush()
            raised = False
        except IntegrityError:
            raised = True

    assert raised, (
        "the registry's global UNIQUE(fingerprint) must reject a second "
        "disc claiming an already-registered fingerprint — this is the "
        "exact cross-table split WR-02 exists to prevent"
    )
    rows = (
        db_session.query(FingerprintRegistry)
        .filter(FingerprintRegistry.fingerprint == "dvd1-wr02-a")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].disc_id == disc_a.id
```

### Example 3: D-03 Mixed-Fleet Regression Test

```python
# api/tests/test_disc_submit.py — new case in the existing test class
def test_old_client_resubmit_cannot_demote_promoted_disc(
    client, db_session, auth_header, second_auth_header
):
    """An old client re-submitting dvd1-* as its declared primary against
    an already-promoted (dvdread1-primary) disc must never demote it."""
    # ... seed a disc already promoted to dvdread1 primary with dvd1 as alias ...
    resp = client.post(
        "/v1/disc",
        json={**matrix_matching_submit_payload(), "fingerprint": "dvd1-already-promoted"},
        headers=second_auth_header,
    )
    assert resp.status_code == 200
    db_session.expire_all()
    disc = db_session.query(Disc).filter(Disc.id == seeded_disc_id).one()
    assert disc.fingerprint.startswith("dvdread1-"), (
        "an old client's dvd1-primary submission must never demote an "
        "already-promoted disc back to dvd1 primary (D-03 mixed-fleet guarantee)"
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Alembic + SQLAlchemy 1.x "begin once" connection style, where mid-script commits required manual `connection.execution_options(isolation_level="AUTOCOMMIT")` gymnastics | SQLAlchemy 2.0's native "commit as you go" — `connection.commit()` mid-script simply commits and the next `execute()` auto-begins a new transaction segment | SQLAlchemy 2.0 (already the pinned version, `>=2.0,<3.0`) | D-01's per-disc-commit loop is directly supported with no workarounds — confirmed via official docs, not a hack |

**Deprecated/outdated:** none directly relevant — this phase does not touch any deprecated API surface. `op.get_context().autocommit_block()` (found during research) is a related-but-different Alembic feature intended for DDL that cannot run inside any transaction at all (e.g. Postgres `ALTER TYPE ... ADD VALUE`) — it is not the right tool for D-01's need (which is per-row **DML** commits, not transaction-incompatible DDL), and is noted here only to avoid the planner reaching for it by mistake.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Recommending `identify_dvd()` flip to dvdread1-primary (Pitfall 1 / Open Questions #1) is the cleaner single-point fix versus patching ARM's payload directly | Common Pitfalls #1, Open Questions #1 | If the user/planner disagrees (e.g. wants to preserve dvd1-primary client-side labeling for UX reasons), the ARM gap would need its own direct patch instead — both are documented as options, so risk is low, but the *recommendation* itself is an opinion, not a verified fact |
| A2 | The recommended env-var+restart mechanism (Option A, Pattern 3) is preferable to a DB-backed runtime flag (Option B) for this phase | Architecture Patterns Pattern 3 | If OVID's operators find full-service restarts unacceptable even briefly, Option B becomes necessary sooner than "future note" implies — but CONTEXT.md's own D-04 rationale explicitly frames near-zero cost given current low write volume, supporting A2 |
| A3 | `scripts/promote_dvdread1.py` should be Python (matching `scripts/dump_cc0.py`'s convention) rather than a shell script | Architecture Patterns Pattern 3, Recommended Project Structure | Low risk — purely a style/consistency call left as Claude's Discretion in CONTEXT.md ("script/make-target") |

## Open Questions

1. **Should this phase fix `arm/identify_ovid.py`'s missing `fingerprint_aliases`, flip `identify_dvd()`'s primary preference, or both?**
   - What we know: ARM's auto-register path currently transmits zero alias information, which undermines IDENT-03's "the client submits every known Disc Identity string" for that specific submission path; flipping `identify_dvd()`'s default (mirroring `identify_bd()`'s already-established Tier-2-primary pattern) would fix ARM's gap for free and also directly answers CONTEXT.md's own flagged question about whether `identify_dvd()` should flip.
   - What's unclear: whether the user considers touching `arm/identify_ovid.py` in-scope given the phase's explicit "no ARM interface versioning" scope guard — this research judges the fix to be about IDENT-03 (client submits all known strings), not ARM-02 (interface contract versioning), but the planner should confirm this framing before committing to the change.
   - Recommendation: flip `identify_dvd()` (small, single-point change, mirrors the established BD pattern, fixes ARM's gap transitively) and update `ovid-client/tests/test_disc_identity.py`'s existing assertions accordingly; treat this as in-scope for IDENT-03 unless the user pushes back during `/gsd-discuss-phase` follow-up or plan review.

2. **Does `docs/self-hosting.md` need the D-05 runbook section, or does `docs/deployment.md` (or both)?**
   - What we know: self-hosting.md's own existing Quick Start already runs mirror-mode operators permanently read-only, so the write-quiesce toggle this phase adds is **not actually needed** by that audience — they already run `alembic upgrade head` unconditionally as part of their existing update routine (self-hosting.md Step 4). The audience that genuinely needs a toggle-and-restore wrapper is the canonical server (`oviddb.org`) and any self-hosted **standalone**-mode operator (who is not `self-hosting.md`'s primary documented use case — that doc's Quick Start only walks through mirror-mode setup).
   - What's unclear: CONTEXT.md's D-05 explicitly locks "a `docs/self-hosting.md` section" — this research does not know if that's because the user also wants standalone-mode self-hosting documented there (a real but currently-undocumented use case), or if `docs/deployment.md` (which already documents the canonical production runbook) is the more correct target and CONTEXT.md's phrasing was approximate.
   - Recommendation: add the section to `docs/self-hosting.md` as locked, but ALSO add an equivalent (or cross-referencing) section to `docs/deployment.md` for the canonical-server audience, since that is the operator who will actually run this wrapper in practice for the real `oviddb.org` cutover. Flag this as a two-line addition, not scope creep — both docs already exist and already reference `alembic upgrade head`.

3. **Does the D-01 promotion migration need an explicit progress-checkpoint mechanism beyond print-statement logging, given "potentially large table" framing in the phase description?**
   - What we know: D-01 asks for "progress logging on a potentially large table"; the dataset is currently pre-launch/small (per D-04's own rationale: "the dataset is still small pre-launch"), and OPS-02 (seeding to ≥500 entries) is a later phase (Phase 8).
   - What's unclear: whether simple periodic `print()`/logging (as sketched in Code Example 1) is sufficient, or whether the planner should add a resumable "last processed fingerprint" checkpoint mechanism for a genuinely large future re-run (e.g. a future identity-method migration reusing this same pattern at ≥500+ scale).
   - Recommendation: periodic logging is sufficient for THIS phase's actual data volume; the idempotency guard (`WHERE discs.fingerprint = <old dvd1 value>`) already makes the whole migration safely resumable from scratch on interruption (re-running simply skips already-promoted discs), so no separate checkpoint bookkeeping is needed now — note this as a natural evolution point for the "future note" fully-online-migration path D-04 already defers.

## Environment Availability

> This phase's core work (migrations, code changes, tests) requires no new external tools beyond what every prior phase already assumes (Python 3.12, PostgreSQL 16 via Docker Compose, the already-pinned SQLAlchemy/Alembic/pytest stack). The D-05 cutover wrapper additionally assumes `docker compose` CLI availability, already a documented prerequisite in `docs/self-hosting.md` and `docs/deployment.md`.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + Docker Compose | D-05 cutover wrapper (`docker compose up`/`exec`) | — (not probed in this research session; already a documented project prerequisite per `docs/self-hosting.md`/`docs/deployment.md`) | 24.0+ / v2.0+ (documented minimums) | None needed — this is an existing hard prerequisite of the whole project, not new to this phase |
| PostgreSQL 16 | Alembic migrations (D-01/D-02) run against it in every deployment | — (existing project dependency, unchanged) | 16 (per `docker-compose.yml`: `postgres:16-alpine`) | None needed |

**Missing dependencies with no fallback:** none identified beyond the project's pre-existing Docker/Postgres prerequisites.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=7.0` [CITED: api/requirements.txt / ovid-client/pyproject.toml] |
| Config file | `api/pytest.ini`/`pyproject.toml` (existing, unchanged); `ovid-client/pyproject.toml` (existing, unchanged) |
| Quick run command | `cd api && python -m pytest tests/test_fingerprint_registry.py tests/test_disc_submit.py -x` |
| Full suite command | `cd api && python -m pytest tests/ -x` and `cd ovid-client && python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IDENT-03 | ovid-client CLI DVD submission includes both dvd1 and dvdread1 strings | unit | `pytest ovid-client/tests/test_submission.py::test_build_submit_payload_uses_disc_identity_set -x` | ✅ (already exists — confirms current behavior) |
| IDENT-03 | ARM auto-register includes alias info (pending Open Questions #1 decision) | unit/integration | `pytest arm/tests/test_identify_ovid.py -x` (new, if the fix is in-scope) | ❌ Wave 0 (only if scope confirmed) |
| IDENT-04 | New DVD submission with dvdread1 present picks dvdread1 as primary (D-03) | integration (TestClient) | `pytest api/tests/test_disc_submit.py::test_submit_disc_prefers_dvdread1_primary -x` | ❌ Wave 0 |
| IDENT-04 | Existing promoted disc cannot be demoted by an old-client resubmission (D-03 mixed-fleet) | integration (TestClient) | `pytest api/tests/test_disc_submit.py::test_old_client_resubmit_cannot_demote_promoted_disc -x` | ❌ Wave 0 |
| IDENT-04 | D-01 per-disc promotion loop correctness + idempotency (re-run is a no-op) | unit | `pytest api/tests/test_promote_dvdread1_migration.py -x` | ❌ Wave 0 |
| IDENT-05 [guardrail] | Pre-migration dvd1-* string still resolves after promotion | regression | `pytest api/tests/test_disc_identity_regression.py -x` | ✅ (existing, unmodified per Pitfall 4) |
| WR-02 | Cross-table fingerprint race is closed by the registry | regression | `pytest api/tests/test_fingerprint_registry.py -x` | ❌ Wave 0 |
| WR-02 | Registry backfill covers both `discs` and `disc_identity_aliases` in one migration | unit | `pytest api/tests/test_fingerprint_registry_migration.py -x` (verifies the bulk INSERT...SELECT logic) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant single test file above (`pytest <file> -x`)
- **Per wave merge:** `cd api && python -m pytest tests/ -x && cd ../ovid-client && python -m pytest tests/ -x`
- **Phase gate:** full suite green (both `api/` and `ovid-client/`) before `/gsd-verify-work`; additionally, a manual dry-run of `alembic upgrade head` against a scratch Postgres instance (e.g. via `docker compose run --rm api alembic upgrade head` against a throwaway `docker-compose.yml` `db` service) is recommended before the real cutover, since CI never exercises real Alembic execution (Pitfall 5) — this is a manual verification step, not automatable within the existing CI job shape without adding a new CI job (out of scope for this phase to add).

### Wave 0 Gaps
- [ ] `api/tests/test_fingerprint_registry.py` — covers WR-02
- [ ] `api/tests/test_promote_dvdread1_migration.py` — covers D-01 logic (calls `promote_one_disc()` directly, not via Alembic)
- [ ] `api/tests/test_disc_submit.py` additions — covers D-03 (new-disc hybrid selection + mixed-fleet immutability)
- [ ] `arm/tests/` directory does not currently exist — if Open Questions #1's ARM fix is confirmed in-scope, a new `arm/tests/test_identify_ovid.py` needs Wave 0 scaffolding (check whether `arm/` currently has any test infrastructure at all before assuming pytest is wired there — not confirmed in this research session)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Unchanged by this phase — existing JWT/OAuth deps reused as-is on submission routes |
| V3 Session Management | No | Not touched |
| V4 Access Control | Partial | The D-05 cutover wrapper's restart step is an **operator-only** action (not exposed via any API endpoint) — no new access-control surface is introduced. If Option B (DB-backed runtime flag, not recommended) were chosen instead, an admin-only endpoint to flip it would need V4 controls; Option A (recommended) has no such exposure. |
| V5 Input Validation | Yes | `_select_primary()` operates only on already-validated `Pydantic`-schema fingerprint strings (`DiscSubmitRequest`/`DiscRegisterRequest`); no new untrusted input surface |
| V6 Cryptography | No | Not touched — no key material, no hashing changes in this phase |
| V9 Communication | No | Not touched |
| V13 API/Config | Yes | `OVID_MODE` is a deployment-config value, not a secret; the D-05 wrapper must not log or expose it insecurely, and must not accept it from any untrusted request input — it is read from the local deployment environment only |

### Known Threat Patterns for this Phase's Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A malicious/buggy client submitting a crafted `fingerprint_aliases` list to force a specific primary selection on a NEW disc | Tampering | `_select_primary()` only ever *prefers* a `dvdread1-*`-prefixed string that the submitter themselves provided as part of a normal, schema-validated submission — there is no privileged/trusted-only string; this mirrors the existing trust model where any submitter's fingerprint values are taken at face value pending the two-contributor verification flow (VERIFY-01). No new trust boundary is crossed. |
| Race-induced identity split (WR-02) exploited to attach a forged alias to someone else's disc | Tampering / Repudiation | The D-02 registry closes the race at the DB-constraint level; any residual race is still caught by the existing `DiscIdentityConflict` → 409 response, unchanged |
| Operator-facing cutover wrapper being tricked into running against the wrong deployment (e.g. accidentally targeting canonical prod docker-compose files from a dev checkout) | Tampering / Denial of Service | The wrapper script should require explicit `-f <compose-file>` arguments (no silent defaulting to prod compose files) and should print the captured `OVID_MODE` + target compose files before proceeding, requiring operator confirmation — a plan-level detail, not a code-level control |

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `api/app/disc_identity.py`, `api/app/models.py`, `api/app/routes/disc.py`, `api/app/middleware.py`, `api/app/sync.py`, `api/main.py`, `api/alembic/versions/*.py`, `api/alembic/env.py`, `api/tests/conftest.py`, `api/tests/test_disc_identity_race.py`, `api/tests/test_disc_identity_regression.py`, `api/requirements.txt`, `ovid-client/src/ovid/disc_identity.py`, `ovid-client/src/ovid/disc.py`, `ovid-client/src/ovid/submission.py`, `ovid-client/src/ovid/cli.py`, `ovid-client/tests/test_submission.py`, `arm/identify_ovid.py`, `docker-compose.yml`, `docker-compose.prod.yml`, `docs/self-hosting.md`, `docs/deployment.md`, `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`, `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-REVIEW.md` (WR-02 section, lines 226-271)
- [VERIFIED: package-legitimacy N/A] — no new packages introduced this phase

### Secondary (MEDIUM confidence)
- [CITED: alembic.sqlalchemy.org/en/latest/api/runtime.html] — `autocommit_block()` semantics (confirmed NOT the right tool for D-01; noted to prevent misuse)
- [CITED: docs.sqlalchemy.org/en/20/core/connections.html] — "commit as you go" `Connection.commit()`/autobegin semantics, directly underpinning the D-01 per-disc-commit design

### Tertiary (LOW confidence)
- None — no unverified WebSearch-only claims were relied upon for this research; all technical claims trace to either direct codebase reads or official Context7-fetched documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all versions read directly from the repo's own pinned requirements files
- Architecture: HIGH — every pattern (SAVEPOINT/IntegrityError convergence, MirrorModeMiddleware, `_method_of()`) is direct extension of code already read in full; the two Alembic-migration-mechanics claims are additionally Context7-verified against official docs
- Pitfalls: HIGH for the ARM gap and the MirrorModeMiddleware startup-only wiring (both confirmed by direct code reads); MEDIUM for the recommendation to flip `identify_dvd()` (this is a design opinion, flagged as Assumption A1, not a verified requirement)

**Research date:** 2026-07-06
**Valid until:** 30 days (stable, internal-codebase-driven research; no fast-moving external API surface involved)
