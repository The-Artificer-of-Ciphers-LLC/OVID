# Domain Pitfalls

**Domain:** Community disc identification database (alpha-to-beta transition)
**Researched:** 2026-04-04
**Confidence:** HIGH (based on codebase analysis + domain precedent from MusicBrainz, FreeDB, CDDB)

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or security incidents at beta launch.

### Pitfall 1: JWT in URL Query Parameters Leaks Long-Lived Tokens

**What goes wrong:** `finalize_auth()` (auth/routes.py:114) constructs redirect URLs with the JWT as a query parameter: `?token={jwt_token}`. JWTs are 30-day refresh tokens. Query parameters appear in browser history, HTTP Referer headers sent to third-party resources on the redirect target page, server access logs, proxy logs, and CDN edge logs. A single leaked token grants 30 days of authenticated API access with no revocation mechanism.

**Why it happens:** OAuth callback flows need to pass the token from the API server back to the web frontend. URL query params are the easiest redirect mechanism. The pattern works in development but the security implications only matter at scale with real users.

**Consequences:** Token theft via log aggregation, browser extension access to history, shared computers, or corporate proxy inspection. Combined with the absence of token revocation (CONCERNS.md), a leaked token cannot be invalidated until natural 30-day expiry.

**Prevention:**
1. Replace query param redirect with a short-lived authorization code flow: generate a single-use code, redirect with `?code=X`, frontend exchanges code for JWT via POST within 60 seconds.
2. Alternatively, set the JWT in an HttpOnly secure cookie during the redirect, then have the frontend read it from the cookie.
3. Add a `token_blacklist` table checked on every authenticated request so compromised tokens can be revoked immediately.

**Detection:** Search access logs and reverse proxy logs for `token=eyJ` patterns. If found, those tokens are already exposed.

**Phase mapping:** P0 security fixes -- must ship before any public user touches the auth flow.

---

### Pitfall 2: Race Condition in Mastodon Dynamic Registration Causes Silent Account Creation Failures

**What goes wrong:** `get_or_register_client()` (mastodon.py:43-97) does a read-then-write without any locking. Two users from the same Mastodon instance hitting login simultaneously will both pass the `db.query(...).filter_by(domain=domain).first()` check (returns None for both), both register with the Mastodon instance (creating duplicate OAuth apps on the remote server), then one commit succeeds and the other hits a unique constraint violation, returning a 500 to the user.

**Why it happens:** The classic TOCTOU (time-of-check-to-time-of-use) pattern. Common in OAuth dynamic registration because it only triggers when two users from the same previously-unseen instance arrive within milliseconds of each other -- rare in testing, common at launch when someone posts "check out this new project" on a Mastodon instance.

**Consequences:** First-time users from a popular Mastodon instance (e.g., mastodon.social) get a 500 error on their first login attempt. Orphaned OAuth app registrations accumulate on the remote Mastodon instance. Users retry, it works (because the first commit succeeded), but first impressions are damaged.

**Prevention:**
1. Use PostgreSQL `INSERT ... ON CONFLICT (domain) DO NOTHING` with a `RETURNING` clause, or catch `IntegrityError` and retry the read.
2. Wrap the check-register-insert in a database advisory lock keyed on the domain hash: `SELECT pg_advisory_xact_lock(hashtext('mastodon:' || domain))`.
3. Add a retry decorator (max 2 retries) that catches `IntegrityError` and re-reads from the database.

**Detection:** Search logs for `mastodon_registration` followed by IntegrityError or 500 status codes. Monitor for duplicate OAuth app registrations on the same domain.

**Phase mapping:** P0 security fixes -- fix alongside other Mastodon auth hardening.

---

### Pitfall 3: DNS Rebinding Bypasses Mastodon Domain SSRF Protection

**What goes wrong:** `validate_mastodon_domain()` (mastodon.py:15-40) resolves the domain via `socket.gethostbyname()` and checks if the IP is private. But DNS resolution is not atomic with the subsequent HTTPS request. An attacker controls a domain that resolves to a public IP during validation, then rebinds to `127.0.0.1` or `169.254.169.254` (cloud metadata endpoint) before the actual HTTP request in `get_or_register_client()`. The SSRF check passes, but the registration request hits an internal service.

