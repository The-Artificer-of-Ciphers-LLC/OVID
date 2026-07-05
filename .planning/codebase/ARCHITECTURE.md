<!-- refreshed: 2026-07-05 -->
# Architecture

**Analysis Date:** 2026-07-05

## System Overview

```text
┌───────────────────────────────────────────────────────────────────┐
│                      Clients / Producers                          │
├───────────────────┬───────────────────┬───────────────────────────┤
│  ovid-client CLI   │  ARM integration  │      web (Next.js)        │
│ `ovid-client/src/` │     `arm/`        │        `web/`             │
└─────────┬──────────┴─────────┬─────────┴─────────────┬─────────────┘
          │  HTTP (requests)   │ imports ovid-client    │ HTTP (fetch)
          ▼                    ▼                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                     OVID API (FastAPI)  `api/app/`                │
│  routes/disc.py  routes/sync.py  auth/*  middleware.py            │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│           SQLAlchemy ORM models  `api/app/models.py`               │
│  discs, releases, disc_releases, disc_titles, disc_tracks,         │
│  disc_sets, users, user_oauth_links, disc_edits, global_seq        │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│                      PostgreSQL (docker-compose `db`)              │
└───────────────────────────────────────────────────────────────────┘
```

Two additional processes attach to the same database:
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

**Overall:** Client/server system split across three deployable units — a FastAPI backend (`api/`), a Python disc-identification library + CLI (`ovid-client/`), and a Next.js web frontend (`web/`) — connected by a versioned HTTP API (`/v1/...`). An optional fourth component (`arm/`) integrates the client library into a third-party ripping pipeline (Automatic Ripping Machine).

**Key Characteristics:**
- Layered backend: routes → identity/sync services → ORM models → Postgres, following FastAPI's typical dependency-injection style (`Depends(get_db)`, `Depends(get_current_user)`).
- Format-neutral abstraction boundary in the client library: DVD (libdvdread/IFO) and Blu-ray/UHD (MPLS/AACS) internals are hidden behind `Normalized Disc Structure` types (see `CONTEXT.md`) so downstream code (CLI, submission, API) never branches on disc format.
- Mirror/replica pattern: any OVID API instance can run in `standalone` or `mirror` mode (`OVID_MODE` env var); mirror mode is read-only (enforced by `MirrorModeMiddleware`) and pulls changes via the sync feed keyed by a monotonic `global_seq`.
- Fingerprint versioning: multiple Disc Identity Methods (`dvd1-*`, `dvdread1-*`) can coexist; lookups resolve through alias records rather than requiring a single canonical hash (`api/app/disc_identity.py`).

## Layers

**Route layer (`api/app/routes/`):**
- Purpose: HTTP request/response handling, request validation via Pydantic schemas, auth/rate-limit enforcement.
- Location: `api/app/routes/disc.py`, `api/app/routes/sync.py`, `api/app/auth/routes.py`
- Contains: FastAPI path operation functions, response shaping helpers (e.g. `_build_track_response`).
- Depends on: identity/sync services, ORM models, schemas, auth deps.
- Used by: external clients (CLI, web, ARM) over HTTP.

**Domain/service layer (`api/app/disc_identity.py`, `api/app/sync.py`):**
- Purpose: Disc identity resolution/conflict detection, sync sequence counter management.
- Location: `api/app/disc_identity.py`, `api/app/sync.py`
- Contains: `resolve_disc_identity`, `attach_lookup_aliases`, `resolve_existing_disc_for_identities`, `next_seq`.
- Depends on: ORM models, SQLAlchemy session.
- Used by: route layer.

**Data layer (`api/app/models.py`, `api/app/database.py`):**
- Purpose: SQLAlchemy ORM table definitions and session/engine setup.
- Location: `api/app/models.py`, `api/app/database.py`, `api/alembic/`
- Contains: 9 core tables plus `global_seq`; Alembic migrations under `api/alembic/versions/`.
- Depends on: SQLAlchemy, Postgres.
- Used by: service and route layers via `Depends(get_db)` (`api/app/deps.py`).

