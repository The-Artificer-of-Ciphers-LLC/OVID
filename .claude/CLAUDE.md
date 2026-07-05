<!-- GSD:project-start source:PROJECT.md -->

## Project

**OVID — Open Video Disc Identification Database**

OVID is an open, community-driven database that identifies physical DVD, Blu-ray, and 4K UHD discs by a stable structural fingerprint and maps them to rich release metadata (edition, disc layout, main-feature marker, per-title chapters, audio/subtitle tracks). It is "MusicBrainz for video discs," built primarily as a first-pass metadata provider for the Automatic Ripping Machine (ARM) and similar home-media ripping tools. It ships as a FastAPI + PostgreSQL service, a `ovid-client` Python library/CLI, and a Next.js web UI.

**Core Value:** Given a disc in any drive, OVID returns the correct disc identity and structure — deterministically and reproducibly — so ripping tools can name, tag, and route content without manual correction.

### Constraints

- **Tech stack**: Python 3.12 + FastAPI + PostgreSQL 16 + SQLAlchemy 2.x/Alembic (API); Python `ovid-client` (click/rich CLI); Next.js 16 + React 19 + Tailwind 4 (web); Docker Compose (uvicorn dev, gunicorn prod) — established, do not re-platform
- **Compatibility**: `dvd1-*` (OVID-DVD-1) public fingerprint MUST remain stable and resolvable — no lookup/submission fragmentation during the libdvdread migration (ADR 0001)
- **Performance**: API p95 ≤ 500ms under load
- **Data license**: CC0 (public domain), no single commercial gatekeeper
- **Legal**: no DRM circumvention, no decryption-key storage, no video content/disc images
- **Git**: simplified Gitflow — `feature/*` → `develop` → `release/0.2.0` → `main`; Conventional Commits; nothing committed directly to `main`
- **Testing**: pytest (API against in-memory SQLite via TestClient; `ovid-client` with `real_disc` hardware markers), Vitest (web)

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.12 (CI), `>=3.9` supported — API server (`api/`) and disc-fingerprinting client (`ovid-client/`)
- TypeScript — web frontend (`web/`), Next.js 16 App Router
- Shell scripts — `arm/entrypoint_wrapper.sh`, `arm/start_arm_container.sh` (Automatic Ripping Machine integration)
- Bash/YAML — CI workflows in `.github/workflows/`

## Runtime

- Python 3.12 (`api/Dockerfile`, `.github/workflows/ci.yml`), `ovid-client` declares `requires-python = ">=3.9"` in `ovid-client/pyproject.toml`
- Node.js (version implied by Next.js 16 / React 19 requirements, no `.nvmrc` present) for `web/`
- pip for both Python projects (`api/requirements.txt`, `ovid-client/pyproject.toml`)
- npm for `web/` (`web/package-lock.json` present)
- Lockfile: present for web (`package-lock.json`); Python projects use unpinned/range-pinned `requirements.txt` (no `requirements.lock` or `poetry.lock`)

## Frameworks

- FastAPI `>=0.110,<1.0` — API server, `api/main.py`
- SQLAlchemy `>=2.0,<3.0` (asyncio extra) — ORM, `api/app/models.py`, `api/app/database.py`
- Alembic `>=1.13,<2.0` — DB migrations, `api/alembic/`
- Next.js `16.2.2` + React `19.2.4` — web frontend, `web/app/`
- Tailwind CSS `^4` — styling, `web/postcss.config.mjs`
- pytest `>=7.0` — both `api/tests/` and `ovid-client/tests/`
- Vitest `^4.1.2` + Testing Library (`@testing-library/react`, `jest-dom`, `user-event`) — `web/src/__tests__/`, config in `web/vitest.config.ts`
- uvicorn `[standard] >=0.29,<1.0` — ASGI dev server for API, invoked via `docker-compose.yml`
- gunicorn `>=21.2,<24.0` — production ASGI process manager, `api/Dockerfile`
- ESLint `^9` with `eslint-config-next` — `web/eslint.config.mjs`
- mkdocs — documentation site, `mkdocs.yml`, `docs/`

