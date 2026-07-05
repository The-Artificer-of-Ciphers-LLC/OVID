# Architecture Research

**Domain:** Community disc-identity/metadata database (FastAPI + PostgreSQL API, Python client library, Next.js web) — remaining v0.2.0 scope
**Researched:** 2026-07-05
**Confidence:** HIGH (based on direct reading of current source, ADR 0001, and the technical spec; MEDIUM on the matrix256 external assessment, which rests on a single blog-post source)

This is not a greenfield ecosystem survey. OVID's architecture already exists and is documented in `.planning/codebase/ARCHITECTURE.md` / `STRUCTURE.md`. This document extends that baseline to cover **only the remaining v0.2.0 work**: the Lookup Alias data model, a multi-method Disc Identity interface, the two-contributor verification state machine, and Redis-backed rate limiting — plus how a pressing-level fingerprint (matrix256) would fit if adopted later.

## Current State — More Built Than PROJECT.md Suggests

Direct code reading shows the alias mechanism is **substantially implemented already**, ahead of what `.planning/PROJECT.md`'s "Active" list implies:

| Piece | File | State |
|---|---|---|
| `DiscIdentityAlias` ORM table (`disc_id` FK, unique `fingerprint`, `created_at`) | `api/app/models.py:128-149` | Built |
| `resolve_disc_identity` / `resolve_existing_disc_for_identities` / `attach_lookup_aliases` / `DiscIdentityConflict` | `api/app/disc_identity.py` | Built — fully string-generic, not DVD-specific |
| `DiscSubmitRequest.fingerprint_aliases`, `DiscRegisterRequest.fingerprint_aliases` | `api/app/schemas.py` | Built |
| Client-side `DiscIdentity` / `DiscIdentitySet` / `identify_dvd()` (dvd1 primary, dvdread1 alias, silent fallback + diagnostics) | `ovid-client/src/ovid/disc_identity.py` | Built for DVD only |
| `Disc.from_path()` wires `identify_dvd()` into `_identity_set`, `cli.py` passes it into `build_submit_payload()` | `ovid-client/src/ovid/disc.py`, `cli.py`, `submission.py` | Built for DVD only |
| Two-contributor auto-verify on matching second submission (`_releases_match`), explicit `POST /v1/disc/{fingerprint}/verify` (blocks self-verify), `POST /v1/disc/{fingerprint}/resolve` (trusted/editor/admin dispute resolution) | `api/app/routes/disc.py` | Built, but **scattered across three code paths**, not one state machine |
| Redis-backed rate limiting | `api/app/rate_limit.py` | **Not built** — `storage_uri="memory://"`, no `redis` service in any `docker-compose*.yml` |
| Blu-ray Tier1/Tier2 as coexisting alias pair | `ovid-client/src/ovid/bd_disc.py` | **Not built** — picks exactly one tier, no `DiscIdentitySet`, no `bd_identity.py` analog |
| Alias visibility in lookup response | `api/app/schemas.py` `DiscLookupResponse` | **Not built** — aliases aren't returned to callers |

This matters for the roadmap: the alias **storage and resolution layer is done and format-agnostic**. The remaining work is concentrated in three places — (1) generalizing the *client-side* identity-computation pattern from DVD-only to Blu-ray/UHD, (2) closing small but real gaps in the existing alias/verification code before Phase 3 can safely promote `dvdread1-*`, and (3) adding the Redis rate-limit backend, which has no dependency on the other two.

