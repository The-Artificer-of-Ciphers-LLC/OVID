---
phase: 06-oauth-account-linking
verified: 2026-07-07T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Complete a real browser sign-in round-trip for GitHub, Google, Apple, and Mastodon against live provider apps (real client credentials + registered callback URLs)."
    expected: "Each provider redirects to its authorize endpoint, returns to the OVID callback, and mints a session/JWT for the resolved user; Apple exchange succeeds with the per-exchange ES256 client secret; Mastodon dynamically registers on a real instance."
    why_human: "Live OAuth handshakes require real provider apps, browser interaction, and external services. Unit/integration tests exercise the callback logic with mocked provider HTTP; the real-provider round-trip cannot be unit-tested (AUTH-01/02/03/04 end-to-end clause)."
---

# Phase 6: OAuth & Account Linking Verification Report

**Phase Goal:** All four OAuth providers work end-to-end, with linked-account management and email-merge that is secure by construction against nOAuth-class takeover, SSRF, and config-drift bypass.
**Verified:** 2026-07-07
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal is a security-by-construction claim across three attack classes. Each class was verified against the actual shipped code and its passing behavioral tests, not the SUMMARY narrative:

- **nOAuth-class takeover** — closed by `api/app/auth/merge.py::resolve_auth`, a pure, session-free choke point. A provider-verified email match yields a `PendingAccountLink` OFFER (never an attach, never a new user); the merge is consumed ONLY when the SAME `existing_user_id` re-authenticates through an already-linked provider (the trust anchor). Single-use (`consumed_at`) + TTL (`expires_at`) enforced. The new provider's email is never trusted as proof of ownership.
- **SSRF** — closed by `validate_mastodon_domain` (dual-stack `getaddrinfo`, rejects private/loopback/link-local/multicast/reserved in both families), called before any outbound registration; `httpx.AsyncClient()` default `follow_redirects=False`; error paths return generic messages (no raw upstream reflection).
- **Config-drift bypass** — closed by `api/app/auth/config.py`: `OVID_ENV` is a required env var (raises at import if unset/invalid); `ALLOW_LOCALHOST_BYPASS` is *derived solely* from `OVID_ENV` (no separately-settable flag to drift) and is `False` under production, with an explicit import-time invariant assertion as a belt-and-suspenders guard.

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Sign-in works end-to-end for GitHub/Google/Apple/Mastodon; Apple ES256 JWT per exchange + rotation | ✓ VERIFIED (code + mocked-provider tests) — live handshake → human | All 4 login+callback routes wired to `finalize_auth` (routes.py); Apple `exp = now + 300` regenerated per exchange (routes.py:328; tests `test_client_secret_exp_is_short_lived`, `test_client_secret_regenerated_per_exchange`); Mastodon per-instance `/api/v1/apps` registration with user-supplied `domain` (routes.py:674-712). Live round-trip routed to human verification. |
| 2 | Every Mastodon instance URL validated against SSRF (dual-stack IP checks, no redirect, no raw reflection) before any outbound request | ✓ VERIFIED | `validate_mastodon_domain` (mastodon.py:15-50) dual-stack `getaddrinfo` + private/loopback/link-local/multicast/reserved rejection; called at routes.py:689 BEFORE `get_or_register_client` (line 694). Tests: IPv6-only private/loopback, dual-stack-mixed, IPv4 private/loopback, reserved, no-redirect-to-private, no-raw-reflection — all pass. |
| 3 | Multi-provider link; log in with any; add/remove with server-enforced min-one login method | ✓ VERIFIED | `/v1/auth/providers` lists links; `/unlink/{provider}` enforces `len(oauth_links) <= 1 → 400 cannot_unlink_last` (routes.py:844); multi-provider login via `resolve_auth` existing-link path. Web UI surface is tracked separately as WEBUI-04 (not in this phase's requirement set). |
| 4 | Verified-email match offers linking but requires explicit confirmation + re-auth of existing account — never silent/automatic merge | ✓ VERIFIED | `resolve_auth` verified-email gate (merge.py:269) creates OFFER only; `finalize_auth` returns 409 with `pending_link_id` (routes.py:142-149); consume requires re-auth via already-linked provider owned by same `existing_user_id` (merge.py:196-224). Tests: offer-no-attach, reauth-consumes, without-reauth-rejected, expired/consumed-rejected. |
| 5 | `finalize_auth`/`resolve_auth` isolated unit tests: verified-merge success, unverified-merge rejection, merge-without-reauth rejection | ✓ VERIFIED | `test_auth_merge.py` bare `db_session` (no TestClient): `test_verified_email_match_creates_offer_no_attach` + `test_reauth_success_consumes_and_attaches` (success), `test_unverified_colliding_email_forks_separate_identity` (rejection), `test_merge_without_reauth_different_user_rejected` (rejection). |
| 6 | IndieAuth localhost bypass provably unreachable in production (boot assertion); OAuth setup guide published | ✓ VERIFIED | config.py: `OVID_ENV` required (raises at import), `ALLOW_LOCALHOST_BYPASS = OVID_ENV != "production"` + invariant assertion (config.py:23-40); IndieAuth call site uses `allow_localhost=config.ALLOW_LOCALHOST_BYPASS` (routes.py:491); router gated on `OVID_ENABLE_INDIEAUTH` (main.py:62). Tests: unset/invalid refuses boot, prod disables bypass, 404-when-disabled, localhost rejected-when-off. `docs/auth-setup.md` (201 lines, all 6 sections) + mkdocs nav entry. |

**Score:** 6/6 truths verified at code + automated-test level. Live real-provider OAuth round-trips (truth #1) are inherently manual and routed to human verification per protocol — not a gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `api/app/models.py` `PendingAccountLink` | ORM class → `pending_account_links` | ✓ VERIFIED | Class at line 400; FK `users.id` ondelete CASCADE; `expires_at` no-default, `consumed_at` nullable; index; registered in `Base.metadata`. |
| `api/alembic/versions/900000000007_pending_account_links.py` | Migration, down_revision 900000000006 | ✓ VERIFIED | Creates table + index; `down_revision = '900000000006'`; downgrade drops both. |
| `api/app/auth/merge.py` | `resolve_auth`, `AuthResult`, CRUD, exceptions | ✓ VERIFIED | 299 lines; pure DB-shaped resolver; `MergeReauthMismatchError`, `PendingLinkInvalidError`. |
| `api/app/auth/config.py` | `OVID_ENV` guard + `ALLOW_LOCALHOST_BYPASS` | ✓ VERIFIED | Import-time raise; derived constant + invariant assertion. |
| `api/app/auth/mastodon.py` | Hardened dual-stack `validate_mastodon_domain` | ✓ VERIFIED | `getaddrinfo` over all resolved IPs; reserved-range checks. |
| `api/app/auth/routes.py` | Thin `finalize_auth` + per-provider `email_verified` + 409 + separate `indieauth_router` | ✓ VERIFIED | `finalize_auth` reads session, delegates to `resolve_auth`; GitHub via `/user/emails`, Apple/Google from verified id-token claims, Mastodon/IndieAuth `email_verified=False`. |
| `api/main.py` | Conditional IndieAuth router include | ✓ VERIFIED | `if os.environ.get("OVID_ENABLE_INDIEAUTH", "").lower() in (...)`. |
| `docs/auth-setup.md` + `mkdocs.yml` | Guide + nav | ✓ VERIFIED | All 6 DOCS-03 sections present; nav entry `Auth Setup: auth-setup.md`. |
| Deployment surfaces | `OVID_ENV` in .env.example + 3 compose files + conftest | ✓ VERIFIED | dev/test `${OVID_ENV:-development}`, prod hardcoded `production`, conftest `setdefault`. |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| routes.py `mastodon_login` | `validate_mastodon_domain` | validate BEFORE `get_or_register_client` outbound POST | ✓ WIRED (line 689 → 694) |
| routes.py IndieAuth call site | `config.ALLOW_LOCALHOST_BYPASS` | `validate_url(url, allow_localhost=...)` | ✓ WIRED (line 491) |
| `finalize_auth` | `resolve_auth` | delegates all identity resolution; session only routes `pending_link_id` | ✓ WIRED (routes.py:107-118) |
| all 5 provider callbacks | `finalize_auth(email_verified=...)` | per-provider verified signal gates merge offer | ✓ WIRED (github/apple/indieauth/google/mastodon) |
| `PendingAccountLink.existing_user_id` | `users.id` | ForeignKey CASCADE | ✓ WIRED (models.py:407) |

### Behavioral / Probe Evidence

| Check | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| Full api suite | `api/.venv/bin/python -m pytest tests/ -q` | 398 passed in 5.61s, warning-clean | ✓ PASS |
| SSRF invariants | named tests in `test_auth_mastodon.py` (11 SSRF cases) | included in suite | ✓ PASS |
| Boot-guard / bypass | `test_auth_config.py` (4 subprocess import-time tests) | included in suite | ✓ PASS |
| Merge invariants | `test_auth_merge.py` (offer/consume/reject/expire) | included in suite | ✓ PASS |
| Apple secret exp | `test_auth_apple.py` (exp short-lived + per-exchange) | included in suite | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Status | Evidence |
| ----------- | -------------- | ------ | -------- |
| AUTH-01 GitHub | 06-05 | ✓ SATISFIED (live → human) | `/user/emails` verified-primary; callback wired |
| AUTH-02 Google | 06-05 | ✓ SATISFIED (live → human) | OIDC `email_verified` from verified id_token |
| AUTH-03 Apple | 06-06 | ✓ SATISFIED (live → human) | `exp=300` per exchange; tested |
| AUTH-04 Mastodon per-instance | 06-02 | ✓ SATISFIED (live → human) | dynamic `/api/v1/apps` registration; user-supplied domain |
| AUTH-05 SSRF guardrail | 06-02 | ✓ SATISFIED | dual-stack validate-before-outbound; no redirect/reflection |
| AUTH-06 multi-provider | 06-05 | ✓ SATISFIED | existing-link login + explicit link path |
| AUTH-07 min-one unlink | 06-05 | ✓ SATISFIED | `cannot_unlink_last` 400 guard |
| AUTH-08 confirm-gated merge | 06-01/04/05 | ✓ SATISFIED | offer + 409 + re-auth consume |
| AUTH-09 finalize_auth unit tests | 06-04 | ✓ SATISFIED | 3 required cases + expiry/consume |
| AUTH-10 localhost bypass unreachable | 06-03/06 | ✓ SATISFIED | derived constant + boot assertion; tested |
| DOCS-03 setup guide | 06-07 | ✓ SATISFIED | auth-setup.md + nav |

All 11 requirement IDs declared across the 7 plans map 1:1 to phase requirements — no orphans, no uncovered IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `api/app/auth/routes.py` | 830-834 | `link_provider` for `mastodon`/`indieauth` is a no-op `pass` (these need a domain/url a plain POST doesn't carry) with a rambling inline comment | ℹ️ Info | The explicit `POST /link/{provider}` path is inert for Mastodon/IndieAuth. Core linking for those providers still works via the `resolve_auth` verified-email merge-offer flow and the login-with-`link_to_user_id` session path; GitHub/Google/Apple explicit link redirects work. Not a security concern and outside the phase's nOAuth/SSRF/config-drift goal. Recommend tidying the comment and either wiring domain passthrough or returning 400 for these two in a later WEBUI-04 pass. |

No `TODO`/`FIXME`/`XXX`/`PLACEHOLDER` debt markers in any shipped phase file. `users.py:20` and other `pass` hits are empty exception-class bodies (normal).

### Human Verification Required

1. **Live OAuth round-trip for all four providers** — perform a real browser sign-in for GitHub, Google, Apple, and Mastodon against registered provider apps with real credentials and callback URLs.
   - Expected: each provider redirects to authorize, returns to the OVID callback, and mints a session/JWT for the resolved user; Apple exchange succeeds with the per-exchange ES256 client secret; Mastodon dynamically registers on the live instance.
   - Why human: real provider handshakes need external services + browser interaction and cannot be unit-tested; the callback/merge logic itself is already covered by the passing mocked-provider suite.

### Gaps Summary

No gaps blocking the phase goal. The three attack classes named in the goal (nOAuth takeover, SSRF, config-drift bypass) are each closed by construction in the shipped code and backed by named, passing behavioral tests within the 398-test warning-clean suite. The only outstanding item is the inherently-manual live-provider OAuth round-trip (recommended human confirmation of the "end-to-end" clause for AUTH-01/02/03/04), which per protocol is human verification, not a gap. One informational anti-pattern (inert explicit-link POST for Mastodon/IndieAuth) is noted for future tidy-up and does not affect the goal.

---

_Verified: 2026-07-07_
_Verifier: Claude (gsd-verifier)_

## Post-Review Security Hardening

An advisory security review (`06-REVIEW.md`) of the shared auth callback plumbing this phase
routes all five providers through surfaced 2 HIGH + 2 MEDIUM + 4 LOW findings. Per the project's
NEVER-DEFER policy, ALL 8 findings were remediated inline (not ticketed, not deferred) with
accompanying regression tests:

- HIGH: Apple callback OAuth `state` verification (login CSRF / auth-code injection) — closed.
- HIGH: `web_redirect_uri` open redirect enabling JWT exfiltration/account takeover — closed via a
  `CORS_ORIGINS`-backed allowlist (fail-closed), applied through one shared helper at all 5 login
  sites.
- MEDIUM: unencoded authorize-request query params; MEDIUM: `existing_user_id` leaked in merge-offer
  409 body (enumeration) — both closed.
- LOW: non-atomic single-use consume race; LOW: raw exception text reflected to clients; LOW: unused
  `ec` import; LOW: stray `users.py.patch` + dead unsafe `user_upsert` path — all closed.

Post-remediation verification: `api` suite 400 passed, 0 warnings; `ovid-client` suite 242 passed
(16 hardware-marker tests skipped, unaffected); `arm` suite 12 passed, unaffected.

This section does not change the `status: human_needed` frontmatter above — the manual live-provider
OAuth round-trip (see Human Verification Required) remains the only open item for this phase.