## Key Dependencies

- `authlib >=1.3,<2.0` — OAuth client (GitHub, Google) and Apple Sign-In JWT handling, `api/app/auth/routes.py`
- `PyJWT >=2.8,<3.0` — JWT issuance/verification, `api/app/auth/jwt.py`
- `itsdangerous >=2.1,<3.0` — signed session/token support (used by Starlette `SessionMiddleware`)
- `slowapi >=0.1.9,<1.0` — rate limiting, `api/app/rate_limit.py`
- `httpx >=0.27,<1.0` — outbound HTTP (OAuth token exchange, mirror sync), `api/app/sync.py`
- `pycdlib >=1.14` — DVD/Blu-ray filesystem parsing, `ovid-client/src/ovid/`
- `tmdbv3api >=1.9` — TMDB metadata lookup during disc submission, `ovid-client/src/ovid/tmdb.py`
- `click >=8.0`, `rich >=13.0` — CLI framework and terminal UI, `ovid-client/src/ovid/cli.py`
- `psycopg2-binary >=2.9,<3.0` — PostgreSQL driver, `api/app/database.py`
- `postgres:16-alpine` (Docker image) — primary datastore, `docker-compose.yml`

## Configuration

- `.env` (git-ignored) copied from `.env.example`; loaded via `docker-compose` env interpolation and `os.environ` in Python
- Key vars: `OVID_DB_NAME`, `OVID_DB_USER`, `OVID_DB_PASSWORD`, `DATABASE_URL`, `OVID_SECRET_KEY`, `OVID_API_URL`, `LOG_LEVEL`, `CORS_ORIGINS`, `OVID_MODE` (standalone/mirror/canonical), `SYNC_SOURCE_URL`, `SYNC_INTERVAL_MINUTES`
- OAuth provider vars (all optional, feature-gated on presence): `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET`, `APPLE_CLIENT_ID`/`APPLE_TEAM_ID`/`APPLE_KEY_ID`/`APPLE_PRIVATE_KEY`, `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` — validated in `api/app/auth/config.py` and `api/app/auth/routes.py`
- `api/app/auth/config._require_env` raises at import time if `OVID_SECRET_KEY` is missing — fail-fast pattern for required secrets
- `.env.production.example` referenced (for `oviddb.org` canonical deployment) — not read directly per forbidden-files policy
- `web/next.config.ts`, `web/tsconfig.json`, `web/postcss.config.mjs` — frontend build config
- `api/alembic.ini` + `api/alembic/env.py` — migration runner config
- `docker-compose.yml` (dev), `docker-compose.test.yml`, `docker-compose.prod.yml` — three environment-specific compose stacks

## Platform Requirements

- Docker + Docker Compose (primary dev workflow: `docker-compose up`)
- Local Python 3.12 + Node.js for running services outside Docker
- Optional: real DVD/Blu-ray disc or fixture files for `ovid-client` disc-reading tests (`OVID_TEST_DISC_PATH` env var, `real_disc` pytest marker)
- Docker-based deployment (`api/Dockerfile`, `web/Dockerfile`, `docker-compose.prod.yml`)
- PostgreSQL 16
- Canonical server at `oviddb.org`; self-hosted mirror/standalone instances supported per `docs/self-hosting.md`, `docs/deployment.md`
- ARM (Automatic Ripping Machine) integration for disc identification pipeline, `arm/`

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Repo Layout Relevant to Conventions

- `api/` — Python 3 / FastAPI backend (`api/app/`, routes in `api/app/routes/`)
- `ovid-client/` — Python 3 disc-fingerprinting CLI/library (`ovid-client/src/ovid/`)
- `web/` — TypeScript / Next.js 16 (React 19) frontend (`web/app/`, `web/components/`, `web/lib/`)
- `arm/` — standalone Python scripts for automated ripping identification (no package structure)

## Naming Patterns

