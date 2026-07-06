# Phase 4: Blu-ray/UHD Fingerprinting - Research

**Researched:** 2026-07-06
**Domain:** Blu-ray/UHD disc structural fingerprinting, AACS Disc ID extraction, MPLS/CLPI binary parsing, cross-platform determinism, anti-obfuscation playlist selection
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**A. Alias-pair construction & primary tier (FPRINT-03)**
- **D-01 (PRIMARY = Tier 2 structural):** `bd2-*`/`uhd2-*` (the always-computable structural hash) is the **fixed primary** of the alias pair; `bd1-aacs-*`/`uhd1-aacs-*` is attached as an **alias** whenever the AACS directory is readable. This exactly mirrors `identify_dvd()` making `dvd1-*` (structural, always-computable) primary over `dvdread1-*`. Rejected: Tier-1-primary-when-present (heterogeneous primary type forces every consumer to branch on `fingerprint_version`; AACS-stripped/ripped folders silently flip to structural anyway).
- **D-02 (stop the short-circuit):** Today `BDDisc.from_path()` returns Tier 1 **alone** when AACS is present. Replace with an `identify_bd()` that **unconditionally** builds the Tier-2 identity as primary, then **opportunistically** attempts Tier 1 and appends it to `aliases`. Both tiers always computed and returned together whenever both available.
- **D-03 (one-tier fallback is free):** No AACS directory → `DiscIdentitySet(primary=bd2_identity, aliases=[])`. `aliases` already defaults to empty. `resolve_existing_disc_for_identities` (API side) already matches a submission against any known identity — gives alias-pair convergence for free.
- **D-04 (shape):** `identify_bd(...) -> DiscIdentitySet` mirrors `identify_dvd()`. `BDDisc` stops exposing a single fingerprint and instead delegates to `identify_bd()`, exposing the full `DiscIdentitySet` (e.g. `.identity`); keep `.fingerprint`/`.tier` as thin proxies to `.identity.primary` for CLI/back-compat callers. Attach a diagnostic (e.g. `no_aacs_directory`, `aacs_unit_key_missing`, `aacs_fingerprint_failed`) when Tier 1 is unavailable, for observability.
- **D-05 (format on the disc record, FPRINT-04):** `format_type` (`"bluray"`/`"uhd"`) already derived from MPLS header `"0300"` heuristic; must carry through to the disc record. Planner: confirm submission payload / API disc row records `format` (ARM already reads a `format` field per Phase 2 D-10) and note the UHD header-version heuristic's limits.

**B. Tier-2 anti-obfuscation frozen ruleset (FPRINT-06 guardrail)**
- **D-06 (frozen ruleset content — LOCKED starting spec, OVID-BD-2 v1):**
  1. **Filter** — exclude playlists with `total_duration_seconds < MIN_DURATION_SECONDS` (freeze `60.0`, keep current value).
  2. **Filter** — exclude playlists where any single `clip_id` recurs in the play-items more than `MAX_CLIP_REPEATS` times (freeze `2`, mirrors libbluray `-r2`) — defeats loop-padded duration decoys.
  3. **Dedup** — group survivors by the full ordered tuple of `(clip_id, in_time, out_time)` across all play-items; emit **one** canonical block per equivalence class — defeats renumbered/duplicated decoy copies.
  4. **Sort/tie-break** — order survivors by `(-total_duration_seconds, clip_id_sequence_tuple)` where the tie-break is the full ordered `(clip_id, in_time, out_time)` tuple — **never filename**. Studios renumber `.mpls`; the current `filename ASC` tie-break is a genuine determinism/obfuscation hole. Dedup guarantees this is a true total order.
- **D-07 (freeze ENFORCEMENT — constants module + version tag + CI-pinned golden tests):** Move constants into a dedicated frozen module (e.g. `bd2_spec.py`), embed an explicit `OVID-BD-2` version literal in the canonical string, pin exact SHA-256 outputs against fixture discs in a determinism test. Any edit to a filter/sort/tie-break constant **fails CI** unless the developer also bumps the version literal — minting a new namespace (`bd2-` → e.g. `bd2v2-`) that coexists via the alias model. Rejected: review-discipline-only; auto-hash-of-constants version.
- **D-08 (no migration cost — freeze the improved ruleset NOW):** BD fingerprinting has **not shipped**; no `bd2-*` production data exists. The improved ruleset (D-06) can be frozen directly — current `filename ASC` implementation is pre-release and simply replaced, not migrated.

**C. Tier-1 AACS legal boundary (FPRINT-01)**
- **D-09 (keep `SHA-1(Unit_Key_RO.inf)` — legally clean):** Current Tier-1 source is unchanged. It is a plaintext UDF filesystem read + one-way hash — no descrambling, no drive-level handshake/SCSI passthrough, no secret AACS device keys. The wrapped CPS/Title-Key material is unusable without the Media Key Block + AACS-LA-licensed device keys OVID never holds; a one-way SHA-1 digest cannot be inverted. This **is** what the FOSS ecosystem (libaacs, MakeMKV `keydb.cfg`) calls the "AACS Disc ID."
- **D-10 (doc/wording fix):** Correct FPRINT-01 wording and code docstrings to state: **"AACS Disc ID" ≡ `SHA-1(AACS/Unit_Key_RO.inf)`**. Behavior-neutral, docs-only.
- **D-11 (raw file NEVER committed):** The raw `Unit_Key_RO.inf` must **never** be committed to the CC0 repo. Only the derived `bd1-aacs-*`/`uhd1-aacs-*` string is public. The raw file lives exclusively in the private, hardware-gated `real_disc` fixture tier (never in git). Rejected: AACS Volume ID as Tier-1 source (needs low-level vendor drive commands — circumvention-adjacent); dropping AACS/Tier 1 (fails FPRINT-01).

**D. Fixture corpus & cross-platform determinism (FPRINT-05, FPRINT-07)**
- **D-12 (HYBRID strategy):** Two-tier fixtures matching existing DVD `real_disc` convention:
  - **Committed / public / CI-enforced (synthetic):** Extend `conftest_bd.py` to synthesize a heavily-obfuscated BDMV tree (100+ decoy playlists, duplicated main-feature playlists with shuffled clip order, loop-padded short-clip decoys) — a stronger FPRINT-06 stress test than any real disc, zero legal ambiguity. Add the missing `BDDisc.from_path()` end-to-end test on synthetic fixtures. Run on Linux + macOS CI.
  - **Private / `real_disc`-gated (never committed):** New `test_bd_real_disc.py` mirroring `test_real_disc.py` — env-var gated (`pytest.mark.real_disc`, `OVID_TEST_DISC_PATH` + a second-drive path), asserting `BDDisc.from_path()` yields an identical fingerprint across drives/OSes. Never commits captured bytes.
