# Phase 1: Alias-Layer Hardening & Repo Hygiene - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase hardens the correctness and safety of the disc-identity and verification **write paths**, and cleans ad-hoc repo cruft — establishing the foundation that Phases 4 (BD fingerprinting), 5 (`dvdread1-*` promotion), 6 (OAuth linking), and 7 (Web UI) build on.

It closes six requirements: IDENT-01 (expose all aliases in lookup), IDENT-02 (race-safe alias write path), IDENT-05 (permanent anti-fragmentation CI test), VERIFY-02 (consolidated verification state machine), CLEAN-01 (remove root patch scripts), CLEAN-02 (gitignore UAT artifacts).

**Hard sequencing constraint:** the IDENT-02 race fix and VERIFY-02 consolidation MUST land and soak before Phase 5 promotes `dvdread1-*` to primary — promotion raises write concurrency on the same fingerprint namespace, and a race there would corrupt the `dvd1-*` stability guarantee ADR 0001 exists to protect.

**Not in this phase (redirected to their owning phases):** two-contributor confirmation flow and anti-Sybil weighting (Phase 2, builds ON the `verification.py` module created here); `dvdread1-*` promotion and dual-string submission (Phase 5); rate-limiting/Redis work (Phase 3).
</domain>

<decisions>
## Implementation Decisions

### Race-safety mechanism — alias check-then-insert (IDENT-02)
- **D-01:** Use the **unique-constraint + catch-conflict** strategy: insert-first, catch SQLAlchemy `IntegrityError` (equivalently `ON CONFLICT DO NOTHING`), then re-resolve to the winning `Disc`/alias row. Chosen over Postgres advisory locks, `SELECT … FOR UPDATE`, and SERIALIZABLE+retry.
- **Why:** The load-bearing half already exists — `Disc.fingerprint` and `DiscIdentityAlias.fingerprint` are both declared `unique=True` in `api/app/models.py`. The DDL constraint is already live in *both* SQLite and Postgres. The only gap is that `resolve_disc_identity` / `attach_lookup_aliases` in `api/app/disc_identity.py` check-then-`add()` without handling the violation a concurrent worker would trigger. This is the smallest, most idiomatic fix and touches only `disc_identity.py` + the two submission call sites in `routes/disc.py`.
- **D-02 (testability — the deciding factor):** This is the ONLY option regression-testable against the existing in-memory SQLite harness, because SQLite raises `IntegrityError` on a UNIQUE violation exactly as Postgres does. The alternatives (advisory lock, `FOR UPDATE`, SERIALIZABLE) are Postgres-only semantics that SQLite silently no-ops — any test written against them would falsely pass without exercising serialization, and would require a Postgres-backed integration harness this project does not currently have.
- **D-03 (implementation caution for planning):** Restructure resolution from "check, then unconditionally add" to "add, catch conflict, re-query the winner." Wrap each alias insert in a **savepoint / nested transaction** so one alias losing the race does not roll back the whole submission, and clean up a partial `Disc` insert if a sibling alias insert then collides.

### Alias response shape — GET /v1/disc/{fingerprint} (IDENT-01)
- **D-04:** Return aliases as **objects carrying the method label**, added as a strictly **additive** field: `fingerprint_aliases: list[{fingerprint: str, method: str, is_primary: bool}]`.
- **D-05:** Keep the existing top-level `fingerprint: str` **unchanged** (the primary value). Include the primary in the `fingerprint_aliases` array too, flagged `is_primary: true`, so every identity is enumerable from one collection without any consumer observing a removed field.
- **D-06 (ordering):** Primary-first, then remaining aliases in **insertion order**. Do NOT sort by string — `dvd1-*` and `dvdread1-*` do not compare meaningfully alphabetically.
- **D-07 (compatibility):** Strictly additive — `ovid-client`, the ARM shim (`arm/identify_ovid.py`), and `web/lib/api.ts` `DiscLookupResponse` keep working unmodified; they opt into the new field only when they need method awareness (Phase 5/7). A new Pydantic model (e.g. `FingerprintAliasResponse`) is defined and kept in sync with the alias ORM table.
- **Why:** This shape survives Phase 5 promotion (primary-vs-alias and method become structurally explicit, not prefix-parsed) and Phase 7's disc-detail view (WEBUI-02 renders aliases with a method per entry) **without a second breaking change**. Mirrors MusicBrainz's own alias-object pattern (`primary` boolean) — apt given OVID's "MusicBrainz for video discs" framing.

