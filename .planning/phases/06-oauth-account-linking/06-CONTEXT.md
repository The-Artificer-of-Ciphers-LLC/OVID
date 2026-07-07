# Phase 6: OAuth & Account Linking - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver all four headline OAuth providers (GitHub, Google, Apple, Mastodon) verified working
end-to-end, plus secure, confirm-gated account linking/merge — built on the substantial OAuth
scaffolding that already exists in `api/app/auth/`. This phase **hardens and verifies**; it does
not build OAuth from scratch.

Concretely, the phase must:
- Close three named security guardrails: nOAuth-class merge takeover (AUTH-08), Mastodon SSRF
  (AUTH-05), and the IndieAuth localhost bypass (AUTH-10).
- Give `finalize_auth` isolated unit tests (AUTH-09) — currently only indirect coverage.
- Ship the OAuth setup guide `docs/auth-setup.md` (DOCS-03).

**Already built — NOT decisions for this phase** (confirmed by codebase scout):
- All 5 provider flows are wired: GitHub, Apple, Google, Mastodon, IndieAuth (`api/app/auth/routes.py`).
- Multi-provider linking data model exists: `UserOAuthLink` junction, `UniqueConstraint(provider, provider_id)` (`api/app/models.py:370`).
- Shared `finalize_auth(request, db, provider, provider_id, email, display_name)` (`api/app/auth/routes.py:71`).
- Mastodon SSRF check exists (`api/app/auth/mastodon.py:15` `validate_mastodon_domain`) — must be **completeness-audited** against AUTH-05, not rebuilt.
- Apple ES256 client-secret generated per-callback (`api/app/auth/routes.py:237`).
- `_require_env` import-time fail-fast pattern (`api/app/auth/config.py`).

**Out of scope (belongs to other phases):** the web account-settings UI that drives add/remove of
linked providers is Phase 7 (WEBUI-04). This phase exposes the clean backend API semantics that
Phase 7 wires to.

</domain>

<decisions>
## Implementation Decisions

### Account-merge confirm + re-auth flow (AUTH-08)
- **D-01:** Replace the current session-carried pending-link (which merges into *whatever account
  logs in next* — structurally the nOAuth flaw) with a **server-side `PendingAccountLink` DB row**
  as the state carrier. Row carries `existing_user_id`, `new_provider`, `new_provider_id`,
  `expires_at`, `consumed_at` — giving real TTL + single-use + audit semantics enforceable at the DB layer.
- **D-02:** Re-authentication is proven by a **fresh OAuth re-login through a provider ALREADY
  linked to the existing account**. The re-auth callback loads the pending row, asserts
  `existing_user_id == freshly-authenticated user.id`, marks `consumed_at`, then attaches the new
  provider. This reuses a trust anchor OVID already verified — never trusts the new provider's email claim.
  (Every "existing account" has ≥1 linked provider by definition, so the anchor always exists.)
- **D-03 [informational]:** The emailed-confirmation-link variant is explicitly **deferred** — OVID has zero SMTP/email
  infrastructure today; building it solely for this flow is disproportionate. Revisit only if OVID
  gains general email capability. Session-state-only and bare-signed-token-only were both rejected.
- **D-04:** `finalize_auth` must be refactored to be unit-testable with a plain DB fixture (no
  `Request.session` / Starlette middleware entanglement), so AUTH-09's three required tests
  (verified-email merge success, unverified-email merge rejection, merge-without-reauth rejection)
  assert directly on row state.

### Provider email-trust policy for merge eligibility (AUTH-08)
- **D-05:** **Signal-based allowlist.** A merge OFFER is made only when the provider supplies a real
  verified-email signal, checked at the source:
  - GitHub — must come from `GET /user/emails` (primary + `verified: true`), **not** the profile `email` field.
  - Google — require `id_token.email_verified === true` (issuer/aud checked).
  - Apple — require `id_token.email_verified === true` (note: private-relay addresses are Apple-verified proxies, still valid).
- **D-06:** **Mastodon and IndieAuth never match by email.** They attach to an existing account
  ONLY through the authenticated explicit-link flow (user already signed in, initiates linking).
  Skip the email-conflict path entirely for these two; keep Mastodon's `@noemail.placeholder` /
  null-email-for-IndieAuth pattern. This resolves the STATE.md open question and generalizes
  REQUIREMENTS' existing "Mastodon-merge disabled" default into one rule: *no verified signal → no email match*.