- **D-13 (how FPRINT-05's "≥2 drives + Linux+macOS" is proven):** OS-determinism → CI runs synthetic fixtures on both Linux and macOS runners (deterministic, hardware-free). Drive-independence → a documented manual multi-drive run folded into the release checklist. Rejected: synthetic-only (leaves "≥2 drives" unproven on paper); committing a real-disc metadata extract publicly (unresolved copyright, near the "no disc images" constraint).
- **D-14 (⚠ PLANNER FLAG — macOS CI):** FPRINT-05 names macOS explicitly. The `ovid-client` CI matrix must actually include a macOS runner, or OS-determinism is only asserted on Linux and FPRINT-05 is half-met. **Confirmed gap this session:** `.github/workflows/ci.yml`'s `ovid-client-tests` job runs `ubuntu-latest` only, no OS matrix. `release.yml` *does* already use a `matrix.os` including `macos-latest` (CLI binary build job) — proving macOS runners are available/affordable in this repo's GitHub Actions plan, so extending `ci.yml` with the same runner for BD determinism tests is a known-working pattern, not a new capability.

### Claude's Discretion
- Exact `identify_bd()` signature, where the Tier-1 diagnostic enum lives, and how `BDDisc` proxies `.fingerprint`/`.tier` to `.identity.primary` (within D-02/D-04).
- Naming of the frozen constants module and the version-literal encoding scheme (`bd2v2-` vs `OVID-BD-2.1` vs a numeric suffix) — the mechanism (embedded literal + CI pin + new-namespace-on-bump) is locked; the exact string form is the planner's (D-07).
- The precise synthetic-obfuscation fixture composition (how many decoys, which decoy classes) so long as it exercises all three D-06 defenses: min-duration filter, `MAX_CLIP_REPEATS` loop-pad filter, and clip-sequence dedup (D-12).
- Whether the pinned determinism test and the OVID-BD-2 golden fixtures are one file or split (D-07/D-12).

### Deferred Ideas (OUT OF SCOPE)
- **API-side BD dual-string submission / alias storage (IDENT-03)** — Phase 5. This phase makes the client emit the `DiscIdentitySet`; storing the non-primary BD strings as aliases on submission is ADR 0001 Phase 2 completion, owned by Phase 5.
- **Cross-table fingerprint-registry arbitration (WR-02)** — Phase 5.
- **Web-UI rendering of BD fingerprint aliases (WEBUI-02)** — Phase 7.
- **Bulk-seeding real BD/UHD entries (OPS-01/02)** — Phase 8.
- **matrix256 as a fifth alias fingerprint (MATRIX-01)** — v2 / deferred; spike-first, out of v0.2.0.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FPRINT-01 | `ovid-client` computes a Blu-ray Tier 1 fingerprint from the AACS Disc ID (`bd1-aacs-*`) | Already implemented (`compute_aacs_fingerprint`, `bd_fingerprint.py:35-43`); legal boundary confirmed (D-09/D-10) — see Security Domain and Common Pitfalls. Docstring/requirement wording fix is the only remaining work. |
| FPRINT-02 | `ovid-client` computes a Blu-ray Tier 2 fingerprint from BDMV/PLAYLIST/CLIP structure (`bd2-*`) | Already implemented (`build_bd_canonical_string` + `compute_bd_structure_fingerprint`); MPLS parser (`mpls_parser.py`) exposes `clip_id`/`in_time`/`out_time` needed for D-06's dedup/tie-break — confirmed present, no gap. |
| FPRINT-03 | Client returns both tiers as one `DiscIdentitySet` alias pair, no short-circuit | Gap confirmed: `BDDisc._build()` (`bd_disc.py:114-133`) returns Tier 1 alone via early `return` when AACS present. See Architecture Patterns → `identify_bd()` design, mirroring `identify_dvd()` in `disc_identity.py`. |
| FPRINT-04 | UHD discs fingerprinted via same tiered path, format recorded on disc record | UHD detection already implemented (`is_uhd` from header `"0300"`, `bd_disc.py:108-111`); API `format` column confirmed `String(10)` — `"Blu-ray"`/`"UHD"`/`"DVD"` all fit. See Common Pitfalls for the header-heuristic's known limits. |
| FPRINT-05 | Identical BD/UHD fingerprints across ≥2 drives + Linux/macOS (determinism test) | Gap confirmed: CI (`ci.yml`) has no macOS runner for `ovid-client-tests` (D-14). See Validation Architecture and Environment Availability. |
| FPRINT-06 [guardrail] | Tier 2 filter/sort constants frozen and versioned, not tuned | Gap confirmed: constants (`_MIN_DURATION_SECONDS`) live inline in `bd_fingerprint.py`, tie-break is `filename ASC` (obfuscation hole). See Architecture Patterns → frozen `bd2_spec.py` design. |
| FPRINT-07 | Real BD/UHD fixture corpus incl. ≥1 heavily-obfuscated disc backs regression suite | Gap confirmed: `conftest_bd.py` has basic single-playlist builders only, no obfuscated-tree generator, no `BDDisc.from_path()` E2E test, no `test_bd_real_disc.py`. See Architecture Patterns and Validation Architecture. |
| DOCS-01 | Fingerprint spec updated with OVID-BD-2 Tier 1 & Tier 2 | Gap confirmed: `docs/fingerprint-spec.md` lists BD/UHD prefixes as "planned v0.2.0" with no algorithm section. DVD-1's `Versioning` section is the structural precedent to mirror. See Code Examples → spec section draft. |
</phase_requirements>

## Summary

This is a hardening phase, not a greenfield build: both fingerprint algorithms already exist and are unit-tested in `ovid-client/src/ovid/bd_fingerprint.py` (Tier 1 SHA-1 of `Unit_Key_RO.inf`, Tier 2 SHA-256 of an `OVID-BD-2|...` canonical string). The actual work is four surgical changes, all already scoped by locked decisions in `04-CONTEXT.md`: (1) refactor `BDDisc.from_path()`'s Tier-1-short-circuit into an `identify_bd()` function that mirrors `disc_identity.py`'s existing `identify_dvd()` / `DiscIdentitySet` pattern exactly; (2) extract the Tier-2 filter/sort/tie-break constants into a frozen, versioned `bd2_spec.py` module and replace the `filename ASC` tie-break (a real obfuscation hole — filenames are renumbered by studios) with a `(clip_id, in_time, out_time)` sequence tie-break, matching libbluray's own `-r2 -d` decoy-defense flags (confirmed directly against `mpls_dump.c` source); (3) build a synthetic heavily-obfuscated BDMV fixture generator plus a pinned/golden determinism test, and add a macOS runner to CI (a real, confirmed gap — `ci.yml` currently only runs `ubuntu-latest`, while `release.yml` already proves macOS runners work in this repo's Actions plan); (4) write the `docs/fingerprint-spec.md` OVID-BD-2 section mirroring the existing DVD-1 spec's structure, especially its `Versioning` section.

The AACS legal boundary is well-established open-source practice, not novel legal territory: `SHA-1(AACS/Unit_Key_RO.inf)` is literally what MakeMKV's `keydb.cfg` ecosystem and libaacs call the "Disc ID" — a plaintext-file hash, not a decryption key, and not a circumvention act (the wrapped key material inside the file is inert without AACS-LA-licensed device keys and a Media Key Block that OVID never holds or downloads). No new external package is needed for this phase — the MPLS/AACS parsing is intentionally hand-rolled pure Python already in the codebase (avoiding GPL/native-binding entanglements from `libbluray`/`pyaacs`-style wrappers), and this phase should continue that pattern rather than introducing a dependency.

