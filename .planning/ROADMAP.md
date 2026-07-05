# Roadmap: OVID — v0.2.0 (MVP) Completion

## Overview

OVID's v0.1.0 core (DVD structural fingerprinting, lookup/submission API, PostgreSQL schema, `ovid-client`) has already shipped, and the alias-storage/resolution layer for ADR 0001's staged libdvdread migration is already built and format-agnostic. This milestone closes the remaining v0.2.0 gaps in four largely-parallel strands — disc-identity correctness and the `dvdread1-*` promotion, Blu-ray/UHD fingerprinting, OAuth/account linking, and the web UI — then converges on rate limiting, verification hardening, and a final launch-readiness phase (ARM upstream review, ≥500-entry seeding, DNS redirects, remaining docs, and the public announcement). Phase order honors one hard rule: the alias write-path race fix and verification-consolidation (Phase 1) must land and soak before `dvdread1-*` promotion (Phase 5) increases write concurrency on the same fingerprint namespace, since a race there would corrupt the `dvd1-*` stability guarantee ADR 0001 exists to protect.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Alias-Layer Hardening & Repo Hygiene** - Close the alias write-path race and verification-consolidation gaps that must land before promotion; clean up ad-hoc repo cruft
- [ ] **Phase 2: Two-Contributor Verification Workflow** - Make the two-contributor trust model live and resistant to cheap Sybil abuse
- [ ] **Phase 3: Redis-Backed Rate Limiting & Performance** - Fix multi-worker rate-limit scaling and validate the p95 latency budget against the real deployment config
- [ ] **Phase 4: Blu-ray/UHD Fingerprinting** - Bring BD/UHD discs to fingerprinting parity with the DVD path (Tier 1 AACS + Tier 2 BDMV, coexisting as an alias pair)
- [ ] **Phase 5: ADR 0001 Completion — dvdread1-* Promotion** - Complete alias submission and promote `dvdread1-*` to the primary DVD fingerprint, keeping `dvd1-*` a permanent alias
- [ ] **Phase 6: OAuth & Account Linking** - All four OAuth providers working end-to-end with secure, confirm-gated account linking
- [ ] **Phase 7: Web UI Production Readiness** - Search, disc detail, submission, and account settings live at oviddb.org
- [ ] **Phase 8: Launch Readiness — ARM, Seeding & Announcement** - ARM upstream review, ≥500-entry seeding, DNS redirects, remaining docs, and the public announcement

## Phase Details

### Phase 1: Alias-Layer Hardening & Repo Hygiene

**Goal**: Close the alias write-path and verification correctness gaps — and clean up ad-hoc repo cruft — so the codebase is safe to build BD fingerprinting, `dvdread1-*` promotion, and OAuth linking on top of.
**Depends on**: Nothing (first phase; extends the already-shipped ADR 0001 Phase 1 fallback and Phase 2 alias modeling)
**Requirements**: IDENT-01, IDENT-02, IDENT-05, VERIFY-02, CLEAN-01, CLEAN-02
**Success Criteria** (what must be TRUE):

  1. Concurrent disc submissions from multiple gunicorn workers for the same physical disc never create duplicate or split disc rows — the alias check-then-insert write path is race-safe under load (IDENT-02 [guardrail]).
  2. `GET /v1/disc/{fingerprint}` returns every known `fingerprint_aliases` string for a pressing, so callers can see all identities that resolve to one disc (IDENT-01).
  3. A permanent CI regression test proves an existing `dvd1-*` fingerprint still resolves to its disc with correct data after every change to disc-lookup/submission code, and keeps running on every future PR (IDENT-05 [guardrail]).
  4. Verification status transitions (`unverified → verified → disputed`) run through one guarded service module (`api/app/verification.py`); an already-verified disc cannot be silently flipped to `disputed` by a later mismatched submission outside the explicit dispute-resolution path (VERIFY-02).
  5. The repo root contains none of the ad-hoc debug scripts (`fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py`), and UAT artifacts (`uat_results.json`, `uat_dirs/`) are gitignored (CLEAN-01, CLEAN-02).

