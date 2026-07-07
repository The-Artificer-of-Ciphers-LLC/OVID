---
phase: 06-oauth-account-linking
plan: 05
subsystem: auth
tags: [oauth, oidc, github, google, apple, mastodon, indieauth, noauth, account-linking, jwt, fastapi]

# Dependency graph
requires:
  - phase: 06-oauth-account-linking (plan 04)
    provides: pure session-free resolve_auth + AuthResult + MergeReauthMismatchError/PendingLinkInvalidError + PendingAccountLink lifecycle
  - phase: 06-oauth-account-linking (plan 01)
    provides: PendingAccountLink model
provides:
  - "finalize_auth refactored into a thin route wrapper over resolve_auth; session-carried implicit-merge flaw (nOAuth) removed"
  - "409 merge-offer now carries pending_link_id backed by a real PendingAccountLink row"
  - "pending_link_id session plumbing on all 5 provider /login endpoints (routes the re-auth callback only)"
  - "per-provider verified-email signal computed at the source for all 5 callbacks"
  - "GitHub email + email_verified sourced from GET /user/emails primary+verified (profile email is display-only)"
affects: [oauth account linking, auth UI, docs-auth-setup, security-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin route wrapper delegates identity resolution to a pure choke point (resolve_auth); wrapper only maps session state and AuthResult to HTTP"
    - "Per-provider verified-email signal computed at the provider source, never inferred from a generic profile field"
    - "Merge is confirm-gated: DB PendingAccountLink consumed only by a matching re-auth; session value routes, never proves ownership"

key-files:
  created: []
  modified:
    - "api/app/auth/routes.py - finalize_auth thin wrapper + pending_link_id plumbing + per-provider email_verified extraction"
    - "api/app/auth/merge.py - explicit-link collision guard in resolve_auth (latent-bug fix)"
    - "api/tests/test_auth_linking.py - rewritten for the re-auth-required merge model + cross-account rejection + AUTH-06"
    - "api/tests/test_auth_github.py - mock GET /user/emails (verified/no-verified/unavailable branches)"

key-decisions:
  - "finalize_auth reads only routing state (link_to_user_id, web_redirect_uri, pending_link_id) from session; all identity logic lives in resolve_auth"
  - "MergeReauthMismatchError -> 400 (merge_reauth_required); PendingLinkInvalidError -> 409 (pending_link_invalid); ProviderAlreadyLinkedError -> 400 (already_linked)"
  - "Google's email_verified read wired in Task 1 (ahead of its Task 2 slot) so Task 1's route-level offer/merge behavior was directly testable via the simplest verified provider"
  - "resolve_auth now refuses an explicit link when the provider identity is already owned by a different account (faithful port of user_upsert's guard)"

patterns-established:
  - "Pattern 1: route callbacks compute email_verified at the source and pass it into finalize_auth(..., email_verified=...)"
  - "Pattern 2: GitHub trust signal is GET /user/emails primary+verified; the profile email is a display-only fallback that never sets email_verified=True"

requirements-completed: [AUTH-01, AUTH-02, AUTH-06, AUTH-07, AUTH-08]

coverage:
  - id: D1
    description: "finalize_auth is a thin resolve_auth wrapper; the session-carried implicit-merge flaw is removed; a verified-email conflict returns 409 with a real pending_link_id"
    requirement: "AUTH-08"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestEmailConflict::test_google_verified_email_conflict_returns_409_with_pending_link"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestReauthMerge::test_verified_merge_completes_only_via_reauth"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestReauthMerge::test_plain_login_without_pending_link_does_not_merge"
        status: pass
    human_judgment: false
  - id: D2
    description: "GitHub email + email_verified come from GET /user/emails primary+verified; profile email is display-only fallback (AUTH-01)"
    requirement: "AUTH-01"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_github.py::TestGitHubCallback::test_callback_uses_verified_primary_from_user_emails"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_github.py::TestGitHubCallback::test_callback_no_primary_verified_entry_is_unverified"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_github.py::TestGitHubCallback::test_callback_user_emails_unavailable_falls_back_unverified"
        status: pass
    human_judgment: false
  - id: D3
    description: "Google/Apple pass email_verified from verified claims; Mastodon/IndieAuth pass email_verified=False unconditionally (AUTH-02, D-06)"
    requirement: "AUTH-02"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_google.py::TestGoogleCallback (verified userinfo path, suite green)"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_apple.py::TestAppleCallback::test_callback_decodes_id_token_and_upserts_user"
        status: pass
    human_judgment: false
  - id: D4
    description: "Cross-account re-auth carrying another user's pending_link_id fails closed (nOAuth Pitfall 1 regression); multi-provider login and min-one unlink preserved (AUTH-06, AUTH-07)"
    requirement: "AUTH-06"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestReauthMerge::test_cross_account_reauth_is_rejected"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestMultiProviderLogin::test_login_via_any_linked_provider_returns_same_user"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestExplicitLinkUnlink::test_unlink_last_provider_returns_400"
        status: pass
    human_judgment: false
  - id: D5
    description: "One real GitHub sign-in round-trip confirms GET /user/emails wiring end-to-end (pre-release manual check per VALIDATION.md)"
    verification: []
    human_judgment: true
    rationale: "Live provider round-trip against real GitHub cannot be exercised in the in-memory TestClient suite; requires a manual pre-release sign-in."

# Metrics
duration: 18min
completed: 2026-07-06
status: complete
---

# Phase 6 Plan 05: Wire Provider Callbacks to resolve_auth Summary

**All five OAuth callbacks now route identity through the pure resolve_auth choke point with a source-computed verified-email signal (GitHub via GET /user/emails); the session-carried implicit-merge nOAuth flaw is gone and merges are confirm-gated via a DB pending link consumed only by matching re-auth.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-06T23:2x (plan load)
- **Completed:** 2026-07-06T23:33:35Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- `finalize_auth` reduced to a thin wrapper: reads routing state from session, delegates all identity resolution to `resolve_auth`, maps `AuthResult`/exceptions to HTTP. The old `pending_link` session mechanism (merge-the-next-login-regardless-of-identity) is deleted.
- A verified-email conflict now returns 409 carrying `pending_link_id` (a real `PendingAccountLink` row); the merge completes only when the existing account re-authenticates through an already-linked provider.
- All five provider callbacks compute `email_verified` at the source: GitHub via `GET /user/emails` primary+verified (profile email display-only), Google/Apple from their verified id_token claims (Apple string-normalized), Mastodon/IndieAuth unconditionally `False`.
- `pending_link_id` session plumbing added to all five `/login` endpoints (routes the callback; never the ownership proof).
- Cross-account nOAuth regression, multi-provider login (AUTH-06), and min-one-remaining unlink (AUTH-07) are covered and green.

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor finalize_auth into a resolve_auth thin wrapper** - `c1c4a97` (feat)
2. **Task 2: Per-provider verified-email extraction at all 5 callbacks** - `7cf1833` (feat)
3. **Task 3: Update linking tests for re-auth merge + preserve AUTH-06/07** - `acc98e6` (test)

_TDD note: each task was implemented behavior-first against the existing green suite; the code and its tests were committed together per task._

## Files Created/Modified
- `api/app/auth/routes.py` - `finalize_auth` thin wrapper over `resolve_auth`; `pending_link_id` plumbing on all 5 `/login`s; per-provider `email_verified` extraction (GitHub `/user/emails`, Apple string-normalized claim, Google claim, Mastodon/IndieAuth `False`).
- `api/app/auth/merge.py` - `resolve_auth` step-1 explicit-link collision guard (raises `ProviderAlreadyLinkedError` when the provider identity is already owned by a different account).
- `api/tests/test_auth_linking.py` - rewritten `TestEmailConflict`/`TestReauthMerge` for the confirm-gated model; new cross-account rejection regression and `TestMultiProviderLogin` (AUTH-06).
- `api/tests/test_auth_github.py` - `_patch_oauth` dispatches `GET /user/emails` by path; new verified-primary / no-verified-entry / unavailable branch tests.

## Decisions Made
- Exception→HTTP mapping in the wrapper: `MergeReauthMismatchError`→400 `merge_reauth_required`, `PendingLinkInvalidError`→409 `pending_link_invalid`, `ProviderAlreadyLinkedError`→400 `already_linked` (preserves the existing already_linked contract).
- The 409 merge-offer keeps the existing `error` + `existing_user_id` keys (Open Question 2) and adds `pending_link_id`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a latent explicit-link account-takeover in resolve_auth**
- **Found during:** Task 1 (finalize_auth refactor)
- **Issue:** `resolve_auth`'s step-1 existing-link login did not replicate `user_upsert`'s guard: an explicit link (`link_to_user_id` set) of a provider identity already owned by a *different* account would silently log the requester into the OTHER account and mint that account's JWT, instead of returning 400. This regression was exposed by routing the callbacks through `resolve_auth` (it broke `test_explicit_link_provider_already_linked_to_other_user`).
- **Fix:** Added the guard in `resolve_auth` step 1 — when `link_to_user_id` is set and the existing link's owner differs, raise `ProviderAlreadyLinkedError` (faithful port of `users.py`). Imported the exception from `users.py` so the wrapper's existing 400 `already_linked` mapping catches it unchanged.
- **Files modified:** `api/app/auth/merge.py`
- **Verification:** `test_auth_linking.py::TestProviderAlreadyLinked::test_explicit_link_provider_already_linked_to_other_user` (400) and the full `test_auth_merge.py` suite pass.
- **Committed in:** `c1c4a97` (Task 1 commit)

### Sequencing deviation (no scope change)

**2. Brought Google's `email_verified` read forward from Task 2 into Task 1**
- **Found during:** Task 1
- **Why:** Task 1's stated behavior requires route-level tests for the verified-email 409 offer and the re-auth merge. No callback emits a verified signal until provider wiring, so Task 1 wired Google's one-line `bool(userinfo.get("email_verified"))` — the simplest verified provider — to make its own behavior directly testable. Task 2 then wired GitHub/Apple/Mastodon/IndieAuth. Net provider wiring is identical to the plan; only the commit boundary for Google's one line shifted.
- **Files modified:** `api/app/auth/routes.py` (google_callback)
- **Committed in:** `c1c4a97` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed bug (Rule 1) + 1 benign sequencing adjustment.
**Impact on plan:** The bug fix is a genuine security correctness requirement exposed by the wiring (the plan explicitly authorizes fixing such latent bugs inline). No scope creep; all planned deliverables landed.

## Issues Encountered
- None beyond the deviation above. Interim task states stayed green because each task's tests were updated alongside its code.

## Known Stubs
None — no placeholder data or unwired paths introduced.

## Threat Flags
None — no new network endpoints, auth paths, or trust boundaries beyond those already in the plan's threat register (T-06-08e/f/g/h are all mitigated by this plan's changes).

## User Setup Required
None - no external service configuration required for this plan. (Live-provider env vars remain per the phase's existing auth-setup docs.)

## Next Phase Readiness
- The nOAuth close-out is live across all five providers; the full API suite is green (392 passed) and warning-clean under the project's canonical `cd api && .venv/bin/python -m pytest tests/ -q`.
- Remaining pre-release item: one real GitHub sign-in round-trip to confirm `GET /user/emails` wiring end-to-end (D5, manual per VALIDATION.md).

---
*Phase: 06-oauth-account-linking*
*Completed: 2026-07-06*

## Self-Check: PASSED
- Commits verified present: c1c4a97, 7cf1833, acc98e6
- Files verified present: routes.py, merge.py, test_auth_linking.py, test_auth_github.py, 06-05-SUMMARY.md
- Full API suite: 392 passed, warning-clean (`cd api && .venv/bin/python -m pytest tests/ -q`)