**Client library layer (`ovid-client/src/ovid/`):**
- Purpose: Read disc sources, parse format-specific structures, compute fingerprints, normalize to shared types, submit/query the API.
- Location: `ovid-client/src/ovid/readers/` (I/O), `ifo_parser.py`/`mpls_parser.py` (format parsing), `bd_disc.py`/`disc.py` (per-format disc objects), `disc_structure.py` (normalization), `disc_identity.py`/`fingerprint.py`/`bd_fingerprint.py` (identity), `client.py` (HTTP), `submission.py` (payload building), `cli.py` (entry point).
- Depends on: `pycdlib` (ISO), `libdvdread` (DVD identity), `requests` (HTTP), `click`/`rich` (CLI UX).
- Used by: `arm/identify_ovid.py`, end users via `ovid` CLI.

**Frontend layer (`web/`):**
- Purpose: Browser UI for search, disc detail, submission wizard, dispute resolution, and account settings.
- Location: `web/app/` (Next.js App Router pages), `web/components/` (presentational/interactive components), `web/lib/` (`api.ts` API client, `auth.ts` auth helpers).
- Depends on: OVID API over HTTP (`web/lib/api.ts`).
- Used by: end users' browsers.

## Data Flow

### Primary Submission Path (client → API)

1. User runs `ovid submit <path>` (`ovid-client/src/ovid/cli.py:73`)
2. `_open_disc(path)` picks a reader via `open_reader()` auto-detection (BDMV vs VIDEO_TS vs ISO vs block device) (`ovid-client/src/ovid/readers/__init__.py:70`)
3. Format-specific parser builds a `Disc`/`BDDisc` object, computing the fingerprint (`ovid-client/src/ovid/disc.py`, `ovid-client/src/ovid/bd_disc.py`)
4. `normalize_disc_structure()` projects into format-neutral titles/chapters/tracks (`ovid-client/src/ovid/disc_structure.py`)
5. CLI walks TMDB search, edition/disc-number prompts, then `build_submit_payload()` (`ovid-client/src/ovid/submission.py`)
6. `OVIDClient.submit(payload)` POSTs to `/v1/disc` with Bearer token (`ovid-client/src/ovid/client.py:57`)
7. `api/app/routes/disc.py:379` handler resolves identity via `resolve_disc_identity`/`resolve_existing_disc_for_identities` (`api/app/disc_identity.py`), detects conflicts (409), persists `Disc`/`Release`/`DiscTitle`/`DiscTrack` rows, bumps `global_seq` via `next_seq()` (`api/app/sync.py`)

### Lookup Path

1. `ovid lookup <fingerprint>` or web UI GET request
2. `GET /v1/disc/{fingerprint}` (`api/app/routes/disc.py:267`) queries `Disc` with `joinedload`/`selectinload` for releases/titles/tracks
3. `attach_lookup_aliases()` resolves secondary fingerprints back to the Primary Fingerprint before responding
4. Response serialized via `DiscLookupResponse` schema (`api/app/schemas.py`)

### Mirror Sync Path

1. Mirror instance starts `sync` service (`api/scripts/sync.py --daemon`, profile `mirror` in `docker-compose.yml`)
2. Worker polls `GET /v1/sync/head` then `GET /v1/sync/diff` against `SYNC_SOURCE_URL` on `SYNC_INTERVAL_MINUTES` (`api/app/routes/sync.py:44,62`)
3. Applies incremental changes to local tables, advancing local `global_seq`
4. `MirrorModeMiddleware` rejects all write HTTP methods on a mirror instance so it never diverges from upstream (`api/app/middleware.py`)

**State Management:**
- All durable state lives in PostgreSQL via SQLAlchemy ORM (`api/app/models.py`). No in-process caching layer. Sessions (web auth) use Starlette `SessionMiddleware` for OAuth CSRF state only, not app data.

## Key Abstractions

**Normalized Disc Structure:**
- Purpose: Format-neutral description of a disc's titles/chapters/tracks/fingerprint, hiding DVD IFO and Blu-ray MPLS/AACS details.
- Examples: `ovid-client/src/ovid/disc_structure.py`
- Pattern: Adapter/normalization layer — format-specific parsers (`ifo_parser.py`, `mpls_parser.py`) produce raw structures, `normalize_disc_structure()` projects into the shared shape.