**Primary recommendation:** Refactor around the existing algorithms — do not rewrite `compute_aacs_fingerprint` or `compute_bd_structure_fingerprint`. Spend the phase's effort on `identify_bd()` (mirroring `identify_dvd()`), the frozen `bd2_spec.py` module with a `(clip_id, in_time, out_time)` tie-break, the synthetic obfuscated-fixture generator + pinned golden test, and the macOS CI runner — these four are the actual FPRINT-03/05/06/07 gaps.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| AACS Disc ID extraction (Tier 1) | Client (`ovid-client`) | — | Local filesystem read on the machine with the physical disc/drive; never touches the API until submission. |
| MPLS/CLPI structural parsing (Tier 2) | Client (`ovid-client`) | — | Same — structure exists only in local BDMV directory data. |
| Disc Identity selection / alias-pair construction | Client (`ovid-client`, `disc_identity.py`) | — | `DiscIdentitySet` is a pure client-side value object; API only *stores* the pair (Phase 5, IDENT-03), it does not compute it. |
| Format recording (`bluray`/`uhd`/`dvd`) on disc record | API / Backend (persistence) | Client (detection) | Client detects `format_type`; API's `Disc.format` column persists it — this phase's job is ensuring the client-detected value flows through the existing submission payload unchanged. |
| Fixture corpus (synthetic + real_disc-gated) | Test / Build tooling | Client (consumed by tests) | Fixtures are test-only artifacts; synthetic ones ship in git, real ones are hardware-gated and never committed — this is a test-infrastructure concern, not a runtime one. |
| Cross-platform determinism (Linux/macOS) | CI / Build pipeline | Client (algorithm correctness) | The algorithm must already be OS-independent (pure Python, no locale/float/path-order dependencies); CI's job is *proving* it via a real macOS runner, which is the confirmed gap (D-14). |
| Fingerprint spec documentation | Docs / Static content | — | `docs/fingerprint-spec.md` is a versioned public artifact (CC0), not code — it is the authoritative external contract for the algorithm. |

## Standard Stack

### Core

No new runtime dependencies are required. This phase extends existing hand-rolled modules only.

| Module | Status | Purpose |
|--------|--------|---------|
| `ovid.bd_fingerprint` | Existing — refactor around | Tier 1/2 hash algorithms (keep hash logic, extract constants) |
| `ovid.bd_disc` (`BDDisc`) | Existing — refactor | Remove short-circuit, delegate to new `identify_bd()`, add back-compat proxies |
| `ovid.disc_identity` | Existing — extend | Add `identify_bd()` alongside existing `identify_dvd()` |
| `ovid.mpls_parser` | Existing — no change needed | Already exposes `clip_id`, `in_time`, `out_time` per play item — confirmed sufficient for D-06's dedup/tie-break |
| `ovid.readers.bd_folder` (`BDFolderReader`) | Existing — no change needed | AACS + MPLS file I/O already implemented and tested |

### Supporting

No supporting libraries are added. `hashlib` (stdlib) is already used for SHA-1/SHA-256.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled pure-Python MPLS parser (existing) | `libbluray` Python bindings (`python-libbluray` or ctypes wrapper) | Native dependency, packaging complexity across Linux/macOS/Windows, GPL-2.0 licensing entanglement (libbluray is LGPL-2.1, its `bdplus`/`bdj` companions are more restrictive) for a CC0 project; the existing parser already covers the structural fields OVID needs (play items, streams, chapter marks) with zero native deps. **Verdict: keep hand-rolled.** |
| Reading `Unit_Key_RO.inf` directly via filesystem | `libaacs`/MakeMKV native AACS libraries | Those libraries exist to *decrypt* (need device keys, MKB processing) — using them to merely read one file would pull in a decryption-capable dependency for a read-only-identifier need. Direct file read matches D-09's legal boundary better and needs zero external deps. |

**Installation:** No new packages — nothing to install.

**Version verification:** N/A (no new packages).

## Package Legitimacy Audit

**Not applicable — this phase installs no new external packages.** All work extends existing hand-rolled modules in `ovid-client/src/ovid/` using only the Python standard library (`hashlib`, `struct`, `dataclasses`). If a planner considers adding any BD/AACS-related third-party package during planning, it MUST be run through the Package Legitimacy Gate before inclusion — but no such package is recommended by this research.

## Architecture Patterns

### System Architecture Diagram

```text
                    ┌─────────────────────────────────────────┐
                    │   BDDisc.from_path(path)                 │
                    │   (entry point, ovid-client)             │
                    └───────────────────┬───────────────────────┘
                                        │
                      ┌─────────────────▼─────────────────┐
                      │  BDFolderReader                     │
                      │  - list_mpls_files() → sorted list  │
                      │  - read_mpls(name) → bytes          │
                      │  - has_aacs() / read_aacs_file()    │
                      └───────────┬─────────────┬───────────┘
                                  │             │
                    ┌─────────────▼───┐   ┌─────▼──────────────┐
                    │ parse_mpls(data) │   │ has_aacs() +        │
                    │ (mpls_parser.py) │   │ read Unit_Key_RO.inf│
                    │ → MplsPlaylist   │   │ (I/O only, no crypto)│
                    └─────────┬────────┘   └─────┬──────────────┘
                              │                  │
                              ▼                  ▼
                 ┌─────────────────────┐  ┌────────────────────────┐
                 │ identify_bd(...)     │  │ compute_aacs_fingerprint│
                 │ (NEW — disc_identity │◄─┤ (SHA-1, existing)       │
                 │  .py, mirrors        │  └────────────────────────┘
                 │  identify_dvd)       │
                 │                      │
                 │  1. ALWAYS build     │  ┌────────────────────────┐
                 │     Tier-2 primary   │◄─┤ build_bd_canonical_string│
                 │     via bd2_spec.py  │  │ (uses frozen bd2_spec.py│
                 │     frozen filters   │  │  constants — NEW module)│
                 │  2. OPPORTUNISTICALLY│  └────────────────────────┘
                 │     attempt Tier-1,  │
                 │     append as alias  │
                 │  3. Never short-     │
                 │     circuits         │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌─────────────────────────┐
                 │ DiscIdentitySet          │
                 │  primary = bd2-*/uhd2-*  │
                 │  aliases = [bd1-aacs-*]  │
                 │            (if present)  │
                 └──────────┬───────────────┘
                            │
              ┌─────────────┴──────────────┐
              ▼                             ▼
    BDDisc.identity (new)          BDDisc.fingerprint/.tier
    exposes full pair              (back-compat proxies →
    for CLI submit payload          .identity.primary)
              │
              ▼
    build_submit_payload(...) → client.submit()
    (API-side alias storage is Phase 5 / IDENT-03 — OUT OF SCOPE here)
```

### Recommended Project Structure

No new top-level directories. New/changed files within existing `ovid-client/src/ovid/`:

