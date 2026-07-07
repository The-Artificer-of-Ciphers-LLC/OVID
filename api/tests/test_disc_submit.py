"""Tests for POST /v1/disc."""

import uuid

from sqlalchemy.orm import Session

from app.models import Disc, DiscEdit, DiscIdentityAlias, DiscRelease, DiscTitle, DiscTrack, Release
from app.routes.disc import _select_primary
from tests.conftest import matrix_matching_submit_payload, seed_test_disc, seed_test_disc_set


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

    def test_submit_with_titles_and_tracks(self, client, auth_header, db_session: Session):
        """POST with titles+tracks persists the nested structure.

        The freshly-submitted disc is ``unverified``, so its public GET
        withholds the structural payload (anti-echo redaction, D-09) — the
        titles round-trip via GET only after verification (covered by
        test_disc_lookup / test_lookup_redaction). Persistence is asserted
        here directly against the ORM so submit coverage is preserved.
        """
        client.post("/v1/disc", json=VALID_PAYLOAD, headers=auth_header)

        # Public read of the unverified disc withholds structure (D-09).
        resp = client.get("/v1/disc/bd-NEW001-main")
        assert resp.status_code == 200
        assert resp.json()["titles"] == []

        # …but the submitted structure did persist (proven at the DB layer).
        disc = db_session.query(Disc).filter(Disc.fingerprint == "bd-NEW001-main").first()
        assert disc is not None
        assert len(disc.titles) == 1
        t = disc.titles[0]
        assert t.title_index == 0
        audio = [tr for tr in t.tracks if tr.track_type == "audio"]
        subs = [tr for tr in t.tracks if tr.track_type == "subtitle"]
        assert len(audio) == 1
        assert audio[0].codec == "dts-hd"
        assert len(subs) == 2

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
        self, client, db_session, auth_header
    ):
        """POST same fingerprint with conflicting metadata against an
        UNVERIFIED disc → 200 disputed via the legitimate flag_dispute path.

        The seeded disc has no submitted_by, so the current user is treated
        as a different contributor.  Metadata (tmdb_id) differs → disputed.
        Seeded explicitly unverified (VERIFY-02 A2): a verified disc must
        NEVER silently flip to disputed — see
        test_mismatched_submission_against_verified_disc_stays_verified.
        """
        seed_test_disc(db_session, status="unverified")
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
        db_session,
        test_user,
        second_auth_header,
    ):
        """A distinct second contributor reproducing the WITHHELD structure
        (not just the public release fields) auto-verifies → 200 verified.

        The verify trigger is structural equality now (D-01/D-03), so the
        confirmer must re-submit the seeded disc's actual structure — a
        release-only match no longer verifies. Seeded UNVERIFIED and owned by
        a different user so this exercises the genuine unverified→verified flip.
        """
        seed_test_disc(
            db_session, submitted_by_id=test_user.id, status="unverified"
        )
        resp = client.post(
            "/v1/disc",
            json=matrix_matching_submit_payload(),
            headers=second_auth_header,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "verified"
        assert "auto-verified" in data["message"]

    def test_duplicate_conflicting_metadata_disputes(
        self,
        client,
        db_session,
        test_user,
        second_auth_header,
    ):
        """Second user submitting same fingerprint with different metadata
        against an UNVERIFIED disc → 200 disputed via the legitimate
        flag_dispute path (VERIFY-02 A2 — see the verified-stays-verified
        test below for the case where the seed disc is already verified).
        """
        seed_test_disc(db_session, submitted_by_id=test_user.id, status="unverified")
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

    def test_duplicate_zero_title_submission_does_not_auto_verify(
        self,
        client,
        auth_header,
        second_auth_header,
    ):
        """CR-02: a disc submitted with an empty title list must never
        vacuously auto-verify off a second, distinct contributor's
        zero-title submission — even with an identical, matching release.
        An empty structure is not proof of physical possession (fail-safe);
        the mismatch correctly routes to the dispute path for human review,
        never a silent verify.
        """
        payload = {
            "fingerprint": "bd-ZEROTITLE-001",
            "format": "BD",
            "release": {
                "title": "Zero Title Film",
                "year": 2022,
                "content_type": "movie",
                "tmdb_id": 555555,
                "original_language": "en",
            },
            "titles": [],
        }
        first_resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert first_resp.status_code == 201

        second_resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert second_resp.status_code == 200
        data = second_resp.json()
        assert data["status"] != "verified"

    def test_mismatched_submission_against_verified_disc_stays_verified(
        self,
        client,
        db_session,
        seeded_disc_with_owner,
        second_auth_header,
    ):
        """A2 (VERIFY-02 crit #4): a mismatched submission against an
        already-VERIFIED disc must never silently flip to disputed. It
        stays verified, records an audit DiscEdit, and returns 200 — the
        response body must never report the disputed status.
        """
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
        assert data["status"] != "disputed"
        assert data["status"] == "verified"

        db_session.expire_all()
        disc = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == "dvd-ABC123-main")
            .first()
        )
        assert disc.status == "verified"

        edit = (
            db_session.query(DiscEdit)
            .filter(DiscEdit.disc_id == disc.id)
            .order_by(DiscEdit.created_at.desc())
            .first()
        )
        assert edit is not None, "expected an audit DiscEdit for the conflict attempt"


