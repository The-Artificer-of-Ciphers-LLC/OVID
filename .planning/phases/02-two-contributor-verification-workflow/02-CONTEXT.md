# Phase 2: Two-Contributor Verification Workflow - Context

**Gathered:** 2026-07-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the two-contributor trust model **live end-to-end and resistant to cheap Sybil abuse**, without the deferred v0.3.0 dispute-flagging UI. A disc stays `unverified` until a second, distinct contributor **independently reproduces its structural fingerprint from a physical disc**; self-confirmation is rejected; an already-`verified` disc cannot be flipped back except via the explicit dispute path; and the unverified structural payload is withheld from public reads so a sockpuppet cannot "confirm" by echoing what the first submitter uploaded.

**Requirements:** VERIFY-01, VERIFY-03, VERIFY-04.

**Already built in Phase 1 — hardened/tested here, not re-decided:**
- `api/app/verification.py` consolidated state machine: `verify(db, disc, actor)` with self-verification guard (`submitted_by == actor.id` rejected), `flag_dispute()` as the sole writer of `disputed`, `resolve_dispute()`, and the `LEGAL_TRANSITIONS` frozenset (no entry targets `disputed` outside the dispute path). VERIFY-01's "distinct contributor / no self-confirm" and VERIFY-03's "no silent flip of verified" are largely enforced already — Phase 2 adds behavior tests and the confirmation-mechanism + anti-Sybil layers on top.

**Not built yet — the real Phase 2 work:**
- Confirmation that requires proof of physical possession (today the bodyless `POST /v1/disc/{fp}/verify` route flips status on a bare bearer token).
- VERIFY-04 anti-Sybil weighting (no IP captured, no account-age gating today; rate limits are in-memory only).
- Criterion 4 payload withholding (`_disc_to_response()` returns the full structure unconditionally today).

**Out of scope (belongs to other phases):**
- Redis-backed / multi-worker-correct rate limiting and p95 load validation → Phase 3 (INFRA-01..04). Phase 2 owns only the trust-model confirmation cooldown (see D-13).
- Community dispute-flagging UI → deferred to v0.3.0 (PRD).
- Web-UI confirm surface → Phase 7 (and confirmation is inherently a CLI action anyway — see D-02).
- Cross-table fingerprint-registry arbitration (WR-02) → Phase 5 (user-scoped there).
</domain>

<decisions>
## Implementation Decisions

