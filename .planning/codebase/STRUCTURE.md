# Codebase Structure

**Analysis Date:** 2026-04-04

## Directory Layout

```
OVID/
├── api/                          # FastAPI REST service
│   ├── main.py                   # FastAPI app initialization
│   ├── app/
│   │   ├── models.py             # 9 core ORM models (Disc, Release, User, etc.)
│   │   ├── schemas.py            # Pydantic request/response schemas
│   │   ├── database.py           # SQLAlchemy engine & session factory
│   │   ├── deps.py               # Dependency injection (get_db, etc.)
│   │   ├── middleware.py         # RequestId, MirrorMode middlewares
│   │   ├── rate_limit.py         # slowapi rate limiting config
│   │   ├── sync.py               # Sync feed builders & seq counter
│   │   ├── auth/                 # OAuth, JWT, account linking
│   │   │   ├── routes.py         # /v1/auth/* endpoints
│   │   │   ├── jwt.py            # Token creation/validation
│   │   │   ├── users.py          # User upsert, OAuth link management
│   │   │   ├── config.py         # Secret key generation
│   │   │   ├── indieauth.py      # IndieAuth protocol handler
│   │   │   ├── mastodon.py       # Mastodon OAuth dynamic registration
│   │   │   └── deps.py           # get_current_user dependency
│   │   └── routes/               # Endpoint routers
│   │       ├── disc.py           # /v1/disc/* endpoints (lookup, submit, verify, search)
│   │       └── sync.py           # /v1/sync/* endpoints (mirror feed)
│   ├── alembic/                  # Database migrations (SQLAlchemy)
│   │   ├── env.py
│   │   └── versions/             # Timestamped migration files
│   └── tests/                    # API test suite (pytest)
│       ├── conftest.py           # Fixtures, SQLite test DB, seed helpers
│       ├── test_disc_*.py        # Disc lookup, submit, verify tests
│       ├── test_auth_*.py        # OAuth provider tests
│       └── test_sync_*.py        # Sync feed tests
│
├── ovid-client/                  # Python client library & CLI
│   ├── src/ovid/
│   │   ├── __init__.py
│   │   ├── cli.py                # Entry point: ovid fingerprint/lookup/submit
│   │   ├── client.py             # OVIDClient HTTP wrapper
│   │   ├── disc.py               # Disc class (high-level API)
│   │   ├── fingerprint.py        # Fingerprint algorithm (OVID-DVD-1)
│   │   ├── bd_fingerprint.py     # Blu-ray fingerprinting (OVID-BD-1)
│   │   ├── ifo_parser.py         # DVD IFO file parser
│   │   ├── mpls_parser.py        # Blu-ray MPLS parser
│   │   ├── bd_disc.py            # Blu-ray disc abstraction
│   │   ├── readers/              # Disc source abstraction
│   │   │   ├── base.py           # DiscReader interface
│   │   │   ├── folder.py         # VIDEO_TS/BDMV folder reader
│   │   │   ├── iso.py            # ISO 9660 image reader
│   │   │   ├── drive.py          # Block device reader
│   │   │   └── bd_folder.py      # Blu-ray folder reader
│   │   └── tmdb.py               # TMDB API client (release search)
│   └── tests/                    # Client test suite (pytest)
│       ├── conftest.py           # Fixtures, test data generators
│       ├── test_fingerprint.py   # Fingerprint algorithm tests
│       ├── test_bd_fingerprint.py # Blu-ray fingerprint tests
│       ├── test_disc.py          # Disc class tests
│       ├── test_cli_*.py         # CLI integration tests
│       └── test_readers.py       # Reader abstraction tests
│
├── web/                          # Next.js web application
│   ├── app/
│   │   ├── layout.tsx            # Root layout (fonts, metadata, navbar)
│   │   ├── page.tsx              # Home page (search form, results)
│   │   ├── auth/
│   │   │   └── callback/
│   │   │       └── page.tsx      # OAuth callback handler
│   │   ├── disc/
│   │   │   └── [fingerprint]/
│   │   │       └── page.tsx      # Disc detail page
│   │   ├── submit/
│   │   │   └── page.tsx          # Disc submission wizard
│   │   ├── disputes/
│   │   │   └── page.tsx          # Dispute resolution interface
│   │   ├── settings/
│   │   │   └── page.tsx          # User settings (OAuth unlink)
│   │   └── globals.css           # Tailwind CSS import
│   ├── components/               # Reusable React components
│   │   ├── NavBar.tsx            # Top navigation
│   │   ├── SearchForm.tsx        # Title/year search input
│   │   ├── DiscCard.tsx          # Release card in grid
│   │   ├── DiscStructure.tsx     # Title/track display tree
│   │   ├── EditHistory.tsx       # Disc edit log viewer
│   │   ├── SubmitForm.tsx        # Fingerprint upload & wizard
│   │   ├── DisputeResolver.tsx   # Verify/reject disputed discs
│   │   └── ProviderList.tsx      # OAuth provider link manager
│   ├── lib/
│   │   ├── api.ts                # Typed API client wrapper
│   │   └── auth.ts               # JWT storage & retrieval
│   ├── public/                   # Static assets
│   ├── package.json              # Next.js dependencies
│   └── tsconfig.json             # TypeScript config
│
├── docs/                         # Specification and reference documentation
│   ├── fingerprint-spec.md       # OVID-DVD-1 fingerprinting algorithm
│   ├── OVID-technical-spec.md    # Complete technical design
│   ├── OVID-product-spec.md      # Product requirements & user stories
│   ├── api-reference.md          # OpenAPI endpoint documentation
│   ├── cli-reference.md          # CLI command reference
│   ├── getting-started-dev.md    # Local development setup
│   └── docker-quickstart.md      # Docker Compose quick-start
│
├── tests/                        # Integration tests (system-level)
│   ├── conftest.py               # Shared fixtures
│   └── test_*.py                 # Full-stack test scenarios
│
├── scripts/                      # Utility scripts
│   └── dump_cc0.py               # Export CC0 snapshot for mirrors
│
├── docker-compose.yml            # Local dev (API + web + db)
├── docker-compose.test.yml       # Test runner (CI)
├── docker-compose.prod.yml       # Production deployment variant
│
├── .github/
│   └── workflows/
│       └── ci.yml                # GitHub Actions CI pipeline
│
└── README.md                     # Project overview
```

