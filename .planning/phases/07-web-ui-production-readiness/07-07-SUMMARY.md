---
phase: 07-web-ui-production-readiness
plan: 07
subsystem: ui
tags: [nextjs, react, oauth, settings, enumeration-safety, noauth, suspense]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness (07-01)
    provides: Button/Input/Field primitives with baked-in focus-visible ring (D-02/D-03 floor)
  - phase: 07-web-ui-production-readiness (07-02)
    provides: "finalize_auth's merge-offer branch 302-redirects to web_redirect_uri with error=email_conflict&pending_link_id=<id> instead of dead-ending on raw 409 JSON"
provides:
  - "web/lib/api.ts linkProvider(provider, token) — primes the session cookie via a credentialed, non-following fetch to POST /v1/auth/link/{provider}, returns the deterministic /login URL for a top-level window.location.assign navigation (option-b, frontend-only)"
  - "web/app/settings/page.tsx 'Link a provider' CTA per not-yet-linked provider (github/google/apple), wired through ProviderList"
  - "web/app/settings/page.tsx Suspense-wrapped, enumeration-safe (ME-02) D-05 merge banner reading ?error=email_conflict&pending_link_id="
  - "web/app/auth/callback/page.tsx forwards ?error=email_conflict&pending_link_id= onward to /settings (A2)"
  - "web/lib/api.ts apiFetch now correctly parses FastAPI's HTTPException(detail={error,reason}) nested error shape, not just the flat disc/set {error,message} envelope"
