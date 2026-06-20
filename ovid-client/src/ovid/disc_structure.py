"""Format-neutral disc structure projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedTrack:
    """Format-neutral audio or subtitle track."""

    track_index: int
    language_code: str | None
    codec: str | None = None
    channels: int | None = None
    is_default: bool = False


@dataclass(frozen=True)
class NormalizedChapter:
    """Format-neutral chapter."""

    chapter_index: int
    name: str | None = None
    start_time_secs: int | None = None


@dataclass(frozen=True)
class NormalizedTitle:
    """Format-neutral playable title or playlist."""

    title_index: int
    duration_secs: int | float | None
    chapter_count: int | None
    is_main_feature: bool
    title_type: str | None = None
    display_name: str | None = None
    audio_tracks: list[NormalizedTrack] = field(default_factory=list)
    subtitle_tracks: list[NormalizedTrack] = field(default_factory=list)
    chapters: list[NormalizedChapter] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedDiscStructure:
    """Format-neutral structure for a fingerprinted physical disc."""

    fingerprint: str
    format: str
    source_type: str
    titles: list[NormalizedTitle]
    tier: int | None = None
    legacy_structure: dict[str, Any] = field(default_factory=dict)


def normalize_disc_structure(disc: Any) -> NormalizedDiscStructure:
    """Project a DVD ``Disc`` or Blu-ray ``BDDisc`` to normalized structure."""
    from ovid.bd_disc import BDDisc

    if isinstance(disc, BDDisc):
        return normalize_bd_disc(disc)
    return normalize_dvd_disc(disc)


def normalize_dvd_disc(disc: Any) -> NormalizedDiscStructure:
    """Project a DVD disc to normalized structure."""
    titles: list[NormalizedTitle] = []
    title_index = 0
    first_title = True
    vts_list = []

    for vts in disc._vts_list:
        audio_tracks = [
            NormalizedTrack(
                track_index=index,
                language_code=stream.language,
                codec=stream.codec,
                channels=stream.channels,
            )
            for index, stream in enumerate(vts.audio_streams)
        ]
        subtitle_tracks = [
            NormalizedTrack(
                track_index=index,
                language_code=stream.language,
            )
            for index, stream in enumerate(vts.subtitle_streams)
        ]

        pgcs = []
        for pgc in vts.pgc_list:
            pgcs.append({
                "duration_seconds": pgc.duration_seconds,
                "chapter_count": pgc.chapter_count,
            })
            titles.append(
                NormalizedTitle(
                    title_index=title_index,
                    duration_secs=pgc.duration_seconds,
                    chapter_count=pgc.chapter_count,
                    is_main_feature=first_title,
                    audio_tracks=audio_tracks,
                    subtitle_tracks=subtitle_tracks,
                )
            )
            title_index += 1
            first_title = False

        vts_list.append({
            "pgcs": pgcs,
            "audio_streams": [
                {
                    "codec": track.codec,
                    "language": track.language_code,
                    "channels": track.channels,
                }
                for track in audio_tracks
            ],
            "subtitle_streams": [
                {"language": track.language_code}
                for track in subtitle_tracks
            ],
        })

    return NormalizedDiscStructure(
        fingerprint=disc.fingerprint,
        format="DVD",
        source_type=disc.source_type,
        titles=titles,
        legacy_structure={
            "vts_count": disc.vts_count,
            "title_count": disc.title_count,
            "vts": vts_list,
        },
    )


def normalize_bd_disc(bd_disc: Any) -> NormalizedDiscStructure:
    """Project a Blu-ray or UHD disc to normalized structure."""
    disc_format = "UHD" if bd_disc.format_type == "uhd" else "Blu-ray"
    longest_index = _longest_playlist_index(bd_disc.playlists)
    titles: list[NormalizedTitle] = []
    playlists = []

    for title_index, playlist in enumerate(bd_disc.playlists):
        total_duration = sum(item.duration_seconds for item in playlist.play_items)
        chapter_count = len([
            mark for mark in playlist.chapter_marks
            if mark.mark_type == 1
        ])
        audio_tracks = [
            NormalizedTrack(
                track_index=index,
                language_code=stream.language,
                codec=stream.codec,
                channels=stream.channels,
            )
            for index, stream in enumerate(playlist.audio_streams)
        ]
        subtitle_tracks = [
            NormalizedTrack(
                track_index=index,
                language_code=stream.language,
                codec=stream.codec,
            )
            for index, stream in enumerate(playlist.subtitle_streams)
        ]

        titles.append(
            NormalizedTitle(
                title_index=title_index,
                duration_secs=total_duration,
                chapter_count=chapter_count,
                is_main_feature=title_index == longest_index,
                audio_tracks=audio_tracks,
                subtitle_tracks=subtitle_tracks,
            )
        )
        playlists.append(_legacy_playlist_structure(playlist))

    return NormalizedDiscStructure(
        fingerprint=bd_disc.fingerprint,
        format=disc_format,
        source_type=bd_disc.source_type,
        titles=titles,
        tier=bd_disc.tier,
        legacy_structure={"playlists": playlists},
    )


def to_fingerprint_json(structure: NormalizedDiscStructure) -> dict[str, Any]:
    """Build the current ``ovid fingerprint --json`` output shape."""
    result: dict[str, Any] = {
        "fingerprint": structure.fingerprint,
        "format": structure.format,
        "source_type": structure.source_type,
        "structure": structure.legacy_structure,
    }
    if structure.tier is not None:
        result["tier"] = structure.tier
    return result


def _longest_playlist_index(playlists: list[Any]) -> int:
    longest_index = 0
    longest_duration = 0.0
    for index, playlist in enumerate(playlists):
        duration = sum(item.duration_seconds for item in playlist.play_items)
        if duration > longest_duration:
            longest_duration = duration
            longest_index = index
    return longest_index


def _legacy_playlist_structure(playlist: Any) -> dict[str, Any]:
    return {
        "version": playlist.header.version,
        "play_items": [
            {
                "clip_id": item.clip_id,
                "in_time": item.in_time,
                "out_time": item.out_time,
                "duration_seconds": item.duration_seconds,
            }
            for item in playlist.play_items
        ],
        "audio_streams": [
            {
                "codec": stream.codec,
                "language": stream.language,
                "channels": stream.channels,
            }
            for stream in playlist.audio_streams
        ],
        "subtitle_streams": [
            {
                "codec": stream.codec,
                "language": stream.language,
            }
            for stream in playlist.subtitle_streams
        ],
        "chapters": [
            {
                "mark_type": chapter.mark_type,
                "play_item_ref": chapter.play_item_ref,
                "timestamp": chapter.timestamp,
                "duration_seconds": chapter.duration_seconds,
            }
            for chapter in playlist.chapter_marks
        ],
    }
