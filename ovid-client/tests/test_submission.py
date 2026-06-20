"""Tests for submission payload construction."""

from __future__ import annotations

from ovid.disc_structure import (
    NormalizedDiscStructure,
    NormalizedTitle,
    NormalizedTrack,
)
from ovid.submission import ContributorMetadata, build_submit_payload


def test_build_submit_payload_from_normalized_disc_structure() -> None:
    structure = NormalizedDiscStructure(
        fingerprint="bd2-abc123",
        format="Blu-ray",
        source_type="BDFolderReader",
        tier=2,
        titles=[
            NormalizedTitle(
                title_index=0,
                duration_secs=7200.0,
                chapter_count=20,
                is_main_feature=True,
                audio_tracks=[
                    NormalizedTrack(
                        track_index=0,
                        language_code="eng",
                        codec="AC3",
                        channels=6,
                    )
                ],
                subtitle_tracks=[
                    NormalizedTrack(
                        track_index=0,
                        language_code="spa",
                        codec="PGS",
                    )
                ],
            )
        ],
    )
    metadata = ContributorMetadata(
        title="Test Movie",
        year=2024,
        tmdb_id=12345,
        imdb_id="tt9999999",
        edition_name="Collector's Edition",
        disc_number=1,
        total_discs=2,
    )

    payload = build_submit_payload(structure, metadata)

    assert payload["fingerprint"] == "bd2-abc123"
    assert payload["format"] == "Blu-ray"
    assert payload["disc_number"] == 1
    assert payload["total_discs"] == 2
    assert payload["edition_name"] == "Collector's Edition"
    assert payload["release"] == {
        "title": "Test Movie",
        "year": 2024,
        "content_type": "movie",
        "tmdb_id": 12345,
        "imdb_id": "tt9999999",
    }
    assert payload["titles"][0]["is_main_feature"] is True
    assert payload["titles"][0]["audio_tracks"][0]["language_code"] == "eng"
    assert payload["titles"][0]["subtitle_tracks"][0]["language_code"] == "spa"


def test_build_submit_payload_omits_empty_optional_fields() -> None:
    structure = NormalizedDiscStructure(
        fingerprint="dvd1-abc123",
        format="DVD",
        source_type="FolderReader",
        titles=[
            NormalizedTitle(
                title_index=0,
                duration_secs=120,
                chapter_count=3,
                is_main_feature=True,
            )
        ],
    )
    metadata = ContributorMetadata(
        title="DVD Movie",
        year=None,
        tmdb_id=None,
        imdb_id="",
        edition_name=None,
        disc_number=1,
        total_discs=1,
    )

    payload = build_submit_payload(structure, metadata)

    assert "edition_name" not in payload
    assert "tmdb_id" not in payload["release"]
    assert "imdb_id" not in payload["release"]