**Why it happens:** DNS has a TTL and resolvers cache independently. The validation function resolves once, the httpx client resolves again. The two resolutions can return different IPs.

**Consequences:** Attacker can make the OVID server send POST requests to internal services (localhost, cloud metadata, internal APIs). On cloud infrastructure, this can leak instance credentials, IAM tokens, or internal service data. Even on bare metal (holodeck), it can probe internal network services.

**Prevention:**
1. Pin the resolved IP and pass it directly to httpx: resolve the domain once, validate the IP, then use httpx with `transport=httpx.HTTPTransport(local_address=...)` or construct the URL with the IP and set the Host header manually.
2. Alternatively, use a DNS resolver that returns all records and validate all of them, combined with a custom httpx transport that rejects connections to private ranges at the socket level.
3. Rate limit domain registration to 3 new domains per hour globally (not per user) to make exploitation impractical.
4. Maintain a blocklist of known-bad domains (e.g., domains associated with hate speech instances like gab.com, as noted in CONCERNS.md).

**Detection:** Monitor for Mastodon registration attempts where the domain resolves to different IPs across requests. Alert on any registration where the POST target IP differs from the validated IP.

**Phase mapping:** P0 security fixes -- ship before beta announcement.

---

### Pitfall 4: Bare Exception Handler in Disc Submission Swallows Data Integrity Failures

**What goes wrong:** `submit_disc()` (disc.py:501-506) catches bare `Exception` after a multi-step transaction (create release, create disc, link them, create titles/tracks, assign seq numbers, create audit entry). Any failure -- constraint violation, serialization error, logic bug -- returns a generic 500 with "Failed to submit disc" and logs `disc_submit_failed` without the actual exception type or details in the API response.

**Why it happens:** Defensive programming taken too far. The catch-all was likely added to prevent unhandled exceptions from leaking stack traces to users. But it also prevents legitimate errors (duplicate fingerprint race, invalid foreign key, schema mismatch) from being diagnosed.

**Consequences:** Users get unhelpful error messages. Partial failures before `db.commit()` are rolled back correctly (the `db.rollback()` is there), but the root cause is invisible to both the user and the developer triaging the issue. At beta scale with multiple concurrent submitters, intermittent failures will be impossible to diagnose from user reports alone.

**Prevention:**
1. Catch specific exceptions: `IntegrityError` (duplicate fingerprint, FK violation), `DataError` (bad data types), `ValidationError` (schema mismatch). Return appropriate 409/422/400 responses with structured error bodies.
2. Let unexpected exceptions propagate to FastAPI's default exception handler, which will return 500 but log the full traceback.
3. Use database savepoints (`db.begin_nested()`) around the title/track creation loop so a single bad track doesn't roll back the entire submission.
4. Add a `request_id` to all error log entries (already available via `request.state.request_id`) so users can report the request_id for support.

**Detection:** Monitor for `disc_submit_failed` log entries. If the rate exceeds 1% of submissions, the catch-all is hiding a systematic bug.

**Phase mapping:** P0 bug fixes -- fix before users start submitting their collections.

---

### Pitfall 5: In-Memory Rate Limiting Is Completely Ineffective with Multiple Workers

**What goes wrong:** `rate_limit.py:68` uses `storage_uri="memory://"`. Each gunicorn worker process has an independent counter. With 4 workers, the effective rate limit is 4x the configured value (400/min unauthenticated instead of 100/min). Workers are assigned via round-robin, so an attacker hitting the server at 399 requests/minute will never trigger any individual worker's 100/min limit.

**Why it happens:** `memory://` is the simplest slowapi storage backend and works correctly in single-process development (`uvicorn` without workers). The issue only manifests in production with multiple workers.

**Consequences:** Rate limiting provides zero protection against abuse. Automated scrapers can enumerate the entire database. Brute-force auth attempts are unrestricted. DoS attacks are not mitigated. This is especially dangerous because auth endpoints have no separate rate limits (CONCERNS.md).

