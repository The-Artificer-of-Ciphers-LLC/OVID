# Requirements: OVID — v0.2.0 (MVP) Completion

**Defined:** 2026-07-05
**Core Value:** Given a disc in any drive, OVID returns the correct disc identity and structure — deterministically and reproducibly — so ripping tools can name, tag, and route content without manual correction.

**Scope note:** This milestone completes the remaining **v0.2.0 / Milestone 0.2 (MVP)** exit criteria on the existing OVID codebase. Source of truth: `docs/OVID-product-spec.md` (Milestone 0.2), `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`, and `.planning/research/SUMMARY.md`. Requirements marked **[guardrail]** are non-negotiable safety constraints surfaced by research.

## v1 Requirements

### Blu-ray / UHD Fingerprinting (FPRINT)

- [ ] **FPRINT-01**: `ovid-client` computes a Blu-ray Tier 1 fingerprint from the AACS Disc ID (`bd1-aacs-*`)
- [ ] **FPRINT-02**: `ovid-client` computes a Blu-ray Tier 2 fingerprint from BDMV/PLAYLIST/CLIP structure (`bd2-*`)
- [ ] **FPRINT-03**: When both tiers are computable for a disc, the client returns BOTH in one `DiscIdentitySet` (they become an alias pair) rather than short-circuiting on Tier 1 success
- [ ] **FPRINT-04**: 4K UHD Blu-ray discs are fingerprinted via the same tiered path, with format recorded on the disc record
- [ ] **FPRINT-05**: The same disc produces identical BD/UHD fingerprints across ≥2 drives and both Linux and macOS (determinism regression test)
- [ ] **FPRINT-06 [guardrail]**: Tier 2 playlist filter/sort constants are versioned as part of the fingerprint spec (defends against studio "obfuscation playlist" decoys), not tuned as loose implementation values
- [ ] **FPRINT-07**: A real BD/UHD fixture corpus (including ≥1 heavily-obfuscated disc) backs the regression suite, following the existing private/`real_disc` fixture pattern

### Disc Identity & Alias Migration (IDENT)

- [ ] **IDENT-01**: The lookup response exposes all known `fingerprint_aliases` for a disc so callers can see every identity string that resolves to one pressing
- [ ] **IDENT-02 [guardrail]**: The alias check-then-insert write path is race-safe under concurrent gunicorn workers (no duplicate/split pressings under load)
- [ ] **IDENT-03**: The client submits all known Disc Identity strings (`dvd1-*`, `dvdread1-*`, BD tiers) on submission so the API can store them as aliases (ADR 0001 Phase 2 complete)
- [ ] **IDENT-04**: `dvdread1-*` (libdvdread Disc ID) is promoted to the primary DVD fingerprint, with `dvd1-*` retained as a resolvable alias (ADR 0001 Phase 3)
- [ ] **IDENT-05 [guardrail]**: A permanent CI regression test proves an existing `dvd1-*` string still resolves to its disc after every migration step (anti-fragmentation guarantee)

### OAuth & Accounts (AUTH)

- [ ] **AUTH-01**: Sign in with GitHub works end-to-end
- [ ] **AUTH-02**: Sign in with Google works end-to-end
- [ ] **AUTH-03**: Sign in with Apple works end-to-end, generating a short-lived ES256 JWT client secret per token exchange (not a static secret), with automated secret rotation
- [ ] **AUTH-04**: Sign in with Mastodon works via per-instance app registration (`POST /api/v1/apps`) with user-supplied instance URL
- [ ] **AUTH-05 [guardrail]**: The Mastodon instance URL is validated against SSRF (hostname/IP-range checks) before any outbound `.well-known`/registration request
- [ ] **AUTH-06**: A user can link multiple providers to one account and use any linked provider to log in
- [ ] **AUTH-07**: The account settings page lists all linked providers and allows add/remove, enforcing a minimum of one remaining login method
- [ ] **AUTH-08 [guardrail]**: On a new provider login whose verified email matches an existing account, OVID OFFERS to link and requires explicit confirmation / re-auth of the existing account — never silent/automatic merge (nOAuth/CVE-class takeover defense)
- [ ] **AUTH-09 [guardrail]**: The `finalize_auth` helper has isolated unit tests as a blocking exit criterion (currently an untested path per CONCERNS.md)
- [ ] **AUTH-10 [guardrail]**: The IndieAuth localhost bypass is provably unreachable in production configuration (test-enforced)

### Two-Contributor Verification (VERIFY)

- [ ] **VERIFY-01**: A submitted disc entry is `unverified` until a second, DISTINCT contributor independently confirms the fingerprint (never self-confirmation)
- [ ] **VERIFY-02**: Verification status transitions are consolidated into a single guarded service module (no scattered route-level mutations)
- [ ] **VERIFY-03 [guardrail]**: An already-`verified` disc cannot be flipped back to `disputed`/`unverified` by a later third submission without an explicit dispute path
- [ ] **VERIFY-04 [guardrail]**: Baseline anti-Sybil weighting (account-age / IP-diversity signals) and confirmation-action rate limits gate the verification step — distinct `user_id` alone is not accepted as proof of independence

### Web UI (WEBUI)

