"""Anti-echo redaction tests for GET /v1/disc/{fingerprint} (D-09/D-11/D-12).

An ``unverified`` disc must return a REDACTED-200: fingerprint, status,
confidence, release, and fingerprint_aliases stay visible, but the submitted
structural payload (titles → chapters / main-feature marker / audio+subtitle
tracks) is WITHHELD until a second contributor independently reproduces it
from a physical disc. This is the read-side half of the two-contributor
anti-echo defense (Phase 2 success criterion 4).

Redaction is scoped to ``status == "unverified"`` ONLY — ``verified`` and
``disputed`` reads are unchanged (RESEARCH Pitfall 6). ``fingerprint_aliases``
stay visible for every status (D-11 — identity strings, not structural
payload). Withholding structure is a no-op for ARM, whose
``_extract_result`` reads only release-level fields + confidence + format
(D-10) — asserted here by confirming those fields survive redaction.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import DiscIdentityAlias
from tests.conftest import seed_test_disc


def _seed_with_alias(db: Session, status: str) -> dict:
    """Seed the Matrix disc at ``status`` and attach one identity alias."""
    ids = seed_test_disc(db, status=status)
    alias = DiscIdentityAlias(
        disc_id=ids["disc_id"],
        fingerprint="dvdread1-alias-first",
        created_at=datetime.now(timezone.utc) + timedelta(seconds=1),
    )
    db.add(alias)
    db.commit()
    return ids


# ---------------------------------------------------------------------------
# Unverified → redacted-200 (structural payload withheld)
# ---------------------------------------------------------------------------
class TestUnverifiedRedaction:
    def test_unverified_titles_withheld(self, client, db_session: Session):
        """Unverified disc → 200 but titles list is EMPTY (D-09)."""
        _seed_with_alias(db_session, status="unverified")
        resp = client.get("/v1/disc/dvd-ABC123-main")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unverified"
        # The whole structural payload is withheld — no titles, so no
        # chapters / main-feature marker / audio+subtitle tracks leak.
        assert data["titles"] == []

    def test_unverified_keeps_release(self, client, db_session: Session):
        """Release (title/year/imdb/tmdb) stays visible on unverified (D-09)."""
        _seed_with_alias(db_session, status="unverified")
        data = client.get("/v1/disc/dvd-ABC123-main").json()
        rel = data["release"]
        assert rel is not None
        assert rel["title"] == "The Matrix"
        assert rel["year"] == 1999
        assert rel["imdb_id"] == "tt0133093"
        assert rel["tmdb_id"] == 603

    def test_unverified_keeps_aliases(self, client, db_session: Session):
        """fingerprint_aliases stay visible on unverified discs (D-11)."""
        _seed_with_alias(db_session, status="unverified")
        data = client.get("/v1/disc/dvd-ABC123-main").json()
        aliases = data["fingerprint_aliases"]
        fingerprints = {a["fingerprint"] for a in aliases}
        # Primary (URL segment) plus the attached alias — both present.
        assert "dvd-ABC123-main" in fingerprints
        assert "dvdread1-alias-first" in fingerprints
        assert any(a["is_primary"] for a in aliases)

    def test_unverified_keeps_confidence_and_request_id(
        self, client, db_session: Session
    ):
        """confidence + request_id survive redaction (envelope preserved)."""
        _seed_with_alias(db_session, status="unverified")
        resp = client.get("/v1/disc/dvd-ABC123-main")
        data = resp.json()
        assert data["confidence"] == "medium"
        assert data["request_id"]
        assert resp.headers["x-request-id"] == data["request_id"]

    def test_unverified_arm_fields_intact_d10(self, client, db_session: Session):
        """D-10 no-op: every field ARM's _extract_result reads is present.

        ARM reads only release.{title,year,imdb_id,tmdb_id}, confidence, and
        format — never titles/tracks — so redaction never regresses ARM.
        """
        _seed_with_alias(db_session, status="unverified")
        data = client.get("/v1/disc/dvd-ABC123-main").json()
        rel = data["release"] or {}
        assert rel.get("title") == "The Matrix"
        assert rel.get("year") == 1999
        assert rel.get("imdb_id") == "tt0133093"
        assert rel.get("tmdb_id") == 603
        assert data.get("confidence") == "medium"
        assert data.get("format") == "DVD"


# ---------------------------------------------------------------------------
# Non-unverified statuses → unchanged (structure NOT redacted)
# ---------------------------------------------------------------------------
class TestRedactionScopedToUnverified:
    def test_verified_titles_populated(self, client, db_session: Session):
        """Verified disc → full structural payload (redaction untouched)."""
        _seed_with_alias(db_session, status="verified")
        data = client.get("/v1/disc/dvd-ABC123-main").json()
        assert data["status"] == "verified"
        assert len(data["titles"]) == 1
        title = data["titles"][0]
        assert title["is_main_feature"] is True
        assert title["chapter_count"] == 39
        assert len(title["audio_tracks"]) == 1
        assert len(title["subtitle_tracks"]) == 1

    def test_disputed_titles_populated(self, client, db_session: Session):
        """Disputed disc → full structural payload (Pitfall 6: only redact
        unverified, never disputed)."""
        _seed_with_alias(db_session, status="disputed")
        data = client.get("/v1/disc/dvd-ABC123-main").json()
        assert data["status"] == "disputed"
        assert len(data["titles"]) == 1
        assert data["titles"][0]["chapter_count"] == 39
