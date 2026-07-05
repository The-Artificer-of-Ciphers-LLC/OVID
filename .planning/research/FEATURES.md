# Feature Research

**Domain:** Community-curated physical-media identification database (MusicBrainz/Redump-adjacent, video-disc structural fingerprinting)
**Researched:** 2026-07-05
**Confidence:** HIGH (verification workflow, linked-account merge patterns — cross-checked against MusicBrainz, Redump, and mainstream OAuth-linking guidance); MEDIUM (pressing-level alias UX — single-source article, no existing community DB has shipped this exact user-facing concept yet)

## Scope Note

This research covers only the four remaining v0.2.0 feature areas named in scope: two-contributor verification workflow, multi-provider linked accounts with email-match merge, pressing-level disc identity as a user-facing alias concept, and Blu-ray/UHD Tier 1/Tier 2 identification behavior. Already-shipped features (DVD fingerprinting v1, lookup/submission API, client/CLI, OAuth scaffolding) are treated as given context, not re-researched.

## Feature Landscape

### Table Stakes (Users Expect These)

Features users/contributors assume exist. Missing these makes the community-DB model feel broken or unsafe to use.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Second-submission-confirms verification (unverified → verified) | This is THE core trust mechanism of every disc/audio community DB (Redump, MusicBrainz-style). A single unverified submission is treated as provisional by convention across the genre — users expect a visible "unverified" badge and a path to verified. | MEDIUM | Mirrors Redump: "verifications are submitted just like new discs; if the hash matches something in the DB, the site identifies it as a verification." OVID's analog: a second independent submission whose Disc Identity (fingerprint or alias) matches an existing unverified disc flips it to verified. Must guard against the *same* contributor re-submitting to self-verify (see anti-features). |
| Verification status visible in lookup response and Web UI | ARM and other API consumers need `confidence`/`verification_status` to decide whether to trust a match or prompt the user — this is already partially promised (P0 `confidence` field exists). Contributors need to *see* what needs a second confirmation to know where to focus effort. | LOW | Mostly wiring existing fields through; the API field for confidence already exists per PRD P0. Extend to explicitly expose `unverified`/`verified` state distinctly from confidence score, since they answer different questions (data quality signal vs. corroboration count). |
| One account, multiple linked login methods, minimum-one-remaining rule | Every modern multi-provider auth system (GitHub, Google, Discourse, Auth0/Clerk-style social login) enforces "you cannot unlink your last remaining login method" — otherwise users lock themselves out. This is closer to a security invariant than a preference. | LOW | Straightforward server-side check on unlink: count remaining active provider links + password (if email/password supported) before allowing removal. |
| Settings page listing all linked providers with add/remove | Directly promised in PRD P0 user story ("As a user with multiple linked providers, I want to see all of them in my account settings"). Standard pattern across GitHub, Google, every SSO-capable app. | LOW | UI + API list endpoint; already scaffolded per PROJECT.md (Web UI settings page exists partially). |
| Email-match "offer to link" flow, never silent auto-merge | Users expect that if they sign in with a new provider sharing their existing verified email, OVID recognizes them rather than creating a duplicate account/identity fragmentation — but doing this *silently* is a known account-takeover vector (nOAuth-class vulnerability) if any provider's "verified" email claim can be spoofed or reused. Best practice from Clerk/Ory/Auth.js guidance is consistently: prompt-and-confirm, never blind merge. | MEDIUM | Must require the user to be authenticated as (or actively confirm ownership of) the existing account before merge completes — e.g., "An account with this email already exists — sign in to that account to link, or continue to create a new one." Never merge purely because two providers reported the same email string. |
| Alias resolution at lookup time (multiple Disc Identity strings → one pressing entry) | This is the direct deliverable of ADR 0001 Phase 2, already committed to in Active requirements. Users/tools submitting `dvdread1-*` need the lookup to resolve to the same release data as an existing `dvd1-*` entry for the same physical disc — otherwise the same disc looks unrecognized. | HIGH | This is the most architecturally significant of the four areas — touches DB schema (identity string ↔ pressing many-to-one), lookup resolution order, and submission-time reconciliation (does a new identity string get attached to an existing pressing or create a new one?). |
| Blu-ray Tier 1 (AACS Disc ID) identification | AACS Disc ID is the de facto standard commercial Blu-ray identifier used by existing BD ripping/identification tooling (MakeMKV, redump-adjacent tools reference it) — contributors and ARM users expect BD disc recognition to work at least as well as the DVD path already does. | MEDIUM | Present on commercial (encrypted) BD/UHD only — absent on BD-Rs, some indie pressings. Must be tier 1 *when available*, with fallback. |
| Blu-ray Tier 2 (BDMV/PLAYLIST structure) fallback | Directly parallels the existing DVD structural-fingerprint approach (`dvd1-*`) and is required so BD-Rs, discs without AACS, and any disc where the Tier 1 ID isn't extractable still get a usable identity. Same rationale as OVID-DVD-1: structural fingerprinting must not depend on DRM/licensed identifiers alone. | MEDIUM-HIGH | Requires new parsers for `.mpls`/`.clpi`/`.m2ts` playlist structure analogous to `.ifo` parsing already done for DVD. Needs its own stability testing (same disc across drives/OSes) exactly like OVID-DVD-1 was validated in v0.1.0. |
| Format field disambiguation (DVD / BD / 4K UHD) in disc record | Already promised in PRD P0 ("format (DVD/BD/4K UHD)"). Table stakes because a Tier 1/Tier 2 BD identity string is meaningless without knowing which format/tier produced it — same disc surface (BDMV) is shared by BD and UHD but the encryption layer differs. | LOW | Mostly data-model completeness; UHD needs its own tier/version namespace analogous to `dvdread1-*` vs `dvd1-*` (e.g. a distinct fingerprint-version prefix per format+tier, not overloading BD's). |

### Differentiators (Competitive Advantage)

Features that set OVID apart from generic disc-label lookups (TMDB/OMDb) or proprietary competitors (GD3). Not required for MVP correctness, but where OVID's stated Core Value ("correct disc identity and structure, deterministically") is actually earned.

| Feature | Value Proposition | Complexity | Notes |
|---------|--------------------|------------|-------|
| Pressing-level identity as an explicit, user-visible concept (not just an internal alias table) | The matrix256 article frames "pressing-level" as a genuinely distinct granularity from title-level (TMDB) and format-level (AACS Disc ID) identity — the ability to tell apart Region A vs Region B Blu-rays sharing a TMDB ID, or distinguish 12 same-title-different-season discs in a box set. Surfacing this in the Web UI (e.g., "this pressing" vs "other pressings of this release") is where OVID differentiates itself from a plain fingerprint lookup and delivers on "edition and region resolution" (PRD Goal 3). | MEDIUM | This is a UX/data-presentation layer on top of the table-stakes alias resolution (above) — same underlying schema work, but exposing it as "N known Disc Identity strings map to this pressing, here's why" turns an implementation detail into a trust-building feature. Depends on the alias table stakes item being done first. |
| Independent multi-identity-method corroboration as its own signal | Because OVID now has two independent fingerprint methods for DVD (`dvd1-*` structural hash, `dvdread1-*` libdvdread Disc ID) that can each independently confirm the same disc, a disc where *both* methods agree is a stronger correctness signal than two submissions using the same method. This is genuinely different from MusicBrainz/Redump, which generally have one canonical hash type per medium. | MEDIUM | Optional refinement to the verification model: track which identity method(s) contributed each confirmation, and let cross-method agreement count as (or contribute extra weight toward) verification — a differentiator worth flagging to product but not required for MVP verification to function. |
| Contributor-facing "needs verification" queue/filter | MusicBrainz-style communities sustain themselves by giving contributors a directed way to find low-hanging corroboration work (unverified entries they personally own). A simple filtered list/search ("discs awaiting a second confirmation") converts casual contributors into repeat verifiers. | LOW-MEDIUM | Not promised explicitly in PRD P0/P1 but a very low-cost extension of the verification feature that materially improves the "≥3 active contributors submitting weekly" success metric. |
| Structured alias submission UX in `ovid-client`/Web UI ("this is the same pressing as X") | Rather than only reconciling aliases server-side when identity strings coincidentally match, let a contributor who *knows* two Disc Identity strings are the same physical pressing (e.g. from a personal collection with two ripping tools) assert the linkage directly. This is close to what PRD P1 already anticipates ("Duplicate/alias detection: flag when two submissions appear to be the same disc pressing") but pulled forward as contributor-initiated rather than purely system-detected. | MEDIUM | Needs a dispute/merge-request-like moderation step (already scaffolded in Web UI per PROJECT.md — "disputes" page exists) to avoid users incorrectly merging genuinely distinct pressings. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a v0.2.0 MVP, given OVID's stated non-goals and current scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Self-verification (same contributor's second submission confirms their own first) | Feels convenient — "I already know it's right, why wait for someone else?" — and contributors may be frustrated that their own careful submission sits `unverified` indefinitely if no one else owns the same disc. | Defeats the entire purpose of two-contributor verification (independent corroboration against user error, bad hardware, or malicious submission). Every community-DB precedent (Redump explicitly: "verifications are vital... reproducible by *another person*") treats same-submitter confirmation as non-verifying. Silently allowing it is a spam/abuse vector too — a single bad actor can self-verify garbage entries. | Require verification to come from a distinct account. If low community size makes verification too slow at launch, address via a growth/seeding lever (bulk-seed tooling, contributor recruitment) — not by weakening the trust model. |
| Fully automatic account merge on any matching email across providers, no confirmation step | Reduces friction — user doesn't have to do anything, "it just works." | This is the exact nOAuth-class vulnerability pattern flagged across OAuth security literature: if any linked provider's "verified" email claim can be obtained by an attacker (misconfigured tenant, email reuse, unverified-email providers), auto-merge silently hands over account access. IndieAuth in particular (already in OVID's provider list) has weaker centralized email verification guarantees than GitHub/Google. | Always require an explicit user action to complete the merge (sign in to the existing account, or a "link this to my existing account" click while already authenticated) — offer-to-link, never blind-merge, per the table-stakes item above. |
| Unlinking down to zero login methods, with a "recovery email" safety net promised for later | Seems like a minor edge case not worth blocking on. | Locks the user out of their account with no recovery path; "we'll add account recovery later" is exactly the kind of deferred-safety-net anti-pattern that turns into a support burden and a trust incident. | Enforce minimum-one-remaining at the API layer unconditionally (already in scope) — do not ship a settings UI that allows removing the last provider even temporarily. |
| Automatic pressing merge purely from fingerprint string similarity/fuzzy match | Tempting because it would auto-resolve a lot of near-duplicate entries without contributor effort, and reduces the perceived "clutter" of many similar disc entries. | Two distinct pressings can produce very similar-looking structural data (matrix256 article's explicit point: two pressings with different VOB sizes "look the same" at title granularity) while genuinely being different physical items with different regional edits/timing. Fuzzy-merging on structure risks conflating pressings OVID's product goals explicitly require distinguishing (Goal 3: edition/region resolution). | Merge only on exact Disc Identity string match (deterministic aliasing) or explicit contributor-asserted linkage routed through moderation/dispute review — never on approximate/fuzzy structural similarity. |
| Community edit-voting on disc metadata (MusicBrainz-style multi-voter consensus) for v0.2.0 | It's the "correct," full-strength trust model MusicBrainz uses, and contributors familiar with MusicBrainz may expect it by default. | Explicitly out of scope for this milestone (PRD defers "community edit-voting" to v0.4.0; PROJECT.md Out of Scope confirms "community edit-voting" deferred). Building a voting/reputation system now is a large scope increase disproportionate to the two-contributor verification model actually required for v0.2.0 exit criteria. | Ship the simpler two-contributor confirm model now; treat MusicBrainz-style voting as the explicitly planned v0.4.0 upgrade path, not a v0.2.0 feature. |
| Treating "pressing-level identity" as a brand-new user-facing entity/page separate from existing Disc records | The matrix256 framing is compelling enough that it's tempting to build a whole new "Pressing" concept/table distinct from the existing Disc record, to do it "properly." | ADR 0001 already deliberately keeps Disc Identity and Normalized Disc Structure as two separate concerns with a staged migration; introducing a third first-class concept (Pressing) not anticipated by the ADR would fragment an already-staged migration mid-flight and blow past the v0.2.0 Phase 2/3 scope (aliases resolve to *existing* Disc records, not a new entity). | Implement pressing-level identity as what ADR 0001 already calls it: a Lookup Alias — multiple Disc Identity strings resolving to one existing Disc/pressing record. Surface it in the UI as differentiator polish (see Differentiators above), not as new data-model surface area. |

## Feature Dependencies

```
Blu-ray Tier 2 (BDMV/PLAYLIST structural fingerprint)
    └──independent-of──> Blu-ray Tier 1 (AACS Disc ID)
                              (both feed into the same BD Disc Identity module,
                               Tier 1 preferred when available, Tier 2 fallback —
                               same pattern as dvd1/dvdread1)

Lookup Alias resolution (ADR 0001 Phase 2)
    └──requires──> Disc Identity module (existing, Phase 1 shipped)
    └──blocks────> ADR 0001 Phase 3 (promote dvdread1-* to primary)
    └──blocks────> Pressing-level UI differentiator (aliases must exist server-side first)
    └──enhances──> Two-contributor verification
                       (a submission using a *different* identity method/alias for an
                        already-known pressing should be able to count as independent
                        corroboration, not just an exact-string-match re-submission)

Two-contributor verification workflow
    └──requires──> Distinct-contributor check (anti-self-verification guard)
    └──enhances──> Contributor "needs verification" queue (differentiator)

Multi-provider linked accounts (add/remove, minimum-one-remaining)
    └──requires──> All four OAuth providers working end-to-end
    └──independent-of──> Email-match merge offer
                              (merge is a *login-time* event; linking in settings
                               is a *post-login* event — same underlying account
                               model, different entry points)

Email-match merge offer
    └──requires──> Verified-email claim per provider (must confirm which providers
                    actually assert a *verified* email, not just any email string —
                    flag for phase-specific research: does IndieAuth/Mastodon assert
                    verified email at all?)
    └──conflicts-with──> Silent/automatic merge anti-feature (explicitly rejected above)

Format field (DVD/BD/UHD) + Tier metadata
    └──requires──> Blu-ray Tier 1 + Tier 2 both implemented
                       (UHD reuses BDMV structure but different encryption layer per
                        PRD P2 note — needs its own identity-string namespace)
```

### Dependency Notes

- **Lookup Alias resolution blocks ADR 0001 Phase 3:** the roadmap item "promote `dvdread1-*` to primary" is explicitly gated on alias lookup/submission existing first (per ADR 0001 and PROJECT.md Active list) — sequence Phase 2 before Phase 3 work, never in parallel.
- **Lookup Alias resolution enhances verification:** once aliases exist, a second contributor submitting via the *other* identity method (e.g., someone with libdvdread-only tooling confirming a disc originally submitted via OVID-DVD-1) should satisfy the two-contributor verification requirement — this is a design decision to make explicit rather than an accidental side effect, and it's the basis for the "independent multi-identity-method corroboration" differentiator.
- **Multi-provider linked accounts is independent of email-match merge, but both need the OAuth providers actually finished:** settings-page linking and login-time merge-offer are different code paths sharing the same account/identity-provider data model; both require all four providers (GitHub, Google, Apple, Mastodon) working end-to-end first, which is already tracked as a separate Active item.
- **Email-match merge conflicts with the "silent auto-merge" anti-feature:** this is a hard product/security constraint, not just a preference — document as a requirement guardrail ("must require explicit confirmation") rather than an implementation detail, since it is easy to accidentally build the anti-feature version under time pressure.
- **Pressing-level UI differentiator depends on alias resolution existing server-side:** do not attempt to build user-facing "this pressing has N known identity strings" presentation before the underlying alias data model (table stakes) is real — it would have nothing to display.

## MVP Definition

### Launch With (v0.2.0)

Minimum viable set — what's needed to hit the already-committed v0.2.0 exit criteria (per PROJECT.md Active + product spec Milestone 0.2).

- [ ] Two-contributor verification (unverified → verified), with distinct-contributor enforcement — this is the core trust primitive every comparable community DB has; shipping without it undermines "correct disc identity... deterministically and reproducibly."
- [ ] Lookup Alias resolution (ADR 0001 Phase 2): multiple Disc Identity strings → one pressing, exposed through lookup and submission — already committed, and blocks the also-committed Phase 3 promotion.
- [ ] Multi-provider linked accounts: settings-page add/remove with minimum-one-remaining enforced server-side — directly promised in PRD P0 user stories.
- [ ] Email-match merge offer, confirm-required (never silent) — directly promised in PRD P0, with the confirm-required constraint added by this research to avoid the OAuth anti-pattern.
- [ ] Blu-ray Tier 1 (AACS Disc ID) + Tier 2 (BDMV/PLAYLIST structure) fingerprinting, with Tier 1 preferred/Tier 2 fallback — explicit v0.2.0 exit criterion.
- [ ] Format/tier disambiguation in the disc record (DVD/BD/UHD, tier used) — needed so alias resolution and verification logic can reason about which identity method produced a match.

### Add After Validation (v0.2.x / early v0.3)

Features to add once the core trust/identity mechanisms are proven in production.

- [ ] Contributor-facing "needs verification" queue/filter — add once there's a real backlog of unverified discs to triage; trigger is contributor feedback that finding what-to-verify is hard.
- [ ] Pressing-level identity surfaced explicitly in Web UI ("N known identity strings map to this pressing") — add once alias data exists in volume and early users start asking "why does this disc have two fingerprints."
- [ ] Cross-identity-method corroboration counted explicitly toward verification — add once both `dvd1-*` and `dvdread1-*` are both actively submitted in the wild long enough to have real dual-method disc entries to observe.

### Future Consideration (v0.3+/v0.4+)

Already deferred by the product spec/PROJECT.md — listed here to confirm this research agrees they should stay deferred.

- [ ] Community edit-voting (MusicBrainz-style) — PRD defers to v0.4.0; the two-contributor model is sufficient for MVP trust needs and voting is a large scope increase.
- [ ] Contributor-initiated alias/dispute merge UX ("this is the same pressing as X") beyond system-detected matches — PRD P1 anticipates system-detected alias flagging; contributor-initiated merge requests are a reasonable v0.3 addition once the dispute-review moderation surface (already scaffolded) is exercised in production.
- [ ] UPC barcode cross-referencing as an identity signal — PRD P1/out-of-scope-for-0.2 per PROJECT.md; keep deferred, it's a supplementary lookup path, not core identity.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| Two-contributor verification workflow | HIGH | MEDIUM | P1 |
| Lookup Alias resolution (ADR 0001 Phase 2) | HIGH | HIGH | P1 |
| Linked accounts add/remove, minimum-one-remaining | HIGH | LOW | P1 |
| Email-match merge offer (confirm-required) | MEDIUM-HIGH | MEDIUM | P1 |
| Blu-ray Tier 1 (AACS Disc ID) | HIGH | MEDIUM | P1 |
| Blu-ray Tier 2 (BDMV structural fingerprint) | HIGH | MEDIUM-HIGH | P1 |
| Format/tier disambiguation in disc record | MEDIUM | LOW | P1 |
| Contributor "needs verification" queue | MEDIUM | LOW-MEDIUM | P2 |
| Pressing-level identity surfaced in Web UI | MEDIUM | MEDIUM | P2 |
| Cross-identity-method corroboration signal | LOW-MEDIUM | MEDIUM | P2 |
| Contributor-initiated alias/dispute merge UX | MEDIUM | MEDIUM | P3 |
| Community edit-voting | MEDIUM | HIGH | P3 (v0.4.0 per PRD) |

**Priority key:**
- P1: Must have for v0.2.0 launch (already committed in PROJECT.md Active / PRD Milestone 0.2 exit criteria)
- P2: Should have, natural extension once P1 lands — good candidates for early v0.3 work
- P3: Explicitly deferred by product spec; confirmed correct to defer by this research

## Competitor Feature Analysis

| Feature | MusicBrainz | Redump.org | Our Approach |
|---------|-------------|------------|---------------|
| Independent-confirmation trust model | Multi-voter consensus (3-unanimous-vote fast path, else 7-day majority vote); requires 2-week account age + 10 accepted edits to gain voting rights | Second independent submission with matching hash marks existing entry as a "verification"; dumping twice yourself is recommended practice but doesn't substitute for another person's dump | Two-contributor confirmation (simpler than MusicBrainz voting, same spirit as Redump) — appropriately scoped down from MusicBrainz's full voting system per PRD's explicit v0.4.0 deferral of voting |
| Distinct pressing/release granularity | "Release" vs "Release Group" split — same abstract work, many releases (regional pressings, remasters) each with distinct barcodes/labels | Distinguishes physical dumps per specific disc pressing; hash mismatch across nominally-same title flags a different pressing | Disc Identity (pressing) kept explicitly separate from Release/Title (movie) per ADR 0001 — matches the industry-standard split rather than conflating "the movie" with "this physical disc" |
| Multi-provider account linking | Single account model, no OAuth federation of this shape | N/A (Redump uses simple forum-style accounts) | OVID's four-provider (GitHub/Google/Apple/Mastodon) + email/password linking model is more elaborate than either direct precedent — closer to modern SaaS social-login patterns (Clerk/Ory/Auth.js) than to legacy community-DB auth |
| Alias / duplicate-identity reconciliation | Handled via merge tooling for duplicate Release/Recording MBIDs, moderator-driven | Hash-based; a "correct" dump reproduces the exact same hash, so aliasing is less of a concept — different tools/methods aren't expected to diverge the way `dvd1-*` vs `dvdread1-*` do | OVID's alias need is structurally different: two *different fingerprinting methods* (not just two independent dumps) can legitimately produce two different valid identity strings for the same pressing — this is closer to MusicBrainz's cross-ID merge tooling than to Redump's single-hash model |

## Sources

- [Introduction to Voting — MusicBrainz](https://musicbrainz.org/doc/Introduction_to_Voting) — HIGH confidence, official documentation
- [How Editing Works — MusicBrainz](https://musicbrainz.org/doc/How_Editing_Works) — HIGH confidence, official documentation
- [Editing FAQ — MusicBrainz](https://musicbrainz.org/doc/Editing_FAQ) — HIGH confidence, official documentation
- [Dumping Guide (redumper CLI) — Redump Wiki](http://wiki.redump.org/index.php?title=Dumping_Guide_%28redumper_CLI%29) — HIGH confidence, official community documentation
- [Redump.org — Redump Wiki](http://wiki.redump.org/index.php?title=Redump.org) — HIGH confidence, official community documentation
- [Account linking for OAuth — Clerk Docs](https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking) — MEDIUM-HIGH confidence, vendor documentation but consistent with independent sources
- [Everything you need to know about secure account linking — Ory](https://www.ory.com/blog/secure-account-linking-iam-sso-oidc-saml) — MEDIUM-HIGH confidence, vendor blog, cross-checked against Descope/Auth.js discussion
- [OAuth Vulnerabilities and Misconfigurations — Descope](https://www.descope.com/blog/post/5-oauth-misconfigurations) — MEDIUM confidence, vendor blog, describes the real nOAuth-class vulnerability class
- [Multiple accounts with same mail handling — next-auth GitHub Discussion #2808](https://github.com/nextauthjs/next-auth/discussions/2808) — MEDIUM confidence, community discussion, corroborates confirm-required pattern
- [matrix256: A Pressing-Level Disc Fingerprint — shitwolfymakes Substack](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) — MEDIUM confidence, single independent-author source; no corroborating second source for the specific "pressing-level" terminology, but internally consistent with OVID's own ADR 0001 framing of Disc Identity vs Structure
- `docs/OVID-product-spec.md` (this repo) — project source of truth for P0/P1/P2 requirements and Milestone 0.2 exit criteria
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` (this repo) — project source of truth for alias/Disc Identity architecture
- `.planning/PROJECT.md` (this repo) — project source of truth for current Active/Out-of-Scope requirement status

---
*Feature research for: OVID v0.2.0 remaining scope (verification workflow, linked accounts, pressing-level alias identity, BD/UHD tiers)*
*Researched: 2026-07-05*
