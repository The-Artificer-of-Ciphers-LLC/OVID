# Phase 2: Two-Contributor Verification Workflow - Research

**Researched:** 2026-07-05
**Domain:** Anti-Sybil trust model over a FastAPI + SQLAlchemy + Postgres write path (proof-of-possession confirmation, structural equality matching, IP/account-age weighting, payload redaction)
**Confidence:** HIGH — the phase is almost entirely local-codebase work over an already-consolidated Phase 1 state machine; the only external fact (client-IP-behind-proxy behavior) is verified against uvicorn docs.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Confirmation is **structural re-submission via `POST /v1/disc`**. A second, distinct contributor re-runs their own physical disc through `ovid-client` and re-submits the full independently-computed payload; the server verifies (`unverified → verified`) when that payload matches. Reuses the existing `_handle_existing_disc` → `verify()` wiring. The confirmer must reproduce structure that is withheld from public reads (D-08), so the match is real proof of possession, not an echo.
- **D-02:** **Retire the bodyless `POST /v1/disc/{fingerprint}/verify` route entirely.** Re-submission is the *only* confirmation path. Audit callers before removal (web UI, tests, docs, ARM). Web UI can surface verification *status* but cannot itself confirm (it never reads discs).
- **D-03:** The match that triggers verification is **normalized/tolerant structural equality**, not byte-exact (title count, main-feature marker, per-title chapter counts, audio/subtitle track layout, after canonical ordering). Today `_releases_match` compares only release-level `title`/`year`/`tmdb_id` (publicly searchable) — must be upgraded to structural equality. Define the tolerance envelope explicitly and test it against the disputed-vs-verified boundary (a real mismatch must still → dispute, not silently verify).
- **D-04:** Enforcement is a **weighted trust score**, not per-signal hard-block. The **confirmation rate-limit / cooldown hard-blocks**; **account-age and IP-diversity are soft, offsetting signals** above a threshold.
- **D-05:** A merely-distinct `user_id` is **never by itself** accepted as proof of independence (VERIFY-04 core).
- **D-06:** **IP privacy:** do NOT store raw IP. Store a **salted hash truncated to the /24 subnet (IPv4) / /48 (IPv6)**, short retention (~90 days), documented as a **privacy-policy addendum**. GDPR: an IP is personal data even hashed — truncation + salt + retention limit is the pseudonymization floor.
- **D-07:** **Fail-open** when a signal is unavailable (proxied client, missing IP, brand-new but genuine account) — an absent signal must never itself count against the confirmer. The confirmation cooldown (D-13) is the launch-safe floor when all soft signals are absent.
- **D-08 (starting thresholds — VALIDATE, not hard-locked):** account-age soft cutoff ~24h; IP-diversity: distinct /24-hash = positive trust, same-subnet = penalty (not block); confirmation cooldown ~handful/hour, low-tens/day (hard floor). Surface as named constants/config, not magic numbers.
- **D-09:** **Redacted-200** shape. `GET /v1/disc/{fingerprint}` for an `unverified` disc returns **200** with `fingerprint`, `status="unverified"`, `confidence`, `release` (title/year/imdb/tmdb) — and **withholds** the structural payload (`titles`, main-feature marker, chapters, audio/subtitle tracks). Not a 404.
- **D-10:** **Verified against ARM:** `arm/identify_ovid.py::_extract_result()` reads only release-level fields + `confidence` + `format`, never `titles`/tracks — withholding structure is a **no-op for ARM**. Confirm still holds during planning.
- **D-11:** **Aliases stay visible** on unverified discs (identity strings, not structural payload; primary is already the URL path). Keep IDENT-01 uniform-exposure behavior regardless of verification status.
- **D-12:** Implementation is a **status branch in `_disc_to_response()`** plus a schema change making structural fields optional/omittable. No new auth dependency — redaction is uniform for all readers (including the original submitter, for this phase). Submitter-preview is a separate later UX decision, out of Phase 2 scope.
- **D-13:** VERIFY-04's rate-limit clause is a **Postgres-backed per-account confirmation cooldown/counter**, built on existing `disc_edits` rows (`edit_type="verify"`, `user_id`, `created_at`) — a `COUNT`/`MAX(created_at)` query plus an index (or a small dedicated table). Worker-safe by construction (Postgres is the single shared source of truth), so VERIFY-04 closes correctly regardless of Phase 3 order.
- **D-14:** This is a **distinct mechanism** from the general slowapi API limiter that Phase 3 hardens with Redis. Add a one-line doc note distinguishing them. **Do NOT** use the in-memory slowapi limiter for the confirmation guardrail (Nx-inflated under multi-worker gunicorn — a hollow guardrail on the real prod target).

### Claude's Discretion

- Exact anti-Sybil threshold values (D-08) — propose launch-safe defaults; the *shape* (weighted, soft signals + hard cooldown floor, fail-open) is locked, the *numbers* are tunable.
- Whether the confirmation cooldown lives as an index-on-`disc_edits` query vs. a small dedicated table (D-13).
- Exact structural-tolerance envelope for D-03 — planner defines and tests it against the verify/dispute boundary.

### Deferred Ideas (OUT OF SCOPE)

