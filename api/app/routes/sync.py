"""Sync feed endpoints — /v1/sync router.

Provides two unauthenticated read endpoints for downstream mirrors:

- ``GET /v1/sync/head`` — current global sequence number and timestamp
- ``GET /v1/sync/diff`` — paginated disc records changed since a given seq
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, subqueryload

from app.deps import get_db
from app.models import Disc, DiscTitle, DiscTrack, GlobalSeq
from app.rate_limit import _dynamic_limit, limiter
from app.schemas import (
    SyncDiffRecord,
    SyncDiffResponse,
    SyncHeadResponse,
    SyncReleaseRecord,
    SyncTitleRecord,
    SyncTrackRecord,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sync", tags=["sync"])

# Maximum records per diff page — clamped server-side regardless of request.
MAX_DIFF_LIMIT = 1000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_sync_track(track: DiscTrack) -> SyncTrackRecord:
    return SyncTrackRecord(
        index=track.track_index,
        track_type=track.track_type,
        language=track.language_code,
        codec=track.codec,
        channels=track.channels,
        is_default=track.is_default,
    )


def _build_sync_title(title: DiscTitle) -> SyncTitleRecord:
    tracks = [_build_sync_track(t) for t in title.tracks]
    return SyncTitleRecord(
        title_index=title.title_index,
        is_main_feature=title.is_main_feature,
        title_type=title.title_type,
        display_name=title.display_name,
        duration_secs=title.duration_secs,
        chapter_count=title.chapter_count,
        tracks=tracks,
    )


def _build_sync_disc(disc: Disc) -> SyncDiffRecord:
    """Build a full sync record for a disc, including nested titles/tracks/release."""
    titles = [_build_sync_title(t) for t in disc.titles]

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
        titles=titles,
        release=release_resp,
    )


# ---------------------------------------------------------------------------
# GET /v1/sync/head
# ---------------------------------------------------------------------------
@router.get("/head", response_model=SyncHeadResponse)
@limiter.limit(_dynamic_limit)
def sync_head(request: Request, db: Session = Depends(get_db)) -> SyncHeadResponse:
    """Return the current global sequence number and server timestamp.

    Mirrors poll this to decide whether they need to call ``/diff``.
    No authentication required.
    """
    row = db.execute(select(GlobalSeq).where(GlobalSeq.id == 1)).scalar_one_or_none()
    seq = row.current_seq if row is not None else 0
    now = datetime.now(timezone.utc).isoformat()

    return SyncHeadResponse(seq=seq, timestamp=now)


# ---------------------------------------------------------------------------
# GET /v1/sync/diff
# ---------------------------------------------------------------------------
@router.get("/diff", response_model=SyncDiffResponse)
@limiter.limit(_dynamic_limit)
def sync_diff(
    request: Request,
    since: int = Query(..., ge=0, description="Return records with seq_num > since"),
    limit: int = Query(100, ge=1, description="Max records to return (capped at 1000)"),
    db: Session = Depends(get_db),
) -> SyncDiffResponse:
    """Return disc records changed since a given sequence number.

    Mirrors call this in a loop, advancing ``since`` to ``next_since``
    each iteration until ``has_more`` is false.

    No authentication required.
    """
    # Clamp limit to server maximum
    effective_limit = min(limit, MAX_DIFF_LIMIT)

    # Use subqueryload (not joinedload) so the LIMIT applies correctly
    # to the parent Disc rows — joinedload + LIMIT applies the limit on
    # the joined result set, which can return fewer unique parents than
    # requested when a disc has multiple titles/tracks.
    discs = (
        db.query(Disc)
        .options(
            subqueryload(Disc.titles).subqueryload(DiscTitle.tracks),
            subqueryload(Disc.releases),
        )
        .filter(Disc.seq_num > since)
        .order_by(Disc.seq_num.asc())
        .limit(effective_limit)
        .all()
    )

    records = [_build_sync_disc(d) for d in discs]

    next_since = max(r.seq_num for r in records) if records else since
    has_more = len(discs) == effective_limit

    logger.info(
        "sync_diff since=%d limit=%d record_count=%d next_since=%d has_more=%s",
        since,
        effective_limit,
        len(records),
        next_since,
        has_more,
    )

    return SyncDiffResponse(
        records=records,
        next_since=next_since,
        has_more=has_more,
    )
