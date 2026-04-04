# Coding Conventions

**Analysis Date:** 2026-04-04

## Overview

The OVID codebase uses distinct conventions across three major components: **web** (Next.js/React/TypeScript), **api** (FastAPI/Python), and **ovid-client** (CLI/Python library). Each follows its ecosystem's standards with shared patterns for error handling and logging.

---

## Web (Next.js/TypeScript)

### Naming Patterns

**Files:**
- Components: PascalCase, e.g. `NavBar.tsx`, `DiscCard.tsx`, `SubmitForm.tsx`
- Pages: lowercase with hyphens for routes, e.g. `app/page.tsx`, `app/auth/callback/page.tsx`, `app/disc/[fingerprint]/page.tsx`
- Utilities/lib: camelCase, e.g. `lib/api.ts`, `lib/auth.ts`
- Tests: `{name}.test.ts` or `{name}.test.tsx`, located in `src/__tests__/`

**Functions:**
- camelCase (exported): `searchReleases()`, `getDisc()`, `useAuth()`
- camelCase (helpers): `_error_response()`, `_build_track_response()`
- Prefix underscore for internal/private helper functions within modules
- Hook naming: `use*` prefix, e.g. `useAuth()`

**Variables:**
- camelCase for runtime values: `discCard`, `authState`, `searchResult`
- UPPERCASE for constants: `TOKEN_KEY`, `API_URL`, `TYPE_COLORS`
- Structured constants as maps: `TYPE_COLORS: Record<string, string>`

**Types:**
- PascalCase for interfaces and types: `AuthState`, `DiscLookupResponse`, `UserResponse`
- Suffix `Response` for API response schemas: `DiscLookupResponse`, `ReleaseResponse`, `TrackResponse`
- Suffix `Create` for request/input schemas: `DiscSubmitRequest`, `ReleaseCreate`, `TitleCreate`
- Suffix `Props` or leave unnamed for React component props

### Code Style

**Formatting:**
- ESLint with Next.js defaults (`eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`)
- Config: `web/eslint.config.mjs` uses flat config format (ESLint 9+)
- No Prettier configured — rely on ESLint
- TypeScript `strict: true` in `tsconfig.json`

**Linting Rules:**
- Core Web Vitals checks enforced
- TypeScript strict mode required
- All .ts and .tsx files included

### Import Organization

**Order (observed):**
1. React and Next.js framework imports: `import { useState, useEffect } from "react"`, `import Link from "next/link"`
2. Third-party libraries: `import { renderHook, waitFor } from "@testing-library/react"`
3. Local imports (absolute paths): `import { useAuth } from "@/lib/auth"`, `import NavBar from "@/components/NavBar"`
4. Type imports: `import type { ComponentProps, ReactNode } from "react"`, `import type { SearchResultRelease } from "@/lib/api"`

**Path Aliases:**
- `@/` resolves to `/Users/trekkie/projects/OVID/web/` (configured in `tsconfig.json`)
- Use `@/lib/*` for utilities, `@/components/*` for components, `@/app/*` for pages

### Error Handling

**API Layer (`lib/api.ts`):**
- Custom `ApiError` class extending `Error` with properties: `status`, `code`, `message`
- Thrown when fetch response is not ok
- Catches JSON parse failures and provides fallback error body
- Higher-level consumers catch `ApiError` and display human-readable messages

**Component Error Handling:**
- `app/page.tsx`: Wraps API calls in try/catch, stores `searchError` string in local state
- Display error blocks with conditional rendering: check `if (searchError)` before rendering error UI
- No global error boundary observed — use local state for user feedback

**Hook Error Recovery:**
- `useAuth()` in `lib/auth.ts`: Catches auth failures, clears invalid tokens, returns null user
- Uses isMounted pattern to prevent state updates on unmounted components (`cancelled` flag)

### Logging

**Framework:** Console (via Browser DevTools)

**Patterns:**
- No structured logging in client code
- API errors logged implicitly through ErrorResponse UI
- Test logs via `console` in tests (not observed in production code)

### Comments

**When to Comment:**
- Module-level comments explain purpose: `// OVID API client — typed fetch wrapper for both server and client components`
- Section dividers with dashed lines: `// ---------------------------------------------------------------------------`
- Conditional comments for non-obvious logic: `// Server-side: use internal Docker network URL`, `// Client-side: use public URL`
- No JSDoc observed in component code

**Style:**
- Single-line comments with `//` for inline notes
- Block comments with divider lines for section separation
- Comments precede the code they describe

### Function Design

**Size Guideline:** 50–150 lines typical; helper utilities are 10–30 lines