# ---------------------------------------------------------------------------
# Disc-row insert race safety (IDENT-02)
# ---------------------------------------------------------------------------
class TestDiscRowRace:
    """Two submissions racing the SAME new primary fingerprint must converge
    to a single disc row instead of splitting (IDENT-02).

    Per CLAUDE.md's cross-platform IO-failure rule and 01-RESEARCH.md
    Pitfall 1, this is exercised via deterministic monkeypatch injection —
    never threading/asyncio — restored in a ``finally`` block.
    """

    def test_new_fingerprint_losing_race_converges_to_one_disc(
        self, client, db_session, auth_header
    ):
        """Simulate a stale read: resolve_existing_disc_for_identities
        reports "no existing disc" on its first call (as a losing worker
        would see), even though a real disc row for this fingerprint is
        pre-inserted (the winner). The route's disc-row insert then hits
        the real UNIQUE constraint and must re-resolve to the winner
        instead of crashing or creating a split disc row.
        """
        import app.routes.disc as disc_routes

        fingerprint = "bd-RACE-NEW-001"
        winner = Disc(fingerprint=fingerprint, format="BD", status="unverified")
        db_session.add(winner)
        db_session.commit()
        winner_id = winner.id

        original = disc_routes.resolve_existing_disc_for_identities
        calls = {"n": 0}

        def _stale_once(db, primary_fingerprint, aliases):
            calls["n"] += 1
            if calls["n"] == 1:
                return None
            return original(db, primary_fingerprint, aliases)

        disc_routes.resolve_existing_disc_for_identities = _stale_once
        try:
            payload = {**VALID_PAYLOAD, "fingerprint": fingerprint}
            resp = client.post("/v1/disc", json=payload, headers=auth_header)
        finally:
            disc_routes.resolve_existing_disc_for_identities = original

        assert resp.status_code in (200, 409)
        rows = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == fingerprint)
            .all()
        )
        assert len(rows) == 1, "disc-row insert race must converge to one row"
        assert rows[0].id == winner_id


# ---------------------------------------------------------------------------
# Post-savepoint IntegrityError misclassification (CR-01)
# ---------------------------------------------------------------------------
class TestSubmitPostSavepointIntegrityError:
    """A duplicate ``title_index`` violates ``uq_disc_titles_index`` AFTER the
    release+disc savepoint has already committed. This must be reported as a
    client error (400), never mistaken for a fingerprint race (which would
    return 409) and never leak as an unhandled 500 from a subsequent
    re-resolve against an aborted transaction.
    """

    def test_duplicate_title_index_returns_400_not_409_or_500(
        self, client, auth_header
    ):
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-DUPTITLE-001",
            "titles": [
                {**VALID_PAYLOAD["titles"][0], "title_index": 0},
                {**VALID_PAYLOAD["titles"][0], "title_index": 0},
            ],
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 400
        data = resp.json()
        assert "request_id" in data

        # Session must still be usable — a subsequent valid submit succeeds.
        valid_payload = {**VALID_PAYLOAD, "fingerprint": "bd-DUPTITLE-002"}
        resp2 = client.post("/v1/disc", json=valid_payload, headers=auth_header)
        assert resp2.status_code == 201


