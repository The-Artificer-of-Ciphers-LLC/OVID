---
phase: 07-web-ui-production-readiness
plan: 08
subsystem: deploy
tags: [deployment, docker-compose, cors, staging, oauth, accessibility]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness (07-04)
    provides: Disc detail fingerprint aliases + withheld-structure message
  - phase: 07-web-ui-production-readiness (07-05)
    provides: Search anchor + primitives
  - phase: 07-web-ui-production-readiness (07-06)
    provides: Submit form + set/chapter a11y parity
  - phase: 07-web-ui-production-readiness (07-07)
    provides: "linkProvider option-b add-provider flow; the concrete infra dependency (credentialed cross-origin CORS + session cookie) this plan documents/verifies for staging"
provides:
  - "docs/deployment.md 'Staging' section — chosen hosts (staging.oviddb.org / api.staging.oviddb.org), redshirt/DNS/TLS prerequisites, required CORS_ORIGINS + NEXT_PUBLIC_API_URL wiring, session-cookie mechanics for the 07-07 add-provider flow, a local/uncommitted docker-compose.staging.yml recipe, and the recorded green phase-gate result"
  - ".env.example staging example entries (commented) for CORS_ORIGINS and NEXT_PUBLIC_API_URL"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Staging is documented as a fourth deployment tier (dev/prod/test/staging), following the existing per-environment docker-compose override convention (docker-compose.prod.yml, docker-compose.test.yml) but as a LOCAL, gitignored docker-compose.staging.yml (not committed to the repo) — mirrors how .env.test is already gitignored."
    - "Port bracket convention extended: dev x000, prod x100, test x200, staging x300 (8300/3300), DB not exposed (mirrors prod)."

key-files:
  created: []
  modified:
    - .env.example
    - docs/deployment.md

key-decisions:
  - "Exact staging hostnames (Claude's discretion per 07-CONTEXT.md): staging.oviddb.org (web) / api.staging.oviddb.org (api), consistent with 07-RESEARCH.md's suggested naming."
  - "Staging is a genuinely separate API+DB deployment (not a DNS-only repoint of the existing prod containers), because Pitfall 3 requires a DISTINCT NEXT_PUBLIC_API_URL build pointing at the staging API host, not oviddb.org's. This also matches threat T-07-08-02's framing (staging's near-empty catalog is acceptable specifically because it is non-apex; Phase 8 owns seeding)."
  - "No docker-compose.staging.yml is created/committed by this plan — the plan's own files_modified scope is .env.example + docs/deployment.md only, and prod/test overrides already establish the convention that each tier hardcodes its own container names/ports/build-arg. The full compose-override YAML is embedded as a copy-adaptable code block inside docs/deployment.md instead, explicitly labeled local/uncommitted (mirrors .env.test's gitignored status)."
  - "OVID_ENV stays 'production' for staging (not a third value) — the API only accepts development|production and refuses to boot otherwise; staging is a public HTTPS deployment needing the same security posture (disabled localhost auth bypass) as real prod. 'Staging' is a hostname/DNS distinction, not an OVID_ENV value."
  - "No api/main.py code change for the 07-07 add-provider (Option B) cross-origin session-cookie flow. Investigated SessionMiddleware's config in api/main.py (SameSite=Lax default, no explicit Domain, https_only=False default) and confirmed by design it requires no change: the credentialed fetch sets a cookie scoped to the API host only (by design — no shared-domain cookie needed since the OAuth round-trip returns the JWT via web_redirect_uri query param, not a cookie read by the web origin), and SameSite=Lax cookies ARE sent on the subsequent TOP-LEVEL window.location.assign() navigation to the API's /login route (Lax only blocks cross-site subresource/fetch use, not top-level GET navigations). This is documented in docs/deployment.md rather than requiring a code change, and was deliberately kept out of scope: it is pre-existing Phase 6 code, unrelated to and untouched by this plan's own files, and not required for the flow to function — see 'Deferred/Considered but not changed' below."
  - "docker-compose.prod.yml is unmodified — verified via git diff before commit."

requirements-completed: [WEBUI-01]

coverage:
  - id: D1
    description: "docs/deployment.md documents the staging CORS_ORIGINS allowlist requirement, the distinct NEXT_PUBLIC_API_URL build arg, and the redshirt/DNS/TLS prerequisites"
    requirement: "WEBUI-01"
    verification:
      - kind: other
        ref: "grep -c 'staging' docs/deployment.md == 41 (>=1 required)"
        status: pass
    human_judgment: false
  - id: D2
    description: ".env.example contains commented staging example values for CORS_ORIGINS and NEXT_PUBLIC_API_URL"
    requirement: "WEBUI-01"
    verification:
      - kind: other
        ref: "grep -Ec 'CORS_ORIGINS|NEXT_PUBLIC_API_URL' .env.example == 7 (>=2 required)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Full web + api test suites green as the phase gate, result recorded in docs/deployment.md"
    requirement: "WEBUI-01"
    verification:
      - kind: unit
        ref: "cd web && npm test (93/93 pass); cd api && .venv/bin/python -m pytest tests/ -q (450/450 pass, 0 warnings)"
        status: pass
      - kind: other
        ref: "cd web && npx eslint . (0 issues)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live staging deploy + D-03 accessibility floor sign-off over TLS (search, disc detail+aliases, submit, settings add/remove+merge redirect, keyboard/AA-contrast both themes)"
    requirement: "WEBUI-01"
    verification:
      - kind: manual
        ref: "checkpoint:human-verify — NOT executable by this agent (requires live staging infra + human a11y judgment). See 'Human verification required' below."
        status: pending
    human_judgment: true

