# Phase 7: Web UI Production Readiness - Research

**Researched:** 2026-07-07
**Domain:** Next.js 16 App Router frontend (production polish, wiring, accessibility, completeness) + a small FastAPI backend fix (D-04) + re-review of two re-integrated features
**Confidence:** HIGH (findings are grounded in the actual repo, not assumptions — every UI/API contract below was cross-verified route→schema→client)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Re-integrated feature re-review (multi-disc-set + chapter-name):** Risk-based targeted review, not a full audit and not accept-as-is. Bounded checklist:
  1. Security-model seams — confirm `/v1/set` (`api/app/routes/set.py`) and `DiscChapter` paths in `api/app/routes/disc.py` don't bypass or duplicate main's current submission-attribution, rate-limiting, alias-resolution, or D-09 anti-echo redaction logic.
  2. Migrations — verify `900000000008` (disc-set unique constraint) and `900000000009` (disc_chapters) are correctly ordered and idempotent against main's migration head.
  3. Dead/duplicate code — sweep for leftovers from the merge-conflict resolution.
  4. UX parity — `SiblingDiscs`/`SetSearchInput`/`ChapterEditor`/`ChapterList` match the rest of the production UI (styling, a11y, states).
  Escalate to a fuller audit only if the targeted pass surfaces a genuine security-model or migration-integrity issue. Tests are already green (api 442, ovid-client 266, web 58, tsc clean).

**D-02 — Styling / Design System:** Introduce a Tailwind v4 `@theme` design-token layer (colors, spacing, dark-mode via `@custom-variant dark`) plus a small set of shared primitives (Button, Input, Field). Keep bespoke components; migrate incrementally. **No component library, no new runtime deps.** shadcn/ui explicitly deferred unless complex interactive widgets emerge.

**D-03 — Production accessibility floor (applies to ALL UI):** visible `:focus-visible` on every interactive element; WCAG AA contrast (4.5:1 text, 3:1 UI) verified in **both** light and dark themes; full keyboard operability (tab order, Enter/Space activation, Escape to dismiss any dropdown/dialog); label/aria association for all form controls with `aria-live` on validation errors.

**D-04 — Required backend fix (small):** `finalize_auth`'s merge-offer path (`api/app/auth/routes.py`) currently returns a raw 409 `JSONResponse` with no redirect, so a browser dead-ends on unstyled JSON on the API host. Change it to redirect back to the web app (to `web_redirect_uri` with `error=email_conflict&pending_link_id=<id>`), matching the success path. Keep it enumeration-safe — do NOT leak the matched account/email (mirror the existing ME-02 guard; no `existing_user_id` in the response).

**D-05 — Settings UI = "middle" depth.** `ProviderList` + `settings/page.tsx`: add/remove linked providers, surfacing the min-one guard clearly (`400 cannot_unlink_last`). On an email-conflict return, show an explanatory banner naming the already-linked provider(s) plus a direct re-auth link (`GET /v1/auth/<provider>/login?pending_link_id=<id>`) so the user can complete the merge. **No** fully-automated pending-merge orchestration (deferred to v1.0). Mastodon/IndieAuth never surface email-merge; IndieAuth is hidden in production.

**D-06 — Deployment Scope:** Phase 7 deploys the web app to a **staging/preview URL** for real-environment verification (build, container via the `web` service in `docker-compose.prod.yml`, TLS, DNS, env wiring). The public `oviddb.org` apex cutover is promoted in Phase 8 alongside DB seeding + domain redirects. Phase 7's success-criterion 1 ("live at oviddb.org") is reinterpreted as **"verifiably deployable + live on staging."** Roadmap action: update Phase 7 SC-1 wording (staging) vs Phase 8 (apex).

### Claude's Discretion
- Exact staging URL/subdomain, primitive component API shapes, and token naming are left to research/planning within the decisions above.

### Deferred Ideas (OUT OF SCOPE)
- Full automated pending-merge re-auth flow (persist `pending_link_id` across redirects, TTL/expiry, `merge_reauth_required`/`pending_link_invalid` states, multi-provider disambiguation) — post-launch / v1.0.
- shadcn/ui (Radix) adoption — only if flows grow genuinely complex interactive widgets.
- Public `oviddb.org` apex cutover, domain redirects (`.com`/`.net`), and DB seeding (500+ discs) — Phase 8.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| WEBUI-01 | Search by movie title returns known disc releases (live at oviddb.org) | **Already working.** `web/app/page.tsx` (server component) → `searchReleases()` → `GET /v1/search`. Empty/zero/error states + pagination present. Gap is only production-deploy (D-06) + a11y/token polish. |
| WEBUI-02 | Disc detail renders full normalized structure (titles, main-feature, chapters, audio/subtitle tracks) **and shows fingerprint aliases** | Structure/chapters/tracks render via `DiscStructure`+`ChapterList`. **GAP: fingerprint aliases are fetched but NEVER rendered** — the single biggest requirement gap in the phase. Backend already returns `fingerprint_aliases` (verified). |
| WEBUI-03 | Authenticated user submits a new disc via the submit form | **Already working.** `SubmitForm` → `submitDisc()` → `POST /v1/disc` (Bearer). Includes set-linking + chapter editor. Gap is a11y/token polish + re-review of set/chapter UX (D-01). |
| WEBUI-04 | Account settings surface (linked providers add/remove) wired to AUTH-06/07 | **Partial.** Remove (unlink) works with min-one guard. **GAP: no "add / link a provider" UI at all**, and **GAP: no email-conflict merge banner (D-05)**. Backend `POST /v1/auth/link/{provider}` exists but is unused; D-04 backend redirect fix required. |
</phase_requirements>

## Summary

Phase 7 is **not greenfield** — the Next.js 16 web app already has every page and most components, 58 passing Vitest tests, a working search path, a working submit path, a working unlink path, and a production-ready multi-stage Dockerfile wired into `docker-compose.prod.yml`. The job is to close **real, specific gaps** against the four requirements plus raise the whole surface to the D-02 token layer and D-03 accessibility floor, ship a D-04 backend redirect fix, and re-review two re-integrated features (D-01).

