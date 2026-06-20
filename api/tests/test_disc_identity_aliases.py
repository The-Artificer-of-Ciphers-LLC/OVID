"""Tests for Disc Identity Lookup Alias storage and resolution."""

from sqlalchemy.orm import Session

from app.models import Disc, DiscIdentityAlias, DiscRelease, Release


VALID_PAYLOAD = {
    "fingerprint": "dvd1-submit-primary",
    "fingerprint_aliases": ["dvdread1-submit-alias"],
    "format": "DVD",
    "region_code": "1",
    "release": {
        "title": "Alias Test Film",
        "year": 2026,
        "content_type": "movie",
        "tmdb_id": 20260620,
        "original_language": "en",
    },
    "titles": [],
}


def _add_alias(db: Session, disc_id, fingerprint: str) -> None:
    db.add(DiscIdentityAlias(disc_id=disc_id, fingerprint=fingerprint))
    db.commit()


class TestDiscIdentityAliases:
    def test_submit_stores_alias_and_lookup_returns_primary(
        self, client, auth_header, db_session: Session
    ) -> None:
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        assert resp.status_code == 201
        assert resp.json()["fingerprint"] == "dvd1-submit-primary"

        alias = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-submit-alias")
            .one()
        )
        disc = db_session.query(Disc).filter_by(fingerprint="dvd1-submit-primary").one()
        assert alias.disc_id == disc.id

        lookup = client.get("/v1/disc/dvdread1-submit-alias")
        assert lookup.status_code == 200
        assert lookup.json()["fingerprint"] == "dvd1-submit-primary"

    def test_register_duplicate_persists_new_alias(
        self, client, auth_header, db_session: Session, seeded_disc
    ) -> None:
        resp = client.post(
            "/v1/disc/register",
            json={
                "fingerprint": "dvd-ABC123-main",
                "fingerprint_aliases": ["dvdread1-matrix"],
                "format": "DVD",
            },
            headers=auth_header,
        )
        assert resp.status_code == 409
        assert resp.json()["fingerprint"] == "dvd-ABC123-main"

        alias = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-matrix")
            .one()
        )
        assert alias.disc_id == seeded_disc["disc_id"]

        lookup = client.get("/v1/disc/dvdread1-matrix")
        assert lookup.status_code == 200
        assert lookup.json()["fingerprint"] == "dvd-ABC123-main"

    def test_duplicate_submit_via_new_alias_auto_verifies_existing_disc(
        self,
        client,
        db_session: Session,
        seeded_disc_with_owner,
        second_auth_header,
    ) -> None:
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "dvdread1-matrix-submit",
            "fingerprint_aliases": ["dvd-ABC123-main"],
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
        assert resp.json()["status"] == "verified"

        db_session.expire_all()
        alias = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvdread1-matrix-submit")
            .one()
        )
        assert alias.disc_id == seeded_disc_with_owner["disc_id"]

        lookup = client.get("/v1/disc/dvdread1-matrix-submit")
        assert lookup.status_code == 200
        assert lookup.json()["fingerprint"] == "dvd-ABC123-main"
        assert lookup.json()["status"] == "verified"

    def test_alias_conflict_returns_409(
        self, client, auth_header, db_session: Session, seeded_disc
    ) -> None:
        other_disc = Disc(
            fingerprint="dvd1-other-primary",
            format="DVD",
            status="unverified",
        )
        db_session.add(other_disc)
        db_session.flush()
        _add_alias(db_session, other_disc.id, "dvdread1-shared-conflict")

        resp = client.post(
            "/v1/disc/register",
            json={
                "fingerprint": "dvd-ABC123-main",
                "fingerprint_aliases": ["dvdread1-shared-conflict"],
                "format": "DVD",
            },
            headers=auth_header,
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "identity_conflict"

    def test_verify_accepts_alias_and_returns_primary(
        self, client, auth_header, db_session: Session, seeded_disc
    ) -> None:
        _add_alias(db_session, seeded_disc["disc_id"], "dvdread1-verify-alias")

        resp = client.post("/v1/disc/dvdread1-verify-alias/verify", headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()["fingerprint"] == "dvd-ABC123-main"

    def test_edits_accepts_alias_and_returns_primary(
        self, client, auth_header, db_session: Session
    ) -> None:
        resp = client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)
        assert resp.status_code == 201

        edits = client.get("/v1/disc/dvdread1-submit-alias/edits")
        assert edits.status_code == 200
        assert edits.json()["fingerprint"] == "dvd1-submit-primary"

    def test_resolve_dispute_accepts_alias(
        self, client, trusted_auth_header, db_session: Session
    ) -> None:
        release = Release(
            title="Alias Dispute Film",
            year=2026,
            content_type="movie",
        )
        db_session.add(release)
        db_session.flush()

        disc = Disc(
            fingerprint="dvd1-dispute-primary",
            format="DVD",
            status="disputed",
        )
        db_session.add(disc)
        db_session.flush()
        db_session.execute(
            DiscRelease.__table__.insert().values(
                disc_id=disc.id,
                release_id=release.id,
            )
        )
        _add_alias(db_session, disc.id, "dvdread1-dispute-alias")

        resp = client.post(
            "/v1/disc/dvdread1-dispute-alias/resolve",
            json={"action": "verify"},
            headers=trusted_auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"