### Confirmation mechanism
- **D-01:** Confirmation is **structural re-submission via `POST /v1/disc`**. A second, distinct contributor re-runs their own physical disc through `ovid-client` and re-submits the full independently-computed payload; the server verifies the disc (`unverified → verified`) when that payload matches. This reuses the existing `_handle_existing_disc` → `verify()` wiring. The confirmer must reproduce structure that is **withheld from public reads** (D-08), so the match is real proof of possession, not an echo.
- **D-02:** **Retire the bodyless `POST /v1/disc/{fingerprint}/verify` route entirely.** Re-submission is the *only* confirmation path. Rationale: under D-01 confirmation requires computing a fingerprint from a physical disc, which the web UI can never do (it doesn't read discs) — so confirmation is inherently a CLI/`ovid-client` action, and a no-proof verify endpoint is a pure Sybil bypass with no legitimate caller. Removing it also deletes the weakest link in the two-contributor story.
  - **Planner note:** audit callers of `/verify` before removal (web UI, tests, docs, ARM). The web UI "confirm" affordance, if any exists/was planned for Phase 7, must be reframed — the UI can surface *verification status* but cannot itself confirm.
- **D-03:** The match that triggers verification is **normalized/tolerant structural equality**, not byte-exact. Compare the normalized disc structure (title count, main-feature marker, per-title chapter counts, audio/subtitle track layout) after canonical ordering and any rounding already used in fingerprinting — tolerant of benign independent-rip jitter (track ordering, minor label variance) so two genuine rips don't false-trigger `disputed`. Today `_releases_match` compares only release-level `title`/`year`/`tmdb_id` (which are publicly searchable) — this must be **upgraded to structural equality**, otherwise the "match" gates on public data and proves nothing once the payload is withheld.
  - **Planner note:** define the tolerance envelope explicitly and test it against the disputed-vs-verified boundary (a real mismatch must still → the dispute path, not silently verify).

### Anti-Sybil independence signals (VERIFY-04)
- **D-04:** Enforcement is a **weighted trust score**, not per-signal hard-block. The **confirmation rate-limit / cooldown hard-blocks** (it has no legitimate-user false-positive story); **account-age and IP-diversity are soft, offsetting signals** above a threshold, so e.g. a same-household confirmer on a shared IP but with an established, well-behaved account still passes. This matches VERIFY-04's own wording ("baseline anti-Sybil *weighting*") and keeps the door open to the v0.4.0 reputation system without building it now.
- **D-05:** A merely-distinct `user_id` is **never by itself** accepted as proof of independence (VERIFY-04 core).
- **D-06:** **IP privacy:** do NOT store raw IP. Store a **salted hash truncated to the /24 subnet (IPv4) / /48 (IPv6)**, with a short retention window (~90-day fraud-prevention basis), documented as a **privacy-policy addendum** (OVID stores no IP anywhere today — this is a new data category and must be disclosed; consistent with the CC0 / minimal-data legal posture). Under GDPR an IP is personal data even when hashed, so truncation + salt + retention limit is the pseudonymization floor.
- **D-07:** **Fail-open** when a signal is unavailable (proxied client, missing IP, brand-new but genuine account) — an absent signal must never itself count against the confirmer, because the userbase is smallest and least tolerant of false rejections at launch. The confirmation rate-limit/cooldown (D-13) is the launch-safe floor that still holds when every soft signal is absent.
- **D-08 (starting thresholds — VALIDATE in research, not hard-locked):** No fraud data exists to calibrate yet, so the planner/researcher proposes and the executor implements *tunable* starting values, surfaced as named constants/config (not magic numbers):
  - account-age soft signal: reduced trust weight for accounts younger than a small cutoff (starting point ~24h) — soft, offsettable, never a hard reject on its own.
  - IP-diversity soft signal: confirmer's /24-hash distinct from submitter's contributes positive trust; same-subnet is a *penalty*, not a block.
  - confirmation cooldown / rate: a conservative per-account cap on confirmation actions (starting point on the order of a handful per hour / low-tens per day) — this is the hard-block floor.
  - These are launch-safe defaults; document them and their tuning rationale, and make them easy to adjust once real usage data exists.

### Withholding the unverified payload (criterion 4)
- **D-09:** **Redacted-200** shape. `GET /v1/disc/{fingerprint}` for an `unverified` disc returns **200** with `fingerprint`, `status="unverified"`, `confidence`, `release` (title/year/imdb/tmdb) — and **withholds** the structural payload (`titles`, main-feature marker, chapters, audio/subtitle tracks). Not a 404 (that conflates "pending" with "never submitted" and hides existence from a would-be confirmer). This closes the echo vector while giving ARM/consumers a clear "known but not yet usable" signal.
- **D-10:** **Verified against ARM:** `arm/identify_ovid.py::_extract_result()` reads only release-level fields (`fingerprint`, `release.{title,year,imdb_id,tmdb_id}`, `confidence`, `format`) and never touches `titles`/tracks — so withholding structure for unverified discs is a **no-op for ARM's current behavior**. Confirm this still holds during planning (don't regress ARM).
- **D-11:** **Aliases stay visible** on unverified discs. `fingerprint_aliases` are identity strings (alternate fingerprints), not structural payload, and the primary fingerprint is already public (it's the URL path segment) — withholding aliases gains no anti-echo protection and would diverge from Phase 1 IDENT-01's uniform exposure. Keep IDENT-01 behavior for aliases regardless of verification status.
- **D-12:** Implementation is a **status branch in `_disc_to_response()`** plus a schema change making the structural fields optional/omittable (`titles` currently non-optional-shaped in `schemas.py`). No new auth dependency — the redaction is uniform for all readers (anonymous, confirmer, and — for this phase — the original submitter too). "Should the submitter preview their own pending upload" is a **separate later UX decision**, explicitly not in Phase 2's security scope (avoid inventing an optional-auth path on the currently-anonymous, cacheable GET).

### Confirmation rate-limit seam vs Phase 3
- **D-13:** VERIFY-04's rate-limit clause is implemented as a **Postgres-backed per-account confirmation cooldown/counter**, built on the existing `disc_edits` audit rows (`edit_type="verify"`, `user_id`, `created_at`) — a `COUNT`/`MAX(created_at)` query plus an index (or a small dedicated table). This is **worker-safe by construction** (Postgres is already the single shared source of truth across all gunicorn workers), so VERIFY-04 is closed **correctly and standalone regardless of Phase 3's order** (Phase 3 has no dependency on Phase 2 and may land before or after).
- **D-14:** This is a **distinct mechanism** from the general slowapi API limiter that Phase 3 hardens with Redis (INFRA-01/04). They serve different purposes — general API-abuse throttling vs. a permanent trust-model confirmation cooldown — and nothing built here needs revisiting when Phase 3 swaps slowapi's storage to Redis. Add a one-line doc note distinguishing the two so they aren't mistaken for redundant. **Do NOT** use the in-memory slowapi limiter for the confirmation guardrail (it is Nx-inflated under multi-worker gunicorn per `rate_limit.py`'s own docstring — a hollow guardrail on the real prod target).

### Claude's Discretion
- Exact anti-Sybil threshold values (D-08) — propose launch-safe defaults during research/planning; the *shape* (weighted, soft signals + hard cooldown floor, fail-open) is locked, the *numbers* are tunable.
- Whether the confirmation cooldown lives as an index-on-`disc_edits` query vs. a small dedicated table (D-13) — implementation choice for the planner.
- Exact structural-tolerance envelope for D-03 — planner defines and tests it against the verify/dispute boundary.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Verification trust model & requirements
- `.planning/REQUIREMENTS.md` — VERIFY-01, VERIFY-03, VERIFY-04 (and the "Explicit non-goals" table row on self-verification). The authoritative requirement text and phase mapping.
- `.planning/ROADMAP.md` §"Phase 2" — goal, the four success criteria, and the Phase 2↔Phase 3 boundary.
- `docs/OVID-product-spec.md` — Milestone 0.2 exit criteria (two-contributor verification is a v0.2.0 exit item); source of truth for the milestone.

### Phase 1 foundation (state machine + carried decisions)
- `api/app/verification.py` — the consolidated state machine Phase 2 builds on: `verify()`, `flag_dispute()`, `resolve_dispute()`, `identify()`, `LEGAL_TRANSITIONS`, self-verification guard. Do not re-implement; extend/harden.
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-CONTEXT.md` — Phase 1 decisions (D-09 disputed-writer rule, D-11 self-verification guard placement, idempotent-200 verify contract, A2 mismatch-stays-verified contract).
- `.planning/phases/01-alias-layer-hardening-repo-hygiene/01-REVIEW.md` — context for the verification consolidation; note WR-02 (cross-table fingerprint arbitration) is **Phase 5-scoped**, not Phase 2.

### Identity / lookup surface touched by this phase
- `api/app/routes/disc.py` — `submit_disc`, `_handle_existing_disc`, `_releases_match`, `verify_disc` (to be retired per D-02), `_disc_to_response` (redaction site per D-09/D-12), `GET /v1/disc/{fingerprint}`.
- `api/app/schemas.py` — `DiscLookupResponse` / `TitleResponse` (make structural fields optional per D-12); `DiscSubmitRequest`.
- `api/app/models.py` — `Disc` (`status`, `submitted_by`, `verified_by`), `User` (`created_at`, `verification_count`), `DiscEdit` audit table (cooldown source per D-13).
- `api/app/rate_limit.py` — the general slowapi limiter (Phase 3's territory; do NOT hang the VERIFY-04 guardrail on it — see D-14).
- `arm/identify_ovid.py` — `_extract_result()` (confirm withholding stays a no-op for ARM per D-10).
- `docs/adr/0001-stage-libdvdread-disc-identity-migration.md` — the alias/identity model that structural re-submission (D-01) must stay consistent with; `dvd1-*` must remain resolvable.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `api/app/verification.py` state machine (Phase 1): `verify(db, disc, actor)` already enforces distinct-contributor + `LEGAL_TRANSITIONS`; `flag_dispute()` is the sole `disputed` writer. Phase 2 layers the confirmation-proof and anti-Sybil gate around it, not inside the transition primitives.
- `_handle_existing_disc` → auto-verify wiring in `routes/disc.py` (calls `verify()` when a second submitter's fingerprint resolves to the same disc) — this is the hook D-01 extends by upgrading the match from release-level to structural equality.
- `disc_edits` audit table already records every confirmation (`edit_type="verify"`, `user_id`, `created_at`) — free backing store for the Postgres confirmation cooldown (D-13).
- `User.created_at` exists (account-age signal, D-04/D-08). `User.verification_count` exists (a counter, may inform weighting).

### Established Patterns
- Consistent JSON error/response envelope with `request_id` + `x-request-id` header — new/redacted responses must preserve it.
- Idempotent-200 verify contract and the A2 "mismatch against a verified disc stays verified (200), records a `DiscEdit`, never silently disputed" contract (Phase 1) — Phase 2 must not regress these.
- Race-safe insert pattern from Phase 1 (insert-first / catch `IntegrityError` / re-resolve inside `db.begin_nested()` SAVEPOINTs) — any new write path (IP-hash row, cooldown counter) should follow it under concurrent confirmation load.
- Method derived from fingerprint prefix via `_method_of()` — no method column (D-04, Phase 1).

### Integration Points
- Redaction lives in `_disc_to_response()` (status branch) + `schemas.py` (optional structural fields).
- New IP-hash capture at the submission/confirmation request boundary (needs `request.client.host` → salted /24 hash; today only used ephemerally by `rate_limit.py`, never persisted).
- Confirmation cooldown check sits in the confirmation path (`submit_disc`/verify flow) before `verify()` is allowed to fire.
- New Alembic migration(s): IP-hash storage + any cooldown index/table.
</code_context>

<specifics>
## Specific Ideas

- The guiding threat model, stated by the user: withholding the payload is an **anti-echo defense** — it forces the confirmer to compute the fingerprint/structure from a real disc rather than copying the first submitter's upload. Every decision above is coherent with that: structural re-submission (D-01) + normalized match (D-03) require reproducing exactly the data that redacted-200 (D-09) hides.
- Keep the guardrail **launch-safe**: with ~500 seeded entries and a handful of real early contributors, a too-strict gate that blocks legitimate first confirmations is treated as a failure mode, hence weighted + fail-open (D-04/D-07).
</specifics>

<deferred>
## Deferred Ideas

- **Web-UI "confirm" affordance / submitter preview of own pending upload** — surfaced during D-02/D-12. Web UI is Phase 7; confirmation itself can't happen in-browser (no disc read). "Submitter previews their own withheld structure" is a later opt-in UX decision, not a Phase 2 security requirement.
- **Redis-backed / multi-worker rate limiting + p95 load validation** — Phase 3 (INFRA-01..04). Phase 2's Postgres cooldown (D-13) is deliberately independent of it.
- **Full reputation / edit-voting system** — deferred to v0.4.0 per PRD. The weighted-score primitives (D-04) are a deliberate seed, not that system.
- **Cross-table fingerprint-registry arbitration (WR-02)** — Phase 5-scoped (promotion increases write concurrency on the shared fingerprint namespace); not Phase 2.

</deferred>

---

*Phase: 2-Two-Contributor Verification Workflow*
*Context gathered: 2026-07-05*
