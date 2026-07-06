---
phase: 02-two-contributor-verification-workflow
reviewed: 2026-07-05T00:00:00Z
depth: deep
files_reviewed: 19
files_reviewed_list:
  - api/alembic/versions/900000000004_add_disc_edits_ip_hash_index.py
  - api/app/anti_sybil.py
  - api/app/models.py
  - api/app/routes/disc.py
  - api/app/schemas.py
  - api/app/structural_match.py
  - api/tests/conftest.py
  - api/tests/test_anti_sybil.py
  - api/tests/test_confirmation_flow.py
  - api/tests/test_disc_edits.py
  - api/tests/test_disc_identity_aliases.py
  - api/tests/test_disc_submit.py
  - api/tests/test_lookup_redaction.py
  - api/tests/test_route_retired.py
  - api/tests/test_structural_match.py
  - docs/api-reference.md
  - docs/contributing.md
  - docs/docker-quickstart.md
  - docs/OVID-technical-spec.md
  - docs/privacy.md
findings:
  critical: 3
  warning: 7
  info: 1
  total: 11
status: resolved
remediation: 02-REVIEW-FIX.md
---

# Phase 2: Code Review Report

**Reviewed:** 2026-07-05T00:00:00Z
**Depth:** deep
**Files Reviewed:** 19
**Status:** issues_found

## Summary

The happy-path two-contributor flow (distinct-submitter structural resubmission → auto-verify, mismatch → dispute, verified-disc-never-flips) is well built and well tested — 297 tests pass and the anti-Sybil unit suite is thorough for the cases it covers. However, tracing the full call chain (`routes/disc.py` → `verification.py` → `structural_match.py` → `anti_sybil.py`, plus the documented production deployment topology in `docs/deployment.md`/`docker-compose.prod.yml`) surfaces three BLOCKER-level gaps that each independently let a single actor "confirm" a disc without a genuine second physical disc, and several WARNING-level correctness/consistency gaps in the anti-Sybil signal itself. None of these are caught by the current test suite — each is a scenario the tests never exercise (same user across register→identify→resubmit; empty `titles`; production reverse-proxy topology).

## Critical Issues

### CR-01: Self-confirmation bypass via register → identify → resubmit

**File:** `api/app/routes/disc.py:128-245` (`_identify_existing_disc`), cross-referenced with `api/app/routes/disc.py:289` and `api/app/verification.py:50`

**Issue:** Every self-confirmation guard in this phase compares against `disc.submitted_by` — but `_identify_existing_disc` (the handler for the ARM `register` → first-metadata-`submit` workflow, WR-03) never updates `existing.submitted_by` when a *different* user attaches the first release/title metadata to a bot-pre-registered disc. Concretely:

1. User A calls `POST /v1/disc/register` → `Disc(fingerprint=X, status=pending_identification, submitted_by=A)` (`routes/disc.py:715-724`).
2. User B calls `POST /v1/disc` with fingerprint X + real release/title metadata → since `existing.status == "pending_identification"`, `_identify_existing_disc(db, existing, body, current_user=B, ...)` runs (`routes/disc.py:285-286`). It attaches the Release, `DiscTitle`s, `DiscTrack`s, and calls `identify(db, existing, B)` — but **never sets `existing.submitted_by = B`**. `submitted_by` stays `A`.
3. User B calls `POST /v1/disc` a **second** time with the *same* payload. `existing.status` is now `"unverified"`, so this goes to the main `_handle_existing_disc` body. The same-submitter guard at line 289 checks `existing.submitted_by (A) == current_user.id (B)` → **false**, so B is *not* rejected as a duplicate submitter.
4. The anti-Sybil gate runs (`evaluate_confirmation`), `structural_match` trivially succeeds (B is literally resubmitting the exact structure they just entered), `_releases_match` trivially succeeds, and `verify(db, existing, B)` is called. `verify()`'s own self-check at `verification.py:50` also compares `disc.submitted_by (A) == actor.id (B)` → **false**, so the self-confirmation guard does not fire there either.
5. Result: `disc.status` flips to `"verified"`, `verified_by = B` — **a single account (B) verified their own submission**, with zero involvement from a genuine second physical-disc owner. This is exactly the "distinct `user_id` alone... bypass[ing] independence checks" scenario called out in the anti-Sybil module docstring (D-05) as something that must NOT be possible — except here it isn't even a *distinct* `user_id`, it's the *same* one, laundered through the stale `submitted_by` pointer.