**Plans**: 2/6 plans executed
**Wave 1**

- [x] 01-01-PLAN.md — verification.py guarded state machine (VERIFY-02) [Wave 1, tdd]
- [x] 01-02-PLAN.md — race-safe alias insert in disc_identity.py (IDENT-02) [Wave 1, tdd]
- [ ] 01-05-PLAN.md — permanent dvd1-* anti-fragmentation regression test (IDENT-05) [Wave 1]
- [ ] 01-06-PLAN.md — repo hygiene: remove root scripts, untrack + gitignore UAT artifacts (CLEAN-01, CLEAN-02) [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-03-PLAN.md — wire verification into routes + disc-row race safety + behavior-change tests (VERIFY-02, IDENT-02) [Wave 2, depends 01-01/01-02]

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-04-PLAN.md — expose fingerprint_aliases on the lookup response (IDENT-01) [Wave 3, depends 01-03]

### Phase 2: Two-Contributor Verification Workflow

**Goal**: The two-contributor trust model is live end-to-end and resistant to cheap Sybil abuse, without relying on the deferred v0.3.0 dispute-flagging UI.
**Depends on**: Phase 1 (uses the consolidated `verification.py` state machine)
**Requirements**: VERIFY-01, VERIFY-03, VERIFY-04
**Success Criteria** (what must be TRUE):

  1. A submitted disc entry stays `unverified` until a second, distinct contributor independently confirms the fingerprint; self-confirmation by the original submitter is rejected (VERIFY-01).
  2. An already-`verified` disc cannot be flipped back to `disputed`/`unverified` by a later third submission — only the explicit dispute-resolution path can move it (VERIFY-03 [guardrail]).
  3. Confirmation actions are rate-limited per account and weighted by account-age/IP-diversity signals; a merely-distinct `user_id` is not by itself accepted as proof of independent physical possession (VERIFY-04 [guardrail]).
  4. The full submitted structural payload of an `unverified` disc is withheld from public reads until verification, so a sockpuppet cannot "confirm" without independently computing the fingerprint from a physical disc.

**Plans**: TBD

### Phase 3: Redis-Backed Rate Limiting & Performance

**Goal**: Rate limiting is correct under the real multi-worker gunicorn deployment, and the API meets its latency budget under that same configuration.
**Depends on**: Nothing (independent of the identity/verification work; parallel-safe)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):

  1. Rate limits are enforced correctly across all gunicorn workers via Redis-backed `slowapi` storage — no more Nx effective-limit inflation from in-process counters (INFRA-01).
  2. Fail-open vs. fail-closed behavior when Redis is unreachable is an explicit, documented, and tested decision — not an unconsidered default (INFRA-02 [guardrail]).
  3. A load test run against the actual Redis-backed, multi-worker gunicorn configuration shows API p95 latency ≤500ms (INFRA-03).
  4. Submission and confirmation actions are throttled per account as basic abuse prevention, live in production (INFRA-04).

**Plans**: TBD

### Phase 4: Blu-ray/UHD Fingerprinting

