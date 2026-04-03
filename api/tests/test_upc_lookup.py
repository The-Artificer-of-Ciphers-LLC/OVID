"""Tests for GET /v1/disc/upc/{upc} — UPC barcode lookup."""

import uuid

from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, Release
from tests.conftest import seed_test_disc


def test_upc_found(client, seeded_disc) -> None:
    """A seeded disc with upc='012345678901' is returned in results."""
    resp = client.get("/v1/disc/upc/012345678901")
    assert resp.status_code == 200

    body = resp.json()
    assert "request_id" in body
    assert isinstance(body["results"], list)
    assert len(body["results"]) >= 1

    fps = [r["fingerprint"] for r in body["results"]]
    assert "dvd-ABC123-main" in fps

    # Verify nested data is eager-loaded
    first = body["results"][0]
    assert first["format"] == "DVD"
    assert first["release"] is not None
    assert first["release"]["title"] == "The Matrix"
    assert len(first["titles"]) >= 1


def test_upc_not_found(client) -> None:
    """An unrecognized UPC returns 200 with an empty results list, not 404."""
    resp = client.get("/v1/disc/upc/000000000000")
    assert resp.status_code == 200

    body = resp.json()
    assert body["results"] == []


def test_upc_multi_disc(client, db_session, seeded_disc) -> None:
    """Two discs with the same UPC both appear in results."""
    # Insert a second disc with the same UPC
    release = Release(
        title="The Matrix Reloaded",
        year=2003,
        content_type="movie",
    )
    db_session.add(release)
    db_session.flush()

    disc2 = Disc(
        fingerprint="dvd-SECOND-disc",
        format="DVD",
        region_code="1",
        upc="012345678901",
        status="unverified",
    )
    db_session.add(disc2)
    db_session.flush()

    db_session.execute(
        DiscRelease.__table__.insert().values(
            disc_id=disc2.id, release_id=release.id
        )
    )
    db_session.commit()

    resp = client.get("/v1/disc/upc/012345678901")
    assert resp.status_code == 200

    body = resp.json()
    assert len(body["results"]) == 2

    fps = {r["fingerprint"] for r in body["results"]}
    assert fps == {"dvd-ABC123-main", "dvd-SECOND-disc"}


def test_upc_rate_limited(client) -> None:
    """The 101st anonymous request to the UPC endpoint returns 429."""
    for i in range(100):
        resp = client.get("/v1/disc/upc/012345678901")
        assert resp.status_code == 200, (
            f"Request {i + 1} failed early with {resp.status_code}"
        )

    resp = client.get("/v1/disc/upc/012345678901")
    assert resp.status_code == 429, (
        f"Expected 429 on request 101, got {resp.status_code}"
    )
