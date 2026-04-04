# Codebase Concerns

**Analysis Date:** 2026-04-04

## Tech Debt

**In-Memory Rate Limiting Broken in Distributed Deployments:**
- Issue: `api/app/rate_limit.py` uses `storage_uri="memory://"` with slowapi, creating independent counters per worker process. With gunicorn `-w N`, effective limit is N times the nominal value (e.g., 500 users × 4 workers = 2000/min instead of 500/min).
- Files: `api/app/rate_limit.py` (line 68)
- Impact: Rate limiting completely ineffective at scale. Abuse protection fails in production.
- Fix approach: Switch to Redis-backed storage (`redis://`) or in-process shared state. Requires REDIS_URL env var and redis-py dependency.

**Mastodon Registration Caching Lacks Cleanup:**
- Issue: `MastodonOAuthClient` rows accumulate in DB indefinitely. Once a Mastodon domain is registered (line 88-97 in `api/app/auth/mastodon.py`), the record lives forever. If a Mastodon instance becomes unreachable or credentials expire, there's no mechanism to invalidate/refresh cached registrations.
- Files: `api/app/models.py` (line 375-386), `api/app/auth/mastodon.py` (line 43-97)
- Impact: Stale credentials cause failed OAuth flows; no graceful recovery path.
- Fix approach: Add `expires_at` timestamp to `MastodonOAuthClient`, add periodic cleanup job (via APScheduler or async task), allow explicit reregistration via API endpoint.

**Apple Private Key Parsing Silently Fails:**
- Issue: `_load_apple_private_key()` in `api/app/auth/routes.py` (lines 216-234) catches all exceptions and returns `None`, masking real errors (corrupt key, wrong format). When `None` is returned, `generate_apple_client_secret()` raises `RuntimeError` downstream, but it's not caught in the callback handler.
- Files: `api/app/auth/routes.py` (lines 216-234, 243-245, 309-313)
- Impact: Apple Sign-In breaks silently at startup; users see generic 502 error instead of actionable message about key misconfiguration.
- Fix approach: Validate Apple key at startup in app initialization, raise clear `ConfigurationError` with details about what's wrong (invalid format, missing fields, etc.).

**Exception Handling Too Broad in Disc Submission:**
- Issue: `api/app/routes/disc.py` line 501 catches bare `Exception` during disc submit transaction. This swallows all errors (DB constraint violations, FK failures, logic bugs) and returns generic 500. No error details logged.
- Files: `api/app/routes/disc.py` (lines 501-506)
- Impact: Hard to debug submission failures; failed submissions leave orphaned records if flush succeeds but commit fails.
- Fix approach: Catch specific exceptions (SQLAlchemy IntegrityError, ValidationError), log with full context, ensure rollback on all paths.

**Auth Routes Pass Confidential Data in URL Redirect (Unsafe Pattern):**
- Issue: `api/app/auth/routes.py` line 114 constructs redirect URL with JWT token as query param: `redirect_url = f"{web_redirect_uri}{separator}{urlencode({'token': jwt_token})}"`. Query params are logged in browser history, server logs, and proxy logs.
- Files: `api/app/auth/routes.py` (lines 109-115)
- Impact: JWTs (long-lived 30-day tokens) can leak via access logs, browser history, referrer headers.
- Fix approach: Return token in POST response body instead, or use authorization code flow with secure session storage.

**Race Condition in Mastodon Dynamic Registration:**
- Issue: `get_or_register_client()` in `api/app/auth/mastodon.py` checks DB (line 45), then registers if missing (line 56-67), then commits (line 94). Between the check and commit, another request for the same domain can also register, causing unique constraint violation on domain.
- Files: `api/app/auth/mastodon.py` (lines 43-97)
- Impact: Concurrent auth requests for same Mastodon instance will fail intermittently with 500.
- Fix approach: Use database-level unique constraint with INSERT ON CONFLICT (PostgreSQL) or handle IntegrityError with retry logic.

## Known Bugs

**User Email Placeholder Collision Risk:**
- Issue: `api/app/auth/users.py` line 82 generates fallback email as `f"{provider}_{provider_id}@noemail.placeholder"` for providers that don't return email (Mastodon, IndieAuth). Line 74 skips conflict check if email ends with `@noemail.placeholder`. But if two different Mastodon users on different instances have the same account_id, both generate identical `mastodon_{account_id}@noemail.placeholder` email, causing unique constraint violation.
- Files: `api/app/auth/users.py` (lines 74-77, 82)
- Impact: Users on different Mastodon instances can't sign up if they have the same numerical account_id.
- Fix approach: Include domain in placeholder email: `mastodon_{domain}_{account_id}@noemail.placeholder`.

