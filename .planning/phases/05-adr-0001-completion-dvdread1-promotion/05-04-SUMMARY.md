---
phase: 05-adr-0001-completion-dvdread1-promotion
plan: 04
subsystem: arm-integration
tags: [arm, ovid-client, fingerprint-aliases, ci, tdd]

# Dependency graph
requires:
  - phase: 05-adr-0001-completion-dvdread1-promotion
    provides: "05-03: identify_dvd() dvdread1-*-primary/dvd1-*-alias flip (aliases now exist to thread through)"
provides:
  - "fingerprint_disc_with_identity() in arm/identify_ovid.py — extracts primary + alias fingerprints from a parsed Disc/BDDisc"
  - "submit_to_ovid() fingerprint_aliases param — conditional payload key mirroring build_submit_payload()'s convention"
  - "arm/identify.py alias threading through _try_ovid()/identify() into the auto-register call"
  - "arm/tests/ test package (new, 12 tests) — arm's first-ever test infrastructure"
  - "arm-tests CI job"
affects: [phase-08-arm-interface-versioning]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fingerprint_disc() as a thin backward-compatible wrapper over a richer fingerprint_disc_with_identity() — same shape as build_submit_payload's alias-only-if-present convention"
    - "manual save/override/restore-in-finally monkeypatching of classmethods (Disc.from_path/BDDisc.from_path) and module-level functions (arm.identify.lookup_ovid etc.) instead of pytest monkeypatch fixture, per plan's explicit TDD instructions"

key-files:
  created:
    - arm/tests/__init__.py
    - arm/tests/test_identify_ovid.py
    - arm/tests/test_identify.py
  modified:
    - arm/identify_ovid.py
    - arm/identify.py
    - .github/workflows/ci.yml

key-decisions:
  - "fingerprint_disc_with_identity() reuses fingerprint_disc's existing BD/DVD branching and reads disc._identity_set directly rather than introducing a new identity-resolution path"
  - "arm/identify.py's _load_original() now degrades gracefully (try/except around exec_module) instead of crashing the module's own import when ARM-only deps (pydvdid, arm.config, arm.ripper.utils, arm.ui) are absent — required to make arm.identify importable/testable outside the ARM container"
  - "arm-tests CI job installs ovid-client editable (not just requests+pytest as the plan literally specified) because Task 1's tests monkeypatch real ovid.disc.Disc.from_path/ovid.bd_disc.BDDisc.from_path and construct real DiscIdentitySet instances — the plan's own Task 1 design requires ovid-client to be importable in CI"

patterns-established:
  - "New arm/tests/ suite pattern: manual _patch()/_restore() helpers for module-attribute monkeypatching, mirrored across both new test files"

requirements-completed: [IDENT-03]

coverage:
  - id: D1
    description: "fingerprint_disc_with_identity() extracts both primary fingerprint and alias list from a parsed Disc/BDDisc's _identity_set"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "arm/tests/test_identify_ovid.py::TestFingerprintDiscWithIdentity"
        status: pass
    human_judgment: false
  - id: D2
    description: "submit_to_ovid() conditionally includes fingerprint_aliases in the POST payload only when non-empty, mirroring build_submit_payload()'s convention; unchanged default-call behavior preserved"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "arm/tests/test_identify_ovid.py::TestSubmitToOvidFingerprintAliases"
        status: pass
    human_judgment: false
  - id: D3
    description: "arm/identify.py threads fingerprint_disc_with_identity()'s aliases through _try_ovid()/identify() into the submit_to_ovid auto-register call, preserving the never-raise contract on failure"
    requirement: "IDENT-03"
    verification:
      - kind: unit
        ref: "arm/tests/test_identify.py::TestIdentifyThreadsFingerprintAliases"
        status: pass
    human_judgment: false
  - id: D4
    description: "arm-tests CI job runs the new arm/tests suite as a permanent regression guard"
    verification:
      - kind: other
        ref: "PYTHONPATH=. python -m pytest arm/tests -v --tb=short (12 passed); YAML validated with pyyaml"
        status: pass
    human_judgment: false

duration: 20min
completed: 2026-07-06
status: complete
---

# Phase 5 Plan 4: ARM auto-register fingerprint_aliases threading Summary

