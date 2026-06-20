"""Build API submission payloads from normalized disc structure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ovid.disc_structure import NormalizedDiscStructure, NormalizedTitle


@dataclass(frozen=True)
class ContributorMetadata:
    """Contributor-supplied metadata for a disc submission."""

    title: str
    year: int | None
    tmdb_id: int | None
    imdb_id: str
    edition_name: str | None
    disc_number: int
    total_discs: int
    content_type: str = "movie"


def build_submit_payload(
    structure: NormalizedDiscStructure,
    metadata: ContributorMetadata,
) -> dict[str, Any]:
    """Build the POST /v1/disc payload."""
    release: dict[str, Any] = {
        "title": metadata.title,
        "year": metadata.year,
        "content_type": metadata.content_type,
    }
    if metadata.tmdb_id is not None:
        release["tmdb_id"] = metadata.tmdb_id
    if metadata.imdb_id:
        release["imdb_id"] = metadata.imdb_id

    payload: dict[str, Any] = {
        "fingerprint": structure.fingerprint,
        "format": structure.format,
        "release": release,
        "titles": [_title_payload(title) for title in structure.titles],
        "disc_number": metadata.disc_number,
        "total_discs": metadata.total_discs,
    }
    if metadata.edition_name:
        payload["edition_name"] = metadata.edition_name
    return payload


def _title_payload(title: NormalizedTitle) -> dict[str, Any]:
    result: dict[str, Any] = {
        "title_index": title.title_index,
        "is_main_feature": title.is_main_feature,
        "duration_secs": title.duration_secs,
        "chapter_count": title.chapter_count,
        "audio_tracks": [
            {
                "track_index": track.track_index,
                "language_code": track.language_code,
                "codec": track.codec,
                "channels": track.channels,
            }
            for track in title.audio_tracks
        ],
        "subtitle_tracks": [
            {
                "track_index": track.track_index,
                "language_code": track.language_code,
            }
            for track in title.subtitle_tracks
        ],
    }
    if title.title_type is not None:
        result["title_type"] = title.title_type
    if title.display_name is not None:
        result["display_name"] = title.display_name
    if title.chapters:
        result["chapters"] = [
            {
                "chapter_index": chapter.chapter_index,
                "name": chapter.name,
                "start_time_secs": chapter.start_time_secs,
            }
            for chapter in title.chapters
        ]
    return result
