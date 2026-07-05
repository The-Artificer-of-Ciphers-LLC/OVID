# Pitfalls Research

**Domain:** Multi-format disc fingerprinting + staged identity migration + multi-provider OAuth + community verification (OVID v0.2.0 remaining scope)
**Researched:** 2026-07-05
**Confidence:** MEDIUM-HIGH (project-specific reasoning is HIGH — grounded in the ADR, spec, and codebase concerns already on disk; external security claims are sourced from named vendor/CVE writeups and cross-referenced where possible; a few AACS-regional-variant specifics are LOW confidence — flagged inline)

## Critical Pitfalls

### Pitfall 1: BDMV structure hash falls apart on the "obfuscation playlist" problem

**What goes wrong:**
Modern commercial BD/UHD discs ship hundreds of decoy `.mpls` playlists engineered to defeat ripping tools (the spec's own §2.2 calls out 800+ files on some studio discs, with only 1–2 being the real feature). A naive Tier 2 implementation that hashes *all* playlists — or that changes its 60-second noise filter threshold between releases — produces a different fingerprint for the same physical disc depending on which playlists survive filtering. Any change to the filter constant, the "sort by filename not duration" rule, or the deterministic tie-break for identically-sized playlists silently changes every previously-issued `bd2-`/`uhd2-` fingerprint database-wide.

**Why it happens:** Studios actively adversarially engineer disc structure against exactly this kind of fingerprinting (this is the same "not tamper-proof" property the matrix256 author calls out — a content-addressable identifier without cryptographic signing can be gamed by whoever controls the mastering). Developers treat the filter threshold as a tunable constant instead of a versioned part of the algorithm.

**How to avoid:**
- Freeze the OVID-BD-2 canonical algorithm (filter threshold, sort order, tie-break rule) as a versioned spec the moment it ships — any future change must bump to `bd3-`/`uhd3-`, never silently mutate `bd2-`/`uhd2-` semantics (mirrors the `dvd1-`→`dvdread1-` lesson already learned in ADR 0001).
- Test against real discs with known heavy obfuscation (the spec footnote calls these out as "particularly from major US studios") in the fixture corpus, not just clean indie/TV discs.
- Explicitly define behavior for playlists that tie on duration+chapters+track layout after filtering (rare, but the fallback tier is inherently weaker — document as `confidence: medium` per the existing lookup-confidence field, never silently merge them).

**Warning signs:** Same physical disc pressing produces different `bd2-`/`uhd2-` values across two ripping runs; fixture tests only use small/simple discs; the filter threshold or sort key isn't referenced anywhere in a spec doc, only in code.

**Phase to address:** Blu-ray/UHD fingerprinting phase (Tier 2 implementation) — write the obfuscation-heavy disc into the test fixture corpus before considering Tier 2 "done."

---

### Pitfall 2: AACS Disc ID (Tier 1) assumed to be pressing-unique without verifying regional/reprint variance

**What goes wrong:** The spec treats AACS Disc ID (SHA-1 of `Unit_Keys_RO.inf`) as "a true industry identifier — unique per disc pressing by design." This is directionally correct (it is assigned at mastering, not computed from content), but the *scope* of "per pressing" needs verification: a title re-pressed later with an updated Media Key Block (MKB) revocation list, or released simultaneously across regions from the same content master, may or may not get a new Unit_Keys_RO.inf. If OVID silently assumes 1:1 (AACS Disc ID ↔ physical edition) and two genuinely different editions/regions share one, submissions collide into one DB row; if the assumption runs the other way (one edition ↔ many AACS Disc IDs because of MKB renewal), the same edition fragments across multiple "unverified" entries that never reach two-contributor confirmation.

**Why it happens:** AACS Disc ID computation is well documented cryptographically, but its *stability across MKB revocation cycles for reprints of the same title* is not something OVID's own team has empirically validated yet — this is a genuine gap (LOW confidence claim on the regional-variant behavior specifically; MEDIUM confidence generally that MKBs get renewed across the BD ecosystem over time per general AACS documentation).

**How to avoid:**
- Do not assume Tier 1 fingerprints are collision-free across reprints; treat AACS Disc ID collisions the same way as OVID-DVD-1 collisions — surfaced to the two-contributor/dispute workflow, not silently merged or silently split.
- Store the *raw* AACS Disc ID as its own lookup alias distinct from any structural (Tier 2) fingerprint for the same disc row, exactly as ADR 0001 already models Lookup Aliases for `dvd1-`/`dvdread1-` — this pattern generalizes directly to Tier 1/Tier 2 BD coexistence (§2.3 in the spec already allows a disc row to hold both).
- When bulk-seeding ≥500 discs (an active v0.2.0 item), flag any title with multiple regional Blu-ray releases for manual review rather than assuming AACS Disc ID sameness or difference.

**Warning signs:** Two different known editions (e.g. Region A vs Region B release of the same film) resolve to the same AACS Disc ID and get silently merged; OR the same edition purchased twice shows up as two "unverified, never verified" entries that never match each other.

**Phase to address:** Blu-ray/UHD fingerprinting phase — add a test fixture note (not necessarily a passing test, since real discs are needed) documenting this as a known open question; two-contributor verification phase should treat Tier 1 mismatches as disputes, not silent failures.

---

### Pitfall 3: Tier selection logic silently downgrades confidence without recording *why*

**What goes wrong:** The documented `compute_fingerprint()` tier-selection code (`if aacs_id: ... else: compute_bdmv_structure_hash(disc)`) returns only a fingerprint string. If `libaacs` is present but returns `None` because the disc uses AACS2 (UHD) in a way the installed `libaacs` version doesn't support yet — vs. genuinely being an unprotected/legacy disc — both paths look identical to the caller. A drive/OS/library-version difference then produces Tier 1 on one machine and Tier 2 on another for the *same physical disc*, and because Tier 1 and Tier 2 use different prefixes (`bd1-aacs-` vs `bd2-`), this isn't a hash mismatch bug — it's an entirely different fingerprint. Two contributors submitting the same disc from different environments can appear never to match, permanently stuck at `unverified`.

**Why it happens:** The two tiers were designed as an availability fallback ("whichever source is available"), but "available" depends on the *contributor's* environment (whether `libaacs`/MakeMKV keys are present), not the disc. This is a client-environment variable masquerading as a disc property.

**How to avoid:**
- The client and API must record which tier produced a fingerprint as first-class metadata (already implied by "a single disc entry can hold both a Tier 1 and Tier 2 fingerprint"), and — critically — the two-contributor verification logic must check for a match on *either* tier before declaring "no match, still unverified."
- Actively encourage/require submission of both tiers when both are computable in the same session, rather than treating tier selection as either/or.
- Document for ARM/client integrators that a disc's confidence should never regress from `high` (Tier 1 match) to `medium`/no-match just because a second contributor's environment lacked AACS keys.

**Warning signs:** Verification rate stalls despite plausible duplicate submissions; support/bug reports of "I know someone else has this disc but it won't verify."

**Phase to address:** ADR 0001 Phase 2 (Lookup Aliases) completion and Blu-ray fingerprinting phase jointly — the alias-lookup mechanism being built for `dvd1-`/`dvdread1-` is the same mechanism needed for `bd1-aacs-`/`bd2-` cross-tier matching; build them on one shared code path, not two parallel ones.

---

### Pitfall 4: Migration Phase 2/3 fragments `dvd1-*` lookups despite the ADR's explicit intent

**What goes wrong:** ADR 0001's entire purpose is to prevent exactly this, but the most common way staged identifier migrations fail in practice is *silent scope creep at the boundary*: a new endpoint, test, doc example, or DB query is added during Phase 2/3 work that queries/writes only the new `dvdread1-*` path (because it's the "correct" long-term fingerprint) and forgets that `dvd1-*` must remain a first-class resolvable alias, not a legacy shim. Six months later, a subset of existing bookmarked/cached client lookups (e.g. ARM users who cached `dvd1-*` fingerprints from before the migration) silently 404 or return degraded results, and nobody notices until a user reports it.

