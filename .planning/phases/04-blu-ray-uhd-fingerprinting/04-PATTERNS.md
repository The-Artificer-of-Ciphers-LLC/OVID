# Phase 4: Blu-ray/UHD Fingerprinting - Pattern Map

**Mapped:** 2026-07-06
**Files analyzed:** 10
**Analogs found:** 10 / 10 (this is a hardening phase — every new/modified file has a strong in-tree analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `ovid-client/src/ovid/disc_identity.py` (add `identify_bd()`) | service (identity resolution) | CRUD-like (build+attach identities) | same file, `identify_dvd()` (lines 65-98) | exact — same function, same module |
| `ovid-client/src/ovid/bd2_spec.py` (new) | config/constants | transform | `ovid-client/src/ovid/disc_identity.py` module-constant pattern (`OVID_DVD1_METHOD`/`OVID_DVD1_VERSION`, lines 12-15) | role-match (frozen constants module; no existing dedicated `*_spec.py`, closest is inline constants pattern in `bd_fingerprint.py` lines 26-27) |
| `ovid-client/src/ovid/bd_fingerprint.py` (modify tie-break/dedup) | utility (transform) | transform | same file, `build_bd_canonical_string()` (lines 46-123) | exact — in-place modification |
| `ovid-client/src/ovid/bd_disc.py` (remove short-circuit, delegate) | model/controller (`BDDisc._build`) | request-response (build from I/O) | `ovid-client/src/ovid/disc.py` `Disc.from_path()`/identity delegation (referenced via `test_real_disc.py` `_identity_set`) and `disc_identity.py::identify_dvd` | role-match — mirrors how `Disc` already delegates to `identify_dvd()` |
| `ovid-client/src/ovid/mpls_parser.py` (verify only, no change expected) | utility (parser) | transform | itself — no change needed | exact (no-op) |
| `ovid-client/tests/conftest_bd.py` (extend with obfuscated-tree generator) | test fixture | batch/transform | same file, `make_mpls_file()` (lines 238-313) | exact — extend existing builder file |
| `ovid-client/tests/test_bd_fingerprint.py` (extend + E2E test) | test | request-response | same file (existing component tests) + `test_disc_identity.py` structure | exact |
| `ovid-client/tests/test_bd_fingerprint_pinned.py` (new) | test (golden/pinned) | batch | `ovid-client/tests/test_disc_identity.py` (structure/style) — no existing pinned-hash test to copy exactly, so this is a role-match | role-match (anti-tautology golden-fixture convention referenced from Phase 1 D-14, no direct pinned-hash analog file in tree) |
| `ovid-client/tests/test_bd_identity.py` (new) | test | request-response | `ovid-client/tests/test_disc_identity.py` (all 5 tests, lines 15-89) | exact — direct structural mirror |
| `ovid-client/tests/test_bd_real_disc.py` (new) | test (hardware-gated) | file-I/O | `ovid-client/tests/test_real_disc.py` (full file, lines 1-89) | exact |
| `docs/fingerprint-spec.md` (add OVID-BD-2 section) | docs | transform | same file, existing OVID-DVD-1 sections (`## Algorithm`, `## Versioning` lines 165-169) | exact — same file, new section mirrors existing structure |
| `.github/workflows/ci.yml` (add macOS runner to `ovid-client-tests`) | config (CI) | batch | `.github/workflows/release.yml` `matrix.os`/`matrix.runner` for the `macos-latest` CLI-binary job (lines 147-164) | exact — proven working pattern in the same repo |

## Pattern Assignments

### `ovid-client/src/ovid/disc_identity.py` — add `identify_bd()` (service, CRUD-like)

**Analog:** same file, `identify_dvd()` (lines 65-98), `DiscIdentity`/`DiscIdentitySet`/`DiscIdentityDiagnostic` dataclasses (lines 18-41), and the per-method constants convention (lines 12-15).

**Imports pattern** (lines 1-10):
```python
"""DVD Disc Identity selection and fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

from ovid.dvdread_adapter import LibdvdreadError, read_libdvdread_disc_id
from ovid.fingerprint import compute_fingerprint
```
For `identify_bd()`, mirror this shape: import `compute_aacs_fingerprint`/`compute_bd_structure_fingerprint` from `ovid.bd_fingerprint`, and `BDFolderReader` from `ovid.readers.bd_folder` (or accept a reader-like callable, matching how `identify_dvd` takes `read_libdvdread_disc_id` as an injectable callable for testability — line 69).

**Method/version constant pattern** (lines 12-15):
```python
OVID_DVD1_METHOD = "ovid-dvd-1"
OVID_DVD1_VERSION = "dvd1"
LIBDVDREAD_METHOD = "libdvdread-disc-id"
LIBDVDREAD_VERSION = "dvdread1"
```
Use analogous constants for BD: `OVID_BD2_METHOD = "ovid-bd-2"`, version varies by `is_uhd` (`"bd2"`/`"uhd2"`), `AACS_METHOD = "aacs-disc-id"`, version `"bd1-aacs"`/`"uhd1-aacs"`.

**Core "always primary, opportunistic alias" pattern** (lines 65-98 — the exact function `identify_bd` mirrors):
```python
def identify_dvd(
    path: str,
    canonical: str,
    *,
    read_libdvdread_disc_id: Callable[[str], str] = read_libdvdread_disc_id,
) -> DiscIdentitySet:
    """Identify a DVD while keeping OVID-DVD-1 primary during Phase 1."""
    primary = ovid_dvd1_identity(canonical)
    aliases: list[DiscIdentity] = []
    diagnostics: list[DiscIdentityDiagnostic] = []

    try:
        disc_id_hex = read_libdvdread_disc_id(path)
        aliases.append(libdvdread_identity(disc_id_hex))
        diagnostics.append(
            DiscIdentityDiagnostic(code="libdvdread_disc_id_available")
        )
    except ValueError as exc:
        diagnostics.append(
            DiscIdentityDiagnostic(
                code="libdvdread_invalid_disc_id",
                message=str(exc),
            )
        )
    except LibdvdreadError as exc:
        diagnostics.append(
            DiscIdentityDiagnostic(code=exc.code, message=str(exc))
        )

    return DiscIdentitySet(
        primary=primary,
        aliases=aliases,
        diagnostics=diagnostics,
    )
```
`identify_bd()` follows the identical shape: build `primary` unconditionally (Tier 2, never wrapped in try/except since it's the always-computable structural identity — matches `ovid_dvd1_identity(canonical)` being called unconditionally at line 72), then attempt Tier 1 in a try/except-like diagnostic chain, appending to `aliases` on success and a `DiscIdentityDiagnostic` on every path (success or specific failure reason) — never silently drop the diagnostic trail. RESEARCH.md's Pattern 1 code example (lines 210-260 of `04-RESEARCH.md`) already gives the concrete target implementation; treat it as the draft, `identify_dvd()` above as the enforced style precedent (docstring convention, `Callable[..., ...] = default_impl` injectable pattern for testability, one `DiscIdentityDiagnostic` per branch).

**Dataclasses to reuse verbatim (no changes needed)** (lines 18-41):
```python
@dataclass(frozen=True)
class DiscIdentity:
    fingerprint: str
    method: str
    fingerprint_version: str


@dataclass(frozen=True)
class DiscIdentityDiagnostic:
    code: str
    message: str | None = None


@dataclass(frozen=True)
class DiscIdentitySet:
    primary: DiscIdentity
    aliases: list[DiscIdentity] = field(default_factory=list)
    diagnostics: list[DiscIdentityDiagnostic] = field(default_factory=list)
```
These are format-neutral already — `identify_bd()` reuses them unchanged; no BD-specific subclassing.

---

### `ovid-client/src/ovid/bd2_spec.py` (new frozen constants module)

**Analog:** No dedicated `*_spec.py` module exists yet in the tree. Closest patterns to mirror:
1. Module-level constant + docstring convention from `disc_identity.py` (lines 1, 12-15) — one-line module docstring, `UPPER_SNAKE_CASE` constants at top of file, no class wrapper.
2. The constant this module extracts FROM: `bd_fingerprint.py` lines 25-27:
```python
# Minimum playlist duration in seconds to include in the structure hash.
# Playlists shorter than this are typically menus or anti-rip obfuscation.
_MIN_DURATION_SECONDS = 60.0
```
Move this (renamed public, no leading underscore since it's now the frozen public contract per D-07) plus a new `MAX_CLIP_REPEATS = 2` and `OVID_BD2_VERSION = "OVID-BD-2"` version literal into `bd2_spec.py`. RESEARCH.md Pattern 2 (lines 268-290) is the concrete draft — follow its docstring emphasizing "any edit without bumping the version literal mints silently different fingerprints," matching this project's convention of docstrings explaining *why*, not *what* (CLAUDE.md "Comments" convention, and `conftest.py`'s SQLite/UUID shim docstring precedent).

**Module docstring convention to follow** (module-design rule from project CLAUDE.md — "Module docstrings appear at top of every file, one line, describing the module's purpose"): keep the one-line summary docstring, put rationale in a following paragraph, as `bd_fingerprint.py` lines 1-14 already does.

---

### `ovid-client/src/ovid/bd_fingerprint.py` — replace filename tie-break with clip-sequence tie-break (utility, transform)

**Analog:** same file, `build_bd_canonical_string()` (lines 46-123), specifically the filter+sort block to replace (lines 82-101):
```python
# Filter by minimum duration
filtered: list[tuple[str, MplsPlaylist, float]] = []
for fname, pl in playlists:
    dur = _total_duration(pl)
    if dur >= _MIN_DURATION_SECONDS:
        filtered.append((fname, pl, dur))

if not filtered:
    raise ValueError(
        f"No valid playlists after 60-second filter "
        f"(had {len(playlists)} playlist(s), all under {_MIN_DURATION_SECONDS}s)"
    )
...
# Deterministic sort: by total duration descending, then filename ascending
filtered.sort(key=lambda x: (-x[2], x[0]))
```
Replace `_MIN_DURATION_SECONDS` import with `from ovid.bd2_spec import MIN_DURATION_SECONDS, MAX_CLIP_REPEATS, OVID_BD2_VERSION`, add the `MAX_CLIP_REPEATS` filter and clip-sequence dedup+tie-break exactly as drafted in RESEARCH.md Pattern 3 (lines 298-325), and change the leading `parts: list[str] = ["OVID-BD-2", ...]` (line 103) to reference `OVID_BD2_VERSION` instead of a hardcoded literal, so a version bump in `bd2_spec.py` automatically changes the canonical string prefix.

**Existing `PlayItem` fields already sufficient** (`mpls_parser.py`, confirmed via grep): `clip_id: str`, `in_time: int`, `out_time: int`, `duration_seconds: float` — no parser change needed; `_clip_sequence()`/`_clip_repeat_count()` (RESEARCH.md Pattern 3) consume these directly.

---

### `ovid-client/src/ovid/bd_disc.py` — remove Tier-1 short-circuit, delegate to `identify_bd()`

**Analog:** same file's own `_build()` classmethod (lines 80-160) is what's being refactored; the delegation pattern to copy is `disc_identity.py`'s `identify_dvd()` call-site convention (visible via `test_real_disc.py::test_identity_selection_has_diagnostics`, line 68-70, which asserts `real_disc._identity_set.diagnostics` exists — i.e. `Disc` stores an `_identity_set` attribute fed by `identify_dvd()`).

**Current short-circuit to remove** (lines 114-133 — the FPRINT-03 gap):
```python
# Try AACS Tier 1 first — this does NOT require playlist filtering
# because the fingerprint comes from Unit_Key_RO.inf, not MPLS data.
tier1_fp = cls._try_aacs_tier1(reader, is_uhd)
if tier1_fp is not None:
    logger.info("Using AACS Tier 1 fingerprint")
    ...
    return cls(
        fingerprint=tier1_fp,
        tier=1,
        ...
    )
```
This early `return` is the exact violation of D-02 — replace the entire Tier-1-then-Tier-2 branching in `_build()` with: always build Tier-2 canonical string/fingerprint (using the same 60s+repeat filter now sourced from `bd2_spec.py`), call `identify_bd(...)` to attach Tier-1 as alias, and store the resulting `DiscIdentitySet` as `.identity` (new field) with `.fingerprint`/`.tier` kept as `@property` proxies to `.identity.primary.fingerprint` / a tier-number derived from `.identity.primary.method` — per D-04's back-compat requirement. `BDDisc` is currently `@dataclass(frozen=True)` (line 27) with `fingerprint`/`tier` as plain fields (lines 42-43); converting to properties over an added `identity: DiscIdentitySet` field is the concrete field-shape change.

**Static Tier-1 attempt to reuse (already correct, no change needed)** (lines 162-182):
```python
@staticmethod
def _try_aacs_tier1(reader: BDFolderReader, is_uhd: bool) -> str | None:
    """Attempt AACS Tier 1 fingerprint.  Returns None on any failure."""
    if not reader.has_aacs():
        logger.info("No AACS directory found")
        return None

    unit_key_data = reader.read_aacs_file("Unit_Key_RO.inf")
    if unit_key_data is None:
        logger.warning("AACS directory exists but Unit_Key_RO.inf not found")
        return None

    if len(unit_key_data) == 0:
        logger.warning("Unit_Key_RO.inf is empty")
        return None

    try:
        return compute_aacs_fingerprint(unit_key_data, is_uhd)
    except Exception as exc:
        logger.warning("AACS Tier 1 fingerprint failed: %s", exc)
        return None
```
This logic's *branches* (no AACS dir / missing file / empty file / hash exception) map 1:1 onto the four `DiscIdentityDiagnostic` codes named in CONTEXT.md D-04 (`no_aacs_directory`, `aacs_unit_key_missing`, `aacs_fingerprint_failed`) — either inline this logic into `identify_bd()` directly (preferred, since `identify_dvd()`'s pattern keeps the alias-attempt logic in `disc_identity.py`, not the disc-model file) or keep `_try_aacs_tier1` as a thin reader-facing helper called by `identify_bd()`.

**UHD detection (unchanged, reuse as-is)** (lines 106-112):
```python
is_uhd = any(
    pl.header.version == "0300" for _, pl in parsed_playlists
)
format_type = "uhd" if is_uhd else "bluray"
```

---

### `ovid-client/tests/test_bd_identity.py` (new) — mirrors `test_disc_identity.py`

**Analog:** `ovid-client/tests/test_disc_identity.py` (full file, 5 tests, lines 15-89) — read in full; not re-read here since a targeted grep already confirmed the 5 test names:
```
test_ovid_dvd1_identity_uses_existing_fingerprint_format
test_libdvdread_identity_uses_distinct_version
test_identify_dvd_keeps_ovid_dvd1_primary_in_phase_one
test_identify_dvd_falls_back_when_libdvdread_is_unavailable
test_identify_dvd_rejects_invalid_libdvdread_disc_id
```
Mirror this exact 5-test shape for BD: `test_ovid_bd2_identity_uses_existing_fingerprint_format`, `test_aacs_identity_uses_distinct_version`, `test_identify_bd_keeps_bd2_primary_when_aacs_present` (the FPRINT-03 regression test — the single most important test in this phase), `test_identify_bd_falls_back_when_aacs_unavailable` (D-03 one-tier-fallback), `test_identify_bd_rejects_invalid_or_empty_aacs_data`. Use dependency-injection the same way `identify_dvd` takes `read_libdvdread_disc_id` as a keyword-overridable callable (line 69) — inject a fake reader/fake AACS bytes rather than touching the filesystem, matching `test_identify_dvd_falls_back_when_libdvdread_is_unavailable`'s style (raises `LibdvdreadError` via an injected stub).

---

### `ovid-client/tests/test_bd_real_disc.py` (new) — mirrors `test_real_disc.py`

**Analog:** `ovid-client/tests/test_real_disc.py` (full file, lines 1-89).

**Gating pattern to copy verbatim (env var + marker)** (lines 1-23):
```python
"""Tests for real DVD discs — skipped unless OVID_TEST_DISC_PATH is set.

Set OVID_TEST_DISC_PATH to a VIDEO_TS folder or ISO path to run:

    OVID_TEST_DISC_PATH=/mnt/dvd/VIDEO_TS python -m pytest tests/test_real_disc.py -v
"""

from __future__ import annotations

import os
import re

import pytest

DISC_PATH = os.environ.get("OVID_TEST_DISC_PATH")

pytestmark = [
    pytest.mark.real_disc,
    pytest.mark.skipif(
        DISC_PATH is None,
        reason="OVID_TEST_DISC_PATH not set — skipping real disc tests",
    ),
]


@pytest.fixture(scope="module")
def real_disc():
    """Parse the real disc once for the entire module."""
    from ovid.disc import Disc

    assert DISC_PATH is not None  # guarded by skipif above
    return Disc.from_path(DISC_PATH)
```
For BD: rename env var reference in the docstring/example to the same `OVID_TEST_DISC_PATH` (CONTEXT.md D-12 says "a second-drive path" — consider also reading a second env var, e.g. `OVID_TEST_DISC_PATH_2`, for the multi-drive assertion; this is Claude's Discretion per D-12/D-13, no locked name), swap `from ovid.disc import Disc` → `from ovid.bd_disc import BDDisc`, `Disc.from_path` → `BDDisc.from_path`.

**Assertions to mirror (prefix/format/determinism/diagnostics)** (lines 38-70):
```python
def test_fingerprint_has_dvd1_prefix(self, real_disc):
    assert real_disc.fingerprint.startswith("dvd1-"), ...

def test_fingerprint_is_hex_after_prefix(self, real_disc):
    _, hex_part = real_disc.fingerprint.split("-", 1)
    assert re.fullmatch(r"[0-9a-f]+", hex_part), ...

def test_fingerprint_deterministic(self, real_disc):
    """Parse the same disc again — fingerprint must match."""
    from ovid.disc import Disc
    disc2 = Disc.from_path(DISC_PATH)
    assert disc2.fingerprint == real_disc.fingerprint

def test_canonical_string_starts_with_version(self, real_disc):
    assert real_disc.canonical_string.startswith("OVID-DVD-1|"), ...

def test_identity_selection_has_diagnostics(self, real_disc):
    assert real_disc._identity_set is not None
    assert real_disc._identity_set.diagnostics
```
BD equivalents: assert `bd2-`/`uhd2-` prefix on primary, hex-after-prefix, re-parse determinism (`test_fingerprint_deterministic`), canonical string starts with `bd2_spec.OVID_BD2_VERSION`, and `bd_disc.identity.diagnostics` is non-empty (D-04's diagnostic requirement). Add a cross-drive variant per D-12/D-13 if a second path env var is available — this is the FPRINT-05 "≥2 drives" proof this file is responsible for.

---

### `ovid-client/tests/test_bd_fingerprint_pinned.py` (new) — anti-tautology golden test

**Analog:** no direct pinned-hash test exists in-tree yet; nearest structural precedent is `test_disc_identity.py`'s plain `assert x == "literal"` style (e.g. `test_ovid_dvd1_identity_uses_existing_fingerprint_format`) plus the CONTEXT.md-referenced Phase 1 D-14 anti-tautology convention (hardcode the expected value independent of the fixture builder — do not compute expected inline from the same code under test).

**Pattern to follow (RESEARCH.md Pattern 4, concrete draft)**:
```python
def test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture():
    """Pin the exact fingerprint for a known obfuscated fixture tree.
    If this fails after an intentional bd2_spec.py change, the version
    literal (bd2_spec.OVID_BD2_VERSION) MUST also change — see FPRINT-06."""
    playlists = build_heavily_obfuscated_fixture()  # conftest_bd.py, D-12
    canonical = build_bd_canonical_string(playlists, is_uhd=False)
    fp = compute_bd_structure_fingerprint(canonical, is_uhd=False)
    assert fp == "bd2-<hardcoded-40-char-hash-computed-at-implementation-time>"
```
Compute the hardcoded hash once at implementation time by running the fixture builder + hash function interactively, then paste the literal — never derive the expected value from a second call to the same function inside the test (that would be tautological, testing only "the function is idempotent," not "the function's output is what we intended").

---

### `ovid-client/tests/conftest_bd.py` — extend with obfuscated-tree generator

**Analog:** same file, `make_mpls_file()` (lines 238-313) — the single low-level builder new helpers must compose. Existing signature accepts `play_items: list[dict]` with keys `clip_id`, `in_time`, `out_time`, `audio_streams`, `subtitle_streams` (docstring lines 244-256) — a new `build_heavily_obfuscated_fixture()` should generate many `make_mpls_file(...)` calls (one per decoy `.mpls`) covering: (a) sub-60s decoys (`MIN_DURATION_SECONDS` filter), (b) a playlist whose play-items repeat one `clip_id` >2 times (`MAX_CLIP_REPEATS` filter), (c) 2+ playlists sharing an identical `(clip_id, in_time, out_time)` sequence but different filenames (dedup target), returned as `list[tuple[str, MplsPlaylist]]` matching `build_bd_canonical_string`'s existing input contract (parse each generated blob with `parse_mpls()` from `mpls_parser.py`, pairing with a synthetic filename string).

---

### `docs/fingerprint-spec.md` — add OVID-BD-2 section

**Analog:** same file's existing OVID-DVD-1 sections — `## Algorithm` (line 50) and especially `## Versioning` (lines 165-169):
```markdown
## Versioning

The algorithm version is embedded in the canonical string prefix (`OVID-DVD-1`). If the algorithm changes in a way that produces different fingerprints for the same disc, a new Fingerprint Version is defined.

`dvdread1-*` is the Fingerprint Version for libdvdread Disc ID values. It is not a replacement meaning for `dvd1-*`; the prefixes identify different Disc Identity Methods. Both versions can coexist through Lookup Aliases.
```
Add an `## OVID-BD-2 Fingerprint Algorithm Specification` section (before or after the DVD-1 section, or as a new top-level `##` heading following the same numbered `### Step N` structure seen at lines 50-99) with its own `### Versioning` subsection mirroring the wording above but naming `bd1-aacs-*`/`uhd1-aacs-*` as the Tier-1 alias method and stating that a `bd2_spec.py` constant change requires an `OVID_BD2_VERSION` bump minting a new prefix (e.g. `bd2v2-`), coexisting via aliases — never mutating `bd2-*` in place. RESEARCH.md's own draft (lines 410-449 of `04-RESEARCH.md`) is the ready-to-adapt content; use `docs/fingerprint-spec.md`'s existing heading levels/prose style, not the research doc's shorthand.

---

### `.github/workflows/ci.yml` — add macOS runner for BD determinism tests

**Analog:** `.github/workflows/release.yml` matrix pattern (lines 147-164):
```yaml
    strategy:
      matrix:
        include:
          - os: linux
            ...
          - os: linux
            ...
          - os: macos
            ...
            runner: macos-latest
            artifact: ovid-macos-arm64
```
And the current single-OS `ovid-client-tests` job to modify (`ci.yml` lines 10-28):
```yaml
  ovid-client-tests:
    name: ovid-client tests
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: ovid-client
    steps:
      - uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -e '.[dev]'

      - name: Run tests
        run: python -m pytest tests/ -v --tb=short
```
Add a `strategy: matrix: os: [ubuntu-latest, macos-latest]` and change `runs-on: ubuntu-latest` to `runs-on: ${{ matrix.os }}` — the minimal, proven-working change since `release.yml` already demonstrates `macos-latest` is available/affordable in this repo's Actions plan (confirmed by RESEARCH.md D-14/Environment Availability). No new secrets/setup steps needed; `actions/setup-python@v6` and `pip install -e '.[dev]'` both work cross-platform already (Python + pip, no native compiled deps in `ovid-client`).

---

## Shared Patterns

### DiscIdentity / DiscIdentitySet value objects (format-neutral, reuse verbatim)
**Source:** `ovid-client/src/ovid/disc_identity.py` lines 18-41
**Apply to:** `identify_bd()`, `bd_disc.py`, `test_bd_identity.py`, `test_bd_real_disc.py` — no BD-specific subclass; the dataclasses are already format-neutral (`method`/`fingerprint_version` are plain strings).

### "Always-primary, opportunistic-alias, one-diagnostic-per-branch" identity resolution
**Source:** `ovid-client/src/ovid/disc_identity.py::identify_dvd` (lines 65-98)
**Apply to:** `identify_bd()` — never a bare `return` on Tier-1 success; every branch (success, missing dir, missing file, invalid data, hash exception) appends exactly one `DiscIdentityDiagnostic`.

### Dependency-injected external read for testability
**Source:** `identify_dvd(..., read_libdvdread_disc_id: Callable[[str], str] = read_libdvdread_disc_id)` (line 69)
**Apply to:** `identify_bd()`'s AACS-reading step — accept a reader object or callable with a default bound to the real implementation, so `test_bd_identity.py` can inject fakes without touching the filesystem (matches `test_identify_dvd_falls_back_when_libdvdread_is_unavailable`'s style).

### Cross-platform IO-failure test convention (fs monkeypatch, not chmod)
**Source:** CLAUDE.md project convention (not an in-repo Python file, but a locked repo-wide rule) — "inject deterministically by monkeypatching the `fs`/file-read method: save original, override to throw, assert, restore in `finally`."
**Apply to:** any new BD reader failure-path test in `test_bd_identity.py`/`test_bd_fingerprint.py` that needs to simulate an unreadable `Unit_Key_RO.inf` or malformed MPLS file — monkeypatch `BDFolderReader.read_aacs_file`/`read_mpls` (or the underlying `open`/`os.path` calls) rather than `chmod 0o000`.

### `real_disc` hardware-gated fixture tier (never committed)
**Source:** `ovid-client/tests/test_real_disc.py` lines 1-23 (env var + `pytestmark` gating) and CONTEXT.md D-11/D-12
**Apply to:** `test_bd_real_disc.py` — identical gating shape; raw `Unit_Key_RO.inf` bytes must never be written to any committed fixture file, only the derived `bd1-aacs-*` string may appear in test assertions.

### Anti-tautology golden/pinned fixture assertions
**Source:** Phase 1 D-14 convention (referenced in CONTEXT.md/RESEARCH.md, no single file — applies across `test_bd_fingerprint_pinned.py`)
**Apply to:** any hardcoded-expected-hash test — the expected value must be a literal string pasted from a one-time run, never re-derived by calling the function under test a second time inside the assertion.

### Deterministic explicit sort (never rely on filesystem/OS ordering)
**Source:** `ovid-client/src/ovid/readers/bd_folder.py` `list_mpls_files()` (confirmed via RESEARCH.md "Don't Hand-Roll" table — already calls `sorted(os.listdir(...))`) and `bd_fingerprint.py`'s existing `filtered.sort(key=...)` (line 101, being replaced but the "always explicit `.sort()`, never raw iteration order" convention stays)
**Apply to:** `bd2_spec.py`-driven tie-break replacement in `build_bd_canonical_string()` — the new `sorted()`/`.sort()` key must remain pure `str`/`int`/`float` tuple comparison, no `locale` module, per RESEARCH.md Pitfall 5.

## No Analog Found

None — every file in this phase's scope has at least a role-match analog already in the tree (this is the expected shape of a hardening phase per RESEARCH.md's framing).

## Metadata

**Analog search scope:** `ovid-client/src/ovid/` (disc_identity.py, bd_disc.py, bd_fingerprint.py, mpls_parser.py, dvdread_adapter.py references), `ovid-client/tests/` (test_disc_identity.py, test_real_disc.py, conftest_bd.py, test_bd_fingerprint.py), `docs/fingerprint-spec.md`, `.github/workflows/` (ci.yml, release.yml)
**Files scanned:** 10 read directly + 2 grepped for signatures (mpls_parser.py PlayItem fields, test_disc_identity.py test names)
**Pattern extraction date:** 2026-07-06