**Parameters:**
- Explicit over spread: `{ release }` for component props
- Typed: all function params have TypeScript annotations
- Optional params use `?:` syntax: `const yearNum = params.year ? parseInt(params.year, 10) : undefined`

**Return Values:**
- Functions return typed values (Promise<T>, ReactElement, etc.)
- Async server components: `async function HomePage()` returns JSX directly
- Hooks return object with named properties: `{ user, token, loading, logout }`
- Utility functions return single typed value or tuple (rare)

### Module Design

**Exports:**
- Default export for single-export modules: `export default function NavBar() { ... }`
- Named exports for utility/schema modules: `export interface AuthState { ... }`, `export function getToken() { ... }`
- Mix of defaults and named in some: `lib/api.ts` exports `class ApiError` (named) and multiple functions (named)

**Barrel Files:**
- Not used; imports reference specific files

**File Organization:**
- Related types and functions colocated: `lib/api.ts` contains all response/request types and fetch functions
- Auth logic isolated: `lib/auth.ts` for token helpers and `useAuth` hook
- One component per file

---

## API (FastAPI/Python)

### Naming Patterns

**Files:**
- Modules: lowercase_with_underscores: `app/routes/disc.py`, `app/auth/deps.py`, `app/models.py`
- Test files: `test_*.py` in `api/tests/`

**Functions:**
- snake_case: `get_current_user()`, `decode_access_token()`, `_build_track_response()`
- Prefix underscore for private/internal: `_error_response()`, `_auth_aware_key()`, `_dynamic_limit()`
- Async endpoint functions: `async def lookup_disc_by_upc()`, `async def submit_disc()`

**Classes:**
- PascalCase for models and exceptions: `User`, `Disc`, `ApiError`
- Suffix `Response` or `Request` for schemas: `DiscLookupResponse`, `DiscSubmitRequest`
- SQLAlchemy models use table names: `User`, `Disc`, `DiscEdit`

**Variables:**
- snake_case: `user_id`, `disc_fingerprint`, `request_id`
- UPPERCASE for module-level constants: `TOKEN_KEY`, `SECTOR_SIZE`, `JWT_EXPIRY_DAYS`

### Code Style

**Formatting:**
- No strict formatter configured; follows PEP 8 conventions
- Type hints required on function signatures: `def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:`
- Docstrings for public functions and classes (reStructuredText style observed)

**Linting:**
- No linter config detected in repo (`.ruff_cache/` present but no `ruff.toml`)
- Assume standard Python conventions

### Import Organization

**Order (observed):**
1. Standard library: `import os`, `import logging`, `import uuid`
2. Third-party frameworks: `from fastapi import APIRouter`, `from sqlalchemy import func`
3. Local imports: `from app.auth.deps import get_current_user`, `from app.models import Disc`

**No import aliases** beyond standard practice (e.g., `import jwt as pyjwt` for clarity on JWT library vs local jwt module).

### Error Handling

**Strategy:** FastAPI's `HTTPException` for auth errors, `JSONResponse` for structured errors

**Patterns:**
- **Missing auth**: `HTTPException(status_code=401, detail={"error": "missing_token"})`
- **Expired token**: `HTTPException(status_code=401, detail={"error": "expired_token"})`
- **Invalid token**: `HTTPException(status_code=401, detail={"error": "invalid_token"})`
- **Rate limit**: Custom `rate_limit_exceeded_handler()` returns `JSONResponse(status_code=429, content={...})`
- **Mirror mode**: `MirrorModeMiddleware` returns `JSONResponse(status_code=405, content={"error": "mirror_mode", ...})`

**Exception Handling Flow:**
1. Try block wraps risky operations (JWT decode, DB queries, token validation)
2. Catch specific exception types: `jwt.ExpiredSignatureError`, `jwt.InvalidTokenError`, `Exception`
3. Re-raise as `HTTPException` with appropriate status code and structured detail
4. Detail always includes `error` key with string code: `"missing_token"`, `"invalid_token"`, etc.

### Logging

**Framework:** Python `logging` module (`logger = logging.getLogger(__name__)`)

**Patterns:**
- WARNING level for noteworthy events: `logger.warning("rate_limit_exceeded key=%s limit=%s path=%s", ...)`
- DEBUG level for trace info: `logger.debug("sync_seq_incremented new_seq=%d", row.current_seq)`
- Guard logging: Include key context like `user_id`, `request_id`, `fingerprint`
- No f-strings in logs; use %-style formatting: `logger.warning("auth_user_not_found sub=%s", sub)`

### Comments

