# Deferred Items — Phase 03

Out-of-scope discoveries logged during execution (not fixed under the current plan's scope boundary).

## Third-party deprecation warnings (pre-existing, library-sourced)

Discovered during: Plan 03-01 test runs (present across the whole suite, including the unchanged `test_rate_limit.py`/`test_auth.py`).

1. **`asyncio.iscoroutinefunction` deprecated** — emitted by `slowapi/extension.py:720` (vendored dependency) under Python 3.14. slowapi 0.1.10 uses the deprecated `asyncio.iscoroutinefunction` instead of `inspect.iscoroutinefunction`. Not fixable without patching the vendored package; the project's CI Python is 3.12 where this does not fire. Resolve by upgrading `slowapi` when a release migrates the call, not by editing `.venv`.
2. **`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`** — emitted by `starlette/testclient.py:1`. Test-harness-only, from Starlette's own import. Resolve on a future Starlette/httpx dependency bump.

Both pre-date this plan's changes and originate in third-party library code (not OVID source), so they fall under the executor scope boundary (pre-existing warnings in unrelated files). No behavior impact on the rate-limiting changes.