**Why it happens:** "Promote the new thing to primary" naturally reads as "the old thing becomes secondary/optional," and secondary things get skipped in a rush (tests not written for the alias path, docs updated to only show the new format, a new endpoint added without alias resolution). This is the single most common failure mode of expand/contract-style ID migrations — the "contract" step quietly drops support that was supposed to be permanent, not temporary.

**How to avoid:**
- Treat "does `GET /v1/disc/{dvd1-fingerprint}` still 200 with correct data" as a **non-negotiable regression test** that runs in CI for every PR touching disc lookup or submission code, from Phase 1 through Phase 3 and beyond — not just during the migration window.
- Any new endpoint, fixture, or doc example written during Phase 2/3 must include at least one `dvd1-*` example alongside `dvdread1-*`, enforced via PR review checklist, not memory.
- Explicitly re-read ADR 0001's Consequences section before Phase 3 work begins: "`dvd1-*` remains ... even after `dvdread1-*` becomes the preferred Disc Identity Method" — Phase 3 promotes primary-ness for *new* submissions/display, it does not deprecate `dvd1-*` resolvability. Write this as an acceptance criterion, not an assumption.
- Watch the DB layer specifically: if `discs.fingerprint` stays a single `UNIQUE` column (per the schema in the spec, §3.1) while aliases live in a separate table, every query path that does a raw `WHERE fingerprint = :fp` lookup (rather than going through the alias-resolution layer) is a fragmentation risk the moment `dvdread1-*` becomes primary and `dvd1-*` moves to the alias table.