**ARM's auto-register-on-miss path now submits every known Disc Identity string (fingerprint_aliases), not just the bare primary — closing the genuine IDENT-03 gap in `arm/identify_ovid.py::submit_to_ovid()`**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-06T21:49:00Z
- **Tasks:** 3 (all `auto`, first two `tdd="true"`)
- **Files modified:** 6 (3 created: `arm/tests/__init__.py`, `arm/tests/test_identify_ovid.py`, `arm/tests/test_identify.py`; 3 modified: `arm/identify_ovid.py`, `arm/identify.py`, `.github/workflows/ci.yml`)

## Accomplishments

- Added `fingerprint_disc_with_identity(disc_path)` to `arm/identify_ovid.py`, extracting both the primary fingerprint and alias fingerprint list from an already-parsed `Disc`/`BDDisc`'s `_identity_set`, reusing the existing BD/DVD branching logic; `fingerprint_disc()` is now a one-line backward-compatible wrapper over it.
- Extended `submit_to_ovid()` with a `fingerprint_aliases: list[str] | None = None` keyword parameter that's conditionally added to the POST payload only when non-empty — exactly mirroring `ovid.submission.build_submit_payload()`'s "alias key only when present" convention.
- Threaded the aliases through `arm/identify.py`: `_try_ovid()` now returns `(hit, fingerprint, aliases)` instead of `(hit, fingerprint)`, and `identify()` passes `fingerprint_aliases=ovid_fingerprint_aliases` into the auto-register `submit_to_ovid()` call on the miss-fallback path.
- Created `arm/tests/` — arm's first-ever test package (12 tests, all green) covering both the identity extraction and the alias threading, plus explicit regression tests proving ARM's never-raise contract holds even when `fingerprint_disc_with_identity()` raises, and that `OVID_ENABLED=false` still fully disables the OVID path.
- Added an `arm-tests` CI job (parallel to the existing 5 jobs, no `needs:`) so this closes as a permanent regression guard rather than a one-off patch.

## Task Commits

Each task was committed atomically (TDD tasks split into test/feat commits, plus one prerequisite fix commit):

1. **Task 1 — identify_ovid.py — fingerprint_disc_with_identity() + submit_to_ovid() aliases param**
   - `742fff1` (test) — RED: 7 of 9 tests fail (`AttributeError`/`TypeError`) against the pre-change file
   - `f7f2bb9` (feat) — GREEN: all 9 tests pass
2. **Task 2 — identify.py wiring — thread aliases through _try_ovid()/identify()**
   - `dec5049` (fix) — prerequisite: `_load_original()` degrades gracefully instead of crashing `arm.identify`'s own import (see Deviations)
   - `08391df` (test) — RED: all 3 new tests fail (`AttributeError: no attribute 'fingerprint_disc_with_identity'`)
   - `e37103d` (feat) — GREEN: all 3 tests pass
3. **Task 3 — CI job for arm/tests**
   - `4cb0016` (chore) — `arm-tests` job added to `.github/workflows/ci.yml`

**Plan metadata:** (this commit, made after this SUMMARY)

## Files Created/Modified

- `arm/identify_ovid.py` — new `fingerprint_disc_with_identity()`; `fingerprint_disc()` rewritten as a thin wrapper; `submit_to_ovid()` gains `fingerprint_aliases` param + conditional payload key
- `arm/identify.py` — import shim resolves `fingerprint_disc_with_identity` alongside existing symbols; `_try_ovid()` returns a 3-tuple; `identify()` initializes and threads `ovid_fingerprint_aliases` into the registration call; `_load_original()` hardened against ARM-only-dependency import failures
- `arm/tests/__init__.py` — new empty package init
- `arm/tests/test_identify_ovid.py` — 9 tests covering identity extraction (DVD + BD paths, present/absent/empty aliases) and payload conditional-key behavior
- `arm/tests/test_identify.py` — 3 tests covering miss-path alias threading, never-raise-on-exception, and `OVID_ENABLED=false` short-circuit
- `.github/workflows/ci.yml` — new `arm-tests` job (checkout, Python 3.12, install pytest + editable `ovid-client`, run `arm/tests`)

## Decisions Made

