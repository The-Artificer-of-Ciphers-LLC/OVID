---
gsd_state_version: 1.0
milestone: v0.2.0
milestone_name: milestone
current_phase_name: OAuth & Account Linking
status: verifying
stopped_at: Completed 06-07-PLAN.md
last_updated: "2026-07-07T04:36:17Z"
last_activity: 2026-07-07 -- Phase 6 executed + security-review remediation (8 findings) applied; awaiting manual live-OAuth verification
progress:
  total_phases: 8
  completed_phases: 6
  total_plans: 35
  completed_plans: 35
  percent: 75
current_phase: 06
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-05)

**Core value:** Given a disc in any drive, OVID returns the correct disc identity and structure — deterministically and reproducibly — so ripping tools can name, tag, and route content without manual correction.
**Current focus:** Phase 06 — OAuth & Account Linking

## Current Position

Phase: 06 (OAuth & Account Linking) — EXECUTING
Current Phase Name: OAuth & Account Linking
Plan: 7 of 7
Status: Phase complete — ready for verification
Last activity: 2026-07-07 -- Phase 6 executed + security-review remediation (8 findings) applied; awaiting manual live-OAuth verification
Last Activity Description: Phase 6 executed + security-review remediation (8 findings) applied; awaiting manual live-OAuth verification

Progress: [███░░░░░░░] 38%

## Performance Metrics

**Velocity:**

- Total plans completed: 28
- Average duration: 25 min
- Total execution time: 0.4 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 6 | - | - |
| 02 | 5 | - | - |
| 3 | 4 | - | - |
| 04 | 6 | - | - |
| 05 | 7 | - | - |