# ---------------------------------------------------------------------------
# pending_identification handling (WR-03)
# ---------------------------------------------------------------------------
class TestSubmitAgainstPendingIdentificationDisc:
    """A disc registered via ``POST /v1/disc/register`` (ARM pre-registration)
    has status ``pending_identification`` and no Release/titles/tracks yet.
    The first ``submit_disc`` against it must ATTACH the metadata and
    identify the disc — for ANY user, including the original registrant —
    never the same-submitter 409 guard and never the dispute path (WR-03).
    """

    def test_same_user_register_then_submit_identifies(self, client, auth_header):
        """Register→submit by the SAME user is the legitimate ARM workflow:
        must succeed, never 409.
        """
        register_payload = {
            "fingerprint": "bd-PENDING-SAME-001",
            "format": "BD",
            "disc_label": "PENDING_SAME",
        }
        reg_resp = client.post(
            "/v1/disc/register", json=register_payload, headers=auth_header
        )
        assert reg_resp.status_code == 201
        assert reg_resp.json()["status"] == "pending_identification"

        payload = {**VALID_PAYLOAD, "fingerprint": "bd-PENDING-SAME-001"}
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("error") != "conflict"
        assert data["status"] == "unverified"

        get_resp = client.get("/v1/disc/bd-PENDING-SAME-001")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["status"] == "unverified"
        # Identification attached the release; structure is withheld while
        # the disc is unverified (anti-echo redaction, D-09).
        assert get_data["release"]["title"] == "New Film"
        assert get_data["titles"] == []

    def test_different_user_submits_first_metadata_identifies(
        self, client, auth_header, second_auth_header
    ):
        """User A registers, user B submits the FIRST metadata → must
        attach and identify, never mis-route into the dispute path (there
        is no existing Release yet to conflict against).
        """
        register_payload = {
            "fingerprint": "bd-PENDING-DIFF-001",
            "format": "BD",
            "disc_label": "PENDING_DIFF",
        }
        reg_resp = client.post(
            "/v1/disc/register", json=register_payload, headers=auth_header
        )
        assert reg_resp.status_code == 201

        payload = {**VALID_PAYLOAD, "fingerprint": "bd-PENDING-DIFF-001"}
        resp = client.post("/v1/disc", json=payload, headers=second_auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] != "disputed"
        assert data["status"] == "unverified"

        get_resp = client.get("/v1/disc/bd-PENDING-DIFF-001")
        get_data = get_resp.json()
        assert get_data["status"] == "unverified"
        # First metadata attached (identified, not disputed); structure is
        # withheld while the disc is unverified (anti-echo redaction, D-09).
        assert get_data["release"]["title"] == "New Film"
        assert get_data["titles"] == []


# ---------------------------------------------------------------------------
# D-03: server-side hybrid primary selection (_select_primary pure function)
# ---------------------------------------------------------------------------
class TestSelectPrimary:
    def test_dvdread1_alias_promoted_to_primary(self):
        """A dvdread1-* alias alongside a dvd1-* declared primary is
        promoted — dvd1-* is demoted into the remaining alias list."""
        assert _select_primary("dvd1-a", ["dvdread1-b"]) == (
            "dvdread1-b",
            ["dvd1-a"],
        )

    def test_dvdread1_already_primary_unchanged(self):
        """Client already declared dvdread1-* as primary — no duplicate,
        no reordering churn."""
        assert _select_primary("dvdread1-c", ["dvd1-d"]) == (
            "dvdread1-c",
            ["dvd1-d"],
        )

    def test_no_dvdread1_present_unchanged(self):
        """No dvdread1-* string anywhere in the submission — server has
        nothing to prefer, so the submission passes through unchanged."""
        assert _select_primary("dvd1-e", ["bd1-aacs-f"]) == (
            "dvd1-e",
            ["bd1-aacs-f"],
        )

    def test_dvdread1_alongside_unrelated_bd_alias(self):
        """A dvdread1-* candidate alongside an unrelated BD alias is still
        preferred — the BD alias's presence doesn't disturb the
        preference."""
        assert _select_primary("dvd1-g", ["dvdread1-h", "bd1-aacs-i"]) == (
            "dvdread1-h",
            ["dvd1-g", "bd1-aacs-i"],
        )


