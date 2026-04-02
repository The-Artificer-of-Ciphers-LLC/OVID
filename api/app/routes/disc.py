"""Disc-related API endpoints — /v1 router."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import get_db
from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, Release
from app.schemas import (
    STATUS_CONFIDENCE,
    DiscLookupResponse,
    DiscSubmitRequest,
    DiscSubmitResponse,
    ReleaseResponse,
    TitleResponse,
    TrackResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["disc"])


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


# ---------------------------------------------------------------------------
# GET /v1/disc/{fingerprint}
# ---------------------------------------------------------------------------
@router.get("/disc/{fingerprint}", response_model=DiscLookupResponse)
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
        )
        .filter(Disc.fingerprint == fingerprint)
        .first()
    )

    if disc is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )

    # Confidence from status
    confidence = STATUS_CONFIDENCE.get(disc.status, "low")

    # First release, if any
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

    # Build titles with split tracks
    titles_resp = [_build_title_response(t) for t in disc.titles]

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
        release=release_resp,
        titles=titles_resp,
    )


# ---------------------------------------------------------------------------
# POST /v1/disc
# ---------------------------------------------------------------------------
@router.post("/disc", response_model=DiscSubmitResponse, status_code=201)
def submit_disc(
    body: DiscSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Any:
    """Submit a new disc with release, titles, and tracks."""
    request_id: str = request.state.request_id

    # Duplicate check
    existing = db.query(Disc).filter(Disc.fingerprint == body.fingerprint).first()
    if existing is not None:
        return _error_response(
            request_id,
            "conflict",
            f"Disc with fingerprint '{body.fingerprint}' already exists",
            409,
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
        )
        db.add(disc)
        db.flush()

        # Link disc ↔ release
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

        db.commit()

        logger.info("disc_submitted fingerprint=%s disc_id=%s", body.fingerprint, disc.id)

        return DiscSubmitResponse(
            request_id=request_id,
            fingerprint=disc.fingerprint,
            status=disc.status,
            message="Disc submitted successfully",
        )

    except Exception:
        db.rollback()
        logger.exception("disc_submit_failed fingerprint=%s", body.fingerprint)
        return _error_response(
            request_id, "internal_error", "Failed to submit disc", 500
        )