Three requirement-level gaps are concrete and verified in code: (1) **fingerprint aliases are fetched but never rendered** on the disc-detail page (WEBUI-02); (2) **there is no "add/link a provider" UI** in settings (WEBUI-04); (3) **there is no email-conflict merge banner** and the backend merge-offer still dead-ends on raw JSON (D-04/D-05, WEBUI-04). Everything else is polish: the design-token layer (`globals.css` still ships the Next.js starter `body { font-family: Arial }` drift and has no `@theme` token block or shared primitives), `:focus-visible` rings (currently zero — only mouse-noisy `focus:` is used), and WCAG-AA contrast verification in both themes.

The re-review surfaced two backend findings worth planning around: (a) a **possible anti-echo redaction leak** — `_build_disc_set_nested` exposes an unverified sibling's derived structural data (main-title name, duration, track_count) through the set view even though a direct lookup of that sibling would redact its titles (D-09); and (b) `POST /v1/set` carries only the volumetric `_dynamic_limit`, **not** the stacked `AUTH_WRITE_LIMIT` per-account write ceiling the other three write routes carry (INFRA-04 seam inconsistency). Migrations `900000000008`→`900000000009` chain correctly onto Phase 6's `900000000007` head.

**Primary recommendation:** Structure the phase as (Wave A) the design-token/primitive foundation + D-04 backend fix in parallel; (Wave B) render aliases (WEBUI-02), build the add-provider + merge-banner settings UX (WEBUI-04), and apply the a11y floor across surfaces; (Wave C) staging deploy verification (D-06) + the D-01 re-review fixes. Consult `web/node_modules/next/dist/docs/` before writing any App Router code (project mandate — Next 16.2.2 differs from training data).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Title search (WEBUI-01) | Frontend Server (RSC) | API `/v1/search` | `page.tsx` is an `async` server component that fetches on the server via internal `API_URL`; no client fetch needed. [VERIFIED: web/app/page.tsx] |
| Disc detail render (WEBUI-02) | Frontend Server (RSC) | API `/v1/disc/{fp}` | `disc/[fingerprint]/page.tsx` is server-rendered incl. metadata; aliases already in the response payload. [VERIFIED] |
| Submit form (WEBUI-03) | Browser (client component) | API `POST /v1/disc` (Bearer) | Reads a local fingerprint JSON file + localStorage JWT — inherently client-side. [VERIFIED: SubmitForm.tsx] |
| Auth session / token (WEBUI-04) | Browser (localStorage JWT) | API `/v1/auth/*` | JWT in `localStorage` via `useAuth`; login is a full-page redirect round-trip through the API. [VERIFIED: web/lib/auth.ts] |
| Provider add/remove (WEBUI-04) | Browser (client component) | API `/v1/auth/{providers,link,unlink}` | Settings is a `"use client"` page gated on `useAuth`. [VERIFIED] |
| Merge-offer redirect (D-04) | API (FastAPI) | Browser (settings banner) | The dead-end 409 lives server-side in `finalize_auth`; fix is a backend redirect, banner is client-side. [VERIFIED: auth/routes.py] |
| Design tokens / dark mode (D-02) | CDN/Static (build-time CSS) | — | Tailwind v4 `@theme` compiles to static CSS custom properties at build; zero runtime. [CITED: tailwindcss.com/docs] |
| Production hosting (D-06) | CDN/Static + Frontend Server | Reverse proxy (redshirt) | Next standalone server behind redshirt on :3100; API base URL split server(`API_URL`)/client(`NEXT_PUBLIC_API_URL`). [VERIFIED: docker-compose.prod.yml] |

## Existing vs Missing — Gap Map (the load-bearing section)

> Grounded per success criterion. "EXISTS" = verified working in code; "GAP" = verified missing/incomplete.

### SC-1 Search (WEBUI-01)
- EXISTS: `SearchForm` (client, Suspense-wrapped) pushes `?q=&year=`; `page.tsx` server-fetches `searchReleases()`; renders `DiscCard` grid, result count, pagination, zero-results ("No releases found."), and no-query empty state. [VERIFIED: web/app/page.tsx, web/components/SearchForm.tsx]
- GAP (polish): search input is not the focal anchor per UI-SPEC (currently a compact inline row, not centered/widest); no `:focus-visible`; empty-state hint uses `text-neutral-400` (UI-SPEC flags this as borderline contrast — verify or darken to `neutral-500`).
- GAP (D-06): live staging deploy verification.

### SC-2 Disc detail (WEBUI-02)
- EXISTS: titles table (`DiscStructure`) with main-feature "Main" badge, per-title duration, audio/subtitle track summaries, and expandable chapters (`ChapterList`); status badge; primary fingerprint block; TMDB/IMDb links; SEO metadata; sibling-disc set row; edit history; dispute resolver. [VERIFIED: web/app/disc/[fingerprint]/page.tsx, web/components/DiscStructure.tsx]
- **GAP (requirement-blocking): fingerprint aliases are NOT rendered.** `getDisc()` returns `fingerprint_aliases: FingerprintAlias[]` and the backend populates it (primary-first + `identity_aliases`), but the page only prints `disc.fingerprint` once and never iterates `disc.fingerprint_aliases`. `grep` for "alias" across `web/app`+`web/components` returns zero matches. No test asserts alias rendering. This is the primary WEBUI-02 deliverable. [VERIFIED: grep web/, api/app/routes/disc.py `_disc_to_response`]
- GAP (behavioral): unverified discs return `titles: []` (D-09 redaction), so the detail page shows "No title structure available." — acceptable but should be an explicit "withheld until verified" message per production polish, not a generic empty.

### SC-3 Submit (WEBUI-03)
- EXISTS: file-upload of `ovid fingerprint --json`, parse-error surface (`data-testid="parse-error"`), preview card, release + disc metadata fields, multi-disc-set toggle + `SetSearchInput` + create-new-set, per-title `ChapterEditor`, submit + success/redirect. [VERIFIED: web/components/SubmitForm.tsx]
- GAP (polish/a11y): file input, selects, toggle, and buttons lack `:focus-visible`; no `aria-live` on `submit-error`/`parse-error`; the set-toggle is a custom peer-checkbox (verify keyboard operability against D-03).
- GAP (D-01 UX parity): set/chapter sub-UI must be re-reviewed against the token layer + a11y floor (see Re-review section).

