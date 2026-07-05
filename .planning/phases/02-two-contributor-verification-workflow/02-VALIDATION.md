---
phase: 2
slug: two-contributor-verification-workflow
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-05
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + FastAPI `TestClient` (in-memory SQLite) |
| **Config file** | `api/tests/conftest.py` (fixtures + SQLite engine); no `pytest.ini`/`pyproject` pytest section detected in `api/` |
| **Quick run command** | `cd api && python -m pytest tests/test_disc_submit.py tests/test_verification.py -x -q` |
| **Full suite command** | `cd api && python -m pytest -q` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd api && python -m pytest tests/test_verification.py tests/test_structural_match.py tests/test_anti_sybil.py -x -q`
- **After every plan wave:** Run `cd api && python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | VERIFY-01 | T-2-01 / T-2-03a | RED: 9 boundary tests pin the D-03 tolerance envelope — reordered tracks / relabeled codec ("AC-3"→"ac3") / ±1-2s duration jitter compare EQUAL; wrong title count, wrong per-title chapter count, missing/extra track, different language compare NOT-equal. Fails on ImportError (module absent) before Task 2. | unit | `cd api && python -m pytest tests/test_structural_match.py -x -q` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | VERIFY-01 | T-2-01 / T-2-03a | GREEN: `structural_match()` compares stored vs submitted titles/tracks canonically (exact title-count + index-set match, exact per-title `chapter_count`/`is_main_feature`, duration within `DURATION_TOLERANCE_SECS=2`s, audio/subtitle as sorted multisets on `(language_code, _normalize_codec(codec), channels)`); reads no release-level field; no `disc.status=` write, no `db.commit()`. | unit | `cd api && python -m pytest tests/test_structural_match.py -x -q` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 1 | VERIFY-04 | T-2-07 / T-2-08 | `disc_edits` gains a nullable `ip_hash` (`String(64)`) column + composite index `idx_disc_edits_user_type_created(user_id, edit_type, created_at)` on both the ORM model (SQLite `create_all`) and a chained Alembic migration `900000000004` (`down_revision=900000000003`); no data backfill — historical rows stay NULL (fail-open, D-07). | schema/migration (no pytest) | `cd api && python -c "import importlib,sqlalchemy as sa; from app.database import Base; from app import models; from sqlalchemy import create_engine, inspect; e=create_engine('sqlite://'); Base.metadata.create_all(e); i=inspect(e); cols=[c['name'] for c in i.get_columns('disc_edits')]; idx=[x['name'] for x in i.get_indexes('disc_edits')]; assert 'ip_hash' in cols, cols; assert 'idx_disc_edits_user_type_created' in idx, idx; import importlib.util,glob; f=glob.glob('alembic/versions/900000000004_*.py')[0]; s=importlib.util.spec_from_file_location('m',f); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); assert m.revision=='900000000004' and m.down_revision=='900000000003'; print('OK')"` | N/A — inline check, no dedicated test file | ⬜ pending |
| 2-02-02 | 02 | 1 | VERIFY-04 | T-2-02 / T-2-03 / T-2-04 / T-2-07 / T-2-08 | RED: unit tests pin `ip_subnet_hash` /24 collapse (same-subnet equal, different-subnet distinct, `None` IP / malformed IP / no-salt → `None`) + cooldown floor (under-limit passes, over-`CONFIRMATION_MAX_PER_WINDOW` hard-blocks, stale-window edits excluded) + weighted fail-open score (all-signals-absent→`trust_ok=True`; fresh account + same-/24→`False`; fresh + absent-IP→`True`; established + same-/24→`True`; fresh + distinct-/24→`True`). Fails on ImportError (`anti_sybil` absent) before Task 3. | unit | `cd api && python -m pytest tests/test_anti_sybil.py -x -q` | ❌ W0 | ⬜ pending |
| 2-02-03 | 02 | 1 | VERIFY-04 | T-2-02 / T-2-03 / T-2-04 / T-2-07 / T-2-08 | GREEN: `anti_sybil.py` implements `ip_subnet_hash` (stdlib `ipaddress`+`hmac`+`hashlib.sha256`, fail-open on missing/malformed IP or salt), a Python-computed cooldown cutoff bound param (no SQL `INTERVAL`, Pitfall 4), and `evaluate_confirmation()` composing the weighted score into `ConfirmationGate(hard_blocked, trust_ok, ip_hash)`; no `disc.status=` write, no `db.commit()`. | unit + integration | `cd api && python -m pytest tests/test_anti_sybil.py -x -q` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 2 | VERIFY-01, VERIFY-03, VERIFY-04 | T-2-01 / T-2-02 / T-2-05 / T-2-06 / T-2-09 | RED: integration tests pin — distinct-B structural re-submit verifies; self re-submit→409; benign jitter still verifies; real structural diff does not verify; structural-match+release-mismatch→dispute (A3); 3rd mismatch on a VERIFIED disc stays verified + records `dispute_attempted` (A2/VERIFY-03); cooldown exceeded→429 w/ `Retry-After`+`request_id`; fresh account+same-subnet→403 `insufficient_trust`; fresh+distinct-subnet still verifies; retired `/verify` route→404/405. Fails RED (gate/match unwired, route still present) before Task 2. | integration | `cd api && python -m pytest tests/test_confirmation_flow.py tests/test_route_retired.py -x -q` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 2 | VERIFY-01, VERIFY-03, VERIFY-04 | T-2-01 / T-2-02 / T-2-05 / T-2-06 / T-2-09 | GREEN: `_handle_existing_disc` gated — `evaluate_confirmation()` pre-check (hard_blocked→429 `rate_limited`+`Retry-After`; not trust_ok→403 `insufficient_trust`) then `structural_match()` gates verify (match+release-match→`verify()`, unchanged sole writer; match+release-mismatch OR mismatch→existing `flag_dispute` path, A2 preserved); `ip_hash` captured on the confirmation + create `DiscEdit`; `verify_disc` route + `test_disc_verify.py` DELETED; no `disc.status=` assignment anywhere in `routes/disc.py`. | integration | `cd api && python -m pytest tests/test_confirmation_flow.py tests/test_route_retired.py tests/test_disc_submit.py tests/test_verification.py -x -q` | ❌ W0 (new files) / ✅ (`test_disc_submit.py`, `test_verification.py` pre-exist) | ⬜ pending |
| 2-03-03 | 03 | 2 | VERIFY-01, VERIFY-03, VERIFY-04 | — (regression sweep; no new threat surface) | Full API suite green after wiring; any failure fixed inline (no-defer rule), zero new warnings introduced; no lingering `verify_disc` symbol or `/disc/{fingerprint}/verify` route reference anywhere in `api/app/`. | integration | `cd api && python -m pytest -q` | ✅ (full existing + new suite) | ⬜ pending |
| 2-04-01 | 04 | 3 | VERIFY-01 | T-2-01 / T-2-10 / T-2-11 | RED: integration tests pin unverified `GET`→200 with `titles==[]` (chapters/main-feature/tracks withheld) while `release`+`fingerprint_aliases`+`confidence`+`request_id` stay populated; verified/disputed `GET`→titles populated (untouched, Pitfall 6); D-11 aliases present on the unverified read; D-10 ARM-read fields (`release.title/year/imdb_id/tmdb_id`, `confidence`, `format`) intact. Fails RED (titles still returned unredacted) before Task 2. | integration | `cd api && python -m pytest tests/test_lookup_redaction.py -x -q` | ❌ W0 | ⬜ pending |
| 2-04-02 | 04 | 3 | VERIFY-01 | T-2-01 / T-2-10 / T-2-11 | GREEN: single status branch in `_disc_to_response` — `titles_resp=[]` only when `disc.status=="unverified"`, else the existing per-title build; `release_resp`/`fingerprint_aliases_resp` unchanged for every status; no new auth dependency; `sync.py`/`Sync*Record` untouched; `DiscLookupResponse` docstring documents the redaction contract (fields already optional, no breaking change). | integration | `cd api && python -m pytest tests/test_lookup_redaction.py tests/test_disc_lookup.py -x -q` | ❌ W0 (new) / ✅ (`test_disc_lookup.py` pre-exists) | ⬜ pending |
| 2-05-01 | 05 | 3 | VERIFY-04 | T-2-09d | Retired `POST /v1/disc/{fingerprint}/verify` removed from `api-reference.md`, the `docker-quickstart.md` API table, and the `OVID-technical-spec.md` endpoint listing (the unrelated `disc_edits.edit_type='verify'` audit-value comment at ~line 402 is explicitly left intact); `contributing.md` reframed from the non-existent `ovid verify` example to the real `ovid submit` re-submission-by-a-distinct-contributor flow. | static (grep) | `cd /Users/trekkie/projects/OVID && ! grep -rInE 'disc/\{fingerprint\}/verify' docs/api-reference.md docs/docker-quickstart.md docs/OVID-technical-spec.md && grep -qiE 'ovid submit' docs/contributing.md && echo OK` | N/A — doc/grep verification, no test file | ⬜ pending |
| 2-05-02 | 05 | 3 | VERIFY-04 | T-2-07d / T-2-14 | `docs/privacy.md` discloses the IP-hash data category (salted HMAC-SHA256, /24 IPv4 / /48 IPv6 truncation, ~90-day retention, never raw); `.env.example` documents `OVID_IP_HASH_SALT` as OPTIONAL/fail-open (contrast the mandatory `OVID_SECRET_KEY`); a one-line note distinguishes the permanent Postgres confirmation cooldown (this phase) from the Phase 3 Redis slowapi limiter (D-14). | static (grep) | `cd /Users/trekkie/projects/OVID && grep -qiE 'OVID_IP_HASH_SALT' .env.example && grep -qiE '/24\|subnet\|salt' docs/privacy.md && grep -qiE 'OVID_IP_HASH_SALT' docs/privacy.md && echo OK` | N/A — doc/grep verification, no test file | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `api/tests/test_structural_match.py` — boundary-test stubs for VERIFY-01 / D-03 (tolerant structural-equality envelope, both directions)
- [ ] `api/tests/test_anti_sybil.py` — stubs for VERIFY-04 (IP-hash /24 collapse, cooldown floor, weighted fail-open score)
- [ ] `api/tests/test_confirmation_flow.py` — stubs for VERIFY-01 / VERIFY-03 / VERIFY-04 through the re-submission path
- [ ] `api/tests/test_lookup_redaction.py` — stubs for VERIFY-01 / D-09 (redacted-200 for unverified discs)
- [ ] `api/tests/test_route_retired.py` — stub asserting D-02 removal of `POST /v1/disc/{fingerprint}/verify`
- [ ] `api/tests/conftest.py` — extend the existing fixtures (`second_user`, `second_auth_header`, `seed_test_disc(status=...)`, `test_user`, `trusted_user`) with an account-age (`created_at`-override) helper for the account-age soft-signal tests; no framework install needed (pytest + `TestClient` already in place)
- [ ] Delete `api/tests/test_disc_verify.py` (11 tests targeting the retired bodyless `/verify` endpoint) as part of Plan 03 Task 2

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
