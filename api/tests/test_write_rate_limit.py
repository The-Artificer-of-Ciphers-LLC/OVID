"""Method-scoped per-account write ceiling on the disc write routes (INFRA-04).

A second, tighter ``@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])`` stacks
above the existing ``@limiter.limit(_dynamic_limit)`` on the three write routes
(``POST /v1/disc``, ``POST /v1/disc/register``, ``POST /v1/disc/{fp}/resolve``).

Two concerns:

  1. **D-07 write ceiling** — 20 valid authenticated POSTs within a minute from
     one account succeed; the 21st returns 429. Reads in the same window stay on
     the 500/min auth tier (untouched by the write cap). All three write routes
     enforce the same ``AUTH_WRITE_LIMIT``. The flood uses a UNIQUE fingerprint
     per iteration so each POST is a novel *create*, exercising the D-09 gap the
     Phase-2 confirmation cooldown never covered.

  2. **D-10 seam** — the coarse slowapi volumetric ceiling and the narrow
     Postgres ``anti_sybil.evaluate_confirmation`` cooldown are independent,
     layered, and never decrement each other: a novel-fingerprint flood trips
     the write cap with *zero* ``verify`` edits (anti_sybil uninvolved), while a
     true confirmation records a ``verify`` edit AND consumes a write-limit slot.

CRITICAL (RESEARCH Pitfall 2): every payload must be schema-valid and
authenticated — FastAPI body validation returns 422 BEFORE the limiter runs, so
a malformed body would never exercise the 429 path.
"""

import copy

from app.models import DiscEdit

from tests.conftest import matrix_matching_submit_payload, seed_test_disc


# The tighter write ceiling is 20/minute (from AUTH_WRITE_LIMIT="20/minute;...").
WRITE_CAP = 20


# ---------------------------------------------------------------------------
# Payload helpers — all valid + authed (Pitfall 2)
# ---------------------------------------------------------------------------
def _novel_submit_payload(tag) -> dict:
    """A valid POST /v1/disc payload with a UNIQUE fingerprint (a novel create).

    Derived from ``matrix_matching_submit_payload`` but with the identity fields
    overridden so each POST resolves to no existing disc — a brand-new create,
    never a confirmation. This is the D-09 novel-fingerprint flood the Phase-2
    cooldown never caps.
    """
    payload = copy.deepcopy(matrix_matching_submit_payload())
    payload["fingerprint"] = f"dvd-NOVEL{tag}-main"
    return payload


def _register_payload(tag) -> dict:
    """A valid POST /v1/disc/register payload with a unique fingerprint."""
    return {"fingerprint": f"dvd-REG{tag}-main", "format": "DVD"}


