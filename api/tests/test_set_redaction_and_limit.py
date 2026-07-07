"""RED/GREEN pytest for the D-01 re-review findings R-1 and R-2 (Phase 7 Plan 03).

R-1 (anti-echo redaction leak): ``_build_disc_set_nested`` (disc.py) and
``_build_sibling_summary`` (set.py) must withhold an unverified sibling's derived
structural fields (``main_title``, ``duration_secs``, ``track_count``), mirroring the
D-09 anti-echo redaction ``_disc_to_response`` already applies on a direct lookup. A
verified sibling's structural summary must still be shown — the gate is per-sibling
``status``, never a blanket redaction.

R-2 (write-ceiling inconsistency): ``POST /v1/set`` must carry the stacked
``AUTH_WRITE_LIMIT`` per-account write ceiling like the other three write routes
(INFRA-04 parity), not just the volumetric ``_dynamic_limit``.
"""

import uuid

from app.models import Disc, DiscRelease, DiscSet, DiscTitle, DiscTrack, Release

# AUTH_WRITE_LIMIT == "20/minute;300/hour" (app/rate_limit.py) — mirrors the cap
# used in tests/test_write_rate_limit.py for the other three write routes.
WRITE_CAP = 20


# ---------------------------------------------------------------------------
# Seed helpers — a 2-disc set with one verified + one unverified sibling
# ---------------------------------------------------------------------------
def _seed_release(db) -> Release:
    release = Release(
        title="The Matrix",
        year=1999,
        content_type="movie",
        tmdb_id=603,
        imdb_id="tt0133093",
        original_language="en",
    )
    db.add(release)
    db.flush()
    return release


def _seed_set_sibling(
    db, disc_set_id: uuid.UUID, release_id: uuid.UUID, *, fingerprint: str, disc_number: int, status: str
) -> Disc:
    """Create a Disc in a set with one main-feature title + 2 tracks (audio/subtitle)."""
    disc = Disc(
        fingerprint=fingerprint,
        format="DVD",
        disc_number=disc_number,
        total_discs=2,
        status=status,
        disc_set_id=disc_set_id,
    )
    db.add(disc)
    db.flush()

    db.execute(
        DiscRelease.__table__.insert().values(disc_id=disc.id, release_id=release_id)
    )

    title = DiscTitle(
        disc_id=disc.id,
        title_index=1,
        title_type="main_feature",
        duration_secs=8160,
        chapter_count=39,
        is_main_feature=True,
        display_name="The Matrix",
    )
    db.add(title)
    db.flush()

    db.add_all(
        [
            DiscTrack(
                disc_title_id=title.id,
                track_type="audio",
                track_index=0,
                language_code="en",
                codec="ac3",
                channels=6,
                is_default=True,
            ),
            DiscTrack(
                disc_title_id=title.id,
                track_type="subtitle",
                track_index=0,
                language_code="en",
                codec="vobsub",
                channels=None,
                is_default=False,
            ),
        ]
    )
    db.commit()
    db.refresh(disc)
    return disc


def _seed_mixed_status_set(db) -> tuple[uuid.UUID, Disc, Disc]:
    """Build a 2-disc set: disc1 verified, disc2 unverified.

    Returns (disc_set_id, disc1_verified, disc2_unverified).
    """
    release = _seed_release(db)
    disc_set = DiscSet(
        release_id=release.id, edition_name="Extended Edition", total_discs=2, seq_num=1
    )
    db.add(disc_set)
    db.flush()

    disc1 = _seed_set_sibling(
        db, disc_set.id, release.id,
        fingerprint="dvd-SET1-verified", disc_number=1, status="verified",
    )
    disc2 = _seed_set_sibling(
        db, disc_set.id, release.id,
        fingerprint="dvd-SET2-unverified", disc_number=2, status="unverified",
    )

    return disc_set.id, disc1, disc2


