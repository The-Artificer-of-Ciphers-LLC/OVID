# Testing Patterns

**Analysis Date:** 2026-04-04

## Web (Next.js/React/TypeScript)

### Test Framework

**Runner:**
- Vitest 4.1.2
- Config: `web/vitest.config.ts`

**Assertion Library:**
- @testing-library/react 16.3.2
- @testing-library/jest-dom 6.9.1

**Environment:**
- jsdom (browser-like environment)
- globals: true (no `import { describe, it }` needed)

**Setup:**
- File: `web/src/test-setup.ts` imports `@testing-library/jest-dom/vitest`

**Run Commands:**
```bash
npm test                    # Run tests (vitest run)
npm test -- --watch        # Watch mode (vitest watch)
npm test -- --coverage     # Coverage report
```

### Test File Organization

**Location:**
- Co-located: Tests in `web/src/__tests__/` directory
- Pattern: `{module}.test.ts` or `{module}.test.tsx`

**Current test files:**
- `src/__tests__/auth.test.ts` — Hook and utility tests
- `src/__tests__/pages.test.tsx` — Component rendering tests
- `src/__tests__/submit.test.tsx` — Form and mock integration tests

### Test Structure

**Suite Setup (from `src/__tests__/auth.test.ts`):**
```typescript
import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
// ... imports

describe("Token helpers", () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it("getToken returns null when no token is stored", () => {
    expect(getToken()).toBeNull();
  });
});
```

**Patterns:**
- `beforeEach()` clears mocks and state between tests
- `describe()` groups related tests with domain naming: `"useAuth"`, `"Token helpers"`
- `it()` statements are imperative and specific: `"fetches user from /v1/auth/me when token exists"`
- No nested describe blocks observed (flat structure)

### Mocking

**Framework:** Vitest's `vi` object (global, no import needed with globals: true)

**Patterns:**

**1. Global object mocking (`src/__tests__/auth.test.ts`):**
```typescript
const storage: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => storage[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    storage[key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete storage[key];
  }),
  clear: vi.fn(() => {
    for (const k of Object.keys(storage)) delete storage[k];
  }),
  get length() {
    return Object.keys(storage).length;
  },
  key: vi.fn((_i: number) => null),
};

Object.defineProperty(globalThis, "localStorage", { value: localStorageMock });
```
- Mocks localStorage with manual storage object
- Tracks calls via `vi.fn()`
- Provides length property via getter

**2. Module mocking (`src/__tests__/submit.test.tsx`):**
```typescript
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const mockUseAuth = vi.fn();
vi.mock("@/lib/auth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("@/lib/api", () => ({
  submitDisc: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, code: string, message: string) {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
}));
```
- Replace entire module with stub implementation
- Return mock functions that can be configured per test
- Mock classes by creating stub class with same interface