- Files: `snake_case.py` (`disc_identity.py`, `rate_limit.py`, `mirror_mode` concepts embedded in `sync.py`)
- Functions/variables: `snake_case` (`resolve_disc_identity`, `_disc_to_response`, `submitted_by_id`)
- Private/internal helpers prefixed with `_` (`_error_response`, `_releases_match`, `_build_track_response`, `_sqlite_uuid_compat`)
- Classes: `PascalCase` for models/schemas/exceptions (`Disc`, `DiscSubmitRequest`, `DiscIdentityConflict`)
- Test classes group scenarios: `TestDiscSubmit`, `TestDiscSubmitErrors` (see `api/tests/test_disc_submit.py`)
- Constants: `UPPER_SNAKE_CASE` (`STATUS_CONFIDENCE` in `api/app/schemas.py`)
- Component files: `PascalCase.tsx` (`SubmitForm.tsx`, `ProviderList.tsx` in `web/components/`)
- Route files follow Next.js App Router convention: `web/app/<route>/page.tsx`
- Hooks/libs: `camelCase.ts` (`web/lib/auth.ts`, `web/lib/api.ts`)
- Dynamic route segments use bracket syntax: `web/app/disc/[fingerprint]/`
- Test files: `*.test.ts` / `*.test.tsx` co-located in `web/src/__tests__/`

## Code Style

- No `ruff`/`black`/`mypy` config detected in `api/` or `ovid-client/` — no enforced formatter/linter config file found (check for drift before assuming a style tool runs in CI)
- Modern type hints used throughout: `str | None`, `uuid.UUID | None`, `list[str]` (Python 3.10+ union syntax), confirmed in `api/app/routes/disc.py` and `api/app/schemas.py`
- Function signatures are fully type-annotated including return types (`def _build_track_response(track: DiscTrack) -> TrackResponse:`)
- Module docstrings appear at top of every file, one line, describing the module's purpose (e.g., `"""Disc-related API endpoints — /v1 router."""`)
- Section dividers use comment banners:
- Pydantic v2 (`pydantic.BaseModel`, `Annotated[str, Field(...)]`) for all request/response schemas — see `api/app/schemas.py`
- `strict: true` in `web/tsconfig.json` — write fully-typed code, no implicit `any`
- Path alias `@/*` maps to repo root of `web/` (configured in both `tsconfig.json` and `vitest.config.ts`)
- ESLint via flat config (`web/eslint.config.mjs`) extending `eslint-config-next` core-web-vitals + typescript rulesets

## Import Organization

- Standard library first, then third-party, then local `app.*` imports — visible in `api/app/routes/disc.py`:
- Test files import fixtures/helpers from `app.*` directly; `conftest.py` patches `os.environ["DATABASE_URL"]` **before** any `app` import, with `# noqa: E402` on subsequent imports to suppress the resulting lint warning — this ordering is load-bearing, not accidental (see `api/tests/conftest.py` lines 11-31)
- Vitest/testing-library imports first, then component imports via `@/` alias, then mocks:

## Error Handling

- Consistent JSON error envelope built via a shared helper, not raised HTTPException per-case:
- Domain-specific exceptions are defined per module and caught at the route boundary to produce the structured response, e.g. `DiscIdentityConflict` in `api/app/disc_identity.py` (raised on fingerprint/alias collision), caught in `disc.py` and converted via `_identity_conflict_response()`.
- HTTP status codes are chosen deliberately per business state, not just success/failure: e.g. duplicate submission with conflicting metadata returns `200` with a `disputed` status body rather than an error — domain state, not transport failure (`api/tests/test_disc_submit.py::test_submit_duplicate_fingerprint_conflicting_metadata`).
- Every response includes a `request_id` (both in body and as `x-request-id` header) for traceability — asserted directly in tests.
- Typed error class pattern: `ApiError extends Error` carrying `status` and `code` fields, defined in `web/lib/api.ts` and mocked identically in tests (`web/src/__tests__/submit.test.tsx`).
- UI surfaces parse/validation errors via dedicated `data-testid` elements (`parse-error`) rather than generic alerts — follow this pattern for new form validation.

## Testing-Adjacent Conventions (see TESTING.md for framework details)