**Warning signs:** A grep for `dvd1-` in test files trends down as `dvdread1-` trends up during Phase 2/3 (should stay flat or grow, never shrink); any code path does `discs.fingerprint ==` equality instead of calling a shared `resolve_disc_identity()` helper; docs updated in Phase 3 show only `dvdread1-*` examples.

**Phase to address:** ADR 0001 Phase 2 (alias modeling) and Phase 3 (primary promotion) — both need an explicit "dvd1-* still resolves" regression test as an exit criterion, not just "dvdread1-* now works."

---

### Pitfall 5: Email-match OAuth account merge enables full account takeover if the "verified" flag isn't actually provider-attested

**What goes wrong:** OVID's spec (§4.2) implements exactly the pattern that has caused multiple real CVEs across the industry (Nhost GHSA-6g38-8j4p-j3pr / CVE-class "nOAuth"-style bugs, Descope's writeup, and at least one 2026 CVE against a similarly-named product): a new OAuth login with an email matching an existing account triggers a merge prompt. The documented mitigation ("merging requires the user to authenticate the existing account") is correct *if implemented as literally described*, but the common real-world failure is subtler: the merge-eligibility check itself trusts each provider's `email_verified` claim, and provider adapters are not uniformly trustworthy. If OVID's Google/GitHub/Apple/Mastodon adapters don't each *independently* confirm the provider actually attests email ownership (vs. accepting an email field that the provider populates from an unverified profile field, or that Mastodon instances — which are federated, arbitrary, self-hosted software — never verify at all), an attacker registers on some OAuth provider using a victim's email, triggers the merge-eligible path, and if the "prove you own the existing account" step has any bypass (e.g., allowing merge before the existing-account auth step completes, or silently auto-linking below some threshold), the attacker gets an authenticated session merged onto the victim's account.

**Why it happens:** "The provider says the email is verified" is treated as fact when the provider is (a) not itself trustworthy for that claim (self-hosted Mastodon instances have no verification standard at all — this is different from a Big Tech IdP), or (b) has adapter-level code that maps a non-ownership-proving field (e.g. a UPN or display email) into the "verified" flag.

**How to avoid:**
- Never treat Mastodon-provided email (if collected at all — the spec's flow in §4.2's Mastodon section notably does *not* mention collecting email from Mastodon, only username/instance) as verified for merge purposes; Mastodon merge-by-email should probably be disabled entirely given federated instances have no uniform verification bar.
- For GitHub/Google/Apple, use each provider's actual verified-email API field (GitHub: `email_verified` from the `/user/emails` endpoint, not the profile email; Google: `email_verified` in the ID token; Apple: emails from Sign In with Apple are always relay-verified by Apple's own service) — and unit-test each provider's adapter independently for this, since ADR/spec review shows `finalize_auth` (the shared merge/link helper) currently has **no isolated test file** per the codebase CONCERNS.md audit (`api/app/auth/routes.py:71`).
- The merge flow must require completing authentication of the *existing* account (password or existing OAuth re-login) as a hard gate *before* any linking write happens — verify this is enforced server-side, not just in UI copy ("Link this GitHub login to that account?" must not be clickable without the auth step already having happened).
- Add a negative test: attacker with unverified/self-asserted email on a weak-verification provider must NOT reach the merge-eligible code path at all.

**Warning signs:** `finalize_auth` has no isolated unit test (already true per CONCERNS.md); any provider adapter path sets `email_verified=True` without checking a provider API field named exactly that; Mastodon flow collects/uses email at all for merge purposes.

**Phase to address:** OAuth completion phase (all four providers end-to-end) — before merging linked-accounts work, add `finalize_auth` isolated tests covering: (a) verified-email merge success, (b) unverified-email merge rejection/prompt-to-create-new, (c) merge attempted without existing-account re-auth (must fail).

---

### Pitfall 6: Apple Sign In client secret silently expires in production (max 6 months)

**What goes wrong:** Apple requires the OAuth client secret to be a self-signed ES256 JWT with a maximum lifetime of 15,777,000 seconds (~6 months) from issuance. Unlike GitHub/Google (long-lived static client secrets), this secret **must be regenerated and redeployed** before expiry or Apple Sign In starts failing in production with an opaque error, unrelated to any code change — the classic "why did auth just break, we didn't touch anything" incident.

**Why it happens:** Teams generate the JWT once at initial integration time (often with a long-seeming expiry like 180 days) and never build a renewal/monitoring process, since nothing in local dev ever hits the expiry window.

**How to avoid:**
- Generate the client secret JWT programmatically at a cadence well inside the 6-month ceiling (e.g. regenerate every 120–150 days via a scheduled job or on every deploy) rather than as a one-time manual artifact.
- Alert on expiry proactively (a scheduled check that fails loudly at, say, 30 days before expiry) rather than discovering it via a broken production login.
- Also handle the ES256 signature-encoding gotcha some JWT libraries hit: RFC 7515 expects raw `R || S` (64 bytes), but some crypto libraries (OpenSSL-backed) emit DER-encoded ASN.1 signatures by default — verify whatever JWT library OVID uses produces the raw concatenated format Apple expects, or Apple will reject the secret outright even before the expiry issue ever comes up.