- `fingerprint_disc_with_identity()` reads `disc._identity_set` directly via `getattr` rather than adding a new public accessor to `Disc`/`BDDisc` — both classes already expose the field identically (confirmed by reading `disc.py`/`bd_disc.py`).
- `_try_ovid()`'s miss branch now calls `fingerprint_disc_with_identity()` instead of re-fingerprinting via the primary-only `fingerprint_disc()` — this is the one call site where aliases actually need to reach the registration path (the hit and low-confidence branches return `[]` since they don't feed the registration branch, or the fingerprint belongs to a different, already-registered disc).
- CI job installs `ovid-client` editable rather than the plan-literal "requests + pytest only" — see Deviations below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `arm/identify.py` was unimportable outside the ARM container**
- **Found during:** Task 2, before writing `arm/tests/test_identify.py`
- **Issue:** `_load_original()` called `spec.loader.exec_module(mod)` unguarded on `identify_original.py`, which imports ARM-only runtime dependencies (`pydvdid`, `arm.config`, `arm.ripper.utils`, `arm.ui`) not present in this repo/venv. Because the bottom of `arm/identify.py` unconditionally calls `_orig = _load_original()` at module-import time, merely doing `from arm import identify` raised `ModuleNotFoundError: No module named 'pydvdid'` — blocking any test of `identify()`/`_try_ovid()`, which Task 2 explicitly requires.
- **Fix:** Wrapped `exec_module` in try/except; on failure, log a warning and return `None` — degrading exactly like the pre-existing "original not found" path. `identify()`'s existing `if original and hasattr(original, "identify")` guard already handles a `None` original safely (falls back to the unmodified job), so this is a pure availability fix with zero behavior change on a real ARM container where the dependencies exist.
- **Files modified:** `arm/identify.py`
- **Verification:** `python -c "from arm import identify"` now succeeds cleanly (logs a warning, doesn't crash); all `arm/tests/test_identify.py` tests pass.
- **Committed in:** `dec5049`

**2. [Rule 1/3 - Bug/Blocking] Task 3's CI job spec omitted a genuinely required dependency**
- **Found during:** Task 3, before finalizing the CI job
- **Issue:** The plan's Task 3 action explicitly said to install only `requests` and `pytest` ("do not install... ovid-client package, since both new test files use monkeypatched stand-ins rather than importing real ovid-client/api code"). This directly contradicts Task 1's own action, which required monkeypatching *real* `ovid.disc.Disc.from_path`/`ovid.bd_disc.BDDisc.from_path` and constructing *real* `DiscIdentitySet`/`DiscIdentity` instances (verbatim: "a real `DiscIdentitySet` or `None`"). As literally specified, the CI job would fail on a clean runner with `ModuleNotFoundError: No module named 'ovid'`, making the "permanent regression guard" it exists to be immediately broken.
- **Fix:** Added `pip install -e ovid-client` to the install step (pulls in `requests` transitively via ovid-client's own `dependencies`), keeping `pip install pytest` for the dev-only test runner.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** Confirmed via `grep` that `test_identify_ovid.py` imports `ovid.disc.Disc`, `ovid.bd_disc.BDDisc`, `ovid.disc_identity.{DiscIdentity,DiscIdentitySet}`; validated resulting YAML with `pyyaml` (job list includes `arm-tests`, no `needs:`, structurally parallel to the other 5 jobs); ran the exact CI invocation (`PYTHONPATH=. python -m pytest arm/tests -v --tb=short`) locally under a venv with only `ovid-client` + `pytest` installed (via `ovid-client/.venv`) — 12 passed.
- **Committed in:** `4cb0016`

---

**Total deviations:** 2 auto-fixed (1 blocking-import fix, 1 blocking CI-dependency fix)
**Impact on plan:** Both fixes were necessary for the plan's own stated Task 2/Task 3 work to be testable/functional at all — no scope creep beyond what each task already required.

## Issues Encountered

None beyond the two deviations above (which were the actual blocking issues encountered).

## User Setup Required

None — no external service configuration required. The new CI job requires no new secrets (it doesn't call the live OVID API; all HTTP/network is monkeypatched in tests).

## Next Phase Readiness

- ARM's auto-register path is now feature-complete for IDENT-03: every submission path (interactive CLI wizard via `build_submit_payload`, and ARM's automated auto-register-on-miss via `submit_to_ovid`) carries the full known Disc Identity set.
- `arm/tests/` now exists as a real, CI-enforced test package — future ARM-integration changes have a regression harness to extend.
- No blockers for the remaining Phase 5 plans (05-05 through 05-07 per ROADMAP.md wave sequencing).

---
*Phase: 05-adr-0001-completion-dvdread1-promotion*
*Completed: 2026-07-06*