**Prevention:**
1. Add Redis to the Docker Compose stack and switch `storage_uri` to `redis://redis:6379/0`.
2. Add explicit, tighter rate limits to auth endpoints: 5/min per IP for `/v1/auth/*/login`, 10/min per IP for `/v1/auth/*/callback`.
3. Add a health check that verifies Redis connectivity at startup -- if Redis is unreachable, fail loudly rather than silently falling back to in-memory.

**Detection:** Send 200 requests in 1 minute from a single IP to any rate-limited endpoint. If all succeed, rate limiting is broken.

**Phase mapping:** P0 infrastructure -- must ship before public announcement or any abuse is unmitigated.

---

### Pitfall 6: Placeholder Email Collisions Break Mastodon User Registration at Scale

**What goes wrong:** `users.py:82` generates placeholder emails as `mastodon_{account_id}@noemail.placeholder`. Mastodon account IDs are per-instance integers (not globally unique). User #12345 on mastodon.social and user #12345 on infosec.exchange generate the same placeholder email, causing a unique constraint violation. The second user cannot create an account.

**Why it happens:** The developer assumed Mastodon account IDs are globally unique. They are only unique within a single instance. This works fine in alpha (all testers are on different instances or have different IDs by chance) but fails predictably at scale.

**Consequences:** Real users blocked from registering. The error manifests as a 500 or a confusing account merge (if the email conflict detection kicks in and links them to the wrong account). Account data corruption is possible.

**Prevention:**
1. Include the instance domain in the placeholder: `mastodon_{domain}_{account_id}@noemail.placeholder`.
2. Write a migration to update any existing placeholder emails that lack the domain component.
3. Add a unique constraint on `(provider, provider_id, provider_domain)` rather than relying on email uniqueness for deduplication.

**Detection:** Query for duplicate placeholder emails: `SELECT email, COUNT(*) FROM users WHERE email LIKE '%@noemail.placeholder' GROUP BY email HAVING COUNT(*) > 1`. Any results indicate corruption.

**Phase mapping:** P0 bug fixes -- must fix before Mastodon users beyond the alpha group try to register.

## Moderate Pitfalls

### Pitfall 7: Sync Protocol Has No Integrity Verification

**What goes wrong:** The sync diff endpoint (sync.py:62-114) returns disc records paginated by sequence number. Mirrors consume these by advancing `since` to `next_since`. But there is no checksum or hash chain linking records together. If a record is silently corrupted (bad UTF-8, truncated JSON, ORM serialization bug), the mirror ingests garbage data and has no way to detect it. There is also no mechanism for a mirror to verify it has received all records -- a gap in sequence numbers (from a deleted record or sequence reset) is indistinguishable from missing data.

**Prevention:**
1. Add a `sha256` field to each sync record containing a hash of the canonical JSON representation. Mirrors verify the hash after deserialization.
2. Include a `prev_hash` field that chains each record to the previous one (Merkle-chain style). Mirrors can detect gaps and request a full re-sync if the chain breaks.
3. Add a `/v1/sync/verify` endpoint that returns the SHA256 of all records up to a given sequence number, so mirrors can verify consistency without re-downloading everything.
4. Document the sync protocol formally in `docs/sync-spec.md` with error recovery procedures.

**Phase mapping:** P0 self-hosted node hardening -- sync consumers need integrity guarantees before relying on the data.

---

### Pitfall 8: CLI Binary Distribution Without Cross-Compilation Strategy

**What goes wrong:** PyInstaller cannot cross-compile. A macOS build only produces macOS binaries. A Linux build only produces Linux binaries. Building for both requires CI runners on each platform. Furthermore, PyInstaller bundles the Python interpreter and all dependencies, producing binaries of 50-150MB that may not work across Linux distributions (glibc version mismatches, OpenSSL version conflicts). The ovid-client depends on C libraries (libdvdread, libbluray, libaacs) that PyInstaller cannot bundle.

**Prevention:**
1. Do not distribute PyInstaller binaries for the initial beta. Distribute via `pip install ovid-client` (PyPI) and document the C library prerequisites per platform.
2. If binaries are desired, use GitHub Actions with matrix builds (ubuntu-latest, macos-latest) and test the output on clean VMs.
3. For Linux, build on the oldest supported glibc (e.g., manylinux2014 / CentOS 7 base) to maximize compatibility.
4. Document clearly that `libdvdread`, `libbluray`, and `libaacs` must be installed via the system package manager -- they cannot be bundled.
5. Consider a Homebrew formula for macOS and a `.deb`/`.rpm` for Linux that declare the C library dependencies.

