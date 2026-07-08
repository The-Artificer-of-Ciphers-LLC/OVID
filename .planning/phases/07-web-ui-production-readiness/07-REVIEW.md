---
phase: 07-web-ui-production-readiness
reviewed: 2026-07-07T00:00:00Z
depth: deep
files_reviewed: 32
files_reviewed_list:
  - api/app/auth/routes.py
  - api/app/routes/disc.py
  - api/app/routes/set.py
  - api/main.py
  - api/app/middleware.py
  - api/tests/test_auth_linking.py
  - api/tests/test_auth_merge_redirect.py
  - api/tests/test_disc_lookup.py
  - api/tests/test_session_cookie_secure.py
  - api/tests/test_set_redaction_and_limit.py
  - docs/deployment.md
  - web/app/auth/callback/page.tsx
  - web/app/disc/[fingerprint]/page.tsx
  - web/app/globals.css
  - web/app/page.tsx
  - web/app/settings/page.tsx
  - web/components/Button.tsx
  - web/components/ChapterEditor.tsx
  - web/components/ChapterList.tsx
  - web/components/Field.tsx
  - web/components/Input.tsx
  - web/components/ProviderList.tsx
  - web/components/SearchForm.tsx
  - web/components/SetSearchInput.tsx
  - web/components/SiblingDiscs.tsx
  - web/components/SubmitForm.tsx
  - web/lib/api.ts
  - web/lib/auth.ts
  - web/src/__tests__/auth.test.ts
  - web/src/__tests__/disc-detail.test.tsx
  - web/src/__tests__/pages.test.tsx
  - web/src/__tests__/primitives.test.tsx
  - web/src/__tests__/settings.test.tsx
  - web/src/__tests__/submit.test.tsx
findings:
  critical: 0
  warning: 7
  info: 2
  total: 9
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-07-07
**Depth:** deep (cross-file call-chain tracing: auth redirect flow, redaction builders, middleware stack, rate-limit decorator chain)
**Files Reviewed:** 32 (`.env.example` could not be read — blocked by tool permission settings on `.env*` files; not reviewed)
**Status:** issues_found

## Summary

The three explicitly-scoped Phase 7 deliverables — R-1 (anti-echo redaction of unverified
sibling structural fields in `_build_disc_set_nested`/`_build_sibling_summary`), R-2 (the
`AUTH_WRITE_LIMIT` write ceiling on `POST /v1/set`), and D-04 (the enumeration-safe
merge-offer 302 redirect in `finalize_auth`) — are implemented correctly and are backed by
targeted regression tests (`test_set_redaction_and_limit.py`, `test_auth_merge_redirect.py`)
that actually exercise the claimed behavior rather than rubber-stamping it. The
`_validate_web_redirect_uri` open-redirect guard uses strict `netloc` equality against a
`CORS_ORIGINS`-derived allowlist (not prefix/suffix matching), which resists the common
userinfo-injection (`https://trusted@evil.com`) and parser-confusion bypasses I probed. The
`SESSION_COOKIE_SECURE` env-gate in `api/main.py` is correctly wired and has full green/red
subprocess-level test coverage of the actual `Set-Cookie` header.

Cross-file tracing surfaced a real, previously-undocumented gap outside the phase's stated
scope but squarely inside the reviewed auth surface: **`api/app/auth/routes.py` has zero
rate-limiting on every route**, in a codebase where `disc.py`/`set.py` apply
`@limiter.limit(...)` to literally every endpoint and where `main.py` explicitly disables the
slowapi middleware's blanket default limits ("this avoids the middleware's default_limits
applying on top of per-route dynamic limits") — meaning routes with no decorator get *no*
throttling at all, not a fallback one. I also found a provably-incorrect middleware-ordering
comment in `main.py`, a client-spoofable merge-banner trigger, credential-in-URL / localStorage
exposure worth calling out given the task's explicit ask, a DRY violation between the two R-1
redaction builders, and a silent-data-loss bug in `ChapterEditor`'s time parser. None of these
rise to a correctness break in the phase's own headline deliverables, but several are real,
actionable security/quality gaps in the files under review.

## Warnings

### WR-01: `api/app/auth/routes.py` has no rate limiting on any route