*Updated after each plan completion*
| Phase 01 P02 | 15min | 3 tasks | 2 files |
| Phase 01 P05 | 15min | 2 tasks | 1 files |
| Phase 01 P06 | 3min | 3 tasks | 4 files |
| Phase 01 P03 | 30min | 3 tasks | 4 files |
| Phase 01 P04 | 10min | 3 tasks | 5 files |
| Phase 02 P01 | 15min | 2 tasks | 2 files |
| Phase 02 P02 | 6min | 3 tasks | 5 files |
| Phase 02 P03 | 6min | 3 tasks | 9 files |
| Phase 02 P04 | 6m | 2 tasks | 4 files |
| Phase 02 P05 | 10min | 2 tasks | 6 files |
| Phase 03 P01 | 9min | 3 tasks | 5 files |
| Phase 03 P02 | 10min | 2 tasks | 2 files |
| Phase 03 P03 | 35m | 2 tasks | 6 files |
| Phase 03 P04 | 22min | 3 tasks | 5 files |
| Phase 04 P01 | 30min | 2 tasks | 3 files |
| Phase 04 P02 | 15min | 2 tasks | 2 files |
| Phase 04 P04 | 10m | 1 tasks | 1 files |
| Phase 04 P03 | 25min | 2 tasks | 2 files |
| Phase 04 P05 | 20min | 2 tasks | 3 files |
| Phase 04 P06 | 8min | 2 tasks | 2 files |
| Phase 05 P01 | 5min | 2 tasks | 3 files |
| Phase 05 P02 | 10min | 2 tasks | 2 files |
| Phase 05 P03 | 15min | 1 tasks | 2 files |
| Phase 05 P04 | 20min | 3 tasks | 6 files |
| Phase 05 P05 | 4min | 2 tasks | 3 files |
| Phase 05 P06 | 20min | 3 tasks | 4 files |
| Phase 05 P07 | 20min | 2 tasks | 4 files |
| Phase 06 P01 | 3m | 2 tasks | 2 files |
| Phase 06 P02 | 5min | 2 tasks | 2 files |
| Phase 06 P03 | 7min | 2 tasks | 9 files |
| Phase 06 P04 | 18min | 2 tasks | 2 files |
| Phase 06 P05 | 18min | 3 tasks | 4 files |
| Phase 06 P06 | 16min | 2 tasks | 5 files |
| Phase 06 P07 | 165s | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Stage the libdvdread disc-identity migration (dvd1 primary → aliases → dvdread1 primary) per ADR 0001 — dvd1-* must stay resolvable
- Init: Include non-code v0.2.0 exit items (DNS redirects, announcement, ≥500-entry seeding) as roadmap tasks (Phase 8)
- Init: Move rate limiting to Redis-backed slowapi storage (multi-worker correctness)
- [Phase 01-01]: verify() returns False (not exception/400) for an already-verified disc — preserves route idempotent-200 contract (Pitfall 4)
- [Phase 01-01]: flag_dispute() is the sole writer of disc.status=disputed; LEGAL_TRANSITIONS has zero entries targeting disputed (D-09), closing the VERIFY-02 silent-flip bug
- [Phase 01-01]: Self-verification guard lives inside verify() as a transition invariant (D-11), not in the route layer
- [Phase 01-02]: Alias insert race fix = insert-first / catch sqlalchemy.exc.IntegrityError / re-resolve-the-winner inside per-insert db.begin_nested() SAVEPOINTs (D-01/D-03), closing IDENT-02
- [Phase 01-02]: A post-conflict re-resolve that unexpectedly returns None re-raises the original IntegrityError rather than swallowing it (no-wave-off rule) - a genuinely-unexpected state, not a legitimate race outcome
- [Phase 01-05]: D-16: dvd1-* identity regression asserts stable identity/structure, not the literal top-level fingerprint value, so the guardrail survives Phase 5 libdvdread alias promotion
- [Phase 01]: D-17/D-18/D-19 (01-06): deleted 4 disposable one-shot patch scripts, relocated run_uat.py/create_uat_dirs.py to scripts/ via git mv, untracked+gitignored uat_results.json/uat_dirs/ (git rm --cached required alongside gitignore per Pitfall 5)
- [Phase 01]: A2 contract: a mismatched submission against a verified disc records an audit DiscEdit and stays verified (200), never silently disputed (VERIFY-02 crit #4)
- [Phase 01]: Renamed the /resolve route handler to resolve_dispute_endpoint to free the resolve_dispute name for import from app.verification
- [Phase 01]: submit_disc's disc-row insert SAVEPOINT wraps the Release creation together with the Disc insert, so a losing race unwinds both instead of leaking an orphaned Release row
- [Phase 01-04]: method is derived from the fingerprint prefix via _method_of() in routes/disc.py — no method column, no Alembic migration (D-04)
- [Phase 01-04]: Deterministic alias ordering via order_by=(created_at, id) on Disc.identity_aliases — primary-first then insertion order, never string-sorted (D-06)
- [Phase ?]: 02-01: Verify gate compares WITHHELD stored structure, never public release fields (D-01/D-03 proof-of-possession)
- [Phase ?]: 02-01: Tracks compared as codec-normalized multisets; duration fails open when unknown
- [Phase ?]: VERIFY-04 anti-Sybil gate (anti_sybil.py): Postgres cooldown floor over disc_edits verify rows + salted /24//48 HMAC-SHA256 IP hash + weighted fail-open trust score; salt optional-with-warning (D-07), cooldown via index-on-disc_edits COUNT with Python cutoff bound param (D-13/D-14)
- [Phase 02]: 02-04: Anti-echo redaction is a single status branch in _disc_to_response — titles withheld only for status==unverified; release + fingerprint_aliases stay visible for all statuses (D-09/D-11/D-12).
- [Phase 02]: 02-04: Confirmed D-10 — ARM's _extract_result reads only release-level fields + confidence + format, so redaction is a no-op for ARM.
- [Phase 02]: [Phase 02-05]: Retired /verify endpoint deleted (not annotated in place) across api-reference.md and docker-quickstart.md; replaced with a Confirming an Existing Disc section describing POST /v1/disc re-submission and its 429/403 gate responses.
- [Phase 02]: [Phase 02-05]: docs/privacy.md created as a new top-level privacy-policy page (D-06 IP-hash disclosure) and wired into mkdocs.yml nav; D-14 cooldown-vs-slowapi-limiter note cross-referenced from api-reference.md, OVID-technical-spec.md, and privacy.md.
- [Phase ?]: 03-02: Stacked AUTH_WRITE_LIMIT ceiling on all three disc write routes (INFRA-04/D-07); resolve uses shared_limit with a fixed scope because its {fingerprint} path param defeats slowapi's default url key style
- [Phase ?]: 03-02: anti_sybil left Postgres-backed and untouched (D-10); coarse write ceiling and narrow confirmation cooldown proven independent, layered not double-counted
- [Phase 03]: 03-03: Redis wired into prod+test compose only (redis:7-alpine, internal-only, ephemeral); base compose unchanged so single-worker self-host stays on memory:// (D-05a)
- [Phase 03]: 03-03: Redis-outage behavior documented as fail-open self-healing (D-01/D-02) with a fail-fast multi-worker boot guard (D-06) across self-hosting/deployment/technical-spec docs
- [Phase 03]: 03-04: INFRA-03 p95 proof validates the honest Redis-backed gunicorn -w 4 + Postgres stack via a non-blocking scheduled Locust job (D-12/D-14), never memory://; Plan-02 write-cap 429s marked non-failure (T-03-10)
- [Phase ?]: OVID_BD2_VERSION frozen at 'OVID-BD-2' — v1 ruleset freeze, not a version bump (D-08)
- [Phase ?]: Tie-break/dedup key is the full (clip_id, in_time, out_time) tuple per play item, never filename — closes studio playlist-renumbering obfuscation (FPRINT-06)
- [Phase 04-02]: identify_bd() Tier-2-primary/Tier-1-alias identity resolver added, mirroring identify_dvd() exactly (FPRINT-03)
- [Phase 04]: Only touched the ovid-client-tests job in ci.yml; other jobs (api-tests, e2e-tests, web-tests, docs-build) left unchanged since e2e-tests already waits for all matrix legs of a dependency job by default.
- [Phase ?]: [Phase 04-03]: canonical_string is independently re-derived in BDDisc._build() via build_bd_canonical_string() rather than reusing a value from identify_bd() — identify_bd()'s shipped DiscIdentitySet has no canonical-string field to reuse
- [Phase ?]: [Phase 04-03]: BDDisc.playlists is empty in the degenerate Tier-1-primary case (mirrors pre-existing test_all_playlists_under_60s_with_aacs_uses_tier1 regression guarantee)
- [Phase 04]: Pinned BD/UHD hash literals computed once via throwaway script, hardcoded as anti-tautology-compliant literals in test_bd_fingerprint_pinned.py
- [Phase 04]: Filler playlist durations in build_heavily_obfuscated_fixture cycle through 5-55s in 5s increments across 20 files (11 distinct steps, cycled) — all remain under MIN_DURATION_SECONDS
- [Phase 04-06]: Documented identify_bd() as-shipped, including the degenerate Tier-1-primary fallback and its diagnostic, rather than a simplified always-Tier-2 framing
- [Phase 04-06]: Placed the manual pre-release cross-drive verification step in docs/contributing.md (no existing release-checklist doc) next to automated test-running instructions
- [Phase 05]: 05-01: FingerprintRegistry copies DiscIdentityAlias's exact column shape with only a disc_id index; table is write-only, no separate fingerprint index needed (D-02)
- [Phase 05]: 05-01: register_fingerprint() is a bare db.add() with no flush/commit of its own; caller must invoke it inside its own db.begin_nested() savepoint so a UNIQUE violation surfaces through the existing except IntegrityError: re-resolve/converge path
- [Phase ?]: [Phase 05-02]: promote_one_disc/promote_all_dvdread1_discs are Alembic-independent (zero alembic imports); UUIDs crossing raw text() SQL binds must use .hex (not str()) to match SQLite's non-native hex-no-dash storage format
- [Phase ?]: [Phase 05-03]: identify_dvd() flipped to prefer dvdread1-* primary whenever libdvdread succeeds (dvd1-* demoted to sole alias), mirroring identify_bd()'s Tier-2-primary/Tier-1-alias pattern; fallback to dvd1-*-primary/zero-alias unchanged when libdvdread unavailable/invalid (D-03, closes RESEARCH.md Open Question #1)
- [Phase ?]: [Phase 05-03]: libdvdread_identity()'s hex-validation ValueError must be raised/caught inside the same try block as read_libdvdread_disc_id() so both failure modes converge on identical exception handling
- [Phase 05-04]: fingerprint_disc_with_identity() reads disc._identity_set directly via getattr; fingerprint_disc() is now a thin backward-compatible wrapper over it, mirroring build_submit_payload()'s alias-only-if-present convention in submit_to_ovid()
- [Phase 05-04]: arm/identify.py's _load_original() hardened to degrade gracefully (try/except around exec_module) instead of crashing the module's own import when ARM-only deps (pydvdid, arm.config, arm.ripper.utils, arm.ui) are absent — required to make arm.identify importable/testable outside the ARM container
- [Phase 05-04]: arm-tests CI job installs ovid-client editable (not just requests+pytest as the plan literally specified) because the tests monkeypatch real ovid.disc.Disc.from_path/ovid.bd_disc.BDDisc.from_path and construct real DiscIdentitySet instances
- [Phase ?]: [Phase 05-05]: _select_primary() colocated with _method_of() as a pure fingerprint+aliases -> (primary, remaining_aliases) function, wired into register_disc/submit_disc's new-disc SAVEPOINTs alongside register_fingerprint() inside the same savepoint (T-05-12 atomic rollback together); mixed-fleet zero-fragmentation guarantee proven by explicit regression test
- [Phase ?]: [Phase 05-06]: backfill_fingerprint_registry() dedupes by fingerprint value across discs+aliases before insert (a pre-existing cross-table collision would otherwise violate the registry's global UNIQUE)
- [Phase ?]: [Phase 05-06]: sqlite3.register_adapter(datetime,...) registered in migrations_support.py to unify raw-text()-SQL datetime storage with the ORM's own DateTime bind_processor - fixes a real tz-aware/tz-naive read-back inconsistency across insert paths; no effect on PostgreSQL
- [Phase 05]: [Phase 05-07]: scripts/promote_dvdread1.py drives docker compose subprocess calls exclusively (never imports api/app internals) since MirrorModeMiddleware is wired at process-import time and only a service restart flips it; captures the operator's CURRENT OVID_MODE and restores it in a finally block (never a hardcoded default) even when alembic upgrade head fails
- [Phase 05]: [Phase 05-07]: docs/self-hosting.md and docs/deployment.md both explicitly state the cutover interrupts reads too, not just writes (Pitfall 3) - mirror operators already always-read-only need no toggle; the canonical server and standalone self-hosters are the actual audience for scripts/promote_dvdread1.py
- [Phase ?]: D-01: pending-link merge state persisted as a DB row (PendingAccountLink) keyed by existing_user_id, replacing session-carried state — removes the nOAuth vector
- [Phase ?]: AUTH-05: dual-stack getaddrinfo SSRF validation (both families + is_reserved) at the Mastodon validate-before-registration choke point; DNS-rebinding TOCTOU accepted as documented v0.2.0 residual (T-06-05d).
- [Phase ?]: OVID_ENV required (fail-fast at import); ALLOW_LOCALHOST_BYPASS derived solely from it, False under production — IndieAuth localhost bypass unreachable in prod (AUTH-10)
- [Phase ?]: resolve_auth (merge.py): verified-email match OFFERS a PendingAccountLink (never silent merge); consume requires same existing_user_id re-auth via an already-linked provider (nOAuth defense, AUTH-08/09)
- [Phase ?]: 06-05: finalize_auth is now a thin resolve_auth wrapper; session-carried implicit-merge (nOAuth) flaw removed; 409 merge-offer carries pending_link_id
- [Phase ?]: 06-05: per-provider email_verified computed at source — GitHub via GET /user/emails primary+verified; Mastodon/IndieAuth always False
- [Phase ?]: 06-06: Apple client-secret exp shrunk to now+300 (~5min); per-exchange regeneration IS the automated rotation (AUTH-03, D-10/D-11) — theft/replay window collapses months->minutes
- [Phase ?]: 06-06: IndieAuth split onto indieauth_router, registered only when OVID_ENABLE_INDIEAUTH truthy (default 404, D-08); localhost bypass derived from config.ALLOW_LOCALHOST_BYPASS as a call-time module attr (never hardcoded True) — provably unreachable in production (AUTH-10, D-09); router flag independent of the OVID_ENV guard (Pitfall 6)
- [Phase ?]: DOCS-03: docs/auth-setup.md documents the DNS-rebinding TOCTOU (T-06-05d) as an explicit accepted residual, carried forward from Plan 06-02 rather than dropped

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1 → Phase 5] Alias write-path TOCTOU race (IDENT-02) and verification state-machine consolidation (VERIFY-02) MUST land before ADR 0001 Phase 3 dvdread1-* promotion (IDENT-04)
- [Phase 6] Open question: whether Mastodon/IndieAuth assert a verified email safe for account-merge (AUTH-08) — resolve at phase planning
- [Phase 4] AACS Disc ID stability across regional reprints unverified — validate empirically with real BD fixtures

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Fingerprint | matrix256 pressing-level alias (MATRIX-01) — spike-first, single-source | Deferred to v2 | 2026-07-05 (init) |
| Re-integration | **Multi-disc-set** (set API/UI/client, migration 900000000008) re-integrated onto `main` from retired `gsd/phase-02` (`f2c7a20`); superseded auth/redis line dropped. Tests green, but ported onto a different baseline. | Shipped on `main` — **re-review in Phase 7** (new-plan context) | 2026-07-07 |
| Re-integration | **Chapter-name** (DiscChapter API/UI, client chapter extraction, migration 900000000009) re-integrated onto `main` from retired `gsd/phase-03` (`63d9417`). Tests green, but ported onto a different baseline. | Shipped on `main` — **re-review in Phase 7** (new-plan context) | 2026-07-07 |

## Session Continuity

Last session: 2026-07-07T03:55:26.126Z
Stopped at: Completed 06-07-PLAN.md
Resume file: None
