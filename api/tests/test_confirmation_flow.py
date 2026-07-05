"""Integration tests for the two-contributor confirmation flow (VERIFY-01/03/04).

Confirmation is structural re-submission via POST /v1/disc (D-01): a second,
DISTINCT contributor reproduces the WITHHELD structure to flip
unverified→verified, gated by the anti-Sybil pre-check (cooldown 429 / soft
score 403, D-04/D-13). Everything is exercised end-to-end through the
TestClient — never the retired bodyless /verify route (D-02).

Truth table pinned here (Open Question A3):
  structural-match + release-match     -> verify
  structural-match + release-mismatch  -> dispute
  structural-mismatch                  -> dispute (A2 keeps a verified disc verified)
"""

import copy
from datetime import datetime, timezone

from app.anti_sybil import CONFIRMATION_MAX_PER_WINDOW, ip_subnet_hash
from app.deps import get_db
from app.models import Disc, DiscEdit
from tests.conftest import (
    _get_test_db,
    matrix_matching_submit_payload,
    seed_test_disc,
)

from fastapi.testclient import TestClient

SEED_FP = "dvd-ABC123-main"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _seed_verify_edits(db, user_id, disc_id, count):
    """Seed ``count`` recent verify DiscEdits for ``user_id`` (cooldown source)."""
    now = datetime.now(timezone.utc)
    for _ in range(count):
        db.add(
            DiscEdit(
                disc_id=disc_id,
                user_id=user_id,
                edit_type="verify",
                created_at=now,
            )
        )
    db.commit()


