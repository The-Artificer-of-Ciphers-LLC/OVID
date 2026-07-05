# Codebase Concerns

**Analysis Date:** 2026-07-05

## Tech Debt

**In-memory rate limiting does not scale across workers:**
- Issue: `slowapi` rate limiter uses in-memory storage, keyed per-process. Documented directly in the source as a known limitation.
- Files: `api/app/rate_limit.py` (see module docstring, `UNAUTH_LIMIT`/`AUTH_LIMIT` constants)
- Impact: Running the API with `gunicorn -w N` gives each worker an independent counter, so the effective rate limit becomes up to `N`x the nominal value (e.g. 500/minute becomes 2000/minute across 4 workers). Abuse mitigation is materially weaker than the configured limits imply.
- Fix approach: Switch `storage_uri` to a Redis URL for shared counter state across workers, as already noted in the module docstring.

**Ad-hoc Python patch scripts committed at repo root:**
- Issue: One-off scripts (`fix_test.py`, `fix_test2.py`) that perform string-replace edits directly on `api/tests/test_auth_mastodon.py` are checked into the repository root alongside `run_uat.py`, `verify_t11.py`, `create_uat_dirs.py`, and `test_script.py`.
- Files: `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py`, `create_uat_dirs.py`, `run_uat.py`
- Impact: These are throwaway migration/debug scripts, not part of the application or its test suite, but they live at the project root where they read as first-class tooling. `uat_results.json` is also committed at root, suggesting generated output is being checked in. This clutters the root directory and makes it unclear which scripts are load-bearing vs. disposable one-time patches.
- Fix approach: Delete the one-shot patch scripts (`fix_test.py`, `fix_test2.py`, `test_script.py`) now that their edits are already applied, or move any still-needed dev tooling (`run_uat.py`, `verify_t11.py`, `create_uat_dirs.py`) into `scripts/`. Add generated artifacts like `uat_results.json` to `.gitignore` rather than committing them.

