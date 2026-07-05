---
phase: 02-two-contributor-verification-workflow
plan: 04
subsystem: api
status: complete
tags: [security, redaction, anti-echo, verification, serialization]
requires: ["02-03"]
provides: ["unverified-read-redaction"]
affects: ["api/app/routes/disc.py", "api/app/schemas.py", "arm/identify_ovid.py (verified no-op)"]
tech-stack:
  added: []
  patterns: ["single status-branch redaction in shared serializer", "Pydantic v2 optional structural fields"]
key-files:
  created:
    - api/tests/test_lookup_redaction.py
  modified:
    - api/app/routes/disc.py
    - api/app/schemas.py
    - api/tests/test_disc_submit.py
decisions:
  - "Redaction is a single status branch in _disc_to_response (titles_resp), scoped to status==unverified only (D-09/D-12)."
  - "release + fingerprint_aliases stay populated for every status (D-11)."
  - "No new auth dependency; sync serializers untouched; no schema field made required (D-12)."
  - "D-10 confirmed: ARM's _extract_result reads only release-level fields + confidence + format — redaction is a no-op for ARM."
metrics:
  duration: 6m
  completed: 2026-07-05
  tasks: 2
  files: 4
requirements: [VERIFY-01]
---

# Phase 2 Plan 04: Withhold Unverified Structural Payload Summary

Anti-echo redaction: `GET /v1/disc/{fingerprint}` on an `unverified` disc now returns a redacted-200 — fingerprint, status, confidence, release, and fingerprint_aliases stay visible, but the submitted structural payload (titles → chapters, main-feature marker, audio/subtitle tracks) is withheld until a second contributor independently reproduces it from a physical disc.

## What Was Built

**Task 1 (RED, commit `18e6be4`)** — `api/tests/test_lookup_redaction.py` (127 lines). Two classes:
- `TestUnverifiedRedaction`: unverified GET → `titles == []`, but `release`, `fingerprint_aliases` (primary + attached alias), `confidence`, and `request_id`/`x-request-id` all present; a dedicated test asserts the exact D-10 field set ARM reads (`release.{title,year,imdb_id,tmdb_id}`, `confidence`, `format`) survives redaction.
- `TestRedactionScopedToUnverified`: verified and disputed reads keep full structure (chapter_count, main-feature marker, audio+subtitle tracks) — proves redaction is scoped to `unverified` only (Pitfall 6).

At RED exactly one assertion failed (`test_unverified_titles_withheld` — titles still populated by the unconditional serializer); the other five passed because they exercise fields redaction never touches.

**Task 2 (GREEN, commit `828cdee`)**:
- `api/app/routes/disc.py::_disc_to_response` — the `titles_resp` build is now `[] if disc.status == "unverified" else [_build_title_response(t) for t in disc.titles]`. `release_resp` and `fingerprint_aliases_resp` are unchanged (always populated). No auth dependency added; `sync.py` `Sync*Record` builders untouched.
- `api/app/schemas.py::DiscLookupResponse` — added a docstring documenting the redaction contract and noting `titles` is already `Field(default_factory=list)` and every `TitleResponse` field optional, so an empty list is a valid, non-breaking response (no field became required).

## D-10 Verification (ARM no-op)

Confirmed against `arm/identify_ovid.py::_extract_result` (read directly): it pulls only `data.get("release").{title,year,imdb_id,tmdb_id}`, `data.get("confidence")`, and `data.get("format")` — it never reads `titles`/tracks. Withholding structure for unverified discs is therefore a no-op for ARM's current behavior. This is also asserted at the integration level by `test_unverified_arm_fields_intact_d10`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Contract] Updated 3 pre-existing `test_disc_submit.py` tests to the new unverified-read contract**
- **Found during:** Task 2 (full-suite run).
- **Issue:** `test_submit_with_titles_and_tracks`, `test_same_user_register_then_submit_identifies`, and `test_different_user_submits_first_metadata_identifies` each submit a disc (which lands as `unverified`) then GET it and asserted `len(titles) == 1`. Under D-09 an unverified GET now withholds structure, so those assertions encode the pre-redaction contract this plan intentionally replaces. The planner's GREEN verify listed `test_disc_lookup.py` but did not anticipate these submit-then-GET tests reading an unverified disc.
- **Fix:** Updated the three tests to the new contract — the two identification tests now assert `titles == []` while keeping the `release.title` assertion (which still proves identification worked). `test_submit_with_titles_and_tracks` now asserts the unverified GET withholds structure AND proves the submitted titles/tracks persisted by querying the ORM directly (`disc.titles[0].tracks`), preserving submit-persistence coverage without depending on the redacted read.
- **Files modified:** `api/tests/test_disc_submit.py`
- **Commit:** `828cdee`

## Deferred / Known Issues

**Pre-existing third-party deprecation warnings (out of scope — not introduced by this plan).** The suite emits 13 warnings from third-party package source, unchanged by this work:
- `fastapi/testclient.py:1` — `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead`.
- `slowapi/extension.py:720` — `DeprecationWarning: 'asyncio.iscoroutinefunction' is deprecated ... use inspect.iscoroutinefunction()`.

Root cause: both are emitted inside installed dependencies (Starlette's TestClient importing httpx; slowapi calling the deprecated `asyncio.iscoroutinefunction`), triggered on framework import/use — not by any OVID code. They fired identically in this plan's RED run before any source change and appear across the entire existing suite. Remediation is a dependency migration (adopt `httpx2`, bump `slowapi`), which is a repo-wide infrastructure decision outside a redaction-scoped plan and should not be folded into this atomic commit; it belongs to the Phase 3 (INFRA) dependency work.

## Verification

- `cd api && .venv/bin/python -m pytest tests/test_lookup_redaction.py -x -q` → 6 passed.
- `cd api && .venv/bin/python -m pytest tests/test_lookup_redaction.py tests/test_disc_lookup.py -q` → 16 passed.
- `cd api && .venv/bin/python -m pytest -q` → **297 passed** (full API suite green; verified/disputed lookup and sync suites unaffected).

Note: the local interpreter is `api/.venv/bin/python` (Python 3.14) — bare `python`/`python3` on PATH lack pytest.

## Success Criteria Met

- [x] Unverified structural payload withheld from public reads (phase criterion 4).
- [x] Redaction uniform (no auth path), scoped to `unverified` only, aliases + release + sync feed intact.
- [x] ARM behavior unchanged (D-10 no-op, confirmed by read + integration assertion).
- [x] `_disc_to_response` branches on status; `DiscLookupResponse` structural fields optional/omittable per Pydantic v2.
- [x] `test_lookup_redaction.py` covers both redacted (unverified) and full (verified/disputed) paths; full suite green.

## Self-Check: PASSED

- Files: all 4 present (`test_lookup_redaction.py` created; `disc.py`, `schemas.py`, `test_disc_submit.py` modified).
- Commits: `18e6be4` (test/RED) and `828cdee` (feat/GREEN) both present in git log.
- Redaction branch present at `api/app/routes/disc.py` (`if disc.status == "unverified"`).

## TDD Gate Compliance

- RED gate: `test(02-04)` commit `18e6be4` — failing redaction test before implementation.
- GREEN gate: `feat(02-04)` commit `828cdee` — implementation makes it pass.
- REFACTOR: none needed (single-branch change, already minimal).
