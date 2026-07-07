---
status: complete
phase: 05-adr-0001-completion-dvdread1-promotion
source: [05-VERIFICATION.md]
started: 2026-07-06T00:00:00Z
updated: 2026-07-06T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. dvdread1 cutover wrapper end-to-end on a real docker compose + Postgres deployment

Ran `scripts/promote_dvdread1.py -f docker-compose.yml -f docker-compose.verify.yml` against an
isolated, ephemeral Phase-5 stack (real `docker compose` + PostgreSQL 16) on holodeck, seeded with
Disc A (`dvd1-AAAA1111` primary + `dvdread1-BBBB2222` alias) and Disc B (`dvd1-CCCC3333`, no alias),
DB pre-staged at Alembic `900000000004`.

expected: Writes are 405-gated during the window, reads are briefly interrupted across the two restarts, discs with a recorded dvdread1-* alias come back with dvdread1-* primary, discs without one stay on dvd1-*, and OVID_MODE ends on its original value regardless of migration outcome.

result: pass

observed:
- Wrapper captured `OVID_MODE='standalone'`, flipped api to `mirror` (restart), ran `alembic upgrade head`
  (005 registry create+backfill: "2 from discs, 1 from disc_identity_aliases"; 006 promotion:
  "1 discs promoted"), then restored `OVID_MODE='standalone'`. Exit 0.
- Promotion correct: Disc A -> primary `dvdread1-BBBB2222` with `dvd1-AAAA1111` demoted to its alias;
  Disc B unchanged on `dvd1-CCCC3333`; `fingerprint_registry` holds all 3 fingerprints.
- Zero fragmentation (live API): `GET /v1/disc/dvd1-AAAA1111` -> 200, resolves to primary
  `dvdread1-BBBB2222`; `dvd1-CCCC3333` -> 200 unchanged.
- Mirror-mode write gate (live API): `POST /v1/disc/register` -> 405 in mirror, 200 GET reads served;
  after restore, write -> 401 (auth), i.e. no longer gated.

defect found & fixed during this test (not deferred):
- **Alembic version-stamp bug (Postgres-only, real).** `promote_all_dvdread1_discs()` did
  `connection.commit()` (commit-as-you-go) on Alembic's own bind inside migration 006, which discarded
  Alembic's `alembic_version` stamp for revision 006 — the promotion DATA applied but `alembic current`
  stayed at `900000000005` forever and every `alembic upgrade head` re-ran 006. Missed by unit tests
  (call the function directly, never through real Alembic) and by the SQLite dry-run (didn't assert
  `alembic current`). Fixed by adding `commit=False` for the migration caller so the promotion + the
  version stamp commit atomically as one Alembic transaction (commit `1893b4c`, +2 regression tests).
  Re-verified live: after the fix, `alembic upgrade head` advances `alembic current` -> `900000000006 (head)`,
  promotion idempotent (0 re-promoted). Ephemeral holodeck stack torn down after verification.

## Summary

total: 1
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none]