## Standard Architecture (Extension Points Only)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ovid-client                                                               │
│                                                                            │
│  ┌────────────┐   ┌────────────┐   ┌──────────────────────────────────┐  │
│  │  Disc (DVD) │   │  BDDisc    │   │  (new, cross-format) matrix256   │  │
│  │  identify_  │   │  ← extend  │   │  identity method — reads paths/  │  │
│  │  dvd() ✓    │   │  to build  │   │  sizes only, no format branching │  │
│  │  built      │   │  DiscIdent-│   │  needed                          │  │
│  │             │   │  itySet ✗  │   │                                  │  │
│  └─────┬──────┘   └─────┬──────┘   └────────────────┬─────────────────┘  │
│        │  DiscIdentitySet { primary, aliases[], diagnostics[] }          │
│        └────────────────────────┬───────────────────────────────────────┘│
│                                  ▼                                        │
│                     build_submit_payload() ✓ built, format-agnostic      │
└──────────────────────────────────┬───────────────────────────────────────┘
                                    │ POST /v1/disc { fingerprint, fingerprint_aliases[] }
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ api/app/disc_identity.py  ✓ built, already format/method-agnostic        │
│   resolve_existing_disc_for_identities() → attach_lookup_aliases()       │
│                                  │                                        │
│                                  ▼                                        │
│ api/app/models.py: Disc.fingerprint (unique) ⟷ DiscIdentityAlias.        │
│ fingerprint (unique) — two SEPARATE unique constraints, no cross-table   │
│ uniqueness guarantee ✗ gap                                                │
│                                  │                                        │
│                                  ▼                                        │
│ api/app/routes/disc.py: submit_disc() / verify_disc() / resolve_dispute()│
│  — three separate status-transition code paths ✗ needs consolidation     │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ Rate limiting — orthogonal, no dependency on the above                   │
│  api/app/rate_limit.py: Limiter(storage_uri="memory://") ✗               │
│  → Limiter(storage_uri=REDIS_URL) + new `redis` service in compose files │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities (remaining work only)

| Component | Responsibility | Change needed |
|-----------|----------------|----------------|
| `ovid-client/src/ovid/bd_identity.py` (new) | Mirror `disc_identity.py`'s pattern for Blu-ray/UHD: compute AACS Tier 1 **and** attempt BDMV Tier 2 whenever playlists survive the 60s filter, regardless of which one wins primacy. Returns a `DiscIdentitySet` (primary = Tier 1 if available else Tier 2, alias = the other tier when both compute). | New module + `bd_disc.py` refactor: `_build()` currently `return`s immediately on Tier 1 success without ever computing the Tier 2 canonical string/hash, so the two can never coexist as alias pairs today |
| `ovid-client/src/ovid/disc_identity.py` (generalize) | Promote `DiscIdentity`/`DiscIdentitySet`/`DiscIdentityDiagnostic` out of the DVD-only module into a format-neutral home (or keep them there and have `bd_identity.py` import them) so DVD, BD, and any future method (matrix256) share one result type | Extract shared dataclasses; keep `identify_dvd()` DVD-specific, add `identify_bd()`, and (if adopted) `identify_matrix256(path)` as a peer that runs independent of disc format |
| `api/app/models.py` `DiscIdentityAlias` | Guarantee no fingerprint string exists in both `discs.fingerprint` and `disc_identity_aliases.fingerprint` for different discs | Current check-then-insert in `attach_lookup_aliases`/`resolve_existing_disc_for_identities` is correct in a single transaction but is not race-safe across gunicorn workers submitting the same disc concurrently. Options: (a) `SELECT ... FOR UPDATE` around the check+insert within the existing transaction (cheapest — no schema change), or (b) unify into one `disc_identities` table (`disc_id`, `fingerprint` UNIQUE, `is_primary`) so a single unique index covers both. (a) is lower-risk for v0.2.0; (b) is architecturally cleaner but is itself a `dvd1-*`-affecting migration and should not be bundled with the Phase 2→3 promotion migration |
| `api/app/schemas.py` `DiscLookupResponse` | Expose known aliases on lookup so ARM/CLI/web consumers can see all Disc Identity strings for a pressing | Add `fingerprint_aliases: list[str]` field, populated from `disc.identity_aliases` (relationship already exists) |
| `api/app/verification.py` (new) | Single source of truth for the `unverified → verified → disputed` state machine, replacing the transition logic currently split across `submit_disc()`, `verify_disc()`, and `resolve_dispute()` in `routes/disc.py` | Extract `apply_second_submission(disc, submitter, release) -> Transition`, `apply_explicit_verify(disc, verifier)`, `apply_dispute_resolution(disc, action, resolver)` — mirrors the existing `disc_identity.py` service-layer pattern (pure functions + Session, no route-layer business logic) |
| `api/app/rate_limit.py` | Shared rate-limit counters across gunicorn workers | `storage_uri=os.environ.get("REDIS_URL", "memory://")` — `slowapi`/`limits` already supports a `redis://` URI with no other code change; add `redis:7-alpine` service to `docker-compose.yml` and `docker-compose.prod.yml`, `REDIS_URL` to `.env.example` |

