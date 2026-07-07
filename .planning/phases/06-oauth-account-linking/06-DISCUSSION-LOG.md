# Phase 6: OAuth & Account Linking - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 6-oauth-account-linking
**Areas discussed:** Merge confirm + re-auth flow, Provider email-trust policy, IndieAuth scope + bypass gating, Apple secret lifetime + rotation
**Mode:** advisor (research-backed comparison tables; calibration tier: standard)

---

## Account-merge confirm + re-auth flow (AUTH-08)

| Option | Description | Selected |
|--------|-------------|----------|
| DB row + re-login | Server-side PendingAccountLink row (TTL + single-use) + fresh OAuth re-login through an already-linked provider. Strongest, unit-testable, replaces the session-state flaw. | ✓ |
| DB row + emailed confirm link | Same row, confirmation via signed link emailed to on-file address. Safe + covers first-provider case, but needs net-new email/SMTP infra OVID lacks. | |
| Signed token only | Short-lived signed token as sole carrier, no DB row. Can't enforce single-use/revocation without reintroducing a denylist row. | |

**User's choice:** DB row + re-login (Recommended)
**Notes:** Current session-carried pending-link merges into whatever account logs in next — the structural nOAuth flaw this phase closes. Email variant deferred (no email infra); session-only and token-only rejected.

---

## Provider email-trust policy (AUTH-08)

| Option | Description | Selected |
|--------|-------------|----------|
| Signal-based allowlist | Merge-offer only on real verified signal: GitHub /user/emails primary+verified, Google & Apple id_token.email_verified===true. Mastodon + IndieAuth never email-match. | ✓ |
| Explicit-link-only for all | No provider ever auto-offers on email match; every link requires an already-authenticated explicit connect. Maximally safe, worse UX for legit multi-provider users. | |

**User's choice:** Signal-based allowlist (Recommended)
**Notes:** Resolves the STATE.md open question on Mastodon/IndieAuth email trust; generalizes REQUIREMENTS' existing "Mastodon-merge disabled" default into one rule: no verified signal → no email match. Non-trusted providers attach only via authenticated explicit-link.

---

## IndieAuth scope (AUTH-10)

| Option | Description | Selected |
|--------|-------------|----------|
| Gate off by default | Register IndieAuth routes only on explicit operator opt-in; disabled/404 otherwise. Matches roadmap's four named providers. | ✓ |
| Promote to documented 5th provider | Keep fully on, document + UI button, same UAT/hardening bar. Avoids undocumented path but commits v0.2.0 to a 5th provider's edge cases. | |

**User's choice:** Gate off by default (Recommended)
**Notes:** Roadmap names only four headline providers; the actual defect is a bypass bug (see bypass gating below), not an IndieAuth protocol flaw. "Keep on but undocumented" explicitly rejected as a final state.

---

## IndieAuth localhost-bypass gating mechanism (AUTH-10)

| Option | Description | Selected |
|--------|-------------|----------|
| Single required OVID_ENV | One required env var, no default; bypass allowed iff OVID_ENV != "production"; import-time assertion mirrors _require_env fail-fast. Impossible to misconfigure silently. Breaking change on upgrade. | ✓ |
| Two vars: OVID_ALLOW_LOCALHOST_AUTH + OVID_ENV | Dedicated bypass flag (default false) + OVID_ENV; boot fails if flag true while OVID_ENV=production. Keeps OVID_ENV free for future config but must treat "flag true + OVID_ENV unset" as fatal. | |

**User's choice:** Single required OVID_ENV (Recommended)
**Notes:** Reusing OVID_MODE was researched and rejected — `standalone` is the default in both dev and self-host-prod compose, so it carries no dev/prod signal. Single signal = smallest misconfiguration surface. `OVID_ENV=production` is the sentinel that disables the bypass.

---

## Apple client-secret lifetime + rotation (AUTH-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Short exp, single key, runbook | Drop exp 6mo → ~5 min, regenerated per exchange (= automatic secret rotation). Single .p8; key rotation via ops runbook. One-line code change. | ✓ |
| Short exp + in-app multi-kid rotation | Also add in-app multi-.p8 support (kid selection + overlap) for zero-downtime key rotation. More complete but 3-4 files + new env schema for a rare event. | |

**User's choice:** Short exp, single key, runbook (Recommended)
**Notes:** Per-exchange regeneration of a short-lived JWT IS the "automatic rotation" AUTH-03 asks for; Apple caps exp at 6mo and there's no rate limit on local ES256 signing. Keeping 6-month exp rejected (fails AUTH-03). Buffer >60s for clock skew; existing test_auth_apple.py (11 tests) must update.

## Claude's Discretion

- Mastodon SSRF completeness audit (AUTH-05) — prescribed guardrail behaviors; researcher/planner determine coverage gaps vs. existing `validate_mastodon_domain`. Not a user gray area.
- Exact PendingAccountLink columns/indexes, endpoint paths, migration id — planner's call per existing conventions.
- Exact OVID_ENV accepted values beyond the `production` sentinel — planner's call.

## Deferred Ideas

- Emailed account-merge confirmation link — deferred until OVID has email/SMTP infrastructure.
- In-app multi-kid Apple key rotation — deferred to a later milestone; `.p8` rotation stays a runbook step.
- Promoting IndieAuth to a documented, UI-surfaced 5th provider — deferred; gated off by default for v0.2.0.