**3. Fetch mocking (`src/__tests__/auth.test.ts`):**
```typescript
vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
  new Response(JSON.stringify(mockUser), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }),
);
```
- Spy on global fetch, mock with `mockResolvedValueOnce`
- Return Response object with status and headers
- One mock per test (doesn't persist across tests)

### Fixtures and Test Data

**Inline helpers (from `src/__tests__/submit.test.tsx`):**
```typescript
function createMockFile(content: string, name = "disc.json"): File {
  return new File([content], name, { type: "application/json" });
}

const validFingerprint = JSON.stringify({
  fingerprint: "abc123def456",
  format: "Blu-ray",
  structure: {
    playlists: [{ id: 1 }, { id: 2 }, { id: 3 }],
  },
});
```
- Helper functions for common test data (File objects, JSON strings)
- Inline constants for API response shapes
- No dedicated fixture files observed

**Mock data setup (`src/__tests__/pages.test.tsx`):**
```typescript
const release: SearchResultRelease = {
  id: "rel-001",
  title: "Blade Runner 2049",
  year: 2017,
  content_type: "movie",
  tmdb_id: 335984,
  disc_count: 2,
};
```
- Structured test data matching component props
- Defined at top of test block for reuse

### Coverage

**Requirements:** Not enforced (no coverage thresholds in config)

**View Coverage:**
```bash
npm test -- --coverage
```

### Test Types

**Unit Tests:**
- **Auth utilities** (`src/__tests__/auth.test.ts`): Token storage, JWT handling, hook state
  - Test `getToken()`, `setToken()`, `clearToken()` with localStorage mock
  - Test `useAuth()` hook with mocked fetch, verify state transitions
  - Test hook cleanup (cancelled flag prevents unmounted state updates)

- **Component rendering** (`src/__tests__/pages.test.tsx`): DiscCard, DiscStructure, EditHistory
  - Render with test data, verify output text and structure
  - Check fallback values (e.g., "Unknown year" when year is null)
  - Verify badge colors and formatting

**Integration Tests:**
- **Form submission** (`src/__tests__/submit.test.tsx`): SubmitForm with mocked API
  - File input parsing (valid JSON, invalid JSON, missing fields)
  - Form field rendering after successful upload
  - Mock `submitDisc()` calls via mocked `@/lib/api` module
  - Mock router push via mocked `next/navigation`

**No E2E tests** detected (no Playwright, Cypress, etc.)

---

## API (FastAPI/Python)

### Test Framework

**Runner:**
- pytest 7.0+
- Config: `api/tests/conftest.py` defines shared fixtures

**Test Location:**
- `api/tests/test_*.py`
- Current tests: `test_auth.py`, `test_cors.py`, `test_disc_verify.py`, `test_search.py`, `test_dispute.py`, etc.

**Run Commands:**
```bash
pytest                     # Run all tests
pytest -v                  # Verbose output
pytest -k "test_auth"      # Filter by name
pytest --cov=app          # Coverage
```

### Test Database Setup

**Database:** In-memory SQLite (never touches PostgreSQL)

**Key mechanism (`api/tests/conftest.py`):**

```python
# Patch DATABASE_URL BEFORE any app module import
os.environ["DATABASE_URL"] = "sqlite://"

# Auth config reads OVID_SECRET_KEY at import time
os.environ.setdefault("OVID_SECRET_KEY", "test-secret-key-for-unit-tests-32b")

# Engine setup
_SQLITE_URL = "sqlite://"
_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_sqlite_uuid_compat(_engine)
_TestSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
```

**Fixtures:**

1. **`_reset_tables`** (autouse=True):
   - Creates all tables before each test
   - Seeds `global_seq` table with id=1
   - Drops all tables after test
   - Ensures clean state per test

2. **`_reset_rate_limiter`** (autouse=True):
   - Clears slowapi in-memory storage before each test
   - Prevents rate limit counters from leaking between tests

3. **`_get_test_db()`:**
   - Dependency override for `get_db`
   - Returns in-memory session per test

### Test Structure

**Suite setup (from `api/tests/test_auth.py`):**
```python
class TestCreateAccessToken:
    def test_returns_decodable_jwt(self):
        """create_access_token returns a JWT with correct sub, iss, exp."""
        uid = uuid.uuid4()
        token = create_access_token(uid)
        
        payload = pyjwt.decode(token, _TEST_SECRET, algorithms=["HS256"], issuer="ovid")
        assert payload["sub"] == str(uid)
```

**Patterns:**
- Organized into test classes by function: `TestCreateAccessToken`, `TestDecodeAccessToken`, `TestGetCurrentUser`
- One assertion or related group per test method
- Test names are docstrings explaining what should happen
- No test fixtures beyond autouse ones; tests pass parameters directly

### Mocking

**Standard approaches (from `api/tests/conftest.py`):**

**1. Database dependency override:**
```python
from app.deps import get_db

def _get_test_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()

# In test file:
from fastapi.testclient import TestClient

client = TestClient(app)
app.dependency_overrides[get_db] = _get_test_db
```

**2. JWT testing without mocking:**
```python
import jwt as pyjwt

payload = {
    "sub": str(uuid.uuid4()),
    "exp": datetime.now(timezone.utc) + timedelta(days=1),
    "iss": "ovid",
}
token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")
```
- Create real tokens with test secret key
- Use PyJWT library directly to construct payloads
- No vi.fn() or mock objects; test with real JWT

**3. Expired/invalid token scenarios:**
```python
def test_expired_token(self):
    payload = {
        "sub": str(uuid.uuid4()),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),  # Past
        "iss": "ovid",
        "iat": datetime.now(timezone.utc) - timedelta(days=31),
    }
    token = pyjwt.encode(payload, _TEST_SECRET, algorithm="HS256")
    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_access_token(token)
```

### Fixtures and Test Data

**Test data inline:**
```python
user_data = {
    "id": "user-1",
    "username": "testuser",
    "email": "test@example.com",
    "display_name": "Test User",
    "role": "user",
    "email_verified": True,
}
```

**Model creation:**
```python
user = User(
    id=uuid.uuid4(),
    username="testuser",
    email="test@example.com",
    display_name="Test User",
    role="user"
)
db.add(user)
db.commit()
```

**No dedicated fixture files**, but test data and setup is done within test methods.

### Coverage

**Requirements:** Not enforced (no threshold in pytest config)

**View Coverage:**
```bash
pytest --cov=app --cov-report=html
```

### Test Types

**Unit Tests:**
- **JWT encoding/decoding** (`api/tests/test_auth.py`):
  - `create_access_token()` returns valid JWT with correct payload
  - `decode_access_token()` extracts subject, issuer, expiry
  - Handles expired tokens, tampered tokens, wrong issuer
  - Raises `jwt.ExpiredSignatureError`, `jwt.InvalidTokenError` appropriately

- **Auth dependency** (`api/tests/test_auth.py::TestGetCurrentUser`):
  - Missing Authorization header → HTTPException(401, "missing_token")
  - Invalid Bearer format → HTTPException(401, "missing_token")
  - Expired token → HTTPException(401, "expired_token")
  - Non-existent user → HTTPException(401, "invalid_token")

**Integration Tests:**
- **Endpoint integration** (test classes that use TestClient):
  - Tests routes with dependency override (in-memory DB)
  - Makes HTTP requests to FastAPI app
  - Verifies response status codes and JSON body

**Database Tests:**
- Models are tested implicitly through integration tests (ORM behavior verified)
- No dedicated ORM unit tests observed

---

## ovid-client (Python Library/CLI)

### Test Framework

**Runner:**
- pytest 7.0+
- Markers: `real_disc` for tests requiring actual disc path via `OVID_TEST_DISC_PATH` env var

**Test Location:**
- `ovid-client/tests/test_*.py`
- Fixture builders: `tests/conftest.py`, `tests/conftest_bd.py`

**Run Commands:**
```bash
pytest                           # Run unit tests (skip real_disc)
pytest -m real_disc             # Run real disc tests only
pytest -v                       # Verbose
pytest --co                     # Collect tests without running
```

### Test Structure

**Suite setup (from `tests/test_fingerprint.py`):**
```python
class TestBuildCanonicalString:
    """Verify the canonical string exactly matches spec §2.1 format."""
    
    def test_single_vts_single_pgc(self):
        vmg = VMGInfo(vts_count=1, title_count=1)
        vts = VTSInfo(
            pgc_list=[PGCInfo(duration_seconds=7287, chapter_count=28)],
            audio_streams=[
                AudioStream(codec="AC3", language="en", channels=6),
            ],
            subtitle_streams=[SubtitleStream(language="en")],
        )
        result = build_canonical_string(vmg, [vts])
        assert result == "OVID-DVD-1|1|1|1:7287:28:en:en"
```

**Patterns:**
- Organized into test classes by function
- One assertion per test (verify exact output)
- Docstring explains what spec requirement is tested

### Fixtures and Test Data

**Synthetic IFO binary builders (`tests/conftest.py`):**
```python
def make_vmg_ifo(vts_count: int, title_entries: int) -> bytes:
    """Build a minimal VIDEO_TS.IFO (VMG) binary blob.
    
    Layout:
      0x0000: 12-byte identifier "DVDVIDEO-VMG"
      0x003E: VTS count (2 bytes BE)
      ...
    """
    buf = bytearray(SECTOR_SIZE * 2)
    buf[0:12] = b"DVDVIDEO-VMG"
    struct.pack_into(">H", buf, 0x3E, vts_count)
    # ... more setup
    return bytes(buf)

def make_vts_ifo(
    pgcs: list[tuple[int, int, int, int]] | None = None,
    audio_streams: list[tuple[int, str, int]] | None = None,
    subtitle_streams: list[str] | None = None,
) -> bytes:
    """Build a minimal VTS_XX_0.IFO binary blob..."""
```

**Test data construction (from `tests/test_fingerprint.py`):**
```python
vmg = VMGInfo(vts_count=1, title_count=1)
vts = VTSInfo(
    pgc_list=[PGCInfo(duration_seconds=7287, chapter_count=28)],
    audio_streams=[AudioStream(codec="AC3", language="en", channels=6)],
    subtitle_streams=[SubtitleStream(language="en")],
)
```

### Test Types

**Unit Tests:**
- **Fingerprint generation** (`tests/test_fingerprint.py`):
  - Canonical string building with various PGC/audio/subtitle configurations
  - SHA-256 hashing and prefix format (`dvd1-{40 hex chars}`)
  - Edge cases: empty PGCs, no audio/subs, multiple VTS

- **IFO parsing** (`tests/test_ifo_parser.py`):
  - Parse VMG info (VTS count, title count)
  - Parse VTS info (PGC duration, chapter count, audio/subtitle streams)
  - Handle BCD time encoding/decoding

- **Disc reading** (`tests/test_disc.py`, `tests/test_bd_disc.py`):
  - DVD disc object construction
  - Blu-ray disc handling and path detection
  - Reader backend selection (ISO, folder, drive, BD-specific)

**Real Disc Tests:**
- Marked with `@pytest.mark.real_disc`
- Require `OVID_TEST_DISC_PATH` environment variable
- Test against actual DVD/BD images
- Verify fingerprints match expected values

---

## Testing Best Practices (Observed)

### Web

1. **Use data-testid for all queries** — Don't rely on text content:
   ```typescript
   expect(screen.getByTestId("disc-card-title")).toHaveTextContent(...)
   ```

2. **Mock at module boundaries** — Mock entire modules (`vi.mock()`) rather than individual functions:
   ```typescript
   vi.mock("@/lib/auth", () => ({ useAuth: () => mockUseAuth() }))
   ```

3. **Clear state between tests** — Use `beforeEach()` to reset mocks and globals:
   ```typescript
   beforeEach(() => {
     localStorageMock.clear();
     vi.clearAllMocks();
   });
   ```

4. **Test async state changes** — Use `waitFor()` for hooks that fetch data:
   ```typescript
   await waitFor(() => {
     expect(result.current.loading).toBe(false);
   });
   ```

### API

1. **Use in-memory SQLite, not mocking** — Real DB engine for integration testing
2. **Patch environment before imports** — Database URL set before app module load
3. **Test concrete behavior** — Create real JWTs, real DB records; verify actual exceptions
4. **One assertion per test method** — Clear, focused test intent
5. **Use dependency_overrides** for FastAPI injections

### ovid-client

1. **Build synthetic binary data** — Use conftest builders to create test IFO blobs
2. **Test spec compliance** — Assertions match technical spec requirements
3. **Separate unit from integration** — Use markers for real disc tests
4. **Clear docstrings** — Explain what spec requirement is being tested