## Architectural Patterns

### Pattern 1: Format-agnostic Identity Method as the extension seam (not format branching)

**What:** Every current identity method (`ovid-dvd-1`, `libdvdread-disc-id`, and eventually AACS/BDMV/matrix256) already produces the same shape — `DiscIdentity(fingerprint, method, fingerprint_version)` — collected into one `DiscIdentitySet(primary, aliases[], diagnostics[])`. The server never inspects `method` or format; it only ever sees a primary string plus a list of alias strings (`resolve_existing_disc_for_identities`, `attach_lookup_aliases`).

**When to use:** Any new identity method (Blu-ray Tier 2 alongside Tier 1, matrix256, a hypothetical future `dvd2-*`) should be added as one more producer feeding into the same `DiscIdentitySet`, never as a new branch in the API/DB layer.

**Trade-off:** Keeps the server permanently stable while methods evolve, at the cost of requiring every client-side format module (DVD, BD/UHD, future) to independently implement "try method, fall back, record diagnostic" rather than sharing one runner. Given only two formats exist today, a small shared helper (`run_identity_methods(methods: list[Callable[[], DiscIdentity | None]]) -> DiscIdentitySet`) is worth extracting once BD identity is added, so DVD and BD don't duplicate the try/except/diagnostic bookkeeping.

**Example (target shape for BD):**
```python
# ovid-client/src/ovid/bd_identity.py (new)
def identify_bd(reader: BDFolderReader, is_uhd: bool) -> DiscIdentitySet:
    primary: DiscIdentity | None = None
    aliases: list[DiscIdentity] = []
    diagnostics: list[DiscIdentityDiagnostic] = []

    tier1 = _try_aacs_tier1(reader, is_uhd)  # existing helper, unchanged
    tier2 = _try_structure_tier2(reader, is_uhd)  # NEW: always attempted

    if tier1 is not None:
        primary = tier1
        if tier2 is not None:
            aliases.append(tier2)
    elif tier2 is not None:
        primary = tier2
    else:
        raise ValueError("No Blu-ray identity method succeeded")

    return DiscIdentitySet(primary=primary, aliases=aliases, diagnostics=diagnostics)
```

### Pattern 2: Alias resolution is already a two-table lookup, not a join

**What:** `resolve_disc_identity()` queries `discs.fingerprint` first, then falls back to `disc_identity_aliases.fingerprint` joined back to `discs` by `disc_id`. This is O(1) indexed lookups on both tables (`idx_discs_fingerprint`, `idx_disc_identity_aliases_fingerprint`), not a single UNION query.

**When to use:** Any new lookup path (e.g. a future `GET /v1/disc/{fingerprint}/aliases`, or matrix256 lookups) should reuse `resolve_disc_identity()` rather than querying `Disc` directly, or it will silently fail to resolve alias-only fingerprints.

**Trade-off:** Simple and already correct for reads. The gap is only on the *write* side (race condition noted above) — reads are safe as-is.

### Pattern 3: Verification transitions belong in a service module, not routes

**What:** `disc_identity.py` and `sync.py` already establish the convention of pulling business logic out of `routes/disc.py` into small, pure, session-taking functions. Verification state transitions do not yet follow this convention — `submit_disc()` contains inline auto-verify/dispute logic, `verify_disc()` contains a second, slightly different unverified→verified path (no release-match check, blocks self-verify), and `resolve_dispute()` contains a third (role-gated, only from `disputed`).

**When to use:** Before hardening "two-contributor verification workflow live" for v0.2.0 exit, consolidate into `api/app/verification.py` following the `disc_identity.py` shape (dataclass result + exception type + pure functions). This also closes a real correctness gap: today, a *third* submitter's conflicting metadata against an **already-verified** disc falls into the same `_releases_match` branch as a first-vs-second comparison and can flip a verified disc back to `disputed` without moderation. A single state-machine module makes "verified is sticky against non-admin overwrites; only `/resolve` moves `disputed` ↔ `verified`" an enforceable invariant instead of an implicit property of route ordering.

**Trade-off:** Pure refactor risk (touches three passing endpoints) — sequence it as its own plan/PR with full regression coverage on `test_disc_submit.py`/`test_disc_verify.py`/`test_disc_dispute.py` before adding new behavior on top.

