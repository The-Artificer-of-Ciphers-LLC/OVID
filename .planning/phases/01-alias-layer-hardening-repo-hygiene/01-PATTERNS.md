# Phase 1: Alias-Layer Hardening & Repo Hygiene - Pattern Map

**Mapped:** 2026-07-05
**Files analyzed:** 8 code/test files + repo-hygiene targets
**Analogs found:** 8 / 8 (all in-tree — no external precedent needed)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `api/app/verification.py` (NEW) | service (domain) | request-response / state-transition | `api/app/disc_identity.py` | exact (same house style: flat funcs + domain exception, imported by routes) |
| `api/app/disc_identity.py` (MODIFY) | service (domain) | CRUD (race-safe insert) | itself — `attach_lookup_aliases` lines 115-128 | in-place restructure |
| `api/app/routes/disc.py` (MODIFY) | route (controller) | request-response | itself — `verify_disc`, `resolve_dispute`, `submit_disc`, `_disc_to_response` | in-place |
| `api/app/schemas.py` (MODIFY) | model (Pydantic contract) | transform | `TitleResponse` / `ReleaseResponse` (lines 22-63) | exact |
| `api/app/models.py` (MODIFY) | model (ORM) | CRUD | `Disc.titles` relationship (line 101) | exact |
| `api/tests/test_disc_identity_regression.py` (NEW) | test | request-response assertion | `test_disc_identity_aliases.py`, `seed_test_disc` | role-match |
| `api/tests/test_verification.py` (NEW) | test | unit / state-transition | `TestDiscSubmitErrors` class shape | role-match |
| `api/tests/test_disc_identity_race.py` (NEW) | test | unit / deterministic fault-injection | `conftest.py` fixtures + CLAUDE.md fs-monkeypatch rule | role-match |
| `api/tests/test_disc_submit.py`, `test_dispute.py` (MODIFY) | test | integration | existing classes in those files | in-place |
| repo root scripts + `.gitignore` (MODIFY/DELETE) | config / VCS | — | — | n/a |

## Pattern Assignments

### `api/app/verification.py` (NEW — service, state-transition)

**Analog:** `api/app/disc_identity.py` (read in full). Copy its module shape exactly: one-line module docstring, a frozen domain exception carrying context fields, flat module-level functions taking `(db: Session, ...)` first, no service class.

**Module docstring + domain-exception pattern** — mirror `disc_identity.py:1,20-28`:
```python
"""Guarded verification state machine — the single writer of disc.status."""
# exception mirrors DiscIdentityConflict (disc_identity.py:20-28): __init__ stores
# structured attrs then calls super().__init__(<human message>)
class VerificationTransitionError(Exception):
    def __init__(self, disc_id, current_status, attempted_status) -> None:
        self.disc_id = disc_id
        self.current_status = current_status
        self.attempted_status = attempted_status
        super().__init__(
            f"Illegal transition {current_status!r}→{attempted_status!r} for disc {disc_id}"
        )
```

**Transition table + functions** (per RESEARCH Pattern 2, D-08/D-09/D-11/D-12):
```python
LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({
    ("unverified", "verified"),
    ("disputed",   "verified"),    # via resolve only
    ("disputed",   "unverified"),  # via resolve only
    # NO ("*", "disputed") entry — disputed reachable ONLY via flag_dispute (D-09)
})

def verify(db, disc, actor) -> bool:      # returns True iff a transition occurred (Pitfall 4)
def flag_dispute(db, disc, actor, reason) -> bool:  # ONLY writer of status="disputed"; refuses verified discs
def resolve_dispute(db, disc, actor, action) -> None:  # absorbs lines 240-246
```
- `actor` is the full `User` object, NOT a bare id (D-12 Phase-2 seam).
- `verify()` returns `bool` so the route keeps its idempotent-200/no-edit vs. auto-verify/edit distinction (Pitfall 4). Do NOT return a 400 for `verified→verify`.
- Move the self-verify invariant INTO `verify()` (D-11), raising `VerificationTransitionError` with `attempted_status="verified"`.

---

### `api/app/disc_identity.py` (MODIFY — race-safe insert, IDENT-02)

**Analog:** the file itself. Current racing code at **lines 115-128** (`attach_lookup_aliases`, check-then-`add()`) and the disc-insert flow.

**Current TOCTOU block to replace** (`disc_identity.py:122-128`):
```python
for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
    resolution = resolve_disc_identity(db, alias)   # read (T0)
    if resolution is None:
        db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))  # insert (T1) — race window
        continue
    if resolution.disc.id != disc.id:
        raise DiscIdentityConflict(alias, resolution.disc)
```

