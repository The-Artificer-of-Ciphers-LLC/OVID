---
phase: 02-two-contributor-verification-workflow
plan: 01
subsystem: api
tags: [verification, structural-match, proof-of-possession, anti-echo, tolerance-envelope, tdd]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene
    provides: "consolidated verification state machine (verify/flag_dispute), DiscTitle/DiscTrack ORM, DiscSubmitRequest schema, seed_test_disc(status=...) fixture"
provides:
  - "structural_match(existing_disc, body, db) -> bool — tolerant canonical structural-equality gate over WITHHELD stored structure (D-03)"
  - "_normalize_codec(codec) helper (AC-3/ac3/AC3 -> ac3)"
  - "DURATION_TOLERANCE_SECS named module constant (D-08 tunable)"
  - "boundary test suite pinning the verify/dispute frontier both directions"
affects: [02-03 (_handle_existing_disc verify gate), 02-04 (lookup redaction pairs with anti-echo), 02-anti-sybil]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Comparison-only domain module (no status writes, no db.commit) mirroring disc_identity.py shape"
    - "Order-independent track comparison via collections.Counter multiset keyed on (language, normalized codec, channels)"
    - "Tolerance envelope with named constants and fail-open on unknown durations (D-07)"

key-files:
  created:
    - api/app/structural_match.py
    - api/tests/test_structural_match.py
  modified: []

key-decisions:
  - "Verify gate reads NO release-level (public) field — proof-of-possession, not metadata echo (D-01/D-03)"
  - "Duration enforced only when both sides known; unknown duration fails open (D-07)"
  - "Tracks compared as sorted multisets, never positional track_index (benign rip reordering tolerated)"

patterns-established:
  - "Structural-equality envelope: exact title count + per-title chapter_count + is_main_feature + duration-within-tolerance + audio/subtitle multiset equality"
  - "Codec normalization: lowercase + strip non-alphanumeric before compare"

requirements-completed: [VERIFY-01]

coverage:
  - id: D1
    description: "Two independent rips of the same disc (reordered tracks, relabeled codec, +/-1-2s duration jitter) compare as structurally EQUAL and are eligible to verify."
    requirement: "VERIFY-01"
    verification:
      - kind: unit
        ref: "api/tests/test_structural_match.py#test_exact_match,test_reordered_audio_tracks_match,test_relabeled_codec_matches,test_duration_within_tolerance_matches"
        status: pass
    human_judgment: false
  - id: D2
    description: "A real structural difference (wrong title count, wrong per-title chapter count, missing/extra track, different language, out-of-tolerance duration) compares as NOT equal and is routed away from verify."
    requirement: "VERIFY-01"
    verification:
      - kind: unit
        ref: "api/tests/test_structural_match.py#test_extra_title_no_match,test_different_chapter_count_no_match,test_missing_audio_track_no_match,test_different_language_no_match,test_duration_outside_tolerance_no_match"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-07-05
status: complete
---

# Phase 2 Plan 01: Structural-Match Verify Gate Summary

**Tolerant canonical structural-equality gate (`structural_match`) that verifies a disc only when a second contributor reproduces its WITHHELD stored structure — title/chapter counts, main-feature marker, and codec-normalized track multisets within a ±2s duration window — reading no public release field.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-05T18:22:00-04:00
- **Completed:** 2026-07-05T18:35:20-04:00
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2 created

## Accomplishments
- `structural_match(existing_disc, body, db) -> bool` — the proof-of-possession verify gate that upgrades the trigger from public release fields (`_releases_match`) to withheld structure (D-01/D-03).
- Tolerance envelope pinned in both directions: benign independent-rip jitter (reordered audio multiset, `AC-3`↔`ac3` relabel, +1s duration) → match; real structural difference (extra title, wrong chapter_count, missing audio track, different language, +40s duration) → no-match.
- Comparison-only module: no `disc.status =` assignment, no `db.commit()`, no release-level field read — clean VERIFY-02 boundary; status writes stay in `verification.py`.
- Full API suite green (271 passed), module is additive with no regressions.

## Task Commits

Each task committed atomically (TDD):

1. **Task 1: RED — boundary tests for the D-03 tolerance envelope** - `c1c5918` (test)
2. **Task 2: GREEN — implement structural_match.py tolerance envelope** - `237435b` (feat)

_RED confirmed the expected `ModuleNotFoundError: No module named 'app.structural_match'` before implementation._

## Files Created/Modified
- `api/app/structural_match.py` - Tolerant structural-equality gate: `structural_match()`, `_normalize_codec()`, `_track_multiset()`, `_title_matches()`, `DURATION_TOLERANCE_SECS`.
- `api/tests/test_structural_match.py` - 9 boundary tests (4 match, 5 no-match), one axis varied per test against the Matrix seed; track comparison asserts multiset equality, never positional index.

## Decisions Made
- **Duration fail-open (D-07):** duration is compared only when both stored and submitted values are present; an unknown duration on either side never fails the match.
- **Multiset track comparison:** audio and subtitle tracks compared as `collections.Counter` over `(language_code, normalized_codec, channels)` so independent rips emitting tracks in a different order still match; positional `track_index` is deliberately ignored.
- **Codec normalization:** lowercase + strip non-alphanumeric collapses `AC-3`/`ac3`/`AC3` to a single canonical form before compare.
- Named constant `DURATION_TOLERANCE_SECS = 2` at module top (D-08 tunable) — no inline numeric tolerance literals.

## Deviations from Plan

None - plan executed exactly as written. (Removed one unused `TrackCreate` import from the implementation before committing to keep the module warning-clean; not a behavioral change.)

## Issues Encountered
- Local `python` is not on PATH; the API test venv lives at `api/.venv`. Ran the suite via `api/.venv/bin/python -m pytest`. No code impact.

## Out-of-Scope Discoveries (logged, not fixed)
Two pre-existing third-party deprecation warnings surface across the whole suite and are unrelated to this comparison-only plan (untouched files `tests/conftest.py`, `tests/test_auth.py`); their only remedy is a dependency/package change excluded from auto-fix scope. Logged to `deferred-items.md`:
- `StarletteDeprecationWarning` (httpx via `fastapi/testclient.py`) — remedy: `httpx2`.
- `slowapi` `asyncio.iscoroutinefunction` deprecation — remedy: `slowapi` upgrade (relates to Phase 3 INFRA rate-limit hardening).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `structural_match` is ready for Plan 03 to wire into `_handle_existing_disc` as the verify gate, replacing `_releases_match` as the verify trigger (per interface_context: `structural_match(existing, body, db)`).
- No blockers. The dispute-trigger disposition of `_releases_match` (Open Question A3) is a Plan 03 concern, not affected here.

## Self-Check: PASSED

---
*Phase: 02-two-contributor-verification-workflow*
*Completed: 2026-07-05*
