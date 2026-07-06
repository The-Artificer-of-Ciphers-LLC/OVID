# Phase 4: Blu-ray/UHD Fingerprinting - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Bring Blu-ray and 4K UHD discs to **fingerprinting parity with the DVD path** — Tier 1 (AACS Disc ID, `bd1-aacs-*`/`uhd1-aacs-*`) and Tier 2 (BDMV/PLAYLIST/CLIP structure, `bd2-*`/`uhd2-*`), returned together as an **alias pair**, backed by a real fixture corpus and a versioned, frozen fingerprint spec.

**Requirements:** FPRINT-01, FPRINT-02, FPRINT-03, FPRINT-04, FPRINT-05, FPRINT-06 [guardrail], FPRINT-07, DOCS-01.

**Independent of the DVD migration** — a separate fingerprint namespace from `dvd1-*`/`dvdread1-*`; parallel-safe (ROADMAP Wave A). No dependency on Phases 1/2/3/5.

**Critical scouting finding — this is a HARDENING phase, not greenfield.** Both tier algorithms already exist and are unit-tested:
- `compute_aacs_fingerprint()` — SHA-1 of raw `Unit_Key_RO.inf`, prefix `bd1-aacs-`/`uhd1-aacs-` (`bd_fingerprint.py`).
- `build_bd_canonical_string()` + `compute_bd_structure_fingerprint()` — SHA-256[:40] of an `OVID-BD-2|…` canonical string, prefix `bd2-`/`uhd2-` (`bd_fingerprint.py`).
- UHD detected from MPLS header version `"0300"` → `format_type` (`"uhd"`/`"bluray"`) on `BDDisc` (`bd_disc.py`).
- Synthetic MPLS fixture builders + component tests (`conftest_bd.py`, `test_bd_fingerprint.py`).

The real work is the four gaps below — the alias-pair refactor (FPRINT-03), freezing the Tier-2 ruleset (FPRINT-06), the fixture corpus + determinism proof (FPRINT-05/07), and the spec doc (DOCS-01) — NOT re-implementing the hashes.

**Out of scope (owned elsewhere):**
- BD identity-string **submission/alias storage on the API side** — the client emits the pair here; API-side dual-string submission is ADR 0001 Phase 2 / **Phase 5 (IDENT-03)**. This phase makes the client *produce* the `DiscIdentitySet`; it does not change the submission wire path.
- `dvdread1-*` promotion, cross-table fingerprint arbitration (WR-02) → **Phase 5**.
- Web-UI rendering of BD aliases → **Phase 7 (WEBUI-02)**.
- Bulk-seeding real BD/UHD entries → **Phase 8 (OPS-01/02)**.
</domain>

<decisions>
## Implementation Decisions

