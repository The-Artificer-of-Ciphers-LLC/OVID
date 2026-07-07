# Phase 7: Web UI Production Readiness - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the existing Next.js web UI **production-ready** for the OVID v0.2.0 milestone:
search (WEBUI-01), disc detail rendering the full normalized structure incl. fingerprint
aliases (WEBUI-02), the authenticated submit form (WEBUI-03), and the account-settings
surface for add/remove of linked providers wired to Phase 6's AUTH-06/07 (WEBUI-04).

Most pages and components already exist — this phase is **wiring, polish, accessibility,
and completeness**, not greenfield UI. It also carries an explicit mandate to **re-review
the re-integrated multi-disc-set and chapter-name features** (UI + API + client) for
architectural fit before they count as production-ready.

**Out of scope (other phases):** DB seeding, domain redirects, ARM review, and the public
announcement are Phase 8 (Launch Readiness). New product capabilities are their own phases.
</domain>

<decisions>
## Implementation Decisions

### Re-integrated Feature Re-review (multi-disc-set + chapter-name)
- **D-01:** **Risk-based targeted review**, not a full audit and not accept-as-is. Bounded checklist:
  1. **Security-model seams** — confirm `/v1/set` (`api/app/routes/set.py`) and `DiscChapter`
     paths in `api/app/routes/disc.py` don't bypass or duplicate main's current
     submission-attribution, rate-limiting, alias-resolution, or D-09 anti-echo redaction logic.
  2. **Migrations** — verify `900000000008` (disc-set unique constraint) and `900000000009`
     (disc_chapters) are correctly ordered and idempotent against main's migration head.
  3. **Dead/duplicate code** — sweep for leftovers from the merge-conflict resolution.
  4. **UX parity** — `SiblingDiscs`/`SetSearchInput`/`ChapterEditor`/`ChapterList` match the
     rest of the production UI (styling, a11y, states).
  Escalate to a fuller audit **only if** the targeted pass surfaces a genuine security-model
  or migration-integrity issue. Tests are already green (api 442, ovid-client 266, web 58, tsc clean).

### Styling / Design System
- **D-02:** Introduce a **Tailwind v4 `@theme` design-token layer** (colors, spacing, dark-mode
  via `@custom-variant dark`) plus a small set of **shared primitives** (Button, Input, Field).
  Keep bespoke components; migrate incrementally. **No component library, no new runtime deps**
  (honors "no gratuitous dependencies" + "do not re-platform"). shadcn/ui is explicitly deferred
  (see Deferred Ideas) unless complex interactive widgets emerge.
- **D-03:** **Production accessibility floor** (applies to ALL UI regardless of component):
  visible `:focus-visible` on every interactive element; WCAG AA contrast (4.5:1 text, 3:1 UI)
  verified in **both** light and dark themes; full keyboard operability (tab order, Enter/Space
  activation, Escape to dismiss any dropdown/dialog); label/aria association for all form controls
  with `aria-live` on validation errors.

### Account-Settings Merge UX (WEBUI-04)
- **D-04:** **Required backend fix (small):** `finalize_auth`'s merge-offer path
  (`api/app/auth/routes.py`) currently returns a **raw 409 `JSONResponse` with no redirect**,
  so a browser dead-ends on unstyled JSON on the API host. Change it to **redirect back to the
  web app** (to `web_redirect_uri` with `error=email_conflict&pending_link_id=<id>`), matching
  the success path. Keep it **enumeration-safe** — do NOT leak the matched account/email
  (mirror the existing ME-02 guard; no `existing_user_id` in the response).
- **D-05:** **Settings UI = "middle" depth.** `ProviderList` + `settings/page.tsx`: add/remove
  linked providers, surfacing the min-one guard clearly (`400 cannot_unlink_last`). On an
  email-conflict return, show an **explanatory banner** naming the already-linked provider(s)
  plus a **direct re-auth link** (`GET /v1/auth/<provider>/login?pending_link_id=<id>`) so the
  user can complete the merge. **No** fully-automated pending-merge orchestration (deferred to
  v1.0). Mastodon/IndieAuth never surface email-merge; IndieAuth is hidden in production.

### Deployment Scope
- **D-06:** Phase 7 deploys the web app to a **staging/preview URL** for real-environment
  verification (build, container via the `web` service in `docker-compose.prod.yml`, TLS, DNS,
  env wiring). The **public `oviddb.org` apex cutover is promoted in Phase 8** alongside DB
  seeding + domain redirects — avoids exposing a near-empty catalog publicly. Phase 7's
  success-criterion 1 ("live at oviddb.org") is reinterpreted as **"verifiably deployable +
  live on staging"**; Phase 8 owns the public go-live.
  **Roadmap action:** update Phase 7 success-criterion 1 wording (staging) vs Phase 8 (apex)
  to avoid a promised-but-deferred coverage gap.

