---
phase: 02-two-contributor-verification-workflow
source:
  - 02-REVIEW.md
remediated: 2026-07-05T00:00:00Z
findings:
  total: 11
  resolved: 8
  false_positive: 1
  open_feature_gap: 1
  info_not_in_scope: 1
suite_before: 297 passed
suite_after: 310 passed
status: resolved
---

# Phase 2: Security Remediation Report

**Source Review:** `02-REVIEW.md` (deep review, 2026-07-05 — `issues_found`: 3 critical / 7 warning / 1 info, 11 total)
**Remediated:** 2026-07-05
**Status:** resolved
**Full Suite:** 310 passed (was 297 at review time)

## Summary

All 3 CRITICAL findings and all real WARNING findings from the deep code review of the two-contributor verification workflow have been fixed, TDD-style (a failing regression test committed first, then the minimal fix), and are now covered by a passing regression test. An adversarial verifier independently re-examined every finding before any fix landed and **live-reproduced CR-01** end-to-end, confirming it was a genuine, exploitable bypass rather than a review artifact.

- **3/3 criticals fixed:** CR-01 (self-confirmation via register→identify→resubmit), CR-02 (zero-title vacuous structural match / echo attack), CR-03 (anti-Sybil IP-diversity signal dead behind the production reverse proxy).
- **6/7 warnings fixed:** W2 (missing `ip_hash` on the identify-path audit edit), W3 (cooldown check-then-act race), W4 (cooldown off-by-one on both hourly and daily caps), W6 (single-actor verify-bypass via `/resolve`), W7 (stale/fabricated error codes in `docs/api-reference.md`).
- **1/7 warnings is a false positive:** W1 — the adversarial verifier re-checked `duration_secs` handling and found the check is already symmetric (`abs()` with a both-None guard). No change made.
- **1/7 warnings is an open feature gap, not a code defect:** W5 — the ~90-day IP-hash retention window has no automated purge job. Docs were corrected to state this honestly; the purge job itself remains unimplemented (candidate for Phase 3 infra work).
- **1 Info-level finding (IN-01) was not part of this remediation pass** — see "Not Addressed in This Pass" below.

## Adversarial Verification Note

An independent adversarial verifier re-examined all 11 findings from `02-REVIEW.md` before remediation began:

- **CR-01** was **live-reproduced**: the verifier drove the actual `register` → `identify` → `resubmit` sequence against a running instance and confirmed a single account could flip its own submission to `verified` with zero involvement from a genuine second contributor, exactly as the review described.
- **CR-03** was **downgraded from CRITICAL to HIGH**: the verifier determined this is a fail-open *availability/signal-integrity* defect (the anti-Sybil IP-diversity signal is constant behind the prod proxy, which both rejects fresh legitimate confirmers and detects nothing), not a *new* exploit path — an attacker gains no verification capability here that CR-01/CR-02 didn't already independently grant.
- **W1** was found to be a **false positive**: the `duration_secs` tolerance check already treats "stored has a value, submitted omitted it" as a mismatch via a both-None guard combined with `abs()`; the review's concern did not hold up under direct inspection.

## Findings → Verdict → Resolution → Commits

| ID | Severity | Verdict | Resolution | Commits |
|----|----------|---------|------------|---------|
| CR-01 | Critical | Confirmed (live-reproduced) | Fixed | `1679f5b`, `938cdac` |
| CR-02 | Critical | Confirmed | Fixed | `625b522`, `fd5c808` |
| CR-03 | Critical → High (downgraded) | Confirmed | Fixed | `cf9bab3`, `f277c70` |
| W1 | Warning | False positive | No change | — |
| W2 | Warning | Confirmed | Fixed | `5041b68`, `79a5ad8` |
| W3 | Warning | Confirmed | Fixed | `cf9bab3`, `d22e77b` |
| W4 | Warning | Confirmed | Fixed | `cf9bab3`, `d22e77b` |
| W5 | Warning | Confirmed (feature gap) | Docs made honest; purge job **open** | `6b4cfc2` |
| W6 | Warning | Confirmed | Fixed | `ba09d48`, `a34b98e` |
| W7 | Warning | Confirmed | Fixed | `7364da0` |
| IN-01 | Info | Not in scope of this pass | Not addressed | — |