**DiscReader:**
- Purpose: Uniform interface for reading disc contents regardless of source medium.
- Examples: `ovid-client/src/ovid/readers/base.py` (ABC), `folder.py`, `bd_folder.py`, `iso.py`, `drive.py`
- Pattern: Strategy pattern selected by `open_reader()` factory based on path inspection.

**Disc Identity / Lookup Alias:**
- Purpose: Let multiple fingerprint strings (from different identity methods/versions, e.g. `dvd1-*`, `dvdread1-*`) resolve to one physical disc pressing while always exposing the canonical Primary Fingerprint.
- Examples: `api/app/disc_identity.py`, `ovid-client/src/ovid/disc_identity.py`
- Pattern: Alias table resolution with explicit conflict detection (`DiscIdentityConflict`).

## Entry Points

**API server:**
- Location: `api/main.py`
- Triggers: `uvicorn main:app` (see `docker-compose.yml` `api` service)
- Responsibilities: Middleware wiring, router registration, `/health` liveness endpoint.

**Sync daemon:**
- Location: `api/scripts/sync.py`
- Triggers: `python scripts/sync.py --daemon` (docker-compose `sync` service, `mirror` profile only)
- Responsibilities: Periodic pull of upstream diffs into a mirror database.

**CLI:**
- Location: `ovid-client/src/ovid/cli.py`
- Triggers: `ovid fingerprint|lookup|submit` console entry point (see `ovid-client` packaging)
- Responsibilities: Local disc identification, interactive submission wizard.

**ARM hook:**
- Location: `arm/identify_ovid.py`
- Triggers: Imported by ARM's own `identify.py` during automated disc ripping
- Responsibilities: Best-effort, non-blocking OVID lookup (never raises; 5s hard timeout).

**Web app:**
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

**What happens:** Files like `fix_test.py`, `fix_test2.py`, `test_script.py`, `verify_t11.py` sit at the repository root alongside real project config (`root files` listing).
**Why it's wrong:** These look like ad-hoc debugging artifacts rather than part of the shipped system; they clutter the root and are not referenced by `docker-compose.yml`, `README.md`, or CI workflows.
**Do this instead:** Move any still-useful scripts into `scripts/` (which already exists) or `api/scripts/`; delete the rest.

## Error Handling

**Strategy:** FastAPI route handlers return structured JSON error bodies (`request_id`, `error`, `message`) via `_error_response()`/`_identity_conflict_response()` helpers (`api/app/routes/disc.py:52`) rather than raising unhandled exceptions. Rate-limit violations are converted to 429 JSON via a dedicated exception handler (`api/app/rate_limit.py`, registered in `api/main.py:50`).

**Patterns:**
- Identity conflicts return HTTP 409 with a consistent shape (`_identity_conflict_response`).
- The ARM integration explicitly never raises — every failure path logs and returns `None` so a third-party ripping pipeline is never blocked (`arm/identify_ovid.py` module docstring).
- CLI catches `FileNotFoundError, ValueError, OSError` at the command boundary and exits with `click.echo(..., err=True)` + `sys.exit(1)` rather than letting stack traces surface (`ovid-client/src/ovid/cli.py:35-39`).

## Cross-Cutting Concerns

**Logging:** Standard `logging` module throughout (`logging.getLogger(__name__)`), with ARM integration explicitly attaching a stderr handler if none exists so logs surface in ARM's log capture (`arm/identify_ovid.py`).

**Validation:** Pydantic schemas (`api/app/schemas.py`) validate all API request/response bodies; `STATUS_CONFIDENCE` centralizes status-to-confidence mapping logic.

**Authentication:** Multi-provider OAuth (IndieAuth, Mastodon, Google, GitHub, Apple) under `api/app/auth/`, each provider in its own module (`indieauth.py`, `mastodon.py`), issuing JWTs (`api/app/auth/jwt.py`) validated by `get_current_user` dependency (`api/app/auth/deps.py`) used across protected routes.

---

*Architecture analysis: 2026-07-05*