- Web-UI "confirm" affordance / submitter preview of own pending upload → Phase 7 / later UX.
- Redis-backed / multi-worker rate limiting + p95 load validation → Phase 3 (INFRA-01..04).
- Full reputation / edit-voting system → v0.4.0.
- Cross-table fingerprint-registry arbitration (WR-02) → Phase 5.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VERIFY-01 | Disc stays `unverified` until a second, DISTINCT contributor independently confirms the fingerprint; never self-confirmation | `verify()` in `verification.py` already rejects `submitted_by == actor.id` and gates on `LEGAL_TRANSITIONS`. Phase 2 changes the *trigger* (structural re-submission, D-01/D-03) and adds behavior tests. Self-confirm guard is in place; needs a test asserting it through the re-submission path, not just the retired `/verify` route. |
| VERIFY-03 [guardrail] | An already-`verified` disc cannot be flipped to `disputed`/`unverified` by a later 3rd submission except via explicit dispute path | `flag_dispute()` returns `False` (no write) on a verified disc; `_handle_existing_disc` records a `dispute_attempted` audit edit and returns 200 "remains verified" (A2 contract). No `LEGAL_TRANSITIONS` tuple targets `disputed`. Phase 2 must preserve this while upgrading the match logic — add a regression test that a 3rd structural mismatch against a verified disc stays verified. |
| VERIFY-04 [guardrail] | Baseline anti-Sybil weighting (account-age / IP-diversity) + confirmation-action rate limits gate verification; distinct `user_id` alone is not proof | New: Postgres cooldown over `disc_edits` (D-13), salted /24 IP-hash capture (D-06), account-age from `User.created_at`, composed as a weighted score (D-04) that fails open (D-07). All primitives already exist in the schema except IP-hash storage + a `disc_edits` index. |
</phase_requirements>

## Summary

Phase 2 is **~90% local-codebase surgery**, not new-technology adoption. Phase 1 already delivered the guarded state machine (`api/app/verification.py`) with the self-verify guard, the sole-disputed-writer rule, and the `LEGAL_TRANSITIONS` frozenset. The auto-verify wiring (`_handle_existing_disc` → `verify()`) already fires when a second submitter's fingerprint resolves to an existing disc. Phase 2 changes **what proves a legitimate second confirmation** and **what a public reader can see before it happens**.

Four concrete deltas: (1) upgrade the `_releases_match` gate to **tolerant structural equality** over the stored `DiscTitle`/`DiscTrack` data (D-03); (2) **redact the structural payload** from `GET` reads of unverified discs via a status branch in `_disc_to_response()` plus optional schema fields (D-09/D-12); (3) add a **Postgres-backed confirmation cooldown** (a `COUNT`/`MAX(created_at)` over `disc_edits` where `edit_type='verify'`, plus a new index) as the hard floor, and a **weighted, fail-open soft-signal score** from account-age (`User.created_at`) and a **salted /24 IP-hash** (new column/table) (D-04/D-06/D-13); and (4) **retire the bodyless `/verify` route** and its test file, updating three docs pages (D-02).

**No new third-party packages are required** — IP truncation/hashing uses stdlib `ipaddress`, `hashlib`, `hmac`. The single non-obvious external gotcha is that **`request.client.host` does not return the real client IP behind a reverse proxy unless uvicorn/gunicorn is configured to trust the proxy** — and even then `X-Forwarded-For` is spoofable, which is *acceptable here* only because IP-diversity is a soft, fail-open signal and the cooldown is the real floor.

**Primary recommendation:** Keep every status write inside `verification.py`; layer the anti-Sybil gate as a *pre-check* in the confirmation path (before `verify()` is allowed to fire) and the redaction as a *post-shape* in `_disc_to_response()`. Compute the cooldown cutoff in Python and pass it as a bound parameter (portable across the SQLite test engine and prod Postgres). Treat the structural-match tolerance envelope as the highest-risk design decision and pin it with boundary tests.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Structural equality match (proof of possession) | API / Backend (`routes/disc.py` helper + possibly a new `app/` service) | Client (`ovid-client` computes and re-submits structure) | The confirmer computes structure client-side from a physical disc; the *comparison* against stored data is a server-authoritative trust decision and must live server-side. |
| Status transition (`unverified→verified`, dispute) | API service layer (`verification.py`) | — | Phase 1 consolidated all `disc.status` writes here; Phase 2 must not reintroduce route-level mutation (VERIFY-02). |
| Anti-Sybil gate (cooldown + weighted score) | API / Backend (new pre-check in the confirmation path) | Database (`disc_edits` counter, IP-hash storage) | Must be worker-safe → Postgres-authoritative, not in-process (D-13/D-14). |
| Payload redaction | API serialization (`_disc_to_response` + `schemas.py`) | — | Uniform for all readers; a response-shaping concern, not an auth concern (D-12). |
| Client IP capture | API request boundary (`Request`) | Reverse proxy / gunicorn config (trust boundary) | IP is only trustworthy if the proxy trust chain is configured; otherwise fail-open (D-07). |
| Account-age signal | API (reads `User.created_at`) | — | Already-persisted field; pure read. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `>=0.110,<1.0` (installed) | Route + `Request` access for client IP | Already the API framework — no change. `[CITED: ./.claude/CLAUDE.md]` |
| SQLAlchemy | `>=2.0,<3.0` (installed) | Cooldown `COUNT`/`MAX` query, new IP-hash column/table, migration models | Already the ORM. `[CITED: ./.claude/CLAUDE.md]` |
| Alembic | `>=1.13,<2.0` (installed) | Migration for the `disc_edits` index + IP-hash storage | Existing migration runner (`api/alembic/versions/`). `[VERIFIED: ls api/alembic/versions/]` |
| Pydantic v2 | (installed) | Make `titles`/structural fields optional/omittable on `DiscLookupResponse` (D-12) | Already used for all schemas. `[VERIFIED: api/app/schemas.py]` |
| Python stdlib `ipaddress` | 3.12 stdlib | Truncate IPv4→/24, IPv6→/48 before hashing (D-06) | Canonical, no dependency; `ip_network(f"{ip}/24", strict=False)`. `[ASSUMED]` (stdlib, universally available) |
| Python stdlib `hmac` + `hashlib` | 3.12 stdlib | Salted keyed hash of the truncated subnet (D-06) — `hmac.new(salt, subnet_bytes, sha256)` | Salt-with-HMAC is the correct primitive vs. bare `sha256` (defeats rainbow tables over the tiny IPv4 space). Codebase already uses `hashlib.sha256` in `auth/indieauth.py`. `[VERIFIED: grep hashlib api/app]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + FastAPI `TestClient` | installed | All behavior tests against in-memory SQLite | Every Phase 2 test (existing pattern, `api/tests/conftest.py`). `[VERIFIED: api/tests/conftest.py]` |
| slowapi | `>=0.1.9,<1.0` (installed) | General API throttle only — **NOT** the confirmation guardrail (D-14) | Leave as-is; do not attach VERIFY-04 to it. `[VERIFIED: api/app/rate_limit.py docstring]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Postgres cooldown over `disc_edits` (D-13) | slowapi in-memory limiter | REJECTED by D-14 — in-memory is Nx-inflated under `gunicorn -w 4` (verified in prod compose command), a hollow guardrail. |
| New `ip_hash` column on `disc_edits` | Dedicated `submission_ip_hashes` table | Column co-locates the signal with the confirmation record and needs one migration; a separate table adds retention-pruning surface. Planner discretion (D-13). Recommend the column for minimal blast radius. |
| SQL `NOW() - INTERVAL` in the cooldown query | Python-computed cutoff datetime bound param | STRONGLY prefer the Python cutoff — `INTERVAL` arithmetic differs between the SQLite test engine and prod Postgres (see Pitfall 4). |
| HMAC-SHA256 of /24 subnet | bare SHA-256 of raw IP | Bare hash of a full IPv4 is trivially reversible (2^32 preimage space); truncation + salted HMAC is the GDPR pseudonymization floor (D-06). |

