---
phase: 06-oauth-account-linking
plan: 04
subsystem: auth
tags: [oauth, noauth, account-linking, account-merge, pending-account-link, sqlalchemy, tdd, security]

# Dependency graph
requires:
  - phase: 06-oauth-account-linking (Plan 01)
    provides: PendingAccountLink ORM model + table (existing_user_id, new_provider, new_provider_id, expires_at TTL, consumed_at single-use marker); OVID_ENV / ALLOW_LOCALHOST_BYPASS auth config
provides:
  - "api/app/auth/merge.py — pure session-free resolve_auth() decision function"
  - "AuthResult dataclass (user | merge_offer) — the login/offer/consume outcome type"
  - "MergeReauthMismatchError + PendingLinkInvalidError merge exception classes"
  - "PendingAccountLink lifecycle helpers: _load_pending_link, _consume_pending_link, _create_user_with_link, _resolve_existing_link"
  - "Confirm-gated, re-auth-required merge decision that closes nOAuth (AUTH-08/AUTH-09)"
affects: [06-05 (rewires provider callbacks to call resolve_auth via a thin finalize_auth wrapper), oauth-account-linking, routes.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure DB-shaped decision function (no Request/session) unit-tested with a bare db_session fixture — no TestClient, no respx"
    - "Verified-email gate as a single choke point: a provider-verified email match OFFERS a PendingAccountLink, never attaches"
    - "Trust-anchor consume: str(freshly.id) == pending.existing_user_id proven via an already-linked provider re-auth, never the new provider's email"
    - "Cross-platform tz normalization for DateTime(timezone=True) TTL comparison (naive SQLite -> aware UTC), mirroring anti_sybil.py"

key-files:
  created:
    - "api/app/auth/merge.py — AuthResult, resolve_auth, merge exceptions, PendingAccountLink CRUD helpers"
    - "api/tests/test_auth_merge.py — 10 isolated resolve_auth unit tests (bare db_session, no TestClient)"
  modified: []

key-decisions:
  - "Single PendingLinkInvalidError covers missing/expired/consumed (plan permitted one combined exception) alongside MergeReauthMismatchError"
  - "email_verified is the sole gate for offering a merge — Mastodon/IndieAuth (email_verified=False, Plan 05) can never reach the offer branch (D-06 as one unified rule)"
  - "Separate-identity path drops to a placeholder email when the claimed address would collide, so the unique-email constraint blocks a silent overwrite (D-07)"
  - "Consume-path duplicate-link guard added so a double-consume cannot crash; consumed_at + TTL remain the primary single-use guards"

patterns-established:
  - "Pattern: resolve_auth is additive/self-contained — copies users.py upsert+exception shapes rather than importing/mutating the live login path, keeping the Wave 2 boundary green"
  - "Pattern: fail-closed merge consume — mismatch/expired/consumed/unknown-reauth all raise before any attach"

requirements-completed: [AUTH-08, AUTH-09]

coverage:
  - id: D1
    description: "Existing (provider, provider_id) link login returns that user with no merge offer (AUTH-06 preserved)"
    requirement: "AUTH-09"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthLoginOfferSeparate::test_existing_link_login_returns_user_no_offer"
        status: pass
    human_judgment: false
  - id: D2
    description: "Provider-verified email matching an existing account creates a PendingAccountLink OFFER (user=None, no attach, no new user) — the nOAuth confirm-gate"
    requirement: "AUTH-08"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthLoginOfferSeparate::test_verified_email_match_creates_offer_no_attach"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unverified email colliding with an existing account forks a SEPARATE identity (different user, non-colliding email), creates no pending row, leaves existing account untouched (D-06/D-07)"
    requirement: "AUTH-08"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthLoginOfferSeparate::test_unverified_colliding_email_forks_separate_identity"
        status: pass
    human_judgment: false
  - id: D4
    description: "Re-auth success: same existing account re-authenticating via an already-linked provider consumes the offer, attaches the new provider, sets consumed_at (D-02)"
    requirement: "AUTH-08"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthConsumePath::test_reauth_success_consumes_and_attaches"
        status: pass
    human_judgment: false
  - id: D5
    description: "Merge-without-reauth: presenting pending_link_id while authenticating as a DIFFERENT account raises MergeReauthMismatchError, no attach, offer not consumed (AUTH-08 required case 3)"
    requirement: "AUTH-08"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthConsumePath::test_merge_without_reauth_different_user_rejected"
        status: pass
    human_judgment: false
  - id: D6
    description: "Single-use + TTL enforced: expired and already-consumed pending links are rejected (PendingLinkInvalidError) and not consumed"
    requirement: "AUTH-08"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py::TestResolveAuthConsumePath::test_expired_pending_rejected + ::test_already_consumed_pending_rejected"
        status: pass
    human_judgment: false
  - id: D7
    description: "resolve_auth is a pure, session-free function unit-tested in isolation with a bare db_session fixture (no TestClient/Request/respx) — AUTH-09"
    requirement: "AUTH-09"
    verification:
      - kind: unit
        ref: "tests/test_auth_merge.py (10 tests, full file)"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-07-06
status: complete
---

# Phase 6 Plan 04: Confirm-gated OAuth Account-Merge Resolver Summary

**Pure, session-free `resolve_auth` (api/app/auth/merge.py) that OFFERS a PendingAccountLink on a provider-verified email match (never a silent merge) and consumes it only when the same account re-authenticates via an already-linked provider — the nOAuth defense for AUTH-08/AUTH-09.**

## Performance

- **Duration:** 18 min
- **Tasks:** 2 (each RED→GREEN)
- **Files modified:** 2 created (merge.py, test_auth_merge.py)
- **Tests:** 10 new resolve_auth unit tests; full api suite 387 passed (up from 377), warning-clean

## Accomplishments
- `resolve_auth` decides login vs. merge-OFFER vs. separate-identity at a single testable choke point; a provider-verified email match yields a `PendingAccountLink` OFFER with `user=None` — never an attach and never a new user (AUTH-08 / D-05).
- Unverified / colliding emails fork a genuinely separate identity via a placeholder email, so the unique-email constraint blocks a silent account overwrite (D-06 / D-07); no pending row is ever created.
- The consume path attaches the new provider only when `str(freshly.id) == str(pending.existing_user_id)` proven via an already-linked provider re-auth; mismatch/expired/consumed/unknown-reauth all fail closed (D-02, AUTH-08 required case 3).
- Fully additive: merge.py copies `users.py`'s upsert/exception shapes and does not touch the live `user_upsert` login path, so the Wave 2 boundary stays green.

## Task Commits

Each task was committed atomically with RED→GREEN TDD ordering:

1. **Task 1 (RED): login/offer/separate-identity tests** - `a21bf2b` (test)
2. **Task 1 (GREEN): resolve_auth login/offer/separate-identity path** - `fcaa11f` (feat)
3. **Task 2 (RED): re-auth consume-path tests** - `0c9fa60` (test)
4. **Task 2 (GREEN): resolve_auth re-auth consume path** - `771f386` (feat)

_TDD gate compliance: both `test(...)` commits precede their `feat(...)` counterparts._

## Files Created/Modified
- `api/app/auth/merge.py` (new) - `AuthResult` dataclass; `resolve_auth`; `MergeReauthMismatchError` / `PendingLinkInvalidError`; helpers `_resolve_existing_link`, `_create_user_with_link`, `_load_pending_link`, `_consume_pending_link`, `_ensure_aware`.
- `api/tests/test_auth_merge.py` (new) - 10 isolated unit tests + `_create_user_with_link` / `_create_pending_link` bare-session seeding helpers (no TestClient/respx).

## Decisions Made
- Combined missing/expired/consumed into a single `PendingLinkInvalidError` (plan explicitly permitted one exception) alongside `MergeReauthMismatchError`.
- `email_verified` alone gates the merge OFFER — this makes D-06 a single unified rule: providers wired to `email_verified=False` (Mastodon/IndieAuth in Plan 05) can never reach the offer branch.
- Separate-identity creation passes `email=None` (placeholder fallback) whenever the claimed address collides, per D-07.

## Deviations from Plan

None - plan executed exactly as written. One robustness detail worth noting (in-scope, within the plan's own guidance): the pending-link TTL comparison normalizes `DateTime(timezone=True)` values to aware UTC before comparing, because SQLite (the test engine) returns naive datetimes for that column type while PostgreSQL returns aware — mirroring the existing `app/anti_sybil.py` normalization. This was required for a correct, cross-platform TTL check (the plan already directed "compare timezone-aware").

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. This plan is the pure decision layer; provider-callback wiring (and any env/scope changes) lands in Plan 06-05.

## Next Phase Readiness
- `resolve_auth` + `AuthResult` are ready for Plan 06-05 to call from a thin `finalize_auth` route wrapper that translates `request.session` reads and `AuthResult` into the existing HTTP response shapes (409 body + `pending_link_id`, redirect, `{token, user}`).
- No blockers. Live login path untouched; full api suite green (387) and warning-clean.

## Self-Check: PASSED

- Files verified present: api/app/auth/merge.py, api/tests/test_auth_merge.py, 06-04-SUMMARY.md
- Commits verified in history: a21bf2b (test), fcaa11f (feat), 0c9fa60 (test), 771f386 (feat)

---
*Phase: 06-oauth-account-linking*
*Completed: 2026-07-06*
