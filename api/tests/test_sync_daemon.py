"""Tests for the sync daemon (api/scripts/sync.py).

Uses the existing SQLite conftest fixtures (db_session, _reset_tables).
The sync module is imported via sys.path manipulation since api/scripts/
is not a proper Python package.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# Make scripts/ importable
_scripts_dir = str(Path(__file__).parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import sync as sync_daemon  # noqa: E402

from app.models import (  # noqa: E402
    Disc,
    DiscRelease,
    DiscTitle,
    DiscTrack,
    Release,
    SyncState,
)


# ---------------------------------------------------------------------------
# Helpers — build diff record dicts matching the canonical API shape
# ---------------------------------------------------------------------------

def _make_diff_record(
    fingerprint: str = "bluray-TEST001-main",
    seq_num: int = 1,
    *,
    format: str = "Blu-ray",
    status: str = "verified",
    region_code: str | None = "A",
    upc: str | None = "012345678901",
    disc_label: str | None = "TEST_DISC",
    edition_name: str | None = None,
    disc_number: int = 1,
    total_discs: int = 1,
    release: dict | None = None,
    titles: list | None = None,
) -> dict:
    if release is None:
        release = {
            "title": "Test Movie",
            "year": 2024,
            "content_type": "movie",
            "tmdb_id": 99999,
            "imdb_id": "tt9999999",
            "original_language": "en",
        }
    if titles is None:
        titles = [
            {
                "title_index": 0,
                "is_main_feature": True,
                "title_type": "main_feature",
                "display_name": "Test Movie",
                "duration_secs": 7200,
                "chapter_count": 20,
                "tracks": [
                    {
                        "index": 0,
                        "track_type": "audio",
                        "language": "en",
                        "codec": "truehd",
                        "channels": 8,
                        "is_default": True,
                    },
                    {
                        "index": 0,
                        "track_type": "subtitle",
                        "language": "en",
                        "codec": "pgs",
                        "channels": None,
                        "is_default": False,
                    },
                ],
            }
        ]
    return {
        "type": "disc",
        "seq_num": seq_num,
        "fingerprint": fingerprint,
        "format": format,
        "status": status,
        "region_code": region_code,
        "upc": upc,
        "disc_label": disc_label,
        "edition_name": edition_name,
        "disc_number": disc_number,
        "total_discs": total_discs,
        "release": release,
        "titles": titles,
    }


# ---------------------------------------------------------------------------
# sync_state tests
# ---------------------------------------------------------------------------

class TestGetLastSeq:
    def test_empty_returns_zero(self, db_session):
        """Empty sync_state table returns 0."""
        assert sync_daemon.get_last_seq(db_session) == 0

    def test_set_and_get(self, db_session):
        """set_last_seq then get_last_seq round-trips the value."""
        sync_daemon.set_last_seq(db_session, 42)
        db_session.commit()
        assert sync_daemon.get_last_seq(db_session) == 42

    def test_set_idempotent(self, db_session):
        """Repeated set_last_seq overwrites without duplicating rows."""
        sync_daemon.set_last_seq(db_session, 10)
        db_session.commit()
        sync_daemon.set_last_seq(db_session, 20)
        db_session.commit()
        assert sync_daemon.get_last_seq(db_session) == 20
        count = db_session.query(SyncState).filter_by(key="last_seq").count()
        assert count == 1


# ---------------------------------------------------------------------------
# apply_diff tests
# ---------------------------------------------------------------------------

class TestApplyDiff:
    def test_creates_disc(self, db_session):
        """A single diff record creates Disc + DiscTitle + DiscTrack + Release."""
        record = _make_diff_record()
        count = sync_daemon.apply_diff(db_session, [record])
        db_session.commit()

        assert count == 1
        disc = db_session.query(Disc).filter_by(fingerprint="bluray-TEST001-main").one()
        assert disc.format == "Blu-ray"
        assert disc.status == "verified"
        assert disc.seq_num == 1

        # Release created and linked
        releases = disc.releases
        assert len(releases) == 1
        assert releases[0].title == "Test Movie"
        assert releases[0].tmdb_id == 99999

        # Title + tracks
        titles = db_session.query(DiscTitle).filter_by(disc_id=disc.id).all()
        assert len(titles) == 1
        assert titles[0].is_main_feature is True

        tracks = db_session.query(DiscTrack).filter_by(disc_title_id=titles[0].id).all()
        assert len(tracks) == 2

    def test_upserts_disc(self, db_session):
        """Same fingerprint applied twice updates scalar fields, doesn't duplicate titles."""
        record1 = _make_diff_record(seq_num=1, status="unverified")
        sync_daemon.apply_diff(db_session, [record1])
        db_session.commit()

        record2 = _make_diff_record(seq_num=2, status="verified")
        sync_daemon.apply_diff(db_session, [record2])
        db_session.commit()

        discs = db_session.query(Disc).filter_by(fingerprint="bluray-TEST001-main").all()
        assert len(discs) == 1
        assert discs[0].status == "verified"
        assert discs[0].seq_num == 2

        # Titles should not be duplicated
        titles = db_session.query(DiscTitle).filter_by(disc_id=discs[0].id).all()
        assert len(titles) == 1

    def test_copies_seq_num(self, db_session):
        """seq_num in DB matches seq_num from diff record verbatim."""
        record = _make_diff_record(seq_num=777)
        sync_daemon.apply_diff(db_session, [record])
        db_session.commit()

        disc = db_session.query(Disc).filter_by(fingerprint="bluray-TEST001-main").one()
        assert disc.seq_num == 777