---

## Directory Purposes

**`api/`** — FastAPI REST service (Python)
- Purpose: Centralized disc metadata repository with OAuth, verification, sync
- Language: Python 3.10+
- Framework: FastAPI + SQLAlchemy ORM + PostgreSQL
- Entry: `api/main.py:app` → `uvicorn main:app`
- Contains: ORM models, route handlers, auth, middleware, migrations, tests

**`ovid-client/`** — Disc fingerprinting library & CLI (Python)
- Purpose: Parse DVD/Blu-ray/UHD discs, compute fingerprints, query/submit to API
- Language: Python 3.10+
- Framework: Click CLI + Pydantic + requests
- Entry: `ovid-client/src/ovid/cli.py:main()` → `ovid fingerprint`
- Contains: Disc readers, IFO/MPLS parsers, fingerprint algorithms, HTTP client

**`web/`** — Next.js web application (TypeScript/React)
- Purpose: Search discs, view details, submit fingerprints, manage OAuth accounts
- Language: TypeScript 5
- Framework: Next.js 16 (App Router) + React 19 + Tailwind CSS
- Entry: `web/app/page.tsx` → `npm run dev`
- Contains: Pages, components, API wrapper, styling

**`docs/`** — Specification and reference documentation (Markdown)
- Purpose: Algorithm specs, API reference, deployment guides
- Audience: Developers, integrators, operators

**`tests/`** — Integration test suite
- Purpose: Full-stack test scenarios (spanning API, client, optionally web)
- Framework: pytest
- Entry: `pytest tests/`

**`.planning/codebase/`** — GSD mapping documents
- Purpose: Architecture, structure, conventions, testing patterns for future Claude instances
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md

---

## Key File Locations

**Entry Points:**

- `api/main.py` — FastAPI server bootstrap (CORS, middleware, router registration)
- `api/app/routes/disc.py` — 22KB, all disc endpoints (lookup, submit, verify, search, edits, disputes, UPC lookup)
- `ovid-client/src/ovid/cli.py` — CLI main command group (fingerprint, lookup, submit)
- `web/app/page.tsx` — Home page with search form and paginated results

**Configuration:**

- `api/app/auth/config.py` — Secret key generation, environment variable setup
- `api/app/database.py` — SQLAlchemy engine, session factory
- `ovid-client/src/ovid/cli.py` — Click group decorators, command definitions
- `web/package.json` — npm dependencies, build scripts
- `web/tsconfig.json` — TypeScript compiler options (strict mode)

**Core Logic:**

- `api/app/models.py` — 387 lines, 9 core tables + 3 supporting (Disc, Release, DiscRelease, DiscTitle, DiscTrack, DiscSet, User, UserOAuthLink, DiscEdit, GlobalSeq, SyncState, MastodonOAuthClient)
- `api/app/schemas.py` — Pydantic models for request/response validation
- `ovid-client/src/ovid/fingerprint.py` — OVID-DVD-1 algorithm (canonical string → SHA256)
- `ovid-client/src/ovid/bd_fingerprint.py` — OVID-BD-1 algorithm (Blu-ray variant)
- `ovid-client/src/ovid/ifo_parser.py` — DVD IFO binary file parsing
- `ovid-client/src/ovid/mpls_parser.py` — Blu-ray MPLS playlist parsing