**Installation:** None. All primitives are already installed or stdlib. `[VERIFIED: no new external packages required]`

## Package Legitimacy Audit

> Phase 2 installs **no new external packages**. All work uses already-installed libraries (FastAPI, SQLAlchemy, Alembic, Pydantic, pytest, slowapi) and Python 3.12 stdlib (`ipaddress`, `hmac`, `hashlib`, `datetime`).

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none — no new deps) | — | — | — | — | OK | No install step |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                      SECOND CONTRIBUTOR (independent physical disc)
                                     │
                        ovid-client: read disc → normalize_disc_structure()
                        → compute fingerprint + full structural payload
                                     │  POST /v1/disc  {fingerprint, release, titles[...tracks]}
                                     ▼
        ┌────────────────────────────────────────────────────────────────┐
        │  submit_disc()  (routes/disc.py)                                │
        │    resolve_existing_disc_for_identities(fingerprint, aliases)   │
        │              │ resolves to same pressing (alias layer)          │
        │              ▼                                                   │
        │  _handle_existing_disc()                                        │
        │    ├─ same submitter? ────────────────► 409 (self, D-05/VERIFY-01)
        │    ├─ pending_identification? ─────────► attach metadata (WR-03) │
        │    └─ DIFFERENT submitter:                                       │
        │         ┌──────────────────────────────────────────────┐        │
        │         │ [NEW] ANTI-SYBIL GATE (VERIFY-04)             │        │
        │         │   1. cooldown COUNT over disc_edits (HARD)    │◄─ Postgres (worker-safe, D-13)
        │         │      exceeded → 429/refuse, no verify         │        │
        │         │   2. weighted soft score: account-age +       │        │
        │         │      IP-diversity (/24 hash) — fail-open D-07 │        │
        │         └──────────────────────────────────────────────┘        │
        │         ┌──────────────────────────────────────────────┐        │
        │         │ [UPGRADED] structural equality (D-03)         │        │
        │         │   compare submitted structure vs STORED       │        │
        │         │   (tolerant: title count, main-feature,       │        │
        │         │    per-title chapters, track layout)          │        │
        │         └──────────────────────────────────────────────┘        │
        │            ├─ structural match ──► verify(db, disc, actor) ──────┼─► verification.py (sole writer)
        │            │                        + DiscEdit(edit_type=verify, │     unverified→verified
        │            │                          ip_hash=…)                 │
        │            └─ structural mismatch ─► flag_dispute() (verified?   │
        │                                       stays verified, A2)        │
        └────────────────────────────────────────────────────────────────┘

        PUBLIC READER (anonymous / ARM)
              │  GET /v1/disc/{fingerprint}
              ▼
        lookup_disc() → _disc_to_response()
              └─ [NEW] status=="unverified" → REDACT structural payload (D-09/D-12):
                    return {fingerprint, status, confidence, release, fingerprint_aliases}
                    WITHHOLD {titles, chapters, tracks, main-feature marker}
              └─ status in {verified, disputed, ...} → full response (unchanged)
