---
phase: 4
slug: blu-ray-uhd-fingerprinting
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-06
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (constraint `pytest>=7.0` declared in `ovid-client/pyproject.toml`'s `[project.optional-dependencies].dev`) |
| **Config file** | `ovid-client/pyproject.toml` — `[tool.pytest.ini_options]` registers the `real_disc` marker; no separate `pytest.ini`/`setup.cfg` exists |
| **Quick run command** | `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py tests/test_bd_disc.py tests/test_bd_identity.py tests/test_bd_fingerprint_pinned.py tests/test_bd_real_disc.py -q` |
| **Full suite command** | `cd ovid-client && python -m pytest tests/ -q` |
| **Estimated runtime** | ~1–2 seconds (measured baseline on this machine: 218 passed, 10 skipped in 0.44–0.88s *before* Phase 4's ~25 new tests; the suite is pure in-memory Python with no DB/disc I/O, so it stays sub-2s afterward) |

*Note: three of the five files in the quick-run command (`test_bd_identity.py`, `test_bd_fingerprint_pinned.py`, `test_bd_real_disc.py`) do not exist yet — each is scaffolded in-plan by its owning plan's first task (see Wave 0 Requirements below). Until those land, target only the two existing files: `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py tests/test_bd_disc.py -q`.*

---

## Sampling Rate

- **After every task commit:** Run `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py tests/test_bd_disc.py tests/test_bd_identity.py tests/test_bd_fingerprint_pinned.py tests/test_bd_real_disc.py -q` (only the files that exist as of that commit)
- **After every plan wave:** Run `cd ovid-client && python -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | FPRINT-06 | T-04-01 | Loop-padded/duplicate decoy playlists excluded; tie-break by clip-sequence, never filename | tdd | `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py -k "max_clip_repeats or dedup_by_clip_sequence or tie_break_is_clip_sequence or ovid_bd2_version_constant or deduped_playlists_still_sort" -v 2>&1 \| tail -20` | ✅ | ⬜ pending |
| 4-01-02 | 01 | 1 | FPRINT-06, FPRINT-01 | T-04-01 / T-04-02 / T-04-03 | `bd2_spec.py` is the sole source of `MIN_DURATION_SECONDS`/`MAX_CLIP_REPEATS`/version; AACS docstring states SHA-1-of-plaintext-file, not a key | tdd | `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py -v 2>&1 \| tail -40` | ✅ | ⬜ pending |
| 4-02-01 | 02 | 1 | FPRINT-03 | T-04-04 / T-04-06 | `identify_bd()` never short-circuits to Tier-1 when Tier-2 is computable; every AACS branch logs exactly one diagnostic | tdd | `cd ovid-client && python -m pytest tests/test_bd_identity.py -v 2>&1 \| tail -30` | ❌ W0 | ⬜ pending |
| 4-02-02 | 02 | 1 | FPRINT-03 | T-04-04 / T-04-05 / T-04-06 | Tier-2 always primary when computable; Tier-1 attached as alias; raw `Unit_Key_RO.inf` bytes never leave `aacs_identity()` | tdd | `cd ovid-client && python -m pytest tests/test_bd_identity.py tests/test_disc_identity.py -v 2>&1 \| tail -40` | ✅ | ⬜ pending |
| 4-03-01 | 03 | 2 | FPRINT-03, FPRINT-04, FPRINT-06 | T-04-07 / T-04-08 / T-04-09 | `BDDisc` surfaces `bd2-`/`uhd2-` primary + `bd1-aacs-`/`uhd1-aacs-` alias; decoy playlists excluded from `.playlists`, not just the hash | tdd | `cd ovid-client && python -m pytest tests/test_bd_disc.py -v 2>&1 \| tail -60` | ✅ | ⬜ pending |
| 4-03-02 | 03 | 2 | FPRINT-03, FPRINT-04, FPRINT-06 | T-04-07 / T-04-08 / T-04-09 | `.identity` delegates to `identify_bd()`; `.fingerprint`/`.tier` are thin proxies to `.identity.primary`; `.playlists` mirrors the `select_canonical_playlists()` survivor set | tdd | `cd ovid-client && python -m pytest tests/test_bd_disc.py tests/test_bd_fingerprint.py tests/test_bd_identity.py tests/test_disc_structure.py -v 2>&1 \| tail -60` | ✅ | ⬜ pending |
| 4-04-01 | 04 | 1 | FPRINT-05 | T-04-11 | `ovid-client-tests` CI job executes on both `ubuntu-latest` and `macos-latest`; no new secrets/third-party actions introduced | integration | `python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/ci.yml')); assert 'macos-latest' in d['jobs']['ovid-client-tests']['strategy']['matrix']['os']; assert d['jobs']['ovid-client-tests']['runs-on'] == '${{ matrix.os }}'; print('ci.yml matrix OK')"` | ✅ | ⬜ pending |
| 4-05-01 | 05 | 3 | FPRINT-07, FPRINT-06 | T-04-13 / T-04-14 | 23-entry heavily-obfuscated corpus (exact duplicate, loop-padded decoy, 20 short fillers) collapses to exactly 1 canonical survivor through the frozen filter/dedup pipeline | unit | `cd ovid-client && python3 -c "import sys; sys.path.insert(0, 'tests'); from conftest_bd import build_heavily_obfuscated_fixture; from ovid.bd_fingerprint import select_canonical_playlists; pls = build_heavily_obfuscated_fixture(is_uhd=False); assert len(pls) == 23; survivors = select_canonical_playlists(pls); assert len(survivors) == 1; print('conftest_bd fixture OK')"` | ✅ | ⬜ pending |
| 4-05-02 | 05 | 3 | FPRINT-06, FPRINT-07, FPRINT-05 | T-04-12 / T-04-13 | Pinned `bd2-`/`uhd2-` hash for the obfuscated fixture is hardcoded and never re-derived in-test (anti-tautology); real-disc test file only asserts on `.fingerprint`/`.canonical_string`/`.identity.diagnostics`, never raw AACS bytes | unit | `cd ovid-client && python -m pytest tests/test_bd_fingerprint_pinned.py tests/test_bd_real_disc.py -v 2>&1 \| tail -40` | ❌ W0 | ⬜ pending |
| 4-06-01 | 06 | 3 | DOCS-01, FPRINT-01, FPRINT-04 | T-04-15 / T-04-16 | Spec documents the AACS-Disc-ID-is-not-a-key wording and the version-bump-mints-new-namespace rule; UHD `0x0300` heuristic documented as a community-corroborated convention, not a licensed BDA guarantee | integration | `cd /Users/trekkie/projects/OVID && python3 -c "content = open('docs/fingerprint-spec.md').read(); assert '## OVID-BD-2 Fingerprint Algorithm Specification' in content; assert 'planned, v0.2.0' not in content; assert 'MAX_CLIP_REPEATS' in content and 'MIN_DURATION_SECONDS' in content; assert 'AACS Disc ID' in content; print('fingerprint-spec.md OK')"` | ✅ | ⬜ pending |
| 4-06-02 | 06 | 3 | FPRINT-05 | — | Manual cross-drive verification step documented in `docs/contributing.md` so the ≥2-drives/OS requirement can't be silently skipped before a release | integration | `cd /Users/trekkie/projects/OVID && grep -c "Manual pre-release verification" docs/contributing.md && grep -c "OVID_TEST_DISC_PATH_2" docs/contributing.md` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure (pytest 9.1.1, `ovid-client/pyproject.toml` config, the `real_disc` marker, `tests/conftest.py`/`tests/conftest_bd.py` fixture builders) already covers Phase 4 — no framework install is needed. Three test files are new and are scaffolded **in-plan**, as the first (RED) task of the plan that owns them, mirroring Phase 1's convention (no separate Wave 0 pass required):

- [ ] `ovid-client/tests/test_bd_identity.py` — new file; created by Plan 04-02 Task 1 (RED); 8 tests + `_FakeReader` targeting `identify_bd()`/`ovid_bd2_identity()`/`aacs_identity()` before those symbols exist
- [ ] `ovid-client/tests/test_bd_fingerprint_pinned.py` — new file; created by Plan 04-05 Task 2; 4 pinned/golden tests for the obfuscated-fixture hash
- [ ] `ovid-client/tests/test_bd_real_disc.py` — new file; created by Plan 04-05 Task 2; hardware-gated on `OVID_TEST_DISC_PATH`/`OVID_TEST_DISC_PATH_2`, collects and skips cleanly with no hardware present in CI
- [ ] `ovid-client/tests/conftest_bd.py` — existing file, extended (not created) by Plan 04-05 Task 1 with `build_heavily_obfuscated_fixture()`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Blu-ray/UHD fingerprint identical across ≥2 physical drives and both Linux/macOS | FPRINT-05 | No CI runner has physical optical hardware; the `real_disc`-marked, `OVID_TEST_DISC_PATH`/`OVID_TEST_DISC_PATH_2`-gated tests can only be exercised by a contributor with real discs and ≥2 drives (Plan 04-05) | From `ovid-client/`: `OVID_TEST_DISC_PATH=/path/to/drive1 OVID_TEST_DISC_PATH_2=/path/to/drive2 python -m pytest tests/test_bd_real_disc.py -v -m real_disc` — `TestRealBDDiscCrossDrive::test_cross_drive_fingerprint_matches` must pass with both env vars pointed at two drives reading the same physical disc |
| Pre-release cross-drive verification is actually performed before any release touching BD/UHD fingerprinting | FPRINT-05 | This is a process/documentation gate, not a CI job — D-13 requires it folded into a documented step so it can't be silently skipped | Before tagging a release that touches Blu-ray/UHD code, a contributor with real hardware follows `docs/contributing.md`'s "Manual pre-release verification (Blu-ray/UHD)" subsection (added by Plan 04-06 Task 2) and confirms the command above passes across ≥2 drives/OSes |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s (measured ~1–2s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-06
