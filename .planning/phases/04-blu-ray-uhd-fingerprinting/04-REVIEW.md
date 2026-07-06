---
phase: 04-blu-ray-uhd-fingerprinting
reviewed: 2026-07-06T00:00:00Z
depth: deep
files_reviewed: 13
files_reviewed_list:
  - ovid-client/src/ovid/bd2_spec.py
  - ovid-client/src/ovid/bd_disc.py
  - ovid-client/src/ovid/bd_fingerprint.py
  - ovid-client/src/ovid/disc_identity.py
  - ovid-client/tests/conftest_bd.py
  - ovid-client/tests/test_bd_disc.py
  - ovid-client/tests/test_bd_fingerprint.py
  - ovid-client/tests/test_bd_fingerprint_pinned.py
  - ovid-client/tests/test_bd_identity.py
  - ovid-client/tests/test_bd_real_disc.py
  - .github/workflows/ci.yml
  - docs/fingerprint-spec.md
  - docs/contributing.md
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: resolved
resolved: 2026-07-06
resolution_commits: [daad488, 85a9eac, 72e873f]
---

# Phase 04: Code Review Report

**Reviewed:** 2026-07-06T00:00:00Z
**Depth:** deep
**Files Reviewed:** 13
**Status:** resolved — all 10 findings fixed post-review (commits daad488, 85a9eac, 72e873f)

> **Resolution (2026-07-06):** All 10 findings fixed inline per no-defer policy. **CR-01** (0-stream vs 1-empty-stream canonical collision) fixed test-first — new 7-field block `{pic}:{dur}:{cc}:{audio_count}:{audio}:{subtitle_count}:{subtitle}`; pinned hash recomputed to `bd2-a9b2941ab6cd447c0c3ece709a348ff6c6c26ae3`. `OVID_BD2_VERSION` unchanged (pre-release correction — `bd2-*` has no shipped consumers). WR-01/02/03/05 + IN-01..04 fixed; WR-04 (Windows CI) documented as deliberately out of scope per FPRINT-05 (Linux+macOS only). Verified independently: 242 passed, 16 skipped; CR-01 regression test green.

## Summary

Reviewed the OVID-BD-2 Blu-ray/UHD Tier-2 structure-hash pipeline (`bd2_spec.py`, `bd_fingerprint.py`), the Tier-1/Tier-2 alias-pair identity resolution (`disc_identity.py`, `bd_disc.py`), the full BD test suite, and the CI/docs artifacts that codify FPRINT-05 (determinism) and FPRINT-06 (anti-obfuscation).

The frozen-constant discipline (FPRINT-06), the alias-pair correctness (FPRINT-03 — Tier 2 always primary when computable, Tier 1 attached as alias, Tier 1 only becomes primary in the documented degenerate case), and the content-based (not filename-based) tie-break/dedup are all implemented correctly and match their documentation and pinned/golden tests. No legal-boundary violation was found — raw `Unit_Key_RO.inf` bytes are never logged, returned, or persisted; only the derived SHA-1 digest is exposed.

However, a real determinism/uniqueness defect was found in the canonical-string field encoding (`build_bd_canonical_string`): the subtitle-language list is joined without any length/count marker, which collapses "zero subtitle streams" and "one subtitle stream with an empty/unparsed language code" into the identical encoded field — a plausible real-world scenario for forced/unlabeled subtitle tracks, undermining the "different discs produce different fingerprints" guarantee this phase exists to deliver. Several lower-severity robustness, diagnostics-accuracy, and code-hygiene issues are also documented below.

## Critical Issues

### CR-01: Ambiguous audio/subtitle field encoding permits fingerprint collisions between structurally different discs

**File:** `ovid-client/src/ovid/bd_fingerprint.py:184-194`

**Issue:** In `build_bd_canonical_string()`:

```python
sub_parts: list[str] = [s.language for s in pl.subtitle_streams]
subtitle_info = ",".join(sub_parts) if sub_parts else ""
```

`subtitle_info` is derived purely from the joined language codes with no explicit stream count. If a playlist has **zero** subtitle streams, `sub_parts == []` → `subtitle_info == ""`. If a playlist has **exactly one** subtitle stream whose language could not be decoded (e.g. a null/`0x00 0x00 0x00` language field — common for forced or unlabeled PG tracks, and explicitly stripped to `""` by `mpls_parser._parse_stn_table` via `.strip("\x00")`), then `sub_parts == [""]` → `",".join([""]) == ""` → `subtitle_info == ""` again. **Both cases produce the identical encoded field.**

Since every other block field (`play_item_count`, `total_duration`, `chapter_count`, `audio_info`) can plausibly match between two otherwise-distinct pressings (e.g. two cuts sharing the same runtime/chapter layout but differing only in whether a forced-subtitle track is present), this is a real, demonstrable path to two structurally different discs hashing to the *same* `bd2-`/`uhd2-` fingerprint — directly contradicting the stated design goal ("Unique: different disc pressings/editions produce different fingerprints", `docs/fingerprint-spec.md:24`) and the anti-obfuscation intent of FPRINT-06.