```

### Recommended Project Structure

```
api/app/
├── verification.py          # UNCHANGED transition primitives (extend tests only)
├── routes/disc.py           # _handle_existing_disc: insert anti-Sybil gate + swap
│                            #   _releases_match → structural equality;
│                            #   _disc_to_response: add unverified redaction branch;
│                            #   DELETE verify_disc route (D-02)
├── schemas.py               # DiscLookupResponse: titles/structural fields optional
├── anti_sybil.py  (NEW)     # confirmation cooldown query + weighted-score compose +
│                            #   client-IP → salted /24 hash; all thresholds as
│                            #   named module constants (D-08)
├── structural_match.py (NEW)# tolerant structural equality over stored DiscTitle/DiscTrack
│                            #   vs submitted DiscSubmitRequest (D-03)
├── models.py                # disc_edits: add ip_hash column + composite index
└── alembic/versions/9000000000XX_*.py  (NEW) # index + ip_hash migration
```
*(Domain logic lives outside `routes/` per project convention — `disc_identity.py`/`sync.py` precedent. New `anti_sybil.py` + `structural_match.py` follow that pattern; keep route handlers thin.)*

### Pattern 1: Anti-Sybil gate as a pre-check, not a status-writer

**What:** The gate decides *whether `verify()` is allowed to fire*; it never writes `disc.status` itself.
**When to use:** In `_handle_existing_disc`, in the `different-user + structural-match` branch, before calling `verify()`.
**Example:**
```python
# Source: pattern derived from existing api/app/routes/disc.py _handle_existing_disc
# (VERIFY-02 keeps ALL status writes in verification.py)
gate = evaluate_confirmation(db, existing, current_user, request)  # anti_sybil.py
if gate.hard_blocked:                        # cooldown exceeded (D-13, hard floor)
    return _error_response(request_id, "rate_limited",
                           "Confirmation cooldown active", 429)
if not gate.trust_ok:                        # weighted soft score below threshold
    # fail-open already applied inside evaluate_confirmation for absent signals (D-07)
    return _error_response(request_id, "insufficient_trust",
                           "Confirmation rejected by anti-Sybil weighting", 403)
transitioned = verify(db, existing, current_user)   # sole writer, unchanged
```

### Pattern 2: Portable time-window cooldown query (D-13)

**What:** Count a user's recent confirmations without dialect-specific interval SQL.
**Example:**
```python
# Source: derived from api/app/models.py DiscEdit + SQLAlchemy 2.x
from datetime import datetime, timedelta, timezone
cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
recent = (
    db.query(func.count())
      .select_from(DiscEdit)
      .filter(DiscEdit.user_id == actor.id,
              DiscEdit.edit_type == "verify",
              DiscEdit.created_at >= cutoff)   # bound param — portable SQLite/Postgres
      .scalar()
)
```
*Requires a new composite index `(user_id, edit_type, created_at)` on `disc_edits` — the table currently has **no indexes at all** (`api/app/models.py` DiscEdit has no `__table_args__`).* `[VERIFIED: api/app/models.py]`

### Pattern 3: Salted, truncated IP hash (D-06)

**Example:**
```python
# Source: stdlib ipaddress + hmac; salt from env (fail-fast like OVID_SECRET_KEY)
import hmac, hashlib, ipaddress
def ip_subnet_hash(raw_ip: str | None, salt: bytes) -> str | None:
    if not raw_ip:
        return None                          # fail-open (D-07): absent IP → no signal
    try:
        addr = ipaddress.ip_address(raw_ip)
    except ValueError:
        return None
    prefix = 24 if addr.version == 4 else 48
    net = ipaddress.ip_network(f"{raw_ip}/{prefix}", strict=False)
    return hmac.new(salt, net.network_address.packed, hashlib.sha256).hexdigest()
