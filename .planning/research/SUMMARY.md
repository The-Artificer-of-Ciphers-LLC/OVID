# Project Research Summary

**Project:** OVID — Open Video Disc Identification Database
**Domain:** Community-curated physical-media identification service (MusicBrainz/Redump-adjacent structural fingerprinting) — subsequent-milestone research for v0.2.0 remaining scope
**Researched:** 2026-07-05
**Confidence:** MEDIUM-HIGH overall

## Executive Summary

OVID's remaining v0.2.0 work is not greenfield — direct code reading (ARCHITECTURE.md) shows the hardest part, the format-agnostic Lookup Alias storage/resolution layer, is already built and already string-generic (`resolve_existing_disc_for_identities` / `attach_lookup_aliases` never inspect fingerprint format). This changes the shape of the remaining milestone: Blu-ray/UHD fingerprinting and even the speculative matrix256 method are additive alias producers requiring **zero API/schema change**, not new subsystems. What remains is (1) client-side computation for Blu-ray/UHD (Tier 1 AACS + Tier 2 BDMV, mirroring the DVD pattern), (2) closing real correctness gaps in the existing alias/verification code, and (3) finishing four-provider OAuth and Redis-backed rate limiting.

The recommended approach is disciplined sequencing, not new architecture: fix the alias write-path race condition and consolidate the three scattered verification-transition code paths into one state machine **before** ADR 0001 Phase 3 (`dvdread1-*` promotion) increases write concurrency on the same fingerprint namespace. Stack picks are narrow and mostly additive to the existing baseline — `bluread` (ctypes over `libbluray`/`libaacs`) covers both BD tiers in one dependency, `redis` fixes a documented multi-worker rate-limit defect, and `Mastodon.py` handles Mastodon's non-standard per-instance app registration (existing `authlib` stays for GitHub/Google/Apple).

The key risks are security- and trust-model risks, not technical-feasibility risks: silent email-merge is a documented CVE-class account-takeover pattern (nOAuth) if provider `email_verified` claims aren't checked per-provider and Mastodon email is trusted at all; two-contributor verification is a Sybil target by construction since "confirmation" today is just a distinct `user_id`, not proof of physical disc possession; Mastodon instance discovery is an SSRF surface if the user-supplied instance hostname isn't validated against internal/reserved IP ranges. All three must be treated as hard product/security constraints carried into requirements, not implementation details to harden later. matrix256 (external pressing-level fingerprint concept) is assessed as a legitimate future addition — a fifth alias-fingerprint type — but single-source (MEDIUM confidence) and explicitly out of v0.2.0 scope; do not let it expand this milestone.

## Key Findings

### Recommended Stack

New-for-this-milestone technologies are narrow, mostly system libraries plus thin Python wrappers, and deliberately do not touch the existing Python 3.12/FastAPI/PostgreSQL 16/Next.js 16 baseline.

**Core technologies:**
- `bluread` (PyPI, 1.4, wraps `libbluray` 1.4.1 + `libaacs` 0.11.1 via ctypes) — covers both AACS Disc ID (Tier 1) and BDMV/playlist enumeration (Tier 2) through one dependency; actively maintained (last push 2024-07-12); **ships no LICENSE file despite wrapping GPL/LGPL code — flag for legal review, pin to a specific version**.
- `libdvdread`'s `DVDDiscID()` — already present, no new dependency, but is an **MD5 content hash of raw IFO bytes**, not a semantic hash — more sensitive to byte-level rip differences than OVID-DVD-1, confirming ADR 0001's cautious staging (not a "more stable" drop-in replacement).
- `redis` (server 8.x + redis-py client) — fixes the documented defect where `slowapi`'s in-memory storage keeps per-gunicorn-worker counters, silently multiplying the effective rate limit by worker count. One-line `Limiter(storage_uri=...)` change; no `slowapi` version bump needed.
- `Mastodon.py` (2.2.1, new dependency) — Mastodon does not implement RFC 7591 Dynamic Client Registration; every instance needs its own `POST /api/v1/apps` call before OAuth. Use `Mastodon.py` for this path only; keep `authlib` for GitHub/Google/Apple.
- `PyJWT` (already pinned) + `cryptography` (already pinned) — generates Apple's ES256-signed client-secret JWT at request time from `.p8` key material; Apple has no static client secret.

**What NOT to use:** `pympls` (unmaintained since 2021, no CLPI support); a `.well-known` discovery-only Mastodon path (only 4.3.0+ instances support it — breaks the "any Mastodon-compatible software" goal); treating Apple's client secret as a static one-time value (max 6-month JWT lifetime, silently expires).