def _seed_create_edit_ip(db, disc_id, user_id, ip_hash):
    """Seed the submitter's create DiscEdit carrying ``ip_hash`` (IP-diversity ref)."""
    db.add(
        DiscEdit(
            disc_id=disc_id,
            user_id=user_id,
            edit_type="create",
            ip_hash=ip_hash,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _post_from_ip(ip, payload, headers):
    """POST /v1/disc through a TestClient whose request.client.host == ``ip``."""
    from main import app

    app.dependency_overrides[get_db] = _get_test_db
    try:
        with TestClient(app, client=(ip, 40000)) as c:
            return c.post("/v1/disc", json=payload, headers=headers)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# VERIFY-01 — structural re-submission verifies; self-confirm rejected
# ---------------------------------------------------------------------------
class TestStructuralConfirmation:
    def test_distinct_contributor_structural_resubmit_verifies(
        self, client, db_session, test_user, second_auth_header
    ):
        """User B reproduces the withheld structure of A's unverified disc via
        POST /v1/disc → 200 verified; GET reflects verified."""
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
        resp = client.post(
            "/v1/disc",
            json=matrix_matching_submit_payload(),
            headers=second_auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert "auto-verified" in data["message"]

        get_resp = client.get(f"/v1/disc/{SEED_FP}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "verified"

    def test_self_resubmit_returns_409(
        self, client, db_session, test_user, auth_header
    ):
        """The ORIGINAL submitter re-submitting their own disc → 409, never a
        self-confirmation (VERIFY-01/D-05)."""
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
        resp = client.post(
            "/v1/disc",
            json=matrix_matching_submit_payload(),
            headers=auth_header,
        )
        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "conflict"

        get_resp = client.get(f"/v1/disc/{SEED_FP}")
        assert get_resp.json()["status"] == "unverified"

    def test_benign_rip_jitter_still_verifies(
        self, client, db_session, test_user, second_auth_header
    ):
        """Relabeled codec (AC-3 vs ac3) and ±duration within tolerance are
        benign independent-rip jitter → still verifies (D-03)."""
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
        payload = copy.deepcopy(matrix_matching_submit_payload())
        payload["titles"][0]["audio_tracks"][0]["codec"] = "AC-3"
        payload["titles"][0]["duration_secs"] = 8162  # +2s, within DURATION_TOLERANCE_SECS
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    def test_real_structural_difference_does_not_verify(
        self, client, db_session, test_user, second_auth_header
    ):
        """A real structural difference (wrong chapter_count) does NOT verify —
        it routes to the dispute path even though the RELEASE matches (D-03)."""
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
        payload = copy.deepcopy(matrix_matching_submit_payload())
        payload["titles"][0]["chapter_count"] = 40  # real difference vs stored 39
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] != "verified"
        assert data["status"] == "disputed"

    def test_structural_match_release_mismatch_disputes(
        self, client, db_session, test_user, second_auth_header
    ):
        """Matching structure but conflicting RELEASE metadata → dispute, not
        verify (A3: release-consistency is the dispute trigger)."""
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
        payload = copy.deepcopy(matrix_matching_submit_payload())
        payload["release"] = {
            "title": "Totally Different Film",
            "year": 2020,
            "content_type": "movie",
            "tmdb_id": 99999,
            "original_language": "en",
        }
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disputed"


# ---------------------------------------------------------------------------
# VERIFY-03 / A2 — a verified disc is never silently flipped
# ---------------------------------------------------------------------------
class TestVerifiedDiscNotFlipped:
    def test_third_mismatch_against_verified_stays_verified(
        self, client, db_session, test_user, second_auth_header
    ):
        """A structural mismatch against an already-VERIFIED disc stays
        verified (200) and records a dispute_attempted audit edit — never a
        silent flip (VERIFY-03/A2)."""
        seeded = seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="verified"
        )
        payload = copy.deepcopy(matrix_matching_submit_payload())
        payload["titles"][0]["chapter_count"] = 41  # structural mismatch
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

        db_session.expire_all()
        disc = db_session.get(Disc, seeded["disc_id"])
        assert disc.status == "verified"
        edit = (
            db_session.query(DiscEdit)
            .filter(
                DiscEdit.disc_id == seeded["disc_id"],
                DiscEdit.edit_type == "dispute_attempted",
            )
            .first()
        )
        assert edit is not None, "expected a dispute_attempted audit edit"


# ---------------------------------------------------------------------------
# VERIFY-04 — anti-Sybil gate BEFORE any status write
# ---------------------------------------------------------------------------
class TestAntiSybilGate:
    def test_cooldown_hard_block_returns_429(
        self, client, db_session, test_user, second_user, second_auth_header
    ):
        """After more than CONFIRMATION_MAX_PER_WINDOW verify edits in the
        window, the next confirmation → 429 with Retry-After + request_id
        (cooldown hard floor, D-13), before any structural comparison."""
        seeded = seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="unverified"
        )
        _seed_verify_edits(
            db_session,
            second_user.id,
            seeded["disc_id"],
            CONFIRMATION_MAX_PER_WINDOW + 1,
        )
        resp = client.post(
            "/v1/disc",
            json=matrix_matching_submit_payload(),
            headers=second_auth_header,
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        data = resp.json()
        assert data["error"] == "rate_limited"
        assert "request_id" in data

        db_session.expire_all()
        assert db_session.get(Disc, seeded["disc_id"]).status == "unverified"

    def test_fresh_account_same_subnet_returns_403(
        self, client, db_session, test_user, second_auth_header, monkeypatch
    ):
        """A fresh account confirming from the SAME /24 subnet as the submitter
        is the exact Sybil signature → 403 insufficient_trust (D-04/D-05),
        before any status write."""
        monkeypatch.setenv("OVID_IP_HASH_SALT", "test-salt")
        salt = b"test-salt"
        seeded = seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="unverified"
        )
        # Submitter's create-edit records their subnet hash (IP-diversity ref).
        _seed_create_edit_ip(
            db_session,
            seeded["disc_id"],
            test_user.id,
            ip_subnet_hash("1.2.3.4", salt),
        )
        # Confirmer (fresh second_user) posts from the SAME /24.
        resp = _post_from_ip(
            "1.2.3.99", matrix_matching_submit_payload(), second_auth_header
        )
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "insufficient_trust"
        assert "request_id" in data

        db_session.expire_all()
        assert db_session.get(Disc, seeded["disc_id"]).status == "unverified"

    def test_fresh_account_distinct_subnet_verifies(
        self, client, db_session, test_user, second_auth_header, monkeypatch
    ):
        """A fresh account confirming from a DISTINCT subnet offsets the
        young-account penalty and verifies (fail-open weighting, D-04/D-07)."""
        monkeypatch.setenv("OVID_IP_HASH_SALT", "test-salt")
        salt = b"test-salt"
        seeded = seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="unverified"
        )
        _seed_create_edit_ip(
            db_session,
            seeded["disc_id"],
            test_user.id,
            ip_subnet_hash("1.2.3.4", salt),
        )
        resp = _post_from_ip(
            "9.9.9.9", matrix_matching_submit_payload(), second_auth_header
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    def test_confirmation_verify_edit_carries_ip_hash(
        self, client, db_session, test_user, second_auth_header, monkeypatch
    ):
        """The verify DiscEdit produced by a confirmation carries the
        confirmer's salted subnet hash (D-06 capture)."""
        monkeypatch.setenv("OVID_IP_HASH_SALT", "test-salt")
        salt = b"test-salt"
        seeded = seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="unverified"
        )
        resp = _post_from_ip(
            "9.9.9.9", matrix_matching_submit_payload(), second_auth_header
        )
        assert resp.status_code == 200

        db_session.expire_all()
        verify_edit = (
            db_session.query(DiscEdit)
            .filter(
                DiscEdit.disc_id == seeded["disc_id"],
                DiscEdit.edit_type == "verify",
            )
            .first()
        )
        assert verify_edit is not None
        assert verify_edit.ip_hash == ip_subnet_hash("9.9.9.9", salt)