# ---------------------------------------------------------------------------
# D-07: the stacked write ceiling on POST /v1/disc
# ---------------------------------------------------------------------------
def test_write_limit_caps_disc_submissions_at_21st(client, auth_header) -> None:
    """20 valid authed POST /v1/disc succeed; the 21st returns a 429 envelope."""
    for i in range(WRITE_CAP):
        resp = client.post("/v1/disc", json=_novel_submit_payload(i), headers=auth_header)
        assert resp.status_code in (200, 201), (
            f"write #{i + 1} unexpectedly got {resp.status_code}: {resp.text}"
        )

    resp = client.post("/v1/disc", json=_novel_submit_payload(WRITE_CAP), headers=auth_header)
    assert resp.status_code == 429, (
        f"Expected 429 on write #{WRITE_CAP + 1}, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["error"] == "rate_limited", f"Unexpected 429 envelope: {body}"
    assert "retry_after" in body, f"Missing retry_after in 429 envelope: {body}"


def test_reads_not_throttled_by_write_cap(client, auth_header) -> None:
    """A GET in the same window is NOT throttled by the 20/min write ceiling."""
    # Exhaust the write cap (21st POST → 429).
    for i in range(WRITE_CAP):
        resp = client.post("/v1/disc", json=_novel_submit_payload(i), headers=auth_header)
        assert resp.status_code in (200, 201)
    blocked = client.post("/v1/disc", json=_novel_submit_payload(WRITE_CAP), headers=auth_header)
    assert blocked.status_code == 429

    # A read in the same window stays on the 500/min auth tier — not throttled.
    read = client.get("/v1/disc/dvd-NOVEL0-main", headers=auth_header)
    assert read.status_code != 429, (
        f"GET was throttled by the write cap ({read.status_code}) — reads must be unaffected"
    )
    assert read.status_code == 200, f"Expected 200 read, got {read.status_code}: {read.text}"


def test_register_route_enforces_write_cap(client, auth_header) -> None:
    """POST /v1/disc/register carries the same AUTH_WRITE_LIMIT ceiling."""
    for i in range(WRITE_CAP):
        resp = client.post("/v1/disc/register", json=_register_payload(i), headers=auth_header)
        assert resp.status_code in (200, 201, 409), (
            f"register #{i + 1} unexpectedly got {resp.status_code}: {resp.text}"
        )

    resp = client.post("/v1/disc/register", json=_register_payload(WRITE_CAP), headers=auth_header)
    assert resp.status_code == 429, (
        f"Expected 429 on register #{WRITE_CAP + 1}, got {resp.status_code}: {resp.text}"
    )


def test_resolve_route_enforces_write_cap(client, auth_header) -> None:
    """POST /v1/disc/{fingerprint}/resolve carries the same write ceiling.

    A contributor lacks the trusted/editor/admin role, so each request is a
    valid, authed 403 (never 422) — which still consumes a write-limit slot.
    The 21st POST trips the 429 write ceiling before the handler runs.
    """
    body = {"action": "verify"}
    for i in range(WRITE_CAP):
        resp = client.post(f"/v1/disc/dvd-NOPE{i}-main/resolve", json=body, headers=auth_header)
        assert resp.status_code != 429, (
            f"resolve #{i + 1} tripped 429 early ({resp.status_code}); expected under cap"
        )
        assert resp.status_code != 422, (
            f"resolve #{i + 1} got 422 — body must be valid so the limiter runs: {resp.text}"
        )

    resp = client.post(f"/v1/disc/dvd-NOPE{WRITE_CAP}-main/resolve", json=body, headers=auth_header)
    assert resp.status_code == 429, (
        f"Expected 429 on resolve #{WRITE_CAP + 1}, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# D-10 seam: the coarse slowapi write ceiling and the narrow Postgres
# anti_sybil.evaluate_confirmation cooldown are independent — layered, never
# double-counted. Proven from both sides.
# ---------------------------------------------------------------------------
def test_novel_flood_caps_with_zero_verify_edits(client, db_session, auth_header) -> None:
    """A novel-fingerprint flood trips the write ceiling with anti_sybil uninvolved.

    Every POST is a brand-new create (no existing disc → ``_handle_existing_disc``
    never runs → ``evaluate_confirmation`` never fires), so the volumetric ceiling
    is doing the work ALONE: zero ``verify`` edits exist even though the 21st POST
    is rejected. This is the D-09 gap the Phase-2 confirmation cooldown never
    covered — the write limit closes it independently (D-10).
    """
    for i in range(WRITE_CAP):
        resp = client.post("/v1/disc", json=_novel_submit_payload(i), headers=auth_header)
        assert resp.status_code in (200, 201), f"write #{i + 1}: {resp.status_code} {resp.text}"

    blocked = client.post("/v1/disc", json=_novel_submit_payload(WRITE_CAP), headers=auth_header)
    assert blocked.status_code == 429

    db_session.expire_all()
    verify_edits = (
        db_session.query(DiscEdit).filter(DiscEdit.edit_type == "verify").count()
    )
    assert verify_edits == 0, (
        f"anti_sybil should NOT have fired on a novel flood, but {verify_edits} "
        "verify edit(s) were recorded — the write ceiling must cap novel creates alone"
    )


def test_confirmation_records_verify_edit_and_consumes_write_slot(
    client, db_session, test_user, second_user, second_auth_header
) -> None:
    """A true confirmation fires anti_sybil AND is counted by the write limit.

    User A owns an unverified disc; a DISTINCT user B resubmits a structure that
    matches it. The two-contributor gate (``evaluate_confirmation``) fires and the
    disc auto-verifies, recording a Postgres ``verify`` edit (the semantic gate) —
    AND the very same POST consumes a slot in the coarse slowapi write bucket. The
    two mechanisms measure different things (raw request rate vs. count of
    verify-edits) and never decrement each other (D-10): because the confirmation
    was write #1, only 19 further novel writes fit before the 20/min ceiling trips.
    """
    seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")

    # Confirmation POST (write #1) → auto-verify + a Postgres verify edit.
    resp = client.post(
        "/v1/disc", json=matrix_matching_submit_payload(), headers=second_auth_header
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "verified"

    db_session.expire_all()
    verify_edits = (
        db_session.query(DiscEdit).filter(DiscEdit.edit_type == "verify").count()
    )
    assert verify_edits == 1, (
        f"anti_sybil semantic gate should have recorded exactly 1 verify edit, got {verify_edits}"
    )

    # The confirmation consumed write-slot #1: only 19 more novel writes fit.
    for i in range(WRITE_CAP - 1):
        r = client.post("/v1/disc", json=_novel_submit_payload(i), headers=second_auth_header)
        assert r.status_code in (200, 201), f"novel write #{i + 1}: {r.status_code} {r.text}"

    blocked = client.post(
        "/v1/disc", json=_novel_submit_payload(WRITE_CAP), headers=second_auth_header
    )
    assert blocked.status_code == 429, (
        f"Expected 429 after confirmation (#1) + {WRITE_CAP - 1} novel writes, "
        f"got {blocked.status_code}: {blocked.text} — the confirmation must have "
        "consumed a write-limit slot"
    )