**When to Comment:**
- Module docstrings explain purpose and design: `"""Disc-related API endpoints — /v1 router."""`
- Section dividers for logical groups: `# ---------------------------------------------------------------------------`
- Complex logic gets inline explanations: `# The CHECK constraint ``id = 1`` enforces exactly one row`
- Raises docstring clause for exceptions: `Raises: HTTPException(401) with...`

**Docstring Style:** reStructuredText format with sections:
```python
def function(x):
    """One-line summary.
    
    Longer description if needed.
    
    Args:
        x: Description.
    
    Returns:
        Description.
    
    Raises:
        ValueError: When something is wrong.
    """
```

### Function Design

**Size Guideline:** 50–100 lines typical; route handlers can be longer

**Parameters:**
- Explicit dependency injection via FastAPI `Depends()`: `db: Session = Depends(get_db)`
- Annotated types: `authorization: str | None = Header(default=None)`
- Path/query params use FastAPI converters: `upc: str`, `page: int = Query(1)`

**Return Values:**
- Pydantic model instances for API responses: `DiscLookupResponse(...)`
- `JSONResponse` for custom error shapes
- Async functions: declare `async def`, use `await` for I/O

### Module Design

**Exports:**
- Routes exported as `router = APIRouter(...)`, included via `app.include_router(router)`
- Dependency functions exported individually: `from app.deps import get_db`
- Models imported for type hints and queries

**File Organization:**
- Routes isolated by domain: `app/routes/disc.py`, `app/routes/sync.py`
- Auth logic grouped: `app/auth/jwt.py`, `app/auth/deps.py`, `app/auth/users.py`
- Models and schemas in separate files: `app/models.py`, `app/schemas.py`
- Middleware in `app/middleware.py`

---

## ovid-client (Python CLI/Library)

### Naming Patterns

**Files:**
- Modules: lowercase_with_underscores: `fingerprint.py`, `bd_disc.py`, `ifo_parser.py`, `cli.py`
- Test files: `test_*.py` in `tests/`
- Readers: `readers/base.py`, `readers/drive.py`, `readers/iso.py`, `readers/bd_folder.py`, `readers/folder.py`

**Functions:**
- snake_case: `build_canonical_string()`, `compute_fingerprint()`, `encode_bcd_time()`
- Prefix underscore for internal: `_to_bcd()`, `_sqlite_uuid_compat()`

**Classes:**
- PascalCase for types and parsers: `VMGInfo`, `VTSInfo`, `AudioStream`, `PGCInfo`
- Suffix with domain: `AudioStream`, `SubtitleStream`, `DiscTrack`

**Variables:**
- snake_case: `vts_count`, `pgc_list`, `language_code`
- UPPERCASE for constants: `SECTOR_SIZE`, `_ALGORITHM`, `_ISSUER`

### Code Style

**Formatting:**
- Type hints on function signatures
- Docstrings with module-level explanations
- Future imports: `from __future__ import annotations` for forward compatibility

### Comments

**When to Comment:**
- Module docstrings: `"""OVID-DVD-1 fingerprint algorithm: canonical string builder and SHA-256 hash."""`
- Section dividers: `# ---------------------------------------------------------------------------`
- Algorithm explanations in docstrings with examples

---

## Cross-Codebase Patterns

### Request/Response ID Tracking

**API**: Middleware generates `X-Request-ID` header on all responses; request_id stored in `request.state.request_id`

**Web**: Passes `request_id` in response objects (e.g., `DiscLookupResponse` includes `request_id: str`)

### Error Response Shape

**Consistent across API:**
```json
{
  "error": "error_code_string",
  "message": "Human-readable message",
  "request_id": "uuid"
}
```

**Web**: Catches `ApiError`, extracts `message`, displays in error UI block

### Status Constants

**API**: Disc status values: `"unverified"`, `"verified"`, `"disputed"`

**Mapping**: `STATUS_CONFIDENCE` dict maps status → confidence level (e.g., `"verified"` → `"high"`)

---

## Recommended Conventions for New Code

**Web (TypeScript):**
- Use `@/` absolute imports for all local imports
- Prefix private helper functions with underscore: `_buildResponse()`
- Return typed objects from hooks, not arrays
- Handle errors with try/catch, store message in local state
- Use `data-testid` attributes for all interactive elements

**API (Python):**
- Use snake_case for all identifiers
- Wrap risky operations in try/except, re-raise as HTTPException
- Use structured logging with context keys
- Docstring all public functions with Args/Returns/Raises sections
- Build schemas in `app/schemas.py` alongside models

**ovid-client (Python):**
- Module docstrings explain algorithm/purpose
- Use section dividers for logical grouping
- Type hint all function signatures
- Prefix private helpers with underscore