# ---------------------------------------------------------------------------
# D-03: server-side hybrid primary selection wired into register_disc /
# submit_disc's new-disc SAVEPOINTs + mixed-fleet zero-fragmentation guard
# ---------------------------------------------------------------------------
def _seed_promoted_disc(db: Session, submitted_by_id) -> dict:
    """Seed a disc already promoted to dvdread1-* primary, mirroring
    ``seed_test_disc``'s Matrix structure/insertion order but with
    dvdread1-/dvd1-* prefixed fingerprint values, so a structurally-
    matching resubmission (``matrix_matching_submit_payload``) is
    possible against it.

    Deliberately NOT a change to ``conftest.py``'s ``seed_test_disc``,
    which intentionally uses non-prefixed fingerprints for its own
    unrelated test population.
    """
    release = Release(
        title="The Matrix",
        year=1999,
        content_type="movie",
        tmdb_id=603,
        imdb_id="tt0133093",
        original_language="en",
    )
    db.add(release)
    db.flush()

    disc = Disc(
        fingerprint="dvdread1-already-promoted",
        format="DVD",
        region_code="1",
        upc="012345678901",
        disc_label="THEMATRIX_D1",
        disc_number=1,
        total_discs=1,
        edition_name="10th Anniversary",
        status="verified",
        submitted_by=submitted_by_id,
    )
    db.add(disc)
    db.flush()

    db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint="dvd1-already-promoted"))

    db.execute(
        DiscRelease.__table__.insert().values(disc_id=disc.id, release_id=release.id)
    )

    title = DiscTitle(
        disc_id=disc.id,
        title_index=1,
        title_type="main_feature",
        duration_secs=8160,
        chapter_count=39,
        is_main_feature=True,
        display_name="The Matrix",
    )
    db.add(title)
    db.flush()

    audio = DiscTrack(
        disc_title_id=title.id,
        track_type="audio",
        track_index=0,
        language_code="en",
        codec="ac3",
        channels=6,
        is_default=True,
    )
    subtitle = DiscTrack(
        disc_title_id=title.id,
        track_type="subtitle",
        track_index=0,
        language_code="en",
        codec="vobsub",
        channels=None,
        is_default=False,
    )
    db.add_all([audio, subtitle])
    db.commit()

    return {"disc_id": disc.id, "release_id": release.id, "title_id": title.id}


class TestSelectPrimaryWiring:
    def test_submit_disc_prefers_dvdread1_primary_on_new_disc(
        self, client, auth_header, db_session: Session
    ):
        """POST /v1/disc for a brand-new fingerprint with a dvdread1-*
        alias present -> the server picks the dvdread1-* string as the
        persisted primary, demoting the client's declared dvd1-* primary
        into a Lookup Alias."""
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "dvd1-select-x",
            "fingerprint_aliases": ["dvdread1-select-y"],
            "format": "DVD",
            "disc_label": "SELECT_PRIMARY_SUBMIT",
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201
        data = resp.json()
        assert data["fingerprint"] == "dvdread1-select-y"

        disc = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == "dvdread1-select-y")
            .one()
        )
        alias = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvd1-select-x")
            .one()
        )
        assert alias.disc_id == disc.id

    def test_register_disc_prefers_dvdread1_primary_on_new_disc(
        self, client, auth_header, db_session: Session
    ):
        """POST /v1/disc/register mirrors the same server-side dvdread1-*
        preference on the register-only (no release metadata) path."""
        payload = {
            "fingerprint": "dvd1-select-reg-x",
            "fingerprint_aliases": ["dvdread1-select-reg-y"],
            "format": "DVD",
            "disc_label": "SELECT_PRIMARY_REGISTER",
        }
        resp = client.post("/v1/disc/register", json=payload, headers=auth_header)
        assert resp.status_code == 201
        data = resp.json()
        assert data["fingerprint"] == "dvdread1-select-reg-y"

        disc = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == "dvdread1-select-reg-y")
            .one()
        )
        alias = (
            db_session.query(DiscIdentityAlias)
            .filter(DiscIdentityAlias.fingerprint == "dvd1-select-reg-x")
            .one()
        )
        assert alias.disc_id == disc.id

    def test_old_client_resubmit_cannot_demote_promoted_disc(
        self, client, db_session: Session, test_user, second_auth_header
    ):
        """An old client re-submitting dvd1-* as its declared primary
        against an already-promoted (dvdread1-* primary) disc must never
        demote it back to dvd1-* primary (D-03 mixed-fleet guarantee,
        zero-fragmentation under a heterogeneous client fleet)."""
        seeded = _seed_promoted_disc(db_session, test_user.id)

        resp = client.post(
            "/v1/disc",
            json={
                **matrix_matching_submit_payload(),
                "fingerprint": "dvd1-already-promoted",
            },
            headers=second_auth_header,
        )
        assert resp.status_code == 200

        db_session.expire_all()
        disc = db_session.query(Disc).filter(Disc.id == seeded["disc_id"]).one()
        assert disc.fingerprint.startswith("dvdread1-"), (
            "an old client's dvd1-primary submission must never demote an "
            "already-promoted disc back to dvd1 primary (D-03 mixed-fleet "
            "guarantee)"
        )