**File:** `api/app/auth/routes.py:224,241,393,423,525,582,654,671,725,764,869,874,898`
**Issue:** Every route in this file (`github_login`, `github_callback`, `apple_login`,
`apple_callback`, `indieauth_login`, `indieauth_callback`, `google_login`, `google_callback`,
`mastodon_login`, `mastodon_callback`, `list_providers`, `link_provider`, `unlink_provider`) is
registered with **no `@limiter.limit(...)` / `@limiter.shared_limit(...)` decorator**, unlike
every route in `api/app/routes/disc.py` and `api/app/routes/set.py`, which apply
`_dynamic_limit` (reads) and `AUTH_WRITE_LIMIT` (writes) consistently to every endpoint. This
is not a "falls back to a global default" situation: `api/main.py` (lines 60-65) deliberately
omits `SlowAPIMiddleware` specifically *because* its blanket `default_limits` would apply "on
top of per-route dynamic limits" — meaning a route with no decorator on this app is completely
unthrottled, not merely under a coarser cap.

Concretely this leaves unauthenticated, network-calling endpoints open to unlimited abuse:
`apple_callback` does a JWKS fetch + ES256 client-secret mint + a `httpx` POST to Apple's token
endpoint per request with no cap; `mastodon_callback`/`mastodon_login` make multiple outbound
HTTP calls to an attacker-chosen Mastodon instance domain per request; and the
Bearer-authenticated `link_provider`/`unlink_provider` mutate `UserOAuthLink` rows with no
per-account write ceiling (unlike every other authenticated write route in the codebase).

**Fix:**
```python
# api/app/auth/routes.py — apply the same pattern already used everywhere else:
from app.rate_limit import AUTH_WRITE_LIMIT, UNAUTH_LIMIT, _dynamic_limit, limiter

@auth_router.get("/github/login")
@limiter.limit(_dynamic_limit)
async def github_login(request: Request, ...): ...

@auth_router.post("/link/{provider}")
@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])
def link_provider(provider: str, request: Request, ...): ...
```
Apply `_dynamic_limit` (or a tighter `UNAUTH_LIMIT`) to every `*_login`/`*_callback` route and
`AUTH_WRITE_LIMIT` to `link_provider`/`unlink_provider`, mirroring `disc.py`/`set.py`.

---

### WR-02: `api/main.py` middleware-ordering comment is inverted relative to Starlette's actual LIFO stack, undermining the CORS-preflight rationale it documents

**File:** `api/main.py:27-58`
**Issue:** The comment at line 27-28 states CORS "must be added before SessionMiddleware so
preflight OPTIONS requests get proper headers without hitting the session layer." Starlette's
`add_middleware()` **prepends** to `self.user_middleware` (`insert(0, ...)`), and
`build_middleware_stack()` wraps the app by iterating that list in *reverse* — meaning the
**last**-added middleware becomes the **outermost** layer (first to see the request), not the
first-added one. Given the actual call order in this file (`CORSMiddleware` →
`SessionMiddleware` → `RequestIdMiddleware` → conditionally `MirrorModeMiddleware`), the real
runtime stack (outermost → innermost) is:
`MirrorModeMiddleware → RequestIdMiddleware → SessionMiddleware → CORSMiddleware → routes`.

That is the *opposite* of what the comment claims — every request, including every CORS
preflight, passes through `RequestIdMiddleware` and `SessionMiddleware` *before* reaching
`CORSMiddleware`, not after. I confirmed `MirrorModeMiddleware` (`api/app/middleware.py:14,40`)
only intercepts `{POST, PUT, DELETE, PATCH}` and explicitly passes `OPTIONS` through, so this
particular ordering does not currently break preflight in mirror mode — but the reasoning
documented in the comment is factually wrong, and a future maintainer trusting it (e.g. adding
a middleware that *does* short-circuit on exception, or extending `_WRITE_METHODS`) would place
it in the wrong position expecting CORS to already have run. It's also a real (if narrow) live
gap today: if `SessionMiddleware` or `RequestIdMiddleware` were to raise before calling
`call_next`, the resulting error response would never pass back out through `CORSMiddleware`,
and the browser would report a CORS failure that masks the real 500.
**Fix:** Correct the comment to reflect Starlette's actual last-added-is-outermost semantics,
and/or reorder so `CORSMiddleware` is genuinely outermost (added *last*, after
`MirrorModeMiddleware`) if outermost-CORS is the intended behavior. Add a regression test that
asserts `OPTIONS` on a protected route returns proper `Access-Control-Allow-*` headers with
`OVID_MODE=mirror` set, so a future `_WRITE_METHODS` expansion can't silently break CORS again.