This is the standard ARM workflow (bot registers bare fingerprint, a human later attaches metadata) — no adversarial two-account setup is even required; the "second contributor" whose identity is checked (`A`) is never the party who actually supplied the metadata being verified (`B`).

**Fix:** `_identify_existing_disc` must attribute the disc to the user who actually supplied the structural/release metadata, since that is the content the confirmation guards must protect:

```python
# in _identify_existing_disc, before/at the identify() call:
existing.submitted_by = current_user.id
identify(db, existing, current_user)
```

(If preserving the original registrant is desired for audit purposes, keep it on the `DiscEdit`/a separate column — but `submitted_by`, which is what both self-confirmation guards read, must reflect the actual metadata author.) Add a regression test: A registers, B identifies, B resubmits the identical payload a third time → must return 409 (or at minimum must never transition the disc to `verified`).

---

### CR-02: `structural_match` trivially passes when a disc has no titles — resurrects the release-only "echo" attack

**File:** `api/app/structural_match.py:59-89`, demonstrated live by `api/tests/test_disc_edits.py:38-56`

**Issue:** `DiscSubmitRequest.titles` is optional (`Field(default_factory=list)`, `schemas.py:151`), and nothing in `submit_disc`/`_handle_existing_disc` requires a non-empty `titles` list. When both the stored disc and the incoming submission have zero titles:

```python
if len(stored_titles) != len(body.titles):   # 0 != 0 -> False
    return False
stored_by_index = {...}                       # {}
submitted_by_index = {...}                    # {}
if set(stored_by_index) != set(submitted_by_index):  # {} != {} -> False
    return False
for title_index, stored in stored_by_index.items():   # loop body never runs
    ...
return True                                    # unconditionally True
```

`structural_match` returns `True` unconditionally whenever both sides have zero titles — meaning verification is then driven *entirely* by `_releases_match` (release title/year/tmdb_id), which is exactly the release-level, publicly-searchable metadata the module's own docstring says this gate exists to avoid trusting ("a match proves the confirmer read a physical disc rather than echoing searchable metadata"). This is not a hypothetical: `api/tests/test_disc_edits.py::test_edits_after_confirmation_has_two_entries` submits a `titles: []` payload as user A, then submits the *identical* release-only payload as user B, and asserts `status == "verified"` — the test suite itself proves a sockpuppet can "confirm" a title-less disc with nothing but the public release title/year/TMDB id, no disc possession required at all.

**Fix:** Treat an empty stored/submitted title list as insufficient proof of possession rather than a vacuous match — e.g., require at least one stored title for `structural_match` to be eligible to return `True`, and route title-less discs to `flag_dispute`/manual review instead of auto-verify:

```python
def structural_match(existing_disc, body, db) -> bool:
    stored_titles = db.query(DiscTitle).filter(DiscTitle.disc_id == existing_disc.id).all()
    if not stored_titles:
        # No structural payload was ever recorded for this disc — there is
        # nothing to prove possession against, so this can never satisfy the
        # proof-of-possession gate; the release-only path must not auto-verify.
        return False
    if len(stored_titles) != len(body.titles):
        return False
    ...
```

---

### CR-03: Anti-Sybil IP-diversity signal is broken (fails toward false-positive, not fail-open) behind the documented production reverse-proxy topology

**File:** `api/app/anti_sybil.py:116-128` (`client_ip_hash`), `api/main.py` (no `ProxyHeadersMiddleware`/`--forwarded-allow-ips`), cross-referenced with `docs/deployment.md`, `docs/nginx-oviddb-vhosts.conf`, `docker-compose.prod.yml`

**Issue:** `client_ip_hash(request)` reads `request.client.host` directly:

```python
raw_ip: str | None = None
client = getattr(request, "client", None)
if client is not None:
    raw_ip = getattr(client, "host", None)
return ip_subnet_hash(raw_ip, _ip_hash_salt())
```

