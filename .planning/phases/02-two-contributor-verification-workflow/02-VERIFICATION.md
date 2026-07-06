---
phase: 02-two-contributor-verification-workflow
verified: 2026-07-05T00:00:00Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification: No — initial verification
---

# Phase 2: Two-Contributor Verification Workflow Verification Report

**Phase Goal:** The two-contributor trust model is live end-to-end and resistant to cheap Sybil abuse, without relying on the deferred v0.3.0 dispute-flagging UI.
**Verified:** 2026-07-05
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A submitted disc entry stays `unverified` until a second, distinct contributor independently confirms the fingerprint; self-confirmation is rejected (VERIFY-01) | ✓ VERIFIED | `api/app/verification.py:40-58` `verify()` raises `VerificationTransitionError` when `disc.submitted_by == actor.id`; `api/app/routes/disc.py:288-296` returns 409 `conflict` before the gate even runs on a same-user re-submission; verify only fires when `structural_match()` (proof-of-possession over withheld structure) AND `_releases_match()` both pass (`disc.py:331-359`). Behaviorally proven by `test_confirmation_flow.py::TestStructuralConfirmation::test_distinct_contributor_structural_resubmit_verifies` (passing) and `::test_self_resubmit_returns_409` (passing) — independently re-run, both pass. |
| 2 | An already-`verified` disc cannot be flipped back to `disputed`/`unverified` by a later third submission — only the explicit dispute-resolution path can move it (VERIFY-03, guardrail) | ✓ VERIFIED | `api/app/verification.py:79-89` `flag_dispute()` returns `False` (no write) when `disc.status == "verified"` — the ONLY function that ever sets `disputed`, and `LEGAL_TRANSITIONS` (lines 30-37) has no tuple targeting `"disputed"` at all, closing the write path entirely except through this guarded function. `routes/disc.py:386-413` on `flag_dispute` refusal records a `dispute_attempted` audit `DiscEdit` and returns 200 `status: "verified"` — never a silent flip. Behaviorally proven by `test_confirmation_flow.py::TestVerifiedDiscNotFlipped::test_third_mismatch_against_verified_stays_verified` (independently re-run, passes): seeds a `verified` disc, submits a structural mismatch from a second contributor, asserts `disc.status == "verified"` after and a `dispute_attempted` edit exists. |
| 3 | Confirmation actions are rate-limited per account and weighted by account-age/IP-diversity signals; a merely-distinct `user_id` is not by itself accepted as proof of independence (VERIFY-04, guardrail) | ✓ VERIFIED | `api/app/anti_sybil.py::evaluate_confirmation` (lines 200-243) composes a Postgres-backed cooldown hard floor (`_recent_confirmation_count` over `disc_edits` `edit_type="verify"` rows, worker-safe — no in-memory limiter) with a weighted, offsetting, fail-open trust score over account-age (`ACCOUNT_AGE_SOFT_CUTOFF_HOURS`) and IP-subnet diversity (`ip_subnet_hash`, salted /24-/48 HMAC-SHA256). `routes/disc.py:298-324` gates BEFORE any status write: `hard_blocked` → 429 `rate_limited` + `Retry-After`; `not trust_ok` → 403 `insufficient_trust`. A distinct `user_id` alone never suffices — the fresh-account+same-subnet Sybil signature (score -2) is the only combination that blocks. Behaviorally proven by three independently re-run passing tests: `test_cooldown_hard_block_returns_429`, `test_fresh_account_same_subnet_returns_403`, `test_fresh_account_distinct_subnet_verifies`. |
| 4 | The full submitted structural payload of an `unverified` disc is withheld from public reads until verification (D-09 anti-echo redaction) | ✓ VERIFIED | `api/app/routes/disc.py:459-463` — `_disc_to_response`'s `titles_resp` is `[]` iff `disc.status == "unverified"`, else the full built response; `release_resp` and `fingerprint_aliases_resp` are unconditional (D-11). Behaviorally proven by independently re-run passing tests in `test_lookup_redaction.py`: unverified GET returns `titles == []` while `release`/`fingerprint_aliases`/`confidence`/`request_id` remain populated; verified/disputed GETs return full `titles` (redaction correctly scoped, Pitfall 6 honored); ARM's read fields (`release.{title,year,imdb_id,tmdb_id}`, `confidence`, `format`) are intact (D-10 no-op). |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `api/app/structural_match.py` | `structural_match(existing_disc, body, db) -> bool` tolerant structural-equality gate | ✓ VERIFIED | Exists, substantive (89 lines, real Counter-multiset/tolerance logic), no `disc.status =` or `db.commit()` inside it (comparison-only, VERIFY-02 boundary intact) |
| `api/app/anti_sybil.py` | `evaluate_confirmation()`, `ConfirmationGate`, `ip_subnet_hash()`, cooldown + weighted-score helpers | ✓ VERIFIED | Exists, substantive (244 lines), no status writes, named UPPER_SNAKE thresholds, `client_ip_hash()` public wrapper added in Plan 03 |
| `api/app/models.py` — `DiscEdit.ip_hash` + `idx_disc_edits_user_type_created` | nullable column + composite index | ✓ VERIFIED | `models.py:381` `ip_hash: Mapped[str \| None] = mapped_column(String(64))`; `__table_args__` index at lines 389-397, matches (`user_id`, `edit_type`, `created_at`) |
| `api/alembic/versions/900000000004_add_disc_edits_ip_hash_index.py` | chained migration, revision 900000000004 → down_revision 900000000003 | ✓ VERIFIED | Present; `upgrade()` adds column + index; `downgrade()` reverses in symmetric order |
| `api/app/routes/disc.py` — `_handle_existing_disc` gated + verify_disc route DELETED | gate → structural-match → verify() sequence; retired route removed | ✓ VERIFIED | Wiring at lines 298-359 matches exactly; retired-route banner at lines 950-957 confirms deletion with no live handler; `grep -rn "verify_disc\|/verify\""` across `api/app/` returns no matches |
| `api/app/routes/disc.py` — `_disc_to_response` unverified redaction branch | single status-branch redaction | ✓ VERIFIED | Lines 459-463, single `disc.status == "unverified"` branch, no other status branches added |
| `api/tests/test_structural_match.py` | 9 boundary tests both directions | ✓ VERIFIED | 9 tests present (`test_exact_match`, `test_reordered_audio_tracks_match`, `test_relabeled_codec_matches`, `test_duration_within_tolerance_matches`, `test_extra_title_no_match`, `test_different_chapter_count_no_match`, `test_missing_audio_track_no_match`, `test_different_language_no_match`, `test_duration_outside_tolerance_no_match`); independently re-run, all pass |
| `api/tests/test_anti_sybil.py` | IP hash + cooldown + weighted-score suite | ✓ VERIFIED | 17 tests across `TestIpSubnetHash`, `TestCooldown`, `TestWeightedScore`, `TestSaltFailOpen`; independently re-run, all pass |
| `api/tests/test_confirmation_flow.py` | integration suite over the A3 truth table + anti-Sybil gate | ✓ VERIFIED | 11 tests present covering VERIFY-01/03/04 end-to-end; independently re-run, all pass |
| `api/tests/test_route_retired.py` | retired route 404/405 assertions | ✓ VERIFIED | 3 tests (seeded fp, authed, unknown fp); independently re-run, all pass |
| `api/tests/test_lookup_redaction.py` | redaction behavior tests | ✓ VERIFIED | 7 tests across `TestUnverifiedRedaction` + `TestRedactionScopedToUnverified`; independently re-run, all pass |
| `api/tests/test_disc_verify.py` | DELETED | ✓ VERIFIED | File confirmed absent (`ls` returns "No such file or directory") |
| `.env.example` — `OVID_IP_HASH_SALT` | documented optional var | ✓ VERIFIED | Present at line 82, marked optional/fail-open |
| `docs/privacy.md` | IP-hash data-category disclosure | ✓ VERIFIED | Discloses salted/24-/48-truncated hash, ~90-day retention (honestly worded "eligible for deletion", no purge job claimed), GDPR basis, D-14 cooldown-vs-limiter note |
| `docs/api-reference.md`, `docker-quickstart.md`, `OVID-technical-spec.md` | retired `/verify` route removed | ✓ VERIFIED | `grep -n "fingerprint}/verify"` across all three returns no matches |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `_handle_existing_disc` | `evaluate_confirmation()` | pre-check before any status write | ✓ WIRED | `routes/disc.py:300` — gate computed before the structural-match branch; 429/403 short-circuit at lines 301-324, both `db.commit()` first (persists alias attachments), no status transition on either path |
| `_handle_existing_disc` | `structural_match()` | verify trigger (replaces `_releases_match`-only) | ✓ WIRED | `routes/disc.py:331-333` — `if structural_match(existing, body, db) and _releases_match(...)`: verify only fires on BOTH; structural mismatch OR release mismatch falls through to `flag_dispute` |
| `_handle_existing_disc` verify branch | `verify()` (sole status writer) | `app.verification.verify` | ✓ WIRED | Line 335; `ip_hash=gate.ip_hash` captured on the resulting `DiscEdit` (line 346) |
| `submit_disc` new-disc path | `client_ip_hash(request)` | ip_hash capture on create edit | ✓ WIRED | Lines 907-913 — the create `DiscEdit` carries `ip_hash=client_ip_hash(request)` so a future confirmer's subnet can be compared via `_submitter_ip_hash` |
| `_disc_to_response` | `disc.status` | redaction branch | ✓ WIRED | Lines 459-463 — single conditional, `release_resp`/`fingerprint_aliases_resp` unconditional |
| `arm/identify_ovid.py::_extract_result` | redacted GET response | D-10 no-op | ✓ VERIFIED (no-op confirmed) | Reads only `release.{title,year,imdb_id,tmdb_id}`, `confidence`, `format` — never `titles`/tracks; asserted directly by `test_unverified_arm_fields_intact_d10` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full phase-relevant test set (structural_match, anti_sybil, confirmation_flow, route_retired, lookup_redaction) | `cd api && .venv/bin/pytest tests/test_confirmation_flow.py tests/test_route_retired.py tests/test_structural_match.py tests/test_anti_sybil.py tests/test_lookup_redaction.py -q` | 46 passed | ✓ PASS |
| Full API regression suite (run once) | `cd api && .venv/bin/pytest -q` | 297 passed | ✓ PASS |
| No stray reference to retired route/symbol in `api/app/` | `grep -rn "verify_disc\|/verify\""` | no matches | ✓ PASS |
| No stray reference to retired endpoint in published docs | `grep -n "fingerprint}/verify" docs/api-reference.md docs/docker-quickstart.md docs/OVID-technical-spec.md` | no matches | ✓ PASS |
| No debt markers introduced in phase files | `grep -n -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER" api/app/structural_match.py api/app/anti_sybil.py api/app/routes/disc.py api/app/verification.py` | no matches | ✓ PASS |