### Expected Features

**Must have (table stakes) — v0.2.0 launch:**
- Two-contributor verification (unverified → verified), with **distinct-contributor enforcement** (never self-verify) — the core trust primitive of every comparable community DB (Redump, MusicBrainz).
- Lookup Alias resolution (ADR 0001 Phase 2) exposed through lookup and submission — already the most architecturally significant item, and it **blocks** Phase 3 promotion.
- Multi-provider linked accounts: settings-page add/remove, server-enforced minimum-one-remaining login method.
- Email-match merge offer, **confirm-required, never silent** — directly promised in PRD, with the confirm-required constraint added as a hard security guardrail by this research.
- Blu-ray Tier 1 (AACS Disc ID) + Tier 2 (BDMV/PLAYLIST structure), Tier 1 preferred / Tier 2 fallback.
- Format/tier disambiguation (DVD/BD/UHD, tier used) in the disc record.

**Should have (competitive differentiators, add after v0.2.0 validation):**
- Pressing-level identity surfaced explicitly in Web UI ("N known identity strings map to this pressing").
- Cross-identity-method corroboration as its own verification signal (agreement across `dvd1-*`/`dvdread1-*` or Tier1/Tier2 is a stronger correctness signal than same-method resubmission).
- Contributor-facing "needs verification" queue/filter.

**Defer (explicitly out of v0.2.0, confirmed correct to defer):**
- Community edit-voting (MusicBrainz-style) — PRD defers to v0.4.0.
- Contributor-initiated alias/dispute merge UX beyond system-detected matches.
- UPC barcode cross-referencing.
- **matrix256 as a shipped fingerprint** — assess only, defer implementation past v0.2.0.

**Anti-features to explicitly reject:** self-verification; fully automatic email-merge with no confirmation; unlinking down to zero login methods; automatic pressing-merge from fuzzy structural similarity.

### Architecture Approach

The existing codebase already establishes the extension pattern the remaining work must follow: every identity method (DVD structural hash, libdvdread Disc ID, and future AACS/BDMV/matrix256) produces the same `DiscIdentity(fingerprint, method, fingerprint_version)` shape, collected into one `DiscIdentitySet(primary, aliases[], diagnostics[])`. The server (`api/app/disc_identity.py`) never inspects `method` or format — it only ever sees a primary string plus alias strings. This is the single most important finding for roadmap sequencing: **the hard part (alias storage/resolution) is done; remaining work is client-side computation and closing edge cases, not a new subsystem.**

**Major components (remaining work only):**
1. `ovid-client/src/ovid/bd_identity.py` (new) — mirrors `disc_identity.py`'s pattern for Blu-ray/UHD; must compute Tier 1 **and** attempt Tier 2 whenever playlists survive filtering (today's `bd_disc.py` `_build()` returns immediately on Tier 1 success, so the two tiers can never coexist as alias pairs — this must be fixed).
2. `api/app/models.py` `DiscIdentityAlias` uniqueness gap — the check-then-insert in `attach_lookup_aliases` is correct in a single transaction but **not race-safe across gunicorn workers** submitting the same disc concurrently. Fix via `SELECT ... FOR UPDATE` (lower-risk) before increasing write concurrency in Phase 3.
3. `api/app/verification.py` (new) — consolidates the `unverified → verified → disputed` state machine currently scattered across `submit_disc()`, `verify_disc()`, and `resolve_dispute()` in `routes/disc.py`. Closes a real correctness gap: today a third submitter's conflicting metadata against an **already-verified** disc can flip it back to `disputed` without moderation.
4. `api/app/schemas.py` `DiscLookupResponse` — add `fingerprint_aliases: list[str]` so callers can see all known identity strings for a pressing (relationship already exists server-side, just not exposed).
5. `api/app/rate_limit.py` → Redis-backed `storage_uri`, orthogonal to the identity/verification work.

### Critical Pitfalls

