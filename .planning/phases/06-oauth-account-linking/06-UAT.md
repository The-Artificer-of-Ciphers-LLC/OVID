---
status: partial
phase: 06-oauth-account-linking
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md, 06-05-SUMMARY.md, 06-06-SUMMARY.md, 06-07-SUMMARY.md]
started: 2026-07-07T11:58:48Z
updated: 2026-07-07T12:14:00Z
---

## Current Test

[testing paused — 3 items blocked on live provider credentials (Tests 4, 5, 6)]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running API/db containers and clear ephemeral state (test DBs, caches, volumes if safe). Bring the stack up from scratch (`docker-compose up` or prod compose). The API boots without errors, the new `900000000007_pending_account_links` migration applies cleanly, and a primary request (GET /health or a lookup) returns live data. OVID_ENV is now required at boot — the compose files must supply it or the container refuses to start.
result: pass
source: executed by Claude — isolated `ovid_uat6` stack on holodeck from phase-06 HEAD 30847ff (git-bundle → throwaway clone, fresh volume, ports 8600/5600). api booted cold with OVID_ENV=development (compose default) → "Application startup complete"; `alembic upgrade head` applied full chain from empty → 900000000007 (pending_account_links, down_revision 006→007 correct); GET /health → {"status":"ok"}; pending_account_links table exists and queryable. Stack + volume + dir torn down after; holodeck phase-02/prod stacks untouched.

### 2. OVID_ENV Required Boot Guard (breaking change)
expected: Start the API with OVID_ENV UNSET → it refuses to boot (RuntimeError at import). Start with OVID_ENV=production → boots and the localhost/IndieAuth bypass is OFF (a loopback redirect_uri is rejected). Start with OVID_ENV=development → boots with localhost bypass enabled. An invalid value (e.g. OVID_ENV=staging) refuses to boot.
result: pass
source: executed by Claude — ran the phase-06 image with four OVID_ENV values (dummy secret/DB so only the guard varies). UNSET → RuntimeError "Required environment variable OVID_ENV is not set" (config.py:10); production → IMPORT_OK, ALLOW_LOCALHOST_BYPASS=False (confirms AUTH-10); development → IMPORT_OK, bypass=True; invalid "staging" → RuntimeError "must be 'development' or 'production'" (config.py:25).

### 3. IndieAuth Disabled By Default (opt-in gating)
expected: With OVID_ENABLE_INDIEAUTH unset, requests to `/v1/auth/indieauth/login` and `/v1/auth/indieauth/callback` return 404. Set OVID_ENABLE_INDIEAUTH=1 (or true/yes) and restart → those endpoints are now reachable (no longer 404). Default posture is off.
result: pass
source: executed by Claude via live HTTP (FastAPI 0.139 uses lazy router inclusion, so static route introspection is not authoritative — tested over HTTP instead). Disabled (default): GET /v1/auth/indieauth/login and /callback → 404, 404. Enabled (OVID_ENABLE_INDIEAUTH=1, api recreated): → 400 (missing param) / 401 (unauth) — routes registered and reachable, no longer 404. Gate is independent of the OVID_ENV guard (main.py:62).

### 4. Live OAuth Round-Trip — GitHub, Google, Apple, Mastodon
expected: With real client credentials and registered callback URLs, complete a full browser sign-in for each of the four headline providers. Each redirects to its authorize endpoint, returns to `{OVID_API_URL}/v1/auth/<provider>/callback`, and mints a session/JWT for the resolved user. Apple's ES256 client secret (~300s, regenerated per exchange) is accepted; Mastodon dynamically registers on the live instance via POST /api/v1/apps. GitHub email is taken from the verified primary via GET /user/emails.
result: blocked
blocked_by: third-party
reason: "Requires real GitHub/Google/Apple/Mastodon OAuth app credentials + registered callback URLs + interactive browser — not available to Claude. This is the human_needed item flagged in 06-VERIFICATION.md. Callback/exchange logic is covered by the mocked-provider automated suite (AUTH-01→05, 400 tests passing). Needs the operator to run with real credentials."

### 5. Confirm-Gated Account Merge (nOAuth-safe)
expected: Sign in with provider A (verified email) to create a user. Then start sign-in with a DIFFERENT provider B that reports the SAME verified email → instead of silently attaching or creating a duplicate, the callback returns HTTP 409 carrying `pending_link_id` and `existing_user_id` (a merge OFFER, no attach yet). The merge only completes when you re-authenticate through the ORIGINAL provider A (ownership proof); attempting to complete as a different user is rejected. A second provider with an UNVERIFIED email forks a separate account rather than merging.
result: blocked
blocked_by: third-party
reason: "Requires two live verified-email provider sign-ins to exercise the real 409 offer + re-auth consume path — needs real provider credentials (same blocker as Test 4). The resolve_auth decision logic is fully covered by automated tests: test_auth_merge.py (10 isolated unit tests) + test_auth_linking.py (verified-email-creates-offer-no-attach, reauth-consumes-and-attaches, merge-without-reauth-different-user-rejected) — all passing per 06-VERIFICATION.md (AUTH-08)."

### 6. Cannot Unlink Last Provider (min-one guard)
expected: For a user with only one linked OAuth provider, attempting to unlink it returns HTTP 400 (`cannot_unlink_last`). With two or more providers linked, unlinking one succeeds and leaves the account reachable via the remaining provider(s).
result: blocked
blocked_by: third-party
reason: "Requires an authenticated session (JWT) from a live provider login to hit the unlink endpoint — no real provider credentials available (same blocker as Test 4). Guard is covered by the passing AUTH-07 automated test (test_login_via_any_linked_provider / cannot_unlink_last → 400) per 06-VERIFICATION.md."

## Summary

total: 6
passed: 3
issues: 0
pending: 0
skipped: 0
blocked: 3

## Gaps

None recorded yet.

## Notes

This phase is backend security/auth hardening. All 11 requirements (AUTH-01→10, DOCS-03)
are already verified in 06-VERIFICATION.md by 400 passing automated tests (warning-clean);
VERIFICATION status is `human_needed`, gated only on the live OAuth round-trip (Test 4).
Purely-internal deliverables covered by the automated suite are NOT presented as manual
checkpoints: PendingAccountLink model/migration internals, Mastodon dual-stack SSRF
validation, resolve_auth purity/unit isolation, and the Apple exp-shrink mechanics. The
six tests above are the user-observable surface (boot behavior, endpoint gating, live
provider handshakes, merge flow, unlink guard). Tests 4 and 5 require real provider
credentials + a running server; mark them `blocked` if that environment is unavailable.