**Warning signs:** Apple login works in initial testing, then fails months later with a vague `invalid_client` error and no code changes in the diff; client secret generation exists as a one-off script/manual step rather than an automated/monitored process.

**Phase to address:** OAuth completion phase (Apple provider) — build secret rotation into the deployment/ops runbook as an exit criterion, not just "Apple login works today."

---

### Pitfall 7: Mastodon per-instance discovery treated as a pure metadata fetch, not an SSRF-shaped request

**What goes wrong:** OVID's documented flow has the *server* fetch `https://{user-supplied-instance}/.well-known/oauth-authorization-server` (and subsequently redirect/exchange tokens against user-supplied-instance URLs). Any endpoint where the server makes an outbound HTTP request to a URL/hostname substantially controlled by the requesting user is SSRF-shaped by construction, independent of whether Mastodon's own endpoint is "just metadata." A user can supply `instance_url` pointing at an internal service (`http://169.254.169.254/...`, `http://localhost:6379`, an internal admin panel, etc.) and get the OVID server to make a same-origin-privileged request to it, then potentially reflect response data back (e.g. if error responses or fetched JSON get echoed to the client in a way that leaks internal service responses).

**Why it happens:** Mastodon's `.well-known` endpoint doc explicitly says it "does not require authentication" and is "read-only" — true, but that describes the endpoint's own behavior, not the risk of the *server making the request in the first place* to an attacker-chosen host.

**How to avoid:**
- Validate the user-supplied instance hostname before any outbound fetch: require it resolve to a public, non-reserved IP (reject RFC1918/loopback/link-local/metadata-service ranges), require `https://`, and consider an allowlist-by-pattern or at minimum a strict format check (valid public domain, not an IP literal at all) since real Mastodon/Pleroma/Akkoma instances are always domain-named.
- Set a short timeout and do not follow redirects blindly on the discovery fetch (an attacker-controlled instance responding with a redirect to an internal address is a classic SSRF bypass of naive hostname checks).
- Do not reflect raw response bodies/errors from the instance-discovery fetch back to the client; return a generic "could not reach that instance" on failure.
- This is exactly the kind of check that's easy to defer as "we'll add validation later" — treat it as a blocking requirement for the Mastodon provider, not a follow-up.

**Warning signs:** No hostname/IP-range validation exists before the `.well-known` fetch; the discovery code follows redirects with default HTTP client settings; error messages from the discovery fetch include raw upstream response content.

**Phase to address:** OAuth completion phase (Mastodon provider, instance discovery) — SSRF validation must land with the initial instance-discovery implementation, not be treated as post-launch hardening.

---

### Pitfall 8: IndieAuth localhost bypass flag reachable via config drift rather than code

**What goes wrong:** The codebase already documents (CONCERNS.md) that `validate_url()` accepts `http://localhost` when `allow_localhost=True`, and the *code-level* gate looks fine (an explicit parameter). The actual risk in practice is almost never "someone edits the code to pass `True`" — it's an environment/config value (an env var, a settings flag, a feature flag service) that's `True` in staging and gets silently carried into a prod config template, prod `.env` copied from staging, or a container image built from a dev Dockerfile stage that never got its debug flag flipped.

**Why it happens:** Config-driven security gates are safe only if the *provenance* of the config value is itself verified per-environment; "gated behind a parameter" (as CONCERNS.md phrases it) is necessary but not sufficient — the question is what sets that parameter's value in each deployment target, and whether that's audited.

