---
status: testing
phase: 05-adr-0001-completion-dvdread1-promotion
source: [05-VERIFICATION.md]
started: 2026-07-06T00:00:00Z
updated: 2026-07-06T00:00:00Z
---

## Current Test

number: 1
name: dvdread1 cutover wrapper end-to-end on a real docker compose + Postgres deployment
expected: |
  Writes are 405-gated during the window, reads are briefly interrupted across the two
  restarts, discs with a recorded dvdread1-* alias come back with dvdread1-* primary,
  discs without one stay on dvd1-*, and OVID_MODE ends on its original value regardless
  of migration outcome.
awaiting: user response

## Tests

### 1. dvdread1 cutover wrapper end-to-end on a real docker compose + Postgres deployment

On a real `docker compose` + Postgres deployment, run `python scripts/promote_dvdread1.py`
(optionally with `-f <compose-file>`). Confirm it:
  (a) captures the current OVID_MODE,
  (b) flips the api service to OVID_MODE=mirror and restarts,
  (c) runs `alembic upgrade head`,
  (d) restores the captured OVID_MODE on both success and failure, and
  (e) prints the CRITICAL manual-recovery command if the restore step itself fails.

expected: Writes are 405-gated during the window, reads are briefly interrupted across the two restarts, discs with a recorded dvdread1-* alias come back with dvdread1-* primary, discs without one stay on dvd1-*, and OVID_MODE ends on its original value regardless of migration outcome.
why_human: scripts/promote_dvdread1.py orchestrates `docker compose exec/up` subprocesses against a live api container + Postgres; the real end-to-end restart/restore round-trip cannot be exercised in this static/CI environment. The script's capture/restore/finally logic is statically verified in 05-VERIFICATION.md; only the live-deployment behavior needs a human.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
