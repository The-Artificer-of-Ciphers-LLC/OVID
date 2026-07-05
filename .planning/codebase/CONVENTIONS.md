# Coding Conventions

**Analysis Date:** 2026-07-05

## Repo Layout Relevant to Conventions

OVID is a polyglot repo with three main code areas, each with its own convention profile:

- `api/` — Python 3 / FastAPI backend (`api/app/`, routes in `api/app/routes/`)
- `ovid-client/` — Python 3 disc-fingerprinting CLI/library (`ovid-client/src/ovid/`)
- `web/` — TypeScript / Next.js 16 (React 19) frontend (`web/app/`, `web/components/`, `web/lib/`)
- `arm/` — standalone Python scripts for automated ripping identification (no package structure)

## Naming Patterns

**Python (`api/`, `ovid-client/`):**
- Files: `snake_case.py` (`disc_identity.py`, `rate_limit.py`, `mirror_mode` concepts embedded in `sync.py`)
- Functions/variables: `snake_case` (`resolve_disc_identity`, `_disc_to_response`, `submitted_by_id`)
- Private/internal helpers prefixed with `_` (`_error_response`, `_releases_match`, `_build_track_response`, `_sqlite_uuid_compat`)
- Classes: `PascalCase` for models/schemas/exceptions (`Disc`, `DiscSubmitRequest`, `DiscIdentityConflict`)
- Test classes group scenarios: `TestDiscSubmit`, `TestDiscSubmitErrors` (see `api/tests/test_disc_submit.py`)
- Constants: `UPPER_SNAKE_CASE` (`STATUS_CONFIDENCE` in `api/app/schemas.py`)

**TypeScript (`web/`):**
- Component files: `PascalCase.tsx` (`SubmitForm.tsx`, `ProviderList.tsx` in `web/components/`)
- Route files follow Next.js App Router convention: `web/app/<route>/page.tsx`
- Hooks/libs: `camelCase.ts` (`web/lib/auth.ts`, `web/lib/api.ts`)
- Dynamic route segments use bracket syntax: `web/app/disc/[fingerprint]/`
- Test files: `*.test.ts` / `*.test.tsx` co-located in `web/src/__tests__/`

## Code Style

**Python:**
- No `ruff`/`black`/`mypy` config detected in `api/` or `ovid-client/` — no enforced formatter/linter config file found (check for drift before assuming a style tool runs in CI)
- Modern type hints used throughout: `str | None`, `uuid.UUID | None`, `list[str]` (Python 3.10+ union syntax), confirmed in `api/app/routes/disc.py` and `api/app/schemas.py`
- Function signatures are fully type-annotated including return types (`def _build_track_response(track: DiscTrack) -> TrackResponse:`)
- Module docstrings appear at top of every file, one line, describing the module's purpose (e.g., `"""Disc-related API endpoints — /v1 router."""`)
- Section dividers use comment banners:
  ```python
  # ---------------------------------------------------------------------------
  # Helpers
  # ---------------------------------------------------------------------------
  ```
  This pattern appears consistently across `api/app/routes/disc.py`, `api/tests/conftest.py`, `api/tests/test_disc_submit.py` — use it to separate logical sections within a file.
- Pydantic v2 (`pydantic.BaseModel`, `Annotated[str, Field(...)]`) for all request/response schemas — see `api/app/schemas.py`

**TypeScript:**
- `strict: true` in `web/tsconfig.json` — write fully-typed code, no implicit `any`
- Path alias `@/*` maps to repo root of `web/` (configured in both `tsconfig.json` and `vitest.config.ts`)
- ESLint via flat config (`web/eslint.config.mjs`) extending `eslint-config-next` core-web-vitals + typescript rulesets

## Import Organization

**Python:**
- Standard library first, then third-party, then local `app.*` imports — visible in `api/app/routes/disc.py`:
  ```python
  import json
  import logging
  import math
  import uuid
  from typing import Any

  from fastapi import APIRouter, Depends, Query, Request
  from sqlalchemy import func

  from app.auth.deps import get_current_user
  from app.deps import get_db
  ```
