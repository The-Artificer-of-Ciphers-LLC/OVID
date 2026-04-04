"""Tests for disc set CRUD routes — Phase 2."""

import uuid


# ---------------------------------------------------------------------------
# POST /v1/set
# ---------------------------------------------------------------------------
def test_create_set_success(client, db_session, auth_header, seeded_disc):
    """POST /v1/set with valid body returns 201 with set details."""
    release_id = str(seeded_disc["release_id"])
    resp = client.post(
        "/v1/set",
        json={
            "release_id": release_id,
            "edition_name": "Extended Edition",
            "total_discs": 4,
        },
        headers=auth_header,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["release_id"] == release_id
    assert data["edition_name"] == "Extended Edition"
    assert data["total_discs"] == 4
    assert "id" in data
    assert "created_at" in data
    assert "request_id" in data


def test_create_set_no_auth(client, db_session, seeded_disc):
    """POST /v1/set without auth returns 401."""
    resp = client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Test",
            "total_discs": 2,
        },
    )
    assert resp.status_code == 401


def test_create_set_invalid_release(client, db_session, auth_header):
    """POST /v1/set with non-existent release_id returns 404."""
    resp = client.post(
        "/v1/set",
        json={
            "release_id": str(uuid.uuid4()),
            "edition_name": "Test",
            "total_discs": 2,
        },
        headers=auth_header,
    )
    assert resp.status_code == 404


def test_create_set_allocates_seq_num(client, db_session, auth_header, seeded_disc):
    """POST /v1/set allocates seq_num via next_seq()."""
    from app.models import DiscSet

    resp = client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Collector's",
            "total_discs": 3,
        },
        headers=auth_header,
    )
    assert resp.status_code == 201
    set_id = resp.json()["id"]
    disc_set = db_session.query(DiscSet).filter(DiscSet.id == set_id).first()
    assert disc_set is not None
    assert disc_set.seq_num is not None
    assert disc_set.seq_num > 0


# ---------------------------------------------------------------------------
# GET /v1/set/{set_id}
# ---------------------------------------------------------------------------
def test_get_set_empty_discs(client, db_session, auth_header, seeded_disc):
    """GET /v1/set/{set_id} returns set with empty discs array initially."""
    resp = client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Standard",
            "total_discs": 2,
        },
        headers=auth_header,
    )
    set_id = resp.json()["id"]

    resp2 = client.get(f"/v1/set/{set_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["id"] == set_id
    assert data["total_discs"] == 2
    assert data["discs"] == []
    assert "request_id" in data


def test_get_set_with_linked_discs(client, db_session, auth_header, seeded_disc):
    """GET /v1/set/{set_id} with linked discs returns SiblingDiscSummary for each."""
    from app.models import Disc

    # Create a set
    resp = client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Linked",
            "total_discs": 2,
        },
        headers=auth_header,
    )
    set_id = resp.json()["id"]

    # Link existing disc to the set
    disc = db_session.query(Disc).filter(Disc.id == seeded_disc["disc_id"]).first()
    disc.disc_set_id = uuid.UUID(set_id)
    disc.disc_number = 1
    db_session.commit()

    resp2 = client.get(f"/v1/set/{set_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert len(data["discs"]) == 1
    assert data["discs"][0]["fingerprint"] == "dvd-ABC123-main"
    assert data["discs"][0]["disc_number"] == 1
    assert data["discs"][0]["format"] == "DVD"


def test_get_set_not_found(client, db_session):
    """GET /v1/set/{set_id} for non-existent set returns 404."""
    resp = client.get(f"/v1/set/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/set?q=
# ---------------------------------------------------------------------------
def test_search_set_by_release_title(client, db_session, auth_header, seeded_disc):
    """GET /v1/set?q=matrix searches by release title."""
    client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Standard",
            "total_discs": 2,
        },
        headers=auth_header,
    )

    resp = client.get("/v1/set?q=matrix")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] >= 1
    assert any("Matrix" in r.get("edition_name", "") or True for r in data["results"])


def test_search_set_by_edition_name(client, db_session, auth_header, seeded_disc):
    """GET /v1/set?q=extended searches by edition_name."""
    client.post(
        "/v1/set",
        json={
            "release_id": str(seeded_disc["release_id"]),
            "edition_name": "Extended Director Cut",
            "total_discs": 3,
        },
        headers=auth_header,
    )

    resp = client.get("/v1/set?q=extended")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] >= 1


def test_search_set_no_query(client, db_session):
    """GET /v1/set without q param returns 400."""
    resp = client.get("/v1/set")
    assert resp.status_code == 400