- [ ] **WEBUI-01**: Search by movie title returns known disc releases (live at `oviddb.org`)
- [ ] **WEBUI-02**: Disc detail view renders full normalized structure (titles, main-feature marker, chapters, audio/subtitle tracks) and shows fingerprint aliases
- [ ] **WEBUI-03**: A submit form lets an authenticated user contribute a new disc entry
- [ ] **WEBUI-04**: Account settings surface (linked providers add/remove) is wired to AUTH-06/07

### Rate Limiting & Performance (INFRA)

- [ ] **INFRA-01**: Rate limiting uses Redis-backed slowapi storage so limits are correct across gunicorn workers (fixes in-memory multi-worker defect); a `redis` service is added to the relevant compose files
- [ ] **INFRA-02 [guardrail]**: Fail-open vs fail-closed behavior on Redis outage is an explicit, documented decision (and tested)
- [ ] **INFRA-03**: API p95 ≤ 500ms is validated by a load test run against the ACTUAL Redis-backed, multi-worker gunicorn config
- [ ] **INFRA-04**: Basic abuse prevention (submission/confirmation throttles) is live

### ARM Integration (ARM)

- [ ] **ARM-01**: The ARM integration PR is opened and under active review (or merged) upstream
- [ ] **ARM-02**: The ARM shim contract (`identify_ovid.py` file-swap) is given a versioned/asserted interface rather than a comment-only contract

### Seeding & Launch Ops (OPS)

- [ ] **OPS-01**: A bulk-seed import tool ingests a contributor's own disc collection into the database
- [ ] **OPS-02**: The database is seeded to ≥500 real disc entries
- [ ] **OPS-03**: `oviddb.com` and `oviddb.net` redirect to `oviddb.org`
- [ ] **OPS-04**: The public announcement is posted (GitHub, ARM forums, r/DataHoarder, Doom9)

### Documentation (DOCS)

- [ ] **DOCS-01**: Fingerprint spec updated with OVID-BD-2 (Tier 1 & Tier 2) in `docs/fingerprint-spec.md`
- [ ] **DOCS-02**: Web UI user guide, disc submission guide, and ARM integration guide published
- [ ] **DOCS-03**: OAuth setup guide (`docs/auth-setup.md`) published, incl. the Mastodon `requests`-vs-`httpx` client note
- [ ] **DOCS-04**: CC0 data-license explainer published; CHANGELOG updated for v0.2.0

### Repo Hygiene (CLEAN)

- [ ] **CLEAN-01**: Ad-hoc root scripts (`fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py`) are removed or relocated under `scripts/`
- [ ] **CLEAN-02**: UAT artifacts (`uat_results.json`, `uat_dirs/`) are gitignored

## v2 Requirements

Deferred beyond v0.2.0 (tracked, not in this roadmap).

### Pressing-Level Fingerprint (MATRIX)

- **MATRIX-01**: Evaluate/adopt matrix256 as an additional (fifth) alias fingerprint under the existing alias model — spike first; single-source, unvalidated at OVID's scale

### Growth / v0.3.0+ (GROWTH)

- **GROWTH-01**: Sync feed endpoints + self-hosted mirror node (v0.3.0)
- **GROWTH-02**: UPC barcode lookup (v0.3.0)
- **GROWTH-03**: Edit history / audit log UI + community dispute flagging (v0.3.0)
- **GROWTH-04**: Monthly CC0 data dump (v0.3.0)
- **GROWTH-05**: TV-series multi-disc episode mapping + community edit-voting (v0.4.0)
- **GROWTH-06**: JavaScript/Node client library (v0.4.0)

## Out of Scope

Explicitly excluded — includes anti-features from research (with warnings).

| Feature | Reason |
|---------|--------|
| Silent/automatic account merge on matching email | nOAuth/CVE-class account-takeover vector — merge MUST be confirm-gated (see AUTH-08) |
| Self-verification (same user confirms own submission) | Defeats the two-contributor trust model (see VERIFY-01) |
| Unlinking the last remaining login method | Locks the user out — minimum one must remain (see AUTH-07) |
| Fuzzy / approximate pressing merges | Silent data corruption risk; only exact-identity aliasing in v0.2.0 |
| MusicBrainz-style full edit-voting | Deferred to v0.4.0 per PRD; too heavy for MVP |
| Mastodon-driven email-merge | Federated instances have no uniform verified-email standard — do not trust for merge (open question → default disabled) |
| Storing video content, disc images, or decryption keys | Legal non-goal (metadata database only) |
| Replacing TMDB/OMDb for movie metadata; consumer browsing UI | PRD non-goals — OVID owns disc identity/structure only |
| LaserDisc / VHS / HD-DVD | PRD non-goal (small audience) |

## Traceability

Populated during roadmap creation (Step 8). Each v1 requirement maps to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| _(to be filled by roadmapper)_ | — | Pending |

**Coverage:**
- v1 requirements: 46 total (FPRINT 7, IDENT 5, AUTH 10, VERIFY 4, WEBUI 4, INFRA 4, ARM 2, OPS 4, DOCS 4, CLEAN 2)
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 46 ⚠️ (resolved at roadmap creation)

---
*Requirements defined: 2026-07-05*
*Last updated: 2026-07-05 after initial definition*
