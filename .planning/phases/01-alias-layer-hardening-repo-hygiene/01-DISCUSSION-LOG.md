# Phase 1: Alias-Layer Hardening & Repo Hygiene - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 1-Alias-Layer Hardening & Repo Hygiene
**Areas discussed:** Race-safety mechanism, Alias API response shape, Verification state machine, dvd1-* regression fixture
**Mode:** advisor (research-backed comparison tables) — 4 parallel research agents, standard calibration tier

---

## Race-safety mechanism (IDENT-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Unique constraint + catch conflict | Insert-first, catch IntegrityError, re-resolve. UNIQUE already in models.py; only option testable on in-memory SQLite. | ✓ |
| Postgres advisory lock | pg_advisory_xact_lock keyed on fingerprint; Postgres-only, needs branch/no-op on SQLite + a real-PG integration test that doesn't exist yet. | |
| SELECT … FOR UPDATE | Pessimistic lock; chicken-and-egg (no parent row for a new disc); SQLite no-ops FOR UPDATE. | |
| SERIALIZABLE + retry loop | Strongest but pulls in app-wide transaction-retry infra; Postgres-only. | |

**User's choice:** Unique constraint + catch conflict (recommended)
**Notes:** Deciding factor was testability against the existing SQLite `TestClient` harness — SQLite raises `IntegrityError` on UNIQUE violation exactly like Postgres. Research confirmed the `unique=True` constraints already exist in `api/app/models.py`, so this is the smallest fix. Planning must add savepoint/nested-transaction handling so one alias collision doesn't roll back the whole submission (CONTEXT D-03).

---

## Alias API response shape (IDENT-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Objects w/ method, additive | `fingerprint_aliases: [{fingerprint, method, is_primary}]`; keep top-level `fingerprint`; primary in array with is_primary:true; primary-first + insertion order; strictly additive. | ✓ |
| Flat string list | `fingerprint_aliases: list[str]`; loses method label → brittle prefix-parsing in 3 consumers. | |
| Objects, primary folded in (breaking) | Drop top-level `fingerprint`; single collection but breaking, needs coordinated ovid-client + ARM + web release. | |

**User's choice:** Objects w/ method, additive (recommended)
**Notes:** Chosen to survive Phase 5 promotion (primary/method become structural, not prefix-parsed) and Phase 7 UI without a second breaking change. MusicBrainz alias-object precedent (`primary` boolean) cited — apt given OVID's framing. `web/lib/api.ts` `DiscLookupResponse` updated in lockstep (compile-time enforced).

---

## Verification state machine (VERIFY-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Flat functions + transition table | `verification.py` flat funcs + module-level frozenset table; `disputed` reachable ONLY via distinct `flag_dispute()`; domain exception raised+caught. Matches disc_identity.py convention. | ✓ |
| Session-bound service class | `VerificationService(db)`; bundles session+behavior but introduces first OOP-service pattern into a flat-function codebase. | |
| Third-party FSM library | `transitions` package; battle-tested but disproportionate dependency for a ~4-state machine. | |

**User's choice:** Flat functions + transition table (recommended)
**Notes:** The silent-flip bug lives in the submit-conflict branch of `disc.py` (`existing.status = "disputed"` inline). Closing it means `flag_dispute()` becomes the single grep-able writer of `disputed`. Research flagged a discrepancy in `test_disc_verify.py` on `verified→verified` (400 vs idempotent 200) — carried into CONTEXT as a research-note (D-12) to reconcile against live tests before freezing the transition table. Phase 2 seam preserved without over-building.

---

## dvd1-* regression fixture (IDENT-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Golden ORM seed via GET /v1/disc | Reuse seed_test_disc; assert resolution + frozen structure (independent expected dict); plain unmarked pytest in api/tests/ (CI runs all, no hardware). | ✓ |
| Synthetic constructed row | Fabricated dvd1-* string; simplest but weaker — doesn't prove the real algorithm round-trips. | |
| Golden JSON snapshot file | Decoupled/reviewable but invites "just re-approve"; adds snapshot dependency. | |

**User's choice:** Golden ORM seed via GET /v1/disc (recommended)
**Notes:** Assert resolution AND frozen structure (independent expected dict, not re-derived from seed). Unmarked pytest so CI runs it on every PR with no gating risk; no `real_disc` hardware dependency. Assertions target stable disc identity/structure (not literal `response["fingerprint"] == dvd1-*`) so the test survives Phase 5 promotion when `dvd1-*` becomes an alias.

---

## Claude's Discretion

- Exact concurrency-control code structure (savepoint mechanics, catch/re-resolve loop placement) — within D-01/D-03.
- Pydantic model naming/field types for alias objects — within D-04–D-07.
- Repo hygiene disposition (CLEAN-01/02): delete disposable patch scripts, relocate still-useful tooling under `scripts/`, gitignore `uat_results.json` + `uat_dirs/` — defaulted, not separately discussed; planner confirms which root scripts are obsolete vs. still used.

## Deferred Ideas

- Two-contributor confirmation + anti-Sybil weighting → Phase 2 (builds on the `verification.py` module created here).
- `dvdread1-*` promotion / dual-string submission → Phase 5.
- Rate-limiting / Redis multi-worker fix → Phase 3 (only the repo-hygiene half of the CONCERNS.md rate-limit item is in Phase 1 scope).
- ARM shim versioned interface (ARM-02) → Phase 8.
