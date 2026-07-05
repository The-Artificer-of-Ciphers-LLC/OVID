# Testing Patterns

**Analysis Date:** 2026-07-05

OVID has three independent test suites (API, client library, web frontend), each with its own runner and conventions.

## Test Framework

**API (`api/`):**
- Runner: `pytest` (version unpinned in `api/requirements.txt`; test-only deps not listed there — likely installed separately or via dev extras)
- Client: `fastapi.testclient.TestClient` (Starlette/httpx-based, in-process, no real network)
- DB: in-memory SQLite (`sqlite://`) via SQLAlchemy, substituted for the production PostgreSQL engine
- Config: no `pytest.ini`/`pyproject.toml` `[tool.pytest.ini_options]` found under `api/` — pytest runs with defaults; test discovery relies on `test_*.py` naming under `api/tests/`
- Run commands:
```bash
cd api && pytest                       # run all tests
cd api && pytest tests/test_disc_submit.py -v   # single file
```

**ovid-client (`ovid-client/`):**
- Runner: `pytest>=7.0` (declared in `[project.optional-dependencies].dev` in `ovid-client/pyproject.toml`)
- Config: `[tool.pytest.ini_options]` in `ovid-client/pyproject.toml` defines a custom marker:
  ```toml
  markers = [
      "real_disc: tests that require a real DVD disc path via OVID_TEST_DISC_PATH env var",
  ]
  ```
- Run commands:
```bash
cd ovid-client && pytest                          # run all tests (skips real_disc-marked unless env var set)
cd ovid-client && pytest -m "not real_disc"        # explicitly exclude hardware-dependent tests
```

**Web (`web/`):**
- Runner: Vitest 4.x (`web/vitest.config.ts`)
- Environment: `jsdom`, `globals: true` (no need to import `describe`/`it`/`expect` — but tests do import them explicitly anyway, see below)
- Setup file: `web/src/test-setup.ts` (loaded via `setupFiles`)
- Testing library: `@testing-library/react` + `@testing-library/jest-dom` + `@testing-library/user-event`
- Run commands:
```bash
cd web && npm test           # vitest run (from package.json "test" script)
cd web && npx vitest         # watch mode
```

## Test File Organization

