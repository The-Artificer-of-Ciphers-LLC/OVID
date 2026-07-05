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
        self, client, db_session, seeded_disc_with_owner, auth_header
    ):
        """Original submitter cannot verify their own UNVERIFIED disc → 403.

        WR-01: the idempotency no-op (already-verified) must be checked
        BEFORE the self-submission guard, so this test explicitly seeds an
        unverified disc to exercise the genuine self-submission-blocked
        path — see test_self_verify_on_already_verified_disc_is_idempotent
        for the already-verified case, which must NOT 403.
        """
        disc = db_session.get(Disc, seeded_disc_with_owner["disc_id"])
        disc.status = "unverified"
        db_session.commit()

        resp = client.post(
            "/v1/disc/dvd-ABC123-main/verify", headers=auth_header
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "forbidden"
        assert "Cannot verify your own submission" in data["message"]

    def test_self_verify_on_already_verified_disc_is_idempotent(
        self, client, seeded_disc_with_owner, auth_header
    ):
        """WR-01: original submitter re-verifying an ALREADY-verified disc
        gets the same idempotent 200 no-op as any other caller — not a
        spurious 403. ``seeded_disc_with_owner`` defaults to status
        "verified" with submitted_by set to the auth_header user.
        """
        resp = client.post(
            "/v1/disc/dvd-ABC123-main/verify", headers=auth_header
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "already verified"

    def test_different_user_can_verify(
        self, client, db_session, seeded_disc_with_owner, second_auth_header
    ):
        """A different user can verify a disc submitted by someone else → 200."""
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

    def test_verify_already_verified_idempotent(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Verifying an already-verified disc returns 200 with idempotent message."""
        resp = client.post("/v1/disc/dvd-ABC123-main/verify", headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert data["message"] == "already verified"
        assert "request_id" in data

    def test_verify_already_verified_no_extra_edit(
        self, client, db_session, seeded_disc, auth_header
    ):
        """Re-verifying an already-verified disc does NOT create a new DiscEdit."""
        client.post("/v1/disc/dvd-ABC123-main/verify", headers=auth_header)
        edits = db_session.query(DiscEdit).all()
        assert len(edits) == 0  # idempotent, no DiscEdit created

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
        """POST without Authorization header → 401."""
        resp = client.post("/v1/disc/dvd-ABC123-main/verify")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "missing_token"
