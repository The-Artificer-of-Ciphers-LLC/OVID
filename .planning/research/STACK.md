# Stack Research

**Domain:** Physical video-disc structural fingerprinting (DVD/Blu-ray/UHD) + FastAPI backend hardening (rate limiting, OAuth) for OVID v0.2.0
**Researched:** 2026-07-05
**Confidence:** MEDIUM overall (HIGH for library/version facts verified directly against PyPI/GitHub/GitLab APIs; MEDIUM for behavioral/gotcha claims sourced from web search without a primary spec doc; see per-section notes)

This is a **subsequent-milestone, stack-completion** research pass — it does not re-litigate the existing Python 3.12 + FastAPI + PostgreSQL 16 + Next.js 16 baseline (already documented in `.planning/codebase/STACK.md`). It answers only what's needed to finish the four remaining v0.2.0 strands: Blu-ray/UHD fingerprinting, the libdvdread Disc ID method, Redis-backed rate limiting, and the four OAuth providers.

## Recommended Stack

### Core Technologies (new for this milestone)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `libbluray` (system lib, VideoLAN) | 1.4.1 (latest GitLab tag) | Blu-ray/UHD BDMV/PLAYLIST/CLPI structure access; exposes `BLURAY_DISC_INFO.disc_id[20]` | Reference C implementation for both OVID-BD-2 (Tier 2 structure hash) and the AACS Disc ID (Tier 1) in one dependency. Already required transitively by any AACS-capable ripping stack, so ARM users have it installed. LGPL-2.1, already vetted compatible in the technical spec's licensing table. |
| `libaacs` (system lib, VideoLAN) | 0.11.1 (latest GitLab tag) | Computes/exposes the AACS Disc ID (SHA-1 of `Unit_Keys_RO.inf`) used for Tier 1 `bd1-aacs-*` / `uhd1-aacs-*` fingerprints | `aacs_get_disc_id()` returns the 20-byte ID; `libbluray` surfaces it via `BLURAY_DISC_INFO.disc_id` when both libs are present and the disc is AACS-protected. LGPL-2.1, dynamically-linked (do not static-link — preserves the end user's right to swap AACS key databases). |
| `bluread` (PyPI) | 1.4 (tracks libbluray ~1.4.x) | Python ctypes wrapper around `libbluray`, exposing disc info (incl. `disc_id`), playlists, and clips | This is the actual PyPI package for the `PyBluRead` project (github: `cmlburnett/PyBluRead`) — **the package name on PyPI is `bluread`, not `PyBluRead`**. Actively maintained (pushed 2024-07-12, i.e. not stale). Covers both Tier 1 (disc_id) and Tier 2 (playlist/clip enumeration) through one dependency instead of stitching together a separate MPLS-only parser. Caveat: the repo ships no LICENSE file even though it wraps GPL/LGPL code — flag for legal review before shipping, and pin to a specific commit/version rather than trusting semver stability. |
| `libdvdread` (system lib) | already in the stack (ADR 0001 Phase 1 landed) | Source of the `dvdread1-*` Disc ID via `DVDDiscID()`/`DVDGetDiscID()` | No new dependency — already present. New finding: `DVDDiscID()` computes an **MD5 of the concatenated bytes of `VIDEO_TS.IFO` + all `VTS_nn_0.IFO` files** (content hash of the IFO files themselves), not a semantic/structural hash like OVID-DVD-1. This is the "Disc ID" the DVD tooling ecosystem (`libdvdnav`, MakeMKV compatibility layers) commonly refers to. |
| `redis` (Redis server) | 8.x (Docker image `redis:8-alpine` or newer) | Centralized counter store for rate limiting | Fixes the documented in-memory multi-worker defect: `slowapi`'s in-memory `MemoryStorage` keeps a separate counter per gunicorn worker process, silently multiplying the effective rate limit by the worker count. A shared Redis store makes the configured limit global across all workers, matching the PROJECT.md "Pending" decision. |
| `redis` (Python client, redis-py) | `>=5.0,<9.0` (current 8.0.1) | Python client required by the `limits` library's `RedisStorage` backend that `slowapi` delegates to | `slowapi` (already pinned `>=0.1.9,<1.0`, current 0.1.10) does not vendor its own Redis client — it is "just a wrapper around `limits`" and the Redis backend is entirely supplied by `pip install redis`. No slowapi version bump needed; this is purely an added dependency + a one-line `Limiter(storage_uri=...)` change. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `authlib` | already pinned `>=1.3,<2.0` (current 1.7.2 — compatible, no bump required) | OAuth 2.0/OIDC client for GitHub, Google, and the generic OIDC pattern reused for Apple | `authlib.integrations.starlette_client.OAuth` — this is the module the existing `api/app/auth/routes.py` already uses. No new dependency; this milestone's OAuth work is about completing provider-specific wiring, not adding new auth libraries. |
| `Mastodon.py` | `>=2.2,<3.0` (current 2.2.1) — **new dependency, not currently in STACK.md** | Wraps Mastodon's non-standard `POST /api/v1/apps` dynamic-app-registration endpoint plus the subsequent OAuth2 authorize/token exchange | Mastodon does **not** implement RFC 7591 Dynamic Client Registration. Every instance requires its own app registration call before OAuth can begin. `Mastodon.py` already implements this dance (`Mastodon.create_app()` + `Mastodon(...).auth_request_url()` / `.log_in()`) — hand-rolling it in `authlib` (which has no built-in per-instance app-registration primitive) is unnecessary extra work for a workflow this library already solves. Use it **only** for the Mastodon/ActivityPub path; keep GitHub/Google/Apple on `authlib` since those already work with it. |
| `PyJWT` | already pinned `>=2.8,<3.0` (current 2.13.0) | Generates the Apple "Sign in with Apple" client-secret JWT (ES256-signed, `iss`=team ID, `sub`=client ID, `aud`=`https://appleid.apple.com`, `kid`=key ID header) on every token exchange | Apple has no static `client_secret` — it must be a freshly (or periodically) minted, short-lived (max 6 months) signed JWT derived from the `.p8` private key. No new dependency: `PyJWT` + `cryptography` (already pinned, current 49.0.0) is sufficient; `authlib`'s generic JWT support could also do this but PyJWT is simpler for this one-off encode call and is already a direct dependency. |
| `cryptography` | already pinned (implied via authlib/PyJWT deps), current 49.0.0 | ES256 key loading for the Apple client-secret JWT | Needed to load the `APPLE_PRIVATE_KEY` (.p8, EC private key) for `jwt.encode(..., algorithm="ES256")`. |

### Development / Verification Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| A small corpus of real/decrypted BD & UHD ISOs or physical discs | Blu-ray/UHD fingerprint regression fixtures, mirroring the existing "20 known disc ISOs" DVD regression suite described in the technical spec | Cannot be faked with synthetic MPLS files alone for Tier 1 — AACS Disc ID requires an actual `Unit_Keys_RO.inf`, which only exists on real pressed/ripped discs with `libaacs` already applied. Budget for at least a handful of real BD + UHD discs in the test fixture set, same legal posture as the existing DVD fixtures (no disc images/keys committed to the public repo, per the existing "private S3 bucket" pattern). |
| `redis:8-alpine` (Docker) | Local dev/test Redis instance | Add as a new service in `docker-compose.yml` / `docker-compose.test.yml` alongside `db`; no auth needed for local dev, require `requirepass` (or Redis 6+ ACLs) in `docker-compose.prod.yml`. |

## Installation

```bash
# Blu-ray/UHD fingerprinting (system libraries — apt/brew, not pip)
# Debian/Ubuntu:
apt-get install libbluray-dev libaacs-dev libbluray-bdj

# macOS (Homebrew):
brew install libbluray libaacs

# Python wrapper
pip install bluread   # PyPI package name for PyBluRead; pin to a specific version, e.g. bluread==1.4

# Redis-backed rate limiting
pip install redis     # redis-py; slowapi itself needs no version bump (already >=0.1.9,<1.0)

# Mastodon OAuth (dynamic app registration + OAuth flow)
pip install Mastodon.py   # note capitalization on PyPI: "Mastodon.py"
```

```yaml
# docker-compose.yml addition
services:
  redis:
    image: redis:8-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "no"]
    ports:
      - "6379:6379"
```

```python
# api/app/rate_limit.py — Redis-backed Limiter
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
)
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| `bluread` (ctypes wrapper over `libbluray`) for both BD tiers | `pympls` (pure-Python MPLS-only parser) | Only as a reference/fallback for understanding the MPLS binary layout during development, or if `libbluray`'s system dependency proves too heavy for a constrained deployment target. **Do not** make it a runtime dependency — see "What NOT to Use." |
| Raw ctypes binding to `libdvdread.DVDDiscID()` (matching the existing OVID-DVD-1 IFO-reading approach) | A hypothetical `pydvdread`/`python-dvdread` PyPI package | These package names do not exist on PyPI as of this research (2026-07-05, confirmed via direct PyPI API query) — this is not a "prefer X over Y" choice, it's the only real option. If one appears later, evaluate it, but budget for ctypes as the default plan. |
| Redis via the synchronous `redis` package + `limits`' `RedisStorage` | `async+redis://` URI prefix (async storage in `limits>=4.3`) | Use the async variant only if/when the rate-limit check path is moved into a fully async request path; slowapi's dependency middleware currently works fine with the sync client since Redis round-trips are cheap and non-blocking relative to request handling. Revisit if p95 latency budget (500ms) gets tight under load testing. |
| `Mastodon.py` for the Mastodon/ActivityPub OAuth path specifically | Generic `authlib` OAuth2 client + hand-rolled `POST /api/v1/apps` call | If the team wants a single OAuth library across all four providers for consistency, hand-rolling the app-registration call in `authlib` is feasible (it's one `httpx` POST) — but `Mastodon.py` already does this correctly including caching client credentials per instance, so hand-rolling only saves one dependency at the cost of re-implementing tested logic. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pympls` as a production runtime dependency | Unmaintained since 2021-07-09 (confirmed via GitHub API: `pushed_at: 2021-07-09`) — 5 years stale as of this research. No CLPI (clip info) support at all, only MPLS. | `bluread`/`libbluray` ctypes binding, which covers both MPLS and CLPI and is actively maintained upstream (VideoLAN) even if the Python wrapper itself moves slowly. |
| Rolling a custom `.well-known/oauth-authorization-server` discovery flow as the *only* Mastodon integration path | Only Mastodon **4.3.0+** instances expose this discovery endpoint; a large fraction of the fediverse (older Mastodon, Pleroma, Akkoma, GoToSocial, Pixelfed) either doesn't implement it or implements a different app-registration contract. Discovery-only breaks OVID's stated goal of working "with any Mastodon-compatible software." | Always call `POST /api/v1/apps` directly (the de facto universal registration endpoint across the ActivityPub/Mastodon-API ecosystem) rather than gating on `.well-known` discovery; treat discovery as an optional enhancement, not the primary path. |
| Assuming `libdvdread`'s Disc ID (`dvdread1-*`) is a drop-in stability upgrade over OVID-DVD-1 | It is an MD5 **content hash of the raw IFO file bytes**, not a semantic/structural hash. It is therefore *more* sensitive than OVID-DVD-1 to any byte-level difference between rips of the same physical pressing (encoding quirks, minor IFO corruption, truncated reads) — the opposite of what "more stable" implies. | Keep `dvd1-*` as the resilient fallback exactly as ADR 0001 already stages it; treat `dvdread1-*` as an *additional, format-standard* identity string for cross-tool interoperability, not as evidence the structural hash should be retired. This confirms the ADR's cautious staged approach was the right call. |
| In-memory `slowapi` storage (current default) in any multi-worker/gunicorn deployment | Confirmed defect: counters are per-process, so `--workers 4` silently means the effective limit is 4x the configured value. This is exactly the "Pending" item flagged in PROJECT.md Key Decisions. | Redis-backed `storage_uri` as shown above — this is a required fix, not optional, before v0.2.0's "rate limiting and basic abuse prevention live" exit criterion can be honestly claimed. |
| Treating Apple's OAuth `client_secret` as a static, one-time-configured value (as it's stored for GitHub/Google in `.env`) | Apple's secret is a signed JWT with a maximum 6-month lifetime that must be regenerated (either per-request or on a rotation schedule) — storing a single static value in `APPLE_CLIENT_SECRET` and never touching it again will silently start failing after up to 6 months. | Generate the JWT at request time (cheap, no external call) from the already-configured `APPLE_PRIVATE_KEY`/`APPLE_KEY_ID`/`APPLE_TEAM_ID` env vars (all already present per `.env.example`) rather than trying to precompute and store it. |

## Stack Patterns by Variant

**If the AACS directory/`Unit_Keys_RO.inf` is unavailable (undecrypted disc, BD-R burn, non-AACS UHD):**
- Fall back to `bluread`'s playlist/clip enumeration for OVID-BD-2 (Tier 2 structure hash) exactly as the technical spec's `compute_fingerprint()` pseudocode already describes.
- Because `bluread` wraps the same `libbluray` library used for Tier 1, no second dependency is needed for the fallback path.

**If deploying a self-hosted "mirror" node (Topology B, standalone/mirror mode):**
- Redis is still required for correct rate limiting if the mirror runs multiple workers; document this in `docs/self-hosting.md` as a required service, not optional, once that guide is written for v0.3.0.

**If a Mastodon-compatible instance rejects `POST /api/v1/apps` (rare, but non-Mastodon ActivityPub servers vary):**
- Surface a clear, actionable error to the user ("this instance does not support the login flow OVID uses") rather than a generic 500 — this is a legitimate `medium`/`low`-confidence edge the two-contributor verification/moderation model does not need to solve, but the auth UX does.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `bluread` 1.4 | `libbluray` 1.4.x (system) | The wrapper's version number tracks the libbluray API version it targets; do not assume forward compatibility with `libbluray` 1.5+ without re-verifying the ctypes struct layout (`BLURAY_DISC_INFO`) hasn't changed field offsets. |
| `slowapi` 0.1.10 | `limits` (transitive dep, version unresolved from this pass — verify pinned range at implementation time) + `redis-py` 8.0.1 | `limits>=4.3` is required for the `async+redis://` URI form; the synchronous `redis://` form has been supported for longer and is the safer default given slowapi's synchronous middleware hook. |
| `PyJWT` 2.13.0 | `cryptography` 49.0.0 | Required for `algorithm="ES256"` support (elliptic-curve signing) used by the Apple client-secret JWT; both are already direct/transitive OVID dependencies, no version conflict expected. |
| `Mastodon.py` 2.2.1 | Standard `requests`-based sync HTTP (not `httpx`) | Note: `Mastodon.py` uses `requests` internally, not the `httpx` already standardized on elsewhere in OVID's API (`api/app/sync.py`). This introduces a second HTTP client dependency for one auth path — acceptable given `Mastodon.py`'s narrow, well-tested scope, but worth a one-line note in `docs/auth-setup.md` so it isn't mistaken for an inconsistency to "fix." |

## matrix256 — External Fingerprint Method (flagged for adoption assessment)

Source: [matrix256: a pressing-level disc fingerprint](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) (Substack, fetched 2026-07-05, confidence MEDIUM — single-author technical blog post, no independent corroboration found, but the described method is internally consistent and directly checkable).

**Method:** matrix256 hashes *only filesystem metadata* — for every regular file on the mounted disc filesystem: the relative path (NFC-normalized UTF-8, forward slashes) and the file size as reported by the filesystem. Records are sorted lexicographically by path, serialized as `path\0size\n`, concatenated, and SHA-256'd to a 64-hex-char digest. It explicitly does **not** hash file contents.

**How it achieves pressing-level (not just title-level) specificity:** it relies on the fact that a pressed optical disc's filesystem is physically read-only and bit-identical to what the mastering plant wrote — so any two pressings that differ (director's cut vs. theatrical, region variant, remaster) will almost always differ in at least one file's path or size, without needing to decrypt or parse any format-specific structure (IFO/MPLS/AACS). It needs zero DRM-adjacent libraries because file paths/sizes live in plaintext filesystem descriptors even under AACS/CSS encryption.