## Data Flow

### Submission with multiple identity strings (target, DVD already matches this; BD needs the same shape)

```
ovid-client: Disc.from_path() / BDDisc.from_path()
    → identify_dvd() / identify_bd()  → DiscIdentitySet(primary, aliases[], diagnostics[])
    → build_submit_payload(structure, metadata, identity_set)
        → { "fingerprint": primary, "fingerprint_aliases": [alias1, alias2, ...], ... }
    ↓ POST /v1/disc
api: resolve_existing_disc_for_identities(db, fingerprint, fingerprint_aliases)
    → checks EVERY submitted string (primary + aliases) against discs.fingerprint
      then disc_identity_aliases.fingerprint
    → DiscIdentityConflict if two submitted strings already resolve to different discs
    → else: create Disc row (fingerprint = primary) + attach_lookup_aliases() for the rest
```

No API/schema change is required to add matrix256 or Blu-ray Tier 2 as additional aliases — the payload shape and resolution logic are already generic over "however many identity strings the client knows." This is the single most important finding for roadmap sequencing: **the hard part (alias storage/resolution) is done; the remaining work is client-side computation and closing edge cases, not a new subsystem.**

### Verification (current, to be consolidated per Pattern 3)

```
Second distinct submitter → POST /v1/disc (same fingerprint or a known alias)
    → resolve_existing_disc_for_identities() finds the existing Disc
    → attach_lookup_aliases() records any newly-seen alias on the existing disc
    → _releases_match(existing, new_release) →
        match:    status → verified, verified_by = submitter, DiscEdit(edit_type="verify")
        mismatch: status → disputed,                         DiscEdit(edit_type="disputed")
    OR
Explicit second contributor → POST /v1/disc/{fingerprint}/verify
    → blocks if submitter == current_user (no self-verify)
    → status → verified (idempotent if already verified)
    OR
Trusted/editor/admin → POST /v1/disc/{fingerprint}/resolve  (only valid from status=disputed)
    → action=verify → status → verified, verified_by = resolver
    → action=reject → status → unverified
```

### Rate limiting (target)

```
Any request → api/main.py registers `limiter` (slowapi) →
    @limiter.limit(_dynamic_limit) per route →
    _auth_aware_key(request) → "user:{id}" or client IP →
    Limiter.storage: currently in-process dict (memory://) — per-gunicorn-worker,
        so N workers = N× effective limit
    → target: Limiter.storage = Redis client (storage_uri=REDIS_URL) →
        shared counters across all gunicorn workers → correct global limit
```

## matrix256 — Architectural Fit Assessment

Per the fetched source (`shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint`, confidence: MEDIUM — single blog-post source, not cross-verified against a second independent description):

- matrix256 hashes **filesystem metadata only** — relative path (NFC-normalized UTF-8) and reported file size, explicitly excluding content, timestamps, permissions, and extended attributes. Output is a 64-char lowercase SHA-256 hex digest with an explicit versioning convention (`matrix256`, `matrix256v2`, ...) matching OVID's own `dvd1-`/`dvd2-` style version-in-prefix approach.
- It requires **no format-specific library** (no `libaacs`, `libdvdread`, `libbluray`) — only filesystem enumeration. This makes it the *first* identity method in OVID's design space that is genuinely **format-agnostic**: it applies identically to DVD, BD, and UHD sources, including AACS-encrypted Blu-rays that haven't been decrypted (since directory/size listings are plaintext even when file contents are encrypted).
- The author reports it distinguishes different pressings/editions/regional variants of the same title — i.e., it targets the same "which exact physical pressing" question as OVID-DVD-1/AACS Disc ID, not the "what plays" question that Normalized Disc Structure answers. It is squarely a **Disc Identity Method**, never a Disc Structure concern.

**Recommended fit: additional alias, never a replacement, and never primary in v0.2.0.**

