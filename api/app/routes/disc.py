"""Disc-related API endpoints — /v1 router."""

import json
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request  # noqa: F401
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth.deps import get_current_user
from app.deps import get_db
from app.models import (
    Disc,
    DiscEdit,
    DiscRelease,
    DiscSet,
    DiscTitle,
    DiscTrack,
    Release,
    User,
)
from app.rate_limit import _dynamic_limit, limiter
from app.sync import next_seq
from app.schemas import (
    STATUS_CONFIDENCE,
    DiscEditResponse,
    DiscEditsListResponse,
    DiscLookupResponse,
    DiscRegisterRequest,
    DiscSetNested,
    DiscSubmitRequest,
    DiscSubmitResponse,
    DisputeResolveRequest,
    DisputedDiscsResponse,
    ReleaseCreate,
    ReleaseResponse,
    SearchResponse,
    SearchResultRelease,
    SiblingDiscSummary,
    TitleResponse,
    TrackResponse,
    UpcLookupResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["disc"])


# ---------------------------------------------------------------------------
# Status state machine (BUG-02)
# ---------------------------------------------------------------------------
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "unverified": {"verified", "disputed"},
    "disputed": {"verified", "unverified"},
    "verified": set(),  # terminal state
    "pending_identification": {"unverified", "verified", "disputed"},
}


def _validate_status_transition(
    request_id: str, current: str, target: str
) -> JSONResponse | None:
    """Return a 400 error response if the status transition is not allowed.

    Returns None if the transition is valid.
    """
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        return _error_response(
            request_id,
            "invalid_status_transition",
            f"Cannot transition from '{current}' to '{target}'",
            400,
        )
    return None


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


def _build_track_response(track: DiscTrack) -> TrackResponse:
    return TrackResponse(
        index=track.track_index,
        language=track.language_code,
        codec=track.codec,
        channels=track.channels,
        is_default=track.is_default,
    )


def _releases_match(
    existing_disc: Disc, new_release: ReleaseCreate, db: Session
) -> bool:
    """Check if the existing disc's release matches the new submission's release."""
    existing_release = (
        db.query(Release)
        .join(DiscRelease, DiscRelease.release_id == Release.id)
        .filter(DiscRelease.disc_id == existing_disc.id)
        .first()
    )
    if existing_release is None:
        return False
    if existing_release.tmdb_id is not None and new_release.tmdb_id is not None:
        return existing_release.tmdb_id == new_release.tmdb_id
    return (
        existing_release.title.lower() == new_release.title.lower()
        and existing_release.year == new_release.year
    )


def _build_title_response(title: DiscTitle) -> TitleResponse:
    audio = [
        _build_track_response(t) for t in title.tracks if t.track_type == "audio"
    ]
    subs = [
        _build_track_response(t) for t in title.tracks if t.track_type == "subtitle"
    ]
    return TitleResponse(
        title_index=title.title_index,
        is_main_feature=title.is_main_feature,
        title_type=title.title_type,
        display_name=title.display_name,
        duration_secs=title.duration_secs,
        chapter_count=title.chapter_count,
        audio_tracks=audio,
        subtitle_tracks=subs,
    )


def _build_disc_set_nested(disc: Disc) -> DiscSetNested | None:
    """Build a DiscSetNested response if the disc belongs to a set."""
    if disc.disc_set is None:
        return None
    ds = disc.disc_set
    siblings = []
    for sibling in ds.discs:
        if sibling.id == disc.id:
            continue
        main_title_name = None
        main_duration = None
        track_count = 0
        for t in sibling.titles:
            track_count += len(t.tracks) if hasattr(t, "tracks") else 0
            if t.is_main_feature:
                main_title_name = t.display_name
                main_duration = t.duration_secs
        siblings.append(SiblingDiscSummary(
            fingerprint=sibling.fingerprint,
            disc_number=sibling.disc_number,
            format=sibling.format,
            main_title=main_title_name,
            duration_secs=main_duration,
            track_count=track_count,
        ))
    return DiscSetNested(
        id=str(ds.id),
        edition_name=ds.edition_name,
        total_discs=ds.total_discs,
        siblings=siblings,
    )


