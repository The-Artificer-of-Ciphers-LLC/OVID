# Phase 5: ADR 0001 Completion — dvdread1-* Promotion - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Finish ADR 0001's staged libdvdread migration end-to-end:

1. **IDENT-03** — `ovid-client` submits every known Disc Identity string for a disc (`dvd1-*`, `dvdread1-*`, and/or BD tiers) on submission, and the API stores the non-primary strings as aliases. (The client payload path already emits `fingerprint` = primary + `fingerprint_aliases`; this phase makes it genuinely complete/verified end-to-end for the DVD path.)
2. **IDENT-04** — New DVD submissions and lookups show `dvdread1-*` as the primary fingerprint; every existing disc that already has a recorded `dvdread1-*` alias is promoted (one transaction per disc); any disc without a `dvdread1-*` alias stays permanently on `dvd1-*`.
3. **IDENT-05 (carry-forward guardrail)** — pre-migration `dvd1-*` fingerprints still resolve correctly after promotion, with zero fragmentation. The existing CI regression must keep passing.
4. **WR-02 (Phase-1 code-review carry-forward, user-scoped to this phase)** — add cross-table fingerprint arbitration so a "new disc F" vs. "attach F as an alias to a different disc" race can no longer silently split identity. Mandatory in this phase because promotion increases write concurrency on the shared fingerprint namespace.

**Not in this phase (scope guard):** OAuth/accounts (Phase 6), Web UI (Phase 7), ARM interface versioning / seeding / announcement (Phase 8), matrix256 pressing-level alias (deferred to v2, MATRIX-01). No BD/UHD fingerprint *computation* changes — Phase 4 delivered those; this phase only ensures BD identity strings ride along in a full submission.

</domain>

<decisions>
## Implementation Decisions

### D-01: Backfill mechanism — Alembic data migration
Promote existing discs via a **versioned Alembic data migration**, not a standalone script and not lazy promote-on-access.
- Loop **per disc** (not a set-based `UPDATE ... WHERE fingerprint IN (...)`): for each disc that has a `dvdread1-*` alias, in its own explicitly-committed transaction — delete that `disc_identity_aliases` row, set `discs.fingerprint` to the `dvdread1-*` value, and insert the old `dvd1-*` value as a new alias row.
- **Idempotent / re-runnable / resumable:** guard each per-disc write on current state (e.g. `WHERE discs.fingerprint = <old dvd1 value>`) so an already-promoted disc is a safe no-op on re-run or after an interrupted pass.
- Reuse Phase 1's insert-first / catch `IntegrityError` / re-resolve defense so the migration is safe against concurrent `gunicorn -w 4` writers.
- **Rationale:** OVID's permanent self-hosted-mirror model makes deploy-pipeline coupling a *feature* — mirrors already run `alembic upgrade head`. The sync feed (`SyncDiffRecord`) carries only `disc.fingerprint`, **not** alias-table rows, so mirrors cannot learn the dvd1→dvdread1 promotion via sync; each mirror DB must promote locally regardless. Lazy promote-on-access was rejected — untouched long-tail discs would never promote, failing success criterion 2.

### D-02: WR-02 arbitration — shared fingerprint-registry table
Close the cross-table race with a **new shared fingerprint-registry table** (a single table with a global `UNIQUE(fingerprint)`), into which BOTH the new-disc insert path and `attach_lookup_aliases` register the fingerprint first.
- This collapses the cross-table collision into the **same single-UNIQUE-violation shape** the code already handles: insert → catch `sqlalchemy.exc.IntegrityError` → `expire_all()` → re-resolve → converge. Reuses the exact idiom in `attach_lookup_aliases` (Phase 1 D-01/D-03), rather than introducing a second (pessimistic) arbitration strategy.
- **Dialect-portable:** a plain `UNIQUE` column works on SQLite, so the in-memory pytest TestClient suite exercises the *real* code path (must stay green). This is the decisive reason over the `pg_advisory_xact_lock` option, which has no SQLite equivalent and would leave the exact race this phase must close untested by the existing suite.
- **In-savepoint recheck was rejected as a sole fix** — it does not actually close the race (two independent constraints, no atomic backing); acceptable only as defense-in-depth on top of the registry.
- Requires a one-time migration that creates the registry table and **backfills it from every existing `discs.fingerprint` and `disc_identity_aliases.fingerprint` value**, inside a single migration transaction. Every current and future insert path must register first.

