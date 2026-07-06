---
phase: 04-blu-ray-uhd-fingerprinting
plan: 06
subsystem: docs
tags: [fingerprint-spec, aacs, bdmv, mkdocs, contributing-guide]

# Dependency graph
requires:
  - phase: 04-blu-ray-uhd-fingerprinting
    provides: "bd2_spec.py frozen constants (04-01), identify_bd()/DiscIdentitySet alias-pair (04-03), select_canonical_playlists filter/dedup/sort pipeline and UHD 0300 detection (04-03), test_bd_real_disc.py cross-drive test (04-05)"
provides:
  - "docs/fingerprint-spec.md OVID-BD-2 Fingerprint Algorithm Specification section (Overview, Alias-Pair Behavior, Tier 1, Tier 2, Format Detection, Versioning)"
  - "docs/contributing.md Manual pre-release verification (Blu-ray/UHD) subsection"
affects: [release-process, future-fingerprint-spec-revisions]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Docs mirror shipped code exactly — spec text was written from bd2_spec.py/bd_fingerprint.py/disc_identity.py/bd_disc.py source, not the plan's prose"]

key-files:
  created: []
  modified:
    - docs/fingerprint-spec.md
    - docs/contributing.md

key-decisions:
  - "Documented the OVID-BD-2 section as-shipped: identify_bd()'s degenerate Tier-1-primary fallback (with tier2_unavailable_using_tier1_primary diagnostic) is described explicitly, not simplified away"
  - "UHD detection framed strictly as a community-corroborated convention (libbluray precedent), never as a licensed BDA guarantee, per FPRINT-04"
  - "Manual pre-release verification step placed in docs/contributing.md (no existing release-checklist doc in the repo) rather than inventing a new doc"

patterns-established:
  - "Fingerprint-spec.md algorithm sections follow a fixed shape: Version/Status/Last-updated header, Overview, Alias-Pair Behavior, Tier N sections, Format Detection (if applicable), Versioning — established by OVID-DVD-1, now confirmed by OVID-BD-2"

requirements-completed: [DOCS-01, FPRINT-01, FPRINT-04, FPRINT-05]

coverage:
  - id: D1
    description: "docs/fingerprint-spec.md documents OVID-BD-2 Tier 1 (AACS Disc ID) and Tier 2 (BDMV structure hash), mirroring OVID-DVD-1's structure including its own Versioning section"
    requirement: "DOCS-01"
    verification:
      - kind: other
        ref: "grep -c '## OVID-BD-2 Fingerprint Algorithm Specification' docs/fingerprint-spec.md == 1; grep -c 'planned, v0.2.0' docs/fingerprint-spec.md == 0"
        status: pass
    human_judgment: false
  - id: D2
    description: "AACS Disc ID legal-boundary wording (SHA-1 of a plaintext file, not a decryption key) stated explicitly, matching the D-10 code-level fix"
    requirement: "FPRINT-01"
    verification:
      - kind: other
        ref: "grep -c 'AACS Disc ID' docs/fingerprint-spec.md >= 1; prose states SHA-1(AACS/Unit_Key_RO.inf) equivalence"
        status: pass
    human_judgment: false
  - id: D3
    description: "UHD header-version detection heuristic documented as community-corroborated convention, not a licensed BDA guarantee"
    requirement: "FPRINT-04"
    verification: []
    human_judgment: true
    rationale: "Judgment on whether the wording sufficiently disclaims BDA-specification authority is a documentation-quality/legal-nuance call, not something a grep/test can certify."
  - id: D4
    description: "Manual pre-release cross-drive verification step documented in docs/contributing.md so FPRINT-05's >=2-drives requirement can't be silently skipped"
    requirement: "FPRINT-05"
    verification:
      - kind: other
        ref: "grep -c 'Manual pre-release verification' docs/contributing.md == 1; grep -c 'OVID_TEST_DISC_PATH_2' docs/contributing.md >= 1"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-06
status: complete
---

# Phase 4 Plan 6: BD/UHD Fingerprint Spec & Manual Verification Docs Summary