**Goal**: Blu-ray and 4K UHD discs reach fingerprinting parity with the DVD path — Tier 1 (AACS) and Tier 2 (BDMV structure), coexisting as an alias pair, backed by real fixtures and a versioned spec.
**Depends on**: Nothing (independent fingerprint namespace from the DVD migration; parallel-safe)
**Requirements**: FPRINT-01, FPRINT-02, FPRINT-03, FPRINT-04, FPRINT-05, FPRINT-06, FPRINT-07, DOCS-01
**Success Criteria** (what must be TRUE):

  1. `ovid-client` computes a Blu-ray Tier 1 fingerprint from the AACS Disc ID (`bd1-aacs-*`) and a Tier 2 fingerprint from BDMV/PLAYLIST/CLIP structure (`bd2-*`) (FPRINT-01, FPRINT-02).
  2. When both tiers are computable, the client returns both in one `DiscIdentitySet` as an alias pair rather than short-circuiting on Tier 1 success (FPRINT-03).
  3. 4K UHD discs are fingerprinted via the same tiered path, with format recorded on the disc record (FPRINT-04).
  4. The same disc produces identical BD/UHD fingerprints across at least 2 drives and both Linux and macOS, verified by a determinism regression test (FPRINT-05).
  5. Tier 2 playlist filter/sort/tie-break constants are frozen as a versioned part of the fingerprint spec — never tuned as loose implementation values — defending against studio obfuscation-playlist decoys (FPRINT-06 [guardrail]).
  6. A real BD/UHD fixture corpus, including at least one heavily-obfuscated disc, backs the regression suite, and the fingerprint spec is updated with OVID-BD-2 Tier 1 & Tier 2 in `docs/fingerprint-spec.md` (FPRINT-07, DOCS-01).

**Plans**: TBD

### Phase 5: ADR 0001 Completion — dvdread1-* Promotion

**Goal**: The staged libdvdread migration finishes — clients submit every known Disc Identity string, and `dvdread1-*` becomes the primary DVD fingerprint while `dvd1-*` remains a stable, permanently resolvable alias.
**Depends on**: Phase 1 (alias write-path race fix and verification consolidation must land first — promotion increases write concurrency on the same fingerprint namespace), Phase 4 (BD tier identity strings are part of what a full submission now includes)
**Requirements**: IDENT-03, IDENT-04
**Success Criteria** (what must be TRUE):

  1. `ovid-client` submits every known Disc Identity string for a disc (`dvd1-*`, `dvdread1-*`, and/or BD tiers) on submission, and the API stores the non-primary strings as aliases — ADR 0001 Phase 2 is genuinely complete end-to-end (IDENT-03).
  2. New DVD submissions and lookups show `dvdread1-*` as the primary fingerprint; every disc that already has a recorded `dvdread1-*` alias is promoted in one transaction per disc, and any disc without one stays permanently on `dvd1-*` (IDENT-04).
  3. `dvd1-*` fingerprints from before the migration still resolve correctly after promotion — the Phase 1 CI regression test (IDENT-05) continues to pass with zero fragmentation.

**Plans**: TBD

### Phase 6: OAuth & Account Linking

**Goal**: All four OAuth providers work end-to-end, with linked-account management and email-merge that is secure by construction against nOAuth-class takeover, SSRF, and config-drift bypass.
**Depends on**: Nothing (orthogonal to the identity/verification/rate-limiting work; parallel-safe)
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09, AUTH-10, DOCS-03
**Success Criteria** (what must be TRUE):

  1. Sign-in works end-to-end for GitHub, Google, Apple, and Mastodon (per-instance app registration with a user-supplied instance URL), with Apple's ES256 JWT client secret generated per token exchange and automatically rotated (AUTH-01, AUTH-02, AUTH-03, AUTH-04).
  2. Every Mastodon instance URL is validated against SSRF (hostname/reserved-IP-range checks, no redirect-following, no raw-response reflection) before any outbound `.well-known`/registration request (AUTH-05 [guardrail]).
  3. A user can link multiple providers to one account, log in with any linked provider, and add/remove linked providers with a server-enforced minimum of one remaining login method (AUTH-06, AUTH-07).
  4. A new-provider login whose provider-verified email matches an existing account offers linking but requires explicit confirmation and re-authentication of the existing account first — never a silent/automatic merge (AUTH-08 [guardrail]).
  5. The `finalize_auth` helper has isolated unit tests covering verified-email merge success, unverified-email merge rejection, and merge-without-reauth rejection (AUTH-09 [guardrail]).
  6. The IndieAuth localhost bypass is provably unreachable in production configuration — a startup assertion refuses to boot if the bypass flag is set alongside a production indicator (AUTH-10 [guardrail]); the OAuth setup guide is published (DOCS-03).

