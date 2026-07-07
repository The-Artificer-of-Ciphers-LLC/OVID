---
phase: 05-adr-0001-completion-dvdread1-promotion
verified: 2026-07-06T00:00:00Z
status: human_needed
score: 4/4 success criteria verified (28/28 plan must-have truths verified in code)
behavior_unverified: 0
overrides_applied: 0
re_verification:
  # No previous VERIFICATION.md existed — initial verification.
human_verification:
  - test: "On a real `docker compose` + Postgres deployment, run `python scripts/promote_dvdread1.py` (optionally with `-f <compose-file>`). Confirm it (a) captures the current OVID_MODE, (b) flips the api service to OVID_MODE=mirror and restarts, (c) runs `alembic upgrade head`, (d) restores the captured OVID_MODE on both success and failure, and (e) prints the CRITICAL manual-recovery command if the restore step itself fails."
    expected: "Writes are 405-gated during the window, reads are briefly interrupted across the two restarts, discs with a recorded dvdread1-* alias come back with dvdread1-* primary, discs without one stay on dvd1-*, and OVID_MODE ends on its original value regardless of migration outcome."
    why_human: "scripts/promote_dvdread1.py orchestrates `docker compose exec/up` subprocesses against a live api container + Postgres; the real end-to-end restart/restore round-trip cannot be exercised in this static/CI environment (flagged untestable-here in 05-07-SUMMARY). The script's capture/restore/finally logic is statically verified below; only the live-deployment behavior needs a human."
---

# Phase 05: ADR-0001 Completion — dvdread1 Promotion Verification Report

**Phase Goal:** The staged libdvdread migration finishes — clients submit every known Disc Identity string, and `dvdread1-*` becomes the primary DVD fingerprint while `dvd1-*` remains a stable, permanently resolvable alias.
**Verified:** 2026-07-06
**Status:** human_needed (all code-checkable must-haves VERIFIED; one live-deployment cutover item routed to human)
**Re-verification:** No — initial verification.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **IDENT-03** — client submits every known Disc Identity string; API stores non-primary strings as aliases (client payload AND ARM auto-register path) | ✓ VERIFIED | Client: `identify_dvd()` flip `ovid-client/src/ovid/disc_identity.py:118-122` (primary=dvdread1, aliases=[dvd1] on success; `:100-116` primary=dvd1, aliases=[] on libdvdread failure). ARM: `fingerprint_disc_with_identity()` `arm/identify_ovid.py:74-100` returns `(fingerprint, aliases)`; `submit_to_ovid(fingerprint_aliases=…)` `:233-287` sends `fingerprint_aliases` only when non-empty; threaded through `arm/identify.py` `_try_ovid` `:110-146` → `submit_to_ovid(... fingerprint_aliases=ovid_fingerprint_aliases)` `:298-303`. API stores non-primary as aliases via `attach_lookup_aliases()` `api/app/routes/disc.py:826,948`. |
| 2 | **IDENT-04** — new submissions/lookups show `dvdread1-*` primary; each disc with a recorded `dvdread1-*` alias promoted in ONE txn/disc; discs without one stay on `dvd1-*` | ✓ VERIFIED | Server primary selection: `_select_primary()` `api/app/routes/disc.py:99-120` prefers dvdread1-*, else passes through. Promotion transform: `promote_one_disc()` `api/app/migrations_support.py:78-136` (delete dvdread1 alias, set `discs.fingerprint`=dvdread1, re-insert old dvd1 as alias, idempotent WHERE-guard); `promote_all_dvdread1_discs()` `:139-175` commits per-disc (commit-as-you-go, resumable). Migration `900000000006_promote_dvdread1_primary.py:41` calls it (down_revision `900000000005`). |
| 3 | **IDENT-05 (guardrail)** — pre-migration `dvd1-*` still resolves after promotion, zero fragmentation; Phase-1 CI regression test still green & unmodified; no path demotes an already-promoted disc on old-client `dvd1-*` resubmit | ✓ VERIFIED | `api/tests/test_disc_identity_regression.py` unmodified since Phase-1 commit `98d8020` (git log), passes standalone (`1 passed`); asserts identity/structure by fixed `dvd1-*` string, NOT literal top-level fingerprint (D-16, docstring `:19-30`). Promotion keeps old dvd1-* as the sole alias row (`test_promotes_disc_with_dvdread1_alias` asserts `alias_fingerprints == {"dvd1-promote-a"}`). No-demote: `Disc.fingerprint` never reassigned on existing-disc paths (only set in `Disc(...)` constructor on new-disc branch); `test_old_client_resubmit_cannot_demote_promoted_disc` `test_disc_submit.py:678`. |
| 4 | **WR-02 carry-forward** — `fingerprint_registry` table w/ global UNIQUE(fingerprint) + `register_fingerprint()` wired into every new-disc/alias SAVEPOINT | ✓ VERIFIED | Model `FingerprintRegistry` `api/app/models.py:157-185` (String(50) UNIQUE fingerprint, UUID disc_id FK `ondelete="CASCADE"`, disc_id index). `register_fingerprint()` `api/app/disc_identity.py:164-176`. Wired: alias path `attach_lookup_aliases` `:145-148` (inside `begin_nested`, before flush); new-disc `register_disc` `:782-804`; new-disc `submit_disc` `:885-925`. Migration `900000000005` creates table + backfills. |

