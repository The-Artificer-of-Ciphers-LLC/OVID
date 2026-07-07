"""Sync feed utilities — monotonic sequence counter and helpers.

The global sequence counter lives in the ``global_seq`` single-row table
(enforced by CHECK id = 1).  ``next_seq()`` atomically increments it
and returns the new value, suitable for stamping Disc/Release/DiscSet
records so downstream mirrors can request "changes since seq N".

On PostgreSQL the row is locked with ``FOR UPDATE`` to serialise
concurrent writers.  On SQLite ``with_for_update()`` is silently
ignored by SQLAlchemy's dialect compiler, and SQLite serialises all
writes to a single connection anyway, so test-harness correctness
is preserved.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Disc, DiscTitle, DiscTrack, GlobalSeq
from app.schemas import (
    SyncDiffRecord,
    SyncReleaseRecord,
    SyncTitleRecord,
    SyncTrackRecord,
)

logger = logging.getLogger(__name__)


def next_seq(db: Session) -> int:
    """Atomically increment the global sequence counter and return the new value.

    Must be called inside an existing transaction (the caller's request
    transaction).  The counter row is locked with ``FOR UPDATE`` on
    PostgreSQL; SQLAlchemy omits the clause on SQLite automatically.

    Returns:
        The new (post-increment) sequence number.

    Raises:
        RuntimeError: If the ``global_seq`` row is missing (DB not seeded).
    """
    # Use SQLAlchemy's with_for_update() — on PostgreSQL it emits
    # "SELECT ... FOR UPDATE"; on SQLite the clause is omitted by
    # the dialect compiler (see D023).
    stmt = (
        select(GlobalSeq)
        .where(GlobalSeq.id == 1)
        .with_for_update()
    )
    row = db.execute(stmt).scalar_one_or_none()

    if row is None:
        raise RuntimeError(
            "global_seq row missing — run the seed migration or call "
            "_seed_global_seq() in tests"
        )

    row.current_seq += 1
    db.flush()

    logger.debug("sync_seq_incremented new_seq=%d", row.current_seq)
    return row.current_seq


# ---------------------------------------------------------------------------
# Sync record builders — used by /v1/sync/diff route and dump_cc0.py script
# ---------------------------------------------------------------------------

def build_sync_track(track: DiscTrack) -> SyncTrackRecord:
    return SyncTrackRecord(
        index=track.track_index,
        track_type=track.track_type,
        language=track.language_code,
        codec=track.codec,
        channels=track.channels,
        is_default=track.is_default,
    )


def build_sync_title(title: DiscTitle) -> SyncTitleRecord:
    tracks = [build_sync_track(t) for t in title.tracks]
    return SyncTitleRecord(
        title_index=title.title_index,
        is_main_feature=title.is_main_feature,
        title_type=title.title_type,
        display_name=title.display_name,
        duration_secs=title.duration_secs,
        chapter_count=title.chapter_count,
        tracks=tracks,
    )


def build_sync_disc(disc: Disc) -> SyncDiffRecord:
    """Build a full sync record for a disc, including nested titles/tracks/release."""
    titles = [build_sync_title(t) for t in disc.titles]

    release_resp = None
    if disc.releases:
        rel = disc.releases[0]
        release_resp = SyncReleaseRecord(
            title=rel.title,
            year=rel.year,
            content_type=rel.content_type,
            tmdb_id=rel.tmdb_id,
            imdb_id=rel.imdb_id,
            original_language=rel.original_language,
        )

    return SyncDiffRecord(
        type="disc",
        seq_num=disc.seq_num,
        fingerprint=disc.fingerprint,
        format=disc.format,
        status=disc.status,
        region_code=disc.region_code,
        upc=disc.upc,
        disc_label=disc.disc_label,
        edition_name=disc.edition_name,
        disc_number=disc.disc_number,
        total_discs=disc.total_discs,
        disc_set_id=str(disc.disc_set_id) if disc.disc_set_id else None,
        titles=titles,
        release=release_resp,
    )
