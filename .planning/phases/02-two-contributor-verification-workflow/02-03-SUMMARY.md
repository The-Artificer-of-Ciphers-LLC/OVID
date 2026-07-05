---
phase: 02-two-contributor-verification-workflow
plan: 03
subsystem: api
tags: [verification, confirmation-flow, anti-sybil, structural-match, route-retirement, ip-hash, tdd, verify-01, verify-03, verify-04]

# Dependency graph
requires:
  - phase: 02-two-contributor-verification-workflow (plan 01)
    provides: "structural_match(existing_disc, body, db) -> bool — tolerant proof-of-possession gate over withheld structure"
  - phase: 02-two-contributor-verification-workflow (plan 02)
    provides: "evaluate_confirmation(db, disc, actor, request) -> ConfirmationGate(hard_blocked, trust_ok, ip_hash); DiscEdit.ip_hash column; ip_subnet_hash()"
  - phase: 01-alias-layer-hardening-repo-hygiene
    provides: "verification.py state machine (verify/flag_dispute), A2 stays-verified contract, DiscEdit audit table"
provides:
  - "Two-contributor confirmation live end-to-end: unverified→verified requires a distinct contributor's structural re-submission via POST /v1/disc, gated by the anti-Sybil pre-check (D-01/D-03/D-04)"
  - "client_ip_hash(request) -> str | None public helper in anti_sybil.py (reused by the gate and the create-edit capture)"
  - "Retired bodyless POST /v1/disc/{fingerprint}/verify route (D-02) — the no-proof Sybil bypass is gone"
  - "429 rate_limited (Retry-After) + 403 insufficient_trust confirmation responses"