**Score:** 4/4 ROADMAP success criteria verified; 28/28 plan-level must-have truths verified against source. 0 behavior-unverified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/models.py` FingerprintRegistry | WR-02 arbitration table | ✓ VERIFIED | `:157-185`, UNIQUE+FK CASCADE+index |
| `api/app/disc_identity.py` register_fingerprint | savepoint-scoped helper | ✓ VERIFIED | `:164-176`, no self-flush; called `:147` |
| `api/app/routes/disc.py` _select_primary | server-side primary pick | ✓ VERIFIED | `:99-120` |
| `api/app/migrations_support.py` | promote_one/all + backfill | ✓ VERIFIED | `:78-136`, `:139-175`, `:178-262` |
| `api/alembic/.../900000000005_add_fingerprint_registry.py` | registry DDL + backfill | ✓ VERIFIED | created_at `nullable=False`, UNIQUE(fingerprint), FK ondelete CASCADE, idx; down_revision 900000000004 |
| `api/alembic/.../900000000006_promote_dvdread1_primary.py` | promotion migration | ✓ VERIFIED | calls `promote_all_dvdread1_discs`; down_revision 900000000005 (ordered after 005) |
| `ovid-client/src/ovid/disc_identity.py` identify_dvd | flipped | ✓ VERIFIED | `:77-122` |
| `arm/identify_ovid.py` | identity-aware ARM submit | ✓ VERIFIED | `:74-100`, `:233-287` |
| `arm/tests/` + `.github/workflows/ci.yml` arm-tests | regression guard in CI | ✓ VERIFIED | ci.yml `:82,99`; 12 arm tests pass |
| `scripts/promote_dvdread1.py` | cutover wrapper | ✓ VERIFIED (logic) | `:57-201` capture/restore/finally; live run → human |
| `docs/self-hosting.md` / `docs/deployment.md` | cutover runbook + cross-ref | ✓ VERIFIED | self-hosting `:217-243` (states reads briefly interrupted, Pitfall 3); deployment cross-references |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `attach_lookup_aliases` | `register_fingerprint` | same `begin_nested` SAVEPOINT, pre-flush | ✓ WIRED (`disc_identity.py:145-148`) |
| `register_disc` / `submit_disc` new-disc SAVEPOINT | `register_fingerprint` | same savepoint as Disc insert | ✓ WIRED (`disc.py:803,924`) |
| `_select_primary` | `_method_of` | prefix-derivation reuse (no new column) | ✓ WIRED (`disc.py:116`) |
| migration 900000000006 | `promote_all_dvdread1_discs` | direct import, thin wrapper | ✓ WIRED |
| migration 900000000005 DDL | `FingerprintRegistry` ORM | String(50) UNIQUE + UUID FK CASCADE + idx | ✓ MATCH |
| `identify_dvd` | `Disc.from_path` | consumes `identity_set.primary.fingerprint` generically | ✓ WIRED (no change needed) |
| `arm/identify.py` `_try_ovid`/submit | `arm/identify_ovid.py` fns | aliases thread through miss-fallback path | ✓ WIRED (`identify.py:142,302`) |
| `scripts/promote_dvdread1.py` | `MirrorModeMiddleware` | `OVID_MODE` env var + service restart | ✓ WIRED (env-var toggle) |

### REVIEW Remediation (post-fix current state)

| Finding | Fix | Commit | Current-state evidence |
|---------|-----|--------|------------------------|
| WR-01 schema-nullable mismatch | created_at NOT NULL in migration = model | c4245e4 | migration 005 `:43` `nullable=False`; model `:180-182` non-Optional |
| WR-02 cutover-wrapper safety | fail loudly on capture/restore failure | e2a36e0 | `promote_dvdread1.py` finally-restore `:177-201` + CRITICAL recovery print `:190-193` |
| IN-01 dead code | removed | afdd4d7 | commit present; no dead code found |
| IN-02 false docstring | corrected never-raises docstrings | afdd4d7 | `promote_one_disc` docstring now states "May raise" `:91-94` |
| IN-03 FK ondelete | ON DELETE CASCADE | e8c5c77 | model `:178` + migration 005 `:44` both `ondelete='CASCADE'` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IDENT-03 | 05-03, 05-04, 05-05 | Client submits all identity strings; API stores as aliases | ✓ SATISFIED | Criterion 1 above; REQUIREMENTS.md `:24` marked `[x]`/Complete |
| IDENT-04 | 05-02, 05-05, 05-06 | dvdread1-* promoted to primary DVD fingerprint | ✓ SATISFIED | Criterion 2 above; REQUIREMENTS.md `:25` `[x]`/Complete |
| IDENT-05 | (Phase 1 guardrail) | Permanent CI regression proves dvd1-* still resolves | ✓ SATISFIED | Criterion 3; REQUIREMENTS.md `:136` Complete (checklist box `:26` still `[ ]` — cosmetic; traceability table records Complete) |
| WR-02 | 05-01, 05-05, 05-06 | Cross-table fingerprint arbitration | ✓ SATISFIED | Criterion 4 above |

Note: REQUIREMENTS.md line 26 checklist checkbox for IDENT-05 is unticked while the traceability table (line 136) and the test both show it Complete/passing — a cosmetic checkbox inconsistency, not a code gap (the guardrail exists and is green).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| API suite green | `pytest` (api/.venv) | 360 passed | ✓ PASS |
| ovid-client suite green | `pytest` (ovid-client/.venv) | 242 passed, 16 skipped (real_disc) | ✓ PASS |
| arm suite green | `PYTHONPATH=. pytest arm/tests` | 12 passed | ✓ PASS |
| IDENT-05 regression standalone | `pytest tests/test_disc_identity_regression.py` | 1 passed | ✓ PASS |

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`PLACEHOLDER` markers in any phase-05 source file (models.py, disc_identity.py [both], routes/disc.py, migrations_support.py, scripts/promote_dvdread1.py, arm/identify_ovid.py, both migrations).

### Human Verification Required

**1. Live cutover wrapper end-to-end (docker compose + Postgres)**

- **Test:** Run `python scripts/promote_dvdread1.py` (optionally `-f <compose-file>`) against a real deployment.
- **Expected:** Captures current OVID_MODE → flips api to `mirror` + restart → `alembic upgrade head` → restores captured mode on success AND failure; prints CRITICAL manual-recovery command if the restore itself fails; discs with a dvdread1-* alias promote to dvdread1-* primary, others stay dvd1-*.
- **Why human:** subprocess orchestration of `docker compose exec/up` against a live container + Postgres cannot be exercised in this environment (flagged untestable-here in 05-07-SUMMARY). The capture/restore/finally logic is statically verified (`promote_dvdread1.py:158-201`); only the real restart/restore round-trip needs a human.

### Gaps Summary

No code gaps. All four ROADMAP success criteria (IDENT-03, IDENT-04, IDENT-05, WR-02) are delivered by concrete, wired, tested code, and all five REVIEW findings are remediated in the current tree (verified against commits c4245e4, e8c5c77, e2a36e0, afdd4d7). All three test suites are green at the expected counts. The single outstanding item is the intentionally-untestable live-deployment cutover, routed to human verification — its script logic is statically verified. Per the verification decision tree, one human-verification item makes the overall status `human_needed` rather than `passed`; no gap-closure planning is required.

---

_Verified: 2026-07-06_
_Verifier: Claude (gsd-verifier)_
