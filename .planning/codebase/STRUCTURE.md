# Codebase Structure

**Analysis Date:** 2026-07-05

## Directory Layout

```
OVID/
├── api/                    # FastAPI backend service
│   ├── main.py             # App bootstrap, middleware, router registration
│   ├── app/
│   │   ├── auth/           # OAuth providers, JWT, session deps
│   │   ├── routes/         # HTTP route handlers (disc.py, sync.py)
│   │   ├── models.py       # SQLAlchemy ORM models (9 tables + global_seq)
│   │   ├── schemas.py      # Pydantic request/response schemas
│   │   ├── disc_identity.py # Fingerprint alias resolution / conflict detection
│   │   ├── sync.py         # global_seq counter, sync payload helpers
│   │   ├── database.py     # Engine/session/Base setup
│   │   ├── deps.py         # get_db dependency
│   │   ├── middleware.py   # RequestIdMiddleware, MirrorModeMiddleware
│   │   └── rate_limit.py   # slowapi limiter config, dynamic limits
│   ├── alembic/            # DB migrations (env.py, versions/)
│   ├── scripts/            # sync.py (mirror daemon), seed.py
│   └── tests/              # pytest suite (test_*.py per feature)
├── ovid-client/            # Python disc-identification library + CLI
│   ├── src/ovid/
│   │   ├── readers/        # DiscReader implementations (folder, bd_folder, iso, drive)
│   │   ├── ifo_parser.py   # DVD IFO format parsing
│   │   ├── mpls_parser.py  # Blu-ray MPLS/playlist parsing
│   │   ├── disc.py         # DVD Disc object + fingerprint
│   │   ├── bd_disc.py      # Blu-ray/UHD Disc object
│   │   ├── bd_fingerprint.py / fingerprint.py # Fingerprint computation
│   │   ├── disc_identity.py  # Client-side identity types
│   │   ├── disc_structure.py # Normalized Disc Structure projection
│   │   ├── dvdread_adapter.py # libdvdread-based DVD identity method
│   │   ├── submission.py   # Build API submit payloads
│   │   ├── tmdb.py         # TMDB metadata search/lookup
│   │   ├── client.py       # OVIDClient — thin requests wrapper
│   │   └── cli.py          # `ovid` CLI entry point (fingerprint/lookup/submit)
│   └── tests/               # pytest suite mirroring src/ovid modules
├── arm/                    # Automatic Ripping Machine integration
│   ├── identify_ovid.py    # Non-blocking OVID lookup wrapper for ARM
│   ├── identify.py / identify_original.py # ARM's own identify pipeline (reference/original)
│   └── start_arm_container.sh, entrypoint_wrapper.sh
├── web/                    # Next.js frontend
│   ├── app/                # App Router pages (page.tsx per route)
│   │   ├── disc/[fingerprint]/  # Disc detail page
│   │   ├── submit/         # Submission wizard page
│   │   ├── disputes/       # Dispute resolution page
│   │   ├── settings/       # Account settings page
│   │   └── auth/callback/  # OAuth callback handler
│   ├── components/         # Presentational/interactive React components
│   ├── lib/                # api.ts (API client), auth.ts (auth helpers)
│   └── src/__tests__/      # Vitest test suite
├── docs/adr/               # Architecture decision records
├── scripts/                 # Repo-level helper scripts
├── tests/                   # Repo-level test scaffolding (outside api/ and ovid-client/)
├── uat_dirs/                # Synthetic disc fixture directories for UAT (BDMV/VIDEO_TS/AACS trees)
├── docker-compose.yml        # dev stack: db, api, sync (mirror profile), web
├── docker-compose.prod.yml
├── docker-compose.test.yml
├── CONTEXT.md                # Domain glossary (Normalized Disc Structure, Disc Identity, etc.)
└── CHANGELOG.md
```

## Directory Purposes

**`api/app/routes/`:**
- Purpose: HTTP endpoint definitions grouped by resource.
- Contains: `disc.py` (register/submit/lookup/verify/dispute/search), `sync.py` (mirror feed).
- Key files: `api/app/routes/disc.py`, `api/app/routes/sync.py`

**`api/app/auth/`:**
- Purpose: Multi-provider OAuth + JWT session handling.
- Contains: `config.py` (secrets/settings), `deps.py` (`get_current_user`), `jwt.py`, one module per provider (`indieauth.py`, `mastodon.py`), `routes.py`, `users.py`.
- Key files: `api/app/auth/routes.py`, `api/app/auth/deps.py`

**`api/alembic/`:**
- Purpose: Database schema migrations.
- Contains: `env.py`, `versions/` (one file per migration).

**`ovid-client/src/ovid/readers/`:**
- Purpose: Source-medium abstraction (folder/ISO/block device) implementing a common `DiscReader` interface.
- Contains: `base.py` (ABC), `folder.py` (DVD VIDEO_TS), `bd_folder.py` (BD/UHD BDMV), `iso.py` (pycdlib), `drive.py` (block device delegator).
- Key files: `ovid-client/src/ovid/readers/__init__.py` (factory `open_reader`)