# ---------------------------------------------------------------------------
# R-1: nested disc-detail view (GET /v1/disc/{fp})
# ---------------------------------------------------------------------------
def test_nested_disc_set_redacts_unverified_sibling_structural_fields(client, db_session):
    """GET /v1/disc/{fp} nested siblings withhold structural fields for an unverified sibling."""
    _, disc1, disc2 = _seed_mixed_status_set(db_session)

    resp = client.get(f"/v1/disc/{disc1.fingerprint}")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    disc_set = data["disc_set"]
    assert disc_set is not None
    siblings = {s["fingerprint"]: s for s in disc_set["siblings"]}
    assert disc2.fingerprint in siblings

    unverified_sibling = siblings[disc2.fingerprint]
    assert unverified_sibling["main_title"] is None, (
        "unverified sibling's main_title leaked through the nested set view"
    )
    assert unverified_sibling["duration_secs"] is None, (
        "unverified sibling's duration_secs leaked through the nested set view"
    )
    assert unverified_sibling["track_count"] is None, (
        "unverified sibling's track_count leaked through the nested set view"
    )
    # Identity fields stay intact — this is a status-gated redaction, not a
    # blanket one.
    assert unverified_sibling["disc_number"] == 2
    assert unverified_sibling["format"] == "DVD"


def test_nested_disc_set_shows_verified_sibling_structural_fields(client, db_session):
    """GET /v1/disc/{fp} nested siblings still show structural fields for a verified sibling."""
    _, disc1, disc2 = _seed_mixed_status_set(db_session)

    resp = client.get(f"/v1/disc/{disc2.fingerprint}")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    disc_set = data["disc_set"]
    assert disc_set is not None
    siblings = {s["fingerprint"]: s for s in disc_set["siblings"]}
    verified_sibling = siblings[disc1.fingerprint]

    assert verified_sibling["main_title"] == "The Matrix"
    assert verified_sibling["duration_secs"] == 8160
    assert verified_sibling["track_count"] == 2


# ---------------------------------------------------------------------------
# R-1: set-search view (GET /v1/set)
# ---------------------------------------------------------------------------
def test_set_search_view_redacts_unverified_sibling_structural_fields(client, db_session):
    """GET /v1/set applies the same status gate to each result's sibling summaries."""
    _seed_mixed_status_set(db_session)

    resp = client.get("/v1/set?q=matrix")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_results"] >= 1

    result = next(r for r in data["results"] if r["edition_name"] == "Extended Edition")
    discs_by_fp = {d["fingerprint"]: d for d in result["discs"]}

    unverified = discs_by_fp["dvd-SET2-unverified"]
    assert unverified["main_title"] is None
    assert unverified["duration_secs"] is None
    assert unverified["track_count"] is None

    verified = discs_by_fp["dvd-SET1-verified"]
    assert verified["main_title"] == "The Matrix"
    assert verified["duration_secs"] == 8160
    assert verified["track_count"] == 2


# ---------------------------------------------------------------------------
# R-2: POST /v1/set write ceiling
# ---------------------------------------------------------------------------
def test_create_set_enforces_auth_write_limit(client, db_session, auth_header, seeded_disc):
    """POST /v1/set carries the stacked AUTH_WRITE_LIMIT per-account write ceiling."""
    release_id = str(seeded_disc["release_id"])

    for i in range(WRITE_CAP):
        resp = client.post(
            "/v1/set",
            json={"release_id": release_id, "edition_name": f"Edition {i}", "total_discs": 2},
            headers=auth_header,
        )
        assert resp.status_code == 201, f"create #{i + 1}: {resp.status_code} {resp.text}"

    resp = client.post(
        "/v1/set",
        json={"release_id": release_id, "edition_name": "Overflow", "total_discs": 2},
        headers=auth_header,
    )
    assert resp.status_code == 429, (
        f"Expected 429 on set-create #{WRITE_CAP + 1}, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["error"] == "rate_limited", f"Unexpected 429 envelope: {body}"
    assert "retry_after" in body, f"Missing retry_after in 429 envelope: {body}"