**Phase mapping:** P0 CLI scanner tool -- choose distribution strategy before building the packaging pipeline.

---

### Pitfall 9: No Moderation Tooling Before Public Announcement

**What goes wrong:** MusicBrainz and similar community databases learned that moderation tooling must exist before the community arrives, not after. Without it, the first wave of users (including bad actors drawn by the public announcement) can submit garbage data, offensive content in edition names, or bulk-spam the database with fake entries. Reverting bad data without moderation tools requires direct database surgery.

**Prevention:**
1. Build an admin panel (even a simple one) before announcing: view recent submissions, ban users, revert submissions, bulk-delete by user.
2. Implement a submission rate limit per user (not just per IP): max 20 disc submissions per hour per authenticated user.
3. Add a "report" button on disc entries so community members can flag problems.
4. Require a minimum account age (24 hours) before first submission to prevent drive-by spam accounts.
5. Auto-flag submissions with suspicious patterns: identical metadata submitted for many different fingerprints, edition names containing URLs, extremely short session-to-submission time.

**Phase mapping:** P0 before public announcement -- the moderation guide in `docs/moderation.md` is planned but the tooling to execute moderation must exist first.

---

### Pitfall 10: OAuth Secret Leakage in Error Messages

**What goes wrong:** `mastodon.py:74` includes `str(e)` in the HTTPException detail for connection errors. If the httpx request fails after sending credentials, the exception message may contain partial request/response data including OAuth client secrets. FastAPI serializes HTTPException details into JSON responses visible to the caller.

**Prevention:**
1. Never include raw exception strings in API responses. Log the full exception server-side, return a generic error to the client.
2. Replace line 74 with: `raise HTTPException(status_code=502, detail={"error": "bad_gateway", "reason": "Failed to communicate with Mastodon instance"})` -- no `str(e)`.
3. Audit all other `HTTPException(detail=...)` calls for similar patterns.

**Phase mapping:** P0 security fixes.

---

### Pitfall 11: Disc Status State Machine Has No Validation

**What goes wrong:** Disc status transitions (unverified, verified, disputed) have no state machine enforcement. Any status can be set to any other status. A verified disc can be silently reverted to unverified. A disputed disc can be marked verified without resolution. The auto-verify logic in `submit_disc()` (disc.py:360) sets status to "verified" without checking if it's currently "unverified" -- if the disc is already "disputed", the second contributor's matching submission silently overrides the dispute.

**Prevention:**
1. Define an explicit state machine: `unverified -> verified` (via second contributor match), `unverified -> disputed` (via second contributor mismatch), `disputed -> verified` (via admin resolution), `disputed -> unverified` (via admin reset). Reject all other transitions.
2. Check current status before transition in `submit_disc()`: if status is "disputed", a matching second submission should not auto-verify -- it should be queued for admin review.
3. Log all state transitions in `disc_edits` with the previous and new status.

**Phase mapping:** P0 bug fixes -- data integrity depends on this.

## Minor Pitfalls

### Pitfall 12: Sync Snapshot Endpoint Returns 404 When No Dump Exists

**What goes wrong:** `/v1/sync/snapshot` (sync.py:129-161) returns 404 if any of the five required `sync_state` keys are missing. For a new mirror operator following the self-hosted guide, hitting 404 on snapshot is confusing -- it looks like the endpoint doesn't exist rather than "no snapshot has been generated yet." The error message includes the missing keys, which is good, but 404 is the wrong status code.

**Prevention:**
1. Return 200 with `{"available": false, "message": "No snapshot has been generated yet"}` or use 204 No Content.
2. Alternatively, generate the first snapshot as part of the 0.3.0 deployment checklist so the endpoint never returns 404 in production.

**Phase mapping:** Self-hosted node hardening.

---

### Pitfall 13: Global Sequence Counter Bottleneck Under Concurrent Writes