# Metrics
duration: ~20min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 8: Staging deploy documentation + phase gate Summary

**Documented the D-06 staging deployment env (CORS_ORIGINS allowlist, distinct build-time NEXT_PUBLIC_API_URL, redshirt/DNS/TLS prerequisites, 07-07's cross-origin session-cookie mechanics) and recorded a green full-suite phase gate (web 93/93, api 450/450, eslint 0/0) — the two autonomous tasks of this plan are complete. The plan's third task is a human-verify checkpoint (live staging deploy + D-03 accessibility sign-off) that cannot be performed by this agent; see "Human verification required" below.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-07
- **Tasks:** 2 of 3 (Task 1 + Task 2 autonomous, both complete; Task 3 is a human-verify checkpoint, not executable here)
- **Files modified:** 2 (.env.example, docs/deployment.md)

## Accomplishments

- **Task 1 — Staging env wiring documented.** Added a full "Staging" section to `docs/deployment.md`:
  chosen hosts (`staging.oviddb.org` web / `api.staging.oviddb.org` api, port bracket `x300`), external
  redshirt/DNS/TLS prerequisites, the `CORS_ORIGINS` allowlist requirement (Pitfall 2 / threat
  T-07-08-01 — `_validate_web_redirect_uri` fails closed otherwise), the distinct build-time
  `NEXT_PUBLIC_API_URL` arg (Pitfall 3 — baked into the client bundle, not runtime-overridable), why
  `OVID_ENV` stays `production` for staging, and the concrete cross-origin session-cookie mechanics that
  make 07-07's "Link a provider" (Option B: credentialed fetch + top-level navigate) work with zero
  staging-specific code changes. Also added a local/uncommitted `docker-compose.staging.yml` recipe
  (embedded as a doc code block, not a committed file) and matching commented staging examples in
  `.env.example`. Updated the top-of-doc environment/port tables to include the new Staging tier.
  `docker-compose.prod.yml` is verified unchanged (`git diff --stat` empty).
- **Task 2 — Phase gate run and recorded.** Ran the full `web` Vitest suite (93/93 pass), the full `api`
  pytest suite (450/450 pass, 0 warnings — better than the "two pre-existing deprecation warnings"
  baseline noted in the plan, none were emitted in this run), and `npx eslint .` in `web/` (0 issues).
  Recorded the exact counts and commands in `docs/deployment.md`'s "Verified state" note.
- **Task 3 — human-verify checkpoint, NOT performed by this agent.** The live staging deploy + D-03
  accessibility sign-off requires actual staging infrastructure (DNS, redshirt TLS routing, a built
  staging web image) and human accessibility judgment that this agent cannot perform. See "Human
  verification required" below for the exact items a person must check.

## Task Commits

1. **Task 1 (docs):** `8bbe22c` — `docs(07-08): document staging deploy env wiring (D-06)`
2. **Task 2 (docs):** `b46e139` — `docs(07-08): record green phase-gate result (web 93/93, api 450/450)`

## Files Created/Modified
- `.env.example` — new commented "Staging deploy (D-06)" section with example `CORS_ORIGINS` and
  `NEXT_PUBLIC_API_URL` values, cross-referencing `docs/deployment.md`.
- `docs/deployment.md` — new "Staging" section (chosen hosts, prerequisites, env wiring, build/run
  recipe, verified-state phase-gate result, human sign-off pointer); updated the top environment/port
  overview tables to include the Staging tier.

## Decisions Made
See `key-decisions` in frontmatter for the full rationale on: staging as a separate API+DB deployment
(not a DNS-only repoint of prod), no committed `docker-compose.staging.yml` (kept within this plan's
`.env.example` + `docs/deployment.md` file scope), `OVID_ENV` staying `production` for staging, and why
no `api/main.py` change was made for the 07-07 cross-origin session-cookie dependency.

## Deviations from Plan

### Considered at plan time, FIXED in a follow-up hardening commit (no longer deferred)

**SessionMiddleware cookie config (`api/main.py`) for 07-07's add-provider flow.** While researching the
dependency context (07-07's Option B credentialed-fetch-then-navigate flow, which needs the session
cookie to survive a cross-subdomain round-trip on staging), I read `api/main.py`'s
`SessionMiddleware(secret_key=SECRET_KEY)` call and confirmed its defaults: `SameSite=Lax`, `HttpOnly`,
no explicit `Domain`, `https_only=False` (no `Secure` attribute set). At the time this plan executed, I
concluded no functional change was required for the flow to *work* (the credentialed fetch sets a
cookie scoped to the API host only — by design, since the OAuth round-trip returns the JWT via a
`web_redirect_uri` query param, not a cookie the web origin needs to read — and `SameSite=Lax` cookies
ARE sent on the subsequent **top-level** `window.location.assign()` navigation to the API's own
`/login` route, since Lax blocks cross-site use only on subresource/fetch requests, not top-level GET
navigations), and left the missing `Secure`/`https_only=True` attribute "documented for visibility, not
changed" — a real, if narrow, hardening gap (the session cookie would still work but wasn't marked
HTTPS-only).

