---
phase: 07-web-ui-production-readiness
plan: 03
subsystem: api
tags: [fastapi, slowapi, sqlalchemy, rate-limiting, redaction, security]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness
    provides: "Plan 01/02 foundation for the web UI production-readiness phase; this plan closes the D-01 re-review carry-in findings (R-1/R-2) on the re-integrated multi-disc-set feature"
provides:
  - "Status-gated sibling redaction in the disc-detail nested set view (_build_disc_set_nested, disc.py) and the set-search view (_build_sibling_summary, set.py) — an unverified sibling's main_title/duration_secs/track_count are withheld, mirroring the D-09 anti-echo redaction _disc_to_response already applies on a direct lookup"
  - "POST /v1/set now carries the stacked AUTH_WRITE_LIMIT per-account write ceiling (20/minute;300/hour) above the existing volumetric _dynamic_limit, matching submit_disc/register_disc/resolve_dispute_endpoint (INFRA-04 parity)"
affects: [web-ui-production-readiness, disc-set-view, security-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-sibling status gate reusing the exact _disc_to_response D-09 unverified predicate, applied identically in both set.py::_build_sibling_summary and disc.py::_build_disc_set_nested"
    - "Stacked slowapi decorators (AUTH_WRITE_LIMIT above _dynamic_limit) as the standard write-throttle shape for authenticated write routes"

key-files:
  created:
    - api/tests/test_set_redaction_and_limit.py
  modified:
    - api/app/routes/set.py
    - api/app/routes/disc.py
    - api/tests/test_disc_lookup.py

key-decisions:
  - "Redacted fields are set to None (not omitted) for main_title/duration_secs/track_count, matching the SiblingDiscSummary schema's optional int|None/str|None typing — no schema change required"
  - "Fixed test_disc_lookup.py::test_lookup_disc_in_set, which had encoded the R-1 leak as expected behavior (asserting an unverified sibling's structural fields were visible); switched its sibling fixture to verified status to preserve the test's original intent (full sibling-summary rendering) without re-asserting the closed leak"

patterns-established:
  - "Anti-echo redaction gates must be reused verbatim (same status predicate) across every builder that projects sibling/disc structural data, not reinvented per call site"

requirements-completed: []  # Per plan note: WEBUI-02/WEBUI-03 are NOT marked complete here — 07-01/07-02 precedent reserves milestone requirement IDs for the plans that ship the user-facing surface, not backend re-review fix plans.

coverage:
  - id: D1
    description: "Unverified sibling's main_title/duration_secs/track_count are withheld in the nested disc-detail set view (GET /v1/disc/{fp}) while identity fields (fingerprint, disc_number, format) remain visible"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "api/tests/test_set_redaction_and_limit.py#test_nested_disc_set_redacts_unverified_sibling_structural_fields"
        status: pass
    human_judgment: false
  - id: D2
    description: "Verified sibling's structural summary is still shown in the nested disc-detail set view (redaction is per-status, not blanket)"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "api/tests/test_set_redaction_and_limit.py#test_nested_disc_set_shows_verified_sibling_structural_fields"
        status: pass
    human_judgment: false
  - id: D3
    description: "The same status gate applies to the set-search view (GET /v1/set) — each result's sibling summaries redact unverified siblings and show verified ones"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "api/tests/test_set_redaction_and_limit.py#test_set_search_view_redacts_unverified_sibling_structural_fields"
        status: pass
    human_judgment: false
  - id: D4
    description: "POST /v1/set enforces the stacked AUTH_WRITE_LIMIT per-account write ceiling (20/minute), returning 429 with the standard rate-limited envelope past the cap"
    requirement: "WEBUI-03"
    verification:
      - kind: unit
        ref: "api/tests/test_set_redaction_and_limit.py#test_create_set_enforces_auth_write_limit"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-07
status: complete
---

# Phase 07 Plan 03: R-1 Sibling Redaction + R-2 Write Ceiling Summary

**Status-gated redaction of unverified-sibling structural fields in the set/sibling views, plus a stacked per-account write ceiling on POST /v1/set — closing the two D-01 re-review findings on the re-integrated multi-disc-set feature.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-07T13:50:00-04:00 (approx.)
- **Completed:** 2026-07-07T13:57:00-04:00
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 4 (1 new test file, 2 route files, 1 pre-existing test file fixed)

## Accomplishments
- Closed R-1: `_build_disc_set_nested` (disc.py) and `_build_sibling_summary` (set.py) now withhold `main_title`/`duration_secs`/`track_count` for an `unverified` sibling, reusing the exact status predicate `_disc_to_response` already uses for the D-09 anti-echo redaction on a direct disc lookup. Verified siblings are unaffected — the gate is per-sibling status, never blanket.
- Closed R-2: `create_set` (set.py) now carries `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])` stacked above the existing `@limiter.limit(_dynamic_limit)`, matching the write-ceiling shape on `submit_disc`, `register_disc`, and `resolve_dispute_endpoint`.
- Added `api/tests/test_set_redaction_and_limit.py` with 4 tests covering both findings across both views (nested disc-detail + set-search) plus the write-ceiling 429 path.
- Fixed a pre-existing test (`test_disc_lookup.py::test_lookup_disc_in_set`) that had encoded the R-1 leak as expected behavior.
- Reviewed the two Phase-2 Alembic migrations (`900000000008`/`900000000009`) for ordering/idempotency per the D-01 checklist — no defect found, no migration changes needed (documented in PLAN.md's `<d01_migration_review>`).

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — failing pytest for sibling redaction (R-1) + set write ceiling (R-2)** - `ca01825` (test)
2. **Task 2: GREEN — status-gate sibling structural fields + stack AUTH_WRITE_LIMIT on create_set** - `f97c398` (fix)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `api/tests/test_set_redaction_and_limit.py` - New pytest module: 4 tests covering R-1 (both views, verified + unverified siblings) and R-2 (write-ceiling 429)
- `api/app/routes/set.py` - `_build_sibling_summary` status-gated; `create_set` decorated with stacked `AUTH_WRITE_LIMIT`
- `api/app/routes/disc.py` - `_build_disc_set_nested` status-gated (same predicate as `_disc_to_response`)
- `api/tests/test_disc_lookup.py` - `test_lookup_disc_in_set`'s sibling fixture switched from `unverified` to `verified` status so it no longer asserts the now-closed R-1 leak

## Decisions Made
- Redacted fields set to `None`, not omitted — `SiblingDiscSummary`'s `main_title`/`duration_secs`/`track_count` are already `Optional`, so no schema change was needed and the response shape stays stable for every consumer.
- Fixed the pre-existing `test_lookup_disc_in_set` test in place rather than deferring — it directly asserted the leak this plan closes, so leaving it unfixed would either fail post-fix or (worse) mask the fix. Its sibling fixture now uses `verified` status, preserving the test's original intent (full sibling-summary rendering) while a dedicated redacted-unverified-sibling case lives in the new test module.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing test asserting the R-1 leak as correct behavior**
- **Found during:** Task 2 (`cd api && .venv/bin/python -m pytest tests/ -k "set or disc"` regression check)
- **Issue:** `test_disc_lookup.py::test_lookup_disc_in_set` seeded an `unverified` sibling and asserted its `main_title`/`duration_secs`/`track_count` were visible in the nested set view — exactly the leak R-1 closes. After the fix, this assertion correctly failed.
- **Fix:** Changed the sibling fixture's `status` from `"unverified"` to `"verified"`, preserving the test's original purpose (asserting the full sibling-summary shape renders correctly) without re-encoding the closed leak.
- **Files modified:** `api/tests/test_disc_lookup.py`
- **Verification:** `cd api && .venv/bin/python -m pytest tests/ -k "set or disc"` → 132 passed; full suite `cd api && .venv/bin/python -m pytest tests/` → 450 passed, 0 warnings.
- **Committed in:** `f97c398` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — pre-existing test asserting closed leak as correct)
**Impact on plan:** Necessary correctness fix directly in scope of the finding this plan closes. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Both D-01 re-review carry-in findings (R-1, R-2) are closed; the set/sibling view and `POST /v1/set` are now consistent with the rest of the write/read security posture established in earlier phases.
- `WEBUI-02`/`WEBUI-03` requirement IDs remain unchecked per the 07-01/07-02 precedent (reserved for the plans that ship the user-facing surface).
- Full api test suite (450 tests) is green with zero warnings — no known regressions or deferred items block subsequent 07-xx plans.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED
- FOUND: api/tests/test_set_redaction_and_limit.py
- FOUND: commit ca01825 (test)
- FOUND: commit f97c398 (fix)