### D-03: Primary selection — Hybrid (server picks at first-insert)
On a **new-disc** submission, the **server** chooses the primary among the submitted identity strings, preferring `dvdread1-*` when present; the client's declared primary is advisory.
- `Disc.fingerprint` is **immutable on the live write path** once the disc exists. A later submission from any client version (including old clients still sending `dvd1-*` primary) flows through the existing race-safe alias convergence and can only **add/confirm aliases — never demote** `dvdread1-*` back to `dvd1-*`. This is the "zero fragmentation" guarantee under a mixed client fleet (ovid-client upgrades independently via PyPI / ARM).
- A disc where no `dvdread1-*` string is present (libdvdread unavailable at read time) stays `dvd1-*` primary — satisfies success criterion 2's "stays permanently on dvd1-*".
- **Interaction with D-01 (resolved, not a conflict):** immutability governs the *live write path*. The one-time Alembic backfill (D-01) is the **single sanctioned mutation** of an existing `Disc.fingerprint`, run under the D-04 quiesce window — not on the live path.
- Client-authoritative was rejected (first client to touch a disc fixes its method forever → heterogeneous primaries, never converges). Full server re-normalization on every submission was rejected (mutates existing `Disc.fingerprint` on the hot path → collides with D-06 alias ordering + adds races).

### D-04: Cutover posture — write-quiesce via MirrorModeMiddleware
Run the one-time backfill inside a **brief write-quiesce window**, reusing the existing, already-tested `MirrorModeMiddleware` read-only gate (405 on writes; GET/HEAD/OPTIONS pass through). Flip read-only → run backfill → flip back.
- Eliminates the backfill-vs-live-write race **by construction**, rather than making the first real cutover depend on WR-02 being perfect under live concurrent traffic.
- Near-zero cost given OVID's profile: low write volume (community submissions), reads are the hot path (ARM lookups) and stay up throughout, and the dataset is still small pre-launch. Trivially reversible if the backfill is interrupted mid-run.
- **Future note (not this phase):** once the table is large (post the ≥500-entry seeding phase), fully-online promotion — with the D-02 registry hardened and battle-proven — becomes the better posture for later identity-method migrations.

### D-05: Cutover operability — one-command wrapper + self-hosting runbook
Ship a single operator entry point (script / make-target) that performs **toggle read-only → `alembic upgrade head` (promotion) → toggle read-write** as one step, plus a `docs/self-hosting.md` section documenting it.
- Directly mitigates the "operator forgets to flip writes back on" failure the research flagged, and gives self-hosted mirror operators a familiar, low-effort runbook (they already understand the mirror-mode toggle).

### Claude's Discretion
- Exact registry-table name/shape, migration file numbering, and the precise sequencing of the two migrations (registry-create+backfill first, then promotion) — planner/researcher to order. Cross-cut flagged below.
- Whether the WR-02 registry insert lives in `disc_identity.py` alongside the existing convergence helpers or a small new module.
- The precise mechanism of the read-only toggle inside the wrapper (env var vs. runtime flag) provided it reuses `MirrorModeMiddleware` semantics.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### ADR / migration governing docs
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` — the staged migration this phase completes (Phase 3 of the ADR: promote `dvdread1-*` to primary, keep `dvd1-*` a resolvable alias). Hard constraint: `dvd1-*` must remain stable and resolvable — no lookup/submission fragmentation.
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-REVIEW.md` §WR-02 (lines 226-271) — the exact cross-table race description and the three candidate fixes; source of the D-02 mandate.

