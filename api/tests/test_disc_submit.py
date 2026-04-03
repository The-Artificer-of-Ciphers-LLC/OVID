"""Tests for POST /v1/disc."""

from sqlalchemy.orm import Session

from app.models import Disc


VALID_PAYLOAD = {
    "fingerprint": "bd-NEW001-main",
    "format": "BD",
    "region_code": "A",
    "upc": "999888777666",
    "disc_label": "NEWFILM_D1",
    "edition_name": "Collector's Edition",
    "disc_number": 1,
    "total_discs": 2,
    "release": {
        "title": "New Film",
        "year": 2024,
        "content_type": "movie",
        "tmdb_id": 12345,
        "imdb_id": "tt9999999",
        "original_language": "en",
    },
    "titles": [
        {
            "title_index": 0,
            "title_type": "main_feature",
            "duration_secs": 7200,
            "chapter_count": 24,
            "is_main_feature": True,
            "display_name": "New Film",
            "audio_tracks": [
                {
                    "track_index": 0,
                    "language_code": "en",
                    "codec": "dts-hd",
                    "channels": 8,
                    "is_default": True,
                }
            ],
            "subtitle_tracks": [
                {
                    "track_index": 0,
                    "language_code": "en",
                    "codec": "pgs",
                    "is_default": True,
                },
                {
                    "track_index": 1,
                    "language_code": "es",
                    "codec": "pgs",
                    "is_default": False,
                },
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------
class TestDiscSubmit:
    def test_submit_new_disc(self, client, auth_header):
        """POST valid payload with auth → 201, disc retrievable via GET."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        assert resp.status_code == 201
        data = resp.json()
        assert data["fingerprint"] == "bd-NEW001-main"
        assert data["status"] == "unverified"
        assert "request_id" in data

        # Verify round-trip via GET (no auth required for reads)
        get_resp = client.get("/v1/disc/bd-NEW001-main")
        assert get_resp.status_code == 200
        assert get_resp.json()["fingerprint"] == "bd-NEW001-main"

    def test_submit_with_titles_and_tracks(self, client, auth_header):
        """POST with titles+tracks → GET returns nested structure."""
        client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        resp = client.get("/v1/disc/bd-NEW001-main")
        data = resp.json()
        assert len(data["titles"]) == 1
        t = data["titles"][0]
        assert t["title_index"] == 0
        assert len(t["audio_tracks"]) == 1
        assert t["audio_tracks"][0]["codec"] == "dts-hd"
        assert len(t["subtitle_tracks"]) == 2

    def test_submit_has_request_id(self, client, auth_header):
        """Submit response includes request_id in body and header."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        data = resp.json()
        assert "request_id" in data
        assert len(data["request_id"]) > 0
        assert "x-request-id" in resp.headers

    def test_submit_tracks_submitted_by(self, client, auth_header, test_user, db_session):
        """POST sets disc.submitted_by to the authenticated user's ID."""
        payload = {**VALID_PAYLOAD, "fingerprint": "bd-SUBMIT-TRACK-001"}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201

        disc = db_session.query(Disc).filter(Disc.fingerprint == "bd-SUBMIT-TRACK-001").first()
        assert disc is not None
        # SQLite stores UUIDs as strings; compare string representations
        assert str(disc.submitted_by) == str(test_user.id)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------
class TestDiscSubmitErrors:
    def test_submit_duplicate_fingerprint_conflicting_metadata(
        self, client, seeded_disc, auth_header
    ):
        """POST same fingerprint with conflicting metadata → 200 disputed.

        The seeded disc has no submitted_by, so the current user is treated
        as a different contributor.  Metadata (tmdb_id) differs → disputed.
        """
        payload = {**VALID_PAYLOAD, "fingerprint": "dvd-ABC123-main"}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disputed"
        assert "request_id" in data

    def test_submit_duplicate_same_user_returns_409(
        self, client, seeded_disc_with_owner, auth_header
    ):
        """POST same fingerprint by the same user → 409 conflict."""
        payload = {**VALID_PAYLOAD, "fingerprint": "dvd-ABC123-main"}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "conflict"
        assert "already submitted by this user" in data["message"]

    def test_submit_missing_required_fields(self, client, auth_header):
        """POST incomplete payload → 422 from Pydantic validation."""
        resp = client.post("/v1/disc", json={"fingerprint": "x"}, headers=auth_header)
        assert resp.status_code == 422

    def test_submit_empty_fingerprint(self, client, auth_header):
        """Fingerprint with min_length=1 rejects empty string."""
        payload = {**VALID_PAYLOAD, "fingerprint": ""}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 422

    def test_submit_without_titles(self, client, auth_header):
        """Submit with no titles succeeds — titles are optional."""
        payload = {**VALID_PAYLOAD, "fingerprint": "no-titles-disc", "titles": []}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201
        get_resp = client.get("/v1/disc/no-titles-disc")
        assert get_resp.json()["titles"] == []

    def test_submit_without_auth_returns_401(self, client):
        """POST without Authorization header → 401."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD)
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"


# ---------------------------------------------------------------------------
# Two-contributor auto-verify / dispute
# ---------------------------------------------------------------------------
class TestDiscSubmitAutoVerify:
    """Duplicate submission by a second contributor auto-verifies or disputes."""

    def test_duplicate_matching_metadata_auto_verifies(
        self,
        client,
        seeded_disc_with_owner,
        second_auth_header,
    ):
        """Second user submitting same fingerprint with matching tmdb_id → 200 verified."""
        # The seeded disc has tmdb_id=603, title="The Matrix", year=1999
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "dvd-ABC123-main",
            "release": {
                "title": "The Matrix",
                "year": 1999,
                "content_type": "movie",
                "tmdb_id": 603,
                "original_language": "en",
            },
        }
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert "auto-verified" in data["message"]

    def test_duplicate_conflicting_metadata_disputes(
        self,
        client,
        seeded_disc_with_owner,
        second_auth_header,
    ):
        """Second user submitting same fingerprint with different metadata → 200 disputed."""
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "dvd-ABC123-main",
            "release": {
                "title": "Totally Different Film",
                "year": 2020,
                "content_type": "movie",
                "tmdb_id": 99999,
                "original_language": "en",
            },
        }
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disputed"
        assert "disputed" in data["message"]