The project's own documented canonical production deployment (`docs/deployment.md`, `docs/nginx-oviddb-vhosts.conf`) puts `nginx` in front of `gunicorn -k uvicorn.workers.UvicornWorker` (`docker-compose.prod.yml`), setting `X-Forwarded-For`/`X-Real-IP`. But `main.py` never wires uvicorn's `ProxyHeadersMiddleware` and the gunicorn invocation passes no `--forwarded-allow-ips`/equivalent, so `request.client.host` in production is **always the reverse proxy's own address** (e.g. the docker bridge gateway or `127.0.0.1`), not the real client IP, for every request.

Consequence: `client_ip_hash` returns the **same** subnet hash for literally every submitter and every confirmer in production. This is not "signal absent" (the fail-open case the code is designed for, D-07) — it is "signal present but always wrong": `confirmer_hash == submitter_hash` unconditionally, so `SAME_SUBNET_PENALTY` (`anti_sybil.py:232-234`) fires for *every single confirmation*, real or fraudulent. A genuine, distinct, but recently-created contributor confirming someone else's disc in production gets `YOUNG_ACCOUNT_PENALTY (-1) + SAME_SUBNET_PENALTY (-1) = -2`, which is `not > TRUST_BLOCK_THRESHOLD (-2)` → `trust_ok = False` → every fresh legitimate confirmer is rejected with 403 in production. Simultaneously, the signal provides **zero actual Sybil detection** in production, since two sockpuppet accounts behind the *same* real attacker connection look identical to two genuine users behind the shared proxy — the "same subnet" bit is constant, carrying no information either way.

This is untested because `test_confirmation_flow.py`'s `_post_from_ip` helper drives `request.client.host` directly via `TestClient(app, client=(ip, 40000))`, bypassing the entire proxy-header path that production actually uses — so no test in this phase can catch this.

**Fix:** Extract the real client IP from `X-Forwarded-For`/`X-Real-IP` when running behind a trusted proxy, mirroring the pattern uvicorn/gunicorn already ship (`uvicorn.middleware.proxy_headers.ProxyHeadersMiddleware`) — e.g. wire it in `main.py`:

```python
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app = ProxyHeadersMiddleware(app, trusted_hosts=os.environ.get("OVID_TRUSTED_PROXY_IPS", "*"))
```

or, if avoiding ASGI-level wrapping, parse `X-Forwarded-For` explicitly in `client_ip_hash` behind an explicit trusted-proxy allowlist. Add a regression test that sets `X-Forwarded-For` on the TestClient request (not just `client=`) and asserts the resulting `ip_hash` differs between two distinct forwarded IPs.

## Warnings

### WR-01: `duration_secs` tolerance check is skippable by omission, unlike `chapter_count`

**File:** `api/app/structural_match.py:44-47`