**`arm/`:**
- Purpose: Integration shim for the third-party Automatic Ripping Machine project; keeps OVID lookups non-blocking and isolated from ARM's own ripping pipeline.
- Contains: `identify_ovid.py` (the OVID-facing wrapper), `identify.py`/`identify_original.py` (ARM's pipeline, likely vendored/reference copies).

**`web/app/`:**
- Purpose: Next.js App Router pages — one directory per route, `page.tsx` per route.
- Contains: home/search (`page.tsx`), disc detail (`disc/[fingerprint]/page.tsx`), submit wizard, disputes, settings, OAuth callback.

**`uat_dirs/`:**
- Purpose: Synthetic fixture disc directory trees (BDMV/VIDEO_TS/AACS structures) used by `create_uat_dirs.py` and `run_uat.py` for end-to-end UAT scenarios (t1_bd2, t3_uhd, edge_mixed, etc.).
- Generated: Yes — produced by `create_uat_dirs.py`.

## Key File Locations

**Entry Points:**
- `api/main.py`: FastAPI app bootstrap
- `ovid-client/src/ovid/cli.py`: `ovid` CLI (fingerprint/lookup/submit commands)
- `arm/identify_ovid.py`: ARM lookup hook, importable and standalone (`python -m arm.identify_ovid`)
- `web/app/page.tsx`: Web app home/search page

**Configuration:**
- `.env.example`: Env var template (root)
- `docker-compose.yml` / `docker-compose.prod.yml` / `docker-compose.test.yml`: Service topology per environment
- `web/next.config.ts`, `web/tsconfig.json`, `web/eslint.config.mjs`, `web/vitest.config.ts`
- `api/alembic/env.py`: Migration environment config

**Core Logic:**
- `api/app/models.py`: ORM schema (source of truth for DB structure)
- `api/app/disc_identity.py`: Identity/alias resolution logic
- `ovid-client/src/ovid/disc_structure.py`: Normalized Disc Structure projection

**Testing:**
- `api/tests/`: pytest suite, one `test_<feature>.py` file per API concern (auth per-provider, disc lookup/submit/edits, sync, rate limiting, CORS)
- `ovid-client/tests/`: pytest suite mirroring `src/ovid/` modules
- `web/src/__tests__/`: Vitest suite (`auth.test.ts`, `pages.test.tsx`, `submit.test.tsx`)

## Naming Conventions

**Files:**
- Python: `snake_case.py`, one module per concern (e.g., `disc_identity.py`, `rate_limit.py`); test files prefixed `test_` and named after the feature under test (`test_disc_submit.py`, `test_auth_github.py`).
- TypeScript/React: `PascalCase.tsx` for components (`DiscCard.tsx`, `SubmitForm.tsx`), `camelCase.ts` for lib modules (`api.ts`, `auth.ts`); Next.js pages always `page.tsx` inside a route-named directory.

**Directories:**
- Backend concerns grouped by role, not by feature: `routes/`, `auth/`, `alembic/`, `scripts/`, `tests/`.
- Client library grouped by pipeline stage: `readers/` (I/O) separate from parsers, identity, and CLI at the package root.
- Next.js routes use folder-per-route with dynamic segments in brackets (`disc/[fingerprint]/`).

## Where to Add New Code

**New API endpoint:**
- Route handler: add to existing `api/app/routes/disc.py` or `sync.py`, or create a new `api/app/routes/<resource>.py` and register it in `api/main.py` via `app.include_router(...)`.
- Schema: add request/response models to `api/app/schemas.py`.
- Tests: `api/tests/test_<feature>.py`.

**New OAuth provider:**
- Implementation: `api/app/auth/<provider>.py` following the pattern of `indieauth.py`/`mastodon.py`; register route in `api/app/auth/routes.py`.
- Tests: `api/tests/test_auth_<provider>.py`.

**New disc source type (client):**
- Reader: `ovid-client/src/ovid/readers/<new>.py` implementing `DiscReader` (`base.py`), then wire into `open_reader()` in `ovid-client/src/ovid/readers/__init__.py`.
- Tests: `ovid-client/tests/`.

**New DB table/migration:**
- Model: add to `api/app/models.py`.
- Migration: generate under `api/alembic/versions/` via Alembic.

**Web UI feature:**
- Page: new directory under `web/app/<route>/page.tsx`.
- Shared component: `web/components/<Name>.tsx`.
- API call: extend `web/lib/api.ts`.
- Tests: `web/src/__tests__/`.

## Special Directories

**`api/tests/__pycache__`, `ovid-client/.venv`, `node_modules` (web):**
- Purpose: Build/dependency caches.
- Generated: Yes
- Committed: No

**`uat_dirs/`:**
- Purpose: Generated fixture disc trees for manual/UAT testing (`run_uat.py`, `create_uat_dirs.py`).
- Generated: Yes (via `create_uat_dirs.py`)
- Committed: Appears checked in (present at repo root, not under `.gitignore` per visible listing) — verify before treating as disposable.

**`docs/adr/`:**
- Purpose: Architecture Decision Records documenting past design choices.
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-07-05*