- Python tests use `data-testid`-equivalent explicit `assert` on JSON response fields, never snapshot testing.
- Frontend tests query DOM via `data-testid` attributes (`fp-file-input`, `fp-preview`) rather than text/role queries where the target is a specific control — assign a `data-testid` to any new interactive element intended to be tested this way.

## Comments

- Docstrings are used for "why", not "what" — e.g. `conftest.py`'s SQLite/UUID compatibility shim explains *why* the hack is necessary (SQLAlchemy Postgres UUID type doesn't map cleanly to SQLite) rather than restating the code.
- Inline comments explain non-obvious business rules (e.g., "SQLite stores UUIDs as strings; compare string representations" in `test_disc_submit.py`).

## Module Design

- Routes (`api/app/routes/disc.py`, `api/app/routes/sync.py`) contain thin FastAPI endpoint functions plus private `_helper` functions for response-shaping directly above/below their usage — helpers are not extracted to a separate module unless shared across routes.
- Domain logic (identity resolution, conflict detection) lives in dedicated modules outside `routes/` (`api/app/disc_identity.py`, `api/app/sync.py`) and is imported into routes — keep business logic out of route handlers when it's non-trivial.
- Schemas (`api/app/schemas.py`) are centralized in one file, not split per-route.
- `web/lib/` holds cross-cutting concerns (`auth.ts`, `api.ts`) consumed via hooks (`useAuth`) and functions (`submitDisc`), imported through the `@/lib/...` alias and mocked wholesale in tests with `vi.mock`.
- `web/components/` holds reusable, testable UI components separate from `web/app/**/page.tsx` route files.

## AGENTS.md / Project-Specific Guidance

- `web/AGENTS.md` (linked via `web/CLAUDE.md`) explicitly warns: this Next.js version (16.2.2) has breaking changes vs. training-data assumptions — consult `node_modules/next/dist/docs/` before writing App Router code, and heed deprecation notices. Treat any Next.js API usage in `web/` as needing verification against installed docs rather than memory.

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

- **sync worker** (`api/scripts/sync.py`, `--daemon` mode) — mirrors a remote OVID instance into a local read replica when `OVID_MODE=mirror`.
- **sync API** (`api/app/routes/sync.py`) — exposes `/v1/sync/head`, `/v1/sync/diff`, `/v1/sync/snapshot` so mirror instances can pull incremental changes keyed on `global_seq`.

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| FastAPI app bootstrap | Wires middleware, routers, CORS, rate limiting, mirror-mode guard | `api/main.py` |
| Disc routes | Register/submit/lookup/verify/dispute/search endpoints (`/v1/disc*`, `/v1/search`) | `api/app/routes/disc.py` |
| Sync routes | Mirror feed endpoints (`/v1/sync/head`, `/diff`, `/snapshot`) | `api/app/routes/sync.py` |
| Disc identity resolution | Resolves/attaches fingerprint aliases, detects identity conflicts | `api/app/disc_identity.py` |
| ORM models | 9 core tables + `global_seq` counter | `api/app/models.py` |
| Pydantic schemas | Request/response contracts for all API routes | `api/app/schemas.py` |
| Auth | OAuth (IndieAuth, Mastodon, Google, GitHub, Apple), JWT issuance, session deps | `api/app/auth/` |
| Rate limiting | Dynamic per-auth-state limits via slowapi | `api/app/rate_limit.py` |
| Middleware | Request-ID tagging, mirror read-only enforcement | `api/app/middleware.py` |
| Sync engine | `next_seq()` atomic counter, sync payload builders | `api/app/sync.py` |
| Disc reading (client) | Format-specific readers for DVD/BD/UHD sources | `ovid-client/src/ovid/readers/` |
| Fingerprinting (client) | Structural hash computation from IFO/MPLS parses | `ovid-client/src/ovid/bd_fingerprint.py`, `fingerprint.py`, `disc_identity.py` |
| Disc structure normalization | Format-neutral projection (titles/chapters/tracks) shared by DVD and BD | `ovid-client/src/ovid/disc_structure.py` |
| CLI | `ovid fingerprint`, `ovid lookup`, `ovid submit` commands | `ovid-client/src/ovid/cli.py` |
| API client (Python) | Thin `requests`-based wrapper used by CLI and ARM integration | `ovid-client/src/ovid/client.py` |
| ARM integration | Non-blocking lookup wrapper called from ARM's ripping pipeline | `arm/identify_ovid.py`, `arm/identify.py` |
| Web frontend | Next.js App Router UI for search, submit, disputes, settings | `web/app/`, `web/components/`, `web/lib/` |