**Replacement pattern** (RESEARCH Pattern 1; savepoint + catch + re-resolve):
```python
from sqlalchemy.exc import IntegrityError

for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
    try:
        with db.begin_nested():                          # SAVEPOINT — isolates this insert
            db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))
            db.flush()                                    # force INSERT now — raises here on conflict
    except IntegrityError:
        db.expire_all()                                   # discard stale identity map (Pitfall 2)
        winner = resolve_disc_identity(db, alias)
        if winner is None:
            raise                                         # unexpected — do not swallow (no-wave-off)
        if winner.disc.id != disc.id:
            raise DiscIdentityConflict(alias, winner.disc)
        # else our disc already owns it → idempotent no-op
```
- Catch `sqlalchemy.exc.IntegrityError` **specifically**, never bare `Exception` (RESEARCH anti-pattern).
- Reuse the existing `DiscIdentityConflict` (lines 20-28) unchanged for genuine cross-disc collisions.
- Same savepoint shape wraps the `Disc` row insert at the two `routes/disc.py` submission call sites.

---

### `api/app/routes/disc.py` (MODIFY — VERIFY-02 + IDENT-01 + IDENT-02)

**Analog:** the file itself. Thin-handler + `_helper` response-shaper conventions already established.

**Error-envelope + raise-and-catch boundary** — the template already used for `DiscIdentityConflict` (lines 52-59, 62-71, 409-410). Add the identical pattern for `VerificationTransitionError`:
```python
try:
    transitioned = verify(db, disc, current_user)
except VerificationTransitionError as exc:
    if exc.attempted_status == "verified" and str(disc.submitted_by) == str(current_user.id):
        return _error_response(request_id, "forbidden", "Cannot verify your own submission", 403)
    return _error_response(request_id, "invalid_state", str(exc), 409)
if not transitioned:                       # already verified → idempotent, NO DiscEdit
    return JSONResponse(200, {...,"message": "already verified"})
db.add(DiscEdit(disc_id=disc.id, user_id=current_user.id, edit_type="verify"))
```

**Five inline status mutations to replace with `verification.py` calls:**
| Line | Function | Current mutation | Replace with |
|------|----------|------------------|--------------|
| 241 | `resolve_dispute` (verify) | `disc.status = "verified"` | `resolve_dispute(..., action="verify")` |
| 245 | `resolve_dispute` (reject) | `disc.status = "unverified"` | `resolve_dispute(..., action="reject")` |
| 422 | `submit_disc` match | `existing.status = "verified"` | `verify(db, existing, current_user)` |
| 444 | `submit_disc` mismatch | `existing.status = "disputed"` **(THE BUG)** | `flag_dispute(db, existing, current_user, reason)` — refuses verified |
| 616 | `verify_disc` | `disc.status = "verified"` | `verify(db, disc, current_user)` |
- Keep coarse role gate (`current_user.role not in ("trusted","editor","admin")`, line 232) at the route (D-11).
- After change, `grep -rn 'status.*=.*"disputed"' api/app/` must return exactly ONE hit (inside `flag_dispute`).

**IDENT-01 alias exposure in `_disc_to_response`** (line 123) — build primary-first list, insertion-ordered:
```python
aliases = [FingerprintAliasResponse(fingerprint=disc.fingerprint,
                                    method=_method_of(disc.fingerprint), is_primary=True)]
aliases += [FingerprintAliasResponse(fingerprint=a.fingerprint,
                                     method=_method_of(a.fingerprint), is_primary=False)
            for a in sorted(disc.identity_aliases, key=lambda a: (a.created_at, str(a.id)))]
```
- `_method_of` is a new local `_helper` deriving method from prefix (`fp.split("-", 1)[0]`). Method is DERIVED, not a stored column (no migration).
- Add `selectinload(Disc.identity_aliases)` to the lookup query (`selectinload` already imported, line 12); apply at all three `_disc_to_response` call sites (lookup ~277, `lookup_disc_by_upc` ~180, `list_disputed_discs` ~208) to avoid N+1.

---

### `api/app/schemas.py` (MODIFY — IDENT-01 contract)

**Analog:** `TitleResponse` / `ReleaseResponse` / `DiscLookupResponse` (lines 22-63). Copy the Pydantic v2 style: `BaseModel`, typed fields, `Field(default_factory=list)` for collections, defaults for optional additive fields.

**New model + additive field** (strictly additive — D-04/D-07):
```python
class FingerprintAliasResponse(BaseModel):
    fingerprint: str
    method: str                 # derived from prefix by the serializer
    is_primary: bool = False

class DiscLookupResponse(BaseModel):
    ...                         # all existing fields UNCHANGED (fingerprint stays top-level primary)
    titles: list[TitleResponse] = Field(default_factory=list)
    fingerprint_aliases: list[FingerprintAliasResponse] = Field(default_factory=list)  # additive
```

---

### `api/app/models.py` (MODIFY — deterministic alias ordering, D-06)