1. **BDMV obfuscation-playlist instability** — studios ship 800+ decoy `.mpls` files; any change to the filter threshold/sort/tie-break silently changes every issued `bd2-*`/`uhd2-*` fingerprint DB-wide. Freeze the algorithm as a versioned spec the moment it ships (mirrors the `dvd1-`→`dvdread1-` lesson); test against real obfuscation-heavy discs, not just clean fixtures.
2. **AACS Tier 1 assumed pressing-unique without verified evidence** — regional/reprint MKB-renewal behavior is unvalidated (LOW confidence, open question). Model Tier 1 collisions the same way as `dvd1-*` collisions: surface to dispute workflow, never silently merge or split.
3. **Tier selection silently downgrades confidence without recording why** — whether `libaacs` succeeds depends on the *contributor's environment* (keys present or not), not the disc. Two contributors on different machines can produce Tier 1 vs. Tier 2 for the same physical disc and never match — verification must check for a match on **either** tier before declaring "unverified." Build this on the same shared alias-resolution path as ADR 0001, not a parallel mechanism.
4. **Migration Phase 2/3 fragments `dvd1-*` despite ADR 0001's explicit intent** — the classic expand/contract failure: new endpoints/tests/docs quietly written against `dvdread1-*` only. Requires a **permanent CI regression test** ("`dvd1-*` still resolves correctly") from Phase 1 onward, not a one-time migration check.
5. **Email-merge account takeover (nOAuth-class)** — merge-eligibility must check each provider's actual verified-email API field independently (GitHub `/user/emails` `email_verified`, Google ID-token `email_verified`, Apple relay-verified emails); **Mastodon email should probably never be trusted for merge at all** (federated, no uniform verification standard). The existing-account re-auth gate must be enforced server-side before any linking write, with isolated tests for `finalize_auth` (currently has none).
6. **Two-contributor verification is a Sybil target by construction** — "distinct `user_id`" alone is not proof of independent physical disc possession. Requires account-age/IP-diversity weighting, per-account confirmation rate limits, and withholding full pre-verification structural payload from public reads (so a sockpuppet can't "confirm" without ever touching the disc).

## Implications for Roadmap

Based on combined research, especially the architecture finding that alias storage is already built and format-agnostic, the roadmap should sequence around **closing correctness gaps before increasing write concurrency**, not around new subsystem construction.

### Phase 1: Alias-Layer Hardening (pre-Phase-3 gate)
**Rationale:** ADR 0001 Phase 3 (`dvdread1-*` promotion) increases write concurrency on the same fingerprint namespace; any unresolved race or scattered verification logic will corrupt the `dvd1-*` stability guarantee ADR 0001 exists to protect. Architecture research explicitly flags this as the required build order.
**Delivers:** `SELECT ... FOR UPDATE` (or equivalent) fix for the `DiscIdentityAlias` write-path race; `fingerprint_aliases` exposed in `DiscLookupResponse`; consolidated `api/app/verification.py` state machine (verified/disputed made sticky against non-privileged callers); permanent CI regression test asserting `dvd1-*` lookups still 200 with correct data.
**Addresses:** Lookup Alias resolution table-stakes feature; two-contributor verification correctness.
**Avoids:** Pitfall 4 (migration fragmentation), Pitfall 3 (tier-selection confidence gap — verification checking either tier), the verification-regression anti-pattern (Pattern 3/Anti-Pattern 3).

### Phase 2: Redis-Backed Rate Limiting
**Rationale:** Zero dependency on anything else in this milestone (architecture research: "do first or in parallel"); fixes an already-documented multi-worker scaling defect blocking an honest "rate limiting live" exit criterion.
**Delivers:** `redis` service in compose files, `Limiter(storage_uri=REDIS_URL)`, explicit fail-open/fail-closed decision, Compose health-gate (`depends_on: redis: condition: service_healthy`), p95 load test re-run **against the Redis-backed config**.
**Uses:** `redis` 8.x + redis-py, existing `slowapi`/`limits` (no version bump).
**Implements:** `api/app/rate_limit.py` component.

### Phase 3: Blu-ray/UHD Tier 1 + Tier 2 Fingerprinting
**Rationale:** Independent of the DVD migration entirely (different fingerprint namespace, same mechanism); benefits from Phase 1's alias visibility for verification during development, per the architecture build order.
**Delivers:** `ovid-client/src/ovid/bd_identity.py` computing Tier 1 (AACS) **and** attempting Tier 2 (BDMV structure) whenever both are computable, returned as one `DiscIdentitySet`; format/tier disambiguation in the disc record; fixture corpus including at least one heavily-obfuscated real disc.
**Addresses:** Blu-ray Tier 1/Tier 2 table-stakes features; format field disambiguation.
**Avoids:** Pitfall 1 (obfuscation-playlist instability — freeze filter/sort as versioned spec), Pitfall 2 (AACS regional-variance — route Tier 1 mismatches to dispute, not silent merge/split).

### Phase 4: ADR 0001 Phase 3 — `dvdread1-*` Promotion
**Rationale:** Highest-risk item in remaining scope; only safe once Phase 1's write-path race fix and verification consolidation have landed and soaked. This is a hard sequencing dependency, not a preference.
**Delivers:** Migration that only promotes discs with an already-recorded `dvdread1-*` alias, swaps `Disc.fingerprint`/`DiscIdentityAlias.fingerprint` inside one transaction per disc, and leaves discs with no `dvdread1-*` alias permanently on `dvd1-*`.
**Uses:** Phase 1's alias-resolution hardening as a prerequisite.
**Avoids:** Pitfall 4 (fragmentation) — isolate as its own plan with dry-run/rollback path per architecture Anti-Pattern 2 (do not bundle with unrelated schema cleanup like a `disc_identities` table unification).

### Phase 5: OAuth Completion (GitHub, Google, Apple, Mastodon)
**Rationale:** Independent of the identity-migration work; can run in parallel with Phases 1–4, but is the most security-sensitive remaining strand and deserves isolated planning/testing.
**Delivers:** All four providers working end-to-end; isolated `finalize_auth` tests (verified-merge success, unverified-merge rejection, merge-without-reauth rejection); per-provider verified-email field checks (never trusting Mastodon email for merge); Mastodon SSRF validation (reject reserved/internal IP ranges, no redirect-following, no raw-response reflection) shipped with the initial instance-discovery implementation; Apple client-secret JWT rotation automated (well inside the 6-month ceiling) with expiry monitoring; startup assertion refusing to boot with `allow_localhost=True` alongside a production indicator.
**Addresses:** Linked accounts, email-match merge offer table-stakes features.
**Avoids:** Pitfall 5 (email-merge takeover), Pitfall 6 (Apple secret expiry), Pitfall 7 (Mastodon SSRF), Pitfall 8 (IndieAuth localhost bypass via config drift).

### Phase 6: Two-Contributor Verification Anti-Sybil Hardening
**Rationale:** The baseline verification model (Phase 1) must be abuse-resistant enough to survive without the explicitly-deferred v0.3.0 dispute-flagging UI. This is a v0.2.0 exit-criterion requirement, not optional polish.
**Delivers:** Account-age/IP-diversity weighting on confirmations; per-account confirmation rate limits (not just submission rate limits); full structural payload withheld from public reads until `verified`.
**Addresses:** Two-contributor verification workflow, "verification workflow live" exit criterion.
**Avoids:** Pitfall 9 (Sybil/sockpuppet verification abuse).

### Phase Ordering Rationale

- Alias-layer hardening (Phase 1) must precede Phase 3/4-BD-and-migration work because it is a shared prerequisite for both: it makes cross-tier BD verification possible (Pitfall 3) and makes the highest-risk migration (Phase 4) safe.
- OAuth (Phase 5) and rate limiting (Phase 2) are architecturally orthogonal to the identity/verification spine and can be sequenced in parallel by team capacity, not blocked by it.
- The `dvdread1-*` promotion (Phase 4) is deliberately placed last among identity work — it is explicitly the highest-risk item and should not be rushed ahead of its prerequisites for schedule convenience.
- matrix256 is deliberately excluded from all phases above — per STACK.md/ARCHITECTURE.md, it requires no schema change and can be added as a peer alias producer in a later milestone without disturbing this sequencing.

### Research Flags

Needs deeper research during phase planning:
- **Blu-ray/UHD fingerprinting phase:** AACS regional/reprint variance is LOW confidence and unresolved — budget a phase-level research spike using real BD/UHD fixture discs to empirically test whether same-title reprints/regions share `Unit_Keys_RO.inf`.
- **OAuth completion phase (Mastodon sub-strand):** whether Mastodon (or IndieAuth) ever asserts a verified email at all is unconfirmed — needs a targeted check against Mastodon's actual OAuth token response before deciding whether Mastodon participates in email-merge at all.
- **Alias-layer hardening phase:** the `SELECT FOR UPDATE` vs. unified `disc_identities` table decision needs a short design spike — architecture research recommends the row-lock approach as lower-risk for v0.2.0 but flags the unified-table option as architecturally cleaner for later.
- **Stack/legal:** `bluread`'s missing LICENSE file needs a legal review before shipping as a runtime dependency; this is a blocking flag, not a research question, but should be resolved early in the Blu-ray phase.

Phases with standard, well-documented patterns (skip research-phase):
- **Redis-backed rate limiting:** `slowapi`'s Redis backend is a documented config-only change; the operational gaps (fail-open/closed, health-gating) are known patterns to apply, not open questions.
- **Verification state-machine consolidation:** follows the already-established `disc_identity.py` service-layer convention in the codebase; this is a refactor of existing, understood logic.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Library/version facts verified directly against PyPI/GitHub/GitLab APIs (HIGH); behavioral/gotcha claims (e.g. AACS exposure details, Redis async semantics) sourced from aggregated web search (MEDIUM) |
| Features | HIGH | Verification/linked-account patterns cross-checked against MusicBrainz and Redump official docs plus multiple vendor OAuth-linking guides; pressing-level alias UX is MEDIUM (single-source article, no prior community DB has shipped this exact concept) |
| Architecture | HIGH | Grounded in direct reading of current source (`disc_identity.py`, `models.py`, `routes/disc.py`, etc.), the ADR, and the technical spec; matrix256 architectural fit assessment is MEDIUM (single external blog-post source) |
| Pitfalls | MEDIUM-HIGH | Project-specific reasoning (grounded in ADR/spec/CONCERNS.md) is HIGH; external security claims (nOAuth, GHSA-6g38-8j4p-j3pr) are named CVE/vendor sources (HIGH); AACS regional-variant specifics are explicitly LOW confidence and flagged as an open question |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **AACS regional/reprint Disc ID stability** (LOW confidence) — must be validated empirically during Blu-ray fixture collection; treat as an open product question, not a settled fact, when designing Tier 1 collision handling.
- **Mastodon/IndieAuth verified-email assertion** — unconfirmed whether these providers assert verified email at all; resolve before finalizing the email-merge phase's provider-adapter design, and default to excluding Mastodon from merge-eligibility until confirmed otherwise.
- **`bluread` PyPI package's missing LICENSE file** — legal flag, not a technical gap; resolve before the Blu-ray phase ships to production.
- **`SELECT FOR UPDATE` vs. unified `disc_identities` table** for the alias-uniqueness race fix — a real design decision with a recommended default (row-lock) but not yet made; surface as a phase-level decision point.
- **matrix256 stability/collision behavior at OVID's scale** — no production validation exists anywhere (single-author blog post, 69-disc evaluation corpus); if pursued in a future milestone, stage it through the same Phase 1→2→3 alias-introduction pattern ADR 0001 already established, never fast-tracked to primary.

## Sources

### Primary (HIGH confidence)
- Direct source reads: `api/app/disc_identity.py`, `models.py`, `schemas.py`, `routes/disc.py`, `rate_limit.py`, `ovid-client/src/ovid/disc_identity.py`, `bd_disc.py`, `disc.py`, `cli.py`, `docker-compose.yml`
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`, `docs/OVID-technical-spec.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONCERNS.md`, `.planning/PROJECT.md`
- PyPI/GitHub/GitLab APIs (direct queries, 2026-07-05) — `bluread` 1.4, `libbluray` 1.4.1, `libaacs` 0.11.1, `authlib` 1.7.2, `slowapi` 0.1.10, `redis` 8.0.1, `PyJWT` 2.13.0, `Mastodon.py` 2.2.1, `pympls` unmaintained since 2021-07-09
- [Nhost OAuth Account Takeover — GHSA-6g38-8j4p-j3pr](https://github.com/advisories/GHSA-6g38-8j4p-j3pr) — GitHub Security Advisory
- [Introduction to Voting / How Editing Works — MusicBrainz](https://musicbrainz.org/doc/Introduction_to_Voting), [Redump Wiki](http://wiki.redump.org/)

### Secondary (MEDIUM confidence)
- [nOAuth — Descope](https://www.descope.com/blog/post/noauth), [Saying No Thanks to nOAuth — Okta Security](https://sec.okta.com/articles/2023/08/saying-no-thanks-noauth/)
- [Account linking — Clerk Docs](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking), [Secure account linking — Ory](https://www.ory.com/blog/secure-account-linking-iam-sso-oidc-saml)
- [slowapi Redis multi-worker issue #226](https://github.com/laurentS/slowapi/issues/226)
- [Mastodon OAuth documentation](https://docs.joinmastodon.org/spec/oauth/), [RFC 8414 support — mastodon/mastodon issue #24099](https://github.com/mastodon/mastodon/issues/24099)
- [Apple client secrets expiry — better-auth issue #1522](https://github.com/better-auth/better-auth/issues/1522), [ES256 signature encoding — Apple Developer Forums](https://developer.apple.com/forums/thread/123723)

### Tertiary (LOW confidence)
- [matrix256: A Pressing-Level Disc Fingerprint (Substack)](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) — single-author, no independent corroboration; treated as directionally useful, not authoritative
- AACS regional/MKB-renewal specifics — general AACS documentation confirms MKB renewal exists ecosystem-wide, but no source confirms/denies same-Unit-Keys-file-across-regions behavior specifically

---
*Research completed: 2026-07-05*
*Ready for roadmap: yes*
