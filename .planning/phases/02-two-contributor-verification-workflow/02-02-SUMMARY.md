---
phase: 02-two-contributor-verification-workflow
plan: 02
subsystem: api
tags: [anti-sybil, verify-04, hmac, ipaddress, postgres, alembic, sqlalchemy, rate-limit, tdd]

# Dependency graph
requires:
  - phase: 01-alias-layer-hardening-repo-hygiene
    provides: "verification.py state machine (verify/flag_dispute), DiscEdit audit table, disc_edits verify rows"
  - phase: 02-two-contributor-verification-workflow (plan 01)
    provides: "structural_match.py (proof-of-possession comparison the gate sits beside in Plan 03)"
provides:
  - "api/app/anti_sybil.py — evaluate_confirmation() anti-Sybil pre-check (cooldown floor + weighted fail-open trust score)"
  - "ip_subnet_hash() salted /24//48 HMAC-SHA256 IP pseudonymization helper (D-06)"
  - "ConfirmationGate frozen dataclass (hard_blocked, trust_ok, ip_hash) — Plan 03 consumes it"
  - "DiscEdit.ip_hash column + idx_disc_edits_user_type_created composite index (Alembic 900000000004)"
  - "conftest make_user_with_age() account-age override helper"
affects: [02-03 confirmation-flow wiring, 02-05 privacy-policy IP-hash addendum, phase-03 rate-limit hardening]

# Tech tracking
tech-stack:
  added: []  # stdlib only: ipaddress, hmac, hashlib, datetime — no new packages
  patterns:
    - "Anti-Sybil gate as a pre-check, never a status-writer (VERIFY-02): decides whether verify() may fire, never mutates disc.status or commits"
    - "Portable time-window cooldown: Python-computed cutoff bound param over disc_edits, no dialect INTERVAL SQL (D-13, Pitfall 4)"
    - "Salted, /24-truncated HMAC-SHA256 IP hash with optional-with-warning salt (fail-open, not fail-fast)"
    - "Weighted, offsetting, fail-open trust score — only the exact Sybil signature (fresh + same-subnet) blocks"

key-files:
  created:
    - "api/app/anti_sybil.py"
    - "api/tests/test_anti_sybil.py"
    - "api/alembic/versions/900000000004_add_disc_edits_ip_hash_index.py"
  modified:
    - "api/app/models.py"
    - "api/tests/conftest.py"

key-decisions:
  - "IP-hash salt is optional-with-startup-warning (A5/D-07), NOT the fail-fast _require_env pattern — a missing salt degrades IP to no-signal, never blocks"
  - "Cooldown lives as an index-on-disc_edits COUNT query (D-13 discretion), not a dedicated table — minimal migration blast radius"
  - "Account-age is always 'known' for a real User; fail-open concerns the IP signal. Young-alone (-1) never reaches the block threshold (-2) on its own (D-05/D-08)"
  - "_submitter_ip_hash reads the earliest create/identify DiscEdit ip_hash as the submitter subnet reference"

patterns-established:
  - "Pre-check gate pattern: evaluate_confirmation(db, disc, actor, request) -> ConfirmationGate, wraps verification.py without touching status"
  - "Named UPPER_SNAKE tunable thresholds (D-08) with rationale comments, no magic numbers"

requirements-completed: [VERIFY-04]

coverage:
  - id: D1
    description: "disc_edits gains a nullable ip_hash column + composite index (user_id, edit_type, created_at) on both the ORM model and a chained Alembic migration 900000000004"
    requirement: VERIFY-04
    verification:
      - kind: integration
        ref: "api: python -c create_all + inspect(disc_edits) asserts ip_hash col + idx_disc_edits_user_type_created + revision/down_revision (Task 1 automated check)"
        status: pass
    human_judgment: false
  - id: D2
    description: "ip_subnet_hash: salted /24 (IPv4) / /48 (IPv6) HMAC-SHA256; same-subnet collapse, distinct differ, None/malformed/no-salt fail open (D-06/D-07)"
    requirement: VERIFY-04
    verification:
      - kind: unit
        ref: "tests/test_anti_sybil.py::TestIpSubnetHash"
        status: pass
    human_judgment: false
  - id: D3
    description: "Postgres-backed confirmation cooldown hard floor over disc_edits verify rows: under-limit passes, over-limit hard_blocks, stale out-of-window edits not counted (D-13)"
    requirement: VERIFY-04
    verification:
      - kind: integration
        ref: "tests/test_anti_sybil.py::TestCooldown"
        status: pass
    human_judgment: false
  - id: D4
    description: "Weighted, offsetting, fail-open trust score: fresh+same-subnet blocks (Sybil signature); all-absent, young-alone, established+same-subnet, fresh+distinct all pass; distinct user_id alone insufficient (D-04/D-05/D-08)"
    requirement: VERIFY-04
    verification:
      - kind: unit
        ref: "tests/test_anti_sybil.py::TestWeightedScore"
        status: pass
      - kind: unit
        ref: "tests/test_anti_sybil.py::TestSaltFailOpen::test_missing_salt_yields_no_ip_signal"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-07-05
status: complete
---

# Phase 2 Plan 02: VERIFY-04 Anti-Sybil Gate Summary