**Testing:**

- `api/tests/conftest.py` — 312 lines, SQLite test DB, seed helpers (seed_test_disc, seed_test_user)
- `ovid-client/tests/conftest.py` — Test disc fixtures
- `web/` — No dedicated test files (uses vitest config but components untested in repo)

**Authentication:**

- `api/app/auth/routes.py` — OAuth endpoints (/v1/auth/callback/{provider}, /v1/auth/me, /v1/auth/unlink/{provider})
- `api/app/auth/jwt.py` — JWT creation/validation (exp, iat, sub)
- `api/app/auth/users.py` — User upsert and OAuth link management
- `web/lib/auth.ts` — JWT storage in localStorage

**Synchronization:**

- `api/app/sync.py` — Monotonic sequence counter (next_seq), sync record builders
- `api/app/routes/sync.py` — Mirror feed endpoints (/v1/sync/head, /v1/sync/diff, /v1/sync/snapshot)

---

## Naming Conventions

**Files:**

- `.py` files: snake_case (e.g., `ifo_parser.py`, `disc_titles.py`)
- `.tsx/.ts` files: PascalCase (components, e.g., `SearchForm.tsx`); camelCase (libs, e.g., `api.ts`)
- API schemas: PascalCase + Response/Request suffix (e.g., `DiscLookupResponse`)
- Database tables: snake_case plural (e.g., `disc_titles`, `user_oauth_links`)

**Directories:**

- Lowercase snake_case (e.g., `ovid-client/`, `disc_sets/`)
- `readers/` (abstraction), `routes/` (endpoint routers), `auth/` (auth handlers)

**Python Classes:**

- ORM models (SQLAlchemy): PascalCase, singular (e.g., `Disc`, `DiscTitle`, `DiscEdit`)
- Pydantic schemas: PascalCase (e.g., `DiscLookupResponse`, `DiscSubmitRequest`)
- Enums: CapsCase (e.g., `UNAUTH_LIMIT`, `STATUS_CONFIDENCE`)

**TypeScript Types/Interfaces:**

- Interfaces: PascalCase (e.g., `DiscLookupResponse`, `TrackResponse`)
- Constants: UPPER_CASE (e.g., `MAX_DIFF_LIMIT`)

---

## Where to Add New Code

**New Disc-Related Endpoint:**

1. **Define schema** → `api/app/schemas.py` (Pydantic request/response)
2. **Add route** → `api/app/routes/disc.py` (async handler with `@router.get/post/etc`)
3. **Add test** → `api/tests/test_disc_*.py` (use `client`, `db_session`, `seeded_disc` fixtures)
4. **Document** → `docs/api-reference.md`

**New CLI Command:**

1. **Add function** → `ovid-client/src/ovid/cli.py` (with `@main.command()` and `@click.argument/@click.option`)
2. **Add logic** (if needed) → separate module in `ovid-client/src/ovid/` (e.g., `export.py`)
3. **Add tests** → `ovid-client/tests/test_cli_*.py` (call via Click's CliRunner)

**New Web Page:**

1. **Create page** → `web/app/{feature}/page.tsx` (export default async function, use App Router)
2. **Create components** → `web/components/{Feature}.tsx` if reusable
3. **Add to nav** → `web/components/NavBar.tsx` (add Link to new route)

**Shared Utilities:**

- **API helpers** → `api/app/deps.py` (dependency injection) or `api/app/sync.py` (sync builders)
- **Client helpers** → `ovid-client/src/ovid/client.py` (HTTP wrapper) or new module
- **Web helpers** → `web/lib/api.ts` (API client) or `web/lib/auth.ts` (auth)

---

## Special Directories

**`alembic/`:**
- Purpose: Alembic database migrations (SQLAlchemy)
- Generated: No (migrations are checked in)
- Committed: Yes (migration scripts are part of version control)
- How to use: `alembic upgrade head`, `alembic revision --autogenerate -m "..."`

**`migrations/`:**
- None (OVID uses Alembic, not Django/Rails style)

**`.next/`:**
- Purpose: Next.js build output (compiled JS, server components)
- Generated: Yes (`npm run build`)
- Committed: No (in .gitignore)

**`node_modules/`:**
- Purpose: npm dependencies
- Generated: Yes (`npm install`)
- Committed: No (lockfile committed)

**`.venv/`:**
- Purpose: Python virtual environment (pip dependencies)
- Generated: Yes (`python -m venv .venv && pip install -r requirements.txt`)
- Committed: No

**`uat_dirs/`:**
- Purpose: User acceptance test sample discs (fixture data for testing fingerprinting)
- Generated: No (checked in for CI)
- Committed: Yes (important for testing disc parsing)

---

*Structure analysis: 2026-04-04*
