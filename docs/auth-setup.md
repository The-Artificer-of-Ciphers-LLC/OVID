# OAuth & Authentication Setup

This guide is the authoritative reference for configuring OVID's sign-in providers and the operational settings the OAuth subsystem depends on. It covers per-provider registration, the required environment variables, the mandatory `OVID_ENV` declaration, the Apple key-rotation runbook, and the IndieAuth opt-in.

OVID supports four **headline** sign-in providers — **GitHub**, **Google**, **Apple**, and **Mastodon** — plus an optional, off-by-default **IndieAuth** provider. Every provider is feature-gated: OVID only activates a provider when its environment variables are present, so you can enable exactly the providers you want.

!!! danger "Breaking change on upgrade — `OVID_ENV` is now required"
    Existing self-hosted instances **must** set the new `OVID_ENV` variable before the API will boot. See [The `OVID_ENV` requirement](#the-ovid_env-requirement-required) below. This is a deliberate, non-optional breaking change introduced to make the IndieAuth localhost bypass provably unreachable in production.

---

## The `OVID_ENV` requirement (required)

`OVID_ENV` declares the deployment environment. It has **no default** — the API refuses to boot until an operator sets it explicitly. This fail-fast mirrors the existing `OVID_SECRET_KEY` behavior so that "someone forgot to flip the dev bypass off in production" is structurally impossible.

| Variable | Accepted values | Behavior |
|----------|-----------------|----------|
| `OVID_ENV` | `development`, `production` | Required. Any other value (or unset) causes the API to raise a `RuntimeError` at import time and **refuse to boot**. |

Behavioral effects:

- **`OVID_ENV=development`** — the IndieAuth localhost bypass is permitted (`validate_url(..., allow_localhost=True)`), so you can point IndieAuth at `http://localhost` endpoints while developing.
- **`OVID_ENV=production`** — the localhost bypass is disabled by construction. `ALLOW_LOCALHOST_BYPASS` is derived solely from `OVID_ENV` and is always `False` in production; an explicit import-time invariant assertion enforces this.
- **Unset or unrecognized** — the API raises at import time and does not start. There is no silent fallback.

!!! warning "Upgrading an existing deployment"
    Set `OVID_ENV` in every compose file / environment before upgrading:

    - `docker-compose.yml` (dev) → `OVID_ENV=development`
    - `docker-compose.test.yml` (CI/test) → `OVID_ENV=development`
    - `docker-compose.prod.yml` (production) → `OVID_ENV=production`

    A production deployment that omits `OVID_ENV` will fail to start rather than run with an unsafe default.

---

## Provider environment variables

All provider variables are read from the environment (via `.env` or your compose file). Names below match the code exactly (`api/app/auth/config.py`, `api/app/auth/routes.py`).

| Provider | Variables | Required for that provider |
|----------|-----------|----------------------------|
| GitHub | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | Both |
| Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Both |
| Apple | `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | **All four** — Apple activates only when every value is present |
| Mastodon | *(none — dynamic per-instance registration)* | — |
| IndieAuth | `OVID_ENABLE_INDIEAUTH` | Opt-in flag only |

Supporting variables:

| Variable | Purpose |
|----------|---------|
| `OVID_SECRET_KEY` | Required. Signs OVID's own session JWTs. The API refuses to boot without it. |
| `OVID_ENV` | Required. See [above](#the-ovid_env-requirement-required). |
| `OVID_API_URL` | Public base URL of this API (default `http://localhost:8000`). Used to construct each provider's OAuth **redirect URI**. |

Each provider's OAuth **redirect (callback) URI** is `{OVID_API_URL}/v1/auth/<provider>/callback`, for example:

- GitHub: `http://localhost:8000/v1/auth/github/callback`
- Google: `http://localhost:8000/v1/auth/google/callback`
- Apple: `http://localhost:8000/v1/auth/apple/callback`
- Mastodon: `http://localhost:8000/v1/auth/mastodon/callback`

In production, set `OVID_API_URL` to your public HTTPS URL (e.g. `https://api.oviddb.org`) so the redirect URIs you register with each provider match what OVID sends.

---

## Per-provider registration

### GitHub OAuth App

1. Go to **GitHub → Settings → Developer settings → OAuth Apps → New OAuth App** (`https://github.com/settings/developers`).
2. Set **Homepage URL** to your OVID web URL and **Authorization callback URL** to `{OVID_API_URL}/v1/auth/github/callback`.
3. Register the app and copy the **Client ID** and generate a **Client secret**.
4. Set the env vars:

   ```bash
   GITHUB_CLIENT_ID=Iv1.xxxxxxxxxxxx
   GITHUB_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

OVID requests the `user:email read:user` scope. The `user:email` scope is required so OVID can read the **verified primary email** from `GET /user/emails` — the verified-email signal used for safe account linking. No additional scope configuration is needed.

### Google Cloud OAuth Client

1. In the **Google Cloud Console → APIs & Services → Credentials**, create an **OAuth client ID** of type **Web application**.
2. Add `{OVID_API_URL}/v1/auth/google/callback` to **Authorized redirect URIs**.
3. Copy the **Client ID** and **Client secret**.
4. Set the env vars:

   ```bash
   GOOGLE_CLIENT_ID=xxxxxxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   ```

OVID uses Google's OpenID Connect discovery document (`https://accounts.google.com/.well-known/openid-configuration`) with the `openid email profile` scope. The ID token — including the `email_verified` claim — is verified by authlib's OIDC client; OVID does not hand-roll ID-token verification.

### Apple Sign-In (Service ID + Key)

Apple requires four coordinated values. Configure them in the [Apple Developer](https://developer.apple.com/account/resources) portal:

1. Create an **App ID** (or use an existing one) with **Sign in with Apple** enabled.
2. Create a **Services ID** — its identifier becomes your `APPLE_CLIENT_ID`. Configure its **Return URL** to `{OVID_API_URL}/v1/auth/apple/callback`.
3. Note your **Team ID** (`APPLE_TEAM_ID`) from the top-right of the developer portal.
4. Create a **Key** with **Sign in with Apple** enabled, then **download the `.p8` private key file** (Apple lets you download it only once). Record the **Key ID** (`APPLE_KEY_ID`).
5. Set the env vars:

   ```bash
   APPLE_CLIENT_ID=com.example.ovid.service
   APPLE_TEAM_ID=ABCDE12345
   APPLE_KEY_ID=FGHIJ67890
   # The .p8 contents — either raw PEM text, or base64-encoded PEM:
   APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
   ```

`APPLE_PRIVATE_KEY` accepts either the PEM text directly or a base64-encoded PEM (OVID detects and decodes base64 automatically). Apple activates only when **all four** variables are set.

Apple's OAuth `client_secret` is itself a short-lived ES256 JWT that OVID **regenerates on every token exchange** (see the [Apple client-secret rotation](#apple-key-rotation-runbook) section) — you never store or manually rotate a client secret.

### Mastodon (automatic per-instance registration)

Unlike the other three providers, **Mastodon requires no manual app registration.** When a user signs in with a Mastodon instance for the first time, OVID dynamically registers an OAuth app on that instance via `POST https://<instance>/api/v1/apps` and caches the resulting client credentials in its database (`MastodonOAuthClient`). There are no `MASTODON_*` environment variables.

Because the instance URL is user-supplied, OVID validates it against SSRF before making any outbound request — see [Mastodon SSRF posture](#mastodon-ssrf-posture-and-the-httpx-note) below.

---

## Apple key rotation runbook

Apple's `client_secret` is a JWT minted from your `.p8` key with a **~5-minute (`exp = now + 300s`) lifetime, regenerated on every token exchange**. Per-exchange regeneration *is* the automated rotation of the client secret — there is no long-lived secret to rotate.

Rotating the underlying **`.p8` signing key** (for example, if the key is compromised or you follow a periodic rotation policy) is a simple ops step with **no code change**:

1. In the Apple Developer portal, create a **new Key** with **Sign in with Apple** enabled and download its `.p8` file. Note the new **Key ID**.
2. Update the two env vars on the API host:

   ```bash
   APPLE_KEY_ID=<new key id>
   APPLE_PRIVATE_KEY=<new .p8 PEM or base64-encoded PEM>
   ```

3. Restart the API (e.g. `docker compose restart api`).

On the next token exchange, `generate_apple_client_secret()` rebuilds the client-secret JWT from the current env values — the new key takes effect immediately. Once traffic confirms the new key works, **revoke the old key** in the Apple Developer portal.

!!! note "In-app multi-key rotation is deferred"
    OVID uses a single configured `.p8` key. In-app rotation with an overlapping-`kid` window is intentionally deferred; the runbook above is the supported rotation path for v0.2.0.

---

## Mastodon SSRF posture and the `httpx` note

### Why OVID hand-rolls Mastodon OAuth with `httpx` (not `Mastodon.py`)

OVID's Mastodon integration is deliberately **hand-rolled with `httpx`** — the same async HTTP client used across the rest of the OVID codebase — rather than the community `Mastodon.py` package (which depends on `requests`). This is a conscious deviation from the original stack recommendation, made for HTTP-client consistency and to avoid pulling `requests` into a codebase that is otherwise `httpx`-native.

!!! warning "Do not 'fix' this back to Mastodon.py / requests"
    This divergence is intentional and documented here precisely so a future contributor does not "correct" it back to `Mastodon.py`/`requests`. Keep Mastodon OAuth on `httpx`.

### SSRF validation (AUTH-05)

The user-supplied Mastodon instance domain is validated by `validate_mastodon_domain()` **before** any outbound request:

- The domain is resolved with `socket.getaddrinfo()` — **dual-stack (IPv4 + IPv6)**, so an AAAA-only or dual-stack host pointing at a private/loopback IPv6 address cannot slip past an IPv4-only check.
- **Every** resolved address is rejected if it is private, loopback, link-local, multicast, or reserved (`ipaddress.ip_address(...).is_private / is_loopback / is_link_local / is_multicast / is_reserved`).
- The outbound `httpx` calls do **not** follow redirects (httpx's default `follow_redirects=False` is preserved), so a Mastodon endpoint cannot 302-redirect OVID to a private address.

### Known limitation / accepted residual: DNS-rebinding TOCTOU (T-06-05d)

!!! warning "Accepted residual risk for v0.2.0 — DNS rebinding"
    `validate_mastodon_domain()` performs a **validate-then-connect** flow: it resolves the domain once to validate the address family and IP range, and the subsequent `httpx` request in `get_or_register_client()` independently resolves DNS again when it connects. Because the host is resolved **twice**, a DNS-rebinding attacker who controls the authoritative DNS for a domain could return a public IP during validation and then a private/internal IP for the real outbound request, bypassing the check.

    Full closure requires **IP-pinning** the validated address for the lifetime of the outbound request (e.g. a custom `httpx` transport, or a scoped `socket.getaddrinfo` override that returns only the validated address). This is a well-understood, dependency-free pattern, but it is **deferred to a later milestone**. For v0.2.0, the dual-stack validation plus the no-redirect-following posture above are the enforced mitigations, and this DNS-rebinding TOCTOU window is a **knowingly accepted residual risk**, recorded here so it is visible to operators rather than silently dropped.

    Operators concerned about SSRF from user-supplied Mastodon domains should run the API behind egress network controls (e.g. blocking outbound traffic to internal IP ranges at the firewall/proxy layer) as defense in depth until IP-pinning lands.

---

## IndieAuth (opt-in, disabled by default)

IndieAuth is **not** one of the four headline providers. Its routes are **disabled by default** and return `404` unless an operator explicitly opts in.

To enable IndieAuth, set the opt-in flag:

```bash
OVID_ENABLE_INDIEAUTH=true
```

Accepted truthy values (case-insensitive): `1`, `true`, `yes`. Any other value (or unset) leaves IndieAuth off, and its login/callback routes (`/v1/auth/indieauth/login`, `/v1/auth/indieauth/callback`) return `404`.

When enabled in `OVID_ENV=development`, IndieAuth may target `localhost` endpoints (the localhost bypass is permitted in development). In `OVID_ENV=production`, the localhost bypass is disabled regardless of this flag — the two settings are independent, so enabling IndieAuth in production never re-opens the localhost bypass.

!!! note "IndieAuth is not surfaced in the default UI"
    Because IndieAuth is off by default, it is not one of the providers surfaced in the web UI or elsewhere in the docs. Enable it only if you specifically need IndieWeb sign-in.

---

## See also

- [Self-Hosting Guide](self-hosting.md) — running an OVID mirror node.
- [Deployment](deployment.md) — full stack deployment runbook (dev / production / test environments and ports).
