"""Tests for normalized disc structure projection."""

from __future__ import annotations

from unittest.mock import MagicMock

from ovid.disc_structure import (
    normalize_bd_disc,
    normalize_dvd_disc,
    to_fingerprint_json,
)
from ovid.ifo_parser import AudioStream, PGCInfo, SubtitleStream, VTSInfo, VMGInfo
from ovid.mpls_parser import (
    ChapterMark,
    MplsHeader,
    MplsPlaylist,
    PlayItem,
    StreamEntry,
)


def _make_dvd_disc() -> MagicMock:
    pgc1 = PGCInfo(duration_seconds=7200, chapter_count=20)
    pgc2 = PGCInfo(duration_seconds=300, chapter_count=1)
    vts1 = VTSInfo(
        pgc_list=[pgc1],
        audio_streams=[
            AudioStream(codec="AC3", language="en", channels=6),
            AudioStream(codec="DTS", language="fr", channels=6),
        ],
        subtitle_streams=[SubtitleStream(language="en")],
    )
    vts2 = VTSInfo(
        pgc_list=[pgc2],
        audio_streams=[AudioStream(codec="AC3", language="en", channels=2)],
        subtitle_streams=[],
    )
    disc = MagicMock()
    disc.fingerprint = "dvd1-abc123"
    disc.source_type = "FolderReader"
    disc.vts_count = 2
    disc.title_count = 3
    disc._vmg = VMGInfo(vts_count=2, title_count=3)
    disc._vts_list = [vts1, vts2]
    return disc


def _playlist(
    *,
    version: str = "0200",
    duration: float,
    audio_streams: list[StreamEntry] | None = None,
    subtitle_streams: list[StreamEntry] | None = None,
    chapter_count: int = 0,
) -> MplsPlaylist:
    return MplsPlaylist(
        header=MplsHeader(version=version, playlist_start=40, mark_start=100),
        play_items=[
            PlayItem(
                clip_id="00001",
                in_time=0,
                out_time=int(duration * 45_000),
                duration_seconds=duration,
            )
        ],
        audio_streams=audio_streams or [],
        subtitle_streams=subtitle_streams or [],
        chapter_marks=[
            ChapterMark(
                mark_type=1,
                play_item_ref=0,
                timestamp=i * 45_000,
                duration_seconds=float(i),
            )
            for i in range(chapter_count)
        ],
    )


def test_normalize_dvd_disc_builds_format_neutral_titles() -> None:
    normalized = normalize_dvd_disc(_make_dvd_disc())

    assert normalized.fingerprint == "dvd1-abc123"
    assert normalized.format == "DVD"
    assert normalized.source_type == "FolderReader"
    assert [title.title_index for title in normalized.titles] == [0, 1]
    assert [title.is_main_feature for title in normalized.titles] == [True, False]
    assert normalized.titles[0].duration_secs == 7200
    assert normalized.titles[0].chapter_count == 20
    assert [track.language_code for track in normalized.titles[0].audio_tracks] == [
        "en",
        "fr",
    ]
    assert normalized.titles[1].audio_tracks[0].channels == 2


def test_normalize_bd_disc_marks_longest_playlist_as_main_feature() -> None:
    bd = MagicMock()
    bd.fingerprint = "bd2-abc123"
    bd.source_type = "BDFolderReader"
    bd.format_type = "bluray"
    bd.tier = 2
    bd.playlists = [
        _playlist(duration=120.0, chapter_count=1),
        _playlist(
            duration=7200.0,
            audio_streams=[
                StreamEntry("audio", "AC3", "eng", 6),
                StreamEntry("audio", "DTS-HD MA", "fra", 8),
            ],
            subtitle_streams=[StreamEntry("subtitle", "PGS", "eng", 0)],
            chapter_count=20,
        ),
    ]

    normalized = normalize_bd_disc(bd)

    assert normalized.format == "Blu-ray"
    assert normalized.tier == 2
    assert [title.duration_secs for title in normalized.titles] == [120.0, 7200.0]
    assert [title.is_main_feature for title in normalized.titles] == [False, True]
    assert normalized.titles[1].chapter_count == 20
    assert normalized.titles[1].audio_tracks[1].codec == "DTS-HD MA"
    assert normalized.titles[1].subtitle_tracks[0].language_code == "eng"


def test_to_fingerprint_json_preserves_current_dvd_shape() -> None:
    normalized = normalize_dvd_disc(_make_dvd_disc())

    result = to_fingerprint_json(normalized)

    assert result["fingerprint"] == "dvd1-abc123"
    assert result["format"] == "DVD"
    assert result["source_type"] == "FolderReader"
    assert result["structure"]["vts_count"] == 2
    assert result["structure"]["title_count"] == 3
    assert result["structure"]["vts"][0]["pgcs"][0]["duration_seconds"] == 7200


def test_to_fingerprint_json_preserves_current_bd_shape() -> None:
    bd = MagicMock()
    bd.fingerprint = "uhd2-abc123"
    bd.source_type = "BDFolderReader"
    bd.format_type = "uhd"
    bd.tier = 2
    bd.playlists = [_playlist(version="0300", duration=120.0, chapter_count=1)]

    result = to_fingerprint_json(normalize_bd_disc(bd))

    assert result["fingerprint"] == "uhd2-abc123"
    assert result["format"] == "UHD"
    assert result["tier"] == 2
    assert result["structure"]["playlists"][0]["version"] == "0300"
    assert result["structure"]["playlists"][0]["play_items"][0]["duration_seconds"] == 120.0
