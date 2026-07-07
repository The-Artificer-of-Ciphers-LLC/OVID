# Phase 6: OAuth & Account Linking - Research

**Researched:** 2026-07-06
**Domain:** OAuth 2.0 / OIDC hardening (authlib, PyJWT, httpx) on an existing FastAPI auth subsystem
**Confidence:** HIGH (grounded directly in `api/app/auth/*` source and `api/tests/test_auth_*.py`; MEDIUM on exact DNS-rebinding closure approach, LOW/ASSUMED on Mastodon/GoToSocial cross-implementation email-verification behavior which D-06 already makes moot)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Replace the current session-carried pending-link (which merges into *whatever account
  logs in next* — structurally the nOAuth flaw) with a **server-side `PendingAccountLink` DB row**
  as the state carrier. Row carries `existing_user_id`, `new_provider`, `new_provider_id`,
  `expires_at`, `consumed_at` — giving real TTL + single-use + audit semantics enforceable at the DB layer.
- **D-02:** Re-authentication is proven by a **fresh OAuth re-login through a provider ALREADY
  linked to the existing account**. The re-auth callback loads the pending row, asserts
  `existing_user_id == freshly-authenticated user.id`, marks `consumed_at`, then attaches the new
  provider. This reuses a trust anchor OVID already verified — never trusts the new provider's email claim.
  (Every "existing account" has ≥1 linked provider by definition, so the anchor always exists.)
- **D-03:** The emailed-confirmation-link variant is explicitly **deferred** — OVID has zero SMTP/email
  infrastructure today; building it solely for this flow is disproportionate. Revisit only if OVID
  gains general email capability. Session-state-only and bare-signed-token-only were both rejected.
- **D-04:** `finalize_auth` must be refactored to be unit-testable with a plain DB fixture (no
  `Request.session` / Starlette middleware entanglement), so AUTH-09's three required tests
  (verified-email merge success, unverified-email merge rejection, merge-without-reauth rejection)
  assert directly on row state.
- **D-05:** **Signal-based allowlist.** A merge OFFER is made only when the provider supplies a real
  verified-email signal, checked at the source:
  - GitHub — must come from `GET /user/emails` (primary + `verified: true`), **not** the profile `email` field.
  - Google — require `id_token.email_verified === true` (issuer/aud checked).
  - Apple — require `id_token.email_verified === true` (note: private-relay addresses are Apple-verified proxies, still valid).
- **D-06:** **Mastodon and IndieAuth never match by email.** They attach to an existing account
  ONLY through the authenticated explicit-link flow (user already signed in, initiates linking).
  Skip the email-conflict path entirely for these two; keep Mastodon's `@noemail.placeholder` /
  null-email-for-IndieAuth pattern.
- **D-07:** A matching email from a non-trusted provider creates/keeps a **separate identity** — never
  a silent duplicate-merge and never a silent new-merge.
- **D-08:** **IndieAuth is gated off by default.** Register IndieAuth routes only when an operator
  explicitly opts in (feature flag / conditional router registration), disabled/404 otherwise.
  Do NOT leave it enabled-but-undocumented.
- **D-09:** **Bypass gating = single required `OVID_ENV`** env var, no default. The localhost bypass
  in `validate_url(..., allow_localhost=...)` is allowed **iff `OVID_ENV != "production"`**. An
  **import-time assertion** (mirroring the existing `_require_env("OVID_SECRET_KEY")` fail-fast in
  `api/app/auth/config.py`) refuses to boot until the operator declares dev/production, and refuses
  to boot if the bypass would be enabled under `OVID_ENV=production`.
  - Reusing `OVID_MODE` was researched and **rejected**: `standalone` is the default value in dev
    *and* self-host-prod compose, so it carries no dev/prod signal.
  - This is a **breaking change**: existing self-hosted instances must set `OVID_ENV` on upgrade.
  - Remove the unconditional `allow_localhost=True` at `api/app/auth/routes.py:400`; derive it from `OVID_ENV`.
- **D-10:** **Short exp per exchange, single key, runbook rotation.** Drop the Apple ES256 client-secret
  JWT `exp` from `now + 6mo` to a **short lifetime (~5 min / 300s)**, still regenerated per token
  exchange. Keep a single configured `.p8` (`APPLE_PRIVATE_KEY`/`APPLE_KEY_ID`). Rotating the underlying
  `.p8` key is an **ops runbook step**, documented in self-hosting/deployment + `docs/auth-setup.md`.
- **D-11:** In-app multi-`kid` key rotation is **deferred**. Keeping the 6-month exp was rejected
  (fails AUTH-03). Use a few-minutes buffer (not <60s) to tolerate clock skew/retries.

### Claude's Discretion

- Mastodon SSRF completeness audit (AUTH-05): the guardrail behaviors (hostname/reserved-IP checks,
  no redirect-following, no raw-response reflection, IPv6/multi-record/DNS-rebinding handling) are
  prescribed by the requirement — researcher/planner determine exactly which are already covered by
  `validate_mastodon_domain` vs. need adding. Not a user gray area.
- Exact `PendingAccountLink` table columns/indexes, endpoint paths, and migration id — planner's call,
  following existing SQLAlchemy/Alembic conventions.
- Exact `OVID_ENV` accepted values beyond the `production` sentinel — planner's call (e.g.
  `development`/`production`), but `production` must be the value that disables the bypass.

### Deferred Ideas (OUT OF SCOPE)

- Emailed account-merge confirmation link (D-03) — deferred until OVID has general email/SMTP
  infrastructure; would also cover the first-ever-provider merge edge case.
- In-app multi-`kid` Apple key rotation with overlap window (D-11) — deferred to a later milestone
  unless operator demand emerges; `.p8` rotation stays a runbook step for v0.2.0.
- Promoting IndieAuth to a fully-documented, UI-surfaced 5th provider — deferred; gated off by default
  for v0.2.0 (D-08). Revisit if IndieWeb support becomes a headline goal.
- The web account-settings UI that drives add/remove of linked providers is Phase 7 (WEBUI-04). This
  phase exposes the clean backend API semantics that Phase 7 wires to.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Sign in with GitHub works end-to-end | Already implemented (`routes.py` github_login/github_callback); Pattern 2 adds verified-email extraction without changing the happy-path login flow |
