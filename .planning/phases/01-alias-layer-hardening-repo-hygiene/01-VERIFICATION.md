---
phase: 01-alias-layer-hardening-repo-hygiene
verified: 2026-07-05T00:00:00Z
status: passed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: No — initial verification
---

# Phase 01: Alias Layer Hardening & Repo Hygiene Verification Report

**Phase Goal:** Close the alias write-path and verification correctness gaps — and clean up ad-hoc repo cruft — so the codebase is safe to build BD fingerprinting, dvdread1-* promotion, and OAuth linking on top of.

**Verified:** 2026-07-05
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | IDENT-02 [guardrail]: concurrent alias-insert AND disc-row insert paths are race-safe (insert-first / catch IntegrityError / savepoint / re-resolve) | ✓ VERIFIED | `api/app/disc_identity.py:143-159` (`attach_lookup_aliases`) and `api/app/routes/disc.py:524-557` (`register_disc`), `:607-...` (`submit_disc`) all wrap inserts in `db.begin_nested()`, catch `sqlalchemy.exc.IntegrityError` specifically, call `db.expire_all()`, and re-resolve. Deterministic (non-threaded) race tests exist and pass: `api/tests/test_disc_identity_race.py` (5 tests) + `api/tests/test_disc_submit.py::TestDiscRowRace::test_new_fingerprint_losing_race_converges_to_one_disc`. Ran directly: all pass. |
| 2 | IDENT-01: `GET /v1/disc/{fingerprint}` returns every known `fingerprint_aliases` string, primary-first | ✓ VERIFIED | `api/app/schemas.py:49` (`FingerprintAliasResponse`), `:77` (`fingerprint_aliases` field on `DiscLookupResponse`); `api/app/models.py:109-112` (`order_by="DiscIdentityAlias.created_at, DiscIdentityAlias.id"`); `api/app/routes/disc.py:283-296` (`_disc_to_response` builds primary-first then alias-order list) and 3 `selectinload(Disc.identity_aliases)` sites (lines 336, 363, 443). `test_disc_lookup.py::test_lookup_returns_fingerprint_aliases` ran directly and passes. Web `DiscLookupResponse` interface additive-only; `npx tsc --noEmit` ran clean. |
| 3 | IDENT-05 [guardrail]: permanent unmarked regression proves an existing `dvd1-*` fingerprint still resolves with correct, frozen data | ✓ VERIFIED | `api/tests/test_disc_identity_regression.py` exists, is unmarked (no pytest marker), collected by plain `pytest tests/` (confirmed via `--co -q`), asserts frozen structure against a hardcoded expected dict independent of seed variables, and deliberately omits asserting the top-level `fingerprint` literal (survives Phase 5 promotion, D-16). Ran directly and passes. |
| 4 | VERIFY-02: status transitions run through one guarded module; an already-verified disc cannot be silently flipped to disputed | ✓ VERIFIED | `grep -nE 'status[[:space:]]*=[[:space:]]*"disputed"' api/app/routes/disc.py` returns nothing; the only such assignment in `api/app/` is `api/app/verification.py:69` inside `flag_dispute`, which returns `False`/no-write when `disc.status == "verified"`. `grep -nE '\.status[[:space:]]*=[[:space:]]*"(verified|unverified|disputed)"' api/app/routes/disc.py` returns nothing — all 5 former inline mutations now call `verify()`/`flag_dispute()`/`resolve_dispute()` (confirmed by reading `_handle_existing_disc`, `resolve_dispute_endpoint`, `verify_disc`). A2 contract (mismatch against verified disc stays verified, 200, audit `DiscEdit`) implemented at `routes/disc.py:213-240` and tested by `test_mismatched_submission_against_verified_disc_stays_verified` (ran directly, passes). |
| 5 | CLEAN-01: repo root has none of `fix_test.py`/`fix_test2.py`/`test_script.py`/`verify_t11.py` | ✓ VERIFIED | `ls` of all four paths returns "No such file or directory"; `scripts/run_uat.py` and `scripts/create_uat_dirs.py` exist (relocated, git-mv preserved history per `git log`). |
| 6 | CLEAN-02: `uat_results.json` + `uat_dirs/` are gitignored and untracked | ✓ VERIFIED | `.gitignore` contains both entries (lines 37-38); `git check-ignore uat_results.json uat_dirs/` returns both paths; `git ls-files \| grep -E '^(uat_results\.json\|uat_dirs/)'` returns empty (fully untracked). |