## Pattern Overview

- Layered backend: routes → identity/sync services → ORM models → Postgres, following FastAPI's typical dependency-injection style (`Depends(get_db)`, `Depends(get_current_user)`).
- Format-neutral abstraction boundary in the client library: DVD (libdvdread/IFO) and Blu-ray/UHD (MPLS/AACS) internals are hidden behind `Normalized Disc Structure` types (see `CONTEXT.md`) so downstream code (CLI, submission, API) never branches on disc format.
- Mirror/replica pattern: any OVID API instance can run in `standalone` or `mirror` mode (`OVID_MODE` env var); mirror mode is read-only (enforced by `MirrorModeMiddleware`) and pulls changes via the sync feed keyed by a monotonic `global_seq`.
- Fingerprint versioning: multiple Disc Identity Methods (`dvd1-*`, `dvdread1-*`) can coexist; lookups resolve through alias records rather than requiring a single canonical hash (`api/app/disc_identity.py`).

## Layers

- Purpose: HTTP request/response handling, request validation via Pydantic schemas, auth/rate-limit enforcement.
- Location: `api/app/routes/disc.py`, `api/app/routes/sync.py`, `api/app/auth/routes.py`
- Contains: FastAPI path operation functions, response shaping helpers (e.g. `_build_track_response`).
- Depends on: identity/sync services, ORM models, schemas, auth deps.
- Used by: external clients (CLI, web, ARM) over HTTP.
- Purpose: Disc identity resolution/conflict detection, sync sequence counter management.
- Location: `api/app/disc_identity.py`, `api/app/sync.py`
- Contains: `resolve_disc_identity`, `attach_lookup_aliases`, `resolve_existing_disc_for_identities`, `next_seq`.
- Depends on: ORM models, SQLAlchemy session.
- Used by: route layer.
- Purpose: SQLAlchemy ORM table definitions and session/engine setup.
- Location: `api/app/models.py`, `api/app/database.py`, `api/alembic/`
- Contains: 9 core tables plus `global_seq`; Alembic migrations under `api/alembic/versions/`.
- Depends on: SQLAlchemy, Postgres.
- Used by: service and route layers via `Depends(get_db)` (`api/app/deps.py`).
- Purpose: Read disc sources, parse format-specific structures, compute fingerprints, normalize to shared types, submit/query the API.
- Location: `ovid-client/src/ovid/readers/` (I/O), `ifo_parser.py`/`mpls_parser.py` (format parsing), `bd_disc.py`/`disc.py` (per-format disc objects), `disc_structure.py` (normalization), `disc_identity.py`/`fingerprint.py`/`bd_fingerprint.py` (identity), `client.py` (HTTP), `submission.py` (payload building), `cli.py` (entry point).
- Depends on: `pycdlib` (ISO), `libdvdread` (DVD identity), `requests` (HTTP), `click`/`rich` (CLI UX).
- Used by: `arm/identify_ovid.py`, end users via `ovid` CLI.
- Purpose: Browser UI for search, disc detail, submission wizard, dispute resolution, and account settings.
- Location: `web/app/` (Next.js App Router pages), `web/components/` (presentational/interactive components), `web/lib/` (`api.ts` API client, `auth.ts` auth helpers).
- Depends on: OVID API over HTTP (`web/lib/api.ts`).
- Used by: end users' browsers.

## Data Flow

### Primary Submission Path (client → API)

### Lookup Path

### Mirror Sync Path

- All durable state lives in PostgreSQL via SQLAlchemy ORM (`api/app/models.py`). No in-process caching layer. Sessions (web auth) use Starlette `SessionMiddleware` for OAuth CSRF state only, not app data.