The same unescaped-join pattern also means any raw ASCII byte (including `,`, `+`, `:`, or even `|`) surviving the STN-table language decode (`mpls_parser.py` only rejects non-ASCII bytes, not the ASCII delimiter characters used by this encoding) is embedded verbatim into the canonical string with no escaping, so a crafted/corrupted language field can also shift apparent field/block boundaries.

Audio streams are not affected the same way because `audio_info` always prefixes a non-empty codec name (`f"{s.codec}+{s.language}+{s.channels}"`), so an audio entry can never collapse to `""`.

**Fix:** Encode the subtitle (and, for defense in depth, audio) list with an explicit count or length-prefixed/escaped representation so "0 streams" and "1 stream with empty value" cannot collide, e.g.:

```python
sub_parts: list[str] = [s.language for s in pl.subtitle_streams]
subtitle_info = f"{len(sub_parts)}:" + ",".join(sub_parts)
```

or escape delimiter characters in `language`/`codec` before joining. **This is a canonical-string encoding change** — per the project's own versioning rule (`docs/fingerprint-spec.md:239-241`, `bd2_spec.py` module docstring), it must bump `OVID_BD2_VERSION` (e.g. to a `bd2v2-`/`uhd2v2-` Fingerprint Version) rather than silently mutating `bd2-`/`uhd2-` fingerprints for existing discs.

## Warnings

### WR-01: Overly broad `except Exception` in `identify_bd()` AACS branch

**File:** `ovid-client/src/ovid/disc_identity.py:178-183`

**Issue:** Unlike `identify_dvd()`, which catches only the specific, expected exception types (`ValueError`, `LibdvdreadError`), `identify_bd()`'s AACS-hashing branch catches bare `Exception`:

```python
except Exception as exc:
    diagnostics.append(
        DiscIdentityDiagnostic(code="aacs_fingerprint_failed", message=str(exc))
    )
```

This will silently swallow genuine programming errors (e.g. an `AttributeError` from a typo, a `MemoryError`, or a future regression) and misreport them as a benign "AACS hash failed" diagnostic instead of surfacing them as bugs.

**Fix:** Narrow the catch to the concrete failure modes actually expected here (e.g. `TypeError` for malformed reader payloads), matching the precise-exception discipline already used in `identify_dvd()`.

### WR-02: Filesystem permission/read errors on `Unit_Key_RO.inf` are mislabeled as "missing"

**File:** `ovid-client/src/ovid/readers/bd_folder.py:119-124`, cross-referenced by `ovid-client/src/ovid/disc_identity.py:167-172`

**Issue:** `BDFolderReader.read_aacs_file()` catches `OSError` (e.g. permission denied, I/O error) and returns `None`, identically to the "file does not exist" case:

```python
try:
    with open(full, "rb") as fh:
        return fh.read()
except OSError:
    logger.warning("Failed to read AACS file: %s", full)
    return None
```

`identify_bd()` then records `aacs_unit_key_missing` for this `None` result (`disc_identity.py:169-172`), which is semantically wrong when the file exists but couldn't be read (e.g. a permissions problem on the user's system) — the diagnostic should distinguish "not present" from "present but unreadable" so operators can actually act on the signal.

**Fix:** Have `read_aacs_file()` raise a distinct, catchable error (or return a sentinel) for read failures versus returning `None` only for "not found", and add a distinct diagnostic code (e.g. `aacs_unit_key_read_error`) in `identify_bd()`.

### WR-03: Triplicate, independently-invoked filter/dedup/sort pipeline risks future drift

**File:** `ovid-client/src/ovid/bd_disc.py:139-150`

**Issue:** `BDDisc._build()` calls the filter/dedup/sort pipeline three separate times over the same `parsed_playlists`:
1. `build_bd_canonical_string(parsed_playlists, is_uhd)` directly (line 140), just to populate `canonical_string` and detect whether Tier 2 is computable.
2. `identify_bd(...)` internally calls `build_bd_canonical_string()` again (`disc_identity.py:186`) to build the actual primary identity.
3. `select_canonical_playlists(parsed_playlists)` directly (line 149) again, to populate `.playlists`.

All three currently agree because the pipeline is a pure function of `parsed_playlists`, but this duplication means any future change to one call site (e.g. passing a filtered/mutated list, or catching a different exception type) can silently desynchronize `canonical_string`/`.playlists`/`.fingerprint` from each other without any test catching the divergence at the seam — there is no single source of truth for "the survivor set used for this BDDisc".