```
ovid-client/src/ovid/
├── bd_fingerprint.py       # keep hash functions; REMOVE inline _MIN_DURATION_SECONDS
├── bd2_spec.py             # NEW — frozen constants + version literal (FPRINT-06/D-07)
├── bd_disc.py              # MODIFY — remove short-circuit, delegate to identify_bd()
├── disc_identity.py        # MODIFY — add identify_bd() alongside identify_dvd()
├── mpls_parser.py          # unchanged — already exposes needed fields
└── readers/bd_folder.py    # unchanged

ovid-client/tests/
├── conftest_bd.py                  # EXTEND — obfuscated-tree generator
├── test_bd_fingerprint.py          # EXTEND — BDDisc.from_path() E2E tests
├── test_bd_fingerprint_pinned.py   # NEW — golden/pinned determinism tests (D-07)
├── test_bd_identity.py             # NEW — identify_bd() unit tests (mirrors test_disc_identity.py)
└── test_bd_real_disc.py            # NEW — real_disc-gated cross-drive/OS test (D-12/D-13)
```

### Pattern 1: `identify_bd()` mirroring `identify_dvd()`

**What:** A pure function `identify_bd(path, playlists, is_uhd, *, read_aacs=...) -> DiscIdentitySet` that always builds Tier-2 as primary and opportunistically attaches Tier-1 as an alias with a diagnostic on every path (success or failure reason).

**When to use:** This is the FPRINT-03 gap-closing seam. Called from `BDDisc._build()` instead of the current `_try_aacs_tier1()`-then-return-early logic.

**Example (based on the existing `identify_dvd` pattern, `disc_identity.py:65-98`):**
```python
# Source: pattern mirrors ovid-client/src/ovid/disc_identity.py identify_dvd()
OVID_BD2_METHOD = "ovid-bd-2"
AACS_METHOD = "aacs-disc-id"

def ovid_bd2_identity(canonical: str, is_uhd: bool) -> DiscIdentity:
    version = "uhd2" if is_uhd else "bd2"
    return DiscIdentity(
        fingerprint=compute_bd_structure_fingerprint(canonical, is_uhd),
        method=OVID_BD2_METHOD,
        fingerprint_version=version,
    )

def aacs_identity(unit_key_data: bytes, is_uhd: bool) -> DiscIdentity:
    version = "uhd1-aacs" if is_uhd else "bd1-aacs"
    return DiscIdentity(
        fingerprint=compute_aacs_fingerprint(unit_key_data, is_uhd),
        method=AACS_METHOD,
        fingerprint_version=version,
    )

def identify_bd(
    canonical: str,
    is_uhd: bool,
    *,
    reader: "BDFolderReader",
) -> DiscIdentitySet:
    """Identify a BD/UHD disc: Tier-2 structure is ALWAYS primary;
    Tier-1 AACS is attached as an alias whenever readable (FPRINT-03:
    never short-circuit on Tier-1 success)."""
    primary = ovid_bd2_identity(canonical, is_uhd)
    aliases: list[DiscIdentity] = []
    diagnostics: list[DiscIdentityDiagnostic] = []

    if not reader.has_aacs():
        diagnostics.append(DiscIdentityDiagnostic(code="no_aacs_directory"))
        return DiscIdentitySet(primary=primary, aliases=aliases, diagnostics=diagnostics)

    unit_key_data = reader.read_aacs_file("Unit_Key_RO.inf")
    if unit_key_data is None or len(unit_key_data) == 0:
        diagnostics.append(DiscIdentityDiagnostic(code="aacs_unit_key_missing"))
        return DiscIdentitySet(primary=primary, aliases=aliases, diagnostics=diagnostics)

    try:
        aliases.append(aacs_identity(unit_key_data, is_uhd))
        diagnostics.append(DiscIdentityDiagnostic(code="aacs_disc_id_available"))
    except Exception as exc:
        diagnostics.append(DiscIdentityDiagnostic(code="aacs_fingerprint_failed", message=str(exc)))

    return DiscIdentitySet(primary=primary, aliases=aliases, diagnostics=diagnostics)
```

### Pattern 2: Frozen constants module with embedded version literal (FPRINT-06/D-07)

**What:** `bd2_spec.py` holds `MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS`, and the version literal as the single source of truth; `build_bd_canonical_string` imports from it rather than defining inline constants.

**When to use:** Any change to filter/sort/tie-break behavior. A reviewer diffing this file sees an intentional, isolated change; CI's pinned golden test (Pattern 4) fails if the literal isn't bumped alongside a constant change.

```python
# Source: locked by CONTEXT.md D-06/D-07 — new file, ovid-client/src/ovid/bd2_spec.py
"""OVID-BD-2 frozen Tier-2 filter/sort/tie-break spec.

Any edit to a constant in this module WITHOUT bumping OVID_BD2_VERSION
mints silently-different fingerprints for the same disc — this is
exactly the studio-obfuscation defense FPRINT-06 exists to prevent from
happening to us. Bump the version literal below whenever any constant
changes; a new literal mints a new namespace via the alias model rather
than corrupting existing bd2-* values (see docs/fingerprint-spec.md
Versioning section).
"""

OVID_BD2_VERSION = "OVID-BD-2"  # embedded in the canonical string, first field

# Filter 1: exclude playlists shorter than this (menus/previews)
MIN_DURATION_SECONDS = 60.0

# Filter 2: exclude playlists where any clip_id appears more than this many
# times across play-items (loop-padded duration decoys). Mirrors libbluray's
# mpls_dump -r2 flag (verified against libbluray source, see Sources).
MAX_CLIP_REPEATS = 2
```

### Pattern 3: Clip-sequence dedup + tie-break (replaces `filename ASC`)

**What:** Group survivors by the ordered tuple of `(clip_id, in_time, out_time)` across all play-items in a playlist; keep one canonical representative per equivalence class; sort remaining playlists by `(-total_duration, clip_sequence_tuple)`.

**When to use:** Inside `build_bd_canonical_string`, replacing the current `filtered.sort(key=lambda x: (-x[2], x[0]))` (`bd_fingerprint.py:101`, sorts by filename — the obfuscation hole).

```python
# Source: pattern derived from libbluray mpls_dump.c _filter_dup()/_filter_repeats()
# (verified against github.com/xbmc/libbluray source, see Sources)
def _clip_sequence(playlist: MplsPlaylist) -> tuple:
    return tuple((pi.clip_id, pi.in_time, pi.out_time) for pi in playlist.play_items)

def _clip_repeat_count(playlist: MplsPlaylist) -> int:
    from collections import Counter
    counts = Counter(pi.clip_id for pi in playlist.play_items)
    return max(counts.values()) if counts else 0

# Filter 2 (MAX_CLIP_REPEATS):
filtered = [
    (fname, pl, dur) for fname, pl, dur in filtered
    if _clip_repeat_count(pl) <= MAX_CLIP_REPEATS
]

# Dedup (one block per equivalence class):
seen_sequences: dict[tuple, tuple[str, MplsPlaylist, float]] = {}
for fname, pl, dur in filtered:
    seq = _clip_sequence(pl)
    if seq not in seen_sequences:
        seen_sequences[seq] = (fname, pl, dur)
deduped = list(seen_sequences.values())

# Sort/tie-break — NEVER filename:
deduped.sort(key=lambda x: (-x[2], _clip_sequence(x[1])))
```

