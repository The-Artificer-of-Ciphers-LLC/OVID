# Phase 5: ADR 0001 Completion — dvdread1-* Promotion - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 5-ADR 0001 Completion — dvdread1-* Promotion
**Areas discussed:** Backfill mechanism, WR-02 cross-table arbitration, Primary selection, Cutover posture, Cutover operability
**Mode:** advisor (research-backed comparison tables; calibration tier: standard)

---

## Backfill mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Alembic data migration | Per-disc idempotent promotion in a versioned migration; auto-runs on every mirror via `alembic upgrade head`. Sync feed can't carry alias rows, so each DB must promote locally. | ✓ |
| Standalone `api/scripts/` script | Manual, re-runnable, `--dry-run`. Full control, but mirrors silently drift unless operators run it. | |
| Lazy promote-on-access | Promote each disc on next lookup/submit. Untouched long-tail discs never promote → fails success criterion. | |

**User's choice:** Alembic data migration
**Notes:** Research decisive point — `SyncDiffRecord` carries only `disc.fingerprint`, not alias-table rows, so mirrors cannot receive the promotion via sync; deploy-pipeline coupling is a feature for OVID's self-hosted-mirror model.

---

## WR-02 cross-table fingerprint arbitration

| Option | Description | Selected |
|--------|-------------|----------|
| Shared fingerprint-registry table | New table with global UNIQUE; both insert paths register first. Dialect-portable (works under SQLite test suite); reuses the existing IntegrityError/re-resolve idiom. | ✓ |
| Postgres advisory lock | `pg_advisory_xact_lock` on the fingerprint. No schema change, but no SQLite equivalent — race stays untested by the pytest suite. | |
| In-savepoint recheck only | Extra cross-table SELECT before insert. Does NOT actually close the race; defense-in-depth only. | |

**User's choice:** Shared fingerprint-registry table
**Notes:** Only option that holds under `-w 4` Postgres AND stays verifiable under the SQLite TestClient suite this phase must keep green. Mandatory phase work (WR-02 carry-forward); the choice was which approach, not whether.

---

## Primary selection (mixed client fleet)

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid — server picks at first-insert | Server prefers `dvdread1-*` among a new disc's strings; `Disc.fingerprint` immutable after. Old clients can only add aliases, never demote. Deterministic, preserves D-06. | ✓ |
| Server re-normalizes every submission | Server can re-promote existing discs on write. More deterministic but mutates existing `Disc.fingerprint`, colliding with D-06 + adding races. | |
| Client-authoritative | Trust the client's declared primary. First client fixes method forever; independent PyPI/ARM upgrades never converge. | |

**User's choice:** Hybrid — server picks at first-insert
**Notes:** Immutability governs the live path; the one-time Alembic backfill is the single sanctioned mutation. Mixed-fleet invariant (old client can't demote `dvdread1-*`) is load-bearing for zero-fragmentation.

---

## Cutover posture

| Option | Description | Selected |
|--------|-------------|----------|
| Write-quiesce via MirrorModeMiddleware | Flip writes read-only, run backfill, flip back — reuses tested middleware. Eliminates backfill-vs-write race by construction. Near-zero cost pre-launch; reads never interrupted. | ✓ |
| Fully online | No write pause; correctness rides entirely on WR-02 holding for every live interleaving. | |
| Online + gated flag | Flip new-submission primary first, backfill at leisure. Same WR-02 dependence for the gap window, plus a flag branch to build and remove. | |

**User's choice:** Write-quiesce via MirrorModeMiddleware
**Notes:** Pre-launch, small data, read-hot profile makes a brief reversible write pause almost free. Fully-online deferred to a future migration once data is large and WR-02 is battle-proven.

---

## Cutover operability

| Option | Description | Selected |
|--------|-------------|----------|
| One-command wrapper + self-hosting runbook | Script/make-target: toggle read-only → `alembic upgrade` → toggle back, plus a `docs/self-hosting.md` section. Prevents the "operator forgets to flip writes back" failure. | ✓ |
| Raw steps, documented inline only | No wrapper; document the manual sequence in the migration docstring + a docs note. Less to build, more operator error. | |

**User's choice:** One-command wrapper + self-hosting runbook
**Notes:** Directly mitigates the operator-forgets-to-restore-writes risk flagged in research.

## Claude's Discretion

- Registry-table name/shape, migration file numbering, and precise sequencing of the registry vs. promotion migrations.
- Whether WR-02 registry insertion lives in `disc_identity.py` or a small new module.
- The read-only toggle mechanism inside the wrapper (env var vs. runtime flag), provided it reuses `MirrorModeMiddleware` semantics.

## Deferred Ideas

- Fully-online promotion (no write-quiesce) — future identity-method migration once the table is large post-seeding and the registry is battle-proven.
- matrix256 pressing-level alias (MATRIX-01) — spike-first, deferred to v2 (already tracked).