- **D-07:** A matching email from a non-trusted provider creates/keeps a **separate identity** — never
  a silent duplicate-merge and never a silent new-merge.

### IndieAuth scope + localhost-bypass gating (AUTH-10)
- **D-08:** **IndieAuth is gated off by default.** The roadmap names only four headline providers;
  register IndieAuth routes only when an operator explicitly opts in (feature flag / conditional
  router registration), disabled/404 otherwise. Shrinks the default auth surface to exactly the four
  roadmapped providers; IndieWeb self-hosters can still opt in knowingly. (Do NOT leave it enabled-but-undocumented.)
- **D-09:** **Bypass gating = single required `OVID_ENV`** env var, no default. The localhost bypass
  in `validate_url(..., allow_localhost=...)` is allowed **iff `OVID_ENV != "production"`**. An
  **import-time assertion** (mirroring the existing `_require_env("OVID_SECRET_KEY")` fail-fast in
  `api/app/auth/config.py`) refuses to boot until the operator declares dev/production, and refuses
  to boot if the bypass would be enabled under `OVID_ENV=production`. One signal to get right →
  impossible to misconfigure silently.
  - Reusing `OVID_MODE` was researched and **rejected**: `standalone` is the default value in dev
    *and* self-host-prod compose, so it carries no dev/prod signal.
  - This is a **breaking change**: existing self-hosted instances must set `OVID_ENV` on upgrade
    (surfacing the decision is intentional). Document in the migration/deployment notes.
  - Remove the unconditional `allow_localhost=True` at `api/app/auth/routes.py:400`; derive it from `OVID_ENV`.

### Apple client-secret lifetime + rotation (AUTH-03)
- **D-10:** **Short exp per exchange, single key, runbook rotation.** Drop the Apple ES256 client-secret
  JWT `exp` from `now + 6mo` to a **short lifetime (~5 min / 300s)**, still regenerated per token
  exchange — per-exchange regeneration of a short-lived JWT *is* the "automatic rotation" AUTH-03 asks
  for. Keep a single configured `.p8` (`APPLE_PRIVATE_KEY`/`APPLE_KEY_ID`). Rotating the underlying
  `.p8` key is an **ops runbook step** (register new key in Apple console, swap env vars, restart),
  documented in self-hosting/deployment + `docs/auth-setup.md`.
- **D-11:** In-app multi-`kid` key rotation is **deferred** — disproportionate config/code surface for
  a rare event no current requirement asserts. Keeping the 6-month exp was rejected (fails AUTH-03).
  Use a few-minutes buffer (not <60s) to tolerate clock skew / retries. Existing `test_auth_apple.py`
  (11 tests) asserting the old exp must be updated.

### Claude's Discretion
- Mastodon SSRF completeness audit (AUTH-05): the guardrail behaviors (hostname/reserved-IP checks,
  no redirect-following, no raw-response reflection, IPv6/multi-record/DNS-rebinding handling) are
  prescribed by the requirement — researcher/planner determine exactly which are already covered by
  `validate_mastodon_domain` vs. need adding. Not a user gray area.
- Exact `PendingAccountLink` table columns/indexes, endpoint paths, and migration id — planner's call,
  following existing SQLAlchemy/Alembic conventions.
- Exact `OVID_ENV` accepted values beyond the `production` sentinel — planner's call (e.g.
  `development`/`production`), but `production` must be the value that disables the bypass.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone / requirements source of truth
- `.planning/REQUIREMENTS.md` §"OAuth & Accounts (AUTH)" — AUTH-01…AUTH-10 + DOCS-03 exact wording, incl. guardrail flags.
- `.planning/REQUIREMENTS.md` §"Out of Scope" — silent/automatic email-merge, unlinking last login method, Mastodon-driven merge (default disabled) — all binding constraints for this phase.
- `.planning/ROADMAP.md` §"Phase 6: OAuth & Account Linking" — six success criteria (what must be TRUE).
- `docs/OVID-product-spec.md` — Milestone 0.2 exit criteria (referenced by PROJECT.md; not read during discussion — read before planning).