**Relationship to OVID's existing/planned fingerprints:**

| Fingerprint | Scope | What it captures | Requires |
|---|---|---|---|
| OVID-DVD-1 (`dvd1-*`) | DVD only | Semantic IFO fields: title/chapter/track counts, durations, languages | `pycdlib`/`libdvdread` IFO parse, no DRM lib |
| libdvdread Disc ID (`dvdread1-*`) | DVD only | MD5 of raw IFO file bytes | `libdvdread` |
| AACS Disc ID (`bd1-aacs-*`/`uhd1-aacs-*`) | Commercial AACS-protected BD/UHD only | SHA-1 of `Unit_Keys_RO.inf` | `libaacs` (decryption-adjacent, absent on BD-R/camcorder/console discs) |
| OVID-BD-2 (`bd2-*`/`uhd2-*`) | BD/UHD | Semantic MPLS/CLPI fields | `libbluray`, no DRM lib |
| **matrix256** | **DVD, HD-DVD, BD, UHD, VideoCD — one algorithm, format-agnostic** | Whole-disc file listing (paths + sizes only) | **Nothing** — plain filesystem mount, no format-specific parser, no DRM lib |

**Assessment — worth adopting, as an addition, not a replacement:** matrix256 is strictly coarser-grained than OVID's existing tiered fingerprints (it cannot tell you title/chapter/track structure — only "is this the same pressing"), but it has three properties none of OVID's current fingerprints share simultaneously: (1) zero DRM library dependency at all (works even where `libaacs`/`libbluray`/`libdvdread` are entirely absent), (2) one format-agnostic algorithm across every disc type OVID supports plus HD-DVD/VideoCD, and (3) trivially cheap to compute (a directory walk + `stat()`, no format parsing). Recommend adding it as a **fifth alias fingerprint type feeding the ADR 0001 alias/lookup-alias model** — it costs almost nothing to compute alongside the existing tiers, gives OVID a fallback identity signal even on discs where `ovid-client` can't read format-specific structure (e.g., damaged/foreign IFO, BD without AACS applied), and its stated limitations (not tamper-proof, not a content hash, dual-filesystem ambiguity on ISO9660/UDF hybrid discs) are acceptable for a "which pressing is this" alias signal rather than the primary identity string. Do **not** use it to replace `dvd1-*`, `dvdread1-*`, `bd1-aacs-*`, or `bd2-*` — those remain necessary for the structure/metadata OVID actually needs to serve (main-feature detection, chapter/track data), which matrix256 cannot provide.