| AUTH-02 | Sign in with Google works end-to-end | Already implemented; Pattern 2 documents that authlib already verifies the ID token and exposes `email_verified` — no flow change, only a new field read |
| AUTH-03 | Apple sign-in with short-lived rotating ES256 client secret | Pattern/Code Example "Apple client-secret exp change" — one-line `exp` change in `generate_apple_client_secret()`; Assumptions Log A1 covers the `email_verified` string/bool nuance |
| AUTH-04 | Mastodon per-instance app registration | Already implemented (`mastodon.py` get_or_register_client); unaffected by this phase's SSRF hardening except for the validation function itself |
| AUTH-05 [guardrail] | Mastodon SSRF validation before any outbound request | Pitfall 4/5 + Code Example "IPv4+IPv6 hardening" — full gap audit of `validate_mastodon_domain` vs. AUTH-05's four named behaviors, with concrete fix and an explicit discretion point (Open Question 1) on DNS-rebinding closure depth |
| AUTH-06 | Link multiple providers, log in with any | Already implemented (`UserOAuthLink` junction, `/providers`); Pattern 1's refactor must preserve this behavior — covered by existing `test_auth_linking.py` |
| AUTH-07 | Add/remove providers, enforce ≥1 remaining | Already implemented (`unlink_provider`, routes.py:730-742); no code change identified as required, confirm via existing `test_unlink_last_provider_returns_400` |
| AUTH-08 [guardrail] | Merge requires explicit confirmation/re-auth, never silent | Architecture Diagram + Pattern 1/2/3 — full D-01/D-02/D-05/D-06/D-07 implementation path |
| AUTH-09 [guardrail] | `finalize_auth` isolated unit tests | Pattern 1 (session-free refactor) + Code Examples test pattern + Validation Architecture Wave 0 gap `test_auth_merge.py` |
| AUTH-10 [guardrail] | IndieAuth localhost bypass provably unreachable in production | Pattern 4 (OVID_ENV boot assertion) + Pattern 5 (conditional router registration) + Pitfall 6 (keep the assertion independent of the router flag) |
| DOCS-03 | `docs/auth-setup.md` published, incl. Mastodon requests-vs-httpx note | Don't Hand-Roll table (Mastodon.py divergence) + D-10's `.p8` rotation runbook note — see dedicated guidance below |
</phase_requirements>

## Summary

This phase does not build OAuth — GitHub, Google, Apple, Mastodon, and IndieAuth all already have working login flows in `api/app/auth/routes.py`, `mastodon.py`, and `indieauth.py`. The work is a **surgical hardening pass** on three named security defects (nOAuth-class merge takeover, Mastodon SSRF gaps, IndieAuth localhost-bypass reachability) plus a testability refactor of the single choke point (`finalize_auth`) all five providers share. Every locked decision in CONTEXT.md (D-01…D-11) has a concrete, identifiable implementation site in the existing code — this research maps each decision to its exact touch point and documents what is already correct vs. what is missing.