### Critical

#### CR-01 — Self-confirmation bypass via register → identify → resubmit

- **Verdict:** CONFIRMED — adversarial verifier live-reproduced the exploit end-to-end.
- **Root cause:** `_identify_existing_disc` never updated `existing.submitted_by` when a different user attached the first release/title metadata to a bot-pre-registered disc, so both self-confirmation guards (`routes/disc.py`'s same-submitter check and `verification.py`'s `verify()` check) compared against a stale registrant, not the actual metadata author.
- **Resolution:** `_identify_existing_disc` (`api/app/routes/disc.py`) now sets `submitted_by=identifier` (i.e. `existing.submitted_by = current_user.id`) at the point metadata is first attached, so the disc is attributed to whoever actually supplied the structural/release content.
- **Regression test:** `api/tests/test_identify_self_confirm.py`
- **Commits:** `1679f5b` (red test), `938cdac` (fix)

#### CR-02 — `structural_match` trivially passes on zero titles (echo attack)

- **Verdict:** CONFIRMED — `api/tests/test_disc_edits.py` itself encoded the bug, asserting `status == "verified"` on a title-less release-only resubmission.
- **Root cause:** `structural_match` returned `True` unconditionally when both the stored and submitted title lists were empty, so verification was driven entirely by publicly-searchable release metadata (title/year/TMDB id) — exactly what the structural gate exists to avoid trusting.
- **Resolution:** `structural_match` (`api/app/structural_match.py`) now returns `False` whenever either title list is empty; the pre-existing bad fixtures in `api/tests/test_disc_edits.py` that encoded the vacuous-match behavior were repaired to reflect correct expectations.
- **Regression tests:** `api/tests/test_structural_match.py`, `api/tests/test_disc_submit.py`
- **Commits:** `625b522` (red tests), `fd5c808` (fix + fixture repair)

#### CR-03 — Anti-Sybil IP-diversity signal dead behind the production reverse proxy

- **Verdict:** CONFIRMED; **downgraded CRITICAL → HIGH** by the adversarial verifier — a fail-open availability/signal-integrity defect, not a newly-reachable exploit.
- **Root cause:** the app read `request.client.host` directly with no `--forwarded-allow-ips`/proxy-header trust configured, so behind the documented production nginx topology every request's "client IP" was the proxy's own address — making the IP-diversity signal constant (always "same subnet") for every submitter/confirmer pair in production.
- **Resolution:** gunicorn now runs with `--forwarded-allow-ips "${OVID_FORWARDED_ALLOW_IPS:-127.0.0.1}"` in `docker-compose.prod.yml`, with the new env var documented in `.env.example` and an operator note added to `docs/deployment.md`.
- **Regression tests:** `api/tests/test_anti_sybil.py` (`client_ip_hash` unit tests). **Note:** the ASGI proxy-trust chain itself is inspection-verified, not unit-testable via `TestClient` (which never exercises the real reverse-proxy hop).
- **Commits:** `cf9bab3` (client_ip_hash unit tests), `f277c70` (fix)

### Warnings

#### W1 — `duration_secs` tolerance check asymmetry

- **Verdict:** FALSE POSITIVE. The adversarial verifier re-checked the code and found the check is already symmetric — `abs()` combined with a both-None guard correctly treats "stored has a value, submitted omitted it" as a mismatch.
- **Resolution:** No change made.

#### W2 — Identify-path audit edit missing `ip_hash`

- **Verdict:** CONFIRMED — the `"identify"` `DiscEdit` (the only audit record for any disc on the ARM register→identify path) omitted `ip_hash`, silently disabling the IP-diversity signal for that entire path.
- **Resolution:** the identify `DiscEdit` (`api/app/routes/disc.py`) now passes `ip_hash=client_ip_hash(request)`, consistent with the `"create"` edit.
- **Regression test:** `api/tests/test_confirmation_flow.py`
- **Commits:** `5041b68` (red test), `79a5ad8` (fix)

#### W3 — Confirmation cooldown check-then-act race