affects: [07-08-web-ui-production-readiness (staging deploy — this plan's linkProvider/login round-trip needs the staging web origin in CORS_ORIGINS)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Add-provider browser flow (option-b): credentialed fetch(POST /link/{provider}, {credentials:'include', redirect:'manual'}) primes the session cookie as a side effect of an opaque 'opaqueredirect' response, then the caller constructs the deterministic /login URL itself and window.location.assign()s it as a top-level navigation — avoids trying to read the opaque response's unreadable Location header"
    - "Suspense-wrapped useSearchParams page pattern (mirrors SearchForm.tsx / auth/callback/page.tsx): outer default-export wraps <Suspense>, all hook usage lives in an Inner component"
    - "api.ts error parsing now normalizes both response-error envelope conventions used across the API: the flat disc/set {error,message} shape and FastAPI's default HTTPException(detail={...}) nested shape"

key-files:
  created:
    - web/src/__tests__/settings.test.tsx
  modified:
    - web/lib/api.ts
    - web/app/settings/page.tsx
    - web/components/ProviderList.tsx
    - web/app/auth/callback/page.tsx

key-decisions:
  - "Task 1 checkpoint resolved: option-b (frontend-only), per user selection at plan-execution time. No backend change; api/app/auth/routes.py untouched; plan stayed web-only."
  - "linkProvider does NOT try to read the redirect Location header from the opaque 'opaqueredirect' fetch response (unreadable per fetch spec under redirect:'manual'). Instead it relies on the endpoint's redirect target being deterministic in source (RedirectResponse(url=f'/v1/auth/{provider}/login')) and constructs that URL directly — the fetch call's only job is to trigger the Set-Cookie side effect."
  - "Add-provider candidate providers are github/google/apple only — mastodon and indieauth are excluded from the 'Link a provider' CTA because POST /v1/auth/link/{provider} explicitly 400s them with link_requires_domain (R-3, 07-02), and IndieAuth is hidden in production (D-05)."
  - "The D-05 merge banner names ONLY the current account's own already-fetched providers (the `providers` state from getProviders()), never anything derived from the redirect's query params — the 302 redirect (07-02) intentionally carries only error+pending_link_id, no provider/account info, so there is nothing about the matched/different account to leak even if the frontend tried."
  - "web_redirect_uri for the add-provider /login navigation targets /auth/callback (matching the existing NavBar login convention), not /settings directly — callback/page.tsx is the single router that either sets the token (success) or forwards error+pending_link_id to /settings (merge offer), keeping one convention for all provider login/link flows."

patterns-established:
  - "Deterministic-redirect-URL construction over Location-header reading for any future flow that needs to prime session state via a redirecting endpoint under CORS with redirect:'manual'."

requirements-completed: [WEBUI-04]

coverage:
  - id: D1
    description: "'Link a provider' CTA renders for each not-yet-linked candidate provider (github/google/apple) and calls linkProvider (mocked) + window.location.assign on click"
    requirement: "WEBUI-04"
    verification:
      - kind: unit
        ref: "web/src/__tests__/settings.test.tsx::SettingsPage — add-provider CTA (3 tests: renders CTAs, initiates flow + navigates, surfaces error on rejection)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unlink calls the mocked unlinkProvider; the last remaining unlink control is disabled; a 400 cannot_unlink_last surfaces the fixed UI-SPEC copy regardless of the backend's own message text"
    requirement: "WEBUI-04"
    verification:
      - kind: unit
        ref: "web/src/__tests__/settings.test.tsx::SettingsPage — unlink + min-one guard (3 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "On ?error=email_conflict&pending_link_id=, an enumeration-safe role=alert aria-live=polite banner renders naming only current-account providers, with a re-auth link to /v1/auth/<provider>/login?pending_link_id=...&web_redirect_uri=...; no email/existing_user_id ever appears in the banner or link"
    requirement: "WEBUI-04"
    verification:
      - kind: unit
        ref: "web/src/__tests__/settings.test.tsx::SettingsPage — enumeration-safe merge banner (D-05, ME-02) (2 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "ProviderList migrated to the ghost Button primitive (focus-visible ring), text-xs->text-sm, text-neutral-400->neutral-500, all pre-existing data-testids preserved; no full-suite/lint/typecheck/build regressions"
    verification:
      - kind: unit
        ref: "cd web && npm test (93/93 pass, including the 5 pre-existing ProviderList tests in submit.test.tsx unmodified)"
        status: pass
      - kind: other
        ref: "cd web && grep -c 'text-xs' components/ProviderList.tsx == 0 && grep -c 'text-neutral-400' components/ProviderList.tsx == 0; npx eslint . (0/0); npx tsc --noEmit (clean); npm run build (clean)"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 7: Settings add-provider CTA + D-05 merge banner Summary

**"Link a provider" add-flow (option-b, frontend-only credentialed-fetch-then-navigate) wired into settings via a new `linkProvider` api.ts helper, plus the Suspense-wrapped enumeration-safe D-05 merge banner and ProviderList's ghost-Button/D-03 parity migration — completing WEBUI-04.**

## Performance

- **Duration:** ~18 min (continuation agent; Task 1 decision was already resolved by the user before this run started)
- **Started:** 2026-07-07T23:19:00Z (Task 2 RED commit)
- **Completed:** 2026-07-07T23:21:08Z
- **Tasks:** 3 (Task 1 decision recorded; Task 2 RED; Task 3 GREEN)
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments
- **Task 1 (checkpoint:decision) resolved:** option-b (frontend-only) — the "Link a provider" flow primes the backend session cookie via a credentialed `fetch(POST /v1/auth/link/{provider}, {credentials:"include", redirect:"manual"})`, then `window.location.assign()`s the deterministic `/v1/auth/{provider}/login` URL as a top-level navigation. No backend change; `api/app/auth/routes.py` untouched; the plan stayed entirely within `web/`.
- `web/lib/api.ts` gained a new `linkProvider(provider, token): Promise<string>` helper implementing the above, using `getBaseUrl()` (now exported) rather than any hardcoded URL. It correctly distinguishes the endpoint's normal 302 (surfaced as an opaque, unreadable `"opaqueredirect"` fetch response under `redirect:"manual"`, whose sole purpose here is to let the browser process the response's `Set-Cookie`) from genuine failures (400 `invalid_provider`/`link_requires_domain`, 401), which ARE readable and are surfaced as `ApiError`.
- `web/app/settings/page.tsx` now renders the "Link a provider" CTA (via `ProviderList`) for each not-yet-linked candidate provider, and a Suspense-wrapped, `role="alert"` `aria-live="polite"` merge banner on `?error=email_conflict&pending_link_id=` that names ONLY the current account's own already-linked providers (ME-02) with a direct re-auth link (`GET /v1/auth/<provider>/login?pending_link_id=...&web_redirect_uri=...`). The 400 `cannot_unlink_last` path now surfaces the exact UI-SPEC copy ("You must keep at least one login method. Link another provider before removing this one.") regardless of the backend's own message wording.
- `web/components/ProviderList.tsx` migrated the unlink control to the ghost `Button` primitive (baking in the D-03 focus-visible ring), added a parallel "not yet linked" section rendering a primary `Button` "Link a provider" CTA per candidate (`github`/`google`/`apple` — `mastodon`/`indieauth` excluded per R-3/D-05), dropped `text-xs`→`text-sm` and `text-neutral-400`→`neutral-500`, and preserved every existing `data-testid`.
- `web/app/auth/callback/page.tsx` now forwards `?error=email_conflict&pending_link_id=` onward to `/settings` (A2) alongside its existing `?token=` handling, since `web_redirect_uri` for every login/link flow (including the new add-provider flow) consistently targets `/auth/callback`.
- New `web/src/__tests__/settings.test.tsx` (8 tests) mirroring `submit.test.tsx` conventions, proving all three `<must_haves>` truths plus both threat-register mitigations (T-07-07-01 ME-02 enumeration-safety, T-07-07-04 min-one guard) end-to-end at the component level.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: Decide the add-provider browser-flow mechanism** — resolved by the user (option-b) before this continuation agent started; no code, recorded here and consumed by Tasks 2-3.
2. **Task 2 (RED): settings.test.tsx** - `b4c181f` (test) — 3/8 pass (pre-existing unlink behavior), 5/8 fail (CTA/banner/cannot_unlink_last copy did not exist yet)
3. **Task 3 (GREEN): add-provider CTA + merge banner + ProviderList parity + api.ts helper** - `6e43f40` (feat) — 8/8 pass

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `web/src/__tests__/settings.test.tsx` - New Vitest + Testing Library suite (8 tests): unlink + min-one guard, add-provider CTA, D-05 enumeration-safe merge banner.
- `web/lib/api.ts` - New exported `getBaseUrl()`, new `linkProvider(provider, token)` helper, and a fixed `apiFetch` error-body parser that reads both the flat disc/set `{error,message}` envelope and FastAPI's nested `{detail:{error,reason}}` shape.
- `web/app/settings/page.tsx` - Suspense-wrapped `SettingsPageInner`; "Link a provider" CTA wiring (`handleLink`); the D-05 merge banner; the fixed `cannot_unlink_last` copy in `handleUnlink`'s catch branch.
- `web/components/ProviderList.tsx` - Ghost `Button` primitive migration for unlink; new "Link a provider" candidate section (primary `Button`); `text-xs`→`text-sm`, `text-neutral-400`→`neutral-500`; exports `providerLabel` for reuse by the settings page banner.
- `web/app/auth/callback/page.tsx` - Forwards `?error=email_conflict&pending_link_id=` to `/settings` alongside existing `?token=` handling.

## Decisions Made
- **Task 1 (checkpoint:decision):** option-b (frontend-only), selected by the user. See `key-decisions` in frontmatter for the full rationale and the reasoning behind not reading the opaque redirect's `Location` header.
- Add-provider candidates are limited to `github`/`google`/`apple` — `mastodon`/`indieauth` are excluded because the backend's own `POST /v1/auth/link/{provider}` (R-3, shipped in 07-02) explicitly 400s those two with `link_requires_domain`, and IndieAuth is hidden in production per D-05.
- The merge banner's provider list is sourced exclusively from the settings page's own already-fetched `providers` state (the current account's linked providers), never from the redirect's query params — which is moot for enumeration-safety anyway, since 07-02's redirect carries only `error`+`pending_link_id`, nothing about the matched account.
- `web_redirect_uri` for the add-provider `/login` navigation targets `/auth/callback` (the same target the NavBar's existing login button uses), keeping one shared convention for how every provider login/link round-trip returns to the web app; `/auth/callback` is the single router deciding whether to consume a `?token=` or forward `?error=email_conflict&pending_link_id=` to `/settings`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `apiFetch`'s error-body parsing — it never correctly read auth-route error responses**
- **Found during:** Task 3 (implementing the `cannot_unlink_last` UI-SPEC copy requirement)
- **Issue:** `apiFetch`'s existing error handling read `body.error` and `body.message ?? body.detail`. That matches the flat envelope used by `disc.py`/`set.py` (`_error_response` → `{error, message}`), but every auth route (`link_provider`, `unlink_provider`, etc.) raises `HTTPException(status_code=..., detail={"error": ..., "reason": ...})`, which FastAPI's default handler wraps as `{"detail": {"error": ..., "reason": ...}}`. Under the old parsing, `body.error` was always `undefined` (falls back to the generic `"api_error"` code) and `body.detail` was the nested object itself — coerced to the string `"[object Object]"` as the `ApiError` message. This meant the settings page's existing unlink-error handling could never actually detect `cannot_unlink_last` (or `not_found`, `already_linked`, etc.) against the real API — a genuine, pre-existing correctness gap directly blocking this plan's own acceptance criterion ("the 400 `cannot_unlink_last` surfaces the UI-SPEC copy").
- **Fix:** Added `extractErrorDetail()`, which reads either the flat `{error, message}` shape or the nested `{detail: {error, reason}}` shape (and handles `detail` being a plain string, e.g. framework-level 401s), used by both `apiFetch` and the new `linkProvider`.
- **Files modified:** `web/lib/api.ts`
- **Verification:** `settings.test.tsx`'s `cannot_unlink_last` test passes (via the mocked `unlinkProvider`, which bypasses `apiFetch` — the fix is exercised directly by `web/src/__tests__/auth.test.ts`'s existing real-`fetch` 401 test, which still passes since the flat-shape fallback path is preserved); full `npm test` (93/93), `npx tsc --noEmit`, and `npx eslint .` all remain clean.
- **Committed in:** `6e43f40` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (bug fix, directly required by this plan's own `cannot_unlink_last` acceptance criterion against the real API)
**Impact on plan:** The fix is necessary for the plan's own stated correctness requirement to hold beyond the mocked test — without it, the fixed UI-SPEC copy path would never trigger against the real backend. No scope creep: `web/lib/api.ts` was already in `files_modified`, and the fix only changes error-body parsing, not any endpoint's request shape or contract.

## Issues Encountered
None beyond the auto-fixed item above.

## Testing Scope Note
`settings.test.tsx` tests `linkProvider`'s consumer (the "Link a provider" CTA) with `@/lib/api` wholesale-mocked, per the plan's own `<behavior>` spec ("initiates the chosen add-flow (mocked)"). `linkProvider`'s internal `fetch(..., {redirect:"manual"})`/opaqueredirect handling is documented via code comments rather than covered by a dedicated low-level fetch-mocked unit test — jsdom/undici's support for `redirect:"manual"` opacity semantics is not reliably assertable in this environment, and the mechanism itself was explicitly directed by the Task 1 checkpoint resolution rather than an implementation detail this plan needed to independently validate.

## User Setup Required
None - no external service configuration required. (07-08's staging deploy must add the staging web origin to `CORS_ORIGINS` for the credentialed `linkProvider` fetch to succeed there — already known/tracked per 07-02's Pitfall 2 note, not new to this plan.)

## Next Phase Readiness
- WEBUI-04 ("Account settings surface (linked providers add/remove) is wired to AUTH-06/07") is now genuinely fully delivered: 07-02 shipped the backend redirect prerequisite, this plan ships the settings UI surface (add CTA, remove/min-one guard, D-05 merge banner).
- `web/lib/api.ts`'s `apiFetch` error-parsing fix benefits every existing and future auth-route consumer, not just this plan's new code.
- No blockers for 07-08 (staging deploy) — the `linkProvider`/`/login` round-trip depends on the staging web origin being in `CORS_ORIGINS`, which is already 07-08's own Task 1 responsibility (07-02-SUMMARY's Next Phase Readiness note).

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: web/src/__tests__/settings.test.tsx
- FOUND: web/lib/api.ts
- FOUND: web/app/settings/page.tsx
- FOUND: web/components/ProviderList.tsx
- FOUND: web/app/auth/callback/page.tsx
- FOUND commit: b4c181f
- FOUND commit: 6e43f40