**Disc Status Transition Has No Validation:**
- Issue: `api/app/routes/disc.py` allows any status transition without validation. A verified disc can be reverted to unverified, or jumped directly to disputed. No audit trail enforces state machine rules.
- Files: `api/app/routes/disc.py` (lines 221-227)
- Impact: Data integrity issues; unclear disc state history.
- Fix approach: Define explicit allowed transitions (unverified→verified, unverified→disputed, disputed→verified, disputed→unverified). Validate in `resolve_dispute()` and reject invalid transitions.

## Security Considerations

**Mastodon Domain Validation Incomplete:**
- Risk: `validate_mastodon_domain()` in `api/app/auth/mastodon.py` (lines 15-40) checks for private IPs via `socket.gethostbyname()`, but doesn't validate against instance blocklist, check HTTP/2 or certificate issues, or handle DNS rebinding. Attacker could register a domain that resolves to a private IP, pass validation, then DNS change to point to private IP after check.
- Files: `api/app/auth/mastodon.py` (lines 15-40)
- Current mitigation: Basic private IP check.
- Recommendations: Add rate limit on domain registration, cache domain check results with 24-hour TTL, explicitly reject known problematic instances (gab.com, etc.), use DNS-over-HTTPS to prevent spoofing.

**JWT Secret Key Not Validated at Startup:**
- Risk: `OVID_SECRET_KEY` env var read at import time in `api/app/auth/config.py` without validation. If missing or too short, silent failure. Key should be ≥32 bytes for HS256.
- Files: `api/app/auth/config.py`
- Current mitigation: None.
- Recommendations: Validate key length and entropy at app startup, raise clear error if invalid.

**OAuth Client Secrets Logged in Error Messages:**
- Risk: `api/app/auth/mastodon.py` line 74 includes raw error string in HTTPException detail, which may contain partial credentials from failed response.
- Files: `api/app/auth/mastodon.py` (line 74)
- Current mitigation: Only client_secret returned from registration, not stored unsafely.
- Recommendations: Never include external service error text in API responses; log to server logs only.

**Placeholder Email Prediction Attack:**
- Risk: Placeholder email format is predictable (`{provider}_{provider_id}@noemail.placeholder`). Attacker knowing a Mastodon user's account_id can predict their OVID placeholder email and attempt account enumeration.
- Files: `api/app/auth/users.py` (line 82)
- Current mitigation: None.
- Recommendations: Hash or randomize placeholder email, or don't use email as user identifier.

## Performance Bottlenecks

**Sync Snapshot Generation Has N+1 Query:**
- Problem: `/v1/sync/snapshot` endpoint in `api/app/routes/sync.py` fetches sync_state rows, but each subsequent mirror request will re-fetch entire disc/release/track tables without pagination. Large databases (100k+ discs) will timeout.
- Files: `api/app/routes/sync.py`
- Cause: No limit on result set; full table scan on every snapshot request.
- Improvement path: Implement pagination for sync payload, or use database cursors to stream results.

**Rate Limit Key Function Called on Every Request:**
- Problem: `_auth_aware_key()` in `api/app/rate_limit.py` (line 26) decodes JWT on every request to distinguish authenticated users from IPs. JWT decoding has non-trivial CPU cost.
- Files: `api/app/rate_limit.py` (line 26-46)
- Cause: No caching of decoded tokens.
- Improvement path: Cache decoded token in request state after first decode, or use Redis to memoize token-to-user mappings.

**Search Query Uses LIKE Without Index:**
- Problem: `api/app/routes/disc.py` line 644 searches releases with `.filter(Release.title.ilike(f"%{q}%"))`. LIKE pattern with leading wildcard can't use B-tree index on title.
- Files: `api/app/routes/disc.py` (line 644)
- Cause: Full table scan on every search.
- Improvement path: Use PostgreSQL full-text search or trigram index, or add `tsvector` column with index.

## Fragile Areas

**Auth Routes Complex State Machine Without Tests:**
- Files: `api/app/auth/routes.py` (lines 71-124, 186-194, 374-381, etc.)
- Why fragile: Multiple OAuth providers (GitHub, Apple, Google, Mastodon, IndieAuth) each with slightly different token exchange and profile extraction. `finalize_auth()` helper handles user upsert, email conflict detection, explicit linking, implicit linking—all without comprehensive test coverage for error paths. Session state (link_to_user_id, web_redirect_uri, provider state tokens) can get out of sync.
- Safe modification: Add dedicated test for each provider's error path (token exchange timeout, malformed response, missing fields). Mock external OAuth servers. Test session state cleanup on every path.
- Test coverage: Tests exist for happy paths but error recovery (retry logic, stale session recovery) not covered.

**Disc Submission Transaction Logic Fragile:**
- Files: `api/app/routes/disc.py` (lines 338-506)
- Why fragile: Multi-step transaction: create release, create disc, link them, create titles+tracks, assign seq numbers, log edit. One failure partway through leaves orphaned records (release without disc, etc.). The catch-all exception handler (line 501) swallows all errors.
- Safe modification: Use database savepoints or break into smaller, composable operations. Test for partial failures.
- Test coverage: Only happy path tested; failures mid-transaction not exercised.

