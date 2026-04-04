"""Tests for GET /v1/disc/{fingerprint}."""


from sqlalchemy.orm import Session

from app.models import Disc


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------
class TestDiscLookup:
    def test_lookup_existing_disc(self, client, seeded_disc):
        """Seeded disc returns 200 with correct nested JSON shape."""
        resp = client.get("/v1/disc/dvd-ABC123-main")
        assert resp.status_code == 200
        data = resp.json()
        assert data["fingerprint"] == "dvd-ABC123-main"
        assert data["format"] == "DVD"
        assert "request_id" in data
        assert data["release"] is not None
        assert data["release"]["title"] == "The Matrix"
        assert isinstance(data["titles"], list)

    def test_lookup_confidence_verified(self, client, seeded_disc):
        """Disc with status='verified' → confidence='high'."""
        resp = client.get("/v1/disc/dvd-ABC123-main")
        assert resp.status_code == 200
        assert resp.json()["confidence"] == "high"

    def test_lookup_confidence_unverified(self, client, db_session: Session):
        """Disc with status='unverified' → confidence='medium'."""
        disc = Disc(fingerprint="test-unverified", format="BD", status="unverified")
        db_session.add(disc)
        db_session.commit()
        resp = client.get("/v1/disc/test-unverified")
        assert resp.status_code == 200
        assert resp.json()["confidence"] == "medium"

    def test_lookup_includes_titles_and_tracks(self, client, seeded_disc):
        """Nested titles with audio_tracks and subtitle_tracks present."""
        resp = client.get("/v1/disc/dvd-ABC123-main")
        data = resp.json()
        assert len(data["titles"]) == 1
        t = data["titles"][0]
        assert t["title_index"] == 1
        assert t["is_main_feature"] is True
        assert len(t["audio_tracks"]) == 1
        assert t["audio_tracks"][0]["language"] == "en"
        assert t["audio_tracks"][0]["codec"] == "ac3"
        assert len(t["subtitle_tracks"]) == 1
        assert t["subtitle_tracks"][0]["language"] == "en"

    def test_lookup_has_request_id(self, client, seeded_disc):
        """Response body and header both carry request_id."""
        resp = client.get("/v1/disc/dvd-ABC123-main")
        data = resp.json()
        assert "request_id" in data
        assert len(data["request_id"]) > 0
        assert "x-request-id" in resp.headers
        assert resp.headers["x-request-id"] == data["request_id"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------
class TestDiscLookupErrors:
    def test_lookup_not_found(self, client):
        """Non-existent fingerprint → 404 with error format."""
        resp = client.get("/v1/disc/does-not-exist")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data
        assert "message" in data

    def test_lookup_disc_with_no_titles(self, client, db_session: Session):
        """Disc with no titles returns empty titles list."""
        disc = Disc(fingerprint="bare-disc", format="DVD", status="unverified")
        db_session.add(disc)
        db_session.commit()
        resp = client.get("/v1/disc/bare-disc")
        assert resp.status_code == 200
        assert resp.json()["titles"] == []

    def test_lookup_disc_with_no_release(self, client, db_session: Session):
        """Disc with no linked release returns release=null."""
        disc = Disc(fingerprint="no-release", format="BD", status="unverified")
        db_session.add(disc)
        db_session.commit()
        resp = client.get("/v1/disc/no-release")
        assert resp.status_code == 200
        assert resp.json()["release"] is None


# ---------------------------------------------------------------------------
# Set integration tests (Phase 2)
# ---------------------------------------------------------------------------
class TestDiscLookupSetIntegration:
    """Lookup returns disc_set with siblings when disc is in a set."""

    def test_lookup_disc_in_set(self, client, db_session: Session, seeded_disc):
        """GET disc in a set returns disc_set with id, edition_name, total_discs, siblings."""
        set_id = seed_test_disc_set(db_session, seeded_disc["release_id"], total_discs=2)

        # Link the seeded disc to the set
        disc = db_session.query(Disc).filter(Disc.id == seeded_disc["disc_id"]).first()
        disc.disc_set_id = set_id
        disc.disc_number = 1

        # Create a sibling disc in the same set
        sibling = Disc(
            fingerprint="dvd-SIBLING-001",
            format="DVD",
            status="unverified",
            disc_set_id=set_id,
            disc_number=2,
        )
        db_session.add(sibling)
        sibling_title = DiscTitle(
            disc_id=sibling.id,
            title_index=1,
            title_type="main_feature",
            duration_secs=5400,
            chapter_count=20,
            is_main_feature=True,
            display_name="Bonus Features",
        )
        db_session.add(sibling_title)
        db_session.flush()
        db_session.add(DiscTrack(
            disc_title_id=sibling_title.id,
            track_type="audio",
            track_index=0,
            language_code="en",
            codec="ac3",
            channels=6,
            is_default=True,
        ))
        db_session.commit()

        resp = client.get("/v1/disc/dvd-ABC123-main")
        assert resp.status_code == 200
        data = resp.json()
        assert data["disc_set"] is not None
        assert data["disc_set"]["id"] == str(set_id)
        assert data["disc_set"]["total_discs"] == 2
        assert data["disc_set"]["edition_name"] == "Extended Edition"
        # Siblings should contain only the OTHER disc
        siblings = data["disc_set"]["siblings"]
        assert len(siblings) == 1
        assert siblings[0]["fingerprint"] == "dvd-SIBLING-001"
        assert siblings[0]["disc_number"] == 2
        assert siblings[0]["format"] == "DVD"
        assert siblings[0]["main_title"] == "Bonus Features"
        assert siblings[0]["duration_secs"] == 5400
        assert siblings[0]["track_count"] == 1

    def test_lookup_disc_not_in_set(self, client, seeded_disc):
        """GET disc not in a set returns disc_set=null (D-14)."""
        resp = client.get("/v1/disc/dvd-ABC123-main")
        assert resp.status_code == 200
        data = resp.json()
        assert data["disc_set"] is None
