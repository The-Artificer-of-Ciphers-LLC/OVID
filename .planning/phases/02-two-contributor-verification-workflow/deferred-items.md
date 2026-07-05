# Deferred Items — Phase 02

Out-of-scope discoveries logged during execution (not fixed inline; directly
outside this plan's changes and requiring dependency/package changes excluded
from auto-fix Rule 3).

## From Plan 02-01 (structural_match)

- **Third-party deprecation: Starlette TestClient/httpx.** Every test run emits
  `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is
  deprecated; install 'httpx2' instead` from `fastapi/testclient.py:1` (surfaced
  via `tests/conftest.py`'s `TestClient` import). Pre-existing across the whole
  suite; untouched by this comparison-only plan. Remedy is a dependency/package
  change (`httpx2`), which is a package-install decision outside this plan's
  scope (`api/app/structural_match.py` + its unit test). Owner: infra/deps.
- **Third-party deprecation: slowapi asyncio.iscoroutinefunction.** 13 warnings
  from `slowapi/extension.py:720` in `tests/test_auth.py`
  (`'asyncio.iscoroutinefunction' is deprecated ... use inspect.iscoroutinefunction()`).
  Pre-existing, inside the `slowapi` dependency; remedy is a `slowapi` upgrade.
  Owner: infra/deps (relates to Phase 3 rate-limit hardening, INFRA-01/04).