**This was surfaced again during the Phase 7 deploy review and FIXED inline** in a follow-up hardening
commit (`fix(07): env-gate session cookie Secure flag for production (surfaced by D-06 deploy review)`),
rather than left deferred: `api/main.py` now reads an optional `SESSION_COOKIE_SECURE` env var
(defaulting to `false`, so local `http://localhost` dev and the existing TestClient suite are
unaffected) and passes it through as `SessionMiddleware(..., https_only=SESSION_COOKIE_SECURE,
same_site="lax")`. `SESSION_COOKIE_SECURE=true` is now documented as required env for any HTTPS
deployment in both `.env.example` and `docs/deployment.md` (staging "Required env wiring" section,
alongside `CORS_ORIGINS` and the `SameSite=Lax` mechanism already documented there), and covered by
`api/tests/test_session_cookie_secure.py`.

**Total deviations:** 0 code deviations within this plan's own scope. One item identified during this
plan's investigation as a real hardening gap, initially left unmodified as out-of-scope, and
subsequently fixed (not merely documented) in a dedicated follow-up commit — see above.

## Issues Encountered
None. Both autonomous tasks completed on the first pass with no fix-attempt cycles.

## Human Verification Required

**This is the phase-level UAT gate — the checkpoint below has NOT been executed by this agent.** A human
must complete it before Phase 7 / WEBUI-01's D-06 "verifiably deployable + live on staging" criterion (and
the D-03 blocking accessibility gate) can be marked verified.

**Prerequisites (external infra — see `docs/deployment.md` "Staging" section):**
1. DNS: `staging.oviddb.org` + `api.staging.oviddb.org` A records added (Cloudflare, proxied).
2. redshirt TLS routing configured for both staging hostnames, pointing at `holodeck:3300` (web) /
   `holodeck:8300` (api).
3. A staging API instance running with `CORS_ORIGINS=https://staging.oviddb.org` and a staging web image
   built with `--build-arg NEXT_PUBLIC_API_URL=https://api.staging.oviddb.org` (see the
   `docker-compose.staging.yml` recipe in `docs/deployment.md`).

**Verification checklist (all over `https://staging.oviddb.org`):**
1. **Search:** enter a title; confirm the input is the centered focal anchor, results/count/pagination
   render, and the empty-state hint is legible (AA contrast) in BOTH light and dark themes.
2. **Disc detail:** open a disc; confirm the Fingerprint aliases section lists ALL identity strings with
   the primary badged (`data-testid="fingerprint-aliases"`); open an unverified disc and confirm the
   "Structure withheld until a second contributor verifies this disc." message renders.
3. **Submit:** sign in, upload an `ovid fingerprint --json` output, confirm preview + submit success;
   confirm the set-toggle and form fields are keyboard-operable (Tab/Space/Enter) with visible focus
   rings.
4. **Settings:** confirm "Link a provider" initiates the add flow; unlink a provider (the last-remaining
   one stays disabled with the correct copy); trigger an email-conflict and confirm the merge banner is
   styled (not raw JSON on the API host), names only the current account's own providers, offers a
   re-auth link, and leaks no email/account id (D-04 redirect + ME-02).
5. **Accessibility (D-03, blocking):** tab through every interactive element on all four surfaces above —
   each shows a visible `:focus-visible` ring; Escape dismisses any open dropdown/dialog; verify WCAG AA
   contrast (4.5:1 text, 3:1 UI) in BOTH light and dark themes.

**Resume signal:** "approved" once staging is live and all five checks (including the D-03 a11y floor)
pass in both themes, or describe the specific issues found so they can be fixed and re-verified.

## Next Phase Readiness
- Both autonomous tasks of the final Phase 7 plan are complete: staging deploy env is fully documented
  and wired (docs + `.env.example`), and the phase gate (full web + api suites, eslint) is green.
- Phase 7 (WEBUI-01..04) code/docs work is now complete pending only the human staging + a11y sign-off
  above — this is expected per the plan's own `autonomous: false` / `checkpoint:human-verify` design, not
  a blocker introduced by this plan.
- Phase 8 (Launch Readiness) owns the public `oviddb.org` apex cutover, domain redirects, and DB seeding
  — explicitly out of scope here per D-06.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: .env.example
- FOUND: docs/deployment.md
- FOUND: .planning/phases/07-web-ui-production-readiness/07-08-SUMMARY.md
- FOUND commit: 8bbe22c
- FOUND commit: b46e139
