---
phase: 06-oauth-account-linking
plan: 07
subsystem: docs
tags: [docs, oauth, auth, mkdocs, DOCS-03]
requires:
  - "Shipped auth behavior from Plans 06-02/06-03/06-05/06-06 (OVID_ENV, OVID_ENABLE_INDIEAUTH, Apple .p8 rotation, Mastodon SSRF)"
provides:
  - "docs/auth-setup.md — authoritative OAuth setup + operations guide"
  - "mkdocs nav entry under Technical"
affects:
  - "docs/ site nav"
tech-stack:
  added: []
  patterns:
    - "Material for MkDocs admonitions (danger/warning/note) for breaking-change + residual-risk callouts"
key-files:
  created:
    - docs/auth-setup.md
  modified:
    - mkdocs.yml
decisions:
  - "Documented the DNS-rebinding TOCTOU (T-06-05d) as an explicit accepted residual (deferred from Plan 06-02) rather than dropping it"
  - "All env var names, OVID_ENV values, and OVID_ENABLE_INDIEAUTH truthy set verified against shipped code (api/app/auth/*), not from .env.example (permission-denied)"
metrics:
  duration_secs: 165
  completed: 2026-07-07
  tasks: 2
  files: 2
status: complete
---

# Phase 6 Plan 07: OAuth Setup Guide (DOCS-03) Summary

Published `docs/auth-setup.md`, the authoritative operator guide for OVID's OAuth subsystem, and wired it into the mkdocs nav — covering all six DOCS-03 content blocks, verified line-by-line against the shipped `api/app/auth/*` code (written last so it matches exactly what shipped).

## What Was Built

- **`docs/auth-setup.md`** (new) with the six DOCS-03 sections:
  1. Per-provider registration for the four headline providers — GitHub OAuth App, Google Cloud OAuth Client, Apple Sign-In (Service ID + `.p8` Key), and Mastodon (documented as automatic per-instance dynamic registration via `POST /api/v1/apps`, no manual app creation).
  2. Required env vars per provider, using exact names from the code (`GITHUB_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`, `APPLE_CLIENT_ID/TEAM_ID/KEY_ID/PRIVATE_KEY`, plus supporting `OVID_SECRET_KEY`, `OVID_API_URL`), with the `{OVID_API_URL}/v1/auth/<provider>/callback` redirect-URI pattern.
  3. The `OVID_ENV` requirement, flagged prominently as a **breaking change** with a `!!! danger` admonition: accepted values `development`/`production`, refuse-to-boot on unset/unrecognized, and production disabling the localhost bypass by construction.
  4. The Mastodon `httpx`-not-`Mastodon.py` note (deliberate deviation, "don't fix it back" warning) plus the AUTH-05 SSRF posture (dual-stack `getaddrinfo` validation, no redirect-following) **and** the DNS-rebinding TOCTOU accepted-residual note.
  5. The Apple `.p8` rotation runbook (register new key → update `APPLE_KEY_ID`/`APPLE_PRIVATE_KEY` → restart; no code change since `generate_apple_client_secret()` rebuilds the ~300s ES256 secret every exchange).
  6. The IndieAuth opt-in note (off by default → 404; enabled via `OVID_ENABLE_INDIEAUTH` truthy `1`/`true`/`yes`; not a headline provider).
- **`mkdocs.yml`** — added `Auth Setup: auth-setup.md` under the existing `Technical:` nav section; no existing entries reordered or removed.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Write docs/auth-setup.md | 19c27d6 | docs/auth-setup.md |
| 2 | Add auth-setup.md to mkdocs nav | 6fed2cd | mkdocs.yml |

## Verification

- Task 1 automated grep: `DOCS_OK` (OVID_ENV, breaking, httpx, OVID_ENABLE_INDIEAUTH, .p8/rotation, all four providers present).
- Task 2 automated grep: `NAV_OK` (auth-setup.md + api-reference.md + fingerprint-spec.md all present).
- `mkdocs build --strict` in a fresh venv from `docs/requirements.txt` (mkdocs-material): **exit 0** — nav wired, no broken internal links (cross-links to `self-hosting.md` and `deployment.md` resolve). The only INFO-level "not in nav" pages are pre-existing spec/ADR files unrelated to this plan; auth-setup.md is correctly in the nav. The Material team's MkDocs-2.0 advisory banner is an upstream informational notice, not a build error.

## Code-vs-Doc Grounding (every behavioral claim verified against shipped code)

`.env.example` is permission-denied in this environment, so all env var names and semantics were cross-referenced directly against source:

- `api/app/auth/config.py` — `OVID_ENV` required via `_require_env`, must be `development`/`production` else `RuntimeError` at import; `ALLOW_LOCALHOST_BYPASS = OVID_ENV != "production"` with an explicit invariant assertion. `OVID_SECRET_KEY` required.
- `api/app/auth/routes.py` — GitHub scope `user:email read:user`; Google OIDC discovery + `openid email profile`; Apple four-var `_APPLE_CONFIGURED` gate, `generate_apple_client_secret()` `exp = now + 300`; redirect URIs `{OVID_API_URL}/v1/auth/<provider>/callback`; separate `indieauth_router`.
- `api/main.py` — IndieAuth registered only when `OVID_ENABLE_INDIEAUTH.lower() in ("1","true","yes")`.
- `api/app/auth/mastodon.py` — `validate_mastodon_domain()` uses dual-stack `socket.getaddrinfo` and rejects private/loopback/link-local/multicast/reserved IPs; `get_or_register_client()` independently re-resolves DNS on the outbound `httpx.post` (the TOCTOU residual).

## Deviations from Plan

None — plan executed as written. No auto-fixes required; all documented behavior matched the shipped code, so no doc-vs-code mismatch or inline code fix was needed.

## Accepted Residual Documented (carry-forward from Plan 06-02)

The DNS-rebinding TOCTOU (threat T-06-05d) — validate-then-connect resolves the Mastodon host twice, so a rebinding attacker could pass validation then serve a private IP on the real request — is documented in `docs/auth-setup.md` under "Known limitation / accepted residual" with a `!!! warning` admonition, an explanation of the full IP-pinning fix that is deferred, and an egress-firewall defense-in-depth recommendation. It was not silently dropped.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: docs/auth-setup.md
- FOUND: mkdocs.yml (nav entry present)
- FOUND commit 19c27d6 (Task 1)
- FOUND commit 6fed2cd (Task 2)
