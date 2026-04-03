"""Tests for dispute resolution — GET /v1/disc/disputed, POST /v1/disc/{fp}/resolve."""

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from app.models import Disc, DiscEdit, DiscRelease, Release, User
from tests.conftest import seed_test_disc


# ---------------------------------------------------------------------------
# Helper payloads
# ---------------------------------------------------------------------------
VALID_PAYLOAD = {
    "fingerprint": "dvd-DISPUTE-test",
    "format": "DVD",
    "region_code": "1",
    "release": {
        "title": "Test Movie A",
        "year": 2020,
        "content_type": "movie",
        "tmdb_id": 1000,
    },
    "titles": [],
}


# ---------------------------------------------------------------------------
# GET /v1/disc/disputed
# ---------------------------------------------------------------------------
class TestListDisputed:
    def test_list_disputed_empty(self, client) -> None:
        """No disputed discs → 200 with empty results list, total=0."""
        resp = client.get("/v1/disc/disputed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["results"] == []
        assert "request_id" in body

    def test_list_disputed_with_disc(self, client, db_session: Session) -> None:
        """Seed a disc, force status to 'disputed' → GET /v1/disc/disputed shows it."""
        release = Release(
            title="Disputed Movie",
            year=2021,
            content_type="movie",
        )
        db_session.add(release)
        db_session.flush()

        disc = Disc(
            fingerprint="dvd-DISPUTED-001",
            format="DVD",
            status="disputed",
        )
        db_session.add(disc)
        db_session.flush()

        db_session.execute(
            DiscRelease.__table__.insert().values(
                disc_id=disc.id, release_id=release.id
            )
        )
        db_session.commit()

        resp = client.get("/v1/disc/disputed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["results"]) == 1
        assert body["results"][0]["fingerprint"] == "dvd-DISPUTED-001"
        assert body["results"][0]["status"] == "disputed"


# ---------------------------------------------------------------------------
# submit_disc stores conflict data in DiscEdit.new_value
# ---------------------------------------------------------------------------
class TestSubmitStoresConflictData:
    def test_submit_stores_conflict_data(
        self, client, db_session: Session, seeded_disc_with_owner, second_auth_header
    ) -> None:
        """Submit same fingerprint twice with different release titles →
        DiscEdit with edit_type='disputed' has new_value as valid JSON
        containing the second submission's release data.
        """
        conflicting_payload = {
            "fingerprint": "dvd-ABC123-main",
            "format": "DVD",
            "release": {
                "title": "Wrong Movie Title",
                "year": 1999,
                "content_type": "movie",
                "tmdb_id": 99999,
            },
            "titles": [],
        }
        resp = client.post(
            "/v1/disc", json=conflicting_payload, headers=second_auth_header
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disputed"

        # Find the DiscEdit with edit_type='disputed'
        disc = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == "dvd-ABC123-main")
            .first()
        )
        edit = (
            db_session.query(DiscEdit)
            .filter(
                DiscEdit.disc_id == disc.id,
                DiscEdit.edit_type == "disputed",
            )
            .first()
        )
        assert edit is not None
        assert edit.new_value is not None

        conflict_data = json.loads(edit.new_value)
        assert conflict_data["title"] == "Wrong Movie Title"
        assert conflict_data["tmdb_id"] == 99999


# ---------------------------------------------------------------------------
# POST /v1/disc/{fingerprint}/resolve
# ---------------------------------------------------------------------------
class TestResolveDispute:
    def _seed_disputed_disc(self, db_session: Session) -> Disc:
        """Helper: create a disc in 'disputed' status."""
        release = Release(
            title="Disputed Resolve Movie",
            year=2022,
            content_type="movie",
        )
        db_session.add(release)
        db_session.flush()

        disc = Disc(
            fingerprint="dvd-RESOLVE-test",
            format="DVD",
            status="disputed",
        )
        db_session.add(disc)
        db_session.flush()

        db_session.execute(
            DiscRelease.__table__.insert().values(
                disc_id=disc.id, release_id=release.id
            )
        )
        db_session.commit()
        return disc

    def test_resolve_verify_as_trusted(
        self, client, db_session: Session, trusted_auth_header
    ) -> None:
        """POST resolve {"action":"verify"} with trusted user → 200, disc verified."""
        disc = self._seed_disputed_disc(db_session)

        resp = client.post(
            f"/v1/disc/{disc.fingerprint}/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "verified"
        assert body["message"] == "Dispute resolved"

        # Verify disc status in DB
        db_session.expire_all()
        updated = db_session.query(Disc).filter(Disc.id == disc.id).first()
        assert updated.status == "verified"

        # Verify DiscEdit with edit_type='resolve' exists
        edit = (
            db_session.query(DiscEdit)
            .filter(DiscEdit.disc_id == disc.id, DiscEdit.edit_type == "resolve")
            .first()
        )
        assert edit is not None
        assert "marked verified" in edit.edit_note

    def test_resolve_reject_as_trusted(
        self, client, db_session: Session, trusted_auth_header
    ) -> None:
        """POST resolve {"action":"reject"} → disc status is 'unverified'."""
        disc = self._seed_disputed_disc(db_session)

        resp = client.post(
            f"/v1/disc/{disc.fingerprint}/resolve",
            json={"action": "reject"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unverified"

        db_session.expire_all()
        updated = db_session.query(Disc).filter(Disc.id == disc.id).first()
        assert updated.status == "unverified"

    def test_resolve_as_contributor_forbidden(
        self, client, db_session: Session, auth_header
    ) -> None:
        """POST resolve with regular contributor auth_header → 403."""
        disc = self._seed_disputed_disc(db_session)

        resp = client.post(
            f"/v1/disc/{disc.fingerprint}/resolve",
            json={"action": "verify"},
            headers=auth_header,
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"] == "forbidden"

    def test_resolve_nonexistent_disc(
        self, client, trusted_auth_header
    ) -> None:
        """POST /v1/disc/dvd1-nonexistent/resolve → 404."""
        resp = client.post(
            "/v1/disc/dvd1-nonexistent/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"

    def test_resolve_non_disputed_disc(
        self, client, db_session: Session, seeded_disc, trusted_auth_header
    ) -> None:
        """Seed a verified disc, POST resolve → 409."""
        resp = client.post(
            "/v1/disc/dvd-ABC123-main/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"] == "invalid_state"

    def test_resolve_assigns_seq_num(
        self, client, db_session: Session, trusted_auth_header
    ) -> None:
        """After resolve, disc.seq_num is not None and > 0."""
        disc = self._seed_disputed_disc(db_session)

        client.post(
            f"/v1/disc/{disc.fingerprint}/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )

        db_session.expire_all()
        updated = db_session.query(Disc).filter(Disc.id == disc.id).first()
        assert updated.seq_num is not None
        assert updated.seq_num > 0
