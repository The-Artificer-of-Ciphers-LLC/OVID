# Phase 4: Blu-ray/UHD Fingerprinting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 4-Blu-ray/UHD Fingerprinting
**Areas discussed:** A — Alias-pair & primary tier, B — Anti-obfuscation frozen ruleset, C — Tier-1 AACS legal boundary, D — Fixtures & determinism

**Mode:** Advisor (research-backed comparison tables). Four `gsd-advisor-researcher` agents ran in parallel on the four selected areas (calibration tier: standard). A prior `haiku-scout` pass established that both BD tier algorithms already exist and are unit-tested, reframing the phase as hardening rather than greenfield.

---

## A — Alias-pair & primary tier (FPRINT-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Tier 2 structural = primary | `bd2-*`/`uhd2-*` always-computable primary; `bd1-aacs-*` as alias when AACS present. Mirrors `dvd1-*` precedent + ADR 0001; uniform primary contract; no-AACS folders still resolve; convergence via existing `resolve_existing_disc_for_identities`. | ✓ |
| Tier 1 AACS = primary when present | Stronger per-pressing key on retail discs but heterogeneous primary type — consumers must branch on version; ripped/decrypted folders silently flip to structural anyway. | |

**User's choice:** Tier 2 structural = primary (recommended).
**Notes:** Add `identify_bd()` mirroring `identify_dvd()`; stop `BDDisc.from_path()` short-circuit; one-tier fallback = `DiscIdentitySet(primary=bd2, aliases=[])`.

---

## B — Anti-obfuscation frozen ruleset (FPRINT-06 guardrail)

Ruleset **content** was recommended-locked regardless of the enforcement choice: `MIN_DURATION_SECONDS=60.0` (keep) + `MAX_CLIP_REPEATS=2` (new, libbluray `-r2`) + dedup by ordered `(clip_id, in_time, out_time)` + sort/tie-break by clip-id sequence (never filename). The question below was the freeze *enforcement* mechanism.

| Option | Description | Selected |
|--------|-------------|----------|
| Constants module + version tag + CI-pinned golden tests | Frozen `bd2_spec.py` + `OVID-BD-2` version literal in canonical string + exact-SHA-256 fixture assertions; any constant edit fails CI unless the version literal is deliberately bumped (new namespace). Doubles as FPRINT-05 determinism test. | ✓ |
| Version tag + review discipline only | Frozen constants + doc'd version literal, no CI pin — relies on PR review to catch a silent tune. | |
| Auto-hash-of-constants version | Version literal derived from a hash of the constants; impossible to forget, but removes the deliberate/reviewed bump and risks namespace churn. | |

**User's choice:** Constants module + version tag + CI-pinned golden tests (recommended).
**Notes:** BD hasn't shipped → no `bd2-*` production data to fragment; freeze the improved ruleset as OVID-BD-2 v1 directly. Ruleset lifted from libbluray `mpls_dump -d`/`-r2`.

---

## C — Tier-1 AACS legal boundary (FPRINT-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Keep `SHA-1(Unit_Key_RO.inf)`, raw file private-only, clarify docs | Plaintext read + one-way hash is legally clean and IS the FOSS "AACS Disc ID"; raw file never committed (real_disc-gated); only `bd1-aacs-*` public; fix FPRINT-01 wording to state the equivalence. | ✓ |
| Switch Tier 1 to AACS Volume ID | Needs low-level vendor drive commands — circumvention-adjacent, platform-dependent, worse legal posture, no stability gain. | |
| Drop AACS/Tier 1 entirely | Fails FPRINT-01; loses per-pressing uniqueness. (Presented in research; not offered as a live option.) | |

**User's choice:** Keep `SHA-1(Unit_Key_RO.inf)`, raw file private-only, clarify docs (recommended).
**Notes:** Requirement text and code already agree once "AACS Disc ID" ≡ `SHA-1(Unit_Key_RO.inf)` is documented. Docs-only change.

---

## D — Fixtures & determinism (FPRINT-05/07)

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: synthetic committed + real_disc-gated multi-drive proof | Synthetic obfuscated corpus + `BDDisc.from_path()` E2E committed & CI-enforced (OS-determinism, decoy-resistance); `test_bd_real_disc.py` env-gated for drive-determinism, never commits captured bytes. Matches DVD `real_disc` convention. | ✓ |
| Synthetic-only corpus | Fully deterministic/legal in CI but never exercises a real drive — FPRINT-05's "≥2 drives" left unproven. | |
| Commit real-disc metadata extract publicly | Proves cross-drive determinism in CI but unresolved copyright on structural extracts; near the "no disc images" constraint. | |

**User's choice:** Hybrid (recommended).
**Notes:** Flagged for planner — FPRINT-05 names macOS explicitly; the CI matrix must run BD determinism tests on a macOS runner + Linux, or OS-determinism is only half-proven (CONTEXT D-14). Drive-independence proven via a documented manual multi-drive run folded into the release checklist.

---

## Claude's Discretion

- Exact `identify_bd()` signature, Tier-1 diagnostic enum location, `BDDisc` back-compat proxy details.
- Frozen constants module name + version-literal encoding form (`bd2v2-` vs `OVID-BD-2.1` vs numeric) — mechanism locked, string form open.
- Synthetic obfuscation-fixture composition (decoy counts/classes), provided all three D-06 defenses are exercised.
- Whether the pinned determinism test and golden fixtures are one file or split.

## Deferred Ideas

- API-side BD dual-string submission / alias storage (IDENT-03) → Phase 5.
- Cross-table fingerprint-registry arbitration (WR-02) → Phase 5.
- Web-UI rendering of BD aliases (WEBUI-02) → Phase 7.
- Bulk-seeding real BD/UHD entries (OPS-01/02) → Phase 8.
- matrix256 fifth alias fingerprint (MATRIX-01) → v2, spike-first.
</content>
