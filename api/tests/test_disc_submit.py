"""Tests for POST /v1/disc."""

from sqlalchemy.orm import Session


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
    def test_submit_new_disc(self, client):
        """POST valid payload → 201, disc retrievable via GET."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()
        assert data["fingerprint"] == "bd-NEW001-main"
        assert data["status"] == "unverified"
        assert "request_id" in data

        # Verify round-trip via GET
        get_resp = client.get("/v1/disc/bd-NEW001-main")
        assert get_resp.status_code == 200
        assert get_resp.json()["fingerprint"] == "bd-NEW001-main"

    def test_submit_with_titles_and_tracks(self, client):
        """POST with titles+tracks → GET returns nested structure."""
        client.post("/v1/disc", json=VALID_PAYLOAD)
        resp = client.get("/v1/disc/bd-NEW001-main")
        data = resp.json()
        assert len(data["titles"]) == 1
        t = data["titles"][0]
        assert t["title_index"] == 0
        assert len(t["audio_tracks"]) == 1
        assert t["audio_tracks"][0]["codec"] == "dts-hd"
        assert len(t["subtitle_tracks"]) == 2

    def test_submit_has_request_id(self, client):
        """Submit response includes request_id in body and header."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD)
        data = resp.json()
        assert "request_id" in data
        assert len(data["request_id"]) > 0
        assert "x-request-id" in resp.headers


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------
class TestDiscSubmitErrors:
    def test_submit_duplicate_fingerprint(self, client, seeded_disc):
        """POST same fingerprint twice → 409 Conflict."""
        payload = {**VALID_PAYLOAD, "fingerprint": "dvd-ABC123-main"}
        resp = client.post("/v1/disc", json=payload)
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "conflict"
        assert "request_id" in data

    def test_submit_missing_required_fields(self, client):
        """POST incomplete payload → 422 from Pydantic validation."""
        resp = client.post("/v1/disc", json={"fingerprint": "x"})
        assert resp.status_code == 422

    def test_submit_empty_fingerprint(self, client):
        """Fingerprint with min_length=1 rejects empty string."""
        payload = {**VALID_PAYLOAD, "fingerprint": ""}
        resp = client.post("/v1/disc", json=payload)
        assert resp.status_code == 422

    def test_submit_without_titles(self, client):
        """Submit with no titles succeeds — titles are optional."""
        payload = {**VALID_PAYLOAD, "fingerprint": "no-titles-disc", "titles": []}
        resp = client.post("/v1/disc", json=payload)
        assert resp.status_code == 201
        get_resp = client.get("/v1/disc/no-titles-disc")
        assert get_resp.json()["titles"] == []
