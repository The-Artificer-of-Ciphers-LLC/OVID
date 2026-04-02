"""Tests for POST /v1/disc/{fingerprint}/verify endpoint."""

from app.models import Disc


class TestVerifyDisc:
    """POST /v1/disc/{fingerprint}/verify"""

    def test_verify_unverified_disc(self, client, db_session, seeded_disc, auth_header):
        """Verifying an unverified disc promotes status to 'verified'."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "Disc verified successfully"
        assert "request_id" in data

    def test_verify_already_verified(self, client, db_session, seeded_disc, auth_header):
        """Verifying an already-verified disc returns 200 with idempotent message."""
        resp = client.post("/v1/disc/dvd-ABC123-main/verify", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "already verified"
        assert "request_id" in data

    def test_verify_not_found(self, client, auth_header):
        """Verifying a non-existent fingerprint returns 404."""
        resp = client.post("/v1/disc/nonexistent-fp/verify", headers=auth_header)
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data

    def test_verify_updates_confidence(self, client, db_session, seeded_disc, auth_header):
        """After verify, GET lookup shows confidence='high'."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        # Verify
        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200

        # Lookup — confidence should now be "high"
        lookup = client.get(f"/v1/disc/{disc.fingerprint}")
        assert lookup.status_code == 200
        assert lookup.json()["confidence"] == "high"
        assert lookup.json()["status"] == "verified"

    def test_verify_without_auth_returns_401(self, client, seeded_disc):
        """POST without Authorization header → 401."""
        resp = client.post("/v1/disc/dvd-ABC123-main/verify")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"