### A. Alias-pair construction & primary tier (FPRINT-03)
- **D-01 (PRIMARY = Tier 2 structural):** `bd2-*`/`uhd2-*` (the always-computable structural hash) is the **fixed primary** of the alias pair; `bd1-aacs-*`/`uhd1-aacs-*` is attached as an **alias** whenever the AACS directory is readable. This exactly mirrors `identify_dvd()` making `dvd1-*` (structural, always-computable) primary over `dvdread1-*`, and honors ADR 0001's philosophy of not promoting the stronger-but-conditional identity to primary until a promotion is deliberately staged. Rejected: Tier-1-primary-when-present (heterogeneous primary type forces every consumer — ARM, web UI, dedup — to branch on `fingerprint_version`; and AACS-stripped/ripped folders, an increasingly common input, silently flip to structural anyway).
- **D-02 (stop the short-circuit):** Today `BDDisc.from_path()` returns Tier 1 **alone** when AACS is present. Replace with an `identify_bd()` that **unconditionally** builds the Tier-2 identity as primary, then **opportunistically** attempts Tier 1 and appends it to `aliases`. Both tiers are always computed and returned together whenever both are available (satisfies FPRINT-03's "do not short-circuit on Tier 1 success").
- **D-03 (one-tier fallback is free):** No AACS directory → `DiscIdentitySet(primary=bd2_identity, aliases=[])`. The existing `DiscIdentitySet` dataclass already defaults `aliases` to empty — no special-casing. Convergence is already solved: `resolve_existing_disc_for_identities` matches a submission against **any** known identity, so a later contributor who reads the same physical pressing **with** AACS present attaches `bd1-aacs-*` as a new alias onto the record originally keyed by `bd2-*` alone (and the reverse order converges identically, since the pair is always submitted together when computable). No identity split.
- **D-04 (shape):** `identify_bd(...) -> DiscIdentitySet` mirrors `identify_dvd()`. `BDDisc` stops exposing a single fingerprint and instead delegates to `identify_bd()`, exposing the full `DiscIdentitySet` (e.g. `.identity`); keep `.fingerprint`/`.tier` as thin proxies to `.identity.primary` for CLI/back-compat callers. Attach a diagnostic (e.g. `no_aacs_directory`, `aacs_unit_key_missing`, `aacs_fingerprint_failed`) when Tier 1 is unavailable, for observability.
- **D-05 (format on the disc record, FPRINT-04):** `format_type` (`"bluray"`/`"uhd"`) is already derived from the MPLS header `"0300"` heuristic and must be carried through to the disc record. Planner: confirm the submission payload / API disc row records `format` (ARM already reads a `format` field per Phase 2 D-10) and that UHD detection via header version is reliable enough (note it as the frozen detection rule, or document its limits).

### B. Tier-2 anti-obfuscation frozen ruleset (FPRINT-06 guardrail)
- **D-06 (frozen ruleset content — LOCKED starting spec):** The Tier-2 playlist filter/sort/tie-break is frozen as **OVID-BD-2 v1**, lifted from libbluray's reference decoy defenses (`mpls_dump -d`/`-r`):
  1. **Filter** — exclude playlists with `total_duration_seconds < MIN_DURATION_SECONDS` (freeze `60.0`, keep current value).
  2. **Filter** — exclude playlists where any single `clip_id` recurs in the play-items more than `MAX_CLIP_REPEATS` times (freeze `2`, mirrors libbluray `-r2`) — defeats **loop-padded** duration decoys.
  3. **Dedup** — group survivors by the full ordered tuple of `(clip_id, in_time, out_time)` across all play-items; emit **one** canonical block per equivalence class — defeats **renumbered/duplicated** decoy copies of the main feature.
  4. **Sort/tie-break** — order survivors by `(-total_duration_seconds, clip_id_sequence_tuple)` where the tie-break is the full ordered `(clip_id, in_time, out_time)` tuple — **never filename**. Studios renumber `.mpls`; the current `filename ASC` tie-break is a genuine determinism/obfuscation hole, not cosmetic. Dedup guarantees this is a true total order.
- **D-07 (freeze ENFORCEMENT — constants module + version tag + CI-pinned golden tests):** Move the constants into a dedicated frozen module (e.g. `bd2_spec.py`: `MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS`, plus the sort/dedup contract), embed an explicit `OVID-BD-2` **version literal** in the canonical string, and pin **exact SHA-256 outputs** against fixture discs in a determinism test (e.g. `test_bd_fingerprint_pinned.py`). Any edit to a filter/sort/tie-break constant then **fails CI** unless the developer also bumps the version literal — which mints a **new namespace** (`bd2-` → e.g. `bd2v2-` / `OVID-BD-2` → `OVID-BD-2.1`) that coexists via the alias model rather than corrupting existing `bd2-*` values. This mirrors how `dvdread1-*` was introduced alongside `dvd1-*`, and the DVD-1 spec's own `Versioning` section (rule change → new Fingerprint Version, never mutate in place). Rejected: review-discipline-only (a reviewer can miss a silent tune of `MIN_DURATION_SECONDS`); auto-hash-of-constants version (removes the deliberate/reviewed bump; risks pointless namespace churn on no-op refactors).
- **D-08 (no migration cost — freeze the improved ruleset NOW):** BD fingerprinting has **not shipped**; there is **no `bd2-*` production data** to fragment. The improved ruleset (D-06) can be frozen as OVID-BD-2 v1 directly — the current `filename ASC` implementation is pre-release and simply replaced, not migrated.

### C. Tier-1 AACS legal boundary (FPRINT-01)
- **D-09 (keep `SHA-1(Unit_Key_RO.inf)` — legally clean):** The current Tier-1 source is kept unchanged. It is a **plaintext UDF filesystem read + one-way hash** — no descrambling, no drive-level handshake/SCSI passthrough, no secret AACS device keys. The wrapped CPS/Title-Key material inside the file is unusable without the Media Key Block + AACS-LA-licensed device keys OVID never holds, and a one-way SHA-1 digest cannot be inverted to recover key material — so hashing is neither "decryption," "circumvention," nor "decryption-key storage." This **is** what the FOSS ecosystem (libaacs, MakeMKV `keydb.cfg`) calls the "AACS Disc ID," so FPRINT-01's wording and the code already agree.
- **D-10 (doc/wording fix):** Correct the FPRINT-01 requirement wording and the code docstrings to state the equivalence explicitly: **"AACS Disc ID" ≡ `SHA-1(AACS/Unit_Key_RO.inf)`**. Behavior-neutral, docs-only.
- **D-11 (raw file NEVER committed):** Because the raw `Unit_Key_RO.inf` contains wrapped key-management fields, it must **never** be committed to the CC0 repo. Only the **derived `bd1-aacs-*`/`uhd1-aacs-*` string** is public. The raw file lives exclusively in the private, hardware-gated `real_disc` fixture tier (never in git), mirroring current DVD practice. Rejected: AACS Volume ID as Tier-1 source (needs low-level vendor drive commands — circumvention-adjacent, platform-dependent, worse legal posture, no stability gain); dropping AACS/Tier 1 (fails FPRINT-01).

### D. Fixture corpus & cross-platform determinism (FPRINT-05, FPRINT-07)
- **D-12 (HYBRID strategy):** Two-tier fixtures, matching the existing DVD `real_disc` convention:
  - **Committed / public / CI-enforced (synthetic):** Extend `conftest_bd.py` to synthesize a **heavily-obfuscated BDMV tree** — 100+ decoy playlists, duplicated main-feature playlists with shuffled clip order, loop-padded short-clip decoys — which is a **stronger** FPRINT-06 stress test than any single real disc and carries **zero** legal ambiguity (no captured retail bytes). Add the missing **`BDDisc.from_path()` end-to-end test** on synthetic fixtures. These prove the canonicalization/hashing logic is **OS-independent** (run on Linux + macOS CI).
  - **Private / `real_disc`-gated (never committed):** A new `test_bd_real_disc.py` mirroring `test_real_disc.py` — env-var gated (`pytest.mark.real_disc`, `OVID_TEST_DISC_PATH` + a second-drive path or a documented one-off comparison), asserting `BDDisc.from_path()` yields an **identical fingerprint across drives/OSes**. Never commits captured bytes.
- **D-13 (how FPRINT-05's "≥2 drives + Linux+macOS" is proven):** OS-determinism → CI runs the synthetic fixtures on **both Linux and macOS runners** (deterministic, hardware-free). Drive-independence → a **documented manual multi-drive run** by a contributor with hardware, folded into the **release checklist** so it can't be silently skipped — exactly how the DVD suite already handles hardware dependence. Rejected: synthetic-only (leaves "≥2 drives" unproven on paper); committing a real-disc metadata extract publicly (unresolved copyright on structural extracts; sits too near the "no disc images" constraint; irreversible git-history exposure).
- **D-14 (⚠ PLANNER FLAG — macOS CI):** FPRINT-05 names **macOS** explicitly. The `ovid-client` CI matrix must actually include a **macOS runner**, or OS-determinism is only asserted on Linux and FPRINT-05 is half-met. Planner: verify/extend `.github/workflows/` to run the BD determinism tests on macOS **and** Linux. This is a real acceptance-criterion gap, not optional polish.

### Claude's Discretion
- Exact `identify_bd()` signature, where the Tier-1 diagnostic enum lives, and how `BDDisc` proxies `.fingerprint`/`.tier` to `.identity.primary` (within D-02/D-04).
- Naming of the frozen constants module and the version-literal encoding scheme (`bd2v2-` vs `OVID-BD-2.1` vs a numeric suffix) — the *mechanism* (embedded literal + CI pin + new-namespace-on-bump) is locked; the exact string form is the planner's (D-07).
- The precise synthetic-obfuscation fixture composition (how many decoys, which decoy classes) so long as it exercises all three D-06 defenses: min-duration filter, `MAX_CLIP_REPEATS` loop-pad filter, and clip-sequence dedup (D-12).
- Whether the pinned determinism test and the OVID-BD-2 golden fixtures are one file or split (D-07/D-12).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & boundary
- `.planning/REQUIREMENTS.md` — FPRINT-01…07 + DOCS-01 (authoritative requirement text, `[guardrail]` markers, phase mapping). Note the FPRINT-01 wording fix in D-10.
- `.planning/ROADMAP.md` §"Phase 4" — goal, the six success criteria, Wave-A parallel-safe note.
- `docs/OVID-product-spec.md` (Milestone 0.2) — source of truth for the v0.2.0 exit criteria this phase completes.

### Fingerprint spec (the DOCS-01 deliverable + the precedent to mirror)
- `docs/fingerprint-spec.md` — currently OVID-DVD-1 only; BD/UHD listed as "planned v0.2.0" in the summary table with **no algorithm spec**. DOCS-01 adds the **OVID-BD-2 Tier 1 & Tier 2** section. Mirror the DVD-1 spec's structure, especially its **`Versioning` section** (rule change → new Fingerprint Version coexisting via aliases) — that is the precedent for D-07/D-08.
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` — the alias/identity model the BD `DiscIdentitySet` must stay consistent with; defines why the always-computable identity stays primary until a promotion is deliberately staged (grounds D-01).

### Client code this phase changes (ovid-client)
- `ovid-client/src/ovid/disc_identity.py` — `DiscIdentitySet(primary, aliases)` dataclass + `identify_dvd()`; **add `identify_bd()` here** mirroring `identify_dvd()` (D-04).
- `ovid-client/src/ovid/bd_disc.py` — `BDDisc.from_path()` short-circuit to remove (D-02); `_try_aacs_tier1()`; UHD detection via header `"0300"` (D-05).
- `ovid-client/src/ovid/bd_fingerprint.py` — `compute_aacs_fingerprint()` (D-09, keep); `build_bd_canonical_string()` + `_MIN_DURATION_SECONDS` (→ frozen `bd2_spec.py` per D-06/D-07); `compute_bd_structure_fingerprint()`.
- `ovid-client/src/ovid/mpls_parser.py` — MPLS parse (play-items, clip_id, in/out times, chapters) — source of the `(clip_id, in_time, out_time)` tuples the D-06 dedup/tie-break needs; confirm it exposes them.
- `ovid-client/src/ovid/readers/bd_folder.py` — `read_aacs_file()`, `has_aacs()`, `list_mpls_files()`, `read_mpls()` (I/O; unchanged behavior).
- `ovid-client/src/ovid/disc_structure.py`, `cli.py` — consume `BDDisc`; update for the `DiscIdentitySet` exposure (D-04 back-compat proxies).

### Tests & fixtures
- `ovid-client/tests/conftest_bd.py` — synthetic MPLS builders (`make_mpls_file`, `_make_bd_dir`, `_make_long_playlist`); **extend** with the heavily-obfuscated tree generator (D-12).
- `ovid-client/tests/test_bd_fingerprint.py` — existing component tests; add the pinned/golden determinism tests (D-07) and `BDDisc.from_path()` E2E (D-12).
- `ovid-client/tests/test_real_disc.py` — the `real_disc`/`OVID_TEST_DISC_PATH` gating pattern `test_bd_real_disc.py` mirrors (D-12/D-13); **never commits disc-derived bytes**.
- `.github/workflows/` — CI matrix; **must run BD determinism tests on macOS + Linux** for FPRINT-05 (D-14).

### Prior-phase decisions that carry forward
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-CONTEXT.md` §D-04–D-07 — the alias-object API shape (`fingerprint_aliases: [{fingerprint, method, is_primary}]`, primary-first + insertion order) the BD pair maps onto; `_method_of()` prefix-encodes-method convention (no method column).
- `.planning/phases/02-two-contributor-verification-workflow/02-CONTEXT.md` §D-10 — ARM reads only release-level fields incl. `format`; confirm FPRINT-04's format recording stays ARM-compatible.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Both tier algorithms already exist and are unit-tested** (`bd_fingerprint.py`) — Tier 1 SHA-1(Unit_Key_RO.inf), Tier 2 SHA-256 of the `OVID-BD-2|…` canonical string. This phase refactors around them; it does not rewrite them.
- `DiscIdentitySet(primary, aliases)` dataclass + `identify_dvd()` (`disc_identity.py`) — the exact template `identify_bd()` mirrors (D-04); `aliases` already defaults empty (D-03).
- `resolve_existing_disc_for_identities` (API side) already matches a submission against **any** known identity — gives the alias-pair convergence for free (D-03); no new API logic needed for the client-side pair.
- UHD detection (`format_type` from MPLS header `"0300"`) already implemented on `BDDisc` (D-05).
- Synthetic MPLS fixture builders in `conftest_bd.py` — extend for the obfuscated corpus rather than build fresh (D-12).
- `test_real_disc.py` `real_disc`/env-var gating — the pattern for `test_bd_real_disc.py` (D-12/D-13).

### Established Patterns
- **Prefix encodes method/version** (`dvd1-`, `dvdread1-`, `bd1-aacs-`, `bd2-`, `uhd1-aacs-`, `uhd2-`) — a ruleset change mints a new prefix namespace, never mutates existing values (grounds D-07).
- **Structural identity = primary, disc-ID identity = alias** (DVD precedent) — directly reused for D-01.
- **Cross-platform IO-failure tests** via `fs`-method monkeypatch + restore-in-`finally` (CLAUDE.md convention) — any new BD reader failure-path test follows this, NOT chmod/permission tricks.
- **Anti-tautology golden fixtures** (Phase 1 D-14: assert frozen structure against a hardcoded expected value independent of the seed) — the D-07 pinned SHA-256 test must assert exact expected hashes kept independent of the fixture builder, or it's tautological.
- **Frozen/versioned spec sections** (DVD-1 `Versioning`) — OVID-BD-2 mirrors it (D-06/D-07, DOCS-01).

### Integration Points
- `BDDisc.from_path()` → `identify_bd()` → `DiscIdentitySet` (the refactor seam, D-02/D-04); CLI + `disc_structure.py` consume the new shape via back-compat proxies.
- New frozen `bd2_spec.py` constants module consumed by `build_bd_canonical_string()` (D-07).
- New synthetic obfuscated-fixture builder in `conftest_bd.py`; new `test_bd_fingerprint_pinned.py` and `test_bd_real_disc.py` (D-07/D-12).
- `docs/fingerprint-spec.md` gains the OVID-BD-2 section (DOCS-01).
- CI matrix (`.github/workflows/`) gains a macOS runner for the BD determinism tests (D-14).
</code_context>

<specifics>
## Specific Ideas

- **libbluray is the reference for decoy resistance.** The D-06 ruleset is lifted directly from `mpls_dump`'s `-d` (dedup by ordered `(clip_id, in_time, out_time)` sequence) and `-r2` (exclude playlists where a clip_id repeats >2× — loop-pad decoys). Its convenience preset is `-f = -r2 -d -s900`. libbluray's *main-title* heuristic (duration + chapter-count) is deliberately NOT reused: it's a best-guess UX picker for one playable title, not a deterministic whole-structure identity.
- **Real-world obfuscation the ruleset must survive:** Lionsgate's "ScreenPass" (~2013+) and similar — many `.mpls` with near-identical durations/chapter counts where some are non-functional decoys; filename and raw duration alone cannot distinguish them (MakeMKV/Doom9/AVSForum). Filename is renumberable across repressings → unsafe as a tie-break (the current gap).
- **Legal framing (user-relevant):** hashing on-disc plaintext metadata ≠ DRM circumvention; a one-way digest ≠ key storage. But the *raw* AACS file still never touches the public CC0 repo — only the derived fingerprint string does.
</specifics>

<deferred>
## Deferred Ideas

- **API-side BD dual-string submission / alias storage (IDENT-03)** — Phase 5. This phase makes the *client* emit the `DiscIdentitySet`; storing the non-primary BD strings as aliases on submission is ADR 0001 Phase 2 completion, owned by Phase 5.
- **Cross-table fingerprint-registry arbitration (WR-02)** — Phase 5 (promotion raises write concurrency on the shared fingerprint namespace).
- **Web-UI rendering of BD fingerprint aliases (WEBUI-02)** — Phase 7.
- **Bulk-seeding real BD/UHD entries (OPS-01/02)** — Phase 8; depends on this phase's fingerprinting being solid.
- **matrix256 as a fifth alias fingerprint (MATRIX-01)** — v2 / deferred; spike-first, out of v0.2.0.

None of the four discussed areas produced scope creep — discussion stayed within FPRINT-01…07 + DOCS-01.
</deferred>

---

*Phase: 4-Blu-ray/UHD Fingerprinting*
*Context gathered: 2026-07-06*
</content>
</invoke>
