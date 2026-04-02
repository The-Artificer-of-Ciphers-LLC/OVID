"""Tests for GET /v1/search endpoint."""

import uuid

from app.models import Disc, DiscRelease, Release


def _seed_release(db, title="The Matrix", year=1999, content_type="movie", tmdb_id=None):
    """Helper: create a release and return it."""
    rel = Release(
        title=title,
        year=year,
        content_type=content_type,
        tmdb_id=tmdb_id,
        original_language="en",
    )
    db.add(rel)
    db.flush()
    return rel


def _link_disc_to_release(db, release, fingerprint=None):
    """Helper: create a disc and link it to a release."""
    fp = fingerprint or f"dvd-{uuid.uuid4().hex[:8]}"
    disc = Disc(fingerprint=fp, format="DVD", status="unverified")
    db.add(disc)
    db.flush()
    db.execute(
        DiscRelease.__table__.insert().values(disc_id=disc.id, release_id=release.id)
    )
    db.flush()
    return disc


class TestSearch:
    """GET /v1/search"""

    def test_search_by_title(self, client, db_session):
        """Search finds a release by title substring."""
        _seed_release(db_session)
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Matrix"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 1
        assert data["results"][0]["title"] == "The Matrix"
        assert "request_id" in data

    def test_search_case_insensitive(self, client, db_session):
        """Search is case-insensitive."""
        _seed_release(db_session)
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "the matrix"})
        assert resp.status_code == 200
        assert resp.json()["total_results"] == 1

    def test_search_no_results(self, client, db_session):
        """Search for non-existent title returns empty results, not error."""
        resp = client.get("/v1/search", params={"q": "Nonexistent Film XYZ"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 0
        assert data["results"] == []
        assert data["total_pages"] == 0

    def test_search_filter_by_year(self, client, db_session):
        """Year filter narrows results."""
        _seed_release(db_session, title="Film A", year=1999)
        _seed_release(db_session, title="Film B", year=2003)
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Film", "year": 2003})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 1
        assert data["results"][0]["title"] == "Film B"

    def test_search_filter_by_type(self, client, db_session):
        """Type filter narrows results."""
        _seed_release(db_session, title="Film A", content_type="movie")
        _seed_release(db_session, title="Film B", content_type="tv")
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Film", "type": "tv"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 1
        assert data["results"][0]["title"] == "Film B"

    def test_search_pagination(self, client, db_session):
        """With >20 results, pagination fields reflect multiple pages."""
        for i in range(25):
            _seed_release(db_session, title=f"Film {i:03d}", year=2000 + (i % 5))
        db_session.commit()

        # Page 1
        resp = client.get("/v1/search", params={"q": "Film", "page": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_results"] == 25
        assert data["total_pages"] == 2
        assert data["page"] == 1
        assert len(data["results"]) == 20

        # Page 2
        resp = client.get("/v1/search", params={"q": "Film", "page": 2})
        data = resp.json()
        assert data["page"] == 2
        assert len(data["results"]) == 5

    def test_search_page_beyond_results(self, client, db_session):
        """Page beyond available results returns empty list."""
        _seed_release(db_session)
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Matrix", "page": 999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []
        assert data["total_results"] == 1  # total still reported

    def test_search_missing_query(self, client):
        """Missing q parameter returns 400."""
        resp = client.get("/v1/search")
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "bad_request"
        assert "request_id" in data

    def test_search_empty_query(self, client):
        """Empty q parameter returns 400."""
        resp = client.get("/v1/search", params={"q": ""})
        assert resp.status_code == 400

    def test_search_has_request_id(self, client, db_session):
        """Response includes request_id."""
        _seed_release(db_session)
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Matrix"})
        assert resp.status_code == 200
        assert "request_id" in resp.json()

    def test_search_disc_count(self, client, db_session):
        """disc_count reflects actual linked discs."""
        rel = _seed_release(db_session)
        _link_disc_to_release(db_session, rel, "dvd-001")
        _link_disc_to_release(db_session, rel, "dvd-002")
        db_session.commit()

        resp = client.get("/v1/search", params={"q": "Matrix"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"][0]["disc_count"] == 2