affects: [02-04 (lookup redaction pairs with this anti-echo gate), 02-05 (docs — /verify removal + privacy-policy IP-hash addendum)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Anti-Sybil gate as a pre-check in the route (429/403) BEFORE any status write — the gate wraps verify(), never mutates disc.status (VERIFY-02)"
    - "Verify trigger = structural_match AND _releases_match; structural mismatch OR release mismatch falls through to the existing flag_dispute path (A3 truth table)"
    - "ip_hash captured on both the create DiscEdit (submitter subnet ref) and the verify DiscEdit (confirmer subnet), fail-open to NULL"
    - "Route retirement: delete route + decorator + its whole test file; audit all callers across app/web/arm/docs/tests before deletion (D-02)"

key-files:
  created:
    - api/tests/test_confirmation_flow.py
    - api/tests/test_route_retired.py
  modified:
    - api/app/routes/disc.py
    - api/app/anti_sybil.py
    - api/tests/conftest.py
    - api/tests/test_disc_submit.py
    - api/tests/test_disc_edits.py
    - api/tests/test_disc_identity_aliases.py
  deleted:
    - api/tests/test_disc_verify.py

key-decisions:
  - "A3 confirmed: structural equality gates VERIFY; release-consistency retained as the DISPUTE trigger (structural-match+release-mismatch → dispute)"
  - "OQ4: cooldown hard-block → 429 rate_limited with Retry-After (CONFIRMATION_COOLDOWN_WINDOW_HOURS*3600); soft-score reject → 403 insufficient_trust; both keep the {request_id, error, message} envelope"
  - "429/403 gate returns db.commit() first to persist alias attachments (parity with the same-submitter 409 path); no status change on either"
  - "Retired-route caller audit found 2 extra test callers beyond the plan's blast radius (test_disc_edits, test_disc_identity_aliases) — fixed inline per no-defer"

patterns-established:
  - "_handle_existing_disc gains a request: Request param threaded from both submit_disc call sites; gate → structural-match → verify() sequence in the different-user branch"
  - "Shared matrix_matching_submit_payload() conftest helper kept in lockstep with seed_test_disc so a re-submission structurally matches"

requirements-completed: [VERIFY-01, VERIFY-03, VERIFY-04]

coverage:
  - id: D1
    description: "A distinct second contributor's structural re-submission via POST /v1/disc flips unverified→verified; the original submitter's re-submission returns 409 (never self-confirms); the bodyless /verify route is gone (VERIFY-01/D-01/D-02)"
    requirement: "VERIFY-01"
    verification:
      - kind: integration
        ref: "tests/test_confirmation_flow.py::TestStructuralConfirmation::test_distinct_contributor_structural_resubmit_verifies,test_self_resubmit_returns_409; tests/test_route_retired.py::TestVerifyRouteRetired"
        status: pass
    human_judgment: false
  - id: D2
    description: "Tolerant structural equality end-to-end: benign rip jitter (relabeled codec, ±2s duration) still verifies; a real structural difference (wrong chapter_count) routes to dispute even when the release matches (D-03)"
    requirement: "VERIFY-01"
    verification:
      - kind: integration
        ref: "tests/test_confirmation_flow.py::TestStructuralConfirmation::test_benign_rip_jitter_still_verifies,test_real_structural_difference_does_not_verify,test_structural_match_release_mismatch_disputes"
        status: pass
    human_judgment: false
  - id: D3
    description: "An already-verified disc is never silently flipped: a 3rd structural mismatch stays verified (200) and records a dispute_attempted audit edit (VERIFY-03/A2)"
    requirement: "VERIFY-03"
    verification:
      - kind: integration
        ref: "tests/test_confirmation_flow.py::TestVerifiedDiscNotFlipped::test_third_mismatch_against_verified_stays_verified"
        status: pass
    human_judgment: false
  - id: D4
    description: "Confirmation is gated BEFORE any status write: cooldown exceeded → 429 (Retry-After + request_id); fresh account + same subnet → 403 insufficient_trust; fresh account + distinct subnet verifies; the verify DiscEdit carries the confirmer ip_hash (VERIFY-04/D-04/D-06)"
    requirement: "VERIFY-04"
    verification:
      - kind: integration
        ref: "tests/test_confirmation_flow.py::TestAntiSybilGate::test_cooldown_hard_block_returns_429,test_fresh_account_same_subnet_returns_403,test_fresh_account_distinct_subnet_verifies,test_confirmation_verify_edit_carries_ip_hash"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-07-05
status: complete
---

# Phase 2 Plan 03: Confirmation Gate + /verify Route Retirement Summary

**The two-contributor trust model is now live end-to-end: a disc stays unverified until a SECOND, DISTINCT contributor reproduces its WITHHELD structure via `POST /v1/disc` — that structural match (gated by the anti-Sybil cooldown/weighted pre-check, not release fields) flips unverified→verified — and the no-proof bodyless `POST /v1/disc/{fingerprint}/verify` route is deleted (D-01/D-02/D-03/D-04).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-05T22:57:43Z
- **Completed:** 2026-07-05T23:03:15Z
- **Tasks:** 3 (TDD: RED → GREEN → regression sweep)
- **Files:** 2 created, 6 modified, 1 deleted

## Accomplishments
- Wired the two Wave-1 primitives into the confirmation path in `_handle_existing_disc` (`routes/disc.py`): `evaluate_confirmation` runs as a pre-check (cooldown → 429 `rate_limited` with `Retry-After`; soft-score → 403 `insufficient_trust`), then `structural_match` (D-01/D-03) replaces the public-field `_releases_match` as the *verify* trigger while release-consistency is retained as the *dispute* trigger (A3). The verify `DiscEdit` carries `gate.ip_hash` (D-06).
- Threaded a `request: Request` parameter into `_handle_existing_disc` from both `submit_disc` call sites (the up-front duplicate check and the losing-race recovery), and captured the submitter's `ip_hash` on the new-disc create `DiscEdit` so a future confirmer's subnet can be compared (D-06 IP-diversity).
- Retired the bodyless `POST /v1/disc/{fingerprint}/verify` route entirely (D-02) — route + decorator + banner deleted, replaced by a RETIRED comment — and deleted `test_disc_verify.py` (11 tests). No `disc.status =` assignment remains in `routes/` (VERIFY-02).
- All status writes remain inside `verification.py`; the gate and structural match wrap `verify()`/`flag_dispute()` and never touch `disc.status` directly.
- Full API suite green: **290 passed**.

## Task Commits

Each task committed atomically (TDD gate sequence):

1. **Task 1: RED — confirmation-flow + route-retired behavior tests** — `d31a92c` (test)
2. **Task 2: GREEN — gate + structural-match wiring; retire /verify route** — `2658eb5` (feat)
3. **Task 3: Regression sweep — update retired-route callers** — `2ab6454` (fix)

_RED confirmed 7 failing (structural-difference, verified-stays-verified, cooldown 429, same-subnet 403, ip_hash capture, both route-retired assertions) against the current unwired routes before Task 2._

## Files Created/Modified
- `api/app/routes/disc.py` (mod) — `_handle_existing_disc`: `request` param + anti-Sybil gate (429/403) + `structural_match`-gated verify with `ip_hash` capture; `submit_disc` create-edit `ip_hash`; `verify_disc` route DELETED.
- `api/app/anti_sybil.py` (mod) — extracted `client_ip_hash(request)` public helper (pure refactor; `evaluate_confirmation` now reuses it — identical behavior, 26 Wave-1 tests still green).
- `api/tests/test_confirmation_flow.py` (new) — 11 integration tests across the A3 truth table + the anti-Sybil gate (429/403, ip_hash capture, distinct-subnet verify).
- `api/tests/test_route_retired.py` (new) — asserts the retired path 404/405s (seeded, authed, unknown fingerprint).
- `api/tests/conftest.py` (mod) — `matrix_matching_submit_payload()` in lockstep with `seed_test_disc`.
- `api/tests/test_disc_submit.py` (mod) — auto-verify test now reproduces the withheld structure (release-only match no longer verifies).
- `api/tests/test_disc_edits.py` (mod) — confirmation via second-contributor re-submission instead of the retired route.
- `api/tests/test_disc_identity_aliases.py` (mod) — removed the obsolete `/verify` alias-resolution test (coverage retained by /edits, /resolve, lookup tests).
- `api/tests/test_disc_verify.py` (deleted) — targeted the retired endpoint (D-02).

## Decisions Made
- **A3 confirmed:** structural equality gates VERIFY (proof of possession over withheld structure); release-consistency is retained as the DISPUTE trigger. Truth table: structural-match + release-match → verify; structural-match + release-mismatch → dispute; structural-mismatch → dispute (A2 keeps a verified disc verified).
- **OQ4 confirmed:** cooldown hard-block → 429 `rate_limited` with a `Retry-After` header (`CONFIRMATION_COOLDOWN_WINDOW_HOURS * 3600` seconds); soft-score rejection → 403 `insufficient_trust`. Both preserve the `{request_id, error, message}` envelope and `x-request-id` header.
- **Gate-blocked returns commit first:** on 429/403 the alias attachments already applied at the top of `_handle_existing_disc` are committed (parity with the same-submitter 409 path); no status transition occurs on either path.
- **`client_ip_hash` extracted rather than reaching into `_ip_hash_salt`** from the route — a small public wrapper in `anti_sybil.py` keeps the create-edit capture and the gate DRY and behavior-identical.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two retired-route callers beyond the plan's declared blast radius**
- **Found during:** Task 3 (full regression sweep)
- **Issue:** The D-02 caller audit found `api/tests/test_disc_edits.py::test_edits_after_verify_has_two_entries` and `api/tests/test_disc_identity_aliases.py::test_verify_accepts_alias_and_returns_primary` both POST to the retired `/verify` route — neither was listed in the plan's/RESEARCH's blast radius (which named only `test_disc_verify.py`). They failed once the route was deleted.
- **Fix:** Rewrote the edits test to confirm via a second-contributor re-submission (D-01); removed the obsolete alias-resolution test (that endpoint is gone; alias→primary resolution stays covered by the /edits, /resolve, and lookup route tests).
- **Files modified:** `api/tests/test_disc_edits.py`, `api/tests/test_disc_identity_aliases.py`
- **Commit:** `2ab6454`

**2. [Rule 3 - Blocking] `test_disc_submit.py` auto-verify test assumed release-only match**
- **Found during:** Task 2 (its verify command includes `test_disc_submit.py`)
- **Issue:** `test_duplicate_matching_metadata_auto_verifies` seeded a disc with a different structure than the submitted `VALID_PAYLOAD` and expected a verify from a release-only match — which no longer verifies under structural-match semantics.
- **Fix:** Seeded an unverified disc owned by a different user and confirmed with `matrix_matching_submit_payload()` (reproduces the withheld structure).
- **Files modified:** `api/tests/test_disc_submit.py`
- **Commit:** `2658eb5`

**3. [Rule 3 - Support] Shared matching-payload helper added to conftest.py**
- **Reason:** Both the new confirmation-flow tests and the updated submit test need a payload that structurally matches `seed_test_disc`. Added `matrix_matching_submit_payload()` to `conftest.py` (its correct DRY home — it mirrors the seed) rather than duplicating the structure across test files.
- **Files modified:** `api/tests/conftest.py`
- **Commit:** `d31a92c`

## Caller Audit for the Retired /verify Route (D-02) — Follow-ups for Plan 02-05

Full repo audit (grep across `api/`, `web/`, `ovid-client/`, `arm/`, `docs/`):
- **Code:** no callers in `web/`, `ovid-client/`, or `arm/` — confirms D-02's rationale (the UI never reads discs). Only `api/app/routes/disc.py` defined it (deleted).
- **Tests:** `test_disc_verify.py` (deleted), `test_disc_edits.py` + `test_disc_identity_aliases.py` (fixed inline — see deviations).
- **Docs — deferred to Plan 02-05 (out of this plan's file scope):**
  - `docs/api-reference.md:235` — endpoint reference — remove.
  - `docs/docker-quickstart.md:72` — API table row — remove.
  - `docs/OVID-technical-spec.md:664` — endpoint spec — remove/annotate as retired.
  - `docs/contributing.md:32` — "you can verify it" prose — reframe to structural re-submission.
  - `CHANGELOG.md:31` — historical `/verify` line — annotate as retired in the 0.2.0 entry.
  - Plan 02-05 also owns the privacy-policy IP-hash addendum (D-06) and the `OVID_IP_HASH_SALT` / `FORWARDED_ALLOW_IPS` deployment notes carried over from Plan 02-02.

## Threat Flags

None — this plan introduces no new network/auth/file surface. It *removes* surface (the `/verify` route, threat T-2-09) and realizes the mitigations for T-2-05 (self-verify via the 409 re-submission path), T-2-06 (A2 stays-verified), T-2-01 (structural_match over withheld structure), and T-2-02 (cooldown pre-check → 429). All high-severity threats in the register are mitigated.

## Known Stubs

None — no placeholder/empty-data stubs introduced. All new paths are fully wired and exercised by passing tests.

## Deferred Issues

Two pre-existing third-party test-infra deprecation warnings surface on every full-suite run — both already logged in `deferred-items.md` by Plans 02-01/02-02, out of scope here (they require dependency upgrades, not code in this plan, and originate in files untouched by it):
- `StarletteDeprecationWarning` (httpx/Starlette `TestClient`) from `fastapi/testclient.py:1`.
- `slowapi` `asyncio.iscoroutinefunction` deprecation from `slowapi/extension.py:720` (relates to Phase 3 rate-limit hardening).

## User Setup Required

None to run/test. Deployment notes carried by Plan 02-05: set `OVID_IP_HASH_SALT` to enable the IP-diversity signal (fail-open when unset) and configure `FORWARDED_ALLOW_IPS` on the prod proxy so `request.client.host` reflects the real client IP.

## Next Phase Readiness
- The confirmation gate + structural-match trigger are live; `_disc_to_response` redaction (D-09) is the paired anti-echo half owned by Plan 02-04 and is untouched here (structure is still returned on reads — the withholding lands in 02-04).
- Plan 02-05 has the concrete docs/CHANGELOG follow-up list above plus the privacy-policy addendum.
- No blockers. Full API suite green (290 passed).

## Self-Check: PASSED

---
*Phase: 02-two-contributor-verification-workflow*
*Completed: 2026-07-05*
