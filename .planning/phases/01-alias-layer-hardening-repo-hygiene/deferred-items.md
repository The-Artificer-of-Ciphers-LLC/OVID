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

## Plan 01-03 (verification wiring in routes/disc.py + disc-row race safety)

Full suite (`cd api && ./.venv/bin/python -m pytest tests/ -q`) after wiring
`verify()`/`flag_dispute()`/`resolve_dispute()` into `api/app/routes/disc.py`
and savepoint-guarding the disc-row inserts in `submit_disc`/`register_disc`
passes all 254 tests, with the identical `InsecureKeyLengthWarning` /
`StarletteDeprecationWarning` / `asyncio.iscoroutinefunction`
`DeprecationWarning` trio recorded under Plans 01-01/01-02/01-06 above.
Verified via `git log` that `api/tests/test_auth.py` and
`api/tests/test_auth_apple.py` (the InsecureKeyLengthWarning source) were
last touched by an unrelated pre-phase commit (`0dee4dd`) and are untouched
by any of this plan's three task commits — this is the fourth consecutive
plan in this phase to independently confirm the same warnings as
pre-existing and out of file scope (`api/app/routes/disc.py`,
`api/app/verification.py`, `api/app/disc_identity.py`,
`api/tests/test_disc_submit.py`, `api/tests/test_dispute.py`). Not fixed
here — confirmed out of scope.

## Plan 01-04 (fingerprint_aliases lookup exposure — final plan of the phase)

Full suite (`cd api && ./.venv/bin/python -m pytest tests/ -q`) after adding
`FingerprintAliasResponse`/`fingerprint_aliases` to `schemas.py`, the
`order_by` on `Disc.identity_aliases` in `models.py`, and `_method_of` +
eager-loads in `routes/disc.py` passes all 255 tests (one new test added),
with the identical `InsecureKeyLengthWarning` / `StarletteDeprecationWarning`
/ `asyncio.iscoroutinefunction DeprecationWarning` trio recorded under
Plans 01-01/01-02/01-03/01-06 above — the fifth consecutive plan to
independently confirm these as pre-existing and out of this plan's file
scope (`api/app/schemas.py`, `api/app/models.py`, `api/app/routes/disc.py`,
`api/tests/test_disc_lookup.py`).

Additionally, `web/node_modules/` was not present in the working tree before
this plan ran (`npm ci` was required per the plan's technical note before
`npx tsc --noEmit` / `npm test` could execute). Once installed, `npm test`
(Vitest, 3 files / 32 tests) surfaces one pre-existing warning unrelated to
this plan's type-only `web/lib/api.ts` diff:

- `(node:...) [DEP0205] DeprecationWarning: module.register() is deprecated.
  Use module.registerHooks() instead.` — emitted by Vitest's own TS-transform
  loader registration against the installed Node.js runtime, not by any file
  this plan touches (`web/lib/api.ts` gained only a type-only optional
  field). Recommend tracking alongside the API-side dependency-bump item
  above (bump Vitest / Node compatibility) rather than fixing inline here.

Not fixed here — confirmed out of scope for both suites.