**Fix:** Compute the survivor set / canonical string once (e.g. have `identify_bd()` return the computed canonical string and survivor list alongside the `DiscIdentitySet`, or expose them from `build_bd_canonical_string`/`select_canonical_playlists` results) and reuse that single result to populate `canonical_string`, `.playlists`, and the identity — instead of three independent re-derivations.

### WR-04: CI does not verify cross-OS determinism for Blu-ray fingerprinting on Windows

**File:** `.github/workflows/ci.yml:15-16`

**Issue:** FPRINT-05 requires the fingerprint to be "byte-identical across drives/OSes" (per this phase's stated concern, and `docs/contributing.md:149` explicitly calls out "at least 2 physical drives and both Linux and macOS"). The `ovid-client-tests` job matrix is `[ubuntu-latest, macos-latest]` only — Windows is never exercised, even for the fully-synthetic, hardware-independent tests (`test_bd_fingerprint_pinned.py`, `test_bd_disc.py`, etc.) that would catch OS-dependent bugs in path handling, case-insensitive directory lookup (`BDFolderReader._find_bdmv`/`_find_subdir`/`_find_aacs`, all `os.listdir` + `.upper()` based), or filesystem enumeration order.

**Fix:** Add `windows-latest` to the `ovid-client-tests` matrix (the synthetic/no-hardware BD tests do not require real optical media and can run unattended on Windows CI runners), leaving only the real-disc hardware tests gated behind the documented manual pre-release step.

### WR-05: `is_uhd` parameter is entirely unused inside `build_bd_canonical_string()` with no explanatory comment

**File:** `ovid-client/src/ovid/bd_fingerprint.py:136-197`

**Issue:** `build_bd_canonical_string(playlists, is_uhd)` never references `is_uhd` in its body — the canonical string content is identical regardless of format. This is intentional and documented at the *docs* level (`docs/fingerprint-spec.md:237`: "Tier 1 and Tier 2 fingerprints are computed identically regardless of the detected format"), and is even locked in by the pinned tests (`PINNED_BD2_HASH` and `PINNED_UHD2_HASH` in `test_bd_fingerprint_pinned.py:25-26` share the identical 40-hex-char suffix). However, nothing in `bd_fingerprint.py` itself explains this — a future contributor reading only the source (not the docs) could reasonably conclude this is a bug and "fix" it by mixing `is_uhd` into the canonical string, silently minting a new fingerprint space without going through the required `OVID_BD2_VERSION` bump process.

**Fix:** Add an inline comment on the `is_uhd` parameter (or at the top of the function body) explicitly stating it is unused by design and pointing to the "Format Detection (UHD)" section of `docs/fingerprint-spec.md`, so the frozen-ruleset intent is discoverable from the code alone.

## Info

### IN-01: Unused imports in `test_bd_disc.py`

**File:** `ovid-client/tests/test_bd_disc.py:20-21`

**Issue:** `import hashlib` and `import os` are both dead imports — neither name is referenced anywhere in the file.

**Fix:** Remove both unused imports.

### IN-02: Unused imports in `test_bd_fingerprint.py`

**File:** `ovid-client/tests/test_bd_fingerprint.py:14,25`

**Issue:** `import os` (line 14) is never used. `MplsPlaylist` (line 25, imported alongside `parse_mpls`) is also never referenced — only `parse_mpls` is used.

**Fix:** Remove `import os`; change the import to `from ovid.mpls_parser import parse_mpls`.

### IN-03: Diagnostics collected before a re-raised `ValueError` are silently discarded

**File:** `ovid-client/src/ovid/disc_identity.py:185-199`

**Issue:** When Tier 2 is unavailable and no Tier 1 identity exists, `identify_bd()` does a bare `raise` (line 199), propagating the original `ValueError` from `build_bd_canonical_string()`. Any diagnostics already appended to the local `diagnostics` list (e.g. `no_aacs_directory`) are discarded — the caller only sees the generic "No valid playlists..." message, losing potentially useful context about *why* Tier 1 also wasn't available.

**Fix:** Consider re-raising with the accumulated diagnostic codes appended to the error message (e.g. `raise ValueError(f"{exc} (diagnostics: {[d.code for d in diagnostics]})") from exc`) to aid debugging without changing the exception type callers already handle.

### IN-04: Stale marker docstring after this phase's addition of BD/UHD real-disc tests

**File:** `ovid-client/pyproject.toml:53`

**Issue:** The `real_disc` pytest marker is documented as `"real_disc: tests that require a real DVD disc path via OVID_TEST_DISC_PATH env var"`, but this phase adds `test_bd_real_disc.py`, which also uses this exact marker for real Blu-ray/UHD discs (not just DVD).

**Fix:** Update the marker description to `"real_disc: tests that require a real disc path (DVD/BD/UHD) via OVID_TEST_DISC_PATH env var"`.

---

_Reviewed: 2026-07-06T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