## Key Abstractions

- Purpose: Format-neutral description of a disc's titles/chapters/tracks/fingerprint, hiding DVD IFO and Blu-ray MPLS/AACS details.
- Examples: `ovid-client/src/ovid/disc_structure.py`
- Pattern: Adapter/normalization layer — format-specific parsers (`ifo_parser.py`, `mpls_parser.py`) produce raw structures, `normalize_disc_structure()` projects into the shared shape.
- Purpose: Uniform interface for reading disc contents regardless of source medium.
- Examples: `ovid-client/src/ovid/readers/base.py` (ABC), `folder.py`, `bd_folder.py`, `iso.py`, `drive.py`
- Pattern: Strategy pattern selected by `open_reader()` factory based on path inspection.
- Purpose: Let multiple fingerprint strings (from different identity methods/versions, e.g. `dvd1-*`, `dvdread1-*`) resolve to one physical disc pressing while always exposing the canonical Primary Fingerprint.
- Examples: `api/app/disc_identity.py`, `ovid-client/src/ovid/disc_identity.py`
- Pattern: Alias table resolution with explicit conflict detection (`DiscIdentityConflict`).

## Entry Points

- Location: `api/main.py`
- Triggers: `uvicorn main:app` (see `docker-compose.yml` `api` service)
- Responsibilities: Middleware wiring, router registration, `/health` liveness endpoint.
- Location: `api/scripts/sync.py`
- Triggers: `python scripts/sync.py --daemon` (docker-compose `sync` service, `mirror` profile only)
- Responsibilities: Periodic pull of upstream diffs into a mirror database.
- Location: `ovid-client/src/ovid/cli.py`
- Triggers: `ovid fingerprint|lookup|submit` console entry point (see `ovid-client` packaging)
- Responsibilities: Local disc identification, interactive submission wizard.
- Location: `arm/identify_ovid.py`
- Triggers: Imported by ARM's own `identify.py` during automated disc ripping
- Responsibilities: Best-effort, non-blocking OVID lookup (never raises; 5s hard timeout).
- Location: `web/app/page.tsx` (home/search), `web/app/disc/[fingerprint]/page.tsx` (disc detail), `web/app/submit/page.tsx`, `web/app/disputes/page.tsx`, `web/app/settings/page.tsx`
- Triggers: Next.js App Router file-based routing
- Responsibilities: Browser-facing UI backed by `web/lib/api.ts`.

## Architectural Constraints

- **Threading:** FastAPI/uvicorn async request handling; SQLAlchemy sessions are per-request via `Depends(get_db)` (`api/app/deps.py`) — no shared mutable session state across requests.
- **Global state:** `GlobalSeq` is an intentional single-row table (`CheckConstraint("id = 1")`) acting as a DB-level global counter, incremented via `SELECT ... FOR UPDATE` in `next_seq()` (`api/app/sync.py`). No other module-level mutable singletons found in `api/app/`.
- **Mode-dependent behavior:** `OVID_MODE=mirror` env var changes middleware stack (adds `MirrorModeMiddleware`) and swaps the `sync` docker-compose profile from idle to a running polling daemon — a single codebase serves two operational roles.
- **Disc format branching is centralized:** format detection happens only in `ovid-client/src/ovid/readers/__init__.py` (`open_reader`) and in the CLI's `_open_disc`/`_detect_and_fingerprint` helpers; once a `Disc`/`BDDisc` is built, downstream code operates on the normalized structure only.

## Anti-Patterns

### Debug/fix scripts committed at repo root

## Error Handling

- Identity conflicts return HTTP 409 with a consistent shape (`_identity_conflict_response`).
- The ARM integration explicitly never raises — every failure path logs and returns `None` so a third-party ripping pipeline is never blocked (`arm/identify_ovid.py` module docstring).
- CLI catches `FileNotFoundError, ValueError, OSError` at the command boundary and exits with `click.echo(..., err=True)` + `sys.exit(1)` rather than letting stack traces surface (`ovid-client/src/ovid/cli.py:35-39`).

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
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
