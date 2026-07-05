# Phase 2: Two-Contributor Verification Workflow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-05
**Phase:** 2-Two-Contributor Verification Workflow
**Mode:** advisor (research-backed comparison tables) · calibration tier: standard
**Areas discussed:** Confirmation mechanism, Anti-Sybil signals, Withholding unverified payload, Confirmation rate-limit seam vs Phase 3

---

## Confirmation mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Structural re-submission | Confirmer re-runs their own disc, re-submits via POST /v1/disc; server verifies on full structural-payload match. Retire/role-gate the bodyless /verify route. | ✓ |
| Structural + ARM echo shortcut | Same, plus a fingerprint-echo confirm restricted to trusted/automated flows (ARM) only. | |
| Keep one-click /verify | Leave the current bodyless verify route (trusts a distinct account). | |

**User's choice:** Structural re-submission.
**Notes:** Follow-up: existing bodyless `POST /v1/disc/{fp}/verify` route → **retire entirely**, re-submission is the only path (confirmation is inherently a CLI/ovid-client action; web UI can't read discs). Follow-up: match strictness → **normalized/tolerant structural equality** (tolerant of benign rip jitter, avoids false disputes). Research finding: current `_releases_match` compares only public release-level fields, so the match must be upgraded to structural equality to have any anti-echo value.

---

## Anti-Sybil signals (VERIFY-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Weighted score, /24-hashed IP, fail-open | Rate-limit hard-blocks; account-age + IP-diversity soft/offsetting. Salted /24-truncated IP hash, ~90-day retention, privacy addendum. Fail-open on missing signals. | ✓ |
| Hard-block per signal | Reject if any single signal fails. Deterministic but risks blocking legit early/same-household confirmations. | |
| Account-age gate only (no IP) | Gate on age + rate limit, collect no IP. Simplest, zero privacy surface, but weakest. | |

**User's choice:** Weighted score, /24-hashed IP, fail-open.
**Notes:** Concrete thresholds (account-age cutoff, cooldown counts, retention) left as tunable starting defaults for research/planning to validate — no fraud data to calibrate on yet. Privacy: GDPR treats IP as personal data even hashed → salted + /24 (v4) / /48 (v6) truncation + short retention + privacy-policy addendum (OVID stores no IP today).

---

## Withholding unverified payload (criterion 4)

| Option | Description | Selected |
|--------|-------------|----------|
| Redacted 200 | Return fingerprint/status/confidence/release; withhold titles/chapters/tracks for unverified discs. | ✓ |
| Full hide (404) | Unverified discs return 404, indistinguishable from unknown. | |
| Submitter-visible-only | Redact for everyone except the original submitter (needs new optional-auth path). | |

**User's choice:** Redacted 200.
**Notes:** Research finding: `arm/identify_ovid.py::_extract_result()` reads only release-level fields, so withholding `titles` is a no-op for ARM. Follow-up: `fingerprint_aliases` → **stay visible** on unverified discs (identity strings, not structural payload; primary fp is already public; preserves Phase 1 IDENT-01 uniformly). Submitter-preview-of-own-pending-upload explicitly deferred as a later UX call, not a Phase 2 security requirement.

---

## Confirmation rate-limit seam vs Phase 3

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres per-account cooldown | Count/cooldown off existing disc_edits rows. Worker-safe regardless of Phase 3 order; co-locates with weighting; no rework when Phase 3 adds Redis. | ✓ |
| In-memory slowapi now | Reuse existing slowapi limiter — Nx-inflated under multi-worker gunicorn per its own docstring. | |
| Defer throttling to Phase 3 | Ship only weighting signals; let Phase 3 own confirmation throttling (no phase dependency guarantees it closes). | |

**User's choice:** Postgres per-account cooldown.
**Notes:** Closes VERIFY-04 standalone regardless of Phase 3's order (Phase 3 has no dependency on Phase 2). Distinct mechanism from the general slowapi limiter Phase 3 hardens with Redis — needs a doc note so the two aren't mistaken for redundant.

---

## Claude's Discretion

- Exact anti-Sybil threshold values (shape locked: weighted, soft signals + hard cooldown floor, fail-open; numbers tunable).
- Confirmation-cooldown storage: index-on-`disc_edits` vs small dedicated table.
- Exact structural-tolerance envelope for the normalized match.

## Deferred Ideas

- Web-UI confirm affordance / submitter preview of own pending upload → Phase 7 / later UX.
- Redis-backed multi-worker rate limiting + p95 load validation → Phase 3.
- Full reputation / edit-voting system → v0.4.0.
- Cross-table fingerprint-registry arbitration (WR-02) → Phase 5.
