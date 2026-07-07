"""Disc set CRUD endpoints — /v1 router (Phase 2)."""

import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, selectinload

from app.auth.deps import get_current_user
from app.deps import get_db
from app.models import Disc, DiscSet, DiscTitle, Release, User
from app.rate_limit import _dynamic_limit, limiter
from app.schemas import (
    DiscSetCreate,
    DiscSetDetailResponse,
    DiscSetResponse,
    DiscSetSearchResponse,
    SiblingDiscSummary,
)
from app.sync import next_seq

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["set"])

PAGE_SIZE = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error_response(
    request_id: str, error: str, message: str, status_code: int
) -> JSONResponse:
    """Build a JSON error response with consistent shape."""
    return JSONResponse(
        status_code=status_code,
        content={"request_id": request_id, "error": error, "message": message},
    )


def _build_sibling_summary(disc: Disc) -> SiblingDiscSummary:
    """Build a SiblingDiscSummary from a Disc ORM object (D-06)."""
    main_title_name = None
    main_duration = None
    track_count = 0
    for t in disc.titles:
        track_count += len(t.tracks) if hasattr(t, "tracks") else 0
        if t.is_main_feature:
            main_title_name = t.display_name
            main_duration = t.duration_secs
    return SiblingDiscSummary(
        fingerprint=disc.fingerprint,
        disc_number=disc.disc_number,
        format=disc.format,
        main_title=main_title_name,
        duration_secs=main_duration,
        track_count=track_count,
    )


# ---------------------------------------------------------------------------
# POST /v1/set
# ---------------------------------------------------------------------------
@router.post("/set", status_code=201)
@limiter.limit(_dynamic_limit)
def create_set(
    body: DiscSetCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Create a new disc set linked to a release."""
    request_id: str = request.state.request_id

    # Validate release_id exists
    try:
        release_uuid = uuid.UUID(body.release_id)
    except ValueError:
        return _error_response(request_id, "validation_error", "Invalid release_id format", 422)

    release = db.query(Release).filter(Release.id == release_uuid).first()
    if release is None:
        return _error_response(request_id, "not_found", "Release not found", 404)

    disc_set = DiscSet(
        release_id=release_uuid,
        edition_name=body.edition_name,
        total_discs=body.total_discs,
        seq_num=next_seq(db),
    )
    db.add(disc_set)
    db.commit()
    db.refresh(disc_set)

    logger.info("disc_set_created set_id=%s release_id=%s", disc_set.id, release_uuid)

    return JSONResponse(
        status_code=201,
        content=DiscSetResponse(
            request_id=request_id,
            id=str(disc_set.id),
            release_id=str(disc_set.release_id),
            edition_name=disc_set.edition_name,
            total_discs=disc_set.total_discs,
            created_at=disc_set.created_at.isoformat() if disc_set.created_at else "",
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# GET /v1/set/{set_id}
# ---------------------------------------------------------------------------
@router.get("/set/{set_id}")
@limiter.limit(_dynamic_limit)
def get_set(
    set_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Retrieve a disc set with all member discs."""
    request_id: str = request.state.request_id

    try:
        set_uuid = uuid.UUID(set_id)
    except ValueError:
        return _error_response(request_id, "validation_error", "Invalid set_id format", 422)

    disc_set = (
        db.query(DiscSet)
        .options(
            selectinload(DiscSet.discs)
            .joinedload(Disc.titles)
            .joinedload(DiscTitle.tracks),
        )
        .filter(DiscSet.id == set_uuid)
        .first()
    )

    if disc_set is None:
        return _error_response(request_id, "not_found", "Disc set not found", 404)

    discs = [_build_sibling_summary(d) for d in disc_set.discs]

    return DiscSetDetailResponse(
        request_id=request_id,
        id=str(disc_set.id),
        release_id=str(disc_set.release_id),
        edition_name=disc_set.edition_name,
        total_discs=disc_set.total_discs,
        discs=discs,
    ).model_dump()


# ---------------------------------------------------------------------------
# GET /v1/set?q=
# ---------------------------------------------------------------------------
@router.get("/set")
@limiter.limit(_dynamic_limit)
def search_sets(
    request: Request,
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> Any:
    """Search disc sets by release title or edition name."""
    request_id: str = request.state.request_id

    if not q or not q.strip():
        return _error_response(
            request_id, "bad_request", "Query parameter 'q' is required", 400
        )

    query = (
        db.query(DiscSet)
        .join(Release, DiscSet.release_id == Release.id)
        .filter(
            Release.title.ilike(f"%{q}%")
            | DiscSet.edition_name.ilike(f"%{q}%")
        )
        .options(
            selectinload(DiscSet.discs)
            .joinedload(Disc.titles)
            .joinedload(DiscTitle.tracks),
        )
    )

    total_results = query.count()
    total_pages = max(1, math.ceil(total_results / PAGE_SIZE)) if total_results > 0 else 0

    sets = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    results = []
    for ds in sets:
        discs = [_build_sibling_summary(d) for d in ds.discs]
        results.append(
            DiscSetDetailResponse(
                request_id=request_id,
                id=str(ds.id),
                release_id=str(ds.release_id),
                edition_name=ds.edition_name,
                total_discs=ds.total_discs,
                discs=discs,
            )
        )

    return DiscSetSearchResponse(
        request_id=request_id,
        results=results,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    ).model_dump()