### Verification state machine (VERIFY-02)
- **D-08:** Consolidate into a new `api/app/verification.py` as **flat module-level functions + an explicit transition table** (module-level `frozenset`/dict), following the established `api/app/disc_identity.py` / `api/app/sync.py` convention. Rejected: a session-bound `VerificationService` class (would introduce the first OOP-service pattern into a flat-function codebase) and a third-party FSM library (disproportionate dependency for a ~4-state machine).
- **D-09 (`disputed` gating — the core of VERIFY-02):** The general transition table contains **zero** entries with `"disputed"` as a target. `disputed` is reachable ONLY through a distinct, separately-exported `flag_dispute(db, disc, actor, reason)` function, which the submit-conflict branch calls explicitly **instead of** the current inline `existing.status = "disputed"` mutation in `routes/disc.py`. This makes `flag_dispute` the single grep-able writer of that status and closes the silent-flip bug (an already-`verified` disc flipped to `disputed` outside the dispute path).
- **D-10 (errors):** Raise a domain exception (e.g. `VerificationTransitionError` carrying `current_status` / `attempted_status` / `disc_id`), caught at the route boundary and rendered via the structured JSON error envelope — same raise-and-catch pattern as `DiscIdentityConflict`.
- **D-11 (invariant placement):** Move the "cannot verify your own submission" rule INTO the verification function itself (it is a transition invariant, not generic authz), so no future caller can bypass it. Keep coarse role/authz checks (`trusted`/`editor`/`admin`) at the route layer per convention.
- **D-12 (Phase 2 seam — do NOT over-build):** Function signatures accept a full `actor` (not a bare id) and the structured exception, so Phase 2 can wrap them (e.g. a future `confirm()` calling `verify()` after an independent-confirmation + rate-limit check) without changing their contract. Do NOT implement confirmation-counting, a confirmations table, or rate-limit state now — that needs schema Phase 1 does not own. The seam is the stable function boundary + exception type.
- **⚠ RESEARCH-NOTE (reconcile against live tests before planning locks it):** There is a discrepancy on the `verified → verified` transition. `api/tests/test_disc_verify.py` was seen to contain BOTH a `test_verified_to_verified_returns_400` and an "already-verified idempotent" expectation. The consolidated module MUST preserve whatever the *current* passing tests assert (migration constraint: no behavior drift). The researcher/planner must read the live `test_disc_verify.py` and confirm the actual expected behavior (400 vs idempotent 200) before freezing the transition table.