### Phase-1/Phase-4 decisions this phase must honor
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-CONTEXT.md` — D-04 (method derived from fingerprint prefix via `_method_of()`; no method column, no migration), D-06 (alias ordering primary-first by `(created_at, id)`). Promotion must not violate D-06.
- Phase 1 D-16 (see STATE.md / 01 plans): the IDENT-05 anti-fragmentation regression asserts stable **identity/structure**, not the literal top-level fingerprint value — so it survives promotion by design. Extend, don't rewrite.
- Phase 1 IDENT-02 pattern (`api/app/disc_identity.py`): insert-first / catch `sqlalchemy.exc.IntegrityError` / re-resolve inside `db.begin_nested()` SAVEPOINTs — the arbitration idiom D-02 reuses.

### Source files in scope
- `api/app/models.py` — `Disc.fingerprint VARCHAR(50) UNIQUE` (the primary); `DiscIdentityAlias(disc_id FK, fingerprint VARCHAR(50) UNIQUE)`; the two independent UNIQUE constraints that are the WR-02 gap.
- `api/app/disc_identity.py` — `resolve_disc_identity`, `resolve_existing_disc_for_identities`, `attach_lookup_aliases`; where registry registration + arbitration land.
- `api/app/routes/disc.py` — `submit_disc` / `register_disc` / `resolve_dispute_endpoint`; where server-side primary selection (D-03) lives.
- `api/app/middleware.py` — `MirrorModeMiddleware` (reused for D-04 quiesce).
- `api/app/sync.py` — `SyncDiffRecord` carries only `disc.fingerprint`, not alias rows (the reason D-01 must run locally on mirrors).
- `api/alembic/versions/` — existing migration style, incl. prior data-carrying migrations, for D-01/D-02.
- `ovid-client/src/ovid/disc_identity.py` — `identify_dvd()` (currently dvd1-primary / dvdread1-alias; promotion flips this when libdvdread available), `libdvdread_identity`, `DiscIdentitySet`.
- `ovid-client/src/ovid/submission.py` — `build_submit_payload` already emits `fingerprint` = `identity_set.primary` + `fingerprint_aliases`.
- `ovid-client/src/ovid/cli.py` — wires `_disc_identity_set(disc)` into `build_submit_payload`; verify the DVD reader path attaches `_identity_set` for IDENT-03 completeness.
- `docs/self-hosting.md` — target for the D-05 cutover runbook section.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`MirrorModeMiddleware`** (`api/app/middleware.py`): already-built, already-tested read-only enforcement — reused directly for the D-04 quiesce window; no new middleware code.
- **Insert-first / IntegrityError / re-resolve convergence** (`api/app/disc_identity.py`, Phase 1 D-01/D-03): the arbitration idiom the D-02 registry reuses so cross-table races collapse to the same handled shape.
- **`build_submit_payload` + CLI `_disc_identity_set` wiring** (`ovid-client`): the multi-string submission path already exists; IDENT-03 is completion/verification of the DVD path, not new payload plumbing.
- **`_method_of()` prefix derivation** (Phase 1 D-04): "which method" is read from the fingerprint prefix; no method column needed for primary selection.

### Established Patterns
- "Primary" is physically the `discs.fingerprint` column; aliases live in `disc_identity_aliases`, ordered primary-first by `(created_at, id)` (D-06). Promotion = rewrite the column + insert the demoted value as an alias.
- Tests run against **in-memory SQLite** via FastAPI TestClient — any DB-layer arbitration must work under SQLite (drove the D-02 registry-over-advisory-lock choice).
- Alembic migrations wrap one transaction per run by default — the D-01 per-disc-commit loop must manage its own per-row transactions/commits.

### Integration Points
- New fingerprint-registry table (D-02): both the new-disc insert in `routes/disc.py` and `attach_lookup_aliases` in `disc_identity.py` register into it first.
- Server-side primary selection (D-03): the create branch of `submit_disc` / `register_disc`.
- Two Alembic migrations (registry backfill; promotion backfill) sequenced against `api/alembic/versions/` head.
- Cutover wrapper (D-05) toggles `MirrorModeMiddleware` state around `alembic upgrade head`.

</code_context>

<specifics>
## Specific Ideas

- Backfill loop MUST be per-disc with an idempotent state guard (`WHERE discs.fingerprint = <old dvd1 value>`) so partial/interrupted/re-run passes are safe no-ops.
- D-02 registry table must be backfilled from BOTH existing tables (`discs.fingerprint` + `disc_identity_aliases.fingerprint`) in the same migration transaction — no window where the registry lags reality.
- The mixed-fleet invariant is load-bearing: an old client re-submitting a promoted disc must be provably unable to demote `dvdread1-*` back to `dvd1-*`. This deserves an explicit regression test.
- WR-02 should get an explicit regression test proving the cross-table race is closed (the review's option (c), folded in as defense-in-depth verification on top of the registry).

</specifics>

<deferred>
## Deferred Ideas

- **Fully-online promotion (no write-quiesce)** — deferred to a *future* identity-method migration once the table is large post-seeding and the D-02 registry is battle-proven. Not this phase (D-04).
- **matrix256 pressing-level alias (MATRIX-01)** — spike-first, single-source, unvalidated; deferred to v2 per REQUIREMENTS.md (already tracked in STATE.md deferred items).

None of the above expands this phase's scope.

</deferred>

---

*Phase: 5-ADR 0001 Completion — dvdread1-* Promotion*
*Context gathered: 2026-07-06*