# ---------------------------------------------------------------------------
# sync_once tests
# ---------------------------------------------------------------------------

def _mock_response(json_data, status_code=200):
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


class TestSyncOnce:
    def test_up_to_date(self, db_session):
        """When head_seq == last_seq, no diff call is made, returns 0."""
        # Seed last_seq=5
        sync_daemon.set_last_seq(db_session, 5)
        db_session.commit()

        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.return_value = _mock_response({"seq": 5, "timestamp": "2025-01-01T00:00:00Z"})

        result = sync_daemon.sync_once("http://fake", db_session, client=mock_client)

        assert result == 0
        # Only head was called, no diff call
        mock_client.get.assert_called_once_with("http://fake/v1/sync/head")

    def test_applies_records(self, db_session):
        """Mocked head returns seq=5, diff returns 2 records; after sync, 2 discs in DB and last_seq=5."""
        mock_client = MagicMock(spec=httpx.Client)

        head_resp = _mock_response({"seq": 5, "timestamp": "2025-01-01T00:00:00Z"})
        diff_resp = _mock_response({
            "records": [
                _make_diff_record("fp-001", seq_num=4),
                _make_diff_record("fp-002", seq_num=5),
            ],
            "next_since": 5,
            "has_more": False,
        })

        mock_client.get.side_effect = [head_resp, diff_resp]

        result = sync_daemon.sync_once("http://fake", db_session, client=mock_client)

        assert result == 2
        assert db_session.query(Disc).count() == 2
        assert sync_daemon.get_last_seq(db_session) == 5

    def test_paginates(self, db_session):
        """First diff page has_more=True, second has_more=False; both pages applied."""
        mock_client = MagicMock(spec=httpx.Client)

        head_resp = _mock_response({"seq": 10, "timestamp": "2025-01-01T00:00:00Z"})
        page1_resp = _mock_response({
            "records": [_make_diff_record("fp-001", seq_num=5)],
            "next_since": 5,
            "has_more": True,
        })
        page2_resp = _mock_response({
            "records": [_make_diff_record("fp-002", seq_num=10)],
            "next_since": 10,
            "has_more": False,
        })

        mock_client.get.side_effect = [head_resp, page1_resp, page2_resp]

        result = sync_daemon.sync_once("http://fake", db_session, client=mock_client)

        assert result == 2
        assert db_session.query(Disc).count() == 2
        assert sync_daemon.get_last_seq(db_session) == 10

        # Verify 3 calls: head + 2 diff pages
        assert mock_client.get.call_count == 3

    def test_network_error_propagates(self, db_session):
        """httpx.HTTPError raised on head call propagates (caller handles backoff)."""
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(httpx.HTTPError):
            sync_daemon.sync_once("http://fake", db_session, client=mock_client)
