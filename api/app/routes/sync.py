"""Sync feed endpoints — /v1/sync router.

Provides three unauthenticated read endpoints for downstream mirrors:

- ``GET /v1/sync/head`` — current global sequence number and timestamp
- ``GET /v1/sync/diff`` — paginated disc records changed since a given seq
- ``GET /v1/sync/snapshot`` — metadata for the latest CC0 database dump
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, subqueryload

from app.deps import get_db
from app.models import Disc, DiscTitle, GlobalSeq, SyncState
from app.rate_limit import _dynamic_limit, limiter
from app.schemas import (
    SyncDiffResponse,
    SyncHeadResponse,
    SyncSnapshotResponse,
)
from app.sync import build_sync_disc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sync", tags=["sync"])

# Maximum records per diff page — clamped server-side regardless of request.
MAX_DIFF_LIMIT = 1000


# ---------------------------------------------------------------------------
# Helpers — builders are in app.sync to avoid auth import chain for scripts
# ---------------------------------------------------------------------------
_build_sync_disc = build_sync_disc


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


# ---------------------------------------------------------------------------
# GET /v1/sync/snapshot
# ---------------------------------------------------------------------------
_SNAPSHOT_KEYS = [
    "snapshot_url",
    "snapshot_seq",
    "snapshot_size_bytes",
    "snapshot_record_count",
    "snapshot_sha256",
]


@router.get("/snapshot", response_model=SyncSnapshotResponse)
@limiter.limit(_dynamic_limit)
def sync_snapshot(
    request: Request, db: Session = Depends(get_db)
) -> SyncSnapshotResponse:
    """Return metadata for the latest CC0 database snapshot.

    The snapshot is generated offline by ``scripts/dump_cc0.py`` which
    writes the metadata keys into the ``sync_state`` table.  Returns 404
    if no snapshot has been generated yet (any required key is missing).
    """
    rows = (
        db.query(SyncState)
        .filter(SyncState.key.in_(_SNAPSHOT_KEYS))
        .all()
    )
    state = {row.key: row.value for row in rows}

    # All five keys must be present — partial metadata is invalid.
    missing = [k for k in _SNAPSHOT_KEYS if k not in state]
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"No snapshot available (missing keys: {', '.join(missing)})",
        )

    return SyncSnapshotResponse(
        snapshot_seq=int(state["snapshot_seq"]),
        url=state["snapshot_url"],
        size_bytes=int(state["snapshot_size_bytes"]),
        record_count=int(state["snapshot_record_count"]),
        sha256=state["snapshot_sha256"],
    )