**Triplicated ARM identify shim files:**
- Issue: `arm/identify.py`, `arm/identify_ovid.py`, and `arm/identify_original.py` overlap heavily by design — `identify.py` is a volume-mounted overlay shim that imports the renamed original (`identify_original.py`) as a fallback and delegates to `identify_ovid.py` for the OVID-specific lookup.
- Files: `arm/identify.py`, `arm/identify_ovid.py`, `arm/identify_original.py`, `arm/entrypoint_wrapper.sh`
- Impact: The mechanism (entrypoint renames ARM's real `identify.py` to `identify_original.py` at container start, then bind-mounts this shim in its place) is a fragile file-swap integration pattern. Any change to ARM's own internal `identify.py` contract (function signature at "main.py line ~94" per the comment) can silently break the integration since it is coupled by import convention, not by a versioned interface.
- Fix approach: Keep the shim, but add a startup assertion that ARM's `identify_original.py` exports the expected `identify(job)` signature (or pin the ARM image version this shim is validated against), so drift fails loudly instead of at runtime during a rip.

## Known Bugs

No reproducible bugs were identified in first-party code during this pass. `api/app/auth/indieauth.py:45` contains a deliberate dev-only bypass (`pass  # OK for dev` for `http://localhost` when `allow_localhost=True`) — confirm this flag is never set `True` in production configuration.

## Security Considerations

**Dev-mode localhost bypass in IndieAuth URL validation:**
- Risk: `validate_url()` accepts `http://localhost` (unencrypted) when called with `allow_localhost=True`, bypassing the otherwise-enforced HTTPS requirement.
- Files: `api/app/auth/indieauth.py:24-56`
- Current mitigation: Gated behind an explicit `allow_localhost` parameter that callers must opt into.
- Recommendations: Confirm the caller in `api/app/auth/routes.py` only passes `allow_localhost=True` when an explicit dev/debug environment flag is set, not based on user-supplied input.

**Secrets handling:** `SECRET_KEY` (JWT signing) is required via `_require_env("OVID_SECRET_KEY")` with no fallback default in `api/app/auth/config.py`, and OAuth client secrets (`GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_SECRET`) are read from environment variables with empty-string defaults rather than hardcoded values — this is a good pattern, not a concern, but worth confirming `.env` files are excluded from git (they are, per `.gitignore`).

## Performance Bottlenecks

**Rate limiter storage (see Tech Debt above)** also has performance implications: in-memory counters reset on worker restart and are not shared, so bursty traffic across workers is not smoothed.

No other significant bottlenecks were identified in first-party code; `api/app/routes/disc.py` (749 lines) is the largest single route module and merits watching as endpoint count grows (currently 10 endpoints in one file).

## Fragile Areas

**`api/app/routes/disc.py` (749 lines, 10 endpoints):**
- Files: `api/app/routes/disc.py`
- Why fragile: Single file covers disc lookup by fingerprint, UPC lookup, disputed-disc listing, dispute resolution, registration, submission, verification, edit history, and search — a wide responsibility surface in one module with several private helper functions (`_disc_to_response`, `_build_track_response`, `_releases_match`, `_identity_conflict_response`) shared across routes.
- Safe modification: Changes to shared helpers (e.g. `_disc_to_response`) affect every read endpoint; add/extend tests in `api/tests/test_disc_submit.py`, `api/tests/test_dispute.py`, and `api/tests/test_disc_identity_aliases.py` before modifying shared response-building logic.
- Test coverage: Reasonable — dedicated test files exist per concern (`test_dispute.py`, `test_disc_submit.py`, `test_disc_identity_aliases.py`, `test_foundation.py`), but no single test file covers the full `disc.py` surface, so cross-cutting refactors of the private helpers risk untested interactions.

**ARM identify shim (see Tech Debt above):**
- Files: `arm/identify.py`, `arm/entrypoint_wrapper.sh`
- Why fragile: Relies on a file-rename/bind-mount trick at container startup rather than a stable plugin API from the upstream ARM project. The contract ("ARM's main.py line ~94 calls `identify.identify(job)`") is documented only in a comment, not enforced.
- Safe modification: Do not change `lookup_ovid`'s return contract (must never raise; returns `None` on any failure) without updating `identify.py`'s calling code, since the "never blocks ripping" guarantee depends on it.

**Multi-provider auth routes (`api/app/auth/routes.py`, 742 lines):**
- Files: `api/app/auth/routes.py`
- Why fragile: Implements six OAuth/IndieAuth-style provider flows (GitHub, Apple, IndieAuth, Google, Mastodon, plus generic linking/unlinking) in one module, each with its own login/callback pair. Apple's flow additionally generates a signed ES256 JWT client secret (`generate_apple_client_secret`), a common source of expiry-related production bugs (Apple secrets expire and must be regenerated).
- Safe modification: Provider-specific test files exist (`test_auth_github.py`, `test_auth_apple.py`, `test_auth_indieauth.py`, `test_auth_linking.py`) — verify the relevant provider's test file passes before touching shared helpers like `finalize_auth`.
- Test coverage: Good — each provider has a dedicated test file; `finalize_auth` (the shared upsert/link/JWT-issue path) is exercised indirectly through all of them, but has no isolated unit test file of its own.

## Scaling Limits

**Rate limiting under multi-worker deployment:** see Tech Debt — effective throughput scales with worker count instead of being globally enforced. No other scaling limits (DB connection pool sizing, queue depth, etc.) were surfaced in this pass; recommend a dedicated STACK.md/ARCHITECTURE.md review for infra-level scaling limits (DB, ARM job queue).

## Dependencies at Risk

Not deeply assessed in this pass. `ovid-client/` vendors a `.venv` with pinned packages (pytest, pycdlib, click, rich, etc.) — standard virtualenv, not a risk in itself, but confirm `.venv` is excluded from version control (large directory tree observed under `ovid-client/.venv`).

## Missing Critical Features

Not assessed — out of scope for a concerns-only pass without product requirements context.

## Test Coverage Gaps

**`finalize_auth` shared helper lacks isolated tests:**
- What's not tested: The provider-agnostic user upsert / explicit-linking / implicit-linking / JWT-issuance logic in `finalize_auth` (`api/app/auth/routes.py:71`) is only exercised indirectly via each provider's callback tests.
- Files: `api/app/auth/routes.py:71`, provider test files under `api/tests/test_auth_*.py`
- Risk: A regression in `finalize_auth` could pass all provider tests individually if each test's fixture data happens to avoid the buggy branch (e.g. implicit-linking edge cases), while still breaking a provider combination not covered by any single test file.
- Priority: Medium

**Root-level UAT/verification scripts are not part of the automated test suite:**
- What's not tested: `run_uat.py`, `verify_t11.py`, `create_uat_dirs.py` appear to be manual/UAT verification tooling (per `uat_results.json` output) rather than CI-integrated tests.
- Files: `run_uat.py`, `verify_t11.py`, `create_uat_dirs.py`, `uat_results.json`
- Risk: If these encode real acceptance criteria, that coverage is invisible to `pytest`/CI and could silently rot.
- Priority: Low — confirm whether these are superseded by `api/tests/` and `tests/test_pipeline_e2e.py`, and remove if obsolete.

---

*Concerns audit: 2026-07-05*