**How to avoid:**
- Grep/assert at prod startup: fail fast (refuse to boot) if `allow_localhost`-equivalent config is `True` while any other "this is production" indicator (e.g. `ENV=production`, absence of a debug flag) is also set — a runtime self-check, not just a code review comment.
- Never derive `allow_localhost` from anything that could be user-supplied or request-scoped (CONCERNS.md's recommendation is correct — confirm it's not request-derived) — but go further and add an automated deployment-config lint that flags this flag as `True` outside a declared dev/staging environment list.
- Add this specific check as a release-branch gate item (the project's Git workflow already has `release/0.2.0` → `main` — a deploy-config check belongs in that gate).

**Warning signs:** `allow_localhost` (or equivalent) is set via a `.env` file that's copied wholesale between environments rather than per-environment secret/config management; no startup assertion exists that would refuse to boot with the flag on in prod.

**Phase to address:** OAuth completion phase / release-hardening pass before v0.2.0 ships — add the startup assertion as an explicit test in the release checklist.

---

### Pitfall 9: Two-contributor verification is a Sybil/sockpuppet target by construction

**What goes wrong:** A "second independent contributor confirms the same fingerprint" model (documented in the spec §4.3, "Awaiting verification from a second contributor") is exactly the crowdsourced-trust pattern Sybil attacks target: an attacker creates two (or more) accounts and self-confirms their own bad submission, promoting a false/malicious disc entry straight to `verified` status with zero real independent confirmation. This is materially easier here than in comparable systems (e.g. Wikipedia edit review) because the "proof of independence" is currently just "a different `user_id` submitted a matching fingerprint" — nothing ties the confirmation to actual possession of a distinct physical disc.

**Why it happens:** Two-account creation is cheap (the spec's own account-creation flow supports email+password, and OAuth signup is a few clicks per provider), and the confirmation signal (fingerprint match) is by design something anyone with the *data*, not necessarily the disc, could resubmit if they saw the first submission's payload (e.g. via the public API's error/lookup responses, or simply by knowing the film/edition and guessing structural values).

**Why it's worse for OVID specifically:** Fingerprints (especially Tier 2 structural hashes) are computed from disc-structure facts that, once one submission exists, may be partially inferable/replayable without owning the disc (duration, chapter count, track languages for a known edition are sometimes public knowledge, e.g. from Blu-ray.com technical specs pages) — lowering the bar for a sockpuppet's "second confirmation" even below "create two accounts."

**How to avoid:**
- Treat account age/diversity signals, not just distinct `user_id`, as part of "independent" — e.g. weight confirmations from accounts created in the same short window, from the same IP/ASN, or with no other prior contribution history, as weaker evidence (flag for moderator review rather than auto-promoting to `verified`).
- Rate-limit/throttle *submission* volume per account more aggressively than per-IP alone (CONCERNS.md-listed abuse mitigation in the wider spec — "new accounts limited to 10 submissions/day" — is a start, but should also cap *verification/confirmation* actions per account per day, since a Sybil ring only needs enough confirmations to promote entries, not high raw submission volume).
- Never expose the exact fingerprint-derivation payload of an `unverified` disc via the public read API in a way that lets a second party "confirm" without independently computing it from a physical disc — if full submitted-track/structure data is publicly visible pre-verification, that's a blueprint for a fabricated "independent" second submission.
- Consider requiring at least one of the two confirming accounts to have some minimum trust signal (age, prior verified contributions, linked OAuth identity vs. bare email) before auto-promotion; below that bar, route to human/admin dispute review instead of automatic `verified` status.

**Warning signs:** Two confirmations from accounts created within minutes of each other / same IP; a disc's full submitted structural data is fetchable pre-verification via the public API; verification-count metrics per new account spike without corresponding submission-diversity (same account confirming many discs no other established contributor has touched).

**Phase to address:** Two-contributor verification workflow phase — build basic anti-Sybil heuristics (account-age/IP-diversity weighting, confirmation rate limits, no-full-payload-leak-pre-verification) into the verification logic itself, not as a v0.3 "community dispute flagging" follow-on (that's explicitly deferred per PROJECT.md Out of Scope — meaning the *baseline* abuse resistance in the verification model needs to be solid enough to survive without it for the v0.2.0 window).

---

### Pitfall 10: Redis migration for rate limiting is assumed to be a one-line `storage_uri` swap, but changes failure-mode and startup ordering

**What goes wrong:** The documented fix ("switch `storage_uri` to a Redis URL," already noted in the module's own docstring per CONCERNS.md) is correct in principle, but teams commonly under-scope the migration to just that config line and miss: (1) Redis becomes a new hard dependency in the request path — if Redis is unreachable, does the rate limiter fail open (no limiting — an abuse-prevention regression) or fail closed (503 on every request — an availability regression)? Both are wrong defaults if not deliberately chosen. (2) Container/deploy startup ordering — if the API container starts before Redis is ready (common in Docker Compose without explicit `depends_on`+healthcheck), early requests either bypass limiting or the app crashes at import/init time. (3) Existing in-memory counters mid-migration: a rolling deploy where some gunicorn workers still run old in-memory config and others run new Redis config produces inconsistent enforcement during the rollout window itself.

**Why it happens:** slowapi's Redis backend is well-documented as "just pass a redis:// URI," which is accurate for the happy path but doesn't surface the operational failure-mode decision that a shared external dependency in the hot path always introduces — this is a known, repeatedly-hit pitfall for teams moving from in-memory to Redis-backed rate limiting generally, not specific to slowapi.

**How to avoid:**
- Explicitly decide and document fail-open vs. fail-closed behavior when Redis is unreachable (fail-open is usually the pragmatic choice for a metadata-lookup API where availability matters more than perfect abuse resistance, but it must be a decision, not a default nobody chose).
- Add a Docker Compose `depends_on: redis: condition: service_healthy` (or equivalent orchestration health-gate) so the API doesn't serve requests before Redis is reachable.
- Since this is explicitly called out as needing validation with a load test (PROJECT.md Active: "API response time ≤500ms at p95 under load"), run that load test *with* Redis-backed rate limiting in place, not before — Redis round-trips on every request add latency that in-memory counters didn't have, and this could be the difference between meeting and missing the p95 budget.
- During rollout, prefer a full stop/start (not rolling) of gunicorn workers when switching storage backends, or accept and document a brief inconsistent-enforcement window.

**Warning signs:** No explicit fail-open/fail-closed decision documented anywhere; Compose file lacks a Redis health-gate; the p95 load test was run before Redis-backed limiting was in place and never re-run after.

**Phase to address:** Rate-limiting/Redis migration phase — the load-test exit criterion should explicitly be run against the Redis-backed configuration, and the fail-open/fail-closed decision should be an explicit line in that phase's plan, not an implementation detail.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip Tier 1/Tier 2 alias cross-matching for BD (treat as two unrelated fingerprint spaces) | Faster to ship Blu-ray fingerprinting | Verification workflow silently stalls for any disc where contributors' environments differ (Pitfall 3) | Never — build on the same alias-resolution path as ADR 0001 from day one |
| Auto-promote to `verified` on any two distinct `user_id` confirmations | Simple, fast verification UX | Sockpuppet/Sybil promotion of bad data with no real independent confirmation (Pitfall 9) | Only with basic account-age/IP-diversity heuristics in place; never as pure `user_id != user_id` |
| One-time Apple client-secret JWT generated manually and left until it errors | No upfront automation work | Production auth outage months later with a confusing error (Pitfall 6) | Never — automate rotation before Apple provider ships |
| Fetch Mastodon instance `.well-known` with default HTTP client (no hostname/redirect validation) | Fastest path to working federation login | SSRF against internal services (Pitfall 7) | Never — validation must ship with the feature |
| In-memory rate limiting kept "for now" post-migration decision because Redis adds ops complexity | Avoids a new infra dependency | Effective limit scales with worker count in prod, already documented as a known defect | Only acceptable for single-worker dev/local, never for the gunicorn prod deployment target |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `libaacs`/AACS Disc ID | Assuming Tier 1 uniqueness holds across regional/reprint variants without evidence | Model as a Lookup Alias like `dvdread1-*`, surface mismatches to dispute workflow, don't silently merge or split (Pitfall 2) |
| Apple Sign In | Treating the client-secret JWT as a set-and-forget credential | Automate regeneration inside the 6-month ceiling; verify raw `R\|\|S` signature encoding, not DER (Pitfall 6) |
| Mastodon / ActivityPub instances | Treating `.well-known` discovery as a trusted, risk-free metadata fetch | Validate hostname against reserved/internal IP ranges, disable redirect-following, never reflect raw responses (Pitfall 7) |
| GitHub/Google/Apple email-verified claims | Trusting a provider's `email` field as automatically verified for merge purposes | Check the provider's actual verified-email boolean/API field per-provider; never trust Mastodon email for merge at all (Pitfall 5) |
| slowapi + Redis | Treating the storage swap as a config-only change | Decide fail-open/closed explicitly, add health-gated startup ordering, re-run the p95 load test against Redis (Pitfall 10) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| In-memory slowapi counters under gunicorn `-w N` | Effective rate limit is up to Nx nominal (already documented in CONCERNS.md) | Redis-backed shared storage with explicit fail-open/closed decision | Any prod deployment with >1 worker — already broken today, not a future-scale concern |
| Redis round-trip added to every request's rate-limit check | p95 latency creeps toward/past the 500ms budget under load | Load-test specifically with Redis in place before declaring the p95 criterion met; consider a local short-TTL cache in front of Redis if latency is marginal | Becomes visible only under the load test the milestone already requires — don't skip re-running it post-migration |
| Full obfuscation-playlist BD structure parsed and hashed per lookup instead of cached | Slow disc-identity computation on 800+-playlist discs, on the client side (not server, but affects ARM's non-blocking 5s timeout budget) | Client-side computation should stay well inside ARM's existing 5s non-blocking timeout; profile against a real obfuscation-heavy disc, not just clean fixtures | Any UHD major-studio disc with maximal decoy playlists |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting provider `email_verified`-equivalent fields without per-provider validation | Full account takeover via email-match merge (industry-documented pattern: Nhost GHSA-6g38-8j4p-j3pr, nOAuth-class bugs) | Validate each provider's actual verified-email claim independently; gate merge behind existing-account re-auth; add isolated `finalize_auth` tests |
| Mastodon instance-discovery fetch with no hostname/IP validation | SSRF against internal infrastructure via attacker-supplied instance URL | Reject reserved/internal IP ranges, require HTTPS + valid public domain, no redirect-following, no raw-response reflection |
| `allow_localhost` IndieAuth flag driven by copy-pasted env config across environments | HTTPS bypass reaching production | Startup self-check that refuses to boot if the flag is `True` alongside any prod indicator |
| Two-contributor verification with no anti-Sybil signal beyond distinct `user_id` | Malicious/false disc entries promoted to `verified` cheaply | Weight account-age/IP-diversity/prior-contribution signals; rate-limit confirmation actions per account, not just submissions |
| Full submitted structural payload of `unverified` discs publicly readable pre-verification | Lets a sockpuppet "confirm" without ever touching the physical disc | Withhold full structural payload (or at minimum the raw canonical hash-input string) from public read responses until `verified` |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|------------------|
| Cross-tier BD verification silently stuck at `unverified` because two contributors' environments produced different tiers | Legitimate contributors think verification is broken/ignored | Cross-tier alias matching (Pitfall 3) so Tier 1 and Tier 2 submissions of the same disc match each other |
| "Awaiting verification from a second contributor" gives no feedback on *why* a second submission didn't match | Users can't tell if their disc is a genuine new edition or a fingerprinting bug | Surface a diagnostic (e.g., "closest existing entry differs in track count") on submission when a near-miss exists, rather than a bare unverified state |
| Merge prompt copy ("Link this GitHub login to that account?") implies a simple choice, hiding the security-critical re-auth step | Users may not realize/complete the required existing-account proof-of-ownership step, silently failing the security model's key control | Make the existing-account re-auth an explicit, unskippable step in the UI flow, not an implementation detail behind a button |

## "Looks Done But Isn't" Checklist

- [ ] **Blu-ray Tier 1/Tier 2 fingerprinting:** Often missing cross-tier alias resolution — verify a Tier 1 submission and a Tier 2 submission of the *same physical disc* actually match in the verification workflow, not just that each tier's hash is individually deterministic.
- [ ] **libdvdread migration Phase 2/3:** Often missing a `dvd1-*`-still-resolves regression test — verify old fingerprints served before the migration still 200 with correct data after Phase 3 ships, via an automated test that runs in every future CI run, not a one-time manual check.
- [ ] **Multi-provider OAuth "working end-to-end":** Often missing isolated tests for the shared `finalize_auth` merge/link path — verify each of (a) verified-email merge, (b) unverified-email merge rejection, (c) merge without existing-account re-auth rejection has a dedicated passing test, not just that each provider's happy-path callback test passes individually.
- [ ] **Mastodon instance discovery:** Often missing SSRF-class hostname/IP validation — verify a request with `instance_url` pointed at a loopback/link-local/metadata-service address is rejected before any outbound fetch happens.
- [ ] **Apple Sign In "working":** Often missing secret-rotation automation — verify there's a scheduled/automated regeneration process for the client-secret JWT, not just that login works today.
- [ ] **Redis-backed rate limiting:** Often missing an explicit fail-open/fail-closed decision and startup health-gating — verify the API's behavior (not just "it started") when Redis is down at boot and when Redis becomes unreachable mid-run.
- [ ] **Two-contributor verification "live":** Often missing any anti-Sybil signal beyond distinct account IDs — verify confirmation actions are rate-limited/weighted per account, and that full pre-verification structural payloads aren't publicly fetchable.
- [ ] **p95 ≤500ms load test:** Often run against a config that doesn't match the eventual prod deployment (e.g., before Redis-backed rate limiting lands) — verify the load test that satisfies the exit criterion runs against the actual Redis + gunicorn multi-worker configuration.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| `dvd1-*` lookups silently broken by Phase 3 promotion | HIGH | Add the alias back to the resolution path immediately; audit all endpoints/queries for raw `fingerprint =` equality checks and route them through the shared resolver; backfill a regression test before any further disc-lookup changes ship |
| Sockpuppet-verified bad disc entries discovered post-launch | MEDIUM | Since v0.2.0 explicitly defers full dispute-flagging UI to v0.3.0, fall back to admin-role manual correction (already modeled via `role` column and `verified_by`); add retroactive account-age/IP-diversity heuristic to flag suspect existing "verified" rows for review |
| Apple client secret expired in prod | LOW | Regenerate the ES256 JWT and redeploy — fast fix once diagnosed, but diagnosis time is the real cost if no monitoring existed; add the rotation automation immediately after |
| Redis outage causes rate-limit fail-closed (all requests 503) | MEDIUM | Requires an emergency config flip to fail-open or a temporary in-memory fallback; this is exactly why the fail-open/closed decision must be made *before* incident time, not during one |
| AACS Tier 1 collision merges two distinct regional editions into one disc row | MEDIUM | Split via admin tooling once identified; the Lookup Alias model (already being built for ADR 0001) should make "this fingerprint actually maps to two discs" a correctable data operation, not a schema migration |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Obfuscation-playlist Tier 2 instability (#1) | Blu-ray/UHD fingerprinting | Fixture corpus includes a heavily-obfuscated real disc; filter/sort constants documented as versioned spec |
| AACS regional/reprint variance unverified (#2) | Blu-ray/UHD fingerprinting + bulk-seed | Manual review flag for multi-region titles during ≥500-entry seeding; Tier 1 collisions route to dispute, not silent merge |
| Cross-tier verification stall (#3) | ADR 0001 Phase 2 + Blu-ray fingerprinting (shared alias-resolution code) | Test: Tier 1 submission + Tier 2 submission of same disc reach `verified` together |
| `dvd1-*` fragmentation during migration (#4) | ADR 0001 Phase 2/3 | CI regression test asserting `dvd1-*` lookups still 200 with correct data, run on every PR indefinitely |
| Email-merge account takeover (#5) | OAuth completion (all 4 providers) | Isolated `finalize_auth` tests: verified-merge success, unverified-merge rejection, merge-without-reauth rejection |
| Apple client secret expiry (#6) | OAuth completion (Apple) | Rotation automation exists and is tested; expiry monitoring/alerting in place |
| Mastodon SSRF via instance discovery (#7) | OAuth completion (Mastodon) | Test: request with internal/reserved-IP `instance_url` is rejected pre-fetch |
| IndieAuth localhost bypass reaching prod (#8) | OAuth completion / release-hardening gate | Startup assertion test: app refuses to boot with `allow_localhost=True` + prod indicator set |
| Sockpuppet/Sybil verification abuse (#9) | Two-contributor verification workflow | Confirmation actions rate-limited per account; pre-verification structural payload not publicly exposed |
| Redis rate-limit migration operational gaps (#10) | Rate limiting / Redis migration | Fail-open/closed decision documented; Compose health-gate present; p95 load test re-run against Redis config |

## Sources

- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` (project source — HIGH confidence, primary source of migration intent)
- `docs/OVID-technical-spec.md` §2 (Fingerprinting Spec), §4.2–4.4 (Auth/API) (project source — HIGH confidence)
- `.planning/codebase/CONCERNS.md` (project source — HIGH confidence, existing known issues)
- [matrix256: A Pressing-Level Disc Fingerprint](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) — MEDIUM-HIGH confidence (single independent author, but directly on-topic technical analysis with a stated 69-disc evaluation corpus); informed Pitfall 1 and the "not tamper-proof" framing in Pitfall 2
- [nOAuth: How Microsoft OAuth Misconfiguration Can Lead to Full Account Takeover — Descope](https://www.descope.com/blog/post/noauth) — MEDIUM-HIGH confidence (named security vendor research)
- [Nhost OAuth Account Takeover via Email Verification Bypass — GHSA-6g38-8j4p-j3pr](https://github.com/advisories/GHSA-6g38-8j4p-j3pr) — HIGH confidence (GitHub Security Advisory / CVE-backed)
- [Saying "No Thanks" to nOAuth — Okta Security](https://sec.okta.com/articles/2023/08/saying-no-thanks-noauth/) — HIGH confidence (vendor security team)
- [Apple client secrets will eventually expire — better-auth GitHub issue #1522](https://github.com/better-auth/better-auth/issues/1522) — MEDIUM confidence (community-reported, but consistent with Apple's own documented 6-month JWT ceiling)
- [Apple Developer Forums — ES256 signature encoding thread](https://developer.apple.com/forums/thread/123723) — MEDIUM confidence (official forum, community-explained technical detail)
- [Mastodon OAuth documentation](https://docs.joinmastodon.org/spec/oauth/) — HIGH confidence (official docs)
- [RFC 8414 `.well-known/oauth-authorization-server` support — mastodon/mastodon issue #24099](https://github.com/mastodon/mastodon/issues/24099) — HIGH confidence (official repo issue)
- [Redirect URIs for local, staging, and production — WorkOS](https://workos.com/blog/redirect-uris-for-local-staging-and-production) — MEDIUM confidence (vendor blog, general OAuth best-practice guidance, not IndieAuth-specific)
- [slowapi Redis multi-worker issue — GitHub issue #226](https://github.com/laurentS/slowapi/issues/226) — MEDIUM-HIGH confidence (issue directly on the library in use)
- [Sybil attack — Wikipedia](https://en.wikipedia.org/wiki/Sybil_attack) — MEDIUM confidence (general reference, not domain-specific to media-metadata crowdsourcing; no MusicBrainz-specific sockpuppet documentation was found — this is a general-pattern application, flagged as such in Pitfall 9)
- AACS regional/MKB-renewal specifics (Pitfall 2) — LOW confidence; general AACS/MKB documentation confirms MKB renewal exists across the ecosystem, but no source specifically confirms or denies same-Unit-Keys-file-across-regions behavior — flagged as an open question for the team to validate empirically during Blu-ray fixture collection, not asserted as fact

---
*Pitfalls research for: OVID v0.2.0 remaining scope (disc fingerprinting, libdvdread migration, OAuth, verification, rate limiting)*
*Researched: 2026-07-05*
