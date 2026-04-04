"""Tests for POST /v1/disc/{fingerprint}/verify endpoint (R011 two-contributor)."""

from app.models import Disc, DiscEdit


class TestVerifyDisc:
    """POST /v1/disc/{fingerprint}/verify"""

    def test_verify_unverified_disc_no_submitted_by(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Verifying a disc with no submitted_by is allowed for any user."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "Disc verified successfully"
        assert "request_id" in data

    def test_verify_creates_disc_edit(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Successful verify creates a DiscEdit with edit_type='verify'."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200

        edits = (
            db_session.query(DiscEdit)
            .filter(DiscEdit.disc_id == disc.id)
            .all()
        )
        assert len(edits) == 1
        assert edits[0].edit_type == "verify"

    def test_self_verify_returns_403(
        self, client, seeded_disc_with_owner, auth_header
    ):
        """Original submitter cannot verify their own disc - 403."""
        resp = client.post(
            "/v1/disc/dvd-ABC123-main/verify", headers=auth_header
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "forbidden"
        assert "Cannot verify your own submission" in data["message"]

    def test_different_user_can_verify(
        self, client, db_session, seeded_disc_with_owner, second_auth_header
    ):
        """A different user can verify a disc submitted by someone else - 200."""
        disc = db_session.get(Disc, seeded_disc_with_owner["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(
            "/v1/disc/dvd-ABC123-main/verify", headers=second_auth_header
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "Disc verified successfully"

    def test_verify_not_found(self, client, auth_header):
        """Verifying a non-existent fingerprint returns 404."""
        resp = client.post("/v1/disc/nonexistent-fp/verify", headers=auth_header)
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"
        assert "request_id" in data

    def test_verify_updates_confidence(
        self, client, db_session, seeded_disc, auth_header
    ):
        """After verify, GET lookup shows confidence='high'."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200

        lookup = client.get(f"/v1/disc/{disc.fingerprint}")
        assert lookup.status_code == 200
        assert lookup.json()["confidence"] == "high"
        assert lookup.json()["status"] == "verified"

    def test_verify_without_auth_returns_401(self, client, seeded_disc):
        """POST without Authorization header - 401."""
        resp = client.post("/v1/disc/dvd-ABC123-main/verify")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"


# ---------------------------------------------------------------------------
# State machine validation tests (BUG-02)
# ---------------------------------------------------------------------------

class TestVerifyStateMachine:
    """State machine enforcement: verified is a terminal state."""

    def test_verified_to_verified_returns_400(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Verifying an already-verified disc returns 400 (terminal state)."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        assert disc.status == "verified"

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 400
        data = resp.json()
        assert data["error"] == "invalid_status_transition"
        assert "verified" in data["current_status"]

    def test_unverified_to_verified_allowed(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Transition from unverified to verified is allowed."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    def test_disputed_to_verified_allowed(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Transition from disputed to verified is allowed."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        disc.status = "disputed"
        db_session.commit()

        resp = client.post(f"/v1/disc/{disc.fingerprint}/verify", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    def test_resolve_dispute_verified_disc_rejected(
        self, client, db_session, seeded_disc, trusted_auth_header
    ):
        """Cannot resolve a disc that is not in disputed state."""
        disc = db_session.get(Disc, seeded_disc["disc_id"])
        assert disc.status == "verified"

        resp = client.post(
            f"/v1/disc/{disc.fingerprint}/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "invalid_state"