### Pattern 4: Pinned/golden determinism test (anti-tautology, per Phase 1 D-14 precedent)

**What:** Assert an exact expected SHA-256 hash value hardcoded independently of the fixture builder — not merely "same input twice → same output" (that's already covered by `test_determinism_across_calls`, which is tautological about *why* it's stable, not *what* the value is).

```python
# Source: pattern mirrors ovid-client/tests/test_disc_identity.py (DVD identity tests)
# and Phase 1 D-14's anti-tautology golden-fixture convention.
def test_ovid_bd2_v1_pinned_hash_for_obfuscated_fixture():
    """Pin the exact fingerprint for a known obfuscated fixture tree.
    If this fails after an intentional bd2_spec.py change, the version
    literal (bd2_spec.OVID_BD2_VERSION) MUST also change — see FPRINT-06."""
    playlists = build_heavily_obfuscated_fixture()  # conftest_bd.py, D-12
    canonical = build_bd_canonical_string(playlists, is_uhd=False)
    fp = compute_bd_structure_fingerprint(canonical, is_uhd=False)
    # Hardcoded expected value — computed once, reviewed, then frozen.
    assert fp == "bd2-<hardcoded-40-char-hash-computed-at-implementation-time>"
```

### Anti-Patterns to Avoid
- **Tuning `MIN_DURATION_SECONDS`/`MAX_CLIP_REPEATS` as "just a constant edit":** Any edit without a version bump silently changes fingerprints for all future submissions of the same disc, exactly the drift FPRINT-06 guards against. Every edit to `bd2_spec.py` must be paired with a version-literal bump and CI's pinned test will catch an unpaired change.
- **Sorting/tie-breaking by filename:** Studios renumber `.mpls` files across pressings/reissues (confirmed obfuscation pattern — see Common Pitfalls). Filename is never a safe tie-break for identity purposes.
- **Short-circuiting on Tier-1 success:** Defeats FPRINT-03 outright and produces heterogeneous primary types across discs, forcing every downstream consumer (ARM, web UI, dedup) to branch on `fingerprint_version`.
- **Reaching for a native `libbluray`/AACS decryption library "just to read one file":** Pulls in a decryption-capable dependency and licensing complexity for a read-only-identifier need; violates the project's DRM-circumvention-adjacent non-goal even if the specific call used is benign.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHA-1/SHA-256 hashing | Custom hash implementation | `hashlib` (stdlib, already used) | Already correct; no change needed. |
| Cross-platform deterministic file listing | Custom directory-walk with OS-specific ordering assumptions | `sorted(os.listdir(...))` (already done in `BDFolderReader.list_mpls_files()`) | `os.listdir()` order is explicitly unspecified/arbitrary and varies across OSes and even across runs on the same OS — always sort explicitly (verified via general Python documentation/community consensus). `BDFolderReader` already does this correctly for MPLS files; `_find_aacs`/`_find_bdmv` iterate unsorted `os.listdir()` for exact-name matching only (not an ordering-sensitive result) — low risk, but worth a defensive note if multiple case-variant "AACS" directories could ever coexist (edge case, not currently exploitable). |

**Key insight:** This phase's "don't hand-roll" lesson is inverted from the usual case — the correct move is to **keep** the hand-rolled MPLS/AACS parsing (it already exists, is already tested, and avoids a native/GPL dependency), rather than reach for `libbluray` bindings. The real don't-hand-roll risk here is re-deriving the anti-obfuscation ruleset from scratch instead of directly mirroring libbluray's already-proven `-r2 -d` decoy defenses (verified against `mpls_dump.c` source, see Sources).

## Runtime State Inventory

This phase changes `BDDisc`'s public shape (single `.fingerprint`/`.tier` → `.identity` `DiscIdentitySet`, D-04) and the Tier-2 hash algorithm's tie-break rule (D-06). It is scoped as a refactor, so this inventory applies:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — per D-08, "BD fingerprinting has not shipped; there is no `bd2-*` production data to fragment." Confirmed: `docs/fingerprint-spec.md` lists BD prefixes as "planned v0.2.0" (not yet released), and `IDENT-03` (client submits BD strings to API for alias storage) is explicitly Phase 5, not yet built. No database migration needed. | None |
| Live service config | None — no external service (n8n, Datadog, etc.) references BD fingerprint values; this is a pure client-library algorithm change. | None |
| OS-registered state | None — no OS-level task/service registration involves BD fingerprint strings. | None |
| Secrets/env vars | None — no secret or env var name references the BD fingerprint algorithm or its constants. | None |
| Build artifacts / installed packages | `ovid-client` itself is versioned (`pyproject.toml` version `0.2.0`); no stale egg-info/binary artifacts carry the *old* `filename ASC` tie-break behavior baked in, since that behavior lives in source, not a built artifact. Any already-published `ovid` CLI wheel/binary predating this change simply becomes outdated — no data migration, just a version bump on next release. | Bump `ovid-client` version on release per normal practice; no special migration step. |

**Code-level back-compat requirement (not a runtime-state item, but load-bearing):** `BDDisc.fingerprint`/`.tier` are consumed today by `cli.py` (`disc.fingerprint`, `disc.tier`, `disc.format_type`) and `disc_structure.py`'s `normalize_bd_disc()` (`bd_disc.tier`, `bd_disc.playlists`, `bd_disc.format_type`, `bd_disc.fingerprint`). D-04's "thin proxies to `.identity.primary`" requirement exists specifically so these two call sites do not need to change when `BDDisc` gains `.identity`. Verify both continue to pass after the refactor.

## Common Pitfalls

### Pitfall 1: Filename as a tie-break is a real, exploited obfuscation vector
**What goes wrong:** Two structurally-different discs (or the same disc across pressings) can produce different fingerprints purely because `.mpls` files were renumbered, even though the actual playlist *content* (clip sequence) is identical — or worse, a genuine decoy playlist can be indistinguishable from the real feature by filename alone.
**Why it happens:** Studios ("ScreenPass" and similar schemes, ~2013+) deliberately create many `.mpls` files with near-identical durations and chapter counts, some non-functional decoys, specifically to defeat naive "find the main title" heuristics (confirmed via MakeMKV/Doom9/AVSForum community reporting cited in `04-CONTEXT.md`).
**How to avoid:** Tie-break on the full ordered `(clip_id, in_time, out_time)` tuple (Pattern 3), never on filename. This is what libbluray's own `-d` dedup flag does (verified against source).
**Warning signs:** A golden/pinned test starts failing intermittently across "the same disc" fixtures that only differ in which `.mpls` filename got the longer duration — that's the signal the tie-break isn't content-based.