### SC-4 Settings / linked providers (WEBUI-04)
- EXISTS: `settings/page.tsx` (client, auth-gated, redirects unauthenticated) renders profile + `ProviderList`; unlink calls `DELETE /v1/auth/unlink/{provider}`; last-provider button is disabled (`singleProvider`) and API returns `400 cannot_unlink_last`. [VERIFIED: web/app/settings/page.tsx, web/components/ProviderList.tsx, api/app/auth/routes.py]
- **GAP (requirement): no "add / Link a provider" UI.** `grep` finds no link-flow UI; only `getProviders`+`unlinkProvider` are wired. Backend `POST /v1/auth/link/{provider}` exists but is unused (and has an integration wrinkle — see Open Questions). UI-SPEC mandates a "Link a provider" primary CTA. [VERIFIED: grep web/]
- **GAP (D-05): no email-conflict merge banner.** `grep` for `email_conflict`/`pending_link` in `web/` returns nothing. The `auth/callback/page.tsx` only handles `?token=`; it ignores error params. Requires the D-04 backend redirect first, then banner UX. [VERIFIED]
- GAP (D-04 backend): `finalize_auth` merge-offer returns raw 409 JSON (dead-ends on the API host). Must redirect to `web_redirect_uri` with `error=email_conflict&pending_link_id=<id>`, enumeration-safe. [VERIFIED: api/app/auth/routes.py:177-188]
- NOTE: `NavBar` login offers **GitHub only** (hardcoded `github/login`) though four providers are supported — worth surfacing a provider picker for production login, but strictly this is login UX (AUTH-01..04 already "complete"), adjacent to WEBUI-04's add/remove scope.

## Verified API Contracts (route → schema → client)

> Every row cross-checked in `api/app/routes/*` and `web/lib/api.ts`. Shapes match unless noted.

| UI action | Endpoint | Request | Response (key fields) | Notes |
|-----------|----------|---------|-----------------------|-------|
| Search | `GET /v1/search?q&type&year&page` | query params; empty `q`→400 | `SearchResponse{ results[], page, total_pages, total_results }` (PAGE_SIZE=20) | [VERIFIED: disc.py:1232] |
| Disc detail | `GET /v1/disc/{fingerprint}` | path | `DiscLookupResponse{ fingerprint, status, titles[], fingerprint_aliases[], disc_set, ... }`; 404 → `notFound()` | Aliases primary-first; `titles=[]` when `unverified` (D-09). [VERIFIED: disc.py:732, `_disc_to_response`] |
| Edit history | `GET /v1/disc/{fingerprint}/edits` | path | `DiscEditsListResponse{ edits[] }` | Best-effort (`.catch(()=>null)`). [VERIFIED] |
| Submit | `POST /v1/disc` (Bearer) | `DiscSubmitRequest` | 201 `DiscSubmitResponse`; 409 same-user/identity; 429 cooldown; 403 anti-Sybil; 400 invalid structure | Stacked `AUTH_WRITE_LIMIT`. [VERIFIED: disc.py:908] |
| Set search | `GET /v1/set?q&page` | query | `DiscSetSearchResponse{ results[] }`; each result exposes `discs[]` | Field is `discs` (search) vs `siblings` (nested on disc). [VERIFIED: set.py:161] |
| Create set | `POST /v1/set` (Bearer) | `DiscSetCreate{ release_id, edition_name?, total_discs }` | 201 `DiscSetResponse`; 404 release; 422 bad id | **Only `_dynamic_limit` — missing `AUTH_WRITE_LIMIT` (finding R-2).** [VERIFIED: set.py:68] |
| Me | `GET /v1/auth/me` (Bearer) | — | `UserResponse{ id, username, email, role, email_verified, ... }` | Drives `useAuth`. [VERIFIED: auth/routes.py:308] |
| List providers | `GET /v1/auth/providers` (Bearer) | — | `{ providers: string[] }` | [VERIFIED: auth/routes.py:859] |
| Link provider | `POST /v1/auth/link/{provider}` (Bearer) | — | 302 → `/v1/auth/{provider}/login`; sets `link_to_user_id` session | **Unused by UI; browser-flow wrinkle — see Open Questions.** [VERIFIED: auth/routes.py:864] |
| Unlink provider | `DELETE /v1/auth/unlink/{provider}` (Bearer) | — | `{ status:"unlinked", provider }`; 404 not-linked; **400 `cannot_unlink_last`** | [VERIFIED: auth/routes.py:880] |
| Login start | `GET /v1/auth/{provider}/login?web_redirect_uri&pending_link_id` | query | 302 to provider | `web_redirect_uri` allowlisted against `CORS_ORIGINS` (fails closed). [VERIFIED: auth/routes.py:83] |
| Merge offer | (inside `finalize_auth`) | — | **currently** raw 409 `{error:"email_conflict", pending_link_id}` | **D-04: change to redirect.** ME-02: no `existing_user_id`. [VERIFIED: auth/routes.py:177] |

## Standard Stack

### Core (already installed — no additions per D-02)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| next | 16.2.2 | App Router framework, RSC, standalone output | Project-locked; `output: "standalone"` already set. [VERIFIED: web/package.json + node_modules] |
| react / react-dom | 19.2.4 | UI runtime | Project-locked. [VERIFIED] |
| tailwindcss | ^4 (v4) | Utility CSS + `@theme` tokens (D-02) | Already in use with `@import "tailwindcss"`. [VERIFIED: globals.css, package.json] |
| @tailwindcss/postcss | ^4 | PostCSS plugin for v4 | [VERIFIED: postcss.config.mjs, package.json] |
| typescript | ^5 (strict) | Types | `strict:true`; `@/*` alias. [VERIFIED] |

### Supporting (test/build — already installed)
| Library | Version | Purpose |
|---------|---------|---------|
| vitest | ^4.1.2 | Test runner (`vitest run`) [VERIFIED] |
| @testing-library/react | ^16.3.2 | Component tests [VERIFIED] |
| @testing-library/jest-dom | ^6.9.1 | DOM matchers [VERIFIED] |
| @testing-library/user-event | ^14.6.1 | Interaction sim (keyboard for D-03 a11y tests) [VERIFIED] |
| @vitejs/plugin-react | ^6.0.1 | JSX in Vitest [VERIFIED] |
| jsdom | ^29.0.1 | DOM env [VERIFIED] |
| eslint / eslint-config-next | ^9 / 16.2.2 | Lint (flat config) [VERIFIED] |