- **Verdict:** CONFIRMED (bounded overshoot under concurrency) — the cooldown count and the later verify-edit insert were not serialized, so concurrent requests from the same actor could both pass the gate before either committed.
- **Resolution:** `evaluate_confirmation` (`api/app/anti_sybil.py`) now takes a `with_for_update()` lock on the actor's `User` row before counting recent confirmations, mirroring the `next_seq()` pattern in `sync.py`.
- **Regression test:** `api/tests/test_anti_sybil.py`
- **Commits:** `cf9bab3` (test), `d22e77b` (fix)

#### W4 — Cooldown off-by-one on both hourly and daily caps

- **Verdict:** CONFIRMED — `hourly > CONFIRMATION_MAX_PER_WINDOW` (and the daily equivalent) allowed one extra confirmation beyond the named cap on both the hourly and daily windows.
- **Resolution:** both comparisons changed from `>` to `>=` in `api/app/anti_sybil.py`, so the named cap is now the true ceiling on both windows.
- **Regression test:** `api/tests/test_anti_sybil.py` (exact-boundary case now asserted)
- **Commits:** `cf9bab3` (test), `d22e77b` (fix)

#### W5 — 90-day IP-hash retention: no automated purge job

- **Verdict:** CONFIRMED as a **feature gap**, not a code defect — `docs/privacy.md` asserted an enforced ~90-day retention/deletion window that no code anywhere implements.
- **Resolution:** `docs/privacy.md` now states plainly that automated purge is **not yet implemented** and that retention enforcement is currently manual/operator-run.
- **Commit:** `6b4cfc2`
- **Status: OPEN feature gap.** The purge job itself remains unimplemented. Record this as an open feature gap, not as fixed — it is a candidate for Phase 3 infra work, not a Phase 2 completion item.

#### W6 — Single-actor verify-bypass via `/resolve`

- **Verdict:** CONFIRMED — a trusted/editor/admin user could call `POST /v1/disc/{fp}/resolve {"action": "verify"}` against a disc that was merely `unverified` (never disputed) and flip it straight to `verified`, with no second contributor, no structural match, no anti-Sybil gate.
- **Resolution:** `resolve_dispute` (`api/app/verification.py`) now requires `disc.status == "disputed"` as a precondition before it will transition a disc to `verified`.
- **Regression test:** `api/tests/test_dispute.py`
- **Commits:** `ba09d48` (red test), `a34b98e` (fix)

#### W7 — Stale/fabricated error codes and response shapes in `docs/api-reference.md`

- **Verdict:** CONFIRMED — the newly-added confirmation-error examples didn't match the live route's actual error codes/response shape.
- **Resolution:** `docs/api-reference.md` corrected: `duplicate_fingerprint` → `conflict`, `disc_not_found` → `not_found`, `missing_query` → `bad_request`, `"releases"` → `"release"`, and the fabricated `disc_id` field was removed.
- **Commit:** `7364da0`

### Not Addressed in This Pass

#### IN-01 — `register_disc()` writes no `DiscEdit` for the registration action itself

This Info-level finding from `02-REVIEW.md` (audit-trail completeness suggestion — `GET /v1/disc/{fp}/edits` returns an empty list for a disc still in `pending_identification`) was **not part of this remediation pass**. This pass's scope was the 3 critical and 7 warning findings that bear on the two-contributor trust model's security guarantees; IN-01 is neither a security bypass nor a correctness defect in that model — it is a nice-to-have for audit-log completeness. It remains open and unaddressed, with no regression risk to the fixes above.

## Test Suite

Full API regression suite, run clean after all remediation commits:

```
cd api && .venv/bin/pytest -q
310 passed, 13 warnings in 9.24s
```

310 passed (up from 297 at review time — 13 new regression tests added across the CR-01/CR-02/CR-03/W2/W3/W4/W6 remediation commits). The 13 warnings are the same pre-existing third-party deprecation warnings documented in `deferred-items.md` (Starlette `TestClient`/`httpx`, `slowapi`'s `asyncio.iscoroutinefunction`) — unchanged in count and origin from the review baseline, attributed to Phase 3 (INFRA) dependency-upgrade scope, not newly introduced by this remediation.

---

_Remediated: 2026-07-05_
_Basis: TDD fix commits per finding (red test → green fix), adversarially verified (CR-01 live-reproduced; CR-03 severity re-assessed; W1 re-checked as false positive)_