---

### WR-03: Duplicated R-1 anti-echo redaction logic between `disc.py` and `set.py`

**File:** `api/app/routes/disc.py:503-551` (`_build_disc_set_nested`) and
`api/app/routes/set.py:45-80` (`_build_sibling_summary`)
**Issue:** Both functions independently implement the identical
`if sibling.status == "unverified": withhold main_title/duration_secs/track_count` gate with
near-identical bodies (the per-title `is_main_feature`/`track_count` accumulation loop is
copy-pasted verbatim). This is exactly the kind of security-relevant rule that is easy to
silently diverge: a future change to the redaction predicate (e.g. adding `disputed` to the
withheld set, or changing which fields are considered "structural") only needs to be applied to
one of the two call sites to introduce a real R-1 regression, and nothing in the type system or
tests would catch the two implementations drifting apart other than duplicated test coverage
happening to be kept in lockstep.
**Fix:** Extract a single shared helper, e.g. `app/disc_identity.py::redact_sibling_summary(disc) -> SiblingDiscSummary`, and have both `_build_disc_set_nested` and `_build_sibling_summary`
call it.

---

### WR-04: Merge-conflict banner in `web/app/settings/page.tsx` is triggerable by anyone via a crafted URL, with no server-side validation that a real offer exists

**File:** `web/app/settings/page.tsx:104-113`
**Issue:**
```ts
const mergeError = searchParams.get("error");
const pendingLinkId = searchParams.get("pending_link_id");
const showMergeBanner =
  mergeError === "email_conflict" && !providersLoading && providers.length > 0;
```
`showMergeBanner` is derived entirely from client-supplied query parameters with no API call to
confirm `pendingLinkId` references a real, unconsumed `PendingAccountLink` for the current user.
Anyone can send an authenticated victim a link of the form
`https://oviddb.org/settings?error=email_conflict&pending_link_id=<anything>` and the victim
will see "This email is already linked to another OVID account…" with a "Re-authenticate" CTA,
regardless of whether any such conflict actually exists. The actual account merge remains safe
(`resolve_auth` rejects a re-auth whose resolved user doesn't match `pending.existing_user_id` —
verified by `test_cross_account_reauth_is_rejected`), so this is not an account-takeover path,
but it is a real phishing/social-engineering surface: a crafted link can make a legitimate
account look "compromised" or "already claimed" to induce distrust or drive the user into an
unnecessary re-auth flow.
**Fix:** Before rendering the banner, either (a) have `/auth/callback` mint a short-lived,
single-use, server-verifiable token alongside `pending_link_id` that `/settings` exchanges via
an API call before showing the banner, or (b) at minimum call a lightweight
`GET /v1/auth/pending-link/{id}` existence/ownership check server-side before flipping
`showMergeBanner` to `true`.

---

### WR-05: Long-lived JWT delivered via URL query string is captured by the documented reverse-proxy/CDN access-log chain