**Mastodon OAuth Flow Has Multiple External Dependencies:**
- Files: `api/app/auth/mastodon.py` (lines 43-97), `api/app/auth/routes.py` (lines 609-704)
- Why fragile: Depends on DNS resolution, TLS cert validation, HTTP response format from arbitrary Mastodon instances (user-specified domain). Instance may be slow, down, or return malformed JSON.
- Safe modification: Add timeouts (present), validate response structure before parsing (missing), add circuit breaker for repeated failures (missing), cache instance metadata.
- Test coverage: Only mock happy path; no tests for malformed responses, timeouts, or network errors.

## Scaling Limits

**In-Memory Rate Limiter Can't Scale Horizontally:**
- Current capacity: Each worker process has independent counter; effective limit = configured limit × number of workers.
- Limit: Breaks at 4+ workers (effective limit becomes 2000/min for 500/min setting).
- Scaling path: Switch to Redis-backed limiter (`redis://`).

**Global Sequence Counter Single-Row Bottleneck:**
- Current capacity: Handles ~1000 writes/sec on PostgreSQL (atomic increment + FOR UPDATE).
- Limit: Beyond 1000 concurrent writers, lock contention on `global_seq` row will cause request queuing.
- Scaling path: Use database-native sequence or UUID-based versioning (UUID + timestamp).

**Mastodon Instance Cache No Expiry:**
- Current capacity: Unbounded growth; one row per unique domain registered.
- Limit: DB bloat after 10k+ instances; client secrets can't be rotated.
- Scaling path: Add TTL and cleanup job.

## Dependencies at Risk

**Authlib Starlette Integration Limited:**
- Risk: `authlib` (line 10 in `api/app/auth/routes.py`) provides oauth client but lacks built-in token refresh, auto-retry, and circuit breaking. Custom implementation needed for production robustness.
- Impact: Auth failures not gracefully retried; user experience breaks on network blips.
- Migration plan: Consider moving to `python-oauth2` or in-house implementation with retry/timeout logic baked in.

**slowapi Rate Limiter Deprecated in favor of built-in:**
- Risk: `slowapi` (line 12 in `api/app/rate_limit.py`) is mature but low-maintenance. FastAPI 0.100+ has built-in rate limiting support.
- Impact: Potential for slow dependency updates, security patches lag.
- Migration plan: Evaluate FastAPI's native limiter (when available) or switch to `pyrate-limiter`.

## Missing Critical Features

**No Audit Trail for Non-Disc Entities:**
- Problem: Only discs have edit history (`disc_edits` table). User profile changes, auth provider linking/unlinking, role escalations not logged. Can't answer "who changed this setting when."
- Blocks: Compliance audit, abuse investigation, user support troubleshooting.

**No Rate Limiting on Authentication Endpoints:**
- Problem: OAuth login/callback endpoints (`/v1/auth/*/login`, `/v1/auth/*/callback`) have no explicit rate limits. Attacker can brute-force auth code guessing or spam login attempts.
- Blocks: Denial-of-service protection.
- Fix: Add rate limit (5/min per IP for login, 10/min per IP for callback).

**No JWT Token Revocation Mechanism:**
- Problem: Tokens are valid until expiry (30 days). No way to revoke token if user account is compromised or linked provider is unlinked.
- Blocks: Immediate revocation on security incident.
- Fix: Add `token_blacklist` table and check on every request.

## Test Coverage Gaps

**OAuth Error Paths Not Tested:**
- What's not tested: Network timeouts, malformed OAuth provider responses, missing fields in JWT, invalid signatures, JWKS fetch failures.
- Files: `api/app/auth/routes.py` (all OAuth callback handlers), `api/app/tests/test_auth_*.py`
- Risk: Silent failures in production; users get generic 502 instead of actionable error.
- Priority: High

**Mastodon OAuth Not Tested with Real Instance Simulation:**
- What's not tested: Domain validation (private IP rejection), dynamic registration race conditions, credential expiry.
- Files: `api/app/auth/mastodon.py`, `api/app/tests/test_auth_mastodon.py`
- Risk: Domain validation bypass, race condition not caught until production.
- Priority: High

**Disc Submission Concurrency:**
- What's not tested: Multiple users submitting same fingerprint simultaneously; auto-verify/dispute logic under race conditions; transaction rollback on partial failure.
- Files: `api/app/routes/disc.py`, `api/app/tests/test_disc_submit.py`
- Risk: Orphaned database records, lost updates, incorrect disc status.
- Priority: High

**Rate Limiting Edge Cases:**
- What's not tested: Rate limit key extraction with malformed JWT, expired token, missing Authorization header; limiter reset consistency; effective limit with multiple workers.
- Files: `api/app/rate_limit.py`, `api/app/tests/test_rate_limit.py`
- Risk: Rate limiting ineffective; potential DoS.
- Priority: Medium

---

*Concerns audit: 2026-04-04*