**Added the OVID-BD-2 Tier 1/Tier 2 fingerprint spec section (mirroring OVID-DVD-1's structure) and a manual cross-drive pre-release verification subsection in contributing.md, both written from the as-shipped Wave 1-3 code.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-06T18:15:00Z (approx.)
- **Completed:** 2026-07-06T18:23:38Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `docs/fingerprint-spec.md` now has a complete "OVID-BD-2 Fingerprint Algorithm Specification" section (Overview, Alias-Pair Behavior, Tier 1 — AACS Disc ID, Tier 2 — BDMV Structure Hash Algorithm, Format Detection (UHD), Versioning), inserted before `## License` so the CC0 statement continues to cover it.
- The Fingerprint Format Summary table's four BD/UHD rows no longer say "planned, v0.2.0" — they now point at the new section.
- `docs/contributing.md` documents a "Manual pre-release verification (Blu-ray/UHD)" subsection referencing `OVID_TEST_DISC_PATH`/`OVID_TEST_DISC_PATH_2` and `test_bd_real_disc.py`, placed right after "Test requirements" and before "Repository structure."
- `mkdocs build --strict` verified to exit 0 with both changes in place (mkdocs/mkdocs-material installed into a scratch venv for verification since the tool wasn't present in the base environment).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the OVID-BD-2 section to docs/fingerprint-spec.md** - `fdec105` (docs)
2. **Task 2: Document the manual pre-release cross-drive verification step in docs/contributing.md** - `6a63600` (docs)

**Plan metadata:** recorded in this commit (docs: complete plan)

## Files Created/Modified
- `docs/fingerprint-spec.md` - New OVID-BD-2 Fingerprint Algorithm Specification section (Overview, Alias-Pair Behavior, Tier 1 AACS Disc ID, Tier 2 BDMV structure hash algorithm with frozen bd2_spec.py constants, Format Detection UHD heuristic framing, Versioning); Fingerprint Format Summary table's BD/UHD rows updated from "planned" to reference the new section.
- `docs/contributing.md` - New "Manual pre-release verification (Blu-ray/UHD)" subsection documenting the hardware-gated cross-drive test invocation.

## Decisions Made
- Documented `identify_bd()`'s behavior exactly as shipped (read from `disc_identity.py`/`bd_fingerprint.py`/`bd_disc.py`), including the degenerate Tier-1-primary fallback path and its `tier2_unavailable_using_tier1_primary` diagnostic, rather than the simplified always-Tier-2-primary framing implied by the plan's prose alone.
- Cited the frozen constants (`MIN_DURATION_SECONDS = 60.0`, `MAX_CLIP_REPEATS = 2`, `OVID_BD2_VERSION = "OVID-BD-2"`) by their exact names/values from `bd2_spec.py` rather than paraphrasing.
- Kept the UHD detection framing strictly as a community-corroborated convention (matching libbluray's reverse-engineered support), explicitly disclaiming any licensed BDA specification citation, per the plan's constraint and FPRINT-04.
- No existing release-checklist doc exists in this repo, so the manual verification step was added to `docs/contributing.md` next to the existing automated test-running instructions — the lowest-risk, most discoverable home, as called out in the plan's rationale.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their acceptance criteria on first pass; no auto-fixes were required.

## Issues Encountered
- `mkdocs` was not installed in the base environment (`mkdocs: command not found`). Installed `mkdocs`+`mkdocs-material` into a throwaway venv under the session scratchpad directory to run the `mkdocs build --strict` acceptance check; this tooling install is not part of the repo and was not committed. Build passed (exit 0) both after Task 1 and after Task 2, with only pre-existing INFO-level "not in nav" notices for unrelated docs (no warnings/errors).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 4 (Blu-ray/UHD Fingerprinting) documentation is now complete: DOCS-01, FPRINT-01, FPRINT-04, and FPRINT-05's documentation coverage requirements are satisfied.
- No blockers. This was the final (docs) plan of the phase — ready for phase-level requirements/roadmap closeout.

---
*Phase: 04-blu-ray-uhd-fingerprinting*
*Completed: 2026-07-06*

## Self-Check: PASSED

- FOUND: docs/fingerprint-spec.md
- FOUND: docs/contributing.md
- FOUND: fdec105 (Task 1 commit)
- FOUND: 6a63600 (Task 2 commit)