**Plans**: TBD

### Phase 7: Web UI Production Readiness

**Goal**: The Next.js web UI is live at oviddb.org for search, disc detail, submission, and account management.
**Depends on**: Phase 1 (fingerprint aliases must be exposed via the lookup API before the disc-detail view can show them), Phase 6 (linked-provider add/remove requires AUTH-06/07)
**Requirements**: WEBUI-01, WEBUI-02, WEBUI-03, WEBUI-04
**Success Criteria** (what must be TRUE):

  1. A user can search by movie title and see known disc releases, live at oviddb.org (WEBUI-01).
  2. The disc detail view renders the full normalized structure (titles, main-feature marker, chapters, audio/subtitle tracks) and shows fingerprint aliases (WEBUI-02).
  3. An authenticated user can submit a new disc entry through the submit form (WEBUI-03).
  4. The account settings surface lets a user add/remove linked providers, wired to the AUTH-06/07 backend behavior (WEBUI-04).

**Plans**: TBD
**UI hint**: yes

### Phase 8: Launch Readiness — ARM, Seeding & Announcement

**Goal**: OVID v0.2.0 ships publicly — ARM integration is reviewed upstream, the database is seeded with real entries, alternate domains redirect, remaining docs are published, and the announcement goes out as the final exit gate.
**Depends on**: Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7 (final launch gate — needs fingerprinting, identity, verification, rate limiting, OAuth, and web UI all solid)
**Requirements**: ARM-01, ARM-02, OPS-01, OPS-02, OPS-03, OPS-04, DOCS-02, DOCS-04
**Success Criteria** (what must be TRUE):

  1. The ARM shim (`identify_ovid.py` file-swap) has a versioned/asserted interface rather than a comment-only contract, and the ARM integration PR is opened and under active review (or merged) upstream (ARM-01, ARM-02).
  2. A bulk-seed tool ingests a contributor's own disc collection, and the database holds at least 500 real disc entries (OPS-01, OPS-02 — depends on fingerprinting (Phase 4) and disc-identity submission (Phase 1/5) being solid).
  3. `oviddb.com` and `oviddb.net` redirect to `oviddb.org` (OPS-03 — independent, can ship any time within this phase).
  4. A user guide for the web application, a disc submission guide, an ARM integration guide, a CC0 data-license explainer, and the v0.2.0 CHANGELOG are all published (DOCS-02, DOCS-04).
  5. The public announcement is posted to GitHub, ARM forums, r/DataHoarder, and Doom9 (OPS-04 — final v0.2.0 exit gate).

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in dependency order. Waves that can run in parallel (per `parallelization: true`):

- Wave A (no dependencies): Phase 1, Phase 3, Phase 4, Phase 6
- Wave B (depend on Wave A): Phase 2 (needs 1), Phase 5 (needs 1, 4), Phase 7 (needs 1, 6)
- Wave C (final gate): Phase 8 (needs 1–7)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Alias-Layer Hardening & Repo Hygiene | 2/6 | In Progress|  |
| 2. Two-Contributor Verification Workflow | 0/TBD | Not started | - |
| 3. Redis-Backed Rate Limiting & Performance | 0/TBD | Not started | - |
| 4. Blu-ray/UHD Fingerprinting | 0/TBD | Not started | - |
| 5. ADR 0001 Completion — dvdread1-* Promotion | 0/TBD | Not started | - |
| 6. OAuth & Account Linking | 0/TBD | Not started | - |
| 7. Web UI Production Readiness | 0/TBD | Not started | - |
| 8. Launch Readiness — ARM, Seeding & Announcement | 0/TBD | Not started | - |

---
*Roadmap created: 2026-07-05*
*Granularity: standard (8 phases) | Coverage: 46/46 v1 requirements mapped*