- Test files import fixtures/helpers from `app.*` directly; `conftest.py` patches `os.environ["DATABASE_URL"]` **before** any `app` import, with `# noqa: E402` on subsequent imports to suppress the resulting lint warning — this ordering is load-bearing, not accidental (see `api/tests/conftest.py` lines 11-31)

**TypeScript:**
- Vitest/testing-library imports first, then component imports via `@/` alias, then mocks:
  ```typescript
  import { describe, it, expect, vi, beforeEach } from "vitest";
  import { render, screen, fireEvent, waitFor } from "@testing-library/react";
  import SubmitForm from "@/components/SubmitForm";
  ```

## Error Handling

**API (FastAPI):**
- Consistent JSON error envelope built via a shared helper, not raised HTTPException per-case:
  ```python
  def _error_response(request_id: str, error: str, message: str, status_code: int) -> JSONResponse:
      return JSONResponse(
          status_code=status_code,
          content={"request_id": request_id, "error": error, "message": message},
      )
  ```
  (`api/app/routes/disc.py`). Every error response includes `request_id`, `error` (machine-readable code), and `message` (human-readable).
- Domain-specific exceptions are defined per module and caught at the route boundary to produce the structured response, e.g. `DiscIdentityConflict` in `api/app/disc_identity.py` (raised on fingerprint/alias collision), caught in `disc.py` and converted via `_identity_conflict_response()`.
- HTTP status codes are chosen deliberately per business state, not just success/failure: e.g. duplicate submission with conflicting metadata returns `200` with a `disputed` status body rather than an error — domain state, not transport failure (`api/tests/test_disc_submit.py::test_submit_duplicate_fingerprint_conflicting_metadata`).
- Every response includes a `request_id` (both in body and as `x-request-id` header) for traceability — asserted directly in tests.

**Frontend:**
- Typed error class pattern: `ApiError extends Error` carrying `status` and `code` fields, defined in `web/lib/api.ts` and mocked identically in tests (`web/src/__tests__/submit.test.tsx`).
- UI surfaces parse/validation errors via dedicated `data-testid` elements (`parse-error`) rather than generic alerts — follow this pattern for new form validation.

## Testing-Adjacent Conventions (see TESTING.md for framework details)

- Python tests use `data-testid`-equivalent explicit `assert` on JSON response fields, never snapshot testing.
- Frontend tests query DOM via `data-testid` attributes (`fp-file-input`, `fp-preview`) rather than text/role queries where the target is a specific control — assign a `data-testid` to any new interactive element intended to be tested this way.

## Comments

- Docstrings are used for "why", not "what" — e.g. `conftest.py`'s SQLite/UUID compatibility shim explains *why* the hack is necessary (SQLAlchemy Postgres UUID type doesn't map cleanly to SQLite) rather than restating the code.
- Inline comments explain non-obvious business rules (e.g., "SQLite stores UUIDs as strings; compare string representations" in `test_disc_submit.py`).

## Module Design

**Python (`api/app/`):**
- Routes (`api/app/routes/disc.py`, `api/app/routes/sync.py`) contain thin FastAPI endpoint functions plus private `_helper` functions for response-shaping directly above/below their usage — helpers are not extracted to a separate module unless shared across routes.
- Domain logic (identity resolution, conflict detection) lives in dedicated modules outside `routes/` (`api/app/disc_identity.py`, `api/app/sync.py`) and is imported into routes — keep business logic out of route handlers when it's non-trivial.
- Schemas (`api/app/schemas.py`) are centralized in one file, not split per-route.

**TypeScript (`web/`):**
- `web/lib/` holds cross-cutting concerns (`auth.ts`, `api.ts`) consumed via hooks (`useAuth`) and functions (`submitDisc`), imported through the `@/lib/...` alias and mocked wholesale in tests with `vi.mock`.
- `web/components/` holds reusable, testable UI components separate from `web/app/**/page.tsx` route files.

## AGENTS.md / Project-Specific Guidance

- `web/AGENTS.md` (linked via `web/CLAUDE.md`) explicitly warns: this Next.js version (16.2.2) has breaking changes vs. training-data assumptions — consult `node_modules/next/dist/docs/` before writing App Router code, and heed deprecation notices. Treat any Next.js API usage in `web/` as needing verification against installed docs rather than memory.

---

*Convention analysis: 2026-07-05*