- As an **alias**: zero schema or API change required (see Data Flow above) — it is exactly one more string in `fingerprint_aliases`. It would run as a new peer under Pattern 1 (`identify_matrix256(path) -> DiscIdentity`), computed unconditionally for every disc regardless of format, since it needs no format-specific reader beyond the filesystem walk already available from `pycdlib`/mounted-path access.
- **Not a replacement** for `dvd1-*`/`dvdread1-*`/AACS: those are the *structural* families this project has deliberately chosen over filesystem/timestamp-based approaches (see tech spec §2.0's explicit rejection of the Windows `dvdid` algorithm for exactly this reason — it uses filesystem timestamps and breaks on re-rip/re-copy). matrix256 excludes timestamps but still depends on file *sizes and paths as reported by the filesystem*, which is a materially different stability contract than a pure logical-structure hash (IFO/MPLS field values). It has not been running in production anywhere OVID could verify collision/stability behavior at OVID's scale — treat it the same way ADR 0001 treated libdvdread: introduce as a new Fingerprint Version behind the alias mechanism, observe, and only consider promotion after an equivalent Phase 1→2→3 staging, never fast-tracked to primary.
- **Migration implication relative to ADR 0001 staging: none required beyond "yet another alias producer."** It does not compete with or block the `dvd1-*` → `dvdread1-*` promotion path; the two are orthogonal (one is a DVD-family method promotion, the other is a new cross-format supplementary method). If pursued, it belongs in a *later* milestone (v0.3.0+) — it is explicitly outside the v0.2.0 exit criteria and should not be allowed to expand v0.2.0 scope.

## Build Order (dependency-driven, honoring ADR 0001 staging + `dvd1-*` stability)

1. **Redis-backed rate limiting** — zero dependency on anything else in this list. Do first or in parallel; it only touches `rate_limit.py`, `.env.example`, and compose files. No risk to `dvd1-*` or alias correctness.
2. **Expose aliases in `DiscLookupResponse`** — small, additive, no migration. Needed before Blu-ray Tier1/Tier2 coexistence ships, so contributors/ARM can actually see that a lookup resolved through an alias (useful for debugging Tier 2→Tier 1 upgrades and for QA-ing the alias mechanism before trusting it for `dvd1-*`→`dvdread1-*` promotion).
3. **Close the alias write-path race condition** (`SELECT ... FOR UPDATE` in `attach_lookup_aliases`/`resolve_existing_disc_for_identities`, or equivalent transaction-level guard) — **must land before** Phase 3 promotion, since promotion increases write concurrency on the same fingerprint namespace (many discs simultaneously gaining a new primary) and any race here would corrupt the `dvd1-*` stability guarantee ADR 0001 exists to protect.
4. **Consolidate verification into `api/app/verification.py`** (Pattern 3) — independent of the identity work; can run in parallel with steps 1–3. Should land before "two-contributor verification workflow live" is declared an exit criterion, since the current scattered logic has a real correctness gap (verified discs can flip to disputed via a third submitter, see Pattern 3).
5. **Blu-ray/UHD Tier 1 + Tier 2 as a `DiscIdentitySet`** (Pattern 1, `bd_identity.py`) — depends on nothing above except benefiting from step 2 (visible aliases) for verification during development. This is the actual "Blu-ray fingerprinting to real parity with the DVD path" work and is independent of the DVD `dvd1-*`/`dvdread1-*` migration entirely — different fingerprint namespace, same mechanism.
6. **ADR 0001 Phase 2 hardening sign-off** — once steps 2–3 land, Phase 2 ("alias lookup + submission fully supported in API and database") is genuinely complete and testable end-to-end, not just functionally present.
7. **ADR 0001 Phase 3 promotion (`dvdread1-*` becomes primary)** — only after step 6. Requires a data migration that: (a) only promotes discs that already have a recorded `dvdread1-*` alias (never invents one), (b) swaps `Disc.fingerprint` and the corresponding `DiscIdentityAlias.fingerprint` row values inside one transaction per disc to respect both unique constraints without a transient collision, (c) leaves discs with no `dvdread1-*` alias on `dvd1-*` permanently (they were fingerprinted before libdvdread was available, or on a system where it never succeeded) — `dvd1-*` remains a valid, resolvable alias forever regardless of Phase 3, satisfying the PROJECT.md compatibility constraint. This step is the highest-risk item in the remaining v0.2.0 scope and should be its own isolated plan with a dry-run/rollback path.
8. **matrix256 (if pursued)** — deliberately placed after all of the above, and likely deferred past v0.2.0 entirely per milestone scope. Requires no schema change; only a new client-side identity method module following Pattern 1.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Branching the server on fingerprint prefix/format

**What people do:** Add `if fingerprint.startswith("bd1-aacs-")` type logic in `disc_identity.py` or routes to special-case a method.
**Why it's wrong:** Defeats the entire point of the alias abstraction (Pattern 1) — the server has been kept deliberately ignorant of *which* method produced a string, and that's why matrix256/Tier2-Tier1 coexistence require zero server changes today. Any format-aware branching in `api/app/` reintroduces exactly the fragmentation ADR 0001 was written to avoid.
**Instead:** Keep all format/method knowledge in `ovid-client`; the API only ever sees "a primary string and some alias strings."

### Anti-Pattern 2: Bundling the Phase 3 promotion migration with unrelated schema cleanup

**What people do:** Since a migration touching `discs`/`disc_identity_aliases` is already "in flight," fold in the unrelated `disc_identities` table unification (option (b) in the alias-uniqueness fix above) at the same time.
**Why it's wrong:** Phase 3 promotion is the single highest-risk, `dvd1-*`-adjacent change in this milestone. Combining it with a structural table rename/merge multiplies blast radius and rollback complexity for zero v0.2.0-exit-criteria benefit.
**Instead:** If the alias-uniqueness fix needs the "single table" approach rather than `SELECT ... FOR UPDATE`, land it as its own prior migration (step 3), fully soaked, before Phase 3 promotion (step 7) touches the same tables again.

### Anti-Pattern 3: Letting verification status regress without human moderation

**What people do:** Treat every subsequent submission against an existing fingerprint the same way, regardless of current status — as `submit_disc()` does today by feeding a third submitter's mismatched metadata through the same `_releases_match` branch used for the original unverified→verified transition.
**Why it's wrong:** A `verified` disc represents community-confirmed data; letting any later submitter silently flip it to `disputed` (or re-verify it) without going through `/resolve`'s role gate undermines the trust signal the two-contributor model exists to build.
**Instead:** Once Pattern 3's `verification.py` exists, make `verified` and `disputed` sticky against non-privileged callers — only `unverified` accepts the auto-transition logic; `verified`/`disputed` require the explicit `/verify` or `/resolve` (role-gated) endpoints.

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `ovid-client` identity modules (`disc_identity.py`, future `bd_identity.py`) ↔ `submission.py` | Direct function call, `DiscIdentitySet` value object | Keep this the *only* place format knowledge exists client-side |
| `api/app/routes/disc.py` ↔ `api/app/disc_identity.py` | Direct function call, `Session`-scoped | Already the established pattern — extend `verification.py` the same way, don't add logic back into routes |
| `api/app/rate_limit.py` ↔ Redis | `storage_uri=redis://...` via `limits`/`slowapi`'s built-in Redis backend | No custom Redis client code needed — this is a config-only change library-side |
| Web/ARM/CLI ↔ API | HTTP, unchanged | No client-visible contract change for alias/verification work beyond adding `fingerprint_aliases` to `DiscLookupResponse` |

## Sources

- `.planning/PROJECT.md`, `docs/OVID-technical-spec.md`, `docs/adr/0001-stage-libdvdread-disc-identity-migration.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md` (project-internal, HIGH confidence)
- Direct source reads: `api/app/disc_identity.py`, `api/app/models.py`, `api/app/schemas.py`, `api/app/routes/disc.py`, `api/app/rate_limit.py`, `ovid-client/src/ovid/disc_identity.py`, `dvdread_adapter.py`, `disc.py`, `bd_disc.py`, `bd_fingerprint.py`, `fingerprint.py`, `submission.py`, `cli.py`, `docker-compose.yml` (HIGH confidence — ground truth)
- [matrix256: a pressing-level disc fingerprint](https://shitwolfymakes.substack.com/p/matrix256-a-pressing-level-disc-fingerprint) (MEDIUM confidence — single external source, not independently cross-verified; assessment above treats its stability/uniqueness claims as author-reported, not lab-verified)

---
*Architecture research for: OVID v0.2.0 remaining scope (Lookup Aliases, multi-method Disc Identity, verification state machine, Redis rate limiting)*
*Researched: 2026-07-05*
