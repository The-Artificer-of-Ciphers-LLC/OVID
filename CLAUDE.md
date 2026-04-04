<!-- GSD:project-start source:PROJECT.md -->
## Project

**OVID — Open Video Disc Identification Database**

OVID is an open, community-driven database that uniquely identifies physical DVD, Blu-ray, and 4K UHD discs by their structural fingerprint and maps them to rich release metadata — disc layout, title/chapter structure, audio/subtitle tracks, and edition information. It is to video discs what MusicBrainz is to audio CDs. The primary integration target is the Automatic Ripping Machine (ARM) and similar home media ripping tools.

**Core Value:** When a disc is inserted into any optical drive, OVID identifies it by structure — not by unreliable disc labels — and returns the full disc layout so ripping tools know which title is the main feature, what edition it is, and what audio/subtitle tracks are available. If this doesn't work, nothing else matters.

### Constraints

- **License**: AGPL-3.0 for code; CC0 for all submitted disc metadata
- **Dependencies**: C libraries (libdvdread, libbluray, libaacs) required for disc reading — installed separately by users
- **Hosting**: Single server (holodeck.nomorestars.com) for now; no distributed architecture needed at current scale
- **Database**: PostgreSQL 16; all queries via SQLAlchemy ORM with parameterized statements
- **Auth**: JWT (1-hour access, 30-day refresh); OAuth tokens encrypted at rest (AES-256-GCM)
- **API contract**: Read endpoints unauthenticated; write endpoints require Bearer token
- **Fingerprint stability**: Algorithm changes require version bump (dvd2- prefix), never modify existing algorithm output
- **Git strategy**: Gitflow model (main, develop, feature/*, release/*, hotfix/*); conventional commits
- **Multi-language workspace**: Python (API, client), TypeScript (web UI), Swift/iOS (future). Match tooling to component language.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12 - API backend, CLI tools, database migrations (FastAPI + SQLAlchemy)
- TypeScript 5 - Web frontend (Next.js 16.2.2)
- JavaScript - Node.js runtime for web layer
- Shell/Bash - Container entrypoints, deployment scripts
## Runtime
- Python 3.12 (via Docker: `python:3.12-slim`)
- Node.js 24 Alpine (via Docker: `node:24-alpine`)
- pip (Python)
- npm (Node.js)
## Frameworks
- FastAPI 0.110+ - Async web API framework with automatic Swagger/ReDoc docs
- Starlette - ASGI middleware layer (includes CORSMiddleware, SessionMiddleware)
- Next.js 16.2.2 - React full-stack framework with server/client rendering
- React 19.2.4 - UI component library
- SQLAlchemy 2.0+ - ORM with async support
- Alembic 1.13+ - Database migration tool
- PostgreSQL 16 - Relational database (Docker: `postgres:16-alpine`)
- Vitest 4.1.2 - Test runner (web)
- Testing Library - React component testing
- pytest 7.0+ - Python test framework (optional dependency in ovid-client)
- jsdom 29.0.1 - DOM simulation for Node.js tests
- TypeScript 5 - Type checking (web)
- Tailwind CSS 4 - Utility CSS framework
- ESLint 9 - JavaScript linting
- eslint-config-next 16.2.2 - Next.js ESLint rules
- Vitest 4.1.2 - Vite-powered test runner
## Key Dependencies
- authlib 1.3+ - OAuth 2.0 provider integration (GitHub, Google, Apple) via Starlette
- PyJWT 2.8+ - JWT token creation/verification (ES256 for Apple, HS256 for standard)
- httpx 0.27+ - Async HTTP client (IndieAuth discovery, Mastodon API, Apple token exchange)
- psycopg2-binary 2.9+ - PostgreSQL database adapter
- slowapi 0.1.9+ - Rate limiting (decorator-based via `@limiter.limit()`)
- gunicorn 21.2-24 - Production WSGI server with uvicorn worker
- uvicorn[standard] 0.29+ - ASGI server (development and worker mode)
- itsdangerous 2.1+ - Secure token generation (session signing)
- pycdlib 1.14+ - ISO 9660 CD/DVD metadata parser (disc fingerprinting)
- click 8.0+ - CLI argument/option parsing
- requests 2.28+ - HTTP client for ARM integration
- rich 13.0+ - Terminal formatting and logging
- tmdbv3api 1.9+ - TMDB metadata lookups for disc releases
- Next.js built-in `fetch()` - Native browser/Node.js fetch API (no external HTTP library)
## Configuration
- Environment variables only (no config files)
- Loaded at startup via `os.environ.get()`
- Validation at import time for required vars (e.g., `OVID_SECRET_KEY` via `_require_env()`)
- `api/alembic.ini` - Alembic migration config (sqlalchemy.url loaded from `DATABASE_URL` env var at runtime)
- `.env.example` - Development environment template
- `.env.production.example` - Production environment template
- `docker-compose.yml` - Base compose config (dev/standalone)
- `docker-compose.prod.yml` - Production overrides (gunicorn, no volumes, exposed ports)
- `docker-compose.test.yml` - Test environment overrides (holodeck test server)
- `web/next.config.ts` - Next.js config (output: "standalone" for Docker)
- `web/tsconfig.json` - TypeScript config with path alias `@/*`
- `api/requirements.txt` - Python production dependencies
- `ovid-client/pyproject.toml` - Setuptools-based package config (source layout: `src/`)
- `NEXT_PUBLIC_API_URL` - Baked into Next.js client bundles at build time via Docker ARG
## Platform Requirements
- Docker & Docker Compose v2 (for full stack)
- Python 3.12 (local development without containers)
- Node.js 24 (local web development without containers)
- PostgreSQL 16 (or via container)
- Docker (images: `python:3.12-slim`, `node:24-alpine`, `postgres:16-alpine`)
- Docker Compose v2 with profile support (`--profile mirror` for sync mode)
- Environment variables for all secrets
- Reverse proxy (redshirt mentioned in compose comments) for HTTPS
- Currently: holodeck (internal test server) via docker-compose
- Production: Canonical oviddb.org instance
- Self-hosted: Any platform supporting Docker
- Mirror nodes: Syncing read-only copies of the canonical database
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Overview
## Web (Next.js/TypeScript)
### Naming Patterns
- Components: PascalCase, e.g. `NavBar.tsx`, `DiscCard.tsx`, `SubmitForm.tsx`
- Pages: lowercase with hyphens for routes, e.g. `app/page.tsx`, `app/auth/callback/page.tsx`, `app/disc/[fingerprint]/page.tsx`
- Utilities/lib: camelCase, e.g. `lib/api.ts`, `lib/auth.ts`
- Tests: `{name}.test.ts` or `{name}.test.tsx`, located in `src/__tests__/`
- camelCase (exported): `searchReleases()`, `getDisc()`, `useAuth()`
- camelCase (helpers): `_error_response()`, `_build_track_response()`
- Prefix underscore for internal/private helper functions within modules
- Hook naming: `use*` prefix, e.g. `useAuth()`
- camelCase for runtime values: `discCard`, `authState`, `searchResult`
- UPPERCASE for constants: `TOKEN_KEY`, `API_URL`, `TYPE_COLORS`
- Structured constants as maps: `TYPE_COLORS: Record<string, string>`
- PascalCase for interfaces and types: `AuthState`, `DiscLookupResponse`, `UserResponse`
- Suffix `Response` for API response schemas: `DiscLookupResponse`, `ReleaseResponse`, `TrackResponse`
- Suffix `Create` for request/input schemas: `DiscSubmitRequest`, `ReleaseCreate`, `TitleCreate`
- Suffix `Props` or leave unnamed for React component props
### Code Style
- ESLint with Next.js defaults (`eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`)
- Config: `web/eslint.config.mjs` uses flat config format (ESLint 9+)
- No Prettier configured — rely on ESLint
- TypeScript `strict: true` in `tsconfig.json`
- Core Web Vitals checks enforced
- TypeScript strict mode required
- All .ts and .tsx files included
### Import Organization
- `@/` resolves to `/Users/trekkie/projects/OVID/web/` (configured in `tsconfig.json`)
- Use `@/lib/*` for utilities, `@/components/*` for components, `@/app/*` for pages
### Error Handling
- Custom `ApiError` class extending `Error` with properties: `status`, `code`, `message`
- Thrown when fetch response is not ok
- Catches JSON parse failures and provides fallback error body
- Higher-level consumers catch `ApiError` and display human-readable messages
- `app/page.tsx`: Wraps API calls in try/catch, stores `searchError` string in local state
- Display error blocks with conditional rendering: check `if (searchError)` before rendering error UI
- No global error boundary observed — use local state for user feedback
- `useAuth()` in `lib/auth.ts`: Catches auth failures, clears invalid tokens, returns null user
- Uses isMounted pattern to prevent state updates on unmounted components (`cancelled` flag)
### Logging
- No structured logging in client code
- API errors logged implicitly through ErrorResponse UI
- Test logs via `console` in tests (not observed in production code)
### Comments
- Module-level comments explain purpose: `// OVID API client — typed fetch wrapper for both server and client components`
- Section dividers with dashed lines: `// ---------------------------------------------------------------------------`
- Conditional comments for non-obvious logic: `// Server-side: use internal Docker network URL`, `// Client-side: use public URL`
- No JSDoc observed in component code
- Single-line comments with `//` for inline notes
- Block comments with divider lines for section separation
- Comments precede the code they describe
### Function Design
- Explicit over spread: `{ release }` for component props
- Typed: all function params have TypeScript annotations
- Optional params use `?:` syntax: `const yearNum = params.year ? parseInt(params.year, 10) : undefined`
- Functions return typed values (Promise<T>, ReactElement, etc.)
- Async server components: `async function HomePage()` returns JSX directly
- Hooks return object with named properties: `{ user, token, loading, logout }`
- Utility functions return single typed value or tuple (rare)
### Module Design
- Default export for single-export modules: `export default function NavBar() { ... }`
- Named exports for utility/schema modules: `export interface AuthState { ... }`, `export function getToken() { ... }`
- Mix of defaults and named in some: `lib/api.ts` exports `class ApiError` (named) and multiple functions (named)
- Not used; imports reference specific files
- Related types and functions colocated: `lib/api.ts` contains all response/request types and fetch functions
- Auth logic isolated: `lib/auth.ts` for token helpers and `useAuth` hook
- One component per file
## API (FastAPI/Python)
### Naming Patterns
- Modules: lowercase_with_underscores: `app/routes/disc.py`, `app/auth/deps.py`, `app/models.py`
- Test files: `test_*.py` in `api/tests/`
- snake_case: `get_current_user()`, `decode_access_token()`, `_build_track_response()`
- Prefix underscore for private/internal: `_error_response()`, `_auth_aware_key()`, `_dynamic_limit()`
- Async endpoint functions: `async def lookup_disc_by_upc()`, `async def submit_disc()`
- PascalCase for models and exceptions: `User`, `Disc`, `ApiError`
- Suffix `Response` or `Request` for schemas: `DiscLookupResponse`, `DiscSubmitRequest`
- SQLAlchemy models use table names: `User`, `Disc`, `DiscEdit`
- snake_case: `user_id`, `disc_fingerprint`, `request_id`
- UPPERCASE for module-level constants: `TOKEN_KEY`, `SECTOR_SIZE`, `JWT_EXPIRY_DAYS`
### Code Style
- No strict formatter configured; follows PEP 8 conventions
- Type hints required on function signatures: `def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:`
- Docstrings for public functions and classes (reStructuredText style observed)
- No linter config detected in repo (`.ruff_cache/` present but no `ruff.toml`)
- Assume standard Python conventions
### Import Organization
### Error Handling
- **Missing auth**: `HTTPException(status_code=401, detail={"error": "missing_token"})`
- **Expired token**: `HTTPException(status_code=401, detail={"error": "expired_token"})`
- **Invalid token**: `HTTPException(status_code=401, detail={"error": "invalid_token"})`
- **Rate limit**: Custom `rate_limit_exceeded_handler()` returns `JSONResponse(status_code=429, content={...})`
- **Mirror mode**: `MirrorModeMiddleware` returns `JSONResponse(status_code=405, content={"error": "mirror_mode", ...})`
### Logging
- WARNING level for noteworthy events: `logger.warning("rate_limit_exceeded key=%s limit=%s path=%s", ...)`
- DEBUG level for trace info: `logger.debug("sync_seq_incremented new_seq=%d", row.current_seq)`
- Guard logging: Include key context like `user_id`, `request_id`, `fingerprint`
- No f-strings in logs; use %-style formatting: `logger.warning("auth_user_not_found sub=%s", sub)`
### Comments
- Module docstrings explain purpose and design: `"""Disc-related API endpoints — /v1 router."""`
- Section dividers for logical groups: `# ---------------------------------------------------------------------------`
- Complex logic gets inline explanations: `# The CHECK constraint ``id = 1`` enforces exactly one row`
- Raises docstring clause for exceptions: `Raises: HTTPException(401) with...`
### Function Design
- Explicit dependency injection via FastAPI `Depends()`: `db: Session = Depends(get_db)`
- Annotated types: `authorization: str | None = Header(default=None)`
- Path/query params use FastAPI converters: `upc: str`, `page: int = Query(1)`
- Pydantic model instances for API responses: `DiscLookupResponse(...)`
- `JSONResponse` for custom error shapes
- Async functions: declare `async def`, use `await` for I/O
### Module Design
- Routes exported as `router = APIRouter(...)`, included via `app.include_router(router)`
- Dependency functions exported individually: `from app.deps import get_db`
- Models imported for type hints and queries
- Routes isolated by domain: `app/routes/disc.py`, `app/routes/sync.py`
- Auth logic grouped: `app/auth/jwt.py`, `app/auth/deps.py`, `app/auth/users.py`
- Models and schemas in separate files: `app/models.py`, `app/schemas.py`
- Middleware in `app/middleware.py`
## ovid-client (Python CLI/Library)
### Naming Patterns
- Modules: lowercase_with_underscores: `fingerprint.py`, `bd_disc.py`, `ifo_parser.py`, `cli.py`
- Test files: `test_*.py` in `tests/`
- Readers: `readers/base.py`, `readers/drive.py`, `readers/iso.py`, `readers/bd_folder.py`, `readers/folder.py`
- snake_case: `build_canonical_string()`, `compute_fingerprint()`, `encode_bcd_time()`
- Prefix underscore for internal: `_to_bcd()`, `_sqlite_uuid_compat()`
- PascalCase for types and parsers: `VMGInfo`, `VTSInfo`, `AudioStream`, `PGCInfo`
- Suffix with domain: `AudioStream`, `SubtitleStream`, `DiscTrack`
- snake_case: `vts_count`, `pgc_list`, `language_code`
- UPPERCASE for constants: `SECTOR_SIZE`, `_ALGORITHM`, `_ISSUER`
### Code Style
- Type hints on function signatures
- Docstrings with module-level explanations
- Future imports: `from __future__ import annotations` for forward compatibility
### Comments
- Module docstrings: `"""OVID-DVD-1 fingerprint algorithm: canonical string builder and SHA-256 hash."""`
- Section dividers: `# ---------------------------------------------------------------------------`
- Algorithm explanations in docstrings with examples
## Cross-Codebase Patterns
### Request/Response ID Tracking
### Error Response Shape
### Status Constants
## Recommended Conventions for New Code
- Use `@/` absolute imports for all local imports
- Prefix private helper functions with underscore: `_buildResponse()`
- Return typed objects from hooks, not arrays
- Handle errors with try/catch, store message in local state
- Use `data-testid` attributes for all interactive elements
- Use snake_case for all identifiers
- Wrap risky operations in try/except, re-raise as HTTPException
- Use structured logging with context keys
- Docstring all public functions with Args/Returns/Raises sections
- Build schemas in `app/schemas.py` alongside models
- Module docstrings explain algorithm/purpose
- Use section dividers for logical grouping
- Type hint all function signatures
- Prefix private helpers with underscore
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Stateless API (horizontal scalability)
- Disc-centric data model with precise schema for structure metadata
- Community contribution + verification workflow (OAuth multi-provider)
- Sync feed for downstream mirrors (monotonic sequence numbers, CC0 snapshots)
- Mirror mode capability (read-only deployment variant)
## Layers
- Purpose: Parse physical disc formats (DVD, Blu-ray, UHD) and compute stable hash fingerprints
- Location: `ovid-client/src/ovid/`
- Contains: Disc readers (folder, ISO, drive), IFO/MPLS parsers, fingerprint algorithms
- Depends on: `libdvdread`/`libbluray` (system libraries)
- Used by: CLI (`ovid fingerprint`), web submit UI, ARM integration
- Purpose: Repository for disc fingerprints, metadata, community verification, and mirroring
- Location: `api/app/`
- Contains: ORM models, route handlers, auth, rate limiting, sync state management
- Depends on: FastAPI, SQLAlchemy, PostgreSQL, Authlib (OAuth)
- Used by: Web UI, CLI lookup/submit, mobile apps, ARM, downstream mirrors
- Purpose: Search, discover, and submit disc metadata through interactive interface
- Location: `web/`
- Contains: Next.js App Router pages, components, API client wrapper
- Depends on: Next.js 16, React 19, Tailwind CSS
- Used by: End users, contributors, verifiers
- Purpose: Persistent storage for disc registry, user accounts, edit history, sync state
- Location: `api/alembic/` (migrations)
- Schema: 9 core tables + 3 supporting tables
- Primary keys: UUID v4 throughout
## Data Flow
```
```
```
```
- **Disc lifecycle:** unverified → disputed → verified (or rejected)
- **Sync state:** Stored in `sync_state` key-value table (snapshot metadata, last_sync timestamp)
- **OAuth state:** Stored in `request.session` (CSRF protection via SessionMiddleware)
- **Rate limit state:** In-memory per-IP counter (slowapi, reset between requests)
## Key Abstractions
- Purpose: Represents a unique physical disc pressing (structural identity)
- Examples: `api/app/models.py:Disc`, `ovid-client/src/ovid/disc.py:Disc`
- Pattern: Immutable once created; inherent structure never changes (DVD pressing is fixed)
- Fingerprint: Deterministic, stable hash of title/chapter/track layout
- Purpose: A playback title/program on a disc (e.g., main feature, trailer, bonus feature)
- Examples: `api/app/models.py:DiscTitle`, `ovid-client/src/ovid/ifo_parser.py:VTSInfo`
- Contains: Title index, duration, chapter count, track list
- Relationship: 1..* from Disc
- Purpose: Audio, subtitle, or video stream within a title
- Examples: `api/app/models.py:DiscTrack`
- Metadata: Language, codec, channels, is_default flag
- Relationship: 1..* from DiscTitle
- Purpose: Canonical movie/TV show metadata (TMDB/IMDB linked)
- Examples: `api/app/models.py:Release`
- Pattern: Shared across discs (many-to-many join via `disc_releases`)
- Metadata: Title, year, content_type (movie/tv), TMDB/IMDB IDs
- Purpose: Multi-disc grouping (e.g., "complete series", "box set")
- Examples: `api/app/models.py:DiscSet`
- Relationship: Many discs → 1 release through 1 DiscSet
- Fields: Edition name, total_discs count
- Purpose: Stateless HTTP wrapper for API calls from CLI and web
- Examples: `ovid-client/src/ovid/client.py:OVIDClient`
- Pattern: Dependency injection of base_url and token (OAuth JWT)
- Methods: lookup(), submit() with error translation to ClickException
## Entry Points
- Location: `ovid-client/src/ovid/cli.py:main()`
- Triggers: `pip install -e ovid-client/ && ovid fingerprint <path>`
- Responsibilities:
- Location: `api/main.py:app` (FastAPI instance)
- Triggers: `uvicorn main:app` or `docker compose up api`
- Responsibilities:
- Location: `web/app/page.tsx` (Next.js root page)
- Triggers: `npm run dev` or deployed at `https://ovid.example.com`
- Responsibilities:
## Error Handling
```python
```
- Use `click.ClickException` with structured error messages
- Exit code 1 on failure, 0 on success
- Client.submit() and Client.lookup() raise ClickException on HTTP errors
- Catch fetch errors in async server components
- Display user-friendly error banner
- Include retry links where appropriate
## Cross-Cutting Concerns
- Framework: Python `logging` (api), JavaScript console (web)
- Level: DEBUG (local), INFO (production)
- Key events: sync_seq_incremented, mirror_mode_blocked, sync_diff (paginated), rate limit hits
- Format: Structured (key=value pairs)
- API: Pydantic schemas (`api/app/schemas.py`) — strict validation on POST bodies
- CLI: Click argument/option validation
- Web: Fetch error handling with typed response interfaces
- Provider: Multi-provider OAuth (GitHub, Apple, Google, Mastodon, IndieAuth)
- Token: JWT stored in localStorage (web) or env var (CLI)
- Flow: OAuth callback → exchange code for token → create/link user
- Scope: Read (lookup, search), Write (submit disc, verify, dispute resolve)
- Library: slowapi (async rate limiter)
- Rules: Dynamic per IP/auth (see `_dynamic_limit()` in `app/rate_limit.py`)
- Endpoints: All routes wrapped with `@limiter.limit()`
- Response: 429 JSON with Retry-After header
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