### Existing auth implementation to harden (all under `api/app/auth/`)
- `api/app/auth/routes.py` — all 5 provider flows + `finalize_auth` (line 71) + linking routes (`/providers`, `/link/{provider}`, `/unlink/{provider}`, lines 714-742); Apple secret gen at 237; **IndieAuth `allow_localhost=True` at line 400 (the AUTH-10 defect)**.
- `api/app/auth/config.py` — `_require_env` fail-fast pattern to mirror for the `OVID_ENV` boot assertion (D-09).
- `api/app/auth/users.py` — `user_upsert`, `EmailConflictError`, `ProviderAlreadyLinkedError` (the email-conflict path D-05/D-06 rewrite).
- `api/app/auth/indieauth.py:26` — `validate_url(url, *, allow_localhost=False)` (bypass origin).
- `api/app/auth/mastodon.py:15` — `validate_mastodon_domain` (existing SSRF check to audit vs AUTH-05).
- `api/app/auth/jwt.py` — HS256 access-token issuance/decode.
- `api/app/models.py:340` (`User`, unique `email` + `email_verified`) and `api/app/models.py:370` (`UserOAuthLink`), `:456` (`MastodonOAuthClient`).

### Concerns / prior analysis
- `.planning/codebase/CONCERNS.md` §27-35 (IndieAuth localhost bypass), §78-82 (`finalize_auth` untested-in-isolation) — the two concerns AUTH-09/AUTH-10 close.

### Existing tests to extend/update
- `api/tests/test_auth_linking.py` (20 tests), `test_auth_apple.py` (11 — must update for new exp), `test_auth_github.py`, `test_auth_google.py`, `test_auth_indieauth.py`, `test_auth_mastodon.py`, `test_auth.py`.

### To be created this phase
- `docs/auth-setup.md` — OAuth setup guide (DOCS-03), incl. the Mastodon `requests`-vs-`httpx` client note and the Apple `.p8` rotation runbook.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `UserOAuthLink` junction table already models multiple providers per account — the linking/unlink
  data model is done; this phase adds the *merge-confirmation* layer on top, not the linking model.
- `_require_env` import-time fail-fast (`config.py`) is the exact template for the AUTH-10 `OVID_ENV`
  boot assertion (D-09) — reuse the pattern, don't invent a new one.
- `finalize_auth` is the single choke point all 5 providers call — the right place to centralize
  the D-05/D-06 email-trust policy and the D-01/D-02 pending-merge logic.
- `validate_mastodon_domain` (mastodon.py) already does `ipaddress`-based private/loopback/link-local/
  multicast rejection — extend for AUTH-05 gaps rather than rewriting.

### Established Patterns
- Providers are feature-gated on presence of their env vars (client-id/secret) — IndieAuth's
  "gate off by default" (D-08) fits this same env-presence-gated pattern.
- Apple client-secret is already generated per-request (not cached) — D-10 is a one-line `exp` change
  within `generate_apple_client_secret`, not a new mechanism.
- Domain logic lives outside route handlers (mastodon.py, indieauth.py, users.py) — put the new
  pending-merge + email-trust logic in a dedicated module, not inline in routes.

### Integration Points
- New `PendingAccountLink` model + Alembic migration hooks into the existing 9-table schema and
  `api/alembic/versions/` migration chain.
- The pending-merge re-auth flow needs a new callback branch that all existing linked providers can
  route through — wire into the existing per-provider callback structure in `routes.py`.
- `OVID_ENV` becomes a new required env var — must be added to `.env.example` and all compose files,
  and called out in deployment/self-hosting docs as a breaking upgrade step.

</code_context>

<specifics>
## Specific Ideas

- The nOAuth attack class (Microsoft Entra CVE-2023, account pre-hijacking / USENIX Security 2022) is
  the explicit threat model D-01/D-02/D-05 defend against: never treat an unverified/attacker-influenced
  email claim, nor "the next login in this session," as proof of account ownership.
- `OVID_ENV=production` is the sentinel that disables the IndieAuth localhost bypass and must make the
  app refuse to boot if the bypass would otherwise be reachable.
- Apple short exp target: ~300s (a few minutes) — long enough to tolerate clock skew/retries, short
  enough to satisfy "short-lived."

</specifics>

<deferred>
## Deferred Ideas

- Emailed account-merge confirmation link (D-03) — deferred until OVID has general email/SMTP
  infrastructure; would also cover the first-ever-provider merge edge case.
- In-app multi-`kid` Apple key rotation with overlap window (D-11) — deferred to a later milestone
  unless operator demand emerges; `.p8` rotation stays a runbook step for v0.2.0.
- Promoting IndieAuth to a fully-documented, UI-surfaced 5th provider — deferred; gated off by default
  for v0.2.0 (D-08). Revisit if IndieWeb support becomes a headline goal.

</deferred>

---

*Phase: 6-oauth-account-linking*
*Context gathered: 2026-07-06*