# ---------------------------------------------------------------------------
# Set integration tests (Phase 2)
# ---------------------------------------------------------------------------
class TestDiscSubmitSetIntegration:
    """Disc submission with multi-disc set linking."""

    def test_implicit_set_creation(self, client, auth_header):
        """POST with total_discs > 1 and no disc_set_id auto-creates a set (D-01)."""
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-IMPLICIT-001",
            "total_discs": 4,
            "disc_number": 1,
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201

        get_resp = client.get("/v1/disc/bd-SET-IMPLICIT-001")
        data = get_resp.json()
        assert data["disc_set"] is not None
        assert data["disc_set"]["total_discs"] == 4

    def test_explicit_set_linking(self, client, db_session, auth_header, seeded_disc):
        """POST with valid disc_set_id links disc to existing set (D-03)."""
        from tests.conftest import seed_test_disc_set
        set_id = seed_test_disc_set(db_session, seeded_disc["release_id"], total_discs=3)
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-EXPLICIT-001",
            "disc_set_id": str(set_id),
            "disc_number": 2,
            "total_discs": 3,
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201

        get_resp = client.get("/v1/disc/bd-SET-EXPLICIT-001")
        data = get_resp.json()
        assert data["disc_set"] is not None
        assert data["disc_set"]["id"] == str(set_id)

    def test_disc_number_exceeds_total_returns_422(self, client, db_session, auth_header, seeded_disc):
        """POST with disc_number > total_discs returns 422."""
        from tests.conftest import seed_test_disc_set
        set_id = seed_test_disc_set(db_session, seeded_disc["release_id"], total_discs=2)
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-EXCEED-001",
            "disc_set_id": str(set_id),
            "disc_number": 5,
            "total_discs": 2,
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 422
        assert "exceeds" in resp.json()["message"].lower()

    def test_duplicate_disc_number_returns_409(self, client, db_session, auth_header, seeded_disc):
        """POST with disc_set_id and duplicate disc_number returns 409 (D-08)."""
        from tests.conftest import seed_test_disc_set
        set_id = seed_test_disc_set(db_session, seeded_disc["release_id"], total_discs=3)
        # Submit first disc in slot 1
        payload1 = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-DUP-001",
            "disc_set_id": str(set_id),
            "disc_number": 1,
            "total_discs": 3,
        }
        resp1 = client.post("/v1/disc", json=payload1, headers=auth_header)
        assert resp1.status_code == 201

        # Submit second disc in slot 1 — conflict
        payload2 = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-DUP-002",
            "disc_set_id": str(set_id),
            "disc_number": 1,
            "total_discs": 3,
        }
        resp2 = client.post("/v1/disc", json=payload2, headers=auth_header)
        assert resp2.status_code == 409
        assert "already assigned" in resp2.json()["message"]

    def test_nonexistent_set_returns_404(self, client, auth_header):
        """POST with disc_set_id pointing to non-existent set returns 404."""
        import uuid
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-SET-NOEXIST-001",
            "disc_set_id": str(uuid.uuid4()),
            "disc_number": 1,
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 404
        assert "not found" in resp.json()["message"].lower()

    def test_backward_compat_no_set(self, client, auth_header):
        """POST with total_discs=1 and no disc_set_id creates no set (D-14)."""
        payload = {
            **VALID_PAYLOAD,
            "fingerprint": "bd-NOSET-001",
            "total_discs": 1,
            "disc_number": 1,
        }
        resp = client.post("/v1/disc", json=payload, headers=auth_header)
        assert resp.status_code == 201

        get_resp = client.get("/v1/disc/bd-NOSET-001")
        data = get_resp.json()
        assert data["disc_set"] is None