Both pre-existing third-party deprecation warnings (`StarletteDeprecationWarning` from `httpx`/Starlette TestClient; `slowapi`'s `asyncio.iscoroutinefunction` deprecation) surface identically before and after this phase's changes, are documented in `deferred-items.md`, originate entirely in installed dependencies untouched by this phase, and are explicitly attributed to Phase 3 (INFRA) dependency-upgrade scope. Independently confirmed these are not newly introduced.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| VERIFY-01 | 02-01, 02-03, 02-04 | Second, distinct contributor confirms via structural re-submission; self-confirm rejected | ✓ SATISFIED | See truths #1, #4 above |
| VERIFY-03 | 02-03 | Already-verified disc cannot be flipped by later mismatched submission | ✓ SATISFIED | See truth #2 above |
| VERIFY-04 | 02-02, 02-03, 02-05 | Rate-limited + anti-Sybil weighted confirmation; distinct user_id insufficient | ✓ SATISFIED | See truth #3 above; storage + docs both land |

No orphaned requirements — REQUIREMENTS.md's traceability table maps VERIFY-01/03/04 all to "Phase 2 / Complete", matching the plans' declared `requirements:` frontmatter exactly.

**Minor doc-tracking note (informational, non-blocking):** REQUIREMENTS.md's top checkbox list (lines 45-46) still shows `- [ ]` (unchecked) for VERIFY-03 and VERIFY-04 even though the Traceability table at the bottom of the same file marks both "Complete." This is a stale-checkbox inconsistency within REQUIREMENTS.md itself (not a code or test gap — the underlying code and passing tests fully satisfy both requirements) and does not affect phase-goal achievement.

### Anti-Patterns Found

None in the phase's modified/created source files (`structural_match.py`, `anti_sybil.py`, `routes/disc.py`, `verification.py`, `schemas.py`). No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers, no empty-return stubs, no hardcoded-empty-data patterns in the gate/match/redaction logic.

**Informational finding — deferred doc follow-up not landed:** Plan 02-03's SUMMARY explicitly flagged `CHANGELOG.md:31` ("`POST /v1/disc/{fingerprint}/verify` — idempotent status promotion") as a caller-audit follow-up item "for Plan 02-05." Plan 02-05's PLAN.md `files_modified` list did not include `CHANGELOG.md`, and its SUMMARY confirms only `docs/privacy.md`, `docs/api-reference.md`, `docs/docker-quickstart.md`, `docs/OVID-technical-spec.md`, `docs/contributing.md`, `.env.example`, `mkdocs.yml` were touched — `CHANGELOG.md` was not addressed. On inspection, the CHANGELOG.md:31 line is a historical entry under the already-published `[0.1.0]` release section describing what that release added at the time — rewriting historical changelog entries retroactively is not standard practice, and no "Removed" entry documenting the 0.2.0-era retirement of this endpoint exists in the `[0.2.0]` section either. This is a minor documentation completeness gap (the retirement was never mentioned in the `[0.2.0]` changelog as a "Removed" item), not a functional defect — it does not affect the phase's success criteria and was not part of any plan's declared `must_haves`/`files_modified`. Flagged here for visibility; does not block phase completion.

### Human Verification Required

None. All four success criteria are exercised by automated integration/unit tests that were independently re-run during this verification (46/46 phase-relevant tests pass; 297/297 full API suite passes). No visual, real-time, or external-service behavior is in scope for this phase.

### Gaps Summary

No gaps block phase-goal achievement. All four ROADMAP success criteria are implemented, wired, and behaviorally proven by passing tests that were independently re-executed (not merely trusted from SUMMARY.md prose). The retired `POST /v1/disc/{fingerprint}/verify` route has no live handler and no residual callers in `api/`, `web/`, `ovid-client/`, or `arm/`; its test file is genuinely deleted. Two minor, non-blocking documentation-tracking items are noted above for visibility (stale REQUIREMENTS.md checkboxes; an un-landed CHANGELOG.md follow-up) — neither affects the two-contributor trust model's runtime behavior or test coverage.

---

_Verified: 2026-07-05_
_Verifier: Claude (gsd-verifier)_

## Remediation Addendum

**Added:** 2026-07-05
**Reason:** subsequent deep adversarial code review

The initial goal verification above (2026-07-05) confirmed all 4 must-haves (VERIFY-01, VERIFY-03, VERIFY-04, D-09 anti-echo redaction) held under the happy-path two-contributor flow and its existing test suite (297 passed). A subsequent **deep, adversarial code review** (`02-REVIEW.md`) went further — tracing the full call chain rather than trusting the happy-path tests — and found 3 CRITICAL bypasses that each independently let a single actor satisfy these same must-haves without a genuine second, independent contributor:

- **CR-01** (self-confirmation via register → identify → resubmit) directly undermined must-have #1 (VERIFY-01: distinct-contributor confirmation, self-confirmation rejected) — `_identify_existing_disc` never set `submitted_by`, so a stale registrant pointer let one human satisfy both self-confirmation guards on their own resubmission.
- **CR-02** (zero-title vacuous `structural_match`) directly undermined must-have #1's proof-of-possession requirement and is adjacent to must-have #4 (D-09 anti-echo redaction) — a title-less disc could be "confirmed" using nothing but publicly-searchable release metadata, exactly the echo attack the redaction gate exists to prevent.
- **W6** (single-actor verify-bypass via `/resolve`) directly undermined must-have #1/#3 — a trusted/editor/admin role could flip a merely-`unverified` (never-disputed) disc straight to `verified` with a single action, no second contributor involved.

An independent adversarial verifier live-reproduced CR-01 end-to-end before any fix landed, confirming it was a real, exploitable bypass and not a review artifact.

All three were fixed TDD-style (failing regression test committed first, then the minimal fix) and are now covered by dedicated regression tests:

| Finding | Must-have affected | Fix commit | Regression test |
|---|---|---|---|
| CR-01 | VERIFY-01 (truth #1) | `938cdac` (red: `1679f5b`) | `api/tests/test_identify_self_confirm.py` |
| CR-02 | VERIFY-01 / D-09 (truths #1, #4) | `fd5c808` (red: `625b522`) | `api/tests/test_structural_match.py`, `api/tests/test_disc_submit.py` |
| W6 | VERIFY-01 / VERIFY-03 (truths #1, #2) | `a34b98e` (red: `ba09d48`) | `api/tests/test_dispute.py` |

The remaining critical (CR-03, anti-Sybil IP-diversity dead behind the production reverse proxy) and the confirmed warnings (W2, W3, W4) were also fixed, but bear on must-have #3's (VERIFY-04) *robustness under production topology and concurrency* rather than reversing this verification's original truth assertions. See `02-REVIEW-FIX.md` for the complete finding→verdict→resolution→commit mapping.

Full regression suite after all remediation: **310 passed** (was 297 at initial verification). With these fixes, all four must-haves verified above now hold not only under the happy-path tests originally exercised, but also under the adversarial conditions the deep review specifically probed for.

---

_Addendum added: 2026-07-05_
_Source: 02-REVIEW.md (deep adversarial review), 02-REVIEW-FIX.md (remediation record)_