**What goes wrong:** The `next_seq()` function uses a single-row `global_seq` table with `FOR UPDATE` locking. At beta scale (handful of concurrent submitters), this is fine. But if ARM auto-submit becomes popular or batch CLI submissions are used, the single row becomes a write bottleneck. Every disc submission, verification, and dispute locks this row.

**Prevention:**
1. For 0.3.0 scale (hundreds of discs, single-digit concurrent writers): no change needed.
2. Monitor lock wait time on the `global_seq` row. If p95 exceeds 50ms, switch to PostgreSQL `SEQUENCE` objects which handle contention natively.
3. Document in the sync spec that sequence numbers are monotonically increasing but not necessarily contiguous (so future optimizations don't break mirrors).

**Phase mapping:** Post-beta monitoring. Not a 0.3.0 blocker.

---

### Pitfall 14: PyPI Package Name Squatting Window

**What goes wrong:** The `ovid-client` package name on PyPI is not yet registered. Between now and publication, someone else could register it (intentionally or coincidentally). Typosquatting attacks (e.g., `ovid_client`, `ovidclient`, `ovid-cli`) are also common on PyPI.

**Prevention:**
1. Register the `ovid-client` name on PyPI immediately with a minimal placeholder package (version 0.0.1 with just a README). This is standard practice.
2. Also register obvious typosquats: `ovidclient`, `ovid_client`, `oviddb`, `oviddb-client`.
3. Enable PyPI trusted publishers via GitHub Actions OIDC so only the CI pipeline can publish.

**Phase mapping:** Do this immediately, before any other PyPI work.

---

### Pitfall 15: First Public Announcement Without Sufficient Seed Data

**What goes wrong:** Community database projects that launch with too little data fail to demonstrate value. A user inserts a disc, gets a 404, and never returns. MusicBrainz succeeded partly because it had a large initial seed from FreeDB. OVID's target of 500 entries is reasonable for a beta but must cover the most common discs that early adopters are likely to own (popular titles, recent releases, box sets).

**Prevention:**
1. Prioritize seeding popular, commonly-owned discs over obscure titles. Target the top 100 best-selling Blu-rays and DVDs.
2. Track hit rate (lookups that return 200 vs 404) from the first day. If hit rate is below 10%, the seed data isn't covering real usage.
3. Make the "miss" experience good: when a disc isn't found, clearly explain how to submit it and make the submission flow fast (the auto-submit from ARM is already good here).
4. Consider a "most wanted" list based on 404 fingerprints to guide seeding priorities.

**Phase mapping:** Operational -- database seeding milestone before public announcement.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Security fixes (P0) | JWT URL params, DNS rebinding, and rate limiting are interconnected -- fixing one without the others leaves gaps | Fix all three as a single security hardening sprint |
| Mastodon auth hardening | Race condition fix may change DB schema (adding unique constraint) -- requires migration | Test migration on a copy of production data first |
| CLI scanner tool | C library dependencies (libdvdread, libbluray) vary across distros -- binary won't be portable | Ship pip package first, defer binary distribution |
| Self-hosted sync | Mirrors that started syncing during alpha may have inconsistent data after schema changes | Provide a "reset and re-sync from snapshot" procedure |
| Multi-disc set support | Adding `disc_set_id` FK to disc table is a schema migration on a table with real data | Use `ALTER TABLE ... ADD COLUMN ... DEFAULT NULL` to avoid table rewrite |
| Public announcement | First impression is permanent -- broken auth, missing data, or 500 errors will kill adoption | Stage a "soft launch" to ARM community (already engaged) before broader announcement |
| Chapter name data | New table with FK to disc_titles -- sync protocol must include chapters or mirrors diverge | Add chapter data to sync schema in the same release, not as a follow-up |
| PyPI publication | Package name not yet reserved | Register placeholder package immediately |
| Moderation tooling | No admin interface exists -- moderation requires direct DB access | Build minimum admin panel before announcement |
| Email/password auth (P1) | Adding a new auth method post-launch risks account linking bugs with existing OAuth users | Extensive testing of email+OAuth hybrid accounts before shipping |

---

*Pitfalls audit: 2026-04-04. Confidence: HIGH for codebase-specific pitfalls (derived from direct code analysis). MEDIUM for community/ecosystem pitfalls (derived from MusicBrainz/FreeDB precedent and general domain knowledge).*
