"""Tests for sync feed endpoints — GET /v1/sync/head, /v1/sync/diff, /v1/sync/snapshot."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, GlobalSeq, Release, SyncState


# ---------------------------------------------------------------------------
# Helper — seed a disc with seq_num for sync tests
# ---------------------------------------------------------------------------
def _seed_disc_with_seq(
    db: Session,
    fingerprint: str,
    seq_num: int,
    *,
    title: str = "Test Movie",
    year: int = 2020,
    with_titles: bool = False,
    with_release: bool = True,
) -> Disc:
    """Seed a disc with a specific seq_num for sync diff testing."""
    disc = Disc(
        fingerprint=fingerprint,
        format="DVD",
        status="unverified",
        seq_num=seq_num,
    )
    db.add(disc)
    db.flush()

    if with_release:
        release = Release(
            title=title,
            year=year,
            content_type="movie",
            tmdb_id=None,
        )
        db.add(release)
        db.flush()

        db.execute(
            DiscRelease.__table__.insert().values(
                disc_id=disc.id, release_id=release.id
            )
        )

    if with_titles:
        t = DiscTitle(
            disc_id=disc.id,
            title_index=1,
            title_type="main_feature",
            duration_secs=7200,
            chapter_count=20,
            is_main_feature=True,
            display_name="Main Feature",
        )
        db.add(t)
        db.flush()

        db.add(
            DiscTrack(
                disc_title_id=t.id,
                track_type="audio",
                track_index=0,
                language_code="en",
                codec="ac3",
                channels=6,
                is_default=True,
            )
        )
        db.add(
            DiscTrack(
                disc_title_id=t.id,
                track_type="subtitle",
                track_index=0,
                language_code="es",
                codec="vobsub",
                is_default=False,
            )
        )

    db.commit()
    db.refresh(disc)
    return disc


def _set_global_seq(db: Session, value: int) -> None:
    """Set the global sequence counter to a specific value."""
    row = db.query(GlobalSeq).filter(GlobalSeq.id == 1).one()
    row.current_seq = value
    db.commit()


# ---------------------------------------------------------------------------
# /v1/sync/head tests
# ---------------------------------------------------------------------------
class TestSyncHead:
    def test_sync_head_returns_current_seq(self, client, db_session):
        """Seed GlobalSeq to a known value and verify the response."""
        _set_global_seq(db_session, 42)

        resp = client.get("/v1/sync/head")
        assert resp.status_code == 200

        data = resp.json()
        assert data["seq"] == 42
        assert "timestamp" in data
        # Verify timestamp is valid ISO 8601
        datetime.fromisoformat(data["timestamp"])

    def test_sync_head_empty_db(self, client):
        """Fresh DB with GlobalSeq seeded at 0 returns seq 0."""
        resp = client.get("/v1/sync/head")
        assert resp.status_code == 200

        data = resp.json()
        assert data["seq"] == 0


# ---------------------------------------------------------------------------
# /v1/sync/diff tests
# ---------------------------------------------------------------------------
class TestSyncDiff:
    def test_sync_diff_returns_records_after_since(self, client, db_session):
        """Submit 3 discs with sequential seq_nums, diff since=0 returns all 3."""
        for i in range(1, 4):
            _seed_disc_with_seq(db_session, f"fp-{i}", seq_num=i)

        resp = client.get("/v1/sync/diff", params={"since": 0})
        assert resp.status_code == 200

        data = resp.json()
        assert len(data["records"]) == 3
        # Verify ascending seq order
        seqs = [r["seq_num"] for r in data["records"]]
        assert seqs == [1, 2, 3]
        # All records should be type "disc"
        assert all(r["type"] == "disc" for r in data["records"])

    def test_sync_diff_pagination(self, client, db_session):
        """Submit 5 discs, request limit=2, verify pagination mechanics."""
        for i in range(1, 6):
            _seed_disc_with_seq(db_session, f"fp-page-{i}", seq_num=i)

        # First page
        resp = client.get("/v1/sync/diff", params={"since": 0, "limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["records"]) == 2
        assert data["has_more"] is True
        assert data["next_since"] == 2

        # Second page
        resp2 = client.get(
            "/v1/sync/diff", params={"since": data["next_since"], "limit": 2}
        )
        data2 = resp2.json()
        assert len(data2["records"]) == 2
        assert data2["has_more"] is True
        assert data2["next_since"] == 4

        # Third page — only 1 record left
        resp3 = client.get(
            "/v1/sync/diff", params={"since": data2["next_since"], "limit": 2}
        )
        data3 = resp3.json()
        assert len(data3["records"]) == 1
        assert data3["has_more"] is False
        assert data3["next_since"] == 5

    def test_sync_diff_no_new_records(self, client, db_session):
        """since >= current head returns empty with has_more=false."""
        _seed_disc_with_seq(db_session, "fp-only", seq_num=5)

        resp = client.get("/v1/sync/diff", params={"since": 5})
        assert resp.status_code == 200

        data = resp.json()
        assert data["records"] == []
        assert data["has_more"] is False
        assert data["next_since"] == 5  # echoes since when empty

    def test_sync_diff_includes_release_data(self, client, db_session):
        """Verify release title/year present in diff records."""
        _seed_disc_with_seq(
            db_session,
            "fp-rel",
            seq_num=1,
            title="The Matrix",
            year=1999,
        )

        resp = client.get("/v1/sync/diff", params={"since": 0})
        data = resp.json()

        assert len(data["records"]) == 1
        rec = data["records"][0]
        assert rec["release"] is not None
        assert rec["release"]["title"] == "The Matrix"
        assert rec["release"]["year"] == 1999
        assert rec["release"]["content_type"] == "movie"

    def test_sync_diff_includes_titles_and_tracks(self, client, db_session):
        """Verify titles and tracks are fully populated in diff records."""
        _seed_disc_with_seq(
            db_session,
            "fp-full",
            seq_num=1,
            with_titles=True,
        )

        resp = client.get("/v1/sync/diff", params={"since": 0})
        data = resp.json()

        rec = data["records"][0]
        assert len(rec["titles"]) == 1
        title = rec["titles"][0]
        assert title["title_index"] == 1
        assert title["is_main_feature"] is True
        assert title["duration_secs"] == 7200
        assert title["chapter_count"] == 20
        # Should have audio + subtitle tracks
        assert len(title["tracks"]) == 2
        track_types = {t["track_type"] for t in title["tracks"]}
        assert track_types == {"audio", "subtitle"}

    def test_sync_diff_since_required(self, client):
        """Missing since param returns 422 validation error."""
        resp = client.get("/v1/sync/diff")
        assert resp.status_code == 422

    def test_sync_diff_limit_capped(self, client, db_session):
        """limit=9999 is silently capped to 1000 (server doesn't error)."""
        _seed_disc_with_seq(db_session, "fp-cap", seq_num=1)

        resp = client.get("/v1/sync/diff", params={"since": 0, "limit": 9999})
        assert resp.status_code == 200
        # The response is valid — the server capped the limit internally
        data = resp.json()
        assert len(data["records"]) == 1

    def test_sync_diff_disc_fields_complete(self, client, db_session):
        """Verify all disc fields are present for mirror reconstruction."""
        disc = Disc(
            fingerprint="fp-complete",
            format="Blu-ray",
            status="verified",
            region_code="A",
            upc="123456789012",
            disc_label="MATRIX_BD",
            edition_name="4K UHD",
            disc_number=2,
            total_discs=3,
            seq_num=1,
        )
        db_session.add(disc)
        db_session.commit()

        resp = client.get("/v1/sync/diff", params={"since": 0})
        data = resp.json()

        rec = data["records"][0]
        assert rec["fingerprint"] == "fp-complete"
        assert rec["format"] == "Blu-ray"
        assert rec["status"] == "verified"
        assert rec["region_code"] == "A"
        assert rec["upc"] == "123456789012"
        assert rec["disc_label"] == "MATRIX_BD"
        assert rec["edition_name"] == "4K UHD"
        assert rec["disc_number"] == 2
        assert rec["total_discs"] == 3


# ---------------------------------------------------------------------------
# Helper — seed snapshot metadata into sync_state
# ---------------------------------------------------------------------------
def _seed_snapshot_metadata(db: Session, **overrides) -> dict[str, str]:
    """Seed all five snapshot metadata keys into sync_state. Returns the dict."""
    defaults = {
        "snapshot_url": "https://releases.oviddb.org/dumps/ovid-20260401.ndjson.gz",
        "snapshot_seq": "100",
        "snapshot_size_bytes": "524288",
        "snapshot_record_count": "42",
        "snapshot_sha256": "abc123def456789",
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        db.add(SyncState(key=key, value=value))
    db.commit()
    return defaults


# ---------------------------------------------------------------------------
# /v1/sync/snapshot tests
# ---------------------------------------------------------------------------
class TestSyncSnapshot:
    def test_snapshot_no_metadata_returns_404(self, client):
        """No snapshot metadata in sync_state returns 404."""
        resp = client.get("/v1/sync/snapshot")
        assert resp.status_code == 404
        data = resp.json()
        assert "No snapshot available" in data["detail"]

    def test_snapshot_returns_valid_response(self, client, db_session):
        """Seed all five snapshot keys and verify the response schema."""
        meta = _seed_snapshot_metadata(db_session)

        resp = client.get("/v1/sync/snapshot")
        assert resp.status_code == 200

        data = resp.json()
        assert data["snapshot_seq"] == int(meta["snapshot_seq"])
        assert data["url"] == meta["snapshot_url"]
        assert data["size_bytes"] == int(meta["snapshot_size_bytes"])
        assert data["record_count"] == int(meta["snapshot_record_count"])
        assert data["sha256"] == meta["snapshot_sha256"]

    def test_snapshot_partial_metadata_returns_404(self, client, db_session):
        """Only some snapshot keys present — should still return 404."""
        # Seed only 2 of the 5 required keys
        db_session.add(SyncState(key="snapshot_url", value="https://example.com/dump.gz"))
        db_session.add(SyncState(key="snapshot_seq", value="50"))
        db_session.commit()

        resp = client.get("/v1/sync/snapshot")
        assert resp.status_code == 404
        data = resp.json()
        assert "missing keys" in data["detail"]
