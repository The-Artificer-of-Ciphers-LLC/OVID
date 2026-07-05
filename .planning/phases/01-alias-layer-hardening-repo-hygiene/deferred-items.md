# Deferred Items — Phase 01 (alias-layer-hardening-repo-hygiene)

Out-of-scope discoveries surfaced while executing plans in this phase. Per the
executor's SCOPE BOUNDARY rule, these are pre-existing and unrelated to the
task's own file changes, so they are logged here rather than fixed inline.

## Plan 01-01 (verification.py)

Running the full API suite (`cd api && python -m pytest tests/ -q`) after
implementing `api/app/verification.py` passes all 246 tests, but surfaces
warnings entirely pre-existing in files not touched by this plan:

- `tests/test_auth.py::TestDecodeAccessToken::test_tampered_token` and several
  cases in `tests/test_auth_apple.py` deliberately construct JWTs with
  short/weak HMAC keys (as low as 1 byte) to test edge-case decode paths,
  triggering `jwt.api_jwt.InsecureKeyLengthWarning`. This looks intentional
  (testing malformed/tampered tokens) but was not touched by Plan 01-01.
- `fastapi/testclient.py:1` emits a `StarletteDeprecationWarning` — the
  installed `starlette` version deprecates using `httpx` directly with
  `TestClient` in favor of an `httpx2` shim. Library-version concern, present
  before this plan.
- `slowapi/extension.py:720` emits a `DeprecationWarning` for
  `asyncio.iscoroutinefunction` (removal slated for Python 3.16). Library-level
  concern in the `slowapi` dependency, present before this plan.

None of these are caused by `api/app/verification.py` or
`api/tests/test_verification.py`. Recommend triaging in a repo-hygiene plan
(this phase's stated concern) or a dependency-bump plan — not fixed here to
stay within Plan 01-01's file scope (`api/app/verification.py`,
`api/tests/test_verification.py`).

## Plan 01-02 (disc_identity.py alias race hardening)

Full suite (`cd api && python -m pytest tests/ -q`) after restructuring
`attach_lookup_aliases` still passes all 251 tests (12 in the disc-identity
race + alias suites), with the same pre-existing `InsecureKeyLengthWarning`
/ `StarletteDeprecationWarning` / `DeprecationWarning` warnings noted above
under Plan 01-01 — none originate from `api/app/disc_identity.py` or
`api/tests/test_disc_identity_race.py`. No new warnings introduced by this
plan. Confirmed out of scope, not fixed here.

## Plan 01-06 (repo hygiene — disposable script deletion, UAT tooling relocation)

Full suite (`api/.venv/bin/python -m pytest tests/ -q`) after deleting
`fix_test.py`/`fix_test2.py`/`test_script.py`/`verify_t11.py`, relocating
`run_uat.py`/`create_uat_dirs.py` to `scripts/`, and untracking/gitignoring
`uat_results.json`/`uat_dirs/` passes all 252 tests, with the identical
`InsecureKeyLengthWarning` / `StarletteDeprecationWarning` /
`asyncio.iscoroutinefunction DeprecationWarning` warnings recorded under
Plan 01-01 and Plan 01-02 above. This plan is pure VCS/repo-hygiene work —
it touches zero `api/` source or test files (only root-level scripts,
`scripts/`, `.gitignore`, and previously-tracked `uat_*` fixture data), so
these warnings cannot have been introduced or affected by this diff. This
is the third consecutive plan in this phase to independently confirm the
same three warnings as pre-existing and out of this phase's file scope;
recommend a dedicated dependency-bump / test-hardening plan to resolve them
(pin `httpx2` per Starlette's deprecation guidance, raise HMAC test key
lengths to >=32 bytes, and track `slowapi`'s upstream fix for
`asyncio.iscoroutinefunction`). Not fixed here — confirmed out of scope.
