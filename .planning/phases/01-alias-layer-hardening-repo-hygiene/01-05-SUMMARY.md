---
phase: 01-alias-layer-hardening-repo-hygiene
plan: 05
subsystem: testing
tags: [pytest, disc-identity, regression-guardrail, dvd1, fastapi, sqlalchemy]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene (plan 01/02)
    provides: "app/verification.py and the race-safe attach_lookup_aliases/resolve_disc_identity this test locks in"
provides:
  - "A permanent, unmarked pytest (test_disc_identity_regression.py) that seeds a golden dvd1-*-prefixed pressing and asserts GET /v1/disc still resolves it with frozen title/chapter/track/release structure"
affects: [phase-5-libdvdread-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Golden-record regression test: seed a real ORM row (mirroring seed_test_disc's insertion order) and assert the API's normalized response against an independent hardcoded expected dict, never a JSON snapshot file"
    - "Identity-vs-structure assertion split: assert persisted disc/release identity via a direct DB query, and assert response structure via a hardcoded dict that deliberately excludes the top-level `fingerprint` field so the guardrail survives future alias-promotion changes"

key-files:
  created:
    - api/tests/test_disc_identity_regression.py
  modified: []

key-decisions:
  - "Used a dedicated local seeder (seed_dvd1_golden_disc) instead of reusing seed_test_disc, because the shared fixture seeds fingerprint=\"dvd-ABC123-main\" (not dvd1-*-prefixed) per RESEARCH Pattern 3"
  - "Expected structure dict omits the top-level `fingerprint` key entirely (D-16) so the guardrail keeps passing after Phase 5 promotes dvd1-* to a Lookup Alias of a dvdread1-* primary"
  - "Persisted disc/release identity is asserted via a direct DB query (Disc.id == seed_ids[\"disc_id\"]), independent of the HTTP response body, per D-14/D-16 independence requirements"

patterns-established:
  - "Guardrail regression tests carry a `# guardrail: <REQ-ID>` docstring marker for discoverability, stay unmarked (no pytest marker), and assert against dicts hardcoded in the test body rather than external snapshot files"

requirements-completed: [IDENT-05]

coverage:
  - id: D1
    description: "Permanent, unmarked regression test seeds a golden dvd1-*-prefixed pressing and proves GET /v1/disc resolves it with frozen title/chapter/track/release structure, without breaking under future dvd1-*-to-alias promotion (IDENT-05)"
    requirement: "IDENT-05"
    verification:
      - kind: unit
        ref: "api/tests/test_disc_identity_regression.py::TestDvd1GoldenRegression::test_dvd1_golden_pressing_resolves_with_frozen_structure"
        status: pass
      - kind: unit
        ref: "cd api && python -m pytest tests/ --co -q (test_disc_identity_regression.py collected under the same invocation CI uses)"
        status: pass
      - kind: unit
        ref: "cd api && python -m pytest tests/ -q (252 passed, guardrail included, no skips)"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-05
status: complete
---

# Phase 01 Plan 05: dvd1-* Identity Regression Guardrail Summary

**Permanent unmarked pytest seeding a golden `dvd1-*` pressing and asserting frozen title/chapter/track/release structure via GET /v1/disc, independent of the seeder's own variables and immune to future alias-promotion changes**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-05T18:59:16Z
- **Tasks:** 2 (Task 2 required no code changes — verification only)
- **Files modified:** 1 created

## Accomplishments
- Added `api/tests/test_disc_identity_regression.py` with a dedicated golden `dvd1-golden-9f3c7a1b` seeder mirroring `conftest.seed_test_disc`'s insertion order (release → Disc → flush → DiscRelease link → DiscTitle → DiscTrack)
- Test asserts (a) 200 resolution via `GET /v1/disc/{dvd1_fp}`, (b) persisted disc/release identity matches the seeded row (checked via direct DB query, independent of the response body), and (c) the full normalized structure (format, status, region, upc, edition, disc/total counts, release fields, title fields, audio+subtitle track descriptors) equals a hardcoded expected dict written in the test body (D-14)
- Deliberately omits any assertion of `response["fingerprint"] == "dvd1-..."` (D-16) — the guardrail asserts stable identity/structure, not the literal top-level fingerprint value, so it survives the Phase 5 libdvdread promotion where `dvd1-*` may become a Lookup Alias to a `dvdread1-*` primary
- Confirmed (Task 2) the test is unmarked, carries no hardware/`real_disc` marker, is collected by the exact `pytest tests/` invocation `.github/workflows/ci.yml`'s `api-tests` job runs, reports no skip, and the full suite remains green (252 passed) with the guardrail included

## Task Commits

1. **Task 1: Write the golden dvd1-* seeder and the frozen-structure regression test** - `98d8020` (test)
2. **Task 2: Prove the guardrail properties — unmarked, collected every run, no hardware dependency** - no commit (verification-only; all properties already held after Task 1, no file changes required)

**Plan metadata:** committed separately as `docs(01-05): complete dvd1-* identity regression guardrail plan`

## Files Created/Modified
- `api/tests/test_disc_identity_regression.py` - Golden `dvd1-*` seeder (`seed_dvd1_golden_disc`) plus `TestDvd1GoldenRegression`, the permanent unmarked IDENT-05 guardrail test

## Decisions Made
- Built a dedicated local seeder rather than reusing `seed_test_disc` because the shared fixture's fingerprint (`dvd-ABC123-main`) is not `dvd1-`-prefixed (RESEARCH Pattern 3)
- Excluded the top-level `fingerprint` field from the hardcoded expected-structure dict entirely, and separately asserted persisted identity via a direct `db_session` query against `Disc`/`DiscRelease`, so the test proves both "the right disc was found" and "the structure is unchanged" without coupling either assertion to the exact response shape of the `fingerprint` field (D-16)
- Confirmed via a comparison run of `test_disc_identity_aliases.py` that the `StarletteDeprecationWarning`/`slowapi` `DeprecationWarning` seen during this test's run are pre-existing across the entire suite (unrelated to this task's `client`/`slowapi` fixture usage) — out of scope per the deviation-rules scope boundary, not introduced by this change

## Deviations from Plan

None - plan executed exactly as written. Task 2 required no fixes: the test was already unmarked, hardware-independent, and collected by the standard invocation after Task 1.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- IDENT-05's permanent CI tripwire for `dvd1-*` resolution is in place and green; it is designed to remain valid through the Phase 5 libdvdread migration (ADR 0001) without modification.
- No blockers for the remaining Phase 1 plans (01-03, 01-04, 01-06).

---
*Phase: 01-alias-layer-hardening-repo-hygiene*
*Completed: 2026-07-05*