**Analog:** `Disc.titles` relationship (line 101) and the `identity_aliases` relationship itself (lines 109-111). Add an explicit `order_by`:
```python
identity_aliases: Mapped[list["DiscIdentityAlias"]] = relationship(
    back_populates="disc", cascade="all, delete-orphan",
    order_by="DiscIdentityAlias.created_at, DiscIdentityAlias.id",   # NEW — (created_at, id) breaks SQLite ties
)
```
- `DiscIdentityAlias` (lines 128-149) already has `created_at` (140) and `id` (131) — no schema/migration change. Alternatively sort in the serializer (shown above); pick one, not both.

---

### `api/tests/test_disc_identity_regression.py` (NEW — IDENT-05 golden)

**Analog:** `seed_test_disc` (`conftest.py:130-190`) and the lookup-by-alias tolerance in `test_disc_identity_aliases.py:106-108`.

- Seed a **`dvd1-`-prefixed** primary (NOT the fixture's `dvd-ABC123-main`, conftest.py:146). Write a dedicated golden seeder mirroring `seed_test_disc`'s structure (release → disc `db.flush()` → `DiscRelease` link → `DiscTitle` → `DiscTrack`), but with a `status`/fingerprint appropriate to a real pre-migration OVID-DVD-1 identity.
- Assert resolved title/chapter/track/release fields against a **hardcoded literal dict** written into the test (NOT re-read from seed inputs — else tautological; D-14).
- Assert on stable `disc_id`/release identity + normalized structure looked up **by the fixed `dvd1-*` string** — do NOT assert `response["fingerprint"] == "dvd1-…"` (survives Phase 5; D-16).
- Add a `# guardrail: IDENT-05` docstring. Leave it UNMARKED (no `real_disc` marker) so CI collects it.

### `api/tests/test_verification.py` (NEW) & `test_disc_identity_race.py` (NEW)

**Analog:** `TestDiscSubmitErrors` class grouping (`test_disc_submit.py:114`) and explicit-`assert`-on-response-fields style (never snapshots).
- Race test: do NOT use `threading`/`asyncio.gather` (Pitfall 1 — SQLite StaticPool serializes). Inject the losing-race state deterministically: pre-insert the conflicting row via `db_session`, or monkeypatch `resolve_disc_identity` to return `None` on first call, then assert convergence to a single disc. Restore any monkeypatch in a `finally` (CLAUDE.md fs/symbol-override rule).

### `api/tests/test_disc_submit.py` + `test_dispute.py` (MODIFY — behavior change)

**Analog:** existing tests in-file. Per Pitfall 3, these encode the silent-flip bug:
- `test_disc_submit.py:115` (`test_submit_duplicate_fingerprint_conflicting_metadata`) and `:198` (`test_duplicate_conflicting_metadata_disputes`) — seed the disc `unverified` to keep exercising the legit `unverified→disputed` path; ADD a test asserting a genuinely `verified` disc STAYS verified on a mismatched submission (recommend 200 + audit `DiscEdit`, per A2).
- `test_dispute.py:81` (`test_submit_stores_conflict_data`) — same update (uses a verified seed).

## Shared Patterns

### Domain exception raised in service, caught at route boundary
**Source:** `api/app/disc_identity.py:20-28` (`DiscIdentityConflict`) → `api/app/routes/disc.py:62-71,409-410` (`_identity_conflict_response`)
**Apply to:** `VerificationTransitionError` in `verification.py` → catch in `verify_disc`/`resolve_dispute`/`submit_disc`, render via `_error_response` with `request_id`.

### Structured JSON error envelope
**Source:** `api/app/routes/disc.py:52-59`
```python
def _error_response(request_id, error, message, status_code) -> JSONResponse:
    return JSONResponse(status_code=status_code,
        content={"request_id": request_id, "error": error, "message": message})
```
**Apply to:** every new error path (verification 403/409). Every response carries `request_id`.

### Flat-function domain module (no service class)
**Source:** `api/app/disc_identity.py` (module docstring, `@dataclass(frozen=True)` result type, functions taking `db: Session` first)
**Apply to:** `verification.py` — matches `disc_identity.py`/`sync.py` house style (D-08).

### Fixture-seed + explicit-assert testing
**Source:** `api/tests/conftest.py:130-190` (`seed_test_disc`), `test_disc_submit.py` explicit `assert resp.json()["status"] == ...`
**Apply to:** all new/updated tests. No snapshot testing; assert specific JSON fields.

## No Analog Found

None. Every file in this phase has a direct in-tree analog. This is an in-house-pattern hardening phase — no new libraries, no new Alembic migration, no OOP-service pattern.

## Metadata

**Analog search scope:** `api/app/`, `api/tests/`, `api/app/routes/`
**Files scanned (read):** `disc_identity.py` (full), `routes/disc.py` (lines 1-130, 225-262, 405-459, 595-635), `models.py` (60-160), `schemas.py` (1-90), `conftest.py` (130-190), `test_disc_submit.py` (100-150)
**Pattern extraction date:** 2026-07-05
</content>
</invoke>
