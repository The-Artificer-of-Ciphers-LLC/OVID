---
phase: 05
slug: adr-0001-completion-dvdread1-promotion
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-06
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (all 7 PLANs carry a `<threat_model>` block). ASVS L1.
> Mitigations verified via the Phase 5 code review (05-REVIEW.md), goal verification
> (05-VERIFICATION.md), and a live cutover run against real docker compose + PostgreSQL
> (05-UAT.md). No open threats at or above the `high` block threshold.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Authenticated submitter → `attach_lookup_aliases` / `_select_primary` / `register_fingerprint` write path | Submitter identity strings taken at face value pending two-contributor verification — unchanged trust model | fingerprint / fingerprint_aliases (schema-validated, non-secret) |
| Physical disc → local libdvdread read → `identify_dvd()` | Fully client-side computation from the disc's IFO + libdvdread Disc ID; no network input | local disc structure |
| ARM job/bearer-token → `submit_to_ovid` → `POST /v1/disc/register` | Same trust boundary as the CLI submission path — a bearer-token-authenticated write | fingerprint + fingerprint_aliases |
| Operator-triggered `alembic upgrade head` | Migrations operate solely on the deployment's own existing DB state; no external input | internal DB state |
| Operator's local shell → `scripts/promote_dvdread1.py` → docker compose CLI | Trusted operator context only; no network-facing surface, never invoked by the API | OVID_MODE (deployment config, non-secret) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Tampering | attach_lookup_aliases / register_fingerprint | high | mitigate | Global `UNIQUE(fingerprint)` on `fingerprint_registry` collapses the cross-table race into the existing SAVEPOINT/IntegrityError re-resolve idiom (D-02/WR-02). Verified present (models.py, disc_identity.py, migration 900000000005) + live backfill "2 from discs, 1 from aliases". | closed |
| T-05-02 | Repudiation | fingerprint_registry rows | low | accept | Registry is write-only; discs never hard-deleted → orphaning not expected. Accepted (below threshold). | closed |
| T-05-03 | Tampering | IDENT-02 same-table race regression | medium | mitigate | Pre-existing `test_disc_identity_race.py` classes stay green; full api suite (362) passes. | closed |
| T-05-04 | Tampering | promote_one_disc / promote_all_dvdread1_discs | medium | mitigate | Idempotency guard (`WHERE discs.fingerprint = <current dvd1>`) makes re-runs no-ops (D-01). Verified LIVE: re-run promoted 0 discs. | closed |
| T-05-05 | Denial of Service | per-disc commit loop | low | accept | Bounded/resumable; runs only inside the write-quiesce window. Accepted (below threshold). | closed |
| T-05-06 | Tampering | identify_dvd() primary selection | low | accept | Purely local; server re-derives primary via `_select_primary()` (D-03) and never trusts the client's declared primary. Accepted (below threshold). | closed |
| T-05-07 | Denial of Service | libdvdread read-failure handling | low | accept | Existing ValueError/LibdvdreadError handling unchanged; no new failure mode. Accepted (below threshold). | closed |
| T-05-08 | Tampering | submit_to_ovid payload construction | medium | mitigate | ARM aliases come from the same local fingerprint computation; API arbitration treats ARM and CLI aliases identically. Verified (arm/identify_ovid.py, 05-04 tests). | closed |
| T-05-09 | Denial of Service | arm/identify.py never-raise contract | high | mitigate | New call sites wrapped in the pre-existing try/except-pass scaffolding; tests assert `identify()` never raises even when `fingerprint_disc_with_identity` raises. Verified (05-04, verifier). | closed |
| T-05-10 | Tampering | _select_primary() candidate selection | high | mitigate | Only prefers a `dvdread1-*` string the same submitter provided; no privileged/trusted string; no new trust boundary (D-03). Verified (routes/disc.py, code review). | closed |
| T-05-11 | Elevation of Privilege | mixed-fleet demote / fragmentation attack | high | mitigate | `Disc.fingerprint` never reassigned on any existing-disc path; old/malicious client re-declaring `dvd1-*` can only add/confirm aliases. Verified by the mixed-fleet regression test AND LIVE (`dvd1-AAAA1111` still resolves; no demote). | closed |
| T-05-12 | Tampering | register_fingerprint() ordering in the new-disc SAVEPOINT | medium | mitigate | Invoked inside the same `db.begin_nested()` block as the Disc insert → a losing race rolls back atomically; no partial-write window. Verified (routes/disc.py, code review). | closed |
| T-05-13 | Tampering | Alembic migration chain ordering | high | mitigate | `900000000005` chained strictly before `900000000006` via `down_revision`. Verified LIVE: single linear head, migrations ran 005→006 in order. | closed |
| T-05-14 | Repudiation | idempotent migration re-run safety | high | mitigate | Alembic revision tracking + independently idempotent `promote_one_disc()`. Verified LIVE: re-running `alembic upgrade head` re-promoted 0 discs. NOTE: the alembic version stamp itself was fixed post-cutover (commit `1893b4c`) — see audit trail. | closed |
| T-05-15 | Denial of Service | rev-B commit loop against real Postgres | medium | mitigate | **Mitigation mechanism revised (commit `1893b4c`):** the migration now runs the promotion in ONE atomic Alembic transaction (`commit=False`), not per-disc commits — an interrupted run rolls back cleanly and re-runs (safer; also fixes the version-stamp bug). Interruption/DoS still mitigated (atomic re-run + small dataset + write-quiesce window). Verified LIVE. | closed |
| T-05-16 | Tampering / DoS | promote_dvdread1.py targeting wrong deployment | high | mitigate | Requires explicit `--compose-file` (no default), prints captured OVID_MODE + target files, requires operator confirmation. Verified in code + LIVE (confirm prompt shown). | closed |
| T-05-17 | Denial of Service | wrapper crash strands service read-only | high | mitigate | Restore runs in `finally:`; hardened (commit `e2a36e0`) to also fail-loud on capture failure and print a CRITICAL recovery command if restore itself fails. Verified LIVE: OVID_MODE restored to `standalone`. | closed |
| T-05-18 | Information Disclosure | printing OVID_MODE / compose paths | low | accept | OVID_MODE is deployment config, not a secret (V13); no credentials read/printed. Accepted (below threshold). | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-02 | Registry rows are write-only; discs never hard-deleted → orphaning has no functional impact (out-of-scope cleanup). | plan-time disposition | 2026-07-06 |
| AR-05-02 | T-05-05 | Per-disc commit loop is bounded/resumable and runs only inside the D-04 write-quiesce window. | plan-time disposition | 2026-07-06 |
| AR-05-03 | T-05-06 | Client-side primary selection is non-authoritative; server re-derives via `_select_primary()`. | plan-time disposition | 2026-07-06 |
| AR-05-04 | T-05-07 | libdvdread failure handling unchanged; no new failure mode introduced. | plan-time disposition | 2026-07-06 |
| AR-05-05 | T-05-18 | OVID_MODE is non-secret deployment config; no credentials are printed. | plan-time disposition | 2026-07-06 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-06 | 18 | 18 | 0 | secure-phase (ASVS L1, plan-time register; mitigations cross-checked against 05-REVIEW.md, 05-VERIFICATION.md, and the live 05-UAT cutover run) |

Notes:
- During the live UAT cutover, a real Postgres-only Alembic version-stamp bug was found (migration 006's committing bulk driver discarded the `alembic_version` stamp). Fixed inline (commit `1893b4c`) and re-verified live (`alembic current` → `900000000006`). This strengthened T-05-14/T-05-15 (the migration is now atomic and its applied-state records correctly).
- T-05-17's `finally`-restore was hardened during code review (commit `e2a36e0`).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-06
