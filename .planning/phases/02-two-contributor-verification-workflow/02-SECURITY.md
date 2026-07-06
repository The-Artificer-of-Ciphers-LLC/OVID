---
phase: 02-two-contributor-verification-workflow
audited: 2026-07-05
asvs_level: 1
block_on: high
threats_total: 24
threats_closed: 23
threats_open: 0
threats_open_nonblocking: 1
informational_non_security: 2
status: SECURED
re_audit: post-remediation (accounts for 02-REVIEW.md / 02-REVIEW-FIX.md deep-review findings in addition to PLAN.md threat models)
---

# Phase 2: Security Audit — Two-Contributor Verification Workflow

**Audited:** 2026-07-05
**ASVS Level:** 1 (grep/presence-level — mitigation must be present in the cited file at the correct boundary)
**block_on:** high (only `high`/`critical` OPEN threats block ship)
**Suite:** `cd api && .venv/bin/pytest -q` independently re-run during this audit → **310 passed**, 13 pre-existing third-party deprecation warnings (documented in `deferred-items.md`, unrelated to this phase's security surface).

## Scope note

This audit covers two overlapping sources of threats, per explicit instruction:

1. The **PLAN-authored STRIDE registers** in `02-01-PLAN.md` through `02-05-PLAN.md` (`<threat_model>` blocks) — 16 unique threat IDs.
2. The **review-surfaced findings** from the mandated deep code review (`02-REVIEW.md`) and its remediation (`02-REVIEW-FIX.md`) — CR-01, CR-02, CR-03, W2, W3, W4, W5, W6, IN-01 — which found the two-contributor trust model was bypassable in the initial implementation and were then fixed TDD-style (test suite 297 → 310 passing). Every fix claimed by `02-REVIEW-FIX.md` was independently re-verified against the current source in this audit — not trusted from prose.

No blindly-invented new threats are included; every entry below traces to a PLAN threat register or a review finding.

## PLAN-Authored Threat Register

| Threat ID | Category | Component | Severity | Disposition | Status | Evidence |
|-----------|----------|-----------|----------|-------------|--------|----------|
| T-2-01 | Spoofing | `structural_match` verify gate + `_disc_to_response` read redaction | high | mitigate | CLOSED | `api/app/structural_match.py:59-98` (gate over withheld structure); `api/app/routes/disc.py:353-355` (wired as AND with `_releases_match` before `verify()`); `api/app/routes/disc.py:481-485` (redaction withholds structure from unverified reads — read-side half). CR-02 fix (below) closes the vacuous zero-title bypass of this same gate. |
| T-2-02 | Spoofing/Elevation | Sybil farm rapid confirmation | high | mitigate | CLOSED | `api/app/anti_sybil.py:233-247` (Postgres-backed cooldown, `>=` after W4 fix, `with_for_update()` actor lock after W3 fix at line 231); wired pre-check `api/app/routes/disc.py:322-336` (429 `rate_limited` + `Retry-After`, before any status write). |
| T-2-03 | Spoofing | Same-operator confirmer, same /24 | medium | mitigate | CLOSED | `api/app/anti_sybil.py:258-266` (weighted score, `SAME_SUBNET_PENALTY`/`DISTINCT_SUBNET_BONUS`); wired `api/app/routes/disc.py:337-346` (403 `insufficient_trust`). CR-03 fix (below) makes the underlying IP signal meaningful in production rather than constant. |
| T-2-03a | Tampering | Tolerance envelope (D-03) | medium | mitigate | CLOSED | `api/app/structural_match.py` (chapter/main-feature exact match, track multisets, duration tolerance); `api/tests/test_structural_match.py` 9/10 boundary tests independently re-run, all pass. |
| T-2-04 | Tampering | X-Forwarded-For spoofing to fake IP diversity | medium | mitigate | CLOSED | `api/app/anti_sybil.py` design: IP contributes only `±1` to a score whose only hard-block combination is fresh-account+same-subnet; the cooldown hard floor (`_recent_confirmation_count`, lines 149-168) never reads IP at all, so spoofing IP cannot bypass the hard floor, only shift the soft score in the confirmer's favor at worst. |
| T-2-05 | Elevation of Privilege | Original submitter self-verifies | high | mitigate | CLOSED | `api/app/verification.py:50-51` (`verify()` self-guard); `api/app/routes/disc.py:311-318` (same-submitter 409). CR-01 fix (below) closes the register→identify→resubmit bypass of this exact guard. `api/tests/test_identify_self_confirm.py` 2/2 independently re-run, pass. |
| T-2-06 | Tampering | Third party silently flips verified→disputed | high | mitigate | CLOSED | `api/app/verification.py:79-89` (`flag_dispute()` no-ops on verified, only writer of `disputed`); `api/app/routes/disc.py:408-434` (A2 `dispute_attempted` audit branch, 200 `status: verified`, never silent). W6 fix (below) closes an adjacent single-actor flip vector via `/resolve`. |
| T-2-07 | Information Disclosure | Raw IP leaked via DB/logs | high | mitigate | CLOSED | `api/app/anti_sybil.py:99-113` (`ip_subnet_hash` — salted HMAC-SHA256 over /24 or /48 truncated network address only); `api/app/models.py:381` (`ip_hash: String(64)`, nullable) — no code path found that stores/logs `request.client.host` or raw XFF value directly. |
| T-2-08 | Elevation | Cooldown bypass via multi-worker in-memory limiter | high | mitigate | CLOSED | `api/app/anti_sybil.py:149-168` (`_recent_confirmation_count` is a Postgres `COUNT` over `disc_edits`, not slowapi's in-memory limiter). W3 fix adds `with_for_update()` (line 231) closing the check-then-act race across concurrent requests from the same actor. |
| T-2-09 | Elevation | No-proof `POST /{fp}/verify` endpoint | high | mitigate | CLOSED | Grep independently re-run: `grep -rn "verify_disc" api/app/` → no matches; `grep -n "fingerprint}/verify" docs/*.md` → no matches. `api/tests/test_route_retired.py` 3/3 independently re-run, pass (404/405). `api/tests/test_disc_verify.py` confirmed deleted (absent from `api/tests/`). |
| T-2-10 | Information Disclosure | Over-redaction breaking disputed/verified/sync | medium | mitigate | CLOSED | `api/app/routes/disc.py:481-485` — single `disc.status == "unverified"` branch, no other status branch; `api/tests/test_lookup_redaction.py::test_verified_titles_populated` and `::test_disputed_titles_populated` independently re-run, pass; `sync.py` not in any plan's `files_modified`, untouched. |
| T-2-11 | Information Disclosure | Redaction accidentally hiding identity aliases | low | mitigate | CLOSED | `api/app/routes/disc.py:491-504` — `fingerprint_aliases_resp` built unconditionally, no status branch; `test_lookup_redaction.py::test_unverified_keeps_aliases` passes. |
| T-2-07d | Information Disclosure | Undisclosed IP-hash data category | medium | mitigate | CLOSED | `docs/privacy.md:32-67` discloses salted/24-/48-truncated hash, GDPR basis, `OVID_IP_HASH_SALT`; `.env.example:98` documents the var as optional. |
| T-2-09d | Repudiation | Docs advertising retired `/verify` route | low | mitigate | CLOSED | Independently re-grepped: no `fingerprint}/verify` string in `docs/api-reference.md`, `docs/docker-quickstart.md`, `docs/OVID-technical-spec.md`; `docs/contributing.md:18,37` reframed to `ovid submit` re-submission. |
| T-2-14 | Tampering | Phase 3 mistaking cooldown for general limiter | low | mitigate | CLOSED | `docs/privacy.md:87-95` "Confirmation cooldown vs. general API rate limiting" section explicitly distinguishes the Postgres cooldown from the Phase 3 Redis/slowapi limiter. |
| T-2-SC | Tampering | Package installs (supply chain) | low | accept | CLOSED (accepted risk, logged below) | `git log --oneline -- api/requirements.txt` shows no commit in the Phase 2 commit range touched `requirements.txt` (last change predates the phase, Phase-1 Valkey/gunicorn work); independently confirmed no new third-party package was introduced. |

## Review-Surfaced Threats (post-implementation deep review + remediation)

These were not in any PLAN's `<threat_model>` — they surfaced from a mandated adversarial code review after initial implementation, which found the two-contributor trust model was bypassable. Each fix claimed by `02-REVIEW-FIX.md` was independently re-verified against current source (not trusted from the remediation prose).

| Threat ID | Category | Component | Severity | Disposition | Status | Evidence |
|-----------|----------|-----------|----------|-------------|--------|----------|
| CR-01 | Elevation of Privilege | Self-confirmation via register→identify→resubmit | critical | mitigate | CLOSED | `api/app/routes/disc.py:215` — `existing.submitted_by = current_user.id` set in `_identify_existing_disc` at the point metadata is first attached, so both self-confirm guards (`verification.py:50`, `disc.py:311`) compare against the actual metadata author, not a stale registrant. `api/tests/test_identify_self_confirm.py::test_identifier_cannot_self_confirm_after_register` and `::test_distinct_third_user_can_still_confirm` independently re-run, both pass. Adversarial verifier live-reproduced this exploit pre-fix per `02-REVIEW-FIX.md`. |
| CR-02 | Spoofing | Zero-title vacuous `structural_match` (echo attack) | critical | mitigate | CLOSED | `api/app/structural_match.py:83-84` — `if not stored_titles or not body.titles: return False` closes the vacuous-True path when both sides have zero titles. `api/tests/test_structural_match.py::test_empty_titles_both_sides_no_match` and `api/tests/test_disc_submit.py::test_duplicate_zero_title_submission_does_not_auto_verify` independently re-run, both pass. Stale fixtures in `test_disc_edits.py` that had encoded the bug were repaired per the remediation record. |
| CR-03 | Information Disclosure / Spoofing | Anti-Sybil IP-diversity dead (constant) behind the documented production reverse proxy | critical → downgraded to high (per adversarial verifier: fail-open availability/signal-integrity defect, not a newly-reachable exploit path beyond CR-01/CR-02) | mitigate | CLOSED | `docker-compose.prod.yml:34-36` — gunicorn now runs with `--forwarded-allow-ips "${OVID_FORWARDED_ALLOW_IPS:-127.0.0.1}"`. Independently traced the mechanism: `uvicorn.workers.UvicornWorker.__init__` (`api/.venv/lib/python3.14/site-packages/uvicorn/workers.py:52`) passes `forwarded_allow_ips=self.cfg.forwarded_allow_ips` straight into the `uvicorn.Config` used to serve the ASGI app — confirming gunicorn's `--forwarded-allow-ips` CLI flag genuinely reaches uvicorn's proxy-header trust layer for `request.client.host`, not merely a WSGI-only setting. `.env.example:83` documents `OVID_FORWARDED_ALLOW_IPS`; `docs/deployment.md:207` adds the operator note to confirm the actual observed peer IP rather than assume a default. |
| W6 | Elevation of Privilege | Single-actor verify-bypass via `POST /{fp}/resolve` | high | mitigate | CLOSED | `api/app/verification.py:98-109` — `resolve_dispute()` now raises `VerificationTransitionError` unless `disc.status == "disputed"`, closing the path where a trusted/editor/admin could flip a merely-`unverified` disc straight to verified with no second contributor, no structural match, no anti-Sybil gate. `api/app/routes/disc.py:607-610` catches the exception → 409. `api/tests/test_dispute.py::test_resolve_non_disputed_disc` independently re-run, passes. |
| W2 | Information Disclosure (soft-signal integrity) | Identify-path audit edit missing `ip_hash` | medium | mitigate | CLOSED | `api/app/routes/disc.py:233` — `ip_hash=client_ip_hash(request)` now captured on the `"identify"` `DiscEdit`, consistent with the `"create"` edit, so the IP-diversity signal is no longer silently disabled for the ARM register→identify path. `api/tests/test_confirmation_flow.py::test_identify_disc_edit_carries_ip_hash` independently re-run, passes. |
| W3 | Elevation (defense-in-depth) | Confirmation cooldown check-then-act race | medium | mitigate | CLOSED | `api/app/anti_sybil.py:231` — `db.query(User).filter(User.id == actor.id).with_for_update().first()` locks the actor's row before counting recent confirmations, serializing concurrent requests from the same actor on PostgreSQL (mirrors `next_seq()` in `sync.py`). Per the module's own comment (lines 212-230) this is inert on the SQLite test engine (dialect omits the clause) and is not independently unit-testable there — verified by direct code inspection rather than a passing concurrency test; documented as a bounded rate-limit hardening, not a new authorization bypass (VERIFY-02 keeps every status write in `verification.py` regardless of this gate's outcome). |
| W4 | Elevation | Cooldown off-by-one (hourly + daily) | medium | mitigate | CLOSED | `api/app/anti_sybil.py:245-247` — both comparisons changed from `>` to `>=`, so `CONFIRMATION_MAX_PER_WINDOW`/`_PER_DAY` are now the true ceilings. `api/tests/test_anti_sybil.py::test_at_exactly_max_per_window_next_confirmation_hard_blocked` and `::test_at_exactly_max_per_day_next_confirmation_hard_blocked` independently re-run, both pass (exact-boundary case now asserted). |
| W5 | Information Disclosure / Privacy (retention hygiene) | No automated IP-hash retention/purge job, despite `docs/privacy.md` originally asserting a ~90-day enforced window | medium (assigned — see reasoning below) | accept (documented risk) | **OPEN — non-blocking** (below `block_on: high` threshold) | `docs/privacy.md:49-58` was corrected to honestly state purge is **not yet implemented** ("Do not assume IP-hashes are automatically purged after 90 days on any OVID instance today") rather than asserting an enforced window the code doesn't back. No purge job exists anywhere in `api/app/`, `api/scripts/`, or Alembic migrations — confirmed by inspection. **Severity reasoning:** this is a data-retention/compliance-hygiene gap, not an exploitable authorization or disclosure bypass — the underlying data is already minimized at rest (salted, /24-/48-truncated HMAC-SHA256, never raw IP; `T-2-07` above), so failure to purge only extends the retention window of already-pseudonymized data rather than opening any new access path or granting any new capability. Assigned `medium`, explicitly below the `block_on: high` gate — does not count toward `threats_open`. Tracked as a candidate for Phase 3 infra work (a scheduled purge task), per `02-REVIEW-FIX.md`. |

## Informational (non-security) findings — not threats, not counted

| ID | Finding | Disposition |
|----|---------|-------------|
| IN-01 | `register_disc()` writes no `DiscEdit` audit row for the registration action itself (unlike `submit_disc`'s `"create"` edit and `_identify_existing_disc`'s `"identify"` edit) — confirmed present as described at `api/app/routes/disc.py:699-783` (no `db.add(DiscEdit(...))` call in the function body). | Audit-trail completeness gap only — explicitly not a security bypass (no threat ID, no STRIDE mapping): `GET /v1/disc/{fp}/edits` returns an empty list for a disc still `pending_identification`, but `disc.submitted_by`/`disc.created_at` still recover "who registered, when." Left open, no security impact, not part of `threats_open`. |
| W1 | `duration_secs` tolerance-check asymmetry originally flagged in `02-REVIEW.md` (WR-01) as skippable-by-omission. | **False positive**, confirmed by adversarial verifier and independently re-read in this audit: `api/app/structural_match.py:45-47` intentionally checks tolerance only when *both* sides supply a duration (fail-open on absent, symmetric with the phase's broader D-07 "absent signal never counts against confirmer" principle) — this is a deliberate design choice, not asymmetric handling of the *stored* value, since `chapter_count`/`is_main_feature`/track-multisets (which are NOT optional-by-omission in the same way) still form the bulk of the proof-of-possession bar. No code change; no open item. |

## Unregistered Flags (SUMMARY.md `## Threat Flags`)

`02-02-SUMMARY.md` and `02-03-SUMMARY.md` are the only SUMMARYs with a populated `## Threat Flags` section; both explicitly report **None** (no new network/auth/file surface beyond what's already threat-mapped in the PLAN registers above). `02-01-SUMMARY.md`, `02-04-SUMMARY.md`, `02-05-SUMMARY.md` have empty/absent sections. No unregistered flags found.

## Accepted Risks Log

| Threat ID | Risk | Reason Accepted | Owner / Next Action |
|-----------|------|------------------|----------------------|
| T-2-SC | New package supply-chain risk | No new third-party packages were installed across any of the 5 plans in this phase (`api/requirements.txt` last changed in Phase 1, confirmed via `git log`); each plan's own RESEARCH Package Legitimacy Audit found none. | N/A — re-evaluate if a future phase adds a dependency to this surface. |
| W5 | ~90-day IP-hash retention window has no automated enforcement | Data is already pseudonymized at rest (salted, subnet-truncated hash — see T-2-07); this is a retention/compliance-hygiene gap, not an access-control or disclosure bypass. Docs now honestly disclose the gap rather than overclaiming enforcement. | Candidate for Phase 3 infra work (scheduled purge job on `disc_edits.ip_hash` rows older than 90 days). |

## Test Evidence (independently re-run during this audit, not trusted from prose)

```
cd api && .venv/bin/pytest -q
310 passed, 13 warnings in 10.58s
```

Targeted re-runs, all pass:
- `test_identify_self_confirm.py` (2/2) — CR-01
- `test_structural_match.py` (10/10, incl. `test_empty_titles_both_sides_no_match`) — CR-02, T-2-01, T-2-03a
- `test_disc_submit.py -k zero_title` (1/1) — CR-02
- `test_dispute.py` (9/9, incl. `test_resolve_non_disputed_disc`) — W6, T-2-06
- `test_anti_sybil.py` (23/23, incl. both exact-boundary cooldown tests) — W4, T-2-02, T-2-07, T-2-08
- `test_confirmation_flow.py` (11/11, incl. `test_identify_disc_edit_carries_ip_hash`) — W2, T-2-01/02/03/05
- `test_route_retired.py` (3/3) — T-2-09
- `test_lookup_redaction.py` (7/7) — T-2-10, T-2-11

13 pre-existing warnings (`StarletteDeprecationWarning` from httpx/TestClient; `slowapi`'s `asyncio.iscoroutinefunction` deprecation) are third-party dependency deprecations, documented in `deferred-items.md`, unchanged in count/origin from the review baseline, and attributed to Phase 3 (INFRA) dependency-upgrade scope — not a security finding of this phase.

## Verdict

**SECURED.** All 16 PLAN-authored threats and all 8 review-surfaced critical/warning findings that bear on the trust model's security guarantees (CR-01, CR-02, CR-03, W6, W2, W3, W4) are CLOSED with independently-verified code evidence and passing regression tests. One item (W5) is an OPEN, non-blocking, documented-accepted risk below the `block_on: high` threshold (retention hygiene, not an exploitable bypass). One item (IN-01) is a non-security informational gap. `threats_open` (severity-filtered, gating value) = **0**.
