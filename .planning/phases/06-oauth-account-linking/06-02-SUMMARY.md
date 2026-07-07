---
phase: 06-oauth-account-linking
plan: 02
subsystem: auth
tags: [ssrf, mastodon, oauth, socket, getaddrinfo, httpx, security]

# Dependency graph
requires:
  - phase: 06-oauth-account-linking (plan 01)
    provides: existing Mastodon per-instance registration + callback sign-in flow (AUTH-04)
provides:
  - Dual-stack (IPv4 + IPv6) SSRF validation of the Mastodon instance URL at the validate-before-registration choke point
  - Regression-locked no-redirect-following and no-raw-response-reflection on the dynamic-registration POST
  - Network-free, deterministic Mastodon auth test suite (all DNS mocked at socket.getaddrinfo)
affects: [oauth, auth, mastodon, docs/auth-setup.md, 06-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dual-stack SSRF guard: socket.getaddrinfo(domain, None) + validate every resolved address in both families incl. is_reserved"
    - "getaddrinfo-shaped mock helper (_gai) for deterministic, network-free DNS in tests"

key-files:
  created: []
  modified:
    - api/app/auth/mastodon.py
    - api/tests/test_auth_mastodon.py

key-decisions:
  - "Scope AUTH-05 to dual-stack validation at the single validate-before-registration choke point plus preserving no-redirect/no-reflection; full IP-pinning custom-transport closure of the resolve-then-connect TOCTOU gap is a documented, accepted residual for v0.2.0 (T-06-05d)."
  - "Added is_reserved to the rejected-address predicate (the old code lacked it) as defense-in-depth; in Python's stdlib every reserved range is already flagged is_private, so is_reserved is a superset guard, not a new exclusive gate."
  - "Task 2 required no source change: httpx AsyncClient defaults to follow_redirects=False and the non-200 branch already emits a status-only error — Task 2 shipped as a regression lock over already-correct behavior."

patterns-established:
  - "SSRF resolution guard validates the full getaddrinfo result set (both address families), not a single A record."
  - "Auth tests mock socket.getaddrinfo (not real DNS) so the suite is deterministic and offline."

requirements-completed: [AUTH-04, AUTH-05]

coverage:
  - id: D1
    description: "validate_mastodon_domain rejects private/loopback/link-local/multicast/reserved addresses across BOTH IPv4 and IPv6, closing the AAAA-only / dual-stack private-IPv6 bypass (AUTH-05, T-06-05a)."
    requirement: "AUTH-05"
    verification:
      - kind: unit
        ref: "api/tests/test_auth_mastodon.py::TestValidateMastodonDomainSSRF (ipv6_only_private, ipv6_only_loopback, dual_stack_mixed, ipv4_private, ipv4_loopback, reserved_range, unresolvable, public_pass)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Mastodon dynamic-registration POST does not follow redirects to a private Location and does not reflect the raw upstream response body into the caller-facing error (AUTH-05, T-06-05b / T-06-05c)."
    requirement: "AUTH-05"
    verification:
      - kind: unit
        ref: "api/tests/test_auth_mastodon.py::TestMastodonRegistrationHardening::test_ssrf_registration_does_not_follow_redirect_to_private, ::test_ssrf_registration_error_does_not_reflect_upstream_body"
        status: pass
    human_judgment: false
  - id: D3
    description: "Existing Mastodon per-instance registration + callback sign-in still works end-to-end after the SSRF hardening (AUTH-04 no regression)."
    requirement: "AUTH-04"
    verification:
      - kind: integration
        ref: "api/tests/test_auth_mastodon.py::TestMastodonLogin, ::TestMastodonCallback"
        status: pass
      - kind: integration
        ref: "cd api && .venv/bin/python -m pytest tests/ -q (373 passed, warning-clean)"
        status: pass
    human_judgment: false

# Metrics
duration: 5min
completed: 2026-07-07
status: complete
---

# Phase 6 Plan 02: Mastodon SSRF Hardening (AUTH-05) Summary

**Dual-stack (IPv4+IPv6) SSRF validation of the Mastodon instance URL via socket.getaddrinfo + is_reserved, with regression-locked no-redirect / no-raw-reflection on the dynamic-registration call.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-07-07T02:50:08Z
- **Completed:** 2026-07-07T02:55:22Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Replaced IPv4-only `socket.gethostbyname` with dual-stack `socket.getaddrinfo`, validating every resolved address across both families and adding the previously-missing `is_reserved` check — closing the AAAA-only / dual-stack private-IPv6 SSRF bypass (T-06-05a).
- Regression-locked the two behavioral AUTH-05 guardrails: the registration `httpx.AsyncClient` does not chase a 302 to a private Location, and a non-200 registration response yields a generic status-only error that never reflects the raw upstream body (T-06-05b, T-06-05c).
- Removed a pre-existing real-DNS/network coupling from the Mastodon test suite — all resolution is now mocked at `app.auth.mastodon.socket.getaddrinfo`, making the suite deterministic and offline.

## Task Commits

Each task was committed atomically (TDD red → green):

1. **Task 1: Dual-stack SSRF validation** - `9370179` (test, RED) → `4b18b44` (feat, GREEN)
2. **Task 2: Lock no-redirect + no-raw-reflection** - `bddef29` (test, regression lock; no source change required)

**Plan metadata:** (final docs commit)

## Files Created/Modified
- `api/app/auth/mastodon.py` - `validate_mastodon_domain` now resolves via `socket.getaddrinfo(domain, None)` and rejects any resolved address in either family that is private/loopback/link-local/multicast/reserved.
- `api/tests/test_auth_mastodon.py` - Migrated all DNS mocks to `getaddrinfo` via a `_gai()` helper; added `TestValidateMastodonDomainSSRF` (IPv6-only-private, IPv6-loopback, dual-stack-mixed, IPv4 private/loopback, reserved-range, unresolvable, public-pass) and `TestMastodonRegistrationHardening` (no-redirect, no-body-reflection).

## Decisions Made
- **DNS-rebinding TOCTOU is an accepted v0.2.0 residual (T-06-05d):** per CONTEXT.md Claude's Discretion / RESEARCH A2, this plan scopes AUTH-05 to dual-stack validation at the single validate-before-registration choke point plus no-redirect/no-reflection. Full IP-pinning custom-transport closure of the resolve-then-connect time-gap is deferred and to be disclosed in `docs/auth-setup.md` (Plan 07). Not a silent omission — recorded in the plan threat register.
- **`is_reserved` added as a superset guard:** in Python's stdlib every reserved range is also flagged `is_private`, so `is_reserved` does not change any single existing verdict, but it is retained per the plan/PATTERNS block as explicit defense-in-depth against future stdlib classification changes.
- **Task 2 shipped as a pure regression lock:** the current code already satisfied both guardrails (httpx defaults to `follow_redirects=False`; the non-200 branch emits a status-only message with no `resp.text`/`resp.json()` interpolation), so no source edit was needed — only the two regression tests that would fail if a future change regressed either property.

## Deviations from Plan

None - plan executed exactly as written. (The pre-existing real-DNS coupling in `test_validate_mastodon_domain` was explicitly in-scope per Task 1's action and was removed there, not an unplanned deviation.)

## Issues Encountered
- The interactive shell's `grep` wrapper (ugrep-backed) mis-handled the plan's `grep -v '^#' ... | grep -c 'getaddrinfo'` verify pipe over stdin, printing `0`. Verified with `/usr/bin/grep` the pipe yields `1` (GETADDRINFO_PRESENT) and `socket.getaddrinfo` is present on line 34 of `mastodon.py`. This is a shell-wrapper artifact only; the plan's automated verify runs under a plain shell and passes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- AUTH-05 SSRF surface for Mastodon is hardened; the DNS-rebinding residual (T-06-05d) must be surfaced in `docs/auth-setup.md` during Plan 07.
- Full API suite green (373 passed) and warning-clean; no cross-provider regression.

## Self-Check: PASSED

- `api/app/auth/mastodon.py` — FOUND
- `api/tests/test_auth_mastodon.py` — FOUND
- `.planning/phases/06-oauth-account-linking/06-02-SUMMARY.md` — FOUND
- Commits `9370179`, `4b18b44`, `bddef29` — all FOUND in git history

---
*Phase: 06-oauth-account-linking*
*Completed: 2026-07-07*