**Installation:** none. D-02 forbids new runtime deps. Shared primitives (Button, Input, Field) are hand-authored `.tsx` in `web/components/`. Icons stay Unicode/inline-SVG (no icon package).

## Package Legitimacy Audit

**No external packages are added this phase (D-02: "no new runtime deps").** The gate is therefore N/A for new installs. Existing dependencies are all first-party, high-reputation, registry-verified packages already resolved in `web/node_modules` (`next@16.2.2`, `react@19.2.4`, `tailwindcss@4`, `vitest@4.1.2`). If planning nonetheless proposes any new package, it must be blocked behind a `checkpoint:human-verify` and run through `gsd-tools query package-legitimacy check --ecosystem npm <pkg>` first.

- **Packages removed due to [SLOP] verdict:** none
- **Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram (data flow)

```
Browser ──(full-page GET)──────────────► Next standalone server (:3000/3100)
   │                                          │  RSC render
   │  localStorage JWT                        ├─ page.tsx (search)  ──► API_URL /v1/search ──► Postgres
   │                                          └─ disc/[fp]/page.tsx ──► API_URL /v1/disc/{fp} + /edits
   │
   ├─(client fetch, Bearer JWT)──► NEXT_PUBLIC_API_URL ─► FastAPI ─► /v1/disc (submit)
   │                                                              ─► /v1/auth/{me,providers,unlink,link}
   │                                                              ─► /v1/set (search/create)
   │
   └─(login: full-page redirect)─► API /v1/auth/{provider}/login ─► provider ─► /callback
                                     └─ finalize_auth: 302 back to web_redirect_uri?token=...  (success)
                                        └─ D-04 (to build): 302 ...?error=email_conflict&pending_link_id=...
```
Two base URLs by design: server components use internal `API_URL` (`http://api:8000`); browser code uses `NEXT_PUBLIC_API_URL` (`https://api.oviddb.org`), baked at build time. [VERIFIED: web/lib/api.ts `getBaseUrl`, docker-compose.prod.yml]

### Project structure (existing — extend, don't restructure)
```
web/
├── app/            # App Router pages (server unless "use client")
│   ├── page.tsx                    # search (server)
│   ├── disc/[fingerprint]/page.tsx # detail (server) ← add alias section
│   ├── submit/page.tsx             # (client, auth-gated)
│   ├── settings/page.tsx           # (client) ← add link-provider + merge banner
│   ├── auth/callback/page.tsx      # (client) ← handle error params (D-05)
│   ├── layout.tsx  globals.css     # ← token layer + Geist body fix (D-02)
├── components/     # bespoke + re-integrated (SiblingDiscs/SetSearchInput/Chapter*)
│                   # ← add shared primitives Button/Input/Field
├── lib/  api.ts auth.ts            # typed client + useAuth
└── src/__tests__/  *.test.tsx      # Vitest (add alias / link / banner / a11y tests)
```