def _disc_to_response(disc: Disc, request_id: str) -> DiscLookupResponse:
    """Convert a Disc ORM object to a DiscLookupResponse schema."""
    confidence = STATUS_CONFIDENCE.get(disc.status, "low")

    release_resp = None
    if disc.releases:
        rel = disc.releases[0]
        release_resp = ReleaseResponse(
            title=rel.title,
            year=rel.year,
            content_type=rel.content_type,
            tmdb_id=rel.tmdb_id,
            imdb_id=rel.imdb_id,
        )

    titles_resp = [_build_title_response(t) for t in disc.titles]
    disc_set_resp = _build_disc_set_nested(disc)

    return DiscLookupResponse(
        request_id=request_id,
        fingerprint=disc.fingerprint,
        format=disc.format,
        status=disc.status,
        confidence=confidence,
        region_code=disc.region_code,
        upc=disc.upc,
        edition_name=disc.edition_name,
        disc_number=disc.disc_number,
        total_discs=disc.total_discs,
        submitted_by=str(disc.submitted_by) if disc.submitted_by else None,
        verified_by=str(disc.verified_by) if disc.verified_by else None,
        release=release_resp,
        titles=titles_resp,
        disc_set=disc_set_resp,
    )


# ---------------------------------------------------------------------------
# GET /v1/disc/upc/{upc}
# ---------------------------------------------------------------------------
@router.get("/disc/upc/{upc}", response_model=UpcLookupResponse)
@limiter.limit(_dynamic_limit)
def lookup_disc_by_upc(
    upc: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Look up all discs sharing a UPC barcode."""
    request_id: str = request.state.request_id

    discs = (
        db.query(Disc)
        .filter(Disc.upc == upc)
        .options(
            joinedload(Disc.titles).joinedload(DiscTitle.tracks),
            selectinload(Disc.releases),
        )
        .all()
    )
    results = [_disc_to_response(d, request_id) for d in discs]
    return UpcLookupResponse(request_id=request_id, results=results)


# ---------------------------------------------------------------------------
# GET /v1/disc/disputed  (must register before /disc/{fingerprint})
# ---------------------------------------------------------------------------
@router.get("/disc/disputed", response_model=DisputedDiscsResponse)
@limiter.limit(_dynamic_limit)
async def list_disputed_discs(
    request: Request,
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> DisputedDiscsResponse:
    """List all discs currently in 'disputed' status."""
    request_id = str(uuid.uuid4())
    q = db.query(Disc).filter(Disc.status == "disputed")
    total = q.count()
    discs = (
        q.options(
            joinedload(Disc.titles).joinedload(DiscTitle.tracks),
            selectinload(Disc.releases),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    results = [_disc_to_response(d, request_id) for d in discs]
    return DisputedDiscsResponse(
        request_id=request_id,
        total=total,
        limit=limit,
        offset=offset,
        results=results,
    )


# ---------------------------------------------------------------------------
# POST /v1/disc/{fingerprint}/resolve
# ---------------------------------------------------------------------------
@router.post("/disc/{fingerprint}/resolve")
@limiter.limit(_dynamic_limit)
async def resolve_dispute(
    fingerprint: str,
    body: DisputeResolveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Resolve a disputed disc — trusted/editor/admin users only."""
    request_id = str(uuid.uuid4())
    if current_user.role not in ("trusted", "editor", "admin"):
        return _error_response(request_id, "forbidden", "Trusted user role required", 403)
    disc = db.query(Disc).filter(Disc.fingerprint == fingerprint).first()
    if disc is None:
        return _error_response(request_id, "not_found", "Disc not found", 404)
    if disc.status != "disputed":
        return _error_response(request_id, "invalid_state", "Disc is not in disputed state", 409)
    if body.action == "verify":
        disc.status = "verified"
        disc.verified_by = current_user.id
        edit_note = f"Dispute resolved: marked verified by {current_user.username}"
    else:  # reject
        disc.status = "unverified"
        edit_note = f"Dispute resolved: reverted to unverified by {current_user.username}"
    disc.seq_num = next_seq(db)
    db.add(
        DiscEdit(
            disc_id=disc.id,
            user_id=current_user.id,
            edit_type="resolve",
            edit_note=edit_note,
        )
    )
    db.commit()
    logger.info("disc_resolved fingerprint=%s action=%s resolver=%s", fingerprint, body.action, current_user.id)
    return JSONResponse(
        status_code=200,
        content={"request_id": request_id, "status": disc.status, "message": "Dispute resolved"},
    )


# ---------------------------------------------------------------------------
# GET /v1/disc/{fingerprint}
# ---------------------------------------------------------------------------
@router.get("/disc/{fingerprint}", response_model=DiscLookupResponse)
@limiter.limit(_dynamic_limit)
def lookup_disc(
    fingerprint: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Look up a disc by fingerprint with full nested metadata."""
    request_id: str = request.state.request_id

    disc = (
        db.query(Disc)
        .options(
            joinedload(Disc.titles).joinedload(DiscTitle.tracks),
            selectinload(Disc.releases),
            joinedload(Disc.disc_set)
            .selectinload(DiscSet.discs)
            .joinedload(Disc.titles)
            .joinedload(DiscTitle.tracks),
        )
        .filter(Disc.fingerprint == fingerprint)
        .first()
    )

    if disc is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )

    return _disc_to_response(disc, request_id)


# ---------------------------------------------------------------------------
# POST /v1/disc/register — fingerprint-only registration (no release metadata)
# ---------------------------------------------------------------------------
@router.post("/disc/register", response_model=DiscSubmitResponse, status_code=201)
@limiter.limit(_dynamic_limit)
def register_disc(
    body: DiscRegisterRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Register a disc fingerprint without release metadata.

    Used by automated rippers (ARM) to record that a disc exists.
    Creates the disc with status ``pending_identification`` and no
    associated release.  A human must later attach release metadata
    via the web UI, CLI, or ``POST /v1/disc``.

    Returns 409 if the fingerprint already exists (idempotent for ARM).
    """
    request_id: str = request.state.request_id

    existing = db.query(Disc).filter(Disc.fingerprint == body.fingerprint).first()
    if existing is not None:
        return JSONResponse(
            status_code=409,
            content={
                "request_id": request_id,
                "fingerprint": body.fingerprint,
                "status": existing.status,
                "message": "Disc already registered",
            },
        )

    disc = Disc(
        fingerprint=body.fingerprint,
        format=body.format,
        disc_label=body.disc_label,
        status="pending_identification",
        submitted_by=current_user.id,
        seq_num=next_seq(db),
    )
    db.add(disc)
    db.commit()
    logger.info("disc_registered fingerprint=%s by=%s", body.fingerprint, current_user.id)

    return JSONResponse(
        status_code=201,
        content={
            "request_id": request_id,
            "fingerprint": body.fingerprint,
            "status": "pending_identification",
            "message": "Disc registered — awaiting identification",
        },
    )


# ---------------------------------------------------------------------------
# POST /v1/disc
# ---------------------------------------------------------------------------
@router.post("/disc", response_model=DiscSubmitResponse, status_code=201)
@limiter.limit(_dynamic_limit)
def submit_disc(
    body: DiscSubmitRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Submit a new disc with release, titles, and tracks."""
    request_id: str = request.state.request_id

    # Duplicate check — auto-verify or dispute logic
    existing = db.query(Disc).filter(Disc.fingerprint == body.fingerprint).first()
    if existing is not None:
        # Same user submitting again -> conflict
        if existing.submitted_by is not None and str(existing.submitted_by) == str(current_user.id):
            return _error_response(
                request_id,
                "conflict",
                "Disc already submitted by this user",
                409,
            )
        # Different user -- check if release metadata matches
        if _releases_match(existing, body.release, db):
            existing.status = "verified"
            existing.verified_by = current_user.id
            existing.seq_num = next_seq(db)
            db.add(
                DiscEdit(
                    disc_id=existing.id,
                    user_id=current_user.id,
                    edit_type="verify",
                    edit_note="auto-verified by second contributor",
                )
            )
            db.commit()
            logger.info("disc_auto_verified fingerprint=%s", body.fingerprint)
            return JSONResponse(
                status_code=200,
                content={
                    "request_id": request_id,
                    "status": "verified",
                    "message": "Disc auto-verified by second contributor",
                },
            )
        else:
            existing.status = "disputed"
            existing.seq_num = next_seq(db)
            db.add(
                DiscEdit(
                    disc_id=existing.id,
                    user_id=current_user.id,
                    edit_type="disputed",
                    edit_note="metadata conflict on second submission",
                    new_value=json.dumps(body.release.model_dump()),
                )
            )
            db.commit()
            logger.info("disc_disputed fingerprint=%s", body.fingerprint)
            return JSONResponse(
                status_code=200,
                content={
                    "request_id": request_id,
                    "status": "disputed",
                    "message": "Disc flagged as disputed due to metadata conflict",
                },
            )

    try:
        # Create release
        release = Release(
            title=body.release.title,
            year=body.release.year,
            content_type=body.release.content_type,
            tmdb_id=body.release.tmdb_id,
            imdb_id=body.release.imdb_id,
            original_language=body.release.original_language,
        )
        db.add(release)
        db.flush()

        # Create disc
        disc = Disc(
            fingerprint=body.fingerprint,
            format=body.format,
            region_code=body.region_code,
            upc=body.upc,
            disc_label=body.disc_label,
            disc_number=body.disc_number,
            total_discs=body.total_discs,
            edition_name=body.edition_name,
            status="unverified",
            submitted_by=current_user.id,
        )
        db.add(disc)
        db.flush()

        # Link disc <-> release
        db.execute(
            DiscRelease.__table__.insert().values(
                disc_id=disc.id, release_id=release.id
            )
        )

        # Create titles and tracks
        for tc in body.titles:
            title = DiscTitle(
                disc_id=disc.id,
                title_index=tc.title_index,
                title_type=tc.title_type,
                duration_secs=tc.duration_secs,
                chapter_count=tc.chapter_count,
                is_main_feature=tc.is_main_feature,
                display_name=tc.display_name,
            )
            db.add(title)
            db.flush()

            for at in tc.audio_tracks:
                db.add(DiscTrack(
                    disc_title_id=title.id,
                    track_type="audio",
                    track_index=at.track_index,
                    language_code=at.language_code,
                    codec=at.codec,
                    channels=at.channels,
                    is_default=at.is_default,
                ))

            for st in tc.subtitle_tracks:
                db.add(DiscTrack(
                    disc_title_id=title.id,
                    track_type="subtitle",
                    track_index=st.track_index,
                    language_code=st.language_code,
                    codec=st.codec,
                    channels=st.channels,
                    is_default=st.is_default,
                ))

        # --- Set integration (Phase 2: D-01, D-03, D-08, D-14) ---
        if body.disc_set_id is not None:
            try:
                set_uuid = uuid.UUID(body.disc_set_id)
            except ValueError:
                db.rollback()
                return _error_response(request_id, "validation_error", "Invalid disc_set_id format", 422)
            existing_set = db.query(DiscSet).filter(DiscSet.id == set_uuid).first()
            if existing_set is None:
                db.rollback()
                return _error_response(request_id, "not_found", "Disc set not found", 404)
            if body.disc_number > existing_set.total_discs:
                db.rollback()
                return _error_response(
                    request_id, "validation_error",
                    f"Disc number {body.disc_number} exceeds total disc count ({existing_set.total_discs})",
                    422,
                )
            disc.disc_set_id = existing_set.id
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                return _error_response(
                    request_id, "conflict",
                    f"Disc {body.disc_number} is already assigned in this set. Choose a different disc number or dispute the existing entry.",
                    409,
                )
        elif body.total_discs > 1:
            # D-01: implicit set creation
            new_set = DiscSet(
                release_id=release.id,
                edition_name=body.edition_name,
                total_discs=body.total_discs,
                seq_num=next_seq(db),
            )
            db.add(new_set)
            db.flush()
            disc.disc_set_id = new_set.id

        # Assign sync sequence numbers so mirrors can track this change
        seq = next_seq(db)
        disc.seq_num = seq
        release.seq_num = seq

        # Audit trail: record the creation event
        db.add(
            DiscEdit(
                disc_id=disc.id,
                user_id=current_user.id,
                edit_type="create",
            )
        )

        db.commit()

        logger.info("disc_submitted fingerprint=%s disc_id=%s", body.fingerprint, disc.id)

        return DiscSubmitResponse(
            request_id=request_id,
            fingerprint=disc.fingerprint,
            status=disc.status,
            message="Disc submitted successfully",
        )

    except IntegrityError as e:
        db.rollback()
        logger.warning("disc_submit_integrity_error fingerprint=%s detail=%s", body.fingerprint, str(e))
        return _error_response(
            request_id, "duplicate_fingerprint", "A disc with this fingerprint already exists", 409
        )
    except Exception:
        db.rollback()
        logger.exception("disc_submit_failed fingerprint=%s", body.fingerprint)
        return _error_response(
            request_id, "internal_error", "An unexpected error occurred during disc submission", 500
        )


# ---------------------------------------------------------------------------
# POST /v1/disc/{fingerprint}/verify
# ---------------------------------------------------------------------------
@router.post("/disc/{fingerprint}/verify")
@limiter.limit(_dynamic_limit)
def verify_disc(
    fingerprint: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Promote a disc to verified status.

    The original submitter cannot verify their own submission (R011).
    Enforces state machine: verified is a terminal state (BUG-02).
    """
    request_id: str = request.state.request_id

    disc = db.query(Disc).filter(Disc.fingerprint == fingerprint).first()
    if disc is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )

    # Cannot verify your own submission
    if disc.submitted_by is not None and str(disc.submitted_by) == str(current_user.id):
        return _error_response(
            request_id, "forbidden", "Cannot verify your own submission", 403
        )

    # State machine validation
    transition_error = _validate_status_transition(request_id, disc.status, "verified")
    if transition_error is not None:
        return transition_error

    disc.status = "verified"
    disc.verified_by = current_user.id
    disc.seq_num = next_seq(db)
    db.add(
        DiscEdit(
            disc_id=disc.id,
            user_id=current_user.id,
            edit_type="verify",
        )
    )
    db.commit()

    logger.info("disc_verified fingerprint=%s", fingerprint)

    return JSONResponse(
        status_code=200,
        content={
            "request_id": request_id,
            "fingerprint": fingerprint,
            "status": "verified",
            "message": "Disc verified successfully",
        },
    )


# ---------------------------------------------------------------------------
# GET /v1/disc/{fingerprint}/edits
# ---------------------------------------------------------------------------
@router.get("/disc/{fingerprint}/edits", response_model=DiscEditsListResponse)
@limiter.limit(_dynamic_limit)
def get_disc_edits(
    fingerprint: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Return the edit history for a disc (R015)."""
    request_id: str = request.state.request_id

    disc = db.query(Disc).filter(Disc.fingerprint == fingerprint).first()
    if disc is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )

    edits = (
        db.query(DiscEdit)
        .filter(DiscEdit.disc_id == disc.id)
        .order_by(DiscEdit.created_at.asc())
        .all()
    )

    edit_responses = [
        DiscEditResponse(
            edit_type=e.edit_type,
            field_changed=e.field_changed,
            old_value=e.old_value,
            new_value=e.new_value,
            edit_note=e.edit_note,
            created_at=e.created_at.isoformat() if e.created_at else "",
            user_id=str(e.user_id) if e.user_id else None,
        )
        for e in edits
    ]

    return DiscEditsListResponse(
        request_id=request_id,
        fingerprint=fingerprint,
        edits=edit_responses,
    )


# ---------------------------------------------------------------------------
# GET /v1/search
# ---------------------------------------------------------------------------
PAGE_SIZE = 20


@router.get("/search", response_model=SearchResponse)
@limiter.limit(_dynamic_limit)
def search_releases(
    request: Request,
    q: str | None = Query(default=None),
    type: str | None = Query(default=None),
    year: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> Any:
    """Search releases by title with optional type/year filters and pagination."""
    request_id: str = request.state.request_id

    if not q or not q.strip():
        return _error_response(
            request_id, "bad_request", "Query parameter 'q' is required", 400
        )

    query = db.query(Release).filter(Release.title.ilike(f"%{q}%"))

    if type is not None:
        query = query.filter(Release.content_type == type)
    if year is not None:
        query = query.filter(Release.year == year)

    total_results = query.count()
    total_pages = max(1, math.ceil(total_results / PAGE_SIZE)) if total_results > 0 else 0

    releases = query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE).all()

    results = []
    for rel in releases:
        disc_count = (
            db.query(func.count())
            .select_from(DiscRelease)
            .filter(DiscRelease.release_id == rel.id)
            .scalar()
        )
        results.append(
            SearchResultRelease(
                id=str(rel.id),
                title=rel.title,
                year=rel.year,
                content_type=rel.content_type,
                tmdb_id=rel.tmdb_id,
                disc_count=disc_count or 0,
            )
        )

    return SearchResponse(
        request_id=request_id,
        results=results,
        page=page,
        total_pages=total_pages,
        total_results=total_results,
    )
