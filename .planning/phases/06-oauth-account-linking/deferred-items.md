# Deferred Items — Phase 06 (oauth-account-linking)

Out-of-scope discoveries logged during plan execution. NOT fixed by the plan that found them (executor scope boundary: only issues directly caused by the current task's changes are auto-fixed).

## From 06-01 (PendingAccountLink model + migration)

Pre-existing third-party / unrelated-test warnings surfaced by `cd api && .venv/bin/python -m pytest tests/ -q`. Provably invariant to 06-01's two-file diff (new ORM class in `models.py`, new migration `900000000007`) — none reference `pending_account_links`:

- `fastapi/testclient.py:1` — `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`. Import-time deprecation in the FastAPI/Starlette test harness; suite-wide, dependency-level. Requires an httpx2 test-infra migration (test-tooling scope, not this phase).
- `slowapi/extension.py:720` — `DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated ... use inspect.iscoroutinefunction()`. Internal to the third-party `slowapi` package; fixable only by upstream or a dependency bump.
- `tests/test_promote_dvdread1_migration.py:279` — `SAWarning: transaction already deassociated from connection` on `db_session.rollback()`. Pre-existing test for the prior migration (900000000006); test authored before Phase 06.