**Issue:** `chapter_count`/`is_main_feature` use direct equality (`stored.chapter_count != submitted.chapter_count` — a mismatch when one side is `None` and the other isn't), but duration uses a conditional skip:

```python
if stored.duration_secs is not None and submitted.duration_secs is not None:
    if abs(stored.duration_secs - submitted.duration_secs) > DURATION_TOLERANCE_SECS:
        return False
```

If the submitted payload simply omits `duration_secs` (it's `Optional[int]` in `TitleCreate`, `schemas.py:106`), the entire duration check is skipped *regardless of the stored value* — this is different from every other field in the envelope, which enforce equality (with tolerance) even when one side supplies a value. A confirmer can trivially drop one of the harder-to-guess-without-the-disc signals (exact runtime in seconds) by leaving the field out of their submission.

**Fix:** Treat "stored has a value, submitted omitted it" as a mismatch, consistent with `chapter_count`'s handling:

```python
if stored.duration_secs is not None:
    if submitted.duration_secs is None or abs(stored.duration_secs - submitted.duration_secs) > DURATION_TOLERANCE_SECS:
        return False
```

### WR-02: `_identify_existing_disc`'s audit edit never records `ip_hash`, unlocking the ARM register→identify path from the IP-diversity signal entirely

**File:** `api/app/routes/disc.py:207-215`

**Issue:** The `"create"` `DiscEdit` written in `submit_disc()` captures `ip_hash=client_ip_hash(request)` (`routes/disc.py:907-913`), which `_submitter_ip_hash()` (`anti_sybil.py:171-186`) later reads as the reference subnet for IP-diversity comparison. But the `"identify"` `DiscEdit` written in `_identify_existing_disc` — which is the *only* audit record produced for any disc that went through the `register` → first-`submit` (ARM) path, since `register_disc()` itself writes no `DiscEdit` at all — omits `ip_hash`:

```python
db.add(
    DiscEdit(
        disc_id=existing.id,
        user_id=current_user.id,
        edit_type="identify",
        edit_note="disc identified — first release metadata attached",
    )
)
```

Because `_SUBMITTER_EDIT_TYPES = ("create", "identify")` treats this row as the submitter reference, and it carries no `ip_hash`, `_submitter_ip_hash()` always returns `None` for any disc identified via this path — silently and unconditionally disabling one of the two soft signals (IP diversity) for what is likely the single most common submission path in the product (ARM pre-registers, a human later identifies).

**Fix:** Capture the same signal consistently:

```python
db.add(
    DiscEdit(
        disc_id=existing.id,
        user_id=current_user.id,
        edit_type="identify",
        ip_hash=client_ip_hash(request),
        edit_note="disc identified — first release metadata attached",
    )
)
```

(`request` is already a parameter of `_identify_existing_disc`'s caller `_handle_existing_disc`; needs threading into `_identify_existing_disc`'s signature.)

### WR-03: Confirmation cooldown is a check-then-act race, not actually atomic across concurrent requests

**File:** `api/app/anti_sybil.py:149-168, 212-220`

**Issue:** The module docstring claims the cooldown is "worker-safe by construction: Postgres is the single shared source of truth across all gunicorn workers." That's true for *sequential* requests, but `_recent_confirmation_count` is a plain `SELECT COUNT(...)` with no locking, and the eventual `DiscEdit(edit_type="verify")` insert that increments the count happens later, in the caller, after the gate has already returned. Two concurrent requests from the same actor (e.g. a scripted burst) can both read the same pre-increment count and both pass the `hard_blocked` check before either commits its verify edit — the cooldown does not serialize on anything (contrast with `next_seq()` in `sync.py`, which explicitly uses `with_for_update()` for exactly this reason). This lets a determined actor exceed the intended cap under concurrency.

**Fix:** Either serialize via `SELECT ... FOR UPDATE` on a per-user counter row (mirroring `next_seq()`), or accept the race as a documented, acceptable soft-floor gap (currently undocumented) given this is a "launch-safe" cooldown rather than a hard security boundary.

### WR-04: Off-by-one in the cooldown threshold, and the exact-boundary case is untested

**File:** `api/app/anti_sybil.py:218-220`

**Issue:** `hard_blocked = hourly > CONFIRMATION_MAX_PER_WINDOW or daily > CONFIRMATION_MAX_PER_DAY`. Since `hourly`/`daily` count *existing* verify edits (not including the one about to be created), a user with exactly `CONFIRMATION_MAX_PER_WINDOW` (5) prior confirmations in the window is **not** blocked (`5 > 5` is `False`) and is allowed a 6th — the constant's name ("max per window") implies 5 should be the ceiling, but the effective ceiling is 6 (21/day, not 20). `api/tests/test_anti_sybil.py`'s `TestCooldown` only exercises `MAX-1` and `MAX+1`; the exact-boundary case (`count == CONFIRMATION_MAX_PER_WINDOW`) is never asserted either way, so this drift from the named intent is unverified.

**Fix:** If the intent is "at most N confirmations per window," change to `hourly >= CONFIRMATION_MAX_PER_WINDOW`. Add a boundary test asserting behavior at exactly `count == CONFIRMATION_MAX_PER_WINDOW`.

### WR-05: `docs/privacy.md` promises ~90-day IP-hash retention/deletion; no purge mechanism exists anywhere in the codebase

**File:** `docs/privacy.md:49-51`, cross-referenced against `api/app/anti_sybil.py`, `api/app/models.py:379-381`, `api/scripts/` (only `seed.py`, `sync.py` exist)

**Issue:** The new privacy policy states: *"Retention: the IP-hash is retained for approximately 90 days, a fraud-prevention-only retention window, after which it is eligible for deletion."* This retention window is also cited as part of the GDPR legitimate-interest legal basis ("truncation + salting + short retention window together form the pseudonymization floor required for that basis to hold"). Nothing in `api/app/`, `api/scripts/`, or the Alembic migrations implements any retention/expiry/purge job for `disc_edits.ip_hash` — the column (`models.py:379-381`) is a plain nullable `String(64)` with no TTL, no scheduled deletion task, and no reference to a 90-day window anywhere in code. The compliance claim is currently unbacked by implementation.

**Fix:** Either implement the purge job (e.g. a scheduled task nulling `ip_hash` on `disc_edits` older than 90 days) before shipping this privacy claim, or soften the documentation to not assert a specific enforced retention window until the mechanism exists.

### WR-06: `POST /v1/disc/{fingerprint}/resolve` lets a single trusted/editor/admin user verify a disc that was never disputed, bypassing the two-contributor requirement

**File:** `api/app/routes/disc.py:568-607`, `api/app/verification.py:92-105` (`resolve_dispute`), `LEGAL_TRANSITIONS` at `verification.py:30-37`

**Issue:** `resolve_dispute_endpoint` only checks `current_user.role in ("trusted", "editor", "admin")` — it never checks that `disc.status == "disputed"` before calling `resolve_dispute()`. `resolve_dispute()` in turn only validates against `LEGAL_TRANSITIONS`, which includes `("unverified", "verified")` (needed for the `verify()` path) as well as `("disputed", "verified")`. Because both tuples are legal, a trusted/editor/admin user can call `POST /v1/disc/{fp}/resolve {"action": "verify"}` against a disc that is merely `unverified` (never disputed) and instantly flip it to `verified` with a single action — no second contributor, no structural match, no anti-Sybil gate. This may be an intentional escalation path for trusted roles, but it is not documented as such anywhere (the endpoint and its docs are framed purely as "dispute resolution"), and it means the two-contributor guarantee has an unstated, unaudited-in-docs single-actor override.

**Fix:** If this is intentional trusted-role behavior, document it explicitly (in `docs/api-reference.md` and `docs/privacy.md`/threat model) as a deliberate escalation path, and consider requiring `disc.status == "disputed"` as a precondition in the route handler to prevent accidental use against merely-unverified discs.

### WR-07: `docs/api-reference.md`'s newly-added confirmation-error examples don't match the live route's error codes

**File:** `docs/api-reference.md:267-275` (added in this phase), vs. `api/app/routes/disc.py:634-636` (`lookup_disc`'s actual `_error_response`)

**Issue:** The "Confirming an Existing Disc" section added in this phase documents a `404` response with `"error": "disc_not_found"`, but the live `GET /v1/disc/{fingerprint}` handler returns `"error": "not_found"` (`_error_response(request_id, "not_found", ...)`, `routes/disc.py:634-636`). This mismatch pre-dates this phase in the rest of the file, but this phase's new section reproduces the stale code rather than correcting it, and a reader relying on this newly-written section will build a client against the wrong error code.

**Fix:** Update the example to `"error": "not_found"` to match the implementation (and, ideally, fix the older instances of the same mismatch elsewhere in the file while touching it).

## Info

### IN-01: `register_disc()` writes no `DiscEdit` for the registration action itself

**File:** `api/app/routes/disc.py:677-761`

**Issue:** Unlike `submit_disc()` (which records a `"create"` `DiscEdit`) and `_identify_existing_disc` (which records an `"identify"` edit), `register_disc()` never adds a `DiscEdit` row for the bare fingerprint registration. This means `GET /v1/disc/{fp}/edits` on a disc that is still `pending_identification` returns an empty edit list, and the true "who registered this and when" fact is only recoverable from `disc.submitted_by`/`disc.created_at`, not the append-only audit log the rest of the system relies on (R015).

**Fix:** Consider adding a `"register"` `edit_type` `DiscEdit` in `register_disc()` for audit-trail completeness, consistent with every other disc-mutating action.

---

_Reviewed: 2026-07-05T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