The most consequential finding: **`user_upsert` (`api/app/auth/users.py`) currently performs zero email-verification checks at all** — it matches on raw `email` string equality regardless of provider or verified status, and GitHub's email is read from the profile `email` field (`github_user.get("email")`, routes.py:191), not the verified `/user/emails` endpoint. This is the literal nOAuth vulnerability AUTH-08 requires closing, and D-05's per-provider signal-based allowlist must be enforced **before** `user_upsert` is ever called with conflict-checking semantics — i.e., the trust decision has to move to the call site (each provider's callback via `finalize_auth`), not stay inside `user_upsert`, because `user_upsert` currently has no way to know which caller has a verified signal and which doesn't.

The second most consequential finding: **none of the 11 tests in `test_auth_apple.py` actually assert `generate_apple_client_secret()`'s `exp` value.** The `exp: int(time.time()) + 3600` literals in that file are inside hand-built *mock Apple ID tokens* used to test the callback's JWKS/decode path — an entirely different JWT from the client-secret JWT the app itself generates at routes.py:251. CONTEXT.md's claim that "11 tests assert the old exp" does not hold up against the code; the planner should treat D-10's `exp` change as requiring **one new unit test** (asserting `~300s`), not an update to 11 existing tests.

**Primary recommendation:** Do the refactor in this order — (1) extract `finalize_auth`'s pure logic into a session-free function first (D-04), since D-01/D-02/D-05/D-06 all build on top of it; (2) add the `PendingAccountLink` model + migration; (3) rewire GitHub/Google/Apple email extraction to the verified-signal calls (D-05) and hard-block Mastodon/IndieAuth email-matching (D-06); (4) audit-and-patch Mastodon SSRF gaps (AUTH-05); (5) add the `OVID_ENV` boot assertion and IndieAuth conditional registration (AUTH-10); (6) drop the Apple `exp` (AUTH-03); (7) write `docs/auth-setup.md` (DOCS-03) last, once the above behavior is final.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| OAuth provider redirect/callback handling | API / Backend | — | `api/app/auth/routes.py` — FastAPI route handlers, no browser-side OAuth logic exists or should exist |
| Email-trust / merge-eligibility policy | API / Backend | — | Must live server-side; a client can never be trusted to declare its own email verified |
| `PendingAccountLink` state | Database / Storage | API / Backend | DB row is the trust anchor (D-01) — deliberately NOT session/cookie state, so it survives across requests/tabs and is auditable |
| SSRF validation of Mastodon instance URL | API / Backend | — | Must happen server-side before any outbound request; cannot be enforced client-side |
| IndieAuth route registration (on/off) | API / Backend | — | Conditional `include_router` at app-bootstrap time (`api/main.py`), a server config concern |
| `OVID_ENV` boot assertion | API / Backend | — | Import-time fail-fast, mirrors `_require_env` in `api/app/auth/config.py` — runs before any request is served |
| Account settings UI (add/remove providers) | Browser / Client | API / Backend | Explicitly OUT of scope for Phase 6 (WEBUI-04, Phase 7) — this phase only builds the backend semantics it will call |

## Package Legitimacy Audit

**No new packages are introduced by this phase.** All work uses libraries already declared in `api/requirements.txt` and already imported in `api/app/auth/`: `authlib>=1.3,<2.0`, `PyJWT>=2.8,<3.0`, `httpx>=0.27,<1.0`, `cryptography` (transitive, already used for Apple ES256 key loading), `sqlalchemy[asyncio]>=2.0,<3.0`, `alembic>=1.13,<2.0`. Test additions use `unittest.mock` (stdlib) matching the existing test pattern — no `respx` or other HTTP-mocking library is used anywhere in the test suite today, and none should be introduced (see Testing Patterns below).

`Package Legitimacy Gate` is not applicable — skip the full audit table.

## Architecture Patterns

### System Architecture Diagram (merge-confirmation flow, D-01/D-02)

```
                         ┌─────────────────────────────────────────────┐
                         │  Browser: user already logged in as A       │
                         │  (has session/JWT for A, A has ≥1 provider  │
                         │   already linked — e.g. Google)             │
                         └───────────────────┬───────────────────────-─┘
                                              │
   1. New provider login (e.g. GitHub) with  │
      a VERIFIED email matching account A    ▼
      ┌──────────────────────────────────────────────────────────┐
      │ GET /v1/auth/github/callback                              │
      │  → finalize_auth(provider="github", email=<verified>)    │
      │  → email-trust check (D-05): GitHub verified? YES         │
      │  → user_upsert finds email already owned by A             │
      └───────────────────────┬────────────────────────────────-─┘
                               │ 2. Create PendingAccountLink row
                               │    (existing_user_id=A, new_provider=github,
                               │     new_provider_id=<gh id>, expires_at=+N min)
                               ▼
                    Response: 409 { "error": "merge_offered",
                                     "pending_link_id": "<uuid>",
                                     "existing_user_id": "A" }
                               │
   3. Client shows "Link GitHub to your account? Re-authenticate  │
      to confirm" — redirects to an ALREADY-linked provider's      │
      login (e.g. Google) carrying pending_link_id                │
                               ▼
      ┌──────────────────────────────────────────────────────────┐
      │ GET /v1/auth/google/login?pending_link_id=<uuid>           │
      │  → stashes pending_link_id in session (short-lived, only   │
      │    used to route the callback — NOT the trust anchor)      │
      └───────────────────────┬────────────────────────────────-─┘
                               ▼
      ┌──────────────────────────────────────────────────────────┐
      │ GET /v1/auth/google/callback                               │
      │  → finalize_auth resolves google login → freshly-auth'd    │
      │    user via EXISTING UserOAuthLink (google, goog_a) → A    │
      │  → loads PendingAccountLink(id=pending_link_id)             │
      │  → asserts pending.existing_user_id == freshly-auth'd A.id │
      │  → asserts not pending.consumed_at, not expired             │
      │  → attaches UserOAuthLink(github, <gh id>) to A              │
      │  → marks pending.consumed_at = now()                        │
      └───────────────────────┬────────────────────────────────-─┘
                               ▼
                    Response: 200 { "token": <JWT for A>, "user": A }
```

Note that the new provider's own claimed email is **never** the proof of ownership in step 3-4 — the proof is completing a fresh OAuth round-trip through a provider OVID already trusts as linked to A. This is exactly D-02's stated design and is what closes the CVE-class nOAuth flaw (the current code trusts "whoever's session has `pending_link` and next successfully authenticates *anywhere*" — see Common Pitfalls below for why that's exploitable).

### Recommended Module Structure

```
api/app/auth/
├── routes.py         # thin route handlers — unchanged responsibility, but finalize_auth's
│                      # session/request handling moves to a thin wrapper here
├── merge.py           # NEW — PendingAccountLink CRUD, email-trust-signal extraction,
│                      # and the pure (session-free) finalize/resolve logic (D-04)
├── users.py           # user_upsert stays as the low-level upsert primitive; email-conflict
│                      # detection logic here is superseded by merge.py's trust-aware version
├── config.py           # + OVID_ENV boot assertion (D-09), mirroring _require_env
├── mastodon.py         # validate_mastodon_domain hardened for AUTH-05 gaps
└── indieauth.py         # validate_url unchanged logically; allow_localhost now driven by OVID_ENV
```

**Why a new `merge.py` rather than growing `users.py` or `routes.py`:** the existing codebase convention (confirmed in `mastodon.py`, `indieauth.py`) is that non-trivial domain logic (SSRF validation, PKCE, discovery) lives in its own module outside `routes.py`, imported by routes. `users.py`'s `user_upsert` is a narrow, provider-agnostic upsert primitive — the pending-link/email-trust policy is a different concern (merge eligibility) layered above it, matching CONTEXT.md's own "Established Patterns" note.

### Pattern 1: Session-free `finalize_auth` refactor (D-04, AUTH-09)

**What:** Split the current `finalize_auth(request, db, provider, provider_id, email, display_name)` into:
1. A pure function taking only DB-shaped inputs (no `Request`), e.g. `resolve_auth(db, *, provider, provider_id, email, email_verified, display_name, link_to_user_id=None, pending_link_id=None) -> AuthResult` where `AuthResult` is a small dataclass/NamedTuple (`user`, `merge_offer: PendingLinkOffer | None`).
2. A thin route-layer wrapper in `routes.py` that reads `request.session` (for `link_to_user_id`, `web_redirect_uri`, `pending_link_id`), calls the pure function, and translates the `AuthResult` into the existing HTTP response shapes (409 body, redirect, or `{token, user}` JSON).

**When to use:** Any time route-layer state (Starlette `Request.session`) needs to be tested without spinning up `TestClient`/middleware. This is exactly AUTH-09's three required tests:
- verified-email merge success — call `resolve_auth` twice with a plain `db_session` fixture, second call including `email_verified=True` and an existing conflicting email; assert a `PendingAccountLink` row is returned/created, no session/Request object needed.
- unverified-email merge rejection — same but `email_verified=False`; assert **no** merge offer is created (falls through to D-07's "separate identity" path instead of even generating a pending row).
- merge-without-reauth rejection — create a `PendingAccountLink` directly via DB fixture, then call `resolve_auth` for a DIFFERENT user's freshly-authenticated identity; assert `existing_user_id` mismatch is rejected (no attach, no consume).

**Example (pattern, not literal code — planner designs exact signature):**
```python
# api/app/auth/merge.py
from dataclasses import dataclass

@dataclass
class AuthResult:
    user: User
    merge_offer: "PendingAccountLink | None" = None

def resolve_auth(
    db: Session,
    *,
    provider: str,
    provider_id: str,
    email: str | None,
    email_verified: bool,
    display_name: str | None,
    link_to_user_id: str | None = None,
    pending_link_id: str | None = None,
) -> AuthResult:
    """Pure — no Request/session access. Testable with a bare db fixture."""
    if pending_link_id is not None:
        pending = _load_and_validate_pending_link(db, pending_link_id)
        freshly_authed_user = _resolve_existing_link(db, provider, provider_id)
        if freshly_authed_user is None or str(freshly_authed_user.id) != pending.existing_user_id:
            raise MergeReauthMismatchError()
        _attach_provider(db, freshly_authed_user, pending.new_provider, pending.new_provider_id)
        _consume(db, pending)
        return AuthResult(user=freshly_authed_user)
    # ... existing upsert / trust-checked conflict path ...
```

### Pattern 2: Per-provider verified-email extraction (D-05)

**What:** Each provider callback must compute an `email_verified: bool` signal at the *source*, before calling the shared resolver — never inferred from a generic profile field.

| Provider | Current code (routes.py) | Required change |
|---|---|---|
| GitHub | `email=github_user.get("email")` from `GET user` (line 191) — profile email, not verified | Add a second authlib call: `resp = await oauth.github.get("user/emails", token=token)`; iterate the returned list for `e["primary"] and e["verified"]`; use that as `email` + `email_verified=True`; if no such entry, `email=None, email_verified=False` |
| Google | `userinfo.get("email")` (line 561) | authlib's Starlette OIDC client already verifies the ID token signature and populates `token["userinfo"]` from its verified claims when `server_metadata_url` + `openid` scope are configured (confirmed: authlib auto-generates and validates the `nonce` whenever `openid` is in scope — `_create_oauth2_authorization_url` in `authlib/integrations/base_client/sync_app.py`). `userinfo.get("email_verified")` is available directly on that dict — no extra call needed, just start reading the field. [CITED: authlib docs.md — OIDC nonce/userinfo behavior] |
| Apple | `claims.get("email")` from the already-signature-verified ID token (line 372) | Same pattern as Google — read `claims.get("email_verified")` from the already-decoded, JWKS-verified claims dict (no extra call; Apple returns this as the **string** `"true"`/`"false"` in some SDKs — coerce with `str(claims.get("email_verified")).lower() == "true"` to be safe against both bool and string forms) |
| Mastodon | N/A — placeholder email always used | D-06: never compute a verified signal; keep `email_verified=False` unconditionally, `email=<placeholder>` |
| IndieAuth | N/A — `email=None` always | D-06: same — `email_verified=False` unconditionally |

**GitHub `/user/emails` scope note:** the existing GitHub OAuth registration already requests `scope: "user:email read:user"` (routes.py:55) — `user:email` is exactly the scope required for `/user/emails`, so **no scope change is needed**, only the additional API call. [CITED: docs.github.com/en/rest/users/emails — response fields `email`, `primary`, `verified`, `visibility`; `user:email` scope required]

### Pattern 3: `PendingAccountLink` model + migration

Follow the exact conventions already established (see `UserOAuthLink`, `FingerprintRegistry`/900000000005 migration):

```python
# api/app/models.py — new class, alongside UserOAuthLink
class PendingAccountLink(Base):
    __tablename__ = "pending_account_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    existing_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    new_provider: Mapped[str] = mapped_column(String(30), nullable=False)
    new_provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_pending_account_links_existing_user", "existing_user_id"),
    )
```

Migration: new revision `900000000007`, `down_revision = '900000000006'` (current head — confirmed by walking the full chain: `7ffb31fc807f → 800000000000 → 900000000001 → ... → 900000000006`). Follow the `800000000000_mastodon_oauth_clients.py` style exactly (`op.create_table` with `sa.UUID()`, no backfill needed since this is a brand-new table with no prior data, unlike `900000000005`'s backfill case). No SQLite-vs-Postgres shim is needed for this table specifically — it has no raw-`text()` SQL and no bulk backfill script, so the UUID-hex and datetime-adapter shims that `migrations_support.py`/`conftest.py` provide for *other* migrations (05-06's `sqlite3.register_adapter(datetime, ...)`) already cover ORM-level datetime handling transparently; confirm this by running the new table through the existing `_reset_tables` autouse fixture (`Base.metadata.create_all`), which is how all current models get test coverage — no new fixture infrastructure required.

### Pattern 4: `OVID_ENV` boot assertion (D-09, AUTH-10)

**What:** Mirror `_require_env` exactly, in the same file (`api/app/auth/config.py`):

```python
# api/app/auth/config.py — current pattern being mirrored:
def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set. ...")
    return value

SECRET_KEY: str = _require_env("OVID_SECRET_KEY")   # <-- existing fail-fast

# NEW, following the identical shape:
OVID_ENV: str = _require_env("OVID_ENV")
if OVID_ENV not in ("development", "production"):
    raise RuntimeError(
        f"OVID_ENV must be 'development' or 'production', got {OVID_ENV!r}."
    )
```

`api/app/auth/routes.py:400`'s `validate_url(url, allow_localhost=True)` (hardcoded) becomes `validate_url(url, allow_localhost=(OVID_ENV != "production"))`, importing `OVID_ENV` from `app.auth.config`. Because `config.py` raises at **import time**, and `routes.py` already imports from `app.auth.indieauth`/`app.auth.jwt` at module load (both import `app.auth.config` transitively via `jwt.py`), the assertion fires during `main.py`'s `from app.auth.routes import auth_router` — i.e., the app genuinely refuses to boot, matching D-09's intent. Confirm this import chain holds after the IndieAuth conditional-registration change (Pattern 5) — the assertion must NOT be skippable by disabling IndieAuth's router, since `OVID_ENV` also needs to exist for reasons beyond IndieAuth (a general dev/prod signal). Recommend keeping the `OVID_ENV` assertion in `config.py` (always evaluated) independent of whether IndieAuth's router is registered.

### Pattern 5: IndieAuth conditional router registration (D-08)

**Current state:** `indieauth_login`/`indieauth_callback` are defined directly on the shared `auth_router` in `routes.py` (lines 388-504) — same `APIRouter` instance as every other provider, always registered via `api/main.py:54` `app.include_router(auth_router)`.

**Required change:** Split IndieAuth's two routes into their own `APIRouter` (e.g. `indieauth_router = APIRouter(prefix="/v1/auth", tags=["auth"])` in `routes.py`, or a new small module), and register it conditionally in `main.py`:

```python
# api/main.py
app.include_router(disc_router)
app.include_router(sync_router)
app.include_router(auth_router)
if os.environ.get("OVID_ENABLE_INDIEAUTH", "").lower() in ("1", "true", "yes"):
    app.include_router(indieauth_router)
```

This matches the existing "providers are feature-gated on presence of their env vars" convention (GitHub/Google gate on client-id presence via `if _GITHUB_CLIENT_ID: oauth.register(...)`; Apple gates on `_APPLE_CONFIGURED`) — IndieAuth's gate is an explicit boolean opt-in flag instead, since IndieAuth has no client-id/secret to be naturally absent. **Name choice `OVID_ENABLE_INDIEAUTH` is Claude's/planner's discretion** — CONTEXT.md doesn't lock the exact flag name, only that it must default to off. When the router isn't registered, `test_auth_indieauth.py`'s route-based tests (`test_login_redirects_to_authorization_endpoint`, etc.) will need the flag set/patched for the app fixture, or those tests move to directly exercising `validate_url`/`discover_endpoints` (already unit-testable) while route-level tests assert 404 when the flag is unset and 200-path when set — the planner should decide which split minimizes test churn.

### DOCS-03: `docs/auth-setup.md` content requirements

No `docs/auth-setup.md` exists yet (confirmed — not in `docs/` directory listing). It must be added to `mkdocs.yml`'s nav (a natural home is under the existing "Technical" section, alongside `api-reference.md`, or a new "Auth" nav entry). Required contents, derived from the phase's success criteria and DOCS-03's explicit callout:

1. **Per-provider registration steps** for all four headline providers — GitHub OAuth App creation, Google Cloud OAuth Client creation, Apple Sign-In Service ID + Key creation (`.p8` download), and Mastodon (no manual registration needed — dynamic `POST /api/v1/apps` per instance, but document that this is automatic, unlike the other three).
2. **Required env vars** for each provider, matching the existing `_GITHUB_CLIENT_ID`/`_GOOGLE_CLIENT_ID`/`_APPLE_*` env var names read in `routes.py` — cross-reference `.env.example`.
3. **The new `OVID_ENV` requirement** (D-09) — flagged prominently as a **breaking change** for existing self-hosted instances, with the exact accepted values and what happens if it's unset (refuses to boot) or set to an unrecognized value.
4. **The Mastodon `requests`-vs-`httpx` client note** (verbatim requirement wording) — explain that OVID's Mastodon OAuth integration is hand-rolled with `httpx` (matching the rest of the codebase's HTTP client) rather than using the community `Mastodon.py` package (which depends on `requests`) — this is a deliberate deviation from `.planning/research/STACK.md`'s original recommendation, documented so a future contributor doesn't "fix" it back to `Mastodon.py`.
5. **Apple `.p8` key rotation runbook** (D-10) — step-by-step: register a new key in the Apple Developer console, update `APPLE_KEY_ID`/`APPLE_PRIVATE_KEY` env vars, restart the API (no code change needed since `generate_apple_client_secret()` regenerates the JWT client secret from current env values on every token exchange).
6. **IndieAuth opt-in note** (D-08) — document that IndieAuth is disabled by default, how to enable it (the env var chosen in Pattern 5), and that it's not one of the four headline providers surfaced anywhere else in the docs/UI.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Verifying Google/Apple ID token signature | A second manual JWKS-fetch-and-verify path for Google | authlib's Starlette OIDC client (already wired via `server_metadata_url`) — it already verifies signature, `iss`, `aud`, and `nonce` before populating `token["userinfo"]` | Duplicating this is extra attack surface for zero benefit — authlib already does it correctly and it's already in use |
| SSRF-safe outbound HTTP to a validated host | A bespoke resolver/socket library | `socket.getaddrinfo()` (stdlib, gets both A and AAAA records) in place of the current IPv4-only `socket.gethostbyname()`, combined with re-validating immediately before the outbound call or pinning the resolved IP for the request's lifetime | This is a well-known, narrowly-scoped stdlib fix — no third-party SSRF-guard package is necessary or lower-risk than getting the stdlib call right |
| DNS-rebinding-safe HTTP client | A new pip dependency (e.g. an "SSRF-safe requests" wrapper) | A scoped `httpx` custom transport or a `socket.getaddrinfo` monkeypatch active only for the duration of the validated outbound call (documented pattern, no new dependency) — see Common Pitfalls | Third-party SSRF-guard libraries for Python are a thin, poorly-audited ecosystem; a 10-20 line stdlib-only pinning shim is both lower risk and easier to review than adding a new trust boundary |
| Mastodon per-instance dynamic client registration | `Mastodon.py`/other Mastodon SDK, per the ORIGINAL `.planning/research/STACK.md` recommendation | The already-hand-rolled `httpx`-based flow in `api/app/auth/mastodon.py` | The team already diverged from the original stack pick and hand-rolled this with `httpx` for HTTP-client consistency across the codebase — **do not reintroduce `Mastodon.py`/`requests` now**; this divergence is exactly what DOCS-03's "Mastodon requests-vs-httpx client note" must document, so a future contributor doesn't "fix" it back |
| JWT signing/verification primitives | Hand-rolled ES256/RS256 signing | `PyJWT` (already used for both Apple client-secret generation and Apple ID-token verification) | Already the established, correct choice — no change needed here beyond the `exp` value |

**Key insight:** every piece of cryptographic or SSRF-sensitive logic this phase touches already has a correct primitive available in the codebase (authlib's OIDC verification, PyJWT's ES256/RS256, `ipaddress`'s private-range checks). The task is closing **call-site gaps** (which field is read, which claim is checked, which resolver function is called), not introducing new security primitives.

## Common Pitfalls

### Pitfall 1: The current implicit-merge model trusts session continuity, not identity
**What goes wrong:** `finalize_auth`'s existing `pending_link` mechanism (routes.py:84-105) stores the new provider's identity in `request.session["pending_link"]` on a 409, then on the **next** successful login in that same browser session — from ANY provider, matching ANY email — merges it in. There is no check that the "next login" is the account whose email actually matched.
**Why it happens:** The code conflates "whoever's session cookie has `pending_link` set" with "the legitimate owner of the existing account." A session cookie surviving across an OAuth redirect chain is necessary for CSRF-state purposes but is not proof of account ownership.
**How to avoid:** D-01/D-02's `PendingAccountLink` DB row keyed by `existing_user_id` (not session), consumed only when the SAME `existing_user_id` re-authenticates via an ALREADY-linked provider, closes this. Verify with a regression test that mirrors `test_pending_link_merges_on_next_login` but asserts the merge is REJECTED when the second login is a different, unrelated existing account.
**Warning signs:** Any code path that reads merge/link state from `request.session` rather than from a DB row with an explicit owner check.

### Pitfall 2: GitHub's profile `email` field is not a verified-email signal
**What goes wrong:** `github_user.get("email")` (the `GET /user` response) can be `null` even when the user has a verified email (if it's marked private), and historically this field reflects whichever email the user has designated as **public**, not necessarily verified. Using it for merge-eligibility trusts a value GitHub itself doesn't guarantee is verified.
**Why it happens:** `GET /user` and `GET /user/emails` are different endpoints with different guarantees; `GET /user`'s `email` is a convenience/display field, `GET /user/emails`'s `verified`+`primary` combination is the actual trust signal.
**How to avoid:** Always fetch `GET /user/emails` for merge-eligibility purposes (Pattern 2 above); keep `GET /user`'s `email` only as a display fallback for brand-new-user creation display, never for the trust decision.
**Warning signs:** Any `email_verified=True` assignment that isn't backed by a call to a provider's dedicated verified-email endpoint or a JWT claim named `email_verified`.

### Pitfall 3: Apple's `email_verified` claim can be a string, not a boolean
**What goes wrong:** Apple's ID token has historically returned `email_verified` as the string `"true"`/`"false"` rather than a JSON boolean in some token issuance paths — a naive `if claims.get("email_verified"):` check would treat the string `"false"` as truthy (all non-empty strings are truthy in Python).
**Why it happens:** Inconsistency between Apple's documented behavior and some client libraries' JSON decoding of the claim.
**How to avoid:** Normalize explicitly: `str(claims.get("email_verified", "")).strip().lower() == "true"`. Add a unit test asserting both the boolean `True` and the string `"true"` forms are accepted, and both `False`/`"false"`/missing are rejected.
**Warning signs:** A truthy-check on `email_verified` without an explicit string/bool normalization step.

### Pitfall 4: `validate_mastodon_domain`'s IPv4-only resolution misses AAAA-only or dual-stack rebinding
**What goes wrong:** `socket.gethostbyname(domain)` (mastodon.py:32) only resolves A (IPv4) records. A domain with only an AAAA record raises `gaierror` (fails safe — rejected), but a dual-stack domain that resolves to a public IPv4 at validation time and a private/loopback IPv6 address at actual-connection time (when `httpx` performs its own independent DNS resolution inside `get_or_register_client`/`mastodon_callback`) bypasses the check entirely.
**Why it happens:** `validate_mastodon_domain` and the subsequent `httpx.AsyncClient().post(...)`/`.get(...)` calls each independently resolve DNS — a classic TOCTOU DNS-rebinding window, made worse by only checking one address family.
**How to avoid:** (1) Switch to `socket.getaddrinfo(domain, None)` and validate **every** returned address (both families) against `ipaddress.ip_address(...).is_private/is_loopback/is_link_local/is_multicast/is_reserved`. (2) Close the TOCTOU window by pinning the validated IP for the actual outbound request — e.g. resolve once, then either (a) connect directly to the pinned IP with the `Host`/SNI header set to the original domain (custom `httpx` transport), or (b) temporarily monkeypatch `socket.getaddrinfo` to only return the validated address for the duration of the outbound call (a documented, dependency-free Python pattern: [CITED: joshua.hu — "A small solution to DNS rebinding in Python"]). Given the scope/cost tradeoff, the planner should decide whether full IP-pinning is in-scope for v0.2.0 or whether re-validating immediately before each of the two outbound Mastodon calls (registration + token exchange + verify_credentials) with a documented residual-risk note is acceptable — this is explicitly listed as "Claude's Discretion" in CONTEXT.md.
**Warning signs:** Any `httpx` call to a user-supplied hostname that isn't preceded by an IP-pinned or immediately-preceding validation for THAT SPECIFIC connection.

### Pitfall 5: `httpx.AsyncClient()` without `follow_redirects=True` is already safe here — don't "fix" it
**What goes wrong (if changed incorrectly):** A well-intentioned "harden Mastodon" pass might add `follow_redirects=True` to `mastodon.py`'s `httpx.AsyncClient()` calls (matching `indieauth.py`'s `discover_endpoints`, which does set `follow_redirects=True`), inadvertently reopening the exact redirect-based SSRF gap AUTH-05 requires closing.
**Why it happens:** httpx's default `follow_redirects=False` means the current Mastodon registration/token/verify calls (mastodon.py, routes.py) **already satisfy** "no redirect-following on outbound requests" — this guardrail is already in place and should be preserved, not "fixed" toward IndieAuth's more permissive pattern.
**How to avoid:** Explicitly assert `follow_redirects` is never set to `True` on any Mastodon-domain outbound call in a regression test (e.g., a test that has the mocked Mastodon endpoint issue a 302 to a private IP and asserts OVID does NOT follow it).
**Warning signs:** Copy-pasting `indieauth.py`'s `httpx.AsyncClient(follow_redirects=True)` pattern into `mastodon.py`.

### Pitfall 6: Splitting IndieAuth's router without breaking the `OVID_ENV` assertion's reachability
**What goes wrong:** If the `OVID_ENV` boot assertion is accidentally placed inside `indieauth.py` or gated behind the same conditional-registration flag as the router itself, disabling IndieAuth (the default, per D-08) would also disable the boot-time production-safety check — meaning an operator who never enables IndieAuth gets no signal at all about `OVID_ENV`, and one who enables it later without ever having set `OVID_ENV` could silently ship the bypass.
**Why it happens:** Both changes (D-08's gating, D-09's assertion) touch the same code area (`indieauth.py`'s `validate_url` call site) and could be conflated into one conditional block.
**How to avoid:** Keep `OVID_ENV` validation in `config.py`, evaluated unconditionally at import time regardless of whether IndieAuth's router ends up registered — `OVID_ENV` is a general dev/prod signal this phase introduces, not an IndieAuth-specific one.
**Warning signs:** Any code path where `OVID_ENV` is read/validated only inside an `if indieauth_enabled:` branch.

## Code Examples

### GitHub verified-email extraction (D-05)
```python
# Source: pattern confirmed against authlib docs (github.com/authlib/authlib/blob/main/docs/oauth2/client/web/index.md,
# "Fetch GitHub Repositories with Access Token" example — same oauth.<name>.get(path, token=token) call shape
# already used at api/app/auth/routes.py:167 for `oauth.github.get("user", token=token)`)
resp = await oauth.github.get("user/emails", token=token)
if resp.status_code != 200:
    # treat as no verified signal available — fall back to unverified path, do not 500
    email, email_verified = github_user.get("email"), False
else:
    emails = resp.json()
    primary_verified = next((e for e in emails if e.get("primary") and e.get("verified")), None)
    email = primary_verified["email"] if primary_verified else github_user.get("email")
    email_verified = primary_verified is not None
```

### Google/Apple — reading an already-verified claim (D-05)
```python
# Google: userinfo already populated + verified by authlib's OIDC client (routes.py:546)
google_email_verified = bool(userinfo.get("email_verified"))

# Apple: claims already verified via PyJWKClient + pyjwt.decode (routes.py:352-359)
apple_email_verified = str(claims.get("email_verified", "")).strip().lower() == "true"
```

### `validate_mastodon_domain` IPv4+IPv6 hardening (AUTH-05)
```python
# Source: stdlib socket docs — getaddrinfo returns all address families, gethostbyname is IPv4-only.
import socket

def _resolve_all_addresses(domain: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(domain, None)
    except socket.gaierror:
        raise ValueError("Could not resolve domain")
    return list({info[4][0] for info in infos})  # dedupe

resolved_ips = _resolve_all_addresses(domain)
for ip_str in resolved_ips:
    ip = ipaddress.ip_address(ip_str)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        raise ValueError("Domain resolves to private or restricted IP")
```

### Apple client-secret exp change (D-10)
```python
# api/app/auth/routes.py — generate_apple_client_secret(), one-line change:
now = int(time.time())
payload = {
    "iss": _APPLE_TEAM_ID,
    "iat": now,
    "exp": now + 300,   # was: now + (86400 * 180)  — 5 min per D-10, regenerated every exchange
    "aud": "https://appleid.apple.com",
    "sub": _APPLE_CLIENT_ID,
}
```

### Test pattern for the new merge flow (matches existing `unittest.mock` style, no new dependency)
```python
# api/tests/test_auth_merge.py (new file, following test_auth_linking.py's exact structure)
from unittest.mock import AsyncMock, MagicMock, patch

def test_verified_email_merge_offer_creates_pending_link(db_session, ...):
    """D-05: a verified-email match creates a PendingAccountLink, not a silent merge."""
    result = resolve_auth(db_session, provider="github", provider_id="gh_new",
                           email="shared@example.com", email_verified=True, display_name="X")
    assert result.merge_offer is not None
    row = db_session.query(PendingAccountLink).get(result.merge_offer.id)
    assert row.existing_user_id == str(existing_user.id)
    assert row.consumed_at is None

def test_unverified_email_never_offers_merge(db_session, ...):
    """D-05/D-07: an unverified-email match creates a SEPARATE identity, never a merge offer."""
    result = resolve_auth(db_session, provider="mastodon", provider_id="instance:123",
                           email="shared@example.com", email_verified=False, display_name="X")
    assert result.merge_offer is None
    assert result.user.email != "shared@example.com"  # placeholder/separate identity, D-07

def test_merge_without_reauth_is_rejected(db_session, ...):
    """D-02: attaching without the fresh re-auth callback matching existing_user_id fails closed."""
    pending = PendingAccountLink(existing_user_id=user_a.id, new_provider="github",
                                  new_provider_id="gh_new", expires_at=..., )
    db_session.add(pending); db_session.commit()
    with pytest.raises(MergeReauthMismatchError):
        resolve_auth(db_session, provider="google", provider_id="goog_of_user_b",
                      email=None, email_verified=False, pending_link_id=str(pending.id))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Trust profile `email` field for merge eligibility | Trust only provider-verified signals (`/user/emails`, `id_token.email_verified`) | Industry-standard nOAuth mitigation post-2023 disclosures (Descope/Okta writeups) | This phase (AUTH-08) |
| 6-month static-feeling Apple client-secret exp | Short-lived (~5 min), regenerated per exchange | Already technically possible since Apple allows any exp ≤6mo; this phase tightens it | This phase (AUTH-03/D-10) |
| `socket.gethostbyname` for SSRF host validation | `socket.getaddrinfo` (dual-stack) + IP-pinning for the actual request | Best-practice SSRF guidance has required dual-stack + TOCTOU closure for years; the existing code only had the IPv4/no-pinning version | This phase (AUTH-05) |

**Deprecated/outdated:** Session-cookie-carried merge state (`request.session["pending_link"]`) for anything security-sensitive — DB-row-backed state with explicit ownership checks is the correct pattern for any multi-step, cross-request trust decision.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Apple's `email_verified` claim may arrive as a string `"true"/"false"` rather than a JSON boolean, depending on token issuance path | Pitfall 3 / Pattern 2 | Low — the defensive normalization (`str(...).lower() == "true"`) is safe regardless of which form Apple actually sends; worst case is unnecessary defensive code, not a security gap |
| A2 | A lightweight `socket.getaddrinfo`-monkeypatch or custom-transport IP-pinning is an acceptable, in-scope closure of Mastodon's DNS-rebinding TOCTOU window for v0.2.0 | Pitfall 4 | Medium — if the planner decides full pinning is disproportionate for v0.2.0, this must be an explicit, documented residual-risk decision (not silently dropped), since AUTH-05 is a guardrail requirement |
| A3 | No respx or other HTTP-mocking library should be introduced; `unittest.mock` patching of `app.auth.routes.oauth`/`httpx.AsyncClient` remains the correct test pattern for new merge/SSRF tests | Code Examples / Testing Patterns | Low — confirmed by grepping every existing `test_auth_*.py` file; only a stylistic risk if ignored |

**If this table is empty:** N/A — see above; all three assumptions are low-to-medium risk and none block planning.

## Open Questions

1. **How much DNS-rebinding closure is proportionate for AUTH-05 in v0.2.0?**
   - What we know: The gap is real (Pitfall 4) and the fix pattern is well-documented and dependency-free.
   - What's unclear: Whether the planner should scope in full IP-pinning (more code, one custom transport) or accept a documented residual risk with tightened dual-stack validation only.
   - Recommendation: CONTEXT.md already marks this "Claude's Discretion" — the planner should pick one, document the choice explicitly in the phase's DECISIONS trail (not silently), and add a regression test proving whichever level of protection is chosen.

2. **Exact HTTP status/response shape for the merge-offer step.**
   - What we know: The current 409 shape is `{"error": "email_conflict", "existing_user_id": ...}`. D-01 replaces the underlying mechanism (DB row vs. session) but CONTEXT.md doesn't lock the new response shape/field names (e.g. whether to keep `error: "email_conflict"` or rename to `merge_offered`, whether to expose `pending_link_id` to the client).
   - What's unclear: Whether Phase 7's web UI (WEBUI-04, out of scope here) has any existing expectation baked in from `test_auth_linking.py`'s current 409 shape that this phase must preserve for backward compatibility, or whether it's free to change since WEBUI-04 hasn't been built yet.
   - Recommendation: Since Phase 7 is not yet built, this phase is free to define the new shape; keep `error` + `existing_user_id` for continuity, add `pending_link_id` as a new field.

3. **IndieAuth feature-flag env var name and default value semantics.**
   - What we know: CONTEXT.md explicitly defers this to planner discretion, only requiring default-off.
   - What's unclear: Naming convention consistency with the rest of the codebase (`OVID_MODE`, `OVID_ENV`, `CORS_ORIGINS` style vs. a boolean-flag style like `OVID_ENABLE_INDIEAUTH`).
   - Recommendation: `OVID_ENABLE_INDIEAUTH` (boolean-ish, truthy-string-parsed) matches no exact existing precedent but is the clearest/most conventional FastAPI-ecosystem naming; document in `.env.example` immediately below the other provider client-id vars.

## Environment Availability

No new external tool/service dependency is introduced. All work is Python-library-level (already-installed packages) plus one new required env var (`OVID_ENV`) and one new optional env var (`OVID_ENABLE_INDIEAUTH`). Both must be added to `.env.example`, `docker-compose.yml` (dev, default `OVID_ENV=development`), `docker-compose.test.yml` (`OVID_ENV=development` or a CI-specific value), and `docker-compose.prod.yml` (`OVID_ENV=production`, hardcoded like the existing `OVID_MODE: canonical` line, not defaulted via `${...:-}`).

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| authlib | GitHub/Google OAuth, OIDC verification | Yes | `>=1.3,<2.0` (installed) | — |
| PyJWT | Apple client-secret + ID-token verification | Yes | `>=2.8,<3.0` (installed) | — |
| httpx | Mastodon/Apple/IndieAuth outbound calls | Yes | `>=0.27,<1.0` (installed) | — |
| cryptography | Apple ES256 key loading | Yes (transitive via authlib/PyJWT[crypto]) | installed | — |
| `OVID_ENV` (new required env var) | AUTH-10 boot assertion | N/A — must be added to every compose file + `.env.example` | — | None — this is a deliberate breaking change per D-09 |

**Missing dependencies with no fallback:** None (no missing packages). `OVID_ENV` itself has "no fallback" by design (D-09) — every deployment (dev, test, prod, self-hosted) must set it explicitly, which is the intended breaking-change signal.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=7.0` (installed via `pip install -r requirements.txt` + `pip install pytest httpx` in CI) |
| Config file | none detected (no `pytest.ini`/`pyproject.toml` `[tool.pytest]` section found) — defaults apply |
| Quick run command | `cd api && python -m pytest tests/test_auth_merge.py -v` (new file) or targeted `-k` filters |
| Full suite command | `cd api && python -m pytest tests/ -v --tb=short` (matches CI's exact invocation) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | GitHub sign-in end-to-end | integration (existing) | `pytest tests/test_auth_github.py -x` | ✅ |
| AUTH-02 | Google sign-in end-to-end | integration (existing) | `pytest tests/test_auth_google.py -x` | ✅ |
| AUTH-03 | Apple sign-in + short-lived rotating client secret | unit (new) | `pytest tests/test_auth_apple.py -k exp -x` | ❌ Wave 0 — new test asserting `generate_apple_client_secret()`'s exp is ~300s |
| AUTH-04 | Mastodon per-instance registration | integration (existing) | `pytest tests/test_auth_mastodon.py -x` | ✅ |
| AUTH-05 | Mastodon SSRF validation completeness | unit (new) | `pytest tests/test_auth_mastodon.py -k ssrf -x` | ❌ Wave 0 — new tests for IPv6/dual-stack + redirect-rejection + (if scoped in) rebinding-pin |
| AUTH-06 | Link multiple providers, log in with any | integration (existing) | `pytest tests/test_auth_linking.py -x` | ✅ |
| AUTH-07 | Add/remove providers, min-one enforced | integration (existing) | `pytest tests/test_auth_linking.py -k unlink -x` | ✅ (`test_unlink_last_provider_returns_400` already covers this) |
| AUTH-08 | Confirm-gated merge, nOAuth defense | unit + integration (new) | `pytest tests/test_auth_merge.py -x` | ❌ Wave 0 — new file per Code Examples above |
| AUTH-09 | `finalize_auth` isolated unit tests | unit (new) | `pytest tests/test_auth_merge.py -k resolve_auth -x` | ❌ Wave 0 — depends on D-04 refactor landing first |
| AUTH-10 | IndieAuth localhost bypass unreachable in prod | unit (new) | `pytest tests/test_auth_config.py -x` (new file) | ❌ Wave 0 — new test asserting import raises when `OVID_ENV=production` and bypass would be reachable |

### Sampling Rate
- **Per task commit:** targeted `pytest tests/test_auth_<area>.py -x`
- **Per wave merge:** `pytest tests/ -v --tb=short` (full API suite — auth changes touch shared `finalize_auth`, risk of cross-provider regression per CONCERNS.md's own warning)
- **Phase gate:** Full suite green before `/gsd-verify-work`, plus a manual UAT pass against at least one real OAuth provider (GitHub is easiest to register a throwaway OAuth App for) since JWKS/network-dependent paths are mocked in unit tests

### Wave 0 Gaps
- [ ] `api/tests/test_auth_merge.py` — covers AUTH-08, AUTH-09 (resolve_auth pure-function tests + PendingAccountLink DB-state assertions)
- [ ] `api/tests/test_auth_config.py` — covers AUTH-10 (OVID_ENV import-time assertion; needs a subprocess-based or `importlib.reload`-based test since the assertion fires at module import, not at call time — follow the existing pattern of `os.environ.setdefault("OVID_SECRET_KEY", ...)` in `conftest.py` for how the codebase already handles import-time env dependencies in tests)
- [ ] New assertions inside `api/tests/test_auth_mastodon.py` for AUTH-05 (IPv6/dual-stack resolution, redirect-rejection, and whichever DNS-rebinding closure level is chosen per Open Question 1)
- [ ] New assertion inside `api/tests/test_auth_apple.py` (or the new merge test file) directly calling `generate_apple_client_secret()` and asserting the decoded `exp - iat` is `~300` (correcting the CONTEXT.md claim that 11 existing tests need updating — they don't test this value today)
- [ ] Alembic migration `900000000007_pending_account_links.py` — no test framework gap here (existing `_reset_tables` fixture picks up new ORM tables automatically), but the migration itself should be exercised via `alembic upgrade head` in CI if that's already checked elsewhere (not confirmed in this research — verify CI doesn't currently run `alembic upgrade head` as a smoke test; if it doesn't, this is a pre-existing gap outside this phase's scope, not one to silently introduce)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | OAuth 2.0 / OIDC via authlib; JWT session tokens via PyJWT (HS256, existing) |
| V3 Session Management | Yes | Starlette `SessionMiddleware` for OAuth CSRF `state`/`nonce` only (no app data) — unchanged this phase; the NEW `PendingAccountLink` DB row deliberately moves the merge-trust state OUT of session per D-01 |
| V4 Access Control | Yes | `get_current_user` dependency gates `/providers`, `/link`, `/unlink`; unlink enforces ≥1 remaining provider (AUTH-07, already implemented at routes.py:737) |
| V5 Input Validation | Yes | Mastodon domain validation (`validate_mastodon_domain`), IndieAuth URL validation (`validate_url`) — both hardened this phase |
| V6 Cryptography | Yes | ES256 (Apple client secret + PyJWT), RS256 (Apple/JWKS ID-token verification) — never hand-rolled, PyJWT/`cryptography` used throughout |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| nOAuth-class account takeover via unverified email merge | Spoofing / Elevation of Privilege | Per-provider verified-email signal checks (D-05) + confirm-gated re-auth via already-trusted provider (D-01/D-02) — this phase's core deliverable |
| SSRF via user-supplied Mastodon instance hostname | Tampering / Info Disclosure | Dual-stack IP validation + no-redirect-following + (scope-dependent) DNS-rebinding pinning (AUTH-05) |
| Config-drift reachable dev bypass in production | Elevation of Privilege | Import-time fail-fast assertion tying the bypass to a required, no-default env var (D-09/AUTH-10) — the standard mitigation for "a debug flag someone forgot to flip" class bugs |
| Session-fixation-adjacent trust confusion (current `pending_link` mechanism) | Spoofing | Move merge-eligibility state from session cookie to a DB row with an explicit `existing_user_id` ownership check (D-01) |
| JWT algorithm confusion (e.g., accepting `alg: none` or HS256-signed tokens where RS256/ES256 is expected) | Spoofing | Already mitigated: `pyjwt.decode(..., algorithms=["RS256"], ...)` for Apple explicitly pins the algorithm; confirm the same explicit `algorithms=[...]` pinning is preserved in any refactor — **never** widen to accept multiple algorithms without cause |

## Sources

### Primary (HIGH confidence)
- `api/app/auth/routes.py`, `users.py`, `config.py`, `mastodon.py`, `indieauth.py`, `jwt.py` — direct code read, this session
- `api/app/models.py`, `api/alembic/versions/*.py` — direct code read, this session (confirmed migration chain head = `900000000006`)
- `api/tests/test_auth_*.py`, `api/tests/conftest.py` — direct code read, this session (confirmed test-mocking pattern and the Apple-exp claim correction)
- `/authlib/authlib` via Context7 — OIDC nonce/userinfo auto-verification behavior, `oauth.<provider>.get(path, token=token)` call pattern

### Secondary (MEDIUM confidence)
- [docs.github.com/en/rest/users/emails](https://docs.github.com/en/rest/users/emails) — `GET /user/emails` response shape (`email`, `primary`, `verified`, `visibility`), `user:email` scope requirement (WebSearch, cross-referenced against official GitHub docs domain)
- [joshua.hu — A small solution to DNS rebinding in Python](https://joshua.hu/solving-fixing-interesting-problems-python-dns-rebindind-requests) — dependency-free Python DNS-pinning pattern for closing the Mastodon TOCTOU window
- `.planning/research/STACK.md`, `.planning/research/SUMMARY.md` — prior project research confirming the nOAuth threat model and documenting that the team diverged from the original `Mastodon.py` recommendation in favor of hand-rolled `httpx`

### Tertiary (LOW confidence)
- General DNS-rebinding SSRF literature (Behrad's Blog, PrefectHQ commit, thingsboard PR) — background pattern confirmation only, not project-specific; flagged for the planner's discretion on scope (Open Question 1)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries, all patterns confirmed against installed code + authlib's own docs
- Architecture: HIGH — every decision (D-01…D-11) mapped to an exact file/line in the existing codebase
- Pitfalls: HIGH for nOAuth/email-verification gaps (directly observed in code); MEDIUM for the DNS-rebinding closure recommendation (well-documented pattern, but exact implementation choice is explicitly left to planner discretion)

**Research date:** 2026-07-06
**Valid until:** 30 days (stable domain — OAuth provider APIs and authlib's core verification behavior change slowly; re-verify GitHub's `/user/emails` response shape and authlib's nonce-handling if this research is reused after a major authlib version bump)
