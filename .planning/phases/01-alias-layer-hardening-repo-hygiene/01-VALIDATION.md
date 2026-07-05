---
phase: 1
slug: alias-layer-hardening-repo-hygiene
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-05
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (API, against in-memory SQLite via FastAPI TestClient) |
| **Config file** | `api/` (pytest invoked as `pytest tests/` from `api/`) |
| **Quick run command** | `cd api && python -m pytest tests/ -q` |
| **Full suite command** | `cd api && python -m pytest tests/` |
| **Estimated runtime** | ~30 seconds (SQLite TestClient, confirm on first run) |

---

## Sampling Rate

- **After every task commit:** Run the task's focused file(s) with `-x`, then `cd api && python -m pytest tests/ -q`
- **After every plan wave:** Run `cd api && python -m pytest tests/` (VERIFY-02 changes ripple into submit/dispute/verify suites)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | VERIFY-02 | T-01-V2 | Self-verify raises; LEGAL_TRANSITIONS has no `disputed` target | unit | `cd api && python -m pytest tests/test_verification.py -x` | ❌ created in RED task | ⬜ pending |
| 01-01-02 | 01 | 1 | VERIFY-02 | T-01-V1 | `flag_dispute` refuses a verified disc (returns False, no write) | unit | `cd api && python -m pytest tests/test_verification.py -x` | ✅ (same file) | ⬜ pending |
| 01-01-03 | 01 | 1 | VERIFY-02 | — | Module imports without route cycle; conventions parity | unit | `cd api && python -m pytest tests/test_verification.py -x` | ✅ | ⬜ pending |
| 01-02-01 | 02 | 1 | IDENT-02 | T-01-R1 | Losing-race alias insert converges to one disc (no split) | unit | `cd api && python -m pytest tests/test_disc_identity_race.py -x` | ❌ created in RED task | ⬜ pending |
| 01-02-02 | 02 | 1 | IDENT-02 | T-01-R1 / T-01-R2 | Savepoint insert + re-resolve; cross-disc collision → DiscIdentityConflict | unit | `cd api && python -m pytest tests/test_disc_identity_race.py -x` | ✅ | ⬜ pending |
| 01-02-03 | 02 | 1 | IDENT-02 | T-01-R1 | Savepoint scope; no stale identity map / PendingRollbackError | unit | `cd api && python -m pytest tests/test_disc_identity_race.py tests/test_disc_identity_aliases.py -x` | ✅ | ⬜ pending |
| 01-03-01 | 03 | 2 | VERIFY-02 | T-01-V1 | Verified disc stays verified on mismatched submission (RED first) | integration | `cd api && python -m pytest tests/test_disc_submit.py tests/test_dispute.py -x` | ⚠ update existing | ⬜ pending |
| 01-03-02 | 03 | 2 | VERIFY-02 | T-01-V1 / T-01-V2 | Single `disputed` writer; verify idempotent-200/no-edit; self-verify 403 | integration | `cd api && python -m pytest tests/test_disc_submit.py tests/test_dispute.py tests/test_disc_verify.py -x` | ✅ (must stay green) | ⬜ pending |
| 01-03-03 | 03 | 2 | IDENT-02 | T-01-R1 | Disc-row race converges to one disc row; full suite green | integration | `cd api && python -m pytest tests/test_disc_submit.py -x && python -m pytest tests/ -q` | ✅ | ⬜ pending |
| 01-04-01 | 04 | 3 | IDENT-01 | T-01-I2 | `fingerprint_aliases` shape: primary-first, is_primary, insertion order (RED) | integration | `cd api && python -m pytest tests/test_disc_lookup.py -x` | ⚠ extend existing | ⬜ pending |
| 01-04-02 | 04 | 3 | IDENT-01 | T-01-I1 / T-01-I2 | Additive serializer + derived method + eager-load; NO migration | integration | `cd api && python -m pytest tests/test_disc_lookup.py tests/test_disc_identity_aliases.py -x` | ✅ | ⬜ pending |
| 01-04-03 | 04 | 3 | IDENT-01 | T-01-I2 | Web `DiscLookupResponse` optional field typechecks (strict) | type | `cd web && npx tsc --noEmit` | ✅ (existing file) | ⬜ pending |
| 01-05-01 | 05 | 1 | IDENT-05 | T-01-D1 | Golden `dvd1-*` resolves with frozen structure vs. independent dict | integration | `cd api && python -m pytest tests/test_disc_identity_regression.py -x` | ❌ created in task | ⬜ pending |
| 01-05-02 | 05 | 1 | IDENT-05 | T-01-D1 | Unmarked; unconditionally collected by `pytest tests/` (no hardware) | integration | `cd api && python -m pytest tests/ --co -q` | ✅ | ⬜ pending |
| 01-06-01 | 06 | 1 | CLEAN-01 | T-01-C1 | 4 one-shot scripts removed; UAT tooling relocated + byte-compiles | VCS | `test ! -e fix_test.py && test -f scripts/run_uat.py && python -m py_compile scripts/run_uat.py scripts/create_uat_dirs.py` | manual/VCS | ⬜ pending |
| 01-06-02 | 06 | 1 | CLEAN-02 | T-01-C1 | UAT artifacts untracked (git rm --cached) + gitignored | VCS | `git ls-files \| grep -E '^(uat_results\.json\|uat_dirs/)'` returns empty | manual/VCS | ⬜ pending |
| 01-06-03 | 06 | 1 | CLEAN-01/02 | — | Full API suite green after removals (nothing load-bearing lost) | integration | `cd api && python -m pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*(Planner populates this map from the finalized PLAN.md task IDs — one row per task, tying each requirement to its automated `pytest` command.)*

---

## Wave 0 Requirements

- [x] Test harness exists (`api/tests/conftest.py` — in-memory SQLite `TestClient`, `seed_test_disc` fixture, WAL/StaticPool). No framework install needed.
- [x] Missing test files are scaffolded IN-PLAN as the first (RED) task of the plan that owns them — no separate Wave 0 pass required:
  - `api/tests/test_verification.py` → created by Plan 01 Task 1 (RED)
  - `api/tests/test_disc_identity_race.py` → created by Plan 02 Task 1 (RED)
  - `api/tests/test_disc_identity_regression.py` → created by Plan 05 Task 1
  - `api/tests/test_disc_submit.py` / `test_dispute.py` → UPDATED by Plan 03 Task 1 (RED) for the guarded dispute behavior + new "verified stays verified" test
  - `api/tests/test_disc_lookup.py` → EXTENDED by Plan 04 Task 1 (RED) for the `fingerprint_aliases` shape

*Note (from 01-RESEARCH.md): the API suite already runs `pytest tests/` on every PR with no marker exclusions. VERIFY-02 is a deliberate behavior CHANGE — Plan 03 updates `test_disc_submit.py:115,198` and `test_dispute.py:81` (which currently encode the silent verified→disputed flip) and adds a "verified stays verified" test. IDENT-05 (Plan 05) adds a new `dvd1-`-prefixed golden-fixture seeder.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Multi-worker concurrent-submission race safety (IDENT-02) | IDENT-02 | True concurrency needs real Postgres + parallel gunicorn workers; SQLite TestClient is single-threaded | Deferred: document a deterministic IntegrityError-path unit test (savepoint retry) as the automated proxy; note real-concurrency check as manual/load. |

*Automated proxy preferred wherever possible — see planner tasks.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or scaffold their missing test file in the plan's RED task
- [x] Sampling continuity: every task carries an automated command; no 3 consecutive tasks without automated verify
- [x] Missing test references are created in-plan (RED tasks) — no orphan MISSING references
- [x] No watch-mode flags (all commands are single-shot `pytest`/`tsc`/VCS checks)
- [x] Feedback latency ~30s (< target)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner) — 17 task rows mapped, one automated command each.