```

### Pattern 4: Redaction branch in `_disc_to_response` (D-09/D-12)

**Example:**
```python
# Source: api/app/routes/disc.py _disc_to_response (lines 393-445)
titles_resp = [] if disc.status == "unverified" else [_build_title_response(t) for t in disc.titles]
# release + fingerprint_aliases (D-11) always populated; titles withheld when unverified
```

### Anti-Patterns to Avoid

- **Writing `disc.status` outside `verification.py`.** VERIFY-02 consolidated this; any new inline mutation regresses it. The gate and redaction are *around* the primitives, never inside a route mutating status directly.
- **Using the slowapi in-memory limiter for the confirmation cooldown.** Explicitly forbidden by D-14 — inflated Nx under `gunicorn -w 4` (verified in `docker-compose.prod.yml`).
- **`NOW() - INTERVAL '1 hour'` in the cooldown SQL.** Breaks the SQLite test engine and risks TZ drift; compute the cutoff in Python.
- **404 for unverified discs.** D-09 mandates redacted-200; a 404 conflates "pending" with "never submitted" and hides existence from a would-be confirmer.
- **Trusting `X-Forwarded-For` blindly to strengthen a *penalty*.** IP-diversity is a soft *positive* signal; an attacker who spoofs XFF only makes themselves look more diverse (removing a penalty), never triggers a false block. Never let IP feed a hard block (D-04/D-07).
- **Adding an optional-auth path to the currently-anonymous cacheable GET** to let submitters preview their own pending structure — explicitly deferred (D-12).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Truncate IP to /24 or /48 | Manual string splitting on `.`/`:` | stdlib `ipaddress.ip_network(f"{ip}/{prefix}", strict=False)` | Correctly handles IPv6 compression, mapped addresses, malformed input (raises `ValueError` → fail-open). |
| Salted IP hash | `sha256(ip.encode())` | `hmac.new(salt, subnet.packed, sha256)` | Bare hash of a 32-bit space is trivially reversible; HMAC-with-salt is the pseudonymization floor. |
| Worker-safe confirmation counter | In-memory dict / slowapi | Postgres `COUNT` over `disc_edits` | Postgres is the only shared state across gunicorn workers (D-13/D-14). |
| Disc-status transitions | New route-level `disc.status = ...` | `verify()` / `flag_dispute()` / `resolve_dispute()` in `verification.py` | Phase 1 already guards legality, self-verify, and the sole-disputed-writer rule. |
| Structure normalization on the client | Re-parsing IFO/MPLS in Phase 2 | Existing `ovid-client/src/ovid/disc_structure.py::normalize_disc_structure()` | The confirmer's client already computes `NormalizedDiscStructure`; Phase 2 only compares the *submitted server payload* to stored rows. |

**Key insight:** The hardest part of this phase is not any library — it is the **structural-equality tolerance envelope** (D-03), which is pure domain logic that must be written and boundary-tested in-repo. Everything mechanical (IP hashing, counting, redacting) is a few stdlib lines.

## Runtime State Inventory

> Phase 2 adds a new data category (IP-hash) and retires a route. This is not a rename, but the state-inventory lens surfaces real migration/compat items.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `disc_edits` rows already carry `edit_type="verify"`, `user_id`, `created_at` (the cooldown backing store — no backfill needed). **New:** `ip_hash` column will be NULL for all historical rows → fail-open handles this (D-07). | Alembic migration adds nullable `ip_hash` column + composite index; no data backfill. |
| Live service config | Prod `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` sets **no** `--forwarded-allow-ips` / `FORWARDED_ALLOW_IPS` and no `--proxy-headers` override → `request.client.host` is the **proxy socket IP, not the real client** (see Pitfall 1). New env var needed: `OVID_IP_HASH_SALT`. | Document + optionally set `FORWARDED_ALLOW_IPS` on the prod stack and `OVID_IP_HASH_SALT`; fail-open if unset. |
| OS-registered state | None. | None — verified: no cron/systemd/task registrations reference the verify route. |
| Secrets/env vars | **New:** `OVID_IP_HASH_SALT` (salt for D-06). Follow the `OVID_SECRET_KEY` fail-fast-at-import precedent in `auth/config.py` **only if** you decide the salt is mandatory; D-07 fail-open argues for a generated/default-tolerant salt so a missing salt does not hard-block confirmations. | Add to `.env.example` + privacy-policy addendum; decide mandatory-vs-optional (recommend optional-with-warning to preserve fail-open). |
| Build artifacts | None. | None. |

## Common Pitfalls

### Pitfall 1: `request.client.host` returns the proxy IP, not the real client, behind a reverse proxy
**What goes wrong:** IP-diversity becomes useless (every confirmer shares the proxy's IP → every confirmation looks same-subnet, or every confirmation looks distinct if the proxy rotates) — silently defeating VERIFY-04's IP signal.
**Why it happens:** uvicorn's `proxy_headers` defaults to `True`, but only trusts `X-Forwarded-For` from IPs listed in `forwarded_allow_ips`, which **defaults to `127.0.0.1`** (or the `FORWARDED_ALLOW_IPS` env var). Behind a proxy on a different host/container, XFF is *not* trusted and `request.client.host` is the proxy's socket address. `[CITED: https://github.com/kludex/uvicorn/blob/main/docs/settings.md — "Proxy headers ... are restricted to trusted IPs specified in forwarded-allow-ips"]` `[VERIFIED: Config default proxy_headers=True, forwarded_allow_ips=None via Context7 /kludex/uvicorn]`
**How to avoid:** For the signal to work in prod, set `FORWARDED_ALLOW_IPS` (or gunicorn `forwarded_allow_ips`) to the proxy's address/subnet AND ensure the proxy sets `X-Forwarded-For` (the docs' nginx snippet uses `$proxy_add_x_forwarded_for`). Because D-07 mandates fail-open, an unconfigured/absent IP must yield "no signal," never a block. Document this as a deployment note; do not block launch on it.
**Warning signs:** All `ip_hash` values identical across distinct users in staging behind the proxy.