**API:**
- Location: `api/tests/`, flat directory, one file per feature/route area (`test_disc_submit.py`, `test_disc_edits.py`, `test_disc_verify.py`, `test_disc_lookup.py`, `test_sync.py`, `test_sync_daemon.py`, `test_auth.py` + one file per OAuth provider: `test_auth_google.py`, `test_auth_github.py`, `test_auth_apple.py`, `test_auth_mastodon.py`, `test_auth_indieauth.py`, `test_auth_linking.py`)
- Naming: `test_<feature>.py`
- Shared fixtures centralized in `api/tests/conftest.py` — no per-file conftest overrides observed
- `api/tests/debug.py` exists as a non-test utility file (not prefixed `test_`, won't be collected by pytest)

**ovid-client:**
- Location: `ovid-client/tests/`, flat, one file per module/format concern (`test_bd_fingerprint.py`, `test_dvdread_adapter.py`, `test_ifo_parser.py`, `test_mpls_parser.py`, `test_disc_structure.py`, `test_cli_submit.py`, `test_cli_lookup.py`, `test_tmdb.py`)
- Two conftest files: `conftest.py` (general) and `conftest_bd.py` (Blu-ray-specific fixtures) — pattern to follow when a format needs isolated fixtures without polluting the shared conftest
- `test_real_disc.py` and the `real_disc` pytest marker gate tests requiring a physical/mounted disc image via `OVID_TEST_DISC_PATH` env var — do not assume these run in CI by default

**Web:**
- Location: `web/src/__tests__/`, NOT co-located with components — all tests centralized in one directory regardless of what they test (`auth.test.ts`, `pages.test.tsx`, `submit.test.tsx`)
- Naming: `<feature>.test.ts(x)`

## Test Structure

**API — class-based grouping per pytest convention:**
```python
# api/tests/test_disc_submit.py
class TestDiscSubmit:
    def test_submit_new_disc(self, client, auth_header):
        """POST valid payload with auth → 201, disc retrievable via GET."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        assert resp.status_code == 201
        ...

class TestDiscSubmitErrors:
    def test_submit_duplicate_fingerprint_conflicting_metadata(self, client, seeded_disc, auth_header):
        ...
```
- Happy-path and error-path tests are split into separate classes within the same file, divided by a comment banner (`# Happy-path` / `# Error paths`).
- Every test has a one-line docstring stating the scenario and expected outcome in "Given → action → result" style (e.g. `"""POST same fingerprint with conflicting metadata → 200 disputed."""`).

**Web:**
```typescript
describe("SubmitForm", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({ ... });
  });

  it("renders the file input", () => { ... });
  it("parses valid fingerprint JSON and shows preview", async () => { ... });
});
```

## Mocking

**API:**
- No mocking library used for unit isolation — instead, the DB layer itself is swapped (real SQLAlchemy ORM against SQLite) so tests exercise full route → ORM → DB round trips. This is integration-style testing, not mocked-unit testing.
- FastAPI's `app.dependency_overrides[get_db] = _get_test_db` pattern replaces the DB dependency at the app level (`api/tests/conftest.py`), rather than patching import paths.
- Rate limiter state is explicitly reset between tests via an autouse fixture (`_reset_rate_limiter`) to avoid cross-test 429 pollution — apply this pattern for any other shared global/in-memory state introduced later.

**Web:**
- `vi.mock()` used to replace entire modules at the import-path level:
  ```typescript
  vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: vi.fn() }),
  }));

  vi.mock("@/lib/auth", () => ({
    useAuth: () => mockUseAuth(),
  }));

  vi.mock("@/lib/api", () => ({
    submitDisc: vi.fn(),
    ApiError: class ApiError extends Error { ... },
  }));
  ```
- A `vi.fn()` wrapped in an outer `mockUseAuth` variable lets `beforeEach` reconfigure return values per test without re-declaring the mock.
- Mock error classes are hand-reconstructed inside `vi.mock` factories to match the real class's shape (constructor signature `status, code, message`) — keep mock shape in sync with `web/lib/api.ts` when that file changes.

## Fixtures and Factories

**API — layered fixture composition (`api/tests/conftest.py`):**
- `_reset_tables` (autouse): creates all tables before each test, drops after — full schema reset per test, no transaction-rollback strategy.
- `db_session`: raw SQLAlchemy session fixture for direct seeding/inspection.
- `client`: FastAPI `TestClient` with DB dependency overridden; cleans up `dependency_overrides` after each test.
- `seed_test_disc(db, submitted_by_id=None)`: plain helper function (not a fixture) that builds a full disc + release + title + audio/subtitle track graph modeled on "The Matrix" — reused across many test files via direct import, not just fixture injection.
- `seeded_disc` / `seeded_disc_with_owner`: fixture wrappers around `seed_test_disc` for the ownerless and owned cases respectively.
- User fixtures follow a three-tier pattern: `test_user`/`auth_header` (default contributor), `second_user`/`second_auth_header` (for two-contributor dispute/verification tests), `trusted_user`/`trusted_auth_header` (role=`trusted`, for dispute-resolution authorization tests). Follow this naming/tier pattern when adding a new role level.
- JWTs for auth headers are real tokens created via `create_access_token(user.id)` from `app.auth.jwt`, not stubbed — auth middleware runs for real in tests.

**Web:**
- Inline factory functions per test file, e.g. `createMockFile(content, name)` in `submit.test.tsx` builds a `File` object for upload-input testing.
- Test fixture JSON payloads (`validFingerprint`, `invalidFingerprint`) defined as local consts at file top.

## Coverage

**Requirements:** No coverage threshold or CI gate config detected in any of `api/`, `ovid-client/`, or `web/` — coverage is not enforced.

**View Coverage:**
```bash
# API / ovid-client — no coverage plugin config found; would need `pytest --cov` with pytest-cov installed
# Web — vitest supports `vitest run --coverage` but no @vitest/coverage-* package declared in web/package.json devDependencies
```

## Test Types

**Unit Tests:**
- ovid-client: fingerprinting/parsing logic tested in isolation per format (`test_ifo_parser.py`, `test_mpls_parser.py`, `test_bd_fingerprint.py`) — pure-function style, no DB or network involved.

**Integration Tests:**
- API: dominant pattern — full HTTP request through FastAPI's TestClient, hitting real route handlers, real Pydantic validation, real SQLAlchemy ORM against SQLite. `api/tests/test_pipeline_e2e.py` (top-level, outside `api/tests/`) suggests a broader end-to-end pipeline test also exists at repo root `tests/`.
- Web: component-level integration tests rendering full React components with mocked boundaries (auth, API, routing) — not pure unit tests of individual functions.

**E2E Tests:**
- `run_uat.py` and `create_uat_dirs.py` at repo root, plus `uat_dirs/` and `uat_results.json`, indicate a separate manual/scripted UAT (User Acceptance Testing) flow distinct from the pytest/vitest suites — likely drives the ARM (Automatic Ripping Machine) identification pipeline (`arm/identify.py`, `arm/identify_ovid.py`) against real or sample disc data outside the standard test runners.
- Root-level `tests/test_pipeline_e2e.py` with its own `conftest.py` runs a separate end-to-end pipeline distinct from `api/tests/`.

## Common Patterns

**Async Testing:**
- API routes use `async def` in places (FastAPI standard) but `TestClient` is synchronous — tests call `.post()`/`.get()` directly without `await`; async is handled internally by Starlette's test transport.

**Error Testing:**
```python
# api/tests/test_disc_submit.py pattern
def test_submit_duplicate_fingerprint_conflicting_metadata(self, client, seeded_disc, auth_header):
    """POST same fingerprint with conflicting metadata → 200 disputed."""
    resp = client.post("/v1/disc", json={...}, headers=auth_header)
    assert resp.status_code == 200
    assert resp.json()["status"] == "disputed"
```
Error/edge-case tests assert on **response body content and status code together** — never just status code alone — and are grouped into a dedicated `*Errors` test class per feature file.

```typescript
// web/src/__tests__/submit.test.tsx pattern
it("shows error for invalid JSON content", async () => {
  render(<SubmitForm />);
  const input = screen.getByTestId("fp-file-input");
  fireEvent.change(input, { target: { files: [createMockFile("not json at all")] } });
  await waitFor(() => {
    expect(screen.getByTestId("parse-error")).toBeTruthy();
  });
});
```
Frontend error-path tests always assert via a dedicated `data-testid` error element rendered conditionally, queried inside `waitFor` for async state settling.

---

*Testing analysis: 2026-07-05*