**Score:** 6/6 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/verification.py` | Sole guarded writer of `disc.status`, flat-function module | ✓ VERIFIED | Exists; `VerificationTransitionError`, `LEGAL_TRANSITIONS` (zero entries targeting "disputed"), `verify`/`flag_dispute`/`resolve_dispute` all present and correct per plan spec |
| `api/tests/test_verification.py` | Unit coverage of state machine | ✓ VERIFIED | 10 tests, all pass when run directly |
| `api/app/disc_identity.py` | Race-safe `attach_lookup_aliases` | ✓ VERIFIED | Insert-first/catch/re-resolve inside `db.begin_nested()`, catches `IntegrityError` specifically |
| `api/tests/test_disc_identity_race.py` | Deterministic (non-threaded) race regression | ✓ VERIFIED | 5 tests, no `threading`/`asyncio.gather`, all pass |
| `api/app/routes/disc.py` | Wired to `verification.py`; disc-row insert race-safe | ✓ VERIFIED | Imports `verify/flag_dispute/resolve_dispute/VerificationTransitionError`; savepoint-guards `submit_disc`/`register_disc` inserts |
| `api/tests/test_disc_submit.py`, `test_dispute.py` | Behavior-change tests updated + new race/A2 tests | ✓ VERIFIED | `TestDiscRowRace`, `test_mismatched_submission_against_verified_disc_stays_verified` present and pass |
| `api/app/schemas.py` | `FingerprintAliasResponse` + additive `fingerprint_aliases` field | ✓ VERIFIED | Both present |
| `api/app/models.py` | Deterministic `order_by` on `identity_aliases` | ✓ VERIFIED | `order_by="DiscIdentityAlias.created_at, DiscIdentityAlias.id"` |
| `web/lib/api.ts` | Optional `fingerprint_aliases?` field | ✓ VERIFIED | `npx tsc --noEmit` clean |
| `api/tests/test_disc_lookup.py` | New alias-shape test | ✓ VERIFIED | `test_lookup_returns_fingerprint_aliases` passes |
| `api/tests/test_disc_identity_regression.py` | Permanent unmarked `dvd1-*` guardrail | ✓ VERIFIED | Exists, unmarked, collected, passes |
| `.gitignore`, `scripts/run_uat.py`, `scripts/create_uat_dirs.py` | Repo hygiene artifacts | ✓ VERIFIED | All present; four one-shot scripts confirmed absent |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `routes/disc.py` | `app.verification` | import of `verify/flag_dispute/resolve_dispute/VerificationTransitionError` | ✓ WIRED | `routes/disc.py:26-31` |
| `routes/disc.py` (submit/register) | savepoint + `IntegrityError` re-resolve | `db.begin_nested()` + `except IntegrityError` | ✓ WIRED | Lines 524-557 (register_disc), 607+ (submit_disc), confirmed via grep and read |
| `disc_identity.py::attach_lookup_aliases` | savepoint + re-resolve | `db.begin_nested()` + `except IntegrityError` + `db.expire_all()` | ✓ WIRED | Lines 143-159 |
| `_disc_to_response` | `Disc.identity_aliases` relationship | `selectinload` at 3 call sites | ✓ WIRED | Confirmed 3 occurrences via grep |
| `schemas.py::DiscLookupResponse` | `web/lib/api.ts::DiscLookupResponse` | additive optional field | ✓ WIRED | `tsc --noEmit` clean, no consumer breakage |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full API suite green | `cd api && ./.venv/bin/python -m pytest tests/ -q` | 255 passed, 22 warnings (pre-existing, documented in deferred-items.md, unrelated to this phase's files) | ✓ PASS |
| Verification state machine tests | `pytest tests/test_verification.py -v` | 10/10 passed | ✓ PASS |
| Alias-insert race tests | `pytest tests/test_disc_identity_race.py -v` | 5/5 passed | ✓ PASS |
| dvd1-* regression guardrail | `pytest tests/test_disc_identity_regression.py -v` | 1/1 passed | ✓ PASS |
| Disc-row race + A2 contract tests | `pytest tests/test_disc_submit.py -k "race or verified_disc_stays"` | 2/2 passed | ✓ PASS |
| Alias-exposure lookup test | `pytest tests/test_disc_lookup.py -k alias` | 1/1 passed | ✓ PASS |
| Web typecheck | `cd web && npx tsc --noEmit` | No errors found | ✓ PASS |
| Repo hygiene: 4 scripts absent, 2 relocated | `ls` checks | Confirmed absent / present | ✓ PASS |
| UAT artifacts gitignored + untracked | `git check-ignore` / `git ls-files` | Both ignored, zero tracked paths | ✓ PASS |
| No debt markers in phase-touched files | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` | No matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| IDENT-01 | 01-04 | Lookup exposes all fingerprint_aliases | ✓ SATISFIED | `schemas.py`, `models.py`, `routes/disc.py` wiring confirmed; test passes |
| IDENT-02 [guardrail] | 01-02, 01-03 | Alias + disc-row write paths race-safe | ✓ SATISFIED | Both write paths savepoint-guarded; deterministic race tests pass |
| IDENT-05 [guardrail] | 01-05 | Permanent unmarked dvd1-* regression | ✓ SATISFIED | Test exists, unmarked, collected, passes |
| VERIFY-02 | 01-01, 01-03 | Guarded single-writer verification module | ✓ SATISFIED | `verification.py` is sole writer; wired into routes; A2 contract implemented and tested |
| CLEAN-01 | 01-06 | Ad-hoc root scripts removed/relocated | ✓ SATISFIED | Confirmed absent/relocated |
| CLEAN-02 | 01-06 | UAT artifacts gitignored | ✓ SATISFIED | Confirmed gitignored + untracked |

