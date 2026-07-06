---
phase: 04-blu-ray-uhd-fingerprinting
plan: 04
subsystem: ci
tags: [ci, github-actions, cross-platform, matrix]

requires: []
provides:
  - "ovid-client-tests CI job matrix (ubuntu-latest, macos-latest) — actual cross-platform execution of Blu-ray/UHD determinism tests, not just paper claims"
affects: ["phase-05: any future ovid-client CI job additions should follow this matrix pattern"]

tech-stack:
  added: []
  patterns:
    - "GitHub Actions strategy.matrix.os + runs-on: ${{ matrix.os }} + fail-fast: false, mirroring release.yml's cli-binaries job's proven macos-latest usage"

key-files:
  created: []
  modified:
    - .github/workflows/ci.yml

key-decisions:
  - "Only touched the ovid-client-tests job — api-tests, e2e-tests, web-tests, and docs-build are untouched per plan scope; e2e-tests' needs: [ovid-client-tests, api-tests] already waits for all matrix legs of a dependency job with no change required."

requirements-completed: [FPRINT-05]

coverage:
  - id: D1
    description: "ovid-client-tests job runs on both ubuntu-latest and macos-latest via strategy.matrix.os"
    requirement: FPRINT-05
    verification:
      - kind: automated
        ref: "python3 -c \"import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'macos-latest' in d['jobs']['ovid-client-tests']['strategy']['matrix']['os']\""
        status: pass
    human_judgment: false
  - id: D2
    description: "runs-on resolves to the matrix variable, and every other job's runs-on is unchanged"
    requirement: FPRINT-05
    verification:
      - kind: automated
        ref: "grep -n 'runs-on' .github/workflows/ci.yml (line 12 == '${{ matrix.os }}'; lines 36/58/79/96 unchanged 'ubuntu-latest')"
        status: pass
    human_judgment: false

metrics:
  duration: "~10 minutes"
  completed: 2026-07-06

status: complete
---

# Phase 4 Plan 04: Add macos-latest to ovid-client-tests CI Matrix Summary

Added a `strategy.matrix.os: [ubuntu-latest, macos-latest]` (with `fail-fast: false`) to the `ovid-client-tests` job in `.github/workflows/ci.yml`, switching its `runs-on` to `${{ matrix.os }}` and its `name` to `ovid-client tests (${{ matrix.os }})`, so Blu-ray/UHD determinism tests actually execute on both Linux and macOS runners in CI instead of being asserted only on paper.

## What Was Built

`.github/workflows/ci.yml`'s `ovid-client-tests` job previously ran on `ubuntu-latest` only, while FPRINT-05 requires "identical fingerprints across ≥2 drives and both Linux and macOS" — a gap identified as D-14 in phase context/validation. `.github/workflows/release.yml`'s `cli-binaries` job already proves `macos-latest` runners are available and affordable in this repo's GitHub Actions plan, so this change mirrors that proven pattern rather than introducing a new capability.

The diff:
```yaml
  ovid-client-tests:
    name: ovid-client tests (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
    defaults:
      run:
        working-directory: ovid-client
```

Every step (`actions/checkout@v6`, `actions/setup-python@v6` with `python-version: "3.12"`, `pip install -e '.[dev]'`, `python -m pytest tests/ -v --tb=short`) was left unchanged — neither `setup-python` nor `pip install -e` behave differently on `macos-latest` vs `ubuntu-latest` for `ovid-client`, which has no native compiled dependencies. No other job (`api-tests`, `e2e-tests`, `web-tests`, `docs-build`) was modified. `e2e-tests`' `needs: [ovid-client-tests, api-tests]` already waits for all matrix legs of a dependency job by default in GitHub Actions, so no change was needed there.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

Ran locally (no `pyyaml` present in the system Python; used a throwaway venv purely for local YAML-parse verification — no project dependency changes):
```
ci.yml matrix OK
```
Confirmed:
- `d['jobs']['ovid-client-tests']['strategy']['matrix']['os']` contains both `ubuntu-latest` and `macos-latest`
- `d['jobs']['ovid-client-tests']['runs-on'] == '${{ matrix.os }}'`
- `grep -c "macos-latest" .github/workflows/ci.yml` → 1
- All other jobs' `runs-on: ubuntu-latest` lines (api-tests, e2e-tests, web-tests, docs-build) unchanged

Actual execution of both matrix legs in the GitHub Actions UI is outside this plan's automated verification scope (per the plan's own `<verification>` section) and will be observed on the next push/PR.

## Self-Check: PASSED

- FOUND: .github/workflows/ci.yml (modified, matrix present)
- FOUND: commit 075bc27 in `git log --oneline`
