"""Tests for GET /v1/disc/{fingerprint}/edits endpoint (R015)."""

VALID_PAYLOAD = {
    "fingerprint": "bd-EDITS-001",
    "format": "BD",
    "region_code": "A",
    "release": {
        "title": "Test Film",
        "year": 2024,
        "content_type": "movie",
        "tmdb_id": 77777,
        "original_language": "en",
    },
    # CR-02: a non-empty, realistic structure — an empty title list can
    # never structurally match (structural_match rejects zero-title
    # comparisons as vacuous), so the auto-verify tests below need a real
    # structural payload to exercise a legitimate confirmation.
    "titles": [
        {
            "title_index": 0,
            "title_type": "main_feature",
            "duration_secs": 6000,
            "chapter_count": 18,
            "is_main_feature": True,
            "display_name": "Test Film",
            "audio_tracks": [
                {
                    "track_index": 0,
                    "language_code": "en",
                    "codec": "dts",
                    "channels": 6,
                    "is_default": True,
                }
            ],
            "subtitle_tracks": [
                {
                    "track_index": 0,
                    "language_code": "en",
                    "codec": "pgs",
                    "is_default": False,
                }
            ],
        }
    ],
}


class TestDiscEdits:
    """GET /v1/disc/{fingerprint}/edits"""

    def test_edits_after_submit_has_create_entry(
        self, client, auth_header
    ):
        """Submitting a disc creates a 'create' edit; GET edits returns it."""
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        assert resp.status_code == 201

        edits_resp = client.get("/v1/disc/bd-EDITS-001/edits")
        assert edits_resp.status_code == 200
        data = edits_resp.json()
        assert data["fingerprint"] == "bd-EDITS-001"
        assert "request_id" in data
        assert len(data["edits"]) == 1
        assert data["edits"][0]["edit_type"] == "create"
        assert data["edits"][0]["user_id"] is not None
        assert data["edits"][0]["created_at"] != ""

    def test_edits_after_confirmation_has_two_entries(
        self, client, auth_header, second_auth_header
    ):
        """Submit then confirm via a second contributor's structural
        re-submission (D-01, the /verify route is retired per D-02) → GET
        edits shows create + verify entries."""
        client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        confirm_resp = client.post(
            "/v1/disc", json=VALID_PAYLOAD, headers=second_auth_header
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "verified"

        edits_resp = client.get("/v1/disc/bd-EDITS-001/edits")
        assert edits_resp.status_code == 200
        data = edits_resp.json()
        assert len(data["edits"]) == 2
        assert data["edits"][0]["edit_type"] == "create"
        assert data["edits"][1]["edit_type"] == "verify"

    def test_edits_nonexistent_fingerprint_returns_404(self, client):
        """GET edits for an unknown fingerprint → 404."""
        resp = client.get("/v1/disc/totally-fake-fp/edits")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data

    def test_edits_after_auto_verify_shows_verify_entry(
        self, client, auth_header, second_auth_header
    ):
        """Auto-verify via duplicate submit creates a 'verify' edit entry."""
        # First user submits
        client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)

        # Second user submits same fingerprint with matching metadata → auto-verify
        matching_payload = {
            **VALID_PAYLOAD,
            "release": {
                "title": "Test Film",
                "year": 2024,
                "content_type": "movie",
                "tmdb_id": 77777,
                "original_language": "en",
            },
        }
        resp = client.post(
            "/v1/disc", json=matching_payload, headers=second_auth_header
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

        edits_resp = client.get("/v1/disc/bd-EDITS-001/edits")
        data = edits_resp.json()
        assert len(data["edits"]) == 2
        assert data["edits"][0]["edit_type"] == "create"
        assert data["edits"][1]["edit_type"] == "verify"
        assert "auto-verified" in data["edits"][1]["edit_note"]

    def test_edits_after_dispute_shows_disputed_entry(
        self, client, auth_header, second_auth_header
    ):
        """Disputed submission via conflicting metadata creates a 'disputed' edit."""
        client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)

        conflicting_payload = {
            **VALID_PAYLOAD,
            "release": {
                "title": "Completely Different Film",
                "year": 2020,
                "content_type": "movie",
                "tmdb_id": 99999,
                "original_language": "en",
            },
        }
        resp = client.post(
            "/v1/disc", json=conflicting_payload, headers=second_auth_header
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disputed"

        edits_resp = client.get("/v1/disc/bd-EDITS-001/edits")
        data = edits_resp.json()
        assert len(data["edits"]) == 2
        assert data["edits"][0]["edit_type"] == "create"
        assert data["edits"][1]["edit_type"] == "disputed"
        assert "metadata conflict" in data["edits"][1]["edit_note"]