No orphaned requirements: REQUIREMENTS.md maps exactly these 6 IDs to Phase 1, all marked Complete, and all 6 are claimed across the phase's plan frontmatters (`requirements:` fields in 01-01 through 01-06 PLAN.md). Cross-reference is exact — no unmapped/unclaimed IDs found.

### Anti-Patterns Found

None. Grep for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` across all files modified/created by this phase (`verification.py`, `disc_identity.py`, `routes/disc.py`, `schemas.py`, `models.py`, and the new test files) returned zero matches.

### Human Verification Required

None. All must-haves are programmatically verifiable and were verified directly against the running test suite and source code (not inferred from SUMMARY.md claims).

### Gaps Summary

No gaps found. All 6 observable truths derived from the phase's ROADMAP success criteria are verified against the actual codebase:

- Both write paths (alias-insert in `disc_identity.py`, disc-row insert in `routes/disc.py`'s `submit_disc`/`register_disc`) implement the insert-first/savepoint/catch-IntegrityError/re-resolve pattern, each backed by a deterministic (non-threaded) regression test that was executed directly and passes.
- The lookup response's `fingerprint_aliases` field is correctly modeled, ordered, wired at all 3 serialization call sites, and additive on the TypeScript side.
- The `dvd1-*` regression guardrail is unmarked, collected by the standard `pytest tests/` invocation, and asserts frozen structure independent of seed variables.
- `verification.py` is the sole writer of `status="disputed"` across all of `api/app/` (confirmed by grep with zero other hits), and the "silent flip" bug this phase was created to close is closed — verified by both source inspection and a passing dedicated regression test.
- Repo hygiene items (CLEAN-01/CLEAN-02) are fully applied and confirmed via direct filesystem/git checks, not merely claimed in SUMMARY.md.

The full API test suite (255 tests) passes cleanly when run directly in this verification session, and the web typecheck passes with zero errors. Requirements traceability against `.planning/REQUIREMENTS.md` is exact — all 6 IDs assigned to Phase 1 are satisfied, with no orphaned or unaccounted requirements.

---

_Verified: 2026-07-05_
_Verifier: Claude (gsd-verifier)_

---

## Post-Review Remediation (orchestrator, 2026-07-05)

After the automated verification passed (6/6 must-haves), a deep code review (`01-REVIEW.md`) surfaced findings that were each independently verified against source and dispositioned:

- **CR-01 (Critical) — FIXED.** `submit_disc`'s `except IntegrityError` was scoped to the whole function body (not just the `begin_nested()` savepoint), so a post-savepoint constraint violation (e.g. duplicate `title_index`) was misclassified as a fingerprint race and recovered without a rollback → aborted transaction / raw 500 on PostgreSQL (masked by the SQLite test harness). Restructured into two try-blocks mirroring `register_disc`; post-savepoint `IntegrityError` now returns an enveloped `400 invalid_submission`. Commit `32ea477`. Regression test added.
- **WR-01 (Warning) — FIXED.** `verify()` ran the self-submission guard before the idempotency check, giving the original submitter a spurious 403 on an already-verified disc. Reordered idempotency-first. Commit `f69c32a`.
- **WR-03 (Warning) — FIXED (user-scoped to Phase 1).** `submit_disc` against an existing `pending_identification` disc (bare ARM registration) hit the same-user 409 guard / mis-routed a different user's first metadata to dispute. Added a guarded `identify()` transition (`pending_identification → unverified`, sole-writer invariant preserved) and a first-metadata identification path. Commit `e1a9c5b`.
- **WR-02 (Warning) — SCOPED TO PHASE 5 (user decision).** Cross-table fingerprint race between `discs.fingerprint` and `disc_identity_aliases.fingerprint` (independent UNIQUE constraints, no cross-table arbitration). Recorded as an explicit Phase 5 must-address in ROADMAP.md.
- **IN-02 / IN-03 — FIXED.** Renamed misleading `_sqlite_uuid_compat` → `_enable_sqlite_wal` (UUID compat confirmed native to the dialect); added the missing `fingerprint_aliases?` field to the web `DiscSubmitRequest` type.
- **InsecureKeyLengthWarning — FIXED at root** (incidental short JWT keys in auth tests lengthened; not weak-key-behavior tests).
- **Remaining warnings (2, third-party):** `slowapi` `asyncio.iscoroutinefunction` deprecation (already at latest `0.1.10`; upstream) and Starlette `httpx`/`TestClient` notice (would require an `httpx2` dependency decision). Proven third-party; left for a dependency/policy decision.

VERIFY-02 sole-writer invariant re-confirmed after remediation (all `disc.status =` writes remain inside `verification.py`; zero in routes). Full API suite: **262 passed, 0 failed.**