### Claude's Discretion
- Exact staging URL/subdomain, primitive component API shapes, and token naming are left to
  research/planning within the decisions above.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WEBUI-01, WEBUI-02, WEBUI-03, WEBUI-04 (verbatim requirements)
- `.planning/ROADMAP.md` §"Phase 7: Web UI Production Readiness" — goal, success criteria, and the carried-in re-review note

### Auth / account-settings (WEBUI-04)
- `.planning/phases/06-oauth-account-linking/06-CONTEXT.md` — Phase 6 decisions Phase 7 consumes (confirm-gated merge, re-auth via existing provider, email-verified allowlist, IndieAuth gating)
- `api/app/auth/routes.py` (`finalize_auth`, ~lines 118–208) — the merge-offer 409 needing the redirect fix (D-04); per-provider `/login` `pending_link_id` plumbing
- `api/app/auth/merge.py` — `resolve_auth`, ME-02 enumeration guard (mirror in the UI/banner)
- `docs/auth-setup.md` — operator OAuth reference

### Re-integrated features (re-review, D-01)
- `api/app/routes/set.py`, `api/app/routes/disc.py` — disc-set + chapter API integration
- `api/alembic/versions/900000000008_add_disc_set_number_unique.py`, `api/alembic/versions/900000000009_add_disc_chapters.py`
- `ovid-client/src/ovid/disc_structure.py` (chapter normalization wiring), `ovid-client/src/ovid/bdmt_parser.py`
- Git commits `f2c7a20` (disc-set) and `63d9417` (chapter) — the re-integration diffs

### Deployment (D-06)
- `docker-compose.prod.yml` — `web` service (oviddb.org:3100 via redshirt proxy) + api prod stack
- `web/Dockerfile`

### Frontend conventions
- `web/AGENTS.md` — Next.js 16 has breaking changes vs training data; consult `node_modules/next/dist/docs/` before writing App Router code
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Pages (`web/app/`): `page.tsx` (search), `disc/[fingerprint]/page.tsx` (detail), `submit/page.tsx`, `settings/page.tsx`, `disputes/page.tsx`, `auth/callback/page.tsx`, `layout.tsx`
- Components (`web/components/`): `SearchForm`, `DiscCard`, `DiscStructure`, `SubmitForm`, `ProviderList`, `NavBar`, `DisputeResolver`, `EditHistory` + re-integrated `SiblingDiscs`, `SetSearchInput`, `ChapterEditor`, `ChapterList`
- `web/lib/api.ts` (typed fetch client, `ApiError{status,code}`), `web/lib/auth.ts` (`useAuth`)

### Established Patterns
- Bespoke Tailwind v4 with `dark:` variants, no component library; `data-testid` on tested controls; strict TS; `@/` path alias
- API client mocked wholesale in Vitest; typed `ApiError` mirrored in tests
- Next.js 16 App Router (file-based routing, dynamic `[fingerprint]` segment)

### Integration Points
- Settings page ↔ Phase 6 AUTH-06/07 backend + the new D-04 redirect fix
- Disc detail ↔ `fingerprint_aliases` (Phase 1), `disc_set` + `chapters` (re-integrated features)
- Staging deploy ↔ `docker-compose.prod.yml` `web` service behind redshirt proxy
</code_context>

<specifics>
## Specific Ideas

- Use Tailwind v4's native `@theme` directive for tokens (no external theming lib).
- The merge-offer banner copy must not reveal which account/email matched (enumeration guard).
- Deploy verification should exercise the real prod container + TLS path, not just a local build.
</specifics>

<deferred>
## Deferred Ideas

- **Full automated pending-merge re-auth flow** (persist `pending_link_id` across redirects,
  TTL/expiry handling, `merge_reauth_required`/`pending_link_invalid` states, multi-provider
  disambiguation) — post-launch / v1.0 enhancement, revisit if usage shows email-collision
  merges are common.
- **shadcn/ui (Radix) adoption** — only if the submit/dispute/settings flows grow genuinely
  complex interactive widgets (comboboxes, modal dialogs) where hand-rolled ARIA/focus is risky.
- **Public `oviddb.org` apex cutover, domain redirects (`.com`/`.net`), and DB seeding (500+ discs)**
  — Phase 8 (Launch Readiness).
</deferred>

---

*Phase: 07-web-ui-production-readiness*
*Context gathered: 2026-07-07*
