"""Foundation tests — middleware, schemas, test infrastructure.

Verifies:
  - Request-ID middleware adds X-Request-ID to every response
  - Request-ID is a valid UUID4
  - Pydantic schemas instantiate with correct defaults
  - TestClient + SQLite dependency override works
  - seed_test_disc populates realistic data
  - Negative-case schema validation (empty fingerprint, negative disc_number)
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import (
    STATUS_CONFIDENCE,
    DiscLookupResponse,
    DiscSubmitRequest,
    DiscSubmitResponse,
    ErrorResponse,
    ReleaseCreate,
    ReleaseResponse,
    SearchResponse,
    SearchResultRelease,
    TitleCreate,
    TitleResponse,
    TrackCreate,
    TrackResponse,
)
from tests.conftest import seed_test_disc


# ---------------------------------------------------------------------------
# Middleware tests
# ---------------------------------------------------------------------------
class TestRequestIdMiddleware:
    def test_health_has_request_id_header(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers

    def test_request_id_is_valid_uuid(self, client):
        resp = client.get("/health")
        rid = resp.headers["X-Request-ID"]
        parsed = uuid.UUID(rid)  # raises if invalid
        assert str(parsed) == rid

    def test_each_request_gets_unique_id(self, client):
        ids = {client.get("/health").headers["X-Request-ID"] for _ in range(5)}
        assert len(ids) == 5


# ---------------------------------------------------------------------------
# Schema instantiation tests
# ---------------------------------------------------------------------------
class TestSchemaInstantiation:
    def test_track_response_defaults(self):
        t = TrackResponse(index=0)
        assert t.is_default is False
        assert t.language is None

    def test_title_response_empty_tracks(self):
        t = TitleResponse(title_index=1)
        assert t.audio_tracks == []
        assert t.subtitle_tracks == []

    def test_release_response_required_fields(self):
        r = ReleaseResponse(title="Test", content_type="movie")
        assert r.year is None
        assert r.tmdb_id is None

    def test_disc_lookup_response_full(self):
        d = DiscLookupResponse(
            request_id="abc",
            fingerprint="fp-123",
            format="DVD",
            status="verified",
            confidence="high",
            release=ReleaseResponse(title="Test", content_type="movie"),
            titles=[
                TitleResponse(
                    title_index=1,
                    audio_tracks=[TrackResponse(index=0, language="en")],
                )
            ],
        )
        assert d.release is not None
        assert len(d.titles) == 1
        assert d.titles[0].audio_tracks[0].language == "en"

    def test_submit_response(self):
        s = DiscSubmitResponse(
            request_id="r", fingerprint="fp", status="created", message="ok"
        )
        assert s.status == "created"

    def test_search_response_defaults(self):
        s = SearchResponse(request_id="r")
        assert s.results == []
        assert s.total_results == 0

    def test_search_result_release(self):
        r = SearchResultRelease(
            id="abc", title="Matrix", content_type="movie", disc_count=2
        )
        assert r.disc_count == 2

    def test_error_response(self):
        e = ErrorResponse(request_id="r", error="not_found", message="nope")
        assert e.error == "not_found"

    def test_status_confidence_mapping(self):
        assert STATUS_CONFIDENCE["verified"] == "high"
        assert STATUS_CONFIDENCE["unverified"] == "medium"
        assert STATUS_CONFIDENCE["disputed"] == "medium"


# ---------------------------------------------------------------------------
# Schema creation / request models
# ---------------------------------------------------------------------------
class TestCreateSchemas:
    def test_track_create_valid(self):
        t = TrackCreate(track_index=0, language_code="en", codec="ac3", channels=6)
        assert t.is_default is False

    def test_title_create_with_tracks(self):
        t = TitleCreate(
            title_index=1,
            title_type="main_feature",
            audio_tracks=[TrackCreate(track_index=0)],
        )
        assert len(t.audio_tracks) == 1

    def test_release_create_minimal(self):
        r = ReleaseCreate(title="Test", content_type="movie")
        assert r.original_language is None

    def test_disc_submit_request_full(self):
        d = DiscSubmitRequest(
            fingerprint="fp-123",
            format="DVD",
            release=ReleaseCreate(title="Test", content_type="movie"),
            titles=[
                TitleCreate(
                    title_index=1,
                    audio_tracks=[TrackCreate(track_index=0)],
                )
            ],
        )
        assert d.disc_number == 1

    def test_disc_submit_request_custom_disc_number(self):
        d = DiscSubmitRequest(
            fingerprint="fp",
            format="BD",
            disc_number=3,
            total_discs=5,
            release=ReleaseCreate(title="X", content_type="tv"),
        )
        assert d.disc_number == 3
        assert d.total_discs == 5


# ---------------------------------------------------------------------------
# Negative / boundary tests (Q7)
# ---------------------------------------------------------------------------
class TestSchemaNegativeCases:
    def test_empty_fingerprint_rejected(self):
        with pytest.raises(ValidationError):
            DiscSubmitRequest(
                fingerprint="",
                format="DVD",
                release=ReleaseCreate(title="X", content_type="movie"),
            )

    def test_negative_disc_number_rejected(self):
        with pytest.raises(ValidationError):
            DiscSubmitRequest(
                fingerprint="fp",
                format="DVD",
                disc_number=-1,
                release=ReleaseCreate(title="X", content_type="movie"),
            )

    def test_negative_track_index_rejected(self):
        with pytest.raises(ValidationError):
            TrackCreate(track_index=-1)

    def test_empty_release_title_rejected(self):
        with pytest.raises(ValidationError):
            ReleaseCreate(title="", content_type="movie")

    def test_empty_format_rejected(self):
        with pytest.raises(ValidationError):
            DiscSubmitRequest(
                fingerprint="fp",
                format="",
                release=ReleaseCreate(title="X", content_type="movie"),
            )


# ---------------------------------------------------------------------------
# Test infrastructure self-check
# ---------------------------------------------------------------------------
class TestInfrastructure:
    def test_client_works(self, client):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}

    def test_seed_disc(self, db_session):
        ids = seed_test_disc(db_session)
        assert "disc_id" in ids
        assert "release_id" in ids
        assert "title_id" in ids
        assert "audio_track_id" in ids
        assert "subtitle_track_id" in ids

    def test_seed_disc_data_readable(self, db_session):
        from app.models import Disc

        ids = seed_test_disc(db_session)
        disc = db_session.get(Disc, ids["disc_id"])
        assert disc is not None
        assert disc.fingerprint == "dvd-ABC123-main"
        assert disc.status == "verified"
        assert len(disc.titles) == 1
        assert len(disc.titles[0].tracks) == 2
        assert len(disc.releases) == 1
        assert disc.releases[0].title == "The Matrix"