## Sources

- PyPI JSON API (direct queries, 2026-07-05) — `authlib` 1.7.2, `slowapi` 0.1.10, `redis` 8.0.1, `PyJWT` 2.13.0, `Mastodon.py` 2.2.1, `cryptography` 49.0.0, `pycdlib` 1.16.0, `itsdangerous` 2.2.0, `httpx` 0.28.1, `bluread` 1.4, `pympls` 0.0.1 — HIGH confidence (primary registry source)
- GitHub API (direct queries, 2026-07-05) — `rlaphoenix/pympls` last push 2021-07-09 (unmaintained), `cmlburnett/PyBluRead` last push 2024-07-12 (maintained) — HIGH confidence (primary source)
- GitLab (`code.videolan.org`) API (direct queries, 2026-07-05) — `libbluray` latest tag 1.4.1, `libaacs` latest tag 0.11.1 — HIGH confidence (primary source, VideoLAN canonical repo)
- Context7 `/authlib/authlib` — Starlette/FastAPI OAuth registration and callback pattern — MEDIUM confidence (official docs via Context7, cross-checked against existing `api/app/auth/routes.py` usage pattern)
- WebSearch: libaacs/libbluray AACS Disc ID exposure, Python BD bindings landscape, libdvdread `DVDDiscID`/CRC64 semantics, slowapi Redis backend, Sign in with Apple client-secret JWT pattern, Mastodon OAuth dynamic registration — MEDIUM confidence (aggregated web search, cross-checked against PyPI/GitHub/GitLab primary data where version/maintenance claims were checkable)
- `limits` library docs (`limits.readthedocs.io`, fetched via WebFetch) — Redis `storage_uri` format, `RedisStorage` class, async prefix — MEDIUM confidence (official docs, single-fetch, not independently cross-checked against source)
- [matrix256: a pressing-level disc fingerprint](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) (fetched via WebFetch, 2026-07-05) — MEDIUM confidence (single-author blog, method is internally consistent and independently checkable but not corroborated by a second source)
- `docs/OVID-technical-spec.md` §2.2, §6, §2.4 (existing project spec) — baseline fingerprint-tier design and licensing table this research extends, not re-verified as "current 2026" since it is the project's own authored spec

---
*Stack research for: OVID v0.2.0 — Blu-ray/UHD fingerprinting, libdvdread Disc ID, Redis rate limiting, four-provider OAuth*
*Researched: 2026-07-05*