### Pitfall 2: `X-Forwarded-For` is client-controlled and spoofable
**What goes wrong:** If the IP fed a *hard block*, an attacker would spoof XFF to evade it; if it fed a naive *positive*, an attacker spoofs to look diverse.
**Why it happens:** XFF is an attacker-settable header; trusting it only makes sense from a known proxy.
**How to avoid:** Keep IP strictly a **soft** signal (D-04). The only exploit is removing a penalty (looking diverse), which still leaves the **hard cooldown** intact. Never derive a block from IP. Take the *left-most untrusted* hop only after the trusted-proxy chain (uvicorn's ProxyHeaders already does this when `forwarded_allow_ips` is correct).

### Pitfall 3: Structural-tolerance too tight → false disputes on benign rip jitter
**What goes wrong:** Two genuine rips of the same disc differ in track ordering, a codec label (`ac3` vs `AC-3`), or a ±1s duration, and the upgraded match flags `disputed` — punishing an honest second contributor and *failing to verify* (the opposite of the phase goal).
**Why it happens:** `normalize_disc_structure` derives `track_index` from `enumerate()` order and passes through raw `codec`/`language` labels; independent tool versions can reorder or relabel. `[VERIFIED: ovid-client/src/ovid/disc_structure.py]`
**How to avoid:** Compare **canonically**: title *count* exactly; per-title `chapter_count` exactly; audio/subtitle tracks as **sorted multisets** keyed on `(language_code, codec, channels)` rather than positional index; `duration_secs` within a small tolerance window (or exclude if the fingerprint already covers it); normalize codec/case before compare. Pin the envelope with tests at the verify/dispute boundary (D-03 planner note).
**Warning signs:** A test that re-submits a byte-identical-except-track-order payload lands in `disputed`.

### Pitfall 4: Dialect-specific time SQL breaks the SQLite test engine
**What goes wrong:** A cooldown query using `func.now() - text("interval '1 hour'")` passes on Postgres, throws or silently mis-evaluates on the in-memory SQLite test engine, so the guardrail is untested where CI runs.
**Why it happens:** Tests run against SQLite (`conftest.py`), prod is Postgres; interval arithmetic differs. `[VERIFIED: api/tests/conftest.py — sqlite:// in-memory]`
**How to avoid:** Compute `cutoff = datetime.now(timezone.utc) - timedelta(...)` in Python, pass as a bound parameter (Pattern 2).

### Pitfall 5: The fingerprint may already prove structure — or prove nothing (tier-dependent)
**What goes wrong:** For a structural fingerprint (`dvd1-*`, `dvdread1-*`, `bd2-*`), a matching fingerprint *already* implies structural reproduction, so a strict structural re-check is near-redundant. For an **identity fingerprint** (`bd1-aacs-*`, the AACS Disc ID), the fingerprint is a printed/derivable ID that proves **zero** structure — here the structural re-submission + withholding is the *only* real proof of possession. A one-size envelope over-punishes the former and under-tests the latter.
**Why it happens:** OVID's identity model spans tiers (ADR 0001; BD tiers land in Phase 4). `[VERIFIED: .planning/REQUIREMENTS.md FPRINT-01..03]`
**How to avoid:** Note the tier-awareness in the design even though BD fingerprinting is Phase 4; ensure the structural-match logic degrades sanely for identity-only fingerprints (structure is the whole proof) and does not falsely dispute structural-fingerprint confirmations. Surface as an Open Question for the planner.

### Pitfall 6: Redaction must not break the disputed/other-status reads or the sync feed
**What goes wrong:** A blanket "hide titles unless verified" also hides structure for `disputed` discs (which D-09 does not ask to redact) or leaks into the sync `SyncDiffRecord` builder.
**How to avoid:** Redact **only** `status == "unverified"` (D-09 is specific). Leave `disputed`, `verified`, `pending_identification` untouched. The sync feed uses separate `Sync*Record` schemas (`schemas.py`) and its own builders in `sync.py` — confirm the redaction branch lives in `_disc_to_response` and does not touch sync serialization.

## Code Examples

### Enumerate the blast radius of retiring `/verify` (D-02)
```
# Verified callers of POST /v1/disc/{fingerprint}/verify  [VERIFIED: grep across repo]
api/app/routes/disc.py:893-956   # the route + banner — DELETE
api/tests/test_disc_verify.py    # ENTIRE FILE targets the bodyless endpoint — remove/rewrite
                                 #   (11 tests; replace with re-submission-path confirmation tests
                                 #    + one test asserting the retired route now 404/405s)
docs/docker-quickstart.md:72     # API table row — remove
docs/OVID-technical-spec.md:664  # endpoint spec — remove/annotate as retired
docs/api-reference.md:235        # endpoint reference — remove
docs/contributing.md:32          # "you can verify it" prose — reframe to re-submission
# NO callers in: web/ (UI never calls verify — confirms D-02), ovid-client/ (uses submit path), arm/ (register+lookup only)
```

### Confirm ARM is unaffected by redaction (D-10)
```python
# Source: arm/identify_ovid.py _extract_result (lines 120-134)  [VERIFIED]
# Reads ONLY: release.{title,year,imdb_id,tmdb_id}, data.confidence, data.format
# Never touches data["titles"] or tracks → withholding structure is a no-op for ARM.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bodyless `POST /{fp}/verify` flips status on a bare bearer token | Structural re-submission via `POST /v1/disc` (D-01) | This phase | A no-proof endpoint is a pure Sybil bypass; removal deletes the weakest link. |
| `_releases_match` gates on public release fields (`title`/`year`/`tmdb_id`) | Tolerant structural equality over withheld structure (D-03) | This phase | The "match" now proves physical possession, not knowledge of public metadata. |
| No IP captured; account-age unused; rate limit in-memory only | Salted /24 IP-hash + account-age soft signals + Postgres cooldown (D-04/D-06/D-13) | This phase | VERIFY-04 becomes worker-correct and privacy-compliant. |
| Structure returned unconditionally by `_disc_to_response` | Redacted-200 for `unverified` (D-09) | This phase | Closes the echo vector. |

**Deprecated/outdated:**
- `POST /v1/disc/{fingerprint}/verify` — retired (D-02). Any doc/test referencing it must be updated in the same change (see blast-radius list).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ipaddress`/`hmac`/`hashlib` are the right primitives and always available on Python 3.12 | Standard Stack | LOW — stdlib; failure would only be a wrong-primitive choice, caught in review. |
| A2 | Starting thresholds (~24h account-age, ~handful/hr + low-tens/day cooldown) are launch-safe | D-08 | MEDIUM — no fraud data exists (D-08 says validate, not lock). Wrong values → over/under-blocking; mitigated by making them named tunable constants. |
| A3 | Recommending BOTH structural-match (gates verify) AND release-consistency (gates dispute) rather than replacing release-match entirely | Open Questions | MEDIUM — D-03 says "upgrade `_releases_match` to structural equality"; whether release-consistency is *retained* as a dispute trigger is a design call the planner must confirm. Wrong call could drop metadata-conflict detection. |
| A4 | Adding a nullable `ip_hash` column to `disc_edits` (vs. a separate table) is the cleaner minimal-migration path | Architecture | LOW — explicitly planner discretion (D-13); both work. |
| A5 | A missing `OVID_IP_HASH_SALT` should NOT hard-fail at import (unlike `OVID_SECRET_KEY`) to preserve fail-open | Runtime State Inventory | MEDIUM — a mandatory salt contradicts D-07 fail-open; but a weak/default salt weakens pseudonymization. Planner must pick; recommend optional-with-startup-warning. |
| A6 | The IP-diversity signal is worth capturing at all given Pitfall 1 makes it frequently absent behind the prod proxy | D-04/D-06 | MEDIUM — if the proxy trust chain is never configured, the signal is always null and the feature is inert (but harmless, fail-open). Cooldown + account-age still satisfy VERIFY-04's "not user_id alone." |

**If any threshold or the structural envelope is uncertain, it should be surfaced to the user in discuss/plan before locking.**

## Open Questions

1. **Does structural-match REPLACE or SUPPLEMENT release-match in `_handle_existing_disc`?**
   - What we know: D-03 says upgrade `_releases_match` to structural equality; the existing dispute path is triggered by release *mismatch*.
   - What's unclear: With structural match as the verify gate, is a *structural-match + release-mismatch* case a dispute (same disc, disagreeing metadata) or a verify? Truth table: structural-match+release-match→verify; structural-match+release-mismatch→dispute (recommended); structural-mismatch(within tolerance)→verify; structural-mismatch(outside tolerance)→dispute/reject.
   - Recommendation: **Structural equality gates verify (proof of possession); retain release-consistency as the dispute trigger.** Confirm with planner (A3).

2. **Exact structural-tolerance envelope (D-03, planner discretion).**
   - What we know: must tolerate track-ordering/label jitter, must still catch real structural differences.
   - What's unclear: duration tolerance window; whether codec labels are compared or ignored; how identity-only fingerprints (AACS) are handled (Pitfall 5).
   - Recommendation: sorted-multiset track compare on `(language, codec, channels)`; exact title-count and per-title chapter-count; small duration window; boundary tests both directions.

3. **Is `OVID_IP_HASH_SALT` mandatory (fail-fast) or optional (fail-open)?**
   - Recommendation: optional with a startup warning, to preserve D-07 fail-open; document the trade-off in the privacy addendum.

4. **Should the anti-Sybil hard-block return 429 (rate-limited) or 403 (insufficient trust)?**
   - Recommendation: 429 for the cooldown floor (it *is* a rate limit, with `Retry-After`), 403 for a soft-score rejection. Keep the existing `request_id` envelope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Prod cooldown counter (D-13) | ✓ (prod) | 16 | SQLite in tests (portable query, Pattern 2) |
| SQLite (in-memory) | Test suite | ✓ | stdlib | — |
| Python `ipaddress`/`hmac`/`hashlib` | IP hashing (D-06) | ✓ | 3.12 stdlib | — |
| Reverse-proxy trust config (`FORWARDED_ALLOW_IPS`) | Real client IP capture (D-04) | ✗ (not set in prod compose) | — | Fail-open: absent IP → no signal (D-07); cooldown + account-age still satisfy VERIFY-04 |
| `OVID_IP_HASH_SALT` | Salted IP hash (D-06) | ✗ (new var) | — | Optional-with-warning (A5) |

**Missing dependencies with no fallback:** none (nothing blocks execution).
**Missing dependencies with fallback:**
- Proxy trust config + IP-hash salt — both degrade gracefully via fail-open; document as deployment/privacy notes, not blockers.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + FastAPI `TestClient` (in-memory SQLite) |
| Config file | `api/tests/conftest.py` (fixtures + SQLite engine); no `pytest.ini`/`pyproject` pytest section detected in `api/` |
| Quick run command | `cd api && python -m pytest tests/test_disc_submit.py tests/test_verification.py -x -q` |
| Full suite command | `cd api && python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VERIFY-01 | Second distinct contributor's structural re-submission verifies; same submitter re-submitting → 409 | integration | `pytest api/tests/test_confirmation_flow.py -x` | ❌ Wave 0 |
| VERIFY-01 | Self-confirmation rejected through the re-submission path (not just retired `/verify`) | integration | `pytest api/tests/test_confirmation_flow.py::test_self_resubmit_rejected -x` | ❌ Wave 0 |
| VERIFY-03 | 3rd structural-mismatch against a verified disc stays verified, records `dispute_attempted` (A2) | integration | `pytest api/tests/test_confirmation_flow.py::test_verified_disc_not_flipped -x` | ⚠️ partial (`test_disc_submit.py` covers release-level A2; add structural variant) |
| VERIFY-04 | Cooldown hard-blocks after N confirmations/window → 429 | integration | `pytest api/tests/test_anti_sybil.py::test_cooldown_hard_block -x` | ❌ Wave 0 |
| VERIFY-04 | Distinct `user_id` alone does NOT verify when soft-score below threshold; fail-open when signals absent | unit+integration | `pytest api/tests/test_anti_sybil.py -x` | ❌ Wave 0 |
| VERIFY-04 | `/24` IP-hash: same-subnet penalty, distinct positive, null→no-signal | unit | `pytest api/tests/test_anti_sybil.py::test_ip_subnet_hash -x` | ❌ Wave 0 |
| D-03 | Tolerant structural equality: reordered tracks/relabeled codec/±duration → verify; real structural diff → dispute | unit | `pytest api/tests/test_structural_match.py -x` | ❌ Wave 0 |
| D-09 | `GET` on unverified disc → 200 withholding `titles`/tracks, keeping `release` + `fingerprint_aliases` | integration | `pytest api/tests/test_lookup_redaction.py -x` | ❌ Wave 0 |
| D-02 | Retired `/verify` route now 404/405; `test_disc_verify.py` removed | integration | `pytest api/tests/test_route_retired.py -x` | ❌ Wave 0 (delete old file) |
| D-13 | Cooldown query is worker-safe/portable (runs on SQLite test engine) | integration | covered by `test_anti_sybil.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd api && python -m pytest tests/test_verification.py tests/test_structural_match.py tests/test_anti_sybil.py -x -q`
- **Per wave merge:** `cd api && python -m pytest -q`
- **Phase gate:** Full API suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `api/tests/test_structural_match.py` — covers D-03 tolerance envelope (both boundary directions)
- [ ] `api/tests/test_anti_sybil.py` — covers VERIFY-04 cooldown, weighted score, IP-hash, fail-open
- [ ] `api/tests/test_confirmation_flow.py` — covers VERIFY-01/VERIFY-03 through the re-submission path
- [ ] `api/tests/test_lookup_redaction.py` — covers D-09 redacted-200
- [ ] `api/tests/test_route_retired.py` — asserts D-02 removal; **delete** `api/tests/test_disc_verify.py`
- [ ] Shared fixtures already exist (`second_user`, `second_auth_header`, `seed_test_disc(status=...)`, `test_user`, `trusted_user`) in `conftest.py` — extend with an `account_age`/`created_at`-override helper for the account-age soft-signal tests.

## Security Domain

> `security_enforcement: true`, `security_asvs_level: 1`, `security_block_on: high`.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture | yes | Trust decision (confirmation) kept server-authoritative in `verification.py` + `anti_sybil.py`; never client-asserted. |
| V4 Access Control | yes | Self-verification guard (`verify()` rejects `submitted_by == actor.id`); dispute-resolution restricted to trusted/editor/admin roles (existing). |
| V5 Input Validation | yes | Pydantic v2 request schemas (`DiscSubmitRequest`) already validate submitted structure; keep structural-match comparison defensive against malformed/oversized payloads. |
| V6 Cryptography | yes | Salted HMAC-SHA256 for IP pseudonymization — **do not hand-roll**; use stdlib `hmac`. Salt sourced from env, not committed. |
| V7 Error Handling & Logging | yes | Preserve the `request_id` + `x-request-id` envelope on new 429/403 responses; do **not** log raw IPs (log the hash or nothing) — a raw-IP log line would reintroduce the data category D-06 forbids. |
| V8 Data Protection / Privacy | yes | IP is GDPR personal data even hashed → truncation (/24, /48) + salt + ≤90-day retention + privacy-policy addendum (D-06). Redacted-200 (D-09) is itself a data-minimization control against the echo vector. |
| V11 Business Logic / Anti-Automation | yes | The whole phase — Sybil resistance: cooldown floor + weighted soft signals; distinct `user_id` insufficient (D-05). |

### Known Threat Patterns for FastAPI + Postgres two-contributor trust

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sockpuppet "confirms" by echoing the first submitter's uploaded structure | Spoofing | Withhold structure from public reads (D-09) + require independent structural reproduction (D-01/D-03). |
| Sybil farm of fresh accounts rapidly confirming | Spoofing / Elevation | Postgres confirmation cooldown (hard floor, D-13) + account-age soft penalty (D-08). |
| Same-operator confirmer on the same network | Spoofing | IP-diversity soft penalty via /24 hash (D-06) — soft, offsettable, fail-open. |
| `X-Forwarded-For` spoofing to fake IP diversity | Tampering | Keep IP a soft *positive* signal only; trust XFF only from a configured proxy; never derive a hard block from IP (Pitfall 2). |
| Original submitter self-verifies | Elevation of Privilege | `verify()` self-guard (Phase 1) — add a re-submission-path test (VERIFY-01). |
| Third party silently flips a verified disc to disputed | Tampering | `flag_dispute()` no-ops on verified; A2 audit-and-stay-verified contract (VERIFY-03). |
| Raw IP leaked via logs or DB | Information Disclosure | Store only salted/truncated hash; never log raw IP; bounded retention (D-06). |
| Cooldown bypass via multi-worker in-memory limiter | Elevation | Postgres-backed counter, not slowapi in-memory (D-14). |

## Sources

### Primary (HIGH confidence)
- Local codebase (read directly this session): `api/app/routes/disc.py`, `api/app/verification.py`, `api/app/schemas.py`, `api/app/models.py`, `api/app/rate_limit.py`, `api/app/middleware.py`, `api/main.py`, `api/tests/conftest.py`, `api/tests/test_disc_verify.py`, `ovid-client/src/ovid/disc_structure.py`, `arm/identify_ovid.py`, `docker-compose.prod.yml`, `api/Dockerfile`.
- Context7 `/kludex/uvicorn` — `Config` defaults (`proxy_headers=True`, `forwarded_allow_ips=None`) and Deployment > Proxies/Forwarded-Headers docs (client-IP trust behavior).
- `.planning/phases/02-two-contributor-verification-workflow/02-CONTEXT.md` (locked decisions D-01..D-14), `.planning/REQUIREMENTS.md` (VERIFY-01/03/04), `.planning/config.json`.

### Secondary (MEDIUM confidence)
- Cross-repo grep enumeration of `/verify` callers (docs/tests/web/arm/ovid-client).

### Tertiary (LOW confidence)
- Starting threshold values (D-08) — training-informed launch-safe guesses, explicitly flagged for validation (A2).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all installed/stdlib; verified against installed files and Context7.
- Architecture: HIGH — mirrors the existing Phase 1 layering (domain logic outside routes, single status-writer).
- Pitfalls: HIGH for #1/#4/#6 (verified from code + docs), MEDIUM for #3/#5 (domain-judgement on tolerance/tiering).
- Thresholds (D-08): LOW by design — no fraud data; tunable constants.

**Research date:** 2026-07-05
**Valid until:** 2026-08-04 (stable domain; the only external dependency, uvicorn proxy-header behavior, is long-stable — re-verify if the prod proxy/gunicorn invocation changes).
</content>
</invoke>