**File:** `api/app/auth/routes.py:204-209` (success-path redirect); `web/app/auth/callback/page.tsx:12-18` (consumer)
**Issue:** `finalize_auth`'s success path appends the 30-day access token as a raw query
parameter (`?token=<jwt>`) to `web_redirect_uri` and 302s the browser there. Per
`docs/deployment.md`'s own documented topology (`Internet → Cloudflare → redshirt (nginx) →
holodeck`), this URL — full query string included — will be written to nginx's access log on
redshirt and to Cloudflare's edge logs by default, putting a 30-day-lived bearer credential into
plaintext log storage outside the application's control. `web/app/auth/callback/page.tsx` does
call `router.replace("/")` promptly to scrub the token from the visible URL/history, which
mitigates the browser-history exposure, but does nothing about logs already written by
intermediate infrastructure before the redirect is even received by the browser.
**Fix:** If feasible, deliver the token via a short-lived, `httpOnly` cookie set on the redirect
response instead of (or in addition to, for cross-origin cases) a query parameter, or reduce the
token lifetime for the web-redirect path specifically. At minimum, document (in
`docs/deployment.md`, alongside the existing Redis/rate-limit operational notes) that
access-log retention/redaction policy must account for JWTs appearing in the querystring of
`/auth/callback` requests on both nginx and Cloudflare.

---

### WR-06: `ChapterEditor` silently discards malformed chapter start-time input with no user feedback

**File:** `web/components/ChapterEditor.tsx:26-36`
**Issue:**
```ts
function parseTime(value: string): number | null {
  const parts = value.split(":").map((p) => parseInt(p, 10));
  if (parts.some((p) => isNaN(p))) return null;
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return null;
}
```
Any input that isn't exactly `H:MM:SS` or `MM:SS` — including a bare number of seconds (e.g.
`"90"`, which has no `:`, so `parts.length === 1`) or any non-numeric junk — silently resolves
to `null` via `handleTimeBlur` (line 78-84) and is written back into form state with **no error
shown to the user**. A contributor who types a start time in an unsupported format loses that
value on blur without any indication anything went wrong, and the chapter is silently submitted
with `start_time_secs: null`.
**Fix:** Distinguish "empty" (intentional clear) from "unparseable" (user error) in
`handleTimeBlur`, and surface a `Field`-style inline error (the codebase already has this
primitive, see `web/components/Field.tsx`) rather than silently overwriting with `null`:
```ts
function handleTimeBlur(index: number, value: string) {
  const trimmed = value.trim();
  if (trimmed === "") { /* clear as today */ return; }
  const secs = parseTime(trimmed);
  if (secs === null) {
    setTimeError(index, "Use H:MM:SS or MM:SS");
    return; // don't clobber the previously-valid value
  }
  ...
}
```

---

### WR-07: JWT stored in `localStorage` with no additional hardening

**File:** `web/lib/auth.ts:10-25`
**Issue:** `getToken`/`setToken`/`clearToken` persist the API bearer JWT in `localStorage`
under `ovid_token`. `localStorage` is readable by any script executing in the page's origin, so
any future stored-XSS anywhere in the app (including in third-party-influenced surfaces such as
the disc-detail page's TMDB/IMDb external links or user-submitted release metadata rendered
elsewhere) would be sufficient to exfiltrate a live 30-day session token — there is no
`httpOnly` boundary. This is a known, common SPA tradeoff rather than a defect introduced by
this phase, but it's flagged per the explicit review brief to check "credential/token handling
in localStorage," and it compounds WR-05 above (both put the same long-lived token outside any
`httpOnly` protection).
**Fix:** No change required to ship this phase, but worth an explicit accepted-risk note in
`docs/`, and consider a shorter-lived access token + refresh flow, or a migration to an
`httpOnly` session cookie for the web client specifically, as a follow-up hardening item.

## Info

### IN-01: `.env.example` could not be reviewed

**File:** `.env.example`
**Issue:** The `Read` tool reported this file's directory is denied by the current permission
settings, so it was not included in this review despite being listed in the required-reading
set. Given the other reviewed files reference it extensively for `CORS_ORIGINS`,
`SESSION_COOKIE_SECURE`, and OAuth provider variable documentation, it should be reviewed
separately (e.g., via a scoped permission grant or a diff-only view) to confirm its guidance
matches the behavior verified here.
**Fix:** N/A — process note for the orchestrator, not a code defect.

### IN-02: Inconsistent 429 response body shape between the anti-Sybil cooldown and the slowapi write-ceiling

**File:** `api/app/routes/disc.py:360-373` vs. `api/tests/test_set_redaction_and_limit.py:214-224`
**Issue:** The anti-Sybil `hard_blocked` cooldown 429 (`disc.py:365-373`) only sets
`Retry-After` as a response **header**, with no `retry_after` key in the JSON body. The
slowapi-driven write-ceiling 429 exercised by `test_create_set_enforces_auth_write_limit`
(`test_set_redaction_and_limit.py:219-224`) asserts `"retry_after" in body`, i.e. that same
information is duplicated into the JSON body for that path. Two different 429 shapes exist in
the same API for conceptually similar "you're rate limited, retry later" responses, which is a
minor client-integration inconsistency (a caller has to know which of the two 429 flavors it's
looking at to find the retry hint).
**Fix:** Standardize on one shape — either add `retry_after` to the anti-Sybil cooldown body for
parity, or drop it from the slowapi handler's body and document that `Retry-After` is always a
header. Low priority; not part of this phase's stated scope.

---

_Reviewed: 2026-07-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
