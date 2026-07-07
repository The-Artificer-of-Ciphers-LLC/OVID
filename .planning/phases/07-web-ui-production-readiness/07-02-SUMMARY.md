---
phase: 07-web-ui-production-readiness
plan: 02
subsystem: auth
tags: [fastapi, oauth, jwt, session, redirect, enumeration-safety, nOAuth]

# Dependency graph
requires:
  - phase: 06-oauth-account-linking
    provides: resolve_auth's AuthResult.merge_offer (PendingAccountLink OFFER) and the ME-02 enumeration-safe 409 JSON shape this plan makes redirect-capable
provides:
  - "finalize_auth's merge-offer branch 302-redirects the browser to web_redirect_uri with error=email_conflict&pending_link_id=<id> when a web_redirect_uri is in session"
  - "409 JSON fallback preserved for non-browser/API callers with no web_redirect_uri in session"
  - "link_provider returns explicit 400 link_requires_domain for mastodon/indieauth instead of a silent pass-through (R-3)"
affects: [07-07-web-ui-production-readiness (settings-page merge banner consumes ?error=email_conflict&pending_link_id=)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Merge-offer redirect mirrors the pre-existing success-path redirect exactly (module-level urlencode + '&'-vs-'?' separator on web_redirect_uri), keeping both branches structurally identical"

key-files:
  created:
    - api/tests/test_auth_merge_redirect.py
  modified:
    - api/app/auth/routes.py
    - api/tests/test_auth_linking.py

key-decisions:
  - "web_redirect_uri is popped inside the merge-offer branch (not just at the pre-existing success-path pop) so it is consumed exactly once regardless of which branch finalize_auth takes"
  - "R-3: mastodon/indieauth are rejected with 400 link_requires_domain BEFORE session.pop(link_to_user_id) runs, so a rejected POST /link/{provider} never mutates session state"

patterns-established:
  - "Merge-offer payload (error + pending_link_id, never token/existing_user_id) is built once as a dict and reused for both the 302 redirect query string and the 409 JSON fallback body — one enumeration-safe source of truth per response"

requirements-completed: []  # WEBUI-04 appears in this plan's frontmatter but is NOT marked complete here — see Deviations. It requires the settings surface (07-07) too.

coverage:
  - id: D1
    description: "finalize_auth's verified-email merge OFFER 302-redirects the browser to web_redirect_uri with error=email_conflict&pending_link_id=<id>, carrying no token/existing_user_id (ME-02), falling back to 409 JSON with no web_redirect_uri in session"
    requirement: "WEBUI-04"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_merge_redirect.py::TestMergeOfferRedirect::test_merge_offer_redirects_and_is_enumeration_safe"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_merge_redirect.py::TestMergeOfferRedirect::test_merge_offer_without_web_redirect_uri_returns_409_json"
        status: pass
    human_judgment: false
  - id: D2
    description: "link_provider returns explicit 400 link_requires_domain for mastodon/indieauth (R-3), replacing the pass-only branch; github/google/apple link behavior unchanged"
    requirement: "WEBUI-04"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestExplicitLinkUnlink::test_link_domain_provider_returns_400[mastodon]"
        status: pass
      - kind: integration
        ref: "api/tests/test_auth_linking.py::TestExplicitLinkUnlink::test_link_domain_provider_returns_400[indieauth]"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 2: D-04 merge-offer redirect + R-3 link cleanup Summary

**finalize_auth's verified-email merge OFFER now 302-redirects to web_redirect_uri with an enumeration-safe error=email_conflict&pending_link_id query, instead of dead-ending the browser on raw 409 JSON**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-07T17:38:03Z
- **Completed:** 2026-07-07T17:47:13Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `finalize_auth`'s merge-offer branch (`api/app/auth/routes.py`) 302-redirects the browser back to `web_redirect_uri` carrying `error=email_conflict&pending_link_id=<id>` when a `web_redirect_uri` is present in session — mirroring the existing success-path redirect's `urlencode`/separator logic exactly, and popping `web_redirect_uri` exactly once regardless of which branch runs.
- The 409 JSON fallback is preserved byte-for-byte for non-browser/API callers with no `web_redirect_uri` in session (`error` + `pending_link_id` only, no `existing_user_id`, no `token` — ME-02).
- `link_provider`'s leftover merge-conflict cruft (a `pass`-only mastodon/indieauth branch with a rambling "the plan doesn't specify..." comment) is replaced with an explicit `400 {error: "link_requires_domain"}` for those two providers, which need a domain/url a bare POST can't carry; github/google/apple continue to redirect unchanged.
- `api/tests/test_auth_merge_redirect.py` drives the scenario through the real HTTP surface (`/v1/auth/google/login` + `/v1/auth/google/callback`) against a seeded GitHub-linked owner, proving the redirect, the ME-02 guard, and the 409 fallback via `finalize_auth`'s actual code path (not just the pure `resolve_auth` resolver already covered by `test_auth_merge.py`).

## Task Commits

Each task was committed atomically (TDD RED → GREEN, plus one in-scope coverage addition):

1. **Task 1: RED — failing pytest for the D-04 redirect + ME-02 guard + fallback** - `1e26fd0` (test)
2. **Task 2: GREEN — merge-offer 302 redirect + R-3 link_provider cleanup** - `debb430` (fix)
3. **In-scope addition: R-3 test coverage** - `bff9be6` (test) — see Deviations

**Plan metadata:** (this commit)

## Files Created/Modified
- `api/tests/test_auth_merge_redirect.py` - New pytest module: 302 redirect + ME-02 guard + 409 fallback, driven through the real `/v1/auth/google/login`+`/callback` HTTP surface against a seeded verified-email owner
- `api/app/auth/routes.py` - `finalize_auth` merge-offer branch now redirects (D-04); `link_provider` mastodon/indieauth cleanup (R-3); removed a redundant function-scope-shadowing local `urlencode` import surfaced by the new branch
- `api/tests/test_auth_linking.py` - Added `test_link_domain_provider_returns_400` (parametrized mastodon/indieauth) covering the R-3 400 behavior

## Decisions Made
- `web_redirect_uri` is popped inside the merge-offer branch itself (not relying on the pre-existing success-path pop lower in the function), so it is consumed exactly once no matter which branch `finalize_auth` takes — required because the merge branch returns before ever reaching the success-path pop.
- The merge-offer payload (`{error, pending_link_id}`) is built once and reused for both the 302 query string and the 409 JSON body, so there is exactly one enumeration-safe source of truth instead of two payloads that could drift apart.
- `link_provider`'s mastodon/indieauth 400 guard runs BEFORE `request.session["link_to_user_id"]` is set, so a rejected POST never mutates session state.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a function-scope import shadowing bug surfaced by the new merge-branch code**
- **Found during:** Task 2 (implementing the D-04 redirect)
- **Issue:** The pre-existing success-path redirect branch had a local `from urllib.parse import urlencode` inside its `if web_redirect_uri:` block. Python treats any name assigned anywhere in a function body as local to that function for its *entire* scope, so this local import made `urlencode` unbound at the point the new merge-branch code referenced it earlier in the same function — an `UnboundLocalError` at request time, not import time, so it was invisible until the merge-offer branch was actually exercised.
- **Fix:** Removed the redundant local import; `urlencode` is already imported at module scope (`from urllib.parse import urlencode, urlparse`, line 7) and covers both branches.
- **Files modified:** `api/app/auth/routes.py`
- **Verification:** `test_merge_offer_redirects_and_is_enumeration_safe` failed with the `UnboundLocalError` before the fix, passed after; full auth suite (152 tests) and full api suite (446 tests) green after.
- **Committed in:** `debb430` (Task 2 commit)

**2. [Rule 2 - Missing Critical] Added test coverage for R-3's threat-register mitigation**
- **Found during:** post-Task-2 review against the plan's `<threat_model>`
- **Issue:** Threat `T-07-02-04` (Spoofing, mastodon/indieauth link) assigns disposition `mitigate` with "explicit 400 for providers that need a domain a bare POST can't carry, instead of a silent `pass`" — the implementation shipped this in Task 2, but no test proved the 400 actually fires (Task 2's own `<verify>` block only required the R-3 grep-for-removed-comment check and the pre-existing auth suite, neither of which exercises the new branch).
- **Fix:** Added `test_link_domain_provider_returns_400` (parametrized over `mastodon`/`indieauth`) to `api/tests/test_auth_linking.py`, asserting `400 {error: "link_requires_domain"}`.
- **Files modified:** `api/tests/test_auth_linking.py`
- **Verification:** New test passes; full api suite still green (446 passed, up from 444).
- **Committed in:** `bff9be6`

**3. [Process correction] Did NOT mark WEBUI-04 complete despite it being this plan's frontmatter `requirements` field**
- **Found during:** state_updates step (requirements.mark-complete)
- **Issue:** `gsd-tools query requirements.mark-complete WEBUI-04` was run per the standard workflow instruction to extract and mark all requirement IDs in the plan's frontmatter — but WEBUI-04 ("Account settings surface (linked providers add/remove) is wired to AUTH-06/07") is only PARTIALLY delivered by this plan (the backend redirect prerequisite). The actual settings UI surface (add/remove providers, the D-05 merge banner) ships in 07-07. Marking it complete here would be a false-complete state, exactly the failure mode 07-01's own SUMMARY explicitly called out and avoided for WEBUI-01..04.
- **Fix:** Reverted `.planning/REQUIREMENTS.md` — `WEBUI-04` checkbox back to `[ ]` and its traceability-table row back to `Pending`. `requirements-completed: []` in this SUMMARY's frontmatter (not `[WEBUI-04]`). The `coverage:` block still links `requirement: WEBUI-04` per-deliverable (that field is about per-deliverable traceability, not overall requirement completion).
- **Files modified:** `.planning/REQUIREMENTS.md`
- **Verification:** `grep WEBUI-04 .planning/REQUIREMENTS.md` shows `[ ]` and `Pending`, matching WEBUI-01/02/03's still-pending state.
- **Committed in:** (this commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical test coverage) + 1 process correction
**Impact on plan:** The two auto-fixes are necessary for correctness (the shadowing bug would have broken the D-04 fix at runtime for the exact scenario it's meant to fix) and for security-mitigation traceability. No scope creep beyond the plan's own `<threat_model>` and files_modified footprint (routes.py was already in scope; the linking test extends the plan's own test-mirroring convention rather than introducing a new surface). The process correction prevents a false-complete requirement state ahead of 07-07.

## Issues Encountered
None beyond the auto-fixed items above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The `?error=email_conflict&pending_link_id=<id>` redirect this plan ships is exactly what 07-07's settings-page merge banner (D-05) needs to read via `useSearchParams` — no further backend work required for that integration.
- `_validate_web_redirect_uri`'s CORS_ORIGINS-gated allowlist was left untouched, as required; staging-origin wiring remains 07-08's job.
- No blockers for 07-03 through 07-08.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: api/tests/test_auth_merge_redirect.py
- FOUND: api/app/auth/routes.py
- FOUND: api/tests/test_auth_linking.py
- FOUND commit: 1e26fd0
- FOUND commit: debb430
- FOUND commit: bff9be6