### dvd1-* anti-fragmentation regression test (IDENT-05)
- **D-13:** Use a **golden ORM-seeded record asserted through `GET /v1/disc`**. Reuse the existing `seed_test_disc` / `conftest.py` fixture pattern. Rejected: a synthetic fabricated row (doesn't prove the real `dvd1-*` algorithm round-trips) and a golden-JSON snapshot file (invites "just re-approve" that swallows the very regression it guards; new snapshot dependency).
- **D-14 (what is asserted):** Assert resolution **AND frozen structure** — compare the resolved title/chapter/track/release fields against a **hardcoded expected dict kept independent of the seed call** (not re-derived from the seed data, or the test is tautological). IDENT-05 exists to catch *silent data drift*, not just a 200.
- **D-15 (guaranteed to run every PR, no hardware):** A plain, **unmarked** pytest (e.g. `api/tests/test_disc_identity_regression.py`). `.github/workflows/ci.yml` runs the full `pytest` suite with no marker exclusions on every PR, so no special marker or CI-workflow-level required check is needed (adding one would risk gating it out). A `# guardrail: IDENT-05` docstring is enough for discoverability. Must NOT depend on the `real_disc` hardware marker.
- **D-16 (survives Phase 5 promotion):** Assert on **stable disc identity** (e.g. persisted `disc_id` / release) and on the normalized structure returned when looking up by the fixed `dvd1-*` string — NOT on `dvd1-*` literally being `response["fingerprint"]`. After Phase 5, `dvd1-*` resolves as an alias to a `dvdread1-*` primary; the assertion tolerates `fingerprint` becoming the new primary while confirming the same disc/structure resolves, mirroring the pattern already proven in `test_disc_identity_aliases.py`.

### Repo hygiene (CLEAN-01, CLEAN-02) — Claude's discretion, defaulted
- **D-17:** Delete the disposable one-shot patch scripts at repo root: `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py` (their edits are already applied per CONCERNS.md).
- **D-18:** Relocate any still-useful dev/UAT tooling (`run_uat.py`, `create_uat_dirs.py`, and `verify_t11.py` if still needed) under `scripts/` rather than deleting, so nothing load-bearing is lost. Planner to confirm which are obsolete vs. still used.
- **D-19:** Gitignore generated UAT artifacts: `uat_results.json` and `uat_dirs/`. Success criterion #5 requires the repo root to contain none of the named debug scripts and UAT artifacts to be gitignored.

### Claude's Discretion
- Exact concurrency-control code structure (savepoint mechanics, where the catch/re-resolve loop sits) — planner/executor detail, within D-01/D-03.
- Precise Pydantic model naming and field types for the alias objects (within D-04–D-07).
- Final disposition of each individual root script (delete vs. relocate) once obsolescence is confirmed (within D-17/D-18).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Disc identity & alias migration (the spine of this phase)
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` — The staged `dvd1 primary → aliases → dvdread1 primary` migration. Defines WHY `dvd1-*` must stay a stable, permanently resolvable alias and why the IDENT-02 race fix must precede Phase 5 promotion. Read before touching any identity/alias/write-path code.
- `docs/OVID-product-spec.md` (Milestone 0.2) — Source of truth for the v0.2.0 exit criteria this milestone completes.
- `docs/fingerprint-spec.md` — OVID-DVD-1 / `dvd1-*` structural fingerprint definition (relevant to the IDENT-05 golden fixture).

### Requirements & research
- `.planning/REQUIREMENTS.md` — IDENT-01, IDENT-02, IDENT-05, VERIFY-02, CLEAN-01, CLEAN-02 full text (and `[guardrail]` markers).
- `.planning/ROADMAP.md` §"Phase 1" — Success criteria (5) and the hard sequencing rule vs. Phase 5.
- `.planning/research/SUMMARY.md` — Research that surfaced the guardrail constraints.

### Codebase touch points (verified via graph, live tree)
- `api/app/disc_identity.py` — `resolve_disc_identity`, `attach_lookup_aliases`, `resolve_existing_disc_for_identities`; where the check-then-insert race lives (IDENT-02).
- `api/app/models.py` — `Disc.fingerprint` / `DiscIdentityAlias.fingerprint` already `unique=True` (the load-bearing constraint for D-01).
- `api/app/routes/disc.py` — `_disc_to_response` (~line 123) builds the lookup response (IDENT-01); `_validate_status_transition` (~line 68) and the submit-conflict inline `disputed` flip are what VERIFY-02 consolidates; the two submission call sites are the IDENT-02 fix sites.
- `api/app/schemas.py` — `DiscLookupResponse` (~line 49), where `fingerprint_aliases` is added (IDENT-01).
- `web/lib/api.ts` — `DiscLookupResponse` TypeScript interface, updated in lockstep (compile-time enforced).
- `api/tests/conftest.py` — in-memory SQLite `TestClient` harness + `seed_test_disc` fixture (governs how D-02 and D-13 are tested).
- `api/tests/test_disc_verify.py` — existing `TestVerifyStateMachine`; the `verified→verified` behavior to reconcile (see D-12 research-note).
- `api/tests/test_disc_identity_aliases.py` — existing alias-resolution test pattern the IDENT-05 test (D-16) mirrors for Phase-5 survivability.
- `.github/workflows/ci.yml` — runs full `pytest` on every PR, no marker exclusions (why D-15 needs no special gating).
- `.planning/codebase/CONCERNS.md` — documents the root-script cruft and rate-limit debt (context for CLEAN-01/02).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Disc.fingerprint` / `DiscIdentityAlias.fingerprint` `unique=True` constraints (`api/app/models.py`): already provide the DB-level guarantee the IDENT-02 fix relies on — no schema change needed for D-01.
- `DiscIdentityConflict` raise-and-catch pattern (`api/app/disc_identity.py` → `routes/disc.py`): the exact template for VERIFY-02's `VerificationTransitionError` (D-10).
- `seed_test_disc` fixture (`api/tests/conftest.py`): reused directly for the IDENT-05 golden record (D-13).
- `test_disc_identity_aliases.py` alias-resolution assertions: the pattern IDENT-05's Phase-5-survivable assertion mirrors (D-16).

### Established Patterns
- Domain logic lives in dedicated modules OUTSIDE `routes/` (`disc_identity.py`, `sync.py`) and is imported into thin route handlers — VERIFY-02's `verification.py` follows this (D-08).
- Domain exceptions raised in the service, caught at the route boundary, rendered as a structured JSON envelope with `request_id` — extend for verification (D-10).
- API tests run against in-memory SQLite via `TestClient`; `conftest.py` patches `DATABASE_URL` before any `app` import — dictates that all Phase 1 mechanisms must be SQLite-testable (D-02).

### Integration Points
- `GET /v1/disc/{fingerprint}` response contract fans out to `ovid-client`, ARM shim, and `web/lib/api.ts` — IDENT-01 must be additive to avoid a coordinated multi-consumer release (D-07).
- `verification.py` becomes a dependency of Phase 2 (two-contributor workflow) — design the function boundary as the Phase 2 seam (D-12).
</code_context>

<specifics>
## Specific Ideas

- MusicBrainz alias-object shape (`primary` boolean flag) is the explicit precedent for the IDENT-01 response design — consistent with OVID's "MusicBrainz for video discs" framing.
- The `disputed`-status write must become a single grep-able chokepoint (`flag_dispute`) — the whole point of VERIFY-02 is that you can `grep` for exactly one writer of that status.
</specifics>

<deferred>
## Deferred Ideas

- **Two-contributor confirmation + anti-Sybil weighting** — belongs to Phase 2 (VERIFY-01/03/04). Phase 1 only builds the `verification.py` state-machine module it will consume; it does not implement confirmation counting, a confirmations table, or rate-limit gating (D-12).
- **`dvdread1-*` promotion / dual-string submission** — Phase 5 (IDENT-03/04). Phase 1's IDENT-01 response shape and IDENT-05 test are designed to survive that promotion without rework.
- **Rate-limiting / Redis multi-worker fix** — Phase 3 (INFRA-01..04). Surfaced in CONCERNS.md alongside the root-script cruft, but out of Phase 1 scope (only the repo-hygiene half of that concern is in scope here).
- **ARM shim versioned interface (ARM-02)** — Phase 8. CONCERNS.md flags the file-swap shim, but the versioned-contract fix is launch-readiness scope, not this phase.

</deferred>

---

*Phase: 1-Alias-Layer Hardening & Repo Hygiene*
*Context gathered: 2026-07-05*