### Pattern 1: Tailwind v4 `@theme` token layer (D-02)
**What:** Replace the ad-hoc `:root` + `@media (prefers-color-scheme: dark)` block with a `@theme` block that declares color/spacing/radius tokens; keep dark behavior.
**When:** Foundation wave, before primitives.
```css
/* web/app/globals.css  — Source: tailwindcss.com/docs adding-custom-styles + dark-mode */
@import "tailwindcss";

@theme {
  --color-accent: #2563eb;          /* blue-600 primary action */
  --color-accent-ring: #3b82f6;     /* blue-500 focus ring */
  --color-accent-hover: #1d4ed8;    /* blue-700 */
  --radius-control: 4px;            /* rounded default */
  --radius-card: 8px;               /* rounded-lg cards */
  --font-sans: var(--font-geist-sans);
  --font-mono: var(--font-geist-mono);
}
/* Existing `dark:` utilities work under Tailwind's DEFAULT media strategy.
   Only add an explicit variant if a manual toggle is required: */
/* @custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *)); */

/* REMOVE the Next-starter drift so Geist is the single sans source (UI-SPEC): */
/* body { font-family: Arial, Helvetica, sans-serif; }  ← delete this line */
```
[CITED: https://tailwindcss.com/docs/adding-custom-styles ; https://tailwindcss.com/docs/dark-mode] — the `@theme { --color-* }` and `@custom-variant dark (...)` syntaxes are confirmed current for v4.

**⚠ Dark-mode caution:** the app currently relies on Tailwind's **default `prefers-color-scheme` media strategy** — every `dark:` class in the codebase already works that way. If the plan adds `@custom-variant dark (...)` with a class/data-attribute selector, it *overrides* the media strategy and dark mode stops following the OS unless a toggle sets the attribute. Unless a manual theme toggle is a goal (it is not in scope), prefer keeping the media strategy and only add `@theme` tokens. [CITED: tailwindcss.com/docs/dark-mode]

### Pattern 2: Fingerprint-alias rendering (WEBUI-02)
**What:** Iterate `disc.fingerprint_aliases` in the detail page; primary is already first with `is_primary:true`.
```tsx
// disc/[fingerprint]/page.tsx (server) — data already present in `disc`
{disc.fingerprint_aliases && disc.fingerprint_aliases.length > 1 ? (
  <section className="mb-6">
    <h2 className="text-xl font-semibold mb-3">Fingerprint aliases</h2>
    <ul className="space-y-1">
      {disc.fingerprint_aliases.map((a) => (
        <li key={a.fingerprint} className="flex items-center gap-2 text-sm">
          <code className="font-mono break-all">{a.fingerprint}</code>
          <span className="text-neutral-500">{a.method}</span>
          {a.is_primary && <span className="rounded bg-blue-100 px-1.5 py-1 text-blue-800 dark:bg-blue-900 dark:text-blue-200">primary</span>}
        </li>
      ))}
    </ul>
  </section>
) : (
  <p className="text-sm text-neutral-500">No additional fingerprint aliases recorded.</p>
)}
```
Empty-state copy is fixed by UI-SPEC. [VERIFIED shape: api/app/routes/disc.py `fingerprint_aliases_resp`]

### Pattern 3: `:focus-visible` ring on every interactive element (D-03)
```
focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2
dark:focus-visible:ring-offset-neutral-950
```
Current inputs use `focus:` (mouse-noisy); buttons have NO ring. Bake the ring into the shared `Button`/`Input` primitives so every consumer inherits it. [VERIFIED: grep "focus-visible" web/ → 0 matches]

### Pattern 4: Reading redirect error params in a client page (D-05)
`useSearchParams()` in App Router **must** be inside a `<Suspense>` boundary (already the established pattern in `SearchForm` and `auth/callback`). The settings page reads `?error=email_conflict&pending_link_id=...` and renders the enumeration-safe banner + a `<a href={/v1/auth/${provider}/login?pending_link_id=...}>` re-auth link. [VERIFIED pattern: web/components/SearchForm.tsx Suspense usage]

### Anti-Patterns to avoid
- **Do NOT** reintroduce a component library or Radix (D-02) — hand-author primitives.
- **Do NOT** switch dark mode to a class strategy without a toggle (breaks OS-following dark).
- **Do NOT** put the JWT anywhere the merge redirect could leak it — the D-04 redirect carries only `error`+`pending_link_id`, never a token, never `existing_user_id` (ME-02).
- **Do NOT** hardcode API URLs — use the `getBaseUrl()` server/client split already in `api.ts`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Design tokens / theming | A JS theme object or CSS-in-JS | Tailwind v4 `@theme` (D-02) | Zero-runtime, compiles to CSS vars; already the stack. [CITED: tailwindcss.com] |
| Dark mode | A React theme context + toggle plumbing | Tailwind default `dark:` (media) already in use | No toggle is in scope; media strategy is free. |
| Data fetching in RSC | `useEffect`+fetch on the client | `async` server components (`page.tsx` already does this) | SSR, no client waterfall, internal API URL. |
| Search-param reading | Manual `window.location` parsing | `useSearchParams()` + Suspense | App Router idiom already used repo-wide. |
| Focus rings | Custom JS focus tracking | CSS `:focus-visible` | Browser-native keyboard/mouse distinction. |
| Merge state machine | Full pending-merge orchestration in the UI | D-05 "middle" banner + re-auth link only | Full flow explicitly deferred to v1.0. |

## Re-review Findings (D-01) — targeted, per the four-point checklist

### 1. Security-model seams
- **R-1 (MEDIUM — anti-echo redaction leak via set view):** `_build_disc_set_nested` (`api/app/routes/disc.py:503`) iterates every sibling's `titles` to expose `main_title` (display_name), `duration_secs`, and `track_count` **without checking `sibling.status`**. A direct `GET /v1/disc/{sibling}` on an *unverified* sibling redacts `titles` (D-09), but the set view on a *verified* disc leaks that sibling's derived structural data. Same pattern in `set.py::_build_sibling_summary`. This is exactly the "doesn't duplicate/bypass main's D-09 anti-echo redaction" seam D-01 asks to verify. **Recommend:** withhold `main_title`/`duration_secs`/`track_count` for siblings whose `status == "unverified"` (or gate on the same branch `_disc_to_response` uses). Escalation candidate per D-01. [VERIFIED: disc.py:508-527, set.py:45-62]
- **R-2 (MEDIUM — write-ceiling inconsistency):** `POST /v1/set` (`set.py:68`) carries only `@limiter.limit(_dynamic_limit)`, **not** the stacked `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` that `submit_disc`/`register_disc` carry (INFRA-04/D-07). Set creation is an authenticated write that escapes the per-account write throttle. **Recommend:** add the `AUTH_WRITE_LIMIT` ceiling to `create_set`. [VERIFIED: grep set.py decorators]
- **Attribution:** `create_set` records no `DiscEdit` audit row (unlike submit). Low severity; note for parity.
- **Chapters seam — OK:** chapters are written **only** through `submit_disc` (no separate mutation endpoint), so they inherit submission attribution + anti-Sybil gate + `AUTH_WRITE_LIMIT`, and are validated (≤999, unique `chapter_index`). No bypass. [VERIFIED: disc.py:1018-1076]

### 2. Migrations
- **OK:** `900000000008` (`down_revision='900000000007'`) → `900000000009` (`down_revision='900000000008'`) chain cleanly onto Phase 6's `PendingAccountLink` migration head. Ordering correct. [VERIFIED]
- `008` adds `uq_disc_set_disc_number` on `(disc_set_id, disc_number)` — NULL `disc_set_id` rows excluded by SQL-standard NULL-distinct semantics (holds on both Postgres and the SQLite test path).
- `009` creates `disc_chapters` with a UUID PK and **no server_default**; the `DiscChapter` model supplies `default=uuid.uuid4` (Python-side), consistent with every other table in the schema. Not a defect. [VERIFIED: api/app/models.py:316-321]
- Idempotency: both use standard un-guarded Alembic `create_*` (would error if re-run), consistent with all other repo migrations — no special idempotency expected or required.

### 3. Dead/duplicate code
- **R-3 (LOW):** `link_provider` (`auth/routes.py:864-878`) contains leftover merge-resolution cruft — a `pass`-only Mastodon/IndieAuth branch and a rambling comment ("...wait, the plan doesn't specify...if the test tests GitHub, we just redirect"). Clean it up; decide Mastodon/IndieAuth link handling explicitly (they need a domain/url, unsupported by this bare POST). [VERIFIED: auth/routes.py:872-877]
- `_error_response` is duplicated between `disc.py` and `set.py` — acceptable (thin, route-local), note only.

### 4. UX parity
- `SiblingDiscs`, `SetSearchInput`, `ChapterEditor`, `ChapterList` are reasonably well-built (SetSearchInput even has `role="combobox"`/keyboard nav/`aria-selected`). But they predate the D-02 token layer and D-03 floor: they use raw `text-xs` (12px — UI-SPEC bans a 12px tier, folds to `text-sm`), raw `focus:`/no focus-visible, `py-1`/`py-0.5` sub-4px vestiges (`ChapterList` uses `px-2 py-1`), and bespoke `inputClass` strings that should migrate to the shared `Input` primitive. Bring them to parity in the same pass as the rest.

## Common Pitfalls

### Pitfall 1: Next.js 16.2.2 ≠ training data
**What goes wrong:** App Router APIs (async `params`/`searchParams`, `useSearchParams` Suspense rule, metadata, `next/font`, standalone output) differ from memory.
**Avoid:** Per `web/AGENTS.md`, read `web/node_modules/next/dist/docs/` before writing App Router code. The existing code already does the right things (`await params`, Suspense around `useSearchParams`) — mirror those patterns, don't invent.
**Warning signs:** hydration errors, "useSearchParams must be wrapped in a suspense boundary" build errors.

### Pitfall 2: `web_redirect_uri` must be in `CORS_ORIGINS` or login 400s
**What:** `_validate_web_redirect_uri` allowlists the redirect host against `CORS_ORIGINS` and **fails closed** (empty/`*` rejects everything). For a **staging** subdomain (D-06), the staging callback origin MUST be added to `CORS_ORIGINS`, else every login (and the D-04 merge redirect) 400s.
**Avoid:** include the staging web origin in `CORS_ORIGINS` when planning the staging env. [VERIFIED: auth/routes.py:83-112]

### Pitfall 3: `NEXT_PUBLIC_API_URL` is baked at BUILD time
**What:** The Dockerfile takes it as a build `ARG` and bakes it into client bundles; it cannot be changed by runtime env. A staging build needs its own build arg (staging API URL). [VERIFIED: web/Dockerfile:12-15, docker-compose.prod.yml:83-86]
**Avoid:** treat the staging web image as a distinct build; don't expect to re-point it via runtime env.

### Pitfall 4: Unverified disc → empty detail view
**What:** `titles:[]` for `unverified` discs (D-09 redaction) makes the detail page render "No title structure available." A production-polish gap: users will think the page is broken.
**Avoid:** render an explicit "Structure withheld until a second contributor verifies this disc." message when `status==="unverified"`. `fingerprint_aliases` and `release` ARE present for all statuses — still render them. [VERIFIED: disc.py:560-583]

### Pitfall 5: Set-view structural leak (see R-1)
Covered above — planning the alias/set rendering must not assume sibling structural fields are always safe to show.

### Pitfall 6: The "add provider" browser flow is not a simple fetch
**What:** `POST /v1/auth/link/{provider}` needs the Bearer JWT (from `get_current_user`) AND sets `link_to_user_id` in the **session cookie** that must survive the provider OAuth round-trip. A client `fetch` with a Bearer header won't carry the browser through a 302 to the provider and back with cookies intact the way a top-level navigation does. See Open Questions for the design decision. [VERIFIED: auth/routes.py:864-878]

## Code Examples

(See Patterns 1–4 above for the token layer, alias rendering, focus-visible, and search-param banner — those are the load-bearing, verified snippets.)

### Enumeration-safe merge banner (D-05, client)
```tsx
// settings/page.tsx (inside a Suspense'd client component)
const error = searchParams.get("error");
const pendingLinkId = searchParams.get("pending_link_id");
{error === "email_conflict" && (
  <div role="alert" aria-live="polite" className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
    This email is already linked to another OVID account via {/* already-linked providers on THIS account only */}
    {providers.join(", ")}. To connect this login, re-authenticate with that provider.
    {" "}
    <a href={`${API_URL}/v1/auth/${providers[0]}/login?pending_link_id=${encodeURIComponent(pendingLinkId ?? "")}&web_redirect_uri=${encodeURIComponent(callbackUrl)}`}>Re-authenticate</a>
  </div>
)}
```
Copy is fixed by UI-SPEC; MUST name only providers on the *current* account context, never the matched account/email. [CONSTRAINT: 07-UI-SPEC.md Copywriting]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `tailwind.config.js` theme object | Tailwind v4 CSS-first `@theme { --color-* }` in `globals.css` | Tailwind v4 (2024/25) | D-02's token layer is CSS, not JS config. [CITED: tailwindcss.com] |
| `darkMode: 'media'|'class'` in config | `@custom-variant dark (...)` in CSS (or rely on default media) | Tailwind v4 | Default media strategy already powers the app's `dark:` classes. |
| Next `pages/` + `getServerSideProps` | App Router RSC (`async` server components) | Next 13+ (this repo is 16.2.2) | Already adopted; keep. |
| Next-starter `body{font-family:Arial}` | Geist via `next/font` + `font-sans` | — | The starter line is drift to delete (UI-SPEC). [VERIFIED: globals.css:25] |

**Deprecated/outdated in this context:** shadcn/ui and Radix (explicitly deferred, D-02); any `tailwind.config.*` file (v4 is CSS-first — none present in `web/`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Keeping Tailwind's default `prefers-color-scheme` media dark strategy (not adding a class/data-attribute `@custom-variant dark`) satisfies D-02's "dark-mode via @custom-variant dark" intent, since no manual toggle is in scope | Pattern 1 | If a manual theme toggle is actually wanted, the token layer must add the variant + toggle plumbing — larger scope. **Confirm with user in discuss/plan.** |
| A2 | The D-04 merge redirect should target the same `web_redirect_uri`/callback the success path uses, and the settings page (not the callback page) hosts the D-05 banner | SC-4, Pattern 4 | If the redirect target differs, the banner-hosting page changes. Planner must fix the target. |
| A3 | Adding `AUTH_WRITE_LIMIT` to `POST /v1/set` (R-2) is desired parity, not intentional omission | Re-review R-2 | If set-creation was intentionally uncapped, the fix is unwanted. Low risk — inconsistency looks accidental. |
| A4 | Staging deploy (D-06) reuses the `web` service build with a staging `NEXT_PUBLIC_API_URL` build arg + staging origin added to `CORS_ORIGINS` | D-06, Pitfall 2/3 | If staging infra differs (separate compose file), env wiring differs. Exact staging URL is Claude's discretion per CONTEXT. |

## Open Questions (RESOLVED)

1. **How does the browser "Link a provider" flow authenticate (WEBUI-04 add path)?**
   - What we know: `POST /v1/auth/link/{provider}` needs Bearer auth *and* a session cookie that survives the OAuth round-trip; the UI stores the JWT in `localStorage`, not a cookie.
   - What's unclear: a top-level navigation to start OAuth won't carry the Bearer header; a `fetch` won't carry the browser through the provider redirect. The per-provider `/login` endpoints accept `web_redirect_uri`+`pending_link_id` as query params but **not** `link_to_user_id`.
   - Recommendation: decide during planning — options: (a) add a `link_to_user_id`-via-signed-token query param to `/login` so a plain navigation can start an authenticated link; (b) have the client `fetch POST /link/{provider}` with `credentials:"include"` to set the session cookie, then top-level-navigate; (c) minimal MVP: expose provider **login** buttons in settings that, on an already-authenticated browser, link via the existing session. This is the main design decision for the add-provider deliverable. Escalate to discuss if ambiguous.
   - **→ RESOLVED:** Deferred to the **blocking `checkpoint:decision` in 07-07 (Task 1)** — the developer selects the mechanism at plan-execution time (default option-b, frontend-only credentialed-fetch-then-navigate; option-a backend signed-token as the robust alternative). Option-c is documented as rejected (wrong "add provider" semantics). The choice is recorded in 07-07-SUMMARY and consumed by 07-07 Tasks 2-3. Not delegated to Claude's discretion; it is an explicit gated decision.

2. **Staging subdomain + DNS/TLS (D-06):** exact host is Claude's discretion, but it must (a) be added to `CORS_ORIGINS`, (b) get its own `NEXT_PUBLIC_API_URL` build, (c) resolve behind redshirt. Confirm the staging API host (`api.staging.oviddb.org`?) during planning.
   - **→ RESOLVED:** Handled in **07-08** (Claude's discretion per CONTEXT). 07-08 Task 1 documents/wires the staging web origin into `CORS_ORIGINS` (fail-closed otherwise, Pitfall 2), the distinct staging `NEXT_PUBLIC_API_URL` build arg (baked at build, Pitfall 3), and the redshirt/DNS/TLS host-infra prerequisites (`user_setup`); the exact hostname is chosen there (e.g. `staging.oviddb.org` / `api.staging.oviddb.org`) and confirmed at the 07-08 Task 3 human-verify gate.

3. **NavBar login = GitHub only:** should production login expose all configured providers (Google/Apple/Mastodon), or is single-provider acceptable for staging? Adjacent to WEBUI-04; confirm scope.
   - **→ RESOLVED (scope decision):** GitHub-only NavBar login is acceptable for staging; **NavBar provider expansion is out of scope for Phase 7.** WEBUI-04's add-provider path (settings) initiates OAuth independently of NavBar login, so this does not block the requirement — a settings "Link a provider" CTA (07-07) covers Google/Apple/Mastodon linking regardless of the NavBar. A production multi-provider login picker is deferred (revisit in a launch/login-UX pass; login providers AUTH-01..04 are already "complete").

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | web build/test | ✓ (Docker `node:24-alpine`; local for Vitest) | 24 (image) | — |
| Next.js (installed) | all UI work | ✓ | 16.2.2 | — |
| Next.js installed docs | App Router guidance (AGENTS.md mandate) | ✓ | `web/node_modules/next/dist/docs/` | — |
| Vitest + Testing Library | validation | ✓ | 4.1.2 / RTL 16.3.2 | — |
| Docker + Compose v2 | staging deploy (D-06) | assumed on host | — | verify on target |
| redshirt reverse proxy | oviddb.org/staging TLS+routing | external (host infra) | — | none — required for D-06 staging verify |
| `.env.production.example` | operator env reference | ✗ (absent) | — | `.env.example` + docker-compose.prod.yml env block |

**Missing with no fallback:** redshirt proxy config for the staging host is external infra — the plan's D-06 verification depends on it existing/being configured.
**Missing with fallback:** no `.env.production.example` — derive staging env from `docker-compose.prod.yml` + `.env.example`.

## Validation Architecture

> `workflow.nyquist_validation` is enabled — this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest ^4.1.2 + @testing-library/react ^16.3.2 + jest-dom + user-event [VERIFIED] |
| Config file | `web/vitest.config.ts` (jsdom env, `@/` alias, `src/test-setup.ts`) [VERIFIED] |
| Quick run command | `cd web && npx vitest run <file>` |
| Full suite command | `cd web && npm test` (`vitest run`) — currently 58 passing |
| Existing tests | `web/src/__tests__/{disc-detail,pages,submit}.test.tsx`, `auth.test.ts` (1039 lines total) |
| API-side pattern | pytest against in-memory SQLite via TestClient (D-04/R-1/R-2 backend changes) |

### Phase Requirements → Test Map
| Req/Item | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| WEBUI-01 | Search renders results / zero / no-query / pagination | component | `npx vitest run src/__tests__/pages.test.tsx` | ✅ (extend for a11y) |
| WEBUI-02 | **Aliases render** (primary badge + method); empty-state copy | component | `npx vitest run src/__tests__/disc-detail.test.tsx` | ✅ exists; ❌ **no alias assertion yet — Wave 0** |
| WEBUI-02 | Unverified disc shows "withheld" message not blank | component | same | ❌ Wave 0 |
| WEBUI-03 | Submit happy-path + parse-error + auth-gate | component | `npx vitest run src/__tests__/submit.test.tsx` | ✅ (extend a11y) |
| WEBUI-04 | Unlink + `cannot_unlink_last` 400 surfaced | component | new `settings.test.tsx` | ❌ Wave 0 |
| WEBUI-04 | **Add/link provider** CTA present + initiates flow | component | new `settings.test.tsx` | ❌ Wave 0 |
| D-05 | `?error=email_conflict` renders enumeration-safe banner + re-auth link; names only current-account providers | component | new `settings.test.tsx` | ❌ Wave 0 |
| D-03 | `:focus-visible` present on primitives; keyboard (Enter/Space/Escape) operable; `aria-live` on errors | component (user-event) | primitive tests + per-surface | ❌ Wave 0 |
| D-04 | merge-offer returns a 302 redirect (not raw 409) with `error`+`pending_link_id`, no `existing_user_id` | API (pytest) | `api` test suite | ❌ Wave 0 (extend auth tests) |
| R-1 | set/sibling view redacts unverified sibling structural fields | API (pytest) | `api` test suite | ❌ Wave 0 |
| R-2 | `POST /v1/set` enforces `AUTH_WRITE_LIMIT` | API (pytest) | `api` test suite | ❌ Wave 0 |
| D-06 | staging container builds + serves + login round-trip over TLS | manual/smoke | deploy checklist | ❌ manual (justified — real infra) |

### Sampling Rate
- **Per task commit:** the single affected `npx vitest run <file>` (web) or the touched `pytest` module (api) — < 30s.
- **Per wave merge:** `cd web && npm test` + full `api` pytest.
- **Phase gate:** full web + api suites green before `/gsd-verify-work`; D-06 staging smoke is a manual gate.

### Wave 0 Gaps
- [ ] `web/src/__tests__/disc-detail.test.tsx` — add alias-rendering + unverified-withheld assertions (WEBUI-02)
- [ ] `web/src/__tests__/settings.test.tsx` — NEW: unlink/min-one, add-provider CTA, merge banner (WEBUI-04, D-05)
- [ ] Shared-primitive tests (Button/Input/Field) asserting `:focus-visible` classes + keyboard behavior (D-03)
- [ ] API: extend auth tests for D-04 redirect shape; add R-1 redaction + R-2 rate-limit tests
- [ ] Manual staging deploy checklist (D-06) — not automatable in CI

## Security Domain

> `security_enforcement` enabled, ASVS level 1.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control (this phase) |
|---------------|---------|-------------------------------|
| V2 Authentication | yes | Login/link/unlink via existing OAuth flows; JWT via `create_access_token`; **do not weaken** the confirm-gated merge (AUTH-08). New UI must not introduce a silent-merge path. |
| V3 Session Management | yes | JWT in `localStorage` (existing); merge routing via server session cookie. D-04 redirect must carry **no token**, only `error`+`pending_link_id`. |
| V4 Access Control | yes | Settings/submit are auth-gated client-side AND server-enforced (`get_current_user`); unlink min-one enforced server-side (`cannot_unlink_last`). R-2: restore write-ceiling on `/v1/set`. |
| V5 Input Validation | yes | Search `q`, submit payload, chapter counts validated server-side (Pydantic + explicit checks). Client parse-errors surface via `parse-error`. |
| V6 Cryptography | no (unchanged) | No crypto changes; Apple ES256/JWT untouched. |
| V7/V11 Error/Logging | yes | Enumeration-safety (ME-02): merge banner + D-04 redirect must not reveal matched account/email/`existing_user_id`. Mastodon domain errors already non-reflective. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Account-takeover via silent email merge (nOAuth) | Spoofing/Elevation | Keep confirm-gated `resolve_auth`; UI only OFFERS + links to re-auth (D-05). Never auto-merge. [VERIFIED existing: merge.py] |
| User/email enumeration via merge response | Info Disclosure | ME-02: no `existing_user_id`; banner names only current-account providers. |
| Open-redirect / JWT exfiltration on login | Tampering | `_validate_web_redirect_uri` allowlist vs `CORS_ORIGINS`, fail-closed. Staging origin must be added. [VERIFIED] |
| Anti-echo redaction bypass via set/alias views | Info Disclosure | R-1: redact unverified sibling structural fields; alias rendering does not expose withheld titles. |
| Unthrottled authenticated write (`/v1/set`) | DoS | R-2: add `AUTH_WRITE_LIMIT`. |
| XSS via disc/release/provider strings | Tampering | React auto-escapes; keep values in JSX text (no `dangerouslySetInnerHTML`). |

## Project Constraints (from CLAUDE.md + web/AGENTS.md)

- **web/AGENTS.md (hard):** Next.js 16.2.2 has breaking changes vs training data — **read `web/node_modules/next/dist/docs/` before writing any App Router code**; heed deprecation notices. Treat any Next API usage as needing verification against installed docs, not memory.
- **Tech stack locked (do not re-platform):** Next 16 + React 19 + Tailwind 4; Python 3.12 + FastAPI + Postgres + SQLAlchemy/Alembic. No new runtime deps (D-02).
- **Conventions:** `snake_case.py`; `PascalCase.tsx` components; `camelCase.ts` libs; `@/*` alias; strict TS (no implicit `any`); `data-testid` on tested controls; typed `ApiError{status,code}` mirrored in tests; API client mocked wholesale with `vi.mock`.
- **Testing:** pytest (API against in-memory SQLite via TestClient), Vitest (web). Behavior/assert-based, never snapshot; DOM queried via `data-testid`.
- **Error envelope:** consistent JSON `{request_id, error, message}`; deliberate HTTP status per business state (e.g. duplicate submission → 200 disputed, not error).
- **Compatibility guardrail:** `dvd1-*` fingerprints MUST stay resolvable — alias rendering must show all identity strings, never hide/renumber.
- **Global (user CLAUDE.md):** no waving off warnings/errors; fix defects inline (never defer); cross-platform IO-failure tests via `fs`-method monkeypatch, never `chmod`.

## Sources

### Primary (HIGH confidence)
- Repo source (ground truth), read this session: `web/app/{page,layout,disc/[fingerprint]/page,settings/page,submit/page,auth/callback/page}.tsx`, `web/components/{ProviderList,SubmitForm,SearchForm,DiscStructure,SiblingDiscs,SetSearchInput,ChapterEditor,ChapterList,NavBar}.tsx`, `web/lib/{api,auth}.ts`, `web/app/globals.css`, `web/{Dockerfile,next.config.ts,package.json}`, `api/app/routes/{disc,set}.py`, `api/app/auth/routes.py`, `api/app/models.py` (DiscChapter), `api/alembic/versions/90000000000{8,9}_*.py`, `docker-compose.prod.yml`, `.env.example`.
- Installed Next.js 16.2.2 docs: `web/node_modules/next/dist/docs/` (present; index confirms App Router).
- `web/node_modules/next/package.json` → next 16.2.2 [VERIFIED].

### Secondary (MEDIUM confidence)
- Tailwind CSS v4 docs via Context7 (`/tailwindlabs/tailwindcss.com`): `@theme { --color-*/--spacing-* }` and `@custom-variant dark (...)` syntax [CITED: tailwindcss.com/docs/adding-custom-styles, /colors, /dark-mode].

### Tertiary (LOW confidence)
- None — all claims grounded in repo or official docs.

## Metadata

**Confidence breakdown:**
- Existing/missing gap map: HIGH — verified by direct read + grep of actual files.
- API contracts: HIGH — cross-checked route→schema→client.
- Re-review findings (R-1/R-2/R-3): HIGH — verified in source.
- Tailwind v4 syntax: MEDIUM — official docs via Context7 (not executed in-repo yet).
- Add-provider browser flow (Open Q1) + dark-mode intent (A1): MEDIUM — design decisions requiring user/plan confirmation.

**Research date:** 2026-07-07
**Valid until:** 2026-08-06 (stable stack; re-verify if Next/Tailwind minor bumps land).