### Pitfall 2: UHD detection via MPLS header `"0300"` is a heuristic, not an official spec check
**What goes wrong:** The BDA UHD Blu-ray specification is a licensed, non-public document; OVID cannot cite an official source confirming header version `"0300"` universally means UHD. Community sources (Kodi/libbluray forum reports) confirm UHD discs use `"0300"` in MPLS, `index.bdmv` (`INDX0300`), `MovieObject.bdmv` (`MOBJ0300`), and CLPI (`HDMV0300`) consistently, and that libbluray's own UHD support was added specifically to handle these version-3 extensions — but this is reverse-engineered community knowledge, not a licensed spec citation.
**Why it happens:** No public BDA spec access; all open-source BD tooling (libbluray, MakeMKV) works from reverse-engineered structure.
**How to avoid:** Document the heuristic explicitly in `docs/fingerprint-spec.md` as "detected via MPLS header version, following the same convention as libbluray" rather than presenting it as spec-guaranteed. This matches D-05's instruction to "document its limits."
**Warning signs:** A UHD disc misclassified as standard Blu-ray (or vice versa) in the fixture corpus — flag for a wider detection check (e.g., cross-referencing `index.bdmv`'s version too) if this happens with real fixtures.

### Pitfall 3: AACS Disc ID stability across regional reprints is unverified (already flagged in STATE.md)
**What goes wrong:** If a studio re-presses the same title for a different region and the `Unit_Key_RO.inf` differs (e.g., different Volume Unique Key wrapping per region), the same logical disc could produce a different `bd1-aacs-*` value across regions — which is fine for a Tier-1 *alias*, but would be surprising if assumed to be pressing-invariant.
**Why it happens:** AACS key material is provisioned per physical pressing/replication batch by design (that's what makes it useful for anti-piracy); OVID has not yet empirically validated same-title-different-region behavior against real fixtures.
**How to avoid:** This is explicitly why Tier-2 (structural) is the primary, not Tier-1 (D-01) — the alias model already absorbs this risk gracefully (different `bd1-aacs-*` values across regional variants become multiple aliases of possibly-different Tier-2 primaries, which is the *correct* outcome, not a bug). Document this as an open question (see below) and validate empirically once real fixtures across regions are available (FPRINT-07 is the vehicle for this validation, but full regional coverage across every locale is out of scope for this phase's fixture corpus).
**Warning signs:** N/A for this phase — flagged for OPS-01/02 bulk-seeding (Phase 8) to watch for.

### Pitfall 4: Breaking `.fingerprint`/`.tier` back-compat proxies silently
**What goes wrong:** `cli.py` and `disc_structure.py` both read `disc.fingerprint`, `disc.tier`, `disc.playlists`, `disc.format_type` directly on `BDDisc`. If `identify_bd()`'s refactor removes these fields entirely instead of proxying them to `.identity.primary`, both call sites break at runtime (not at typecheck time, since Python has no static enforcement here).
**Why it happens:** `@dataclass(frozen=True)` fields are easy to rename/remove without every call site being visible in one file.
**How to avoid:** Grep for `.fingerprint`, `.tier`, `.canonical_string` usage against `BDDisc` instances specifically (both call sites confirmed above) before finalizing the field list; add/keep them as computed `@property` proxies per D-04.
**Warning signs:** `cli.py`'s `fingerprint` command or `submit` wizard raising `AttributeError` on a Blu-ray path during manual testing.

### Pitfall 5: Locale-dependent string comparison creeping back in
**What goes wrong:** Python's default string comparison (`<`) for `str` is ordinal/codepoint-based and NOT locale-dependent by default — but if any future code path uses `locale.strxfrm` or `sorted(..., key=str.lower)` with locale-aware casing rules, sort order can silently differ between a machine with `LC_ALL=en_US.UTF-8` and one with `LC_ALL=C` or a different locale entirely, breaking FPRINT-05's cross-machine determinism guarantee.
**Why it happens:** Locale-aware sorting is the Python default in some environments/tools outside `sorted()`'s ordinal default, and can be introduced by contributors unfamiliar with the determinism requirement.
**How to avoid:** Keep all comparisons in `bd2_spec.py`/`build_bd_canonical_string` on raw `str`/`int`/`float` tuples via plain `sorted()`/`.sort()` — confirmed the current implementation and the proposed Pattern 3 replacement both do this correctly (no `locale` module usage anywhere in `bd_fingerprint.py`/`mpls_parser.py`).
**Warning signs:** Any `import locale` appearing in fingerprinting code paths — should never happen.

## Code Examples

### `docs/fingerprint-spec.md` OVID-BD-2 section draft shape (DOCS-01)

```markdown
# Source: mirrors the structure of the existing OVID-DVD-1 section in
# the same file (docs/fingerprint-spec.md), especially its Versioning section.

## OVID-BD-2 Fingerprint Algorithm Specification

**Version:** 1.0 (OVID-BD-2 v1)
**Status:** Final (v0.2.0)

### Overview
Two-tier fingerprinting for Blu-ray and 4K UHD discs:
- **Tier 1 (AACS Disc ID):** `bd1-aacs-*` / `uhd1-aacs-*` — SHA-1 of the raw
  `AACS/Unit_Key_RO.inf` bytes. This is the "AACS Disc ID" as commonly
  understood in the FOSS Blu-ray tooling ecosystem (libaacs, MakeMKV
  keydb.cfg) — a plaintext-file hash, not a decryption key, and readable
  without any DRM circumvention.
- **Tier 2 (BDMV structure):** `bd2-*` / `uhd2-*` — SHA-256[:40] of an
  `OVID-BD-2|...` canonical string built from filtered/deduped/sorted
  MPLS playlist structure. ALWAYS computable; the fixed primary of the
  alias pair.

### Alias-pair behavior
Both tiers are computed whenever possible and returned together as one
`DiscIdentitySet` — Tier-2 primary, Tier-1 (if available) as an alias.
Mirrors the `dvd1-*`/`dvdread1-*` alias-pair precedent (ADR 0001).

### Tier 2 Algorithm — frozen filter/sort/tie-break (OVID-BD-2 v1)
1. Filter: exclude playlists with total duration < 60.0 seconds.
2. Filter: exclude playlists where any clip_id repeats more than 2 times
   across play-items (defends against loop-padded duration decoys).
3. Dedup: group by ordered (clip_id, in_time, out_time) tuple; one block
   per equivalence class (defends against renumbered decoy copies).
4. Sort: by (-total_duration_seconds, clip_sequence_tuple) — NEVER filename.

### Versioning
[... mirror OVID-DVD-1's Versioning section: any change to filter/sort/
tie-break constants MUST bump the version literal, minting bd2v2-/uhd2v2-
as new Fingerprint Versions coexisting via aliases, never mutating bd2-*
in place.]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `BDDisc.from_path()` short-circuits: returns Tier 1 alone if AACS present, else Tier 2 | `identify_bd()` always computes Tier 2 as primary, opportunistically attaches Tier 1 as alias | This phase (FPRINT-03) | Every disc submission where AACS is readable now also contributes its structural identity, closing the "AACS-stripped rip silently becomes a different fingerprint namespace" gap |
| Tier-2 tie-break: `filename ASC` | Tie-break: `(clip_id, in_time, out_time)` sequence tuple, with content-based dedup first | This phase (FPRINT-06) | Removes a genuine obfuscation/determinism hole — studio-renumbered decoy playlists no longer influence which block "wins" the sort position |
| Tier-2 constants inline in `bd_fingerprint.py` (`_MIN_DURATION_SECONDS`) | Constants frozen in dedicated `bd2_spec.py` with embedded version literal, CI-pinned | This phase (FPRINT-06/D-07) | A future accidental or unreviewed constant tweak fails CI instead of silently fragmenting the fingerprint space |
| CI: `ubuntu-latest` only for `ovid-client-tests` | Planner must add `macos-latest` to the BD determinism test job | This phase (FPRINT-05/D-14) | FPRINT-05's cross-OS claim becomes provable in CI rather than asserted on paper |

**Deprecated/outdated:**
- Filename-based playlist tie-break: superseded by content-based `(clip_id, in_time, out_time)` tie-break — no longer meets the anti-obfuscation guardrail (FPRINT-06).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MPLS header version `"0300"` reliably indicates UHD across all real-world discs (no official BDA spec access to confirm exhaustively; based on community/libbluray reverse-engineering consensus) | Common Pitfalls (Pitfall 2), Phase Requirements (FPRINT-04) | A UHD disc misclassified as standard Blu-ray (or vice versa) on the `format` field — low likelihood given consistent community corroboration across `index.bdmv`/`MovieObject.bdmv`/CLPI, but not spec-certified. Mitigate by validating against real UHD fixtures in FPRINT-07's corpus and documenting the heuristic explicitly in the spec (per D-05). |
| A2 | AACS `Unit_Key_RO.inf` (and therefore `bd1-aacs-*`) is stable across drives reading the *same physical disc*, but may legitimately differ across regional reprints of the *same title* | Common Pitfalls (Pitfall 3), STATE.md Blockers | If assumed stable across regional reprints and it isn't, could cause confusing alias-pair fragmentation reports from contributors — mitigated already by Tier-2-primary design (D-01), but the assumption itself is unverified against real hardware this session. STATE.md already tracks this as an open blocker to validate empirically with real BD fixtures. |
| A3 | No new external package is needed; hand-rolled MPLS/AACS parsing should continue rather than adopting a `libbluray`-based dependency | Standard Stack, Don't Hand-Roll | If a future need arises for full BD-J/menu navigation (out of scope for fingerprinting), this assumption would need revisiting — but for structural fingerprinting alone, the existing implementation is sufficient and already tested. |

## Open Questions

1. **Does AACS Disc ID stability hold across all real-world regional reprints, or only within one region's pressing run?**
   - What we know: Tier-2 structural identity absorbs any Tier-1 instability gracefully via the alias model (D-01); community sources confirm the hash is disc-embodied, not drive-dependent.
   - What's unclear: Whether two regional editions of literally the same title/master ever share `Unit_Key_RO.inf` bytes, or always differ by design.
   - Recommendation: Treat as empirical — validate against whatever real fixtures land in the FPRINT-07 corpus; do not block this phase on resolving it, since the architecture already tolerates either outcome.

2. **Is a single macOS CI runner sufficient to prove "cross-platform" for FPRINT-05, or does Windows also need coverage eventually?**
   - What we know: FPRINT-05 explicitly names "Linux and macOS" only; `release.yml` already builds for macOS-arm64 specifically (no Windows CLI binary target currently listed in the reviewed matrix).
   - What's unclear: Whether a future milestone will expand the determinism claim to Windows.
   - Recommendation: Scope this phase strictly to Linux + macOS per the explicit requirement wording; do not add Windows CI as in-scope busywork.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| GitHub Actions `ubuntu-latest` runner | FPRINT-05 (Linux determinism) | ✓ | Already used in `ci.yml` | — |
| GitHub Actions `macos-latest` runner | FPRINT-05 (macOS determinism) | ✓ (proven via `release.yml`'s existing matrix) | Not yet wired into `ci.yml`'s `ovid-client-tests` job | Add the runner to `ci.yml`; no fallback needed — the capability already exists in this repo's Actions plan. |
| Real BD/UHD physical disc + drive | FPRINT-07's `real_disc`-gated cross-drive test (D-12/D-13) | ✗ (not available in CI; human-gated) | — | Synthetic obfuscated fixtures (committed, CI-enforced) cover the FPRINT-06 stress test in CI; the real-disc/multi-drive proof is a documented manual step in the release checklist per D-13 — not a CI blocker. |
| `pycdlib` / native BD parsing library | N/A — not needed | — | — | Hand-rolled MPLS/AACS parsing already in place; no dependency to verify. |

**Missing dependencies with no fallback:** None — the one "missing" item (macOS runner wiring) is a config change, not a missing capability.

**Missing dependencies with fallback:** Real BD/UHD hardware for the cross-drive determinism proof — synthetic CI fixtures + documented manual release-checklist step cover this per D-13 (locked decision, not this research's invention).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=7.0` (already configured, `ovid-client/pyproject.toml`) |
| Config file | `ovid-client/pyproject.toml` `[tool.pytest.ini_options]` — has `real_disc` marker registered already |
| Quick run command | `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py tests/test_bd_identity.py -v` |
| Full suite command | `cd ovid-client && python -m pytest tests/ -v --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FPRINT-01 | AACS Tier-1 fingerprint computed correctly, legal-boundary docstring updated | unit | `pytest tests/test_bd_fingerprint.py::TestAACSFingerprint -v` | ✅ (existing, already passing — docstring-only change here) |
| FPRINT-02 | Tier-2 structural fingerprint computed correctly | unit | `pytest tests/test_bd_fingerprint.py::TestBDCanonicalString tests/test_bd_fingerprint.py::TestBDStructureFingerprint -v` | ✅ (existing) |
| FPRINT-03 | Both tiers returned as one `DiscIdentitySet`, never short-circuited | unit | `pytest tests/test_bd_identity.py -v` | ❌ Wave 0 — new file mirroring `test_disc_identity.py` |
| FPRINT-04 | UHD format recorded, same tiered path used | unit + integration | `pytest tests/test_bd_fingerprint.py -k uhd -v` and `pytest tests/test_disc_structure.py -k bd -v` (if exists) | Partial — UHD prefix tests exist; format-on-record integration test likely needs Wave 0 addition |
| FPRINT-05 | Identical fingerprints across drives + Linux/macOS | regression + manual | `pytest tests/test_bd_fingerprint_pinned.py -v` (CI, both OS runners) + documented manual multi-drive step (release checklist) | ❌ Wave 0 — new pinned test file + CI matrix change + release checklist doc update |
| FPRINT-06 [guardrail] | Filter/sort/tie-break constants frozen, versioned, CI-pinned | regression | `pytest tests/test_bd_fingerprint_pinned.py -v` | ❌ Wave 0 — same new file as FPRINT-05 |
| FPRINT-07 | Fixture corpus incl. obfuscated disc backs regression suite | unit + real_disc-gated | `pytest tests/test_bd_fingerprint.py -k obfuscat -v` (synthetic, CI) + `OVID_TEST_DISC_PATH=... pytest tests/test_bd_real_disc.py -v -m real_disc` (manual, hardware-gated) | ❌ Wave 0 — obfuscated fixture generator in `conftest_bd.py` + new `test_bd_real_disc.py` |
| DOCS-01 | Spec updated with OVID-BD-2 | docs build | `mkdocs build --strict` (existing `docs-build` CI job already runs this) | ✅ (CI job exists; content is the Wave 0 gap, not tooling) |

### Sampling Rate
- **Per task commit:** `cd ovid-client && python -m pytest tests/test_bd_fingerprint.py tests/test_bd_identity.py -v`
- **Per wave merge:** `cd ovid-client && python -m pytest tests/ -v --tb=short` (full suite, both OS runners once CI matrix is updated)
- **Phase gate:** Full suite green (Linux + macOS) before `/gsd-verify-work`; `mkdocs build --strict` green for DOCS-01.

### Wave 0 Gaps
- [ ] `ovid-client/src/ovid/bd2_spec.py` — frozen constants module (FPRINT-06)
- [ ] `ovid-client/tests/test_bd_identity.py` — `identify_bd()` unit tests mirroring `test_disc_identity.py` (FPRINT-03)
- [ ] `ovid-client/tests/test_bd_fingerprint_pinned.py` — pinned/golden determinism tests (FPRINT-05/06)
- [ ] `ovid-client/tests/test_bd_real_disc.py` — `real_disc`-gated cross-drive test mirroring `test_real_disc.py` (FPRINT-05/07)
- [ ] `conftest_bd.py` extension — heavily-obfuscated BDMV tree generator (FPRINT-07)
- [ ] `.github/workflows/ci.yml` — add `macos-latest` to (or alongside) the `ovid-client-tests` job, at minimum for the new pinned/determinism tests (FPRINT-05/D-14)
- [ ] `docs/fingerprint-spec.md` — OVID-BD-2 section (DOCS-01)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | No | This phase is client-side parsing only; no auth surface touched. |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes | MPLS binary parsing must remain bounds-checked against truncated/malformed/adversarial input. `mpls_parser.py`'s `_safe_unpack()` (already implemented) raises a clear `ValueError` on truncation rather than reading out-of-bounds — confirmed present and must be preserved/extended for any new parsing logic (e.g., if CLPI parsing is added). |
| V6 Cryptography | Yes | SHA-1 and SHA-256 are used here purely as **content-identity digests**, never as a security/authentication boundary — this must stay explicit in code comments and the spec doc, since SHA-1's known collision weaknesses would matter if it were ever repurposed as an integrity/security control (it is not, and must not become one). Never hand-roll the hash — `hashlib` (stdlib) is already correctly used. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Malformed/truncated MPLS file causing parser crash or out-of-bounds read | Denial of Service | `_safe_unpack()` bounds-checks every multi-byte read and raises `ValueError` with a clear message rather than raising an unhandled `struct.error` or reading past the buffer — already implemented, must be preserved for any parser changes in this phase. |
| Adversarial "obfuscation playlist" input designed to defeat structural identity (studio decoy schemes) | Tampering (of the *identity signal*, not the bytes) | This is the actual threat model FPRINT-06's frozen ruleset defends against — filter by min-duration, filter by clip-repeat count, dedup by content sequence, tie-break by content not filename (Pattern 2/3 above). This is a novel-to-OVID threat class worth naming explicitly: the "attacker" is the disc's own authoring studio trying to defeat fingerprint-based identification/region-locking bypass detection tools, not a remote network attacker. |
| Committing raw AACS key-management file (`Unit_Key_RO.inf`) to a public CC0 repo | Information Disclosure | D-11 (locked): raw file never committed; only the derived one-way hash string is public. Enforced by fixture-tier discipline (`real_disc`-gated, never git-tracked) — same convention as existing DVD `real_disc` fixtures. |

## Sources

### Primary (HIGH confidence)
- Codebase read directly this session: `ovid-client/src/ovid/bd_fingerprint.py`, `bd_disc.py`, `disc_identity.py`, `mpls_parser.py`, `readers/bd_folder.py`, `disc_structure.py`, `cli.py`, `disc.py`; `api/app/disc_identity.py`, `api/app/models.py`, `api/app/schemas.py`; `docs/fingerprint-spec.md`; `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`; `.github/workflows/ci.yml`, `.github/workflows/release.yml`; `ovid-client/tests/conftest_bd.py`, `test_bd_fingerprint.py`, `test_real_disc.py`, `test_disc_identity.py`; `ovid-client/pyproject.toml`.
- [github.com/xbmc/libbluray — `src/devtools/mpls_dump.c`](https://raw.githubusercontent.com/xbmc/libbluray/master/src/devtools/mpls_dump.c) — fetched and quoted directly this session: confirms `-r <N>` (filter titles with >N repeating clips), `-d` (filter duplicate titles), `-s <seconds>` (filter short titles), `-f` (preset `-r2 -d -s900`). Directly verifies the D-06 anti-obfuscation ruleset's provenance claim.

### Secondary (MEDIUM confidence)
- MakeMKV community forum + ArchWiki (via WebSearch): confirms `Disc ID` = `SHA1(AACS/Unit_Key_RO.inf)`, and that the derived Disc ID is distinct from the VUK (Volume Unique Key, the actual decryption material stored separately) — corroborates D-09's legal-boundary claim from independent community sources, though not an official AACS-LA specification (which is not publicly available).
- Kodi/libbluray community forum reports (via WebSearch): UHD discs consistently use version-3 (`"0300"`) headers across MPLS, `index.bdmv`, `MovieObject.bdmv`, and CLPI files; libbluray's own UHD support was added specifically to handle these extensions — corroborates the existing `bd_disc.py` UHD-detection heuristic, though again not from a licensed BDA spec (see Assumptions Log A1).
- General Python documentation/community consensus (via WebSearch): `os.listdir()` order is unspecified/arbitrary and can vary across OSes and runs; `sorted()` must be used explicitly for deterministic enumeration — corroborates that `BDFolderReader.list_mpls_files()`'s existing `.sort()` call is necessary and correctly present.

### Tertiary (LOW confidence)
- None used without corroboration — all external claims in this document are backed by at least one WebSearch/WebFetch source cross-referenced against the existing, already-tested codebase behavior.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies; all recommendations extend existing, already-unit-tested modules whose behavior was read directly from source this session.
- Architecture: HIGH — the `identify_bd()`/`DiscIdentitySet` pattern is a direct mirror of the already-shipped `identify_dvd()` implementation (read directly, not inferred); the frozen-constants pattern is directly derived from libbluray's own verified source flags.
- Pitfalls: MEDIUM-HIGH — filename-tie-break, back-compat proxy, and locale pitfalls are HIGH confidence (verified directly against code + widely corroborated community sources); AACS regional-reprint stability and UHD-header-heuristic-reliability pitfalls are explicitly flagged LOW/unverified-empirically (matches the existing STATE.md blocker and Assumptions Log A1/A2) — these are known unknowns requiring real hardware, not gaps in this research.

**Research date:** 2026-07-06
**Valid until:** 30 days (stable domain — no fast-moving external API/library version dependencies; the frozen spec itself is explicitly designed not to churn)
</content>
