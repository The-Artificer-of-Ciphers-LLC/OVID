# Phase 5 — Deferred Items (out-of-scope pre-existing findings)

Findings observed during Plan 05-06 execution that are pre-existing,
unrelated to this plan's file scope (`api/app/migrations_support.py`,
`api/tests/test_fingerprint_registry_migration.py`,
`api/alembic/versions/900000000005_*.py`,
`api/alembic/versions/900000000006_*.py`), and therefore not fixed here
per the executor's scope-boundary rule.

## 1. `StarletteDeprecationWarning`: httpx + starlette.testclient

- **Where:** `api/.venv/lib/.../fastapi/testclient.py:1`, surfaced on every
  test run that imports `fastapi.testclient.TestClient` (essentially the
  whole suite).
- **What:** `Using httpx with starlette.testclient is deprecated; install
  httpx2 instead.`
- **Why deferred:** environment/dependency-version concern (FastAPI's
  bundled TestClient vs. installed `httpx` version), unrelated to any file
  this plan touches; predates this plan.

## 2. `DeprecationWarning`: `slowapi`'s `asyncio.iscoroutinefunction` usage

- **Where:** `api/.venv/lib/.../slowapi/extension.py:720`, surfaced in
  `tests/test_auth.py` and `tests/test_rate_limit_fallback.py`.
- **What:** `'asyncio.iscoroutinefunction' is deprecated and slated for
  removal in Python 3.16; use inspect.iscoroutinefunction() instead.`
- **Why deferred:** internal to the third-party `slowapi` rate-limiting
  library (Phase 3 subsystem), unrelated to this plan's identity/migration
  scope; predates this plan.

Both were investigated (not waved off) to confirm they are genuinely
pre-existing and orthogonal to this plan's changes, not masking a defect
introduced by Plan 05-06.