**Worker-safe Postgres confirmation cooldown + salted /24 HMAC-SHA256 IP hash + weighted fail-open trust score in a standalone `anti_sybil.py`, backed by a nullable `disc_edits.ip_hash` column and composite index (Alembic 900000000004).**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-05T22:40:15Z
- **Completed:** 2026-07-05T22:46:23Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `disc_edits.ip_hash` nullable column + `idx_disc_edits_user_type_created` composite index landed on both the ORM model (SQLite test schema) and a chained Alembic migration `900000000004` (down_revision `900000000003`); historical rows stay NULL → fail-open, no backfill.
- `api/app/anti_sybil.py` implements the three-layer gate: (1) a Postgres-native confirmation cooldown COUNT over `disc_edits` verify rows using a Python-computed cutoff bound param (worker-safe by construction, D-13/D-14; no dialect INTERVAL SQL); (2) `ip_subnet_hash()` salted /24//48 HMAC-SHA256 with optional-with-warning salt (D-06/A5); (3) a weighted, offsetting, fail-open trust score where only the exact Sybil signature (fresh account AND same subnet = -2) drops below the block threshold.
- 17-test `test_anti_sybil.py` covers IP-hash collapse/fail-open, cooldown under/over/stale-window, all five weighted-score rows, the returned `ip_hash`, and missing-salt fail-open. Full API suite green (288 passed).
- `ConfirmationGate` frozen dataclass and `evaluate_confirmation(db, disc, actor, request)` signature published for Plan 03 to wire into `_handle_existing_disc` (429 on `hard_blocked`, 403 on `not trust_ok`, `ip_hash` stored on the verify DiscEdit).

## Task Commits

Each task was committed atomically:

1. **Task 1: disc_edits.ip_hash column + composite index (model + migration)** - `fb50cec` (feat)
2. **Task 2: RED — anti-Sybil unit tests + conftest account-age helper** - `48ed1a4` (test)
3. **Task 3: GREEN — implement anti_sybil.py** - `6f71716` (feat)

_TDD gate sequence: `test(48ed1a4)` RED (ImportError, module absent) → `feat(6f71716)` GREEN (17 passing)._

## Files Created/Modified
- `api/app/anti_sybil.py` (new) - VERIFY-04 gate: cooldown floor, salted IP hash, weighted fail-open trust score, named tunable thresholds, `ConfirmationGate`.
- `api/tests/test_anti_sybil.py` (new) - unit + integration suite over the three layers (17 tests).
- `api/alembic/versions/900000000004_add_disc_edits_ip_hash_index.py` (new) - adds nullable `ip_hash` + composite index; symmetric downgrade.
- `api/app/models.py` (mod) - `DiscEdit.ip_hash` column + `__table_args__` composite index idiom.
- `api/tests/conftest.py` (mod) - `make_user_with_age()` account-age override helper (+ datetime import).

## Decisions Made
- **Salt is optional-with-warning, not fail-fast** (A5/D-07): `_ip_hash_salt()` logs a one-time warning and returns `None` when `OVID_IP_HASH_SALT` is unset, so a missing salt disables only the IP signal and never blocks a confirmation. This deliberately does the opposite of `auth/config.py::_require_env`.
- **Cooldown as an index-on-`disc_edits` COUNT** rather than a dedicated table (D-13 discretion): co-locates the signal with the confirmation record, single migration, minimal blast radius.
- **Cutoff computed in Python and passed as a bound parameter** (D-13/Pitfall 4): the query runs identically on the SQLite test engine and prod Postgres — proven by the cooldown tests running on SQLite.
- **`_submitter_ip_hash` reads the earliest `create`/`identify` DiscEdit** as the submitter's subnet reference (those are the edit types recorded on original submission per `routes/disc.py`).

## Deviations from Plan

None - plan executed exactly as written. All three tasks implemented to their `<action>`/`<acceptance_criteria>`; no Rule 1-4 deviations required.

## Issues Encountered
- Local `python` shim is absent and the system interpreter is Python 3.14 without the project deps; the project `.venv` (`api/.venv/bin/python`, SQLAlchemy 2.0.51) was used for all verification runs. No code impact.

## Threat Flags

None - the gate introduces no new network/auth/file surface beyond the `disc_edits.ip_hash` column, which is the mitigation for T-2-07 (raw-IP disclosure) and is stored only as a salted, truncated hash. All threat-register mitigations (T-2-02/03/04/07/08) are realized by this plan's cooldown floor + soft signals.

## Deferred Issues

Two pre-existing third-party test-infra deprecation warnings surfaced during the full-suite run — both already logged by Plan 02-01 in `deferred-items.md` and out of scope here (they require dependency changes, not code in this plan):
- `StarletteDeprecationWarning` (httpx/starlette TestClient) from `fastapi/testclient.py:1` via `conftest.py`.
- `slowapi` `asyncio.iscoroutinefunction` deprecation from `slowapi/extension.py:720` in `test_auth.py` (relates to Phase 3 rate-limit hardening).

## User Setup Required

None required to run/test. **Deployment note for Plan 02-05 / prod:** set `OVID_IP_HASH_SALT` to enable the IP-diversity signal (fail-open when unset), and configure `FORWARDED_ALLOW_IPS` on the prod gunicorn/proxy so `request.client.host` reflects the real client IP (Pitfall 1). Neither blocks launch. The new IP-hash data category must be disclosed in the privacy-policy addendum (D-06, owned by Plan 02-05).

## Next Phase Readiness
- `evaluate_confirmation()` + `ConfirmationGate` are ready for Plan 03 to insert into `_handle_existing_disc` before `verify()` (pre-check pattern; 429/403 mapping and `ip_hash` capture on the verify DiscEdit).
- Storage (column + index) is present on both the ORM model and the migration chain; full API suite green (288 passed).
- No blockers.

## Self-Check: PASSED

---
*Phase: 02-two-contributor-verification-workflow*
*Completed: 2026-07-05*
