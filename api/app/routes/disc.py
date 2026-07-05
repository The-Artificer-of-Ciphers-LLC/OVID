"""Disc-related API endpoints — /v1 router."""

import json
import logging
import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.anti_sybil import (
    CONFIRMATION_COOLDOWN_WINDOW_HOURS,
    client_ip_hash,
    evaluate_confirmation,
)
from app.auth.deps import get_current_user
from app.deps import get_db
from app.disc_identity import (
    DiscIdentityConflict,
    attach_lookup_aliases,
    resolve_disc_identity,
    resolve_existing_disc_for_identities,
)
from app.models import Disc, DiscEdit, DiscRelease, DiscTitle, DiscTrack, Release, User
from app.structural_match import structural_match
from app.rate_limit import _dynamic_limit, limiter
from app.sync import next_seq
from app.verification import (
    VerificationTransitionError,
    flag_dispute,
    identify,
    resolve_dispute,
    verify,
)
from app.schemas import (
    STATUS_CONFIDENCE,
    DiscEditResponse,
    DiscEditsListResponse,
    DiscLookupResponse,
    DiscRegisterRequest,
    DiscSubmitRequest,
    DiscSubmitResponse,
    DisputeResolveRequest,
    DisputedDiscsResponse,
    FingerprintAliasResponse,
    ReleaseCreate,
    ReleaseResponse,
    SearchResponse,
    SearchResultRelease,
    TitleResponse,
    TrackResponse,
    UpcLookupResponse,
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


def _identity_conflict_response(
    request_id: str, fingerprint: str
) -> JSONResponse:
    """Build a conflict response for Disc Identity collisions."""
    return _error_response(
        request_id,
        "identity_conflict",
        f"Disc Identity '{fingerprint}' already resolves to another disc",
        409,
    )


def _method_of(fingerprint: str) -> str:
    """Derive the Disc Identity Method label from a fingerprint's prefix.

    Method is DERIVED, not stored — ``DiscIdentityAlias`` has no ``method``
    column and this phase adds no migration (D-04, IDENT-01).
    """
    return fingerprint.split("-", 1)[0]


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


def _identify_existing_disc(
    db: Session,
    existing: Disc,
    body: DiscSubmitRequest,
    current_user: User,
    request_id: str,
) -> JSONResponse:
    """Attach the first release metadata to a ``pending_identification`` disc.

    A disc pre-registered via ``POST /v1/disc/register`` (ARM registers a
    disc before metadata is known) has no Release/titles/tracks yet. The
    first ``submit_disc`` against it — by ANY user, including the original
    registrant — attaches the submitted metadata and identifies the disc
    via ``verification.identify()`` rather than running the same-submitter
    409 guard or the verify/dispute logic, neither of which applies when
    there is no existing release to conflict against (WR-03).
    """
    try:
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

        # Link disc ↔ release
        db.execute(
            DiscRelease.__table__.insert().values(
                disc_id=existing.id, release_id=release.id
            )
        )

        # Create titles and tracks
        for tc in body.titles:
            title = DiscTitle(
                disc_id=existing.id,
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

        identify(db, existing, current_user)

        # Assign sync sequence numbers so mirrors can track this change
        seq = next_seq(db)
        existing.seq_num = seq
        release.seq_num = seq

        # Audit trail: record the identification event
        db.add(
            DiscEdit(
                disc_id=existing.id,
                user_id=current_user.id,
                edit_type="identify",
                edit_note="disc identified — first release metadata attached",
            )
        )

        db.commit()
    except VerificationTransitionError as exc:
        db.rollback()
        return _error_response(request_id, "invalid_state", str(exc), 409)
    except IntegrityError:
        # Consistent with the new-disc path (CR-01): a constraint violation
        # in the metadata inserts (e.g. a duplicate title_index) is a
        # CLIENT error, not a fingerprint race — report 400, never 409/500.
        db.rollback()
        return _error_response(
            request_id,
            "invalid_submission",
            "Duplicate title_index or invalid disc structure in submission",
            400,
        )

    logger.info(
        "disc_identified fingerprint=%s disc_id=%s", existing.fingerprint, existing.id
    )

    return JSONResponse(
        status_code=200,
        content={
            "request_id": request_id,
            "fingerprint": existing.fingerprint,
            "status": "unverified",
            "message": "Disc identified — release metadata attached",
        },
    )


def _handle_existing_disc(
    db: Session,
    existing: Disc,
    body: DiscSubmitRequest,
    current_user: User,
    request_id: str,
    request: Request,
) -> JSONResponse:
    """Handle a submission that resolves to an already-existing disc.

    Attaches any new Lookup Aliases, then applies the two-contributor
    auto-verify / dispute contract (VERIFY-02): matching metadata from a
    different submitter auto-verifies via ``verify()``; mismatched metadata
    calls ``flag_dispute()`` — the sole writer of the disputed status, which
    refuses to touch an already-verified disc. On refusal the disc stays
    verified, an audit ``DiscEdit`` is recorded, and the response is 200
    with an explicit message — never a silent flip to disputed (A2 / crit
    #4). Reused by both the up-front duplicate check and the disc-row
    losing-race recovery path (IDENT-02).

    A disc that is still ``pending_identification`` (WR-03: registered by
    ARM before metadata was known) has no release to conflict/match
    against — the first submission against it always attaches metadata via
    ``_identify_existing_disc``, for any user, before the same-submitter
    409 guard and the verify/dispute logic below (which only apply once a
    disc already carries release metadata).
    """
    try:
        attach_lookup_aliases(
            db,
            existing,
            existing.fingerprint,
            [body.fingerprint, *body.fingerprint_aliases],
        )
    except DiscIdentityConflict as exc:
        return _identity_conflict_response(request_id, exc.fingerprint)

    if existing.status == "pending_identification":
        return _identify_existing_disc(db, existing, body, current_user, request_id)

    # Same user submitting again → conflict
    if existing.submitted_by is not None and str(existing.submitted_by) == str(current_user.id):
        db.commit()
        return _error_response(
            request_id,
            "conflict",
            "Disc already submitted by this user",
            409,
        )

    # Different user — anti-Sybil gate BEFORE any status write (VERIFY-04).
    # The gate only decides; it never mutates disc.status (VERIFY-02).
    gate = evaluate_confirmation(db, existing, current_user, request)
    if gate.hard_blocked:
        # Cooldown floor exceeded (D-13). Persist any alias attachments (parity
        # with the same-submitter 409 path) and refuse with 429 + Retry-After.
        db.commit()
        retry_after = str(CONFIRMATION_COOLDOWN_WINDOW_HOURS * 3600)
        return JSONResponse(
            status_code=429,
            content={
                "request_id": request_id,
                "error": "rate_limited",
                "message": "Confirmation cooldown active",
            },
            headers={"Retry-After": retry_after},
        )
    if not gate.trust_ok:
        # Weighted soft score below threshold (D-04); fail-open already applied
        # inside evaluate_confirmation for absent signals (D-07).
        db.commit()
        return _error_response(
            request_id,
            "insufficient_trust",
            "Confirmation rejected by anti-Sybil weighting",
            403,
        )

    # Structural equality (D-01/D-03) gates VERIFY over the WITHHELD stored
    # structure — a real proof of possession, not a public-metadata echo.
    # Release-consistency is retained as the DISPUTE trigger (A3): a
    # structural match with conflicting release, OR any structural mismatch,
    # falls through to the existing flag_dispute path below.
    if structural_match(existing, body, db) and _releases_match(
        existing, body.release, db
    ):
        try:
            transitioned = verify(db, existing, current_user)
        except VerificationTransitionError as exc:
            db.rollback()
            return _error_response(request_id, "invalid_state", str(exc), 409)
        if transitioned:
            existing.seq_num = next_seq(db)
            db.add(
                DiscEdit(
                    disc_id=existing.id,
                    user_id=current_user.id,
                    edit_type="verify",
                    ip_hash=gate.ip_hash,
                    edit_note="auto-verified by second contributor",
                )
            )
        db.commit()
        logger.info("disc_auto_verified fingerprint=%s", existing.fingerprint)
        return JSONResponse(
            status_code=200,
            content={
                "request_id": request_id,
                "status": "verified",
                "message": "Disc auto-verified by second contributor",
            },
        )

    flagged = flag_dispute(
        db, existing, current_user, reason="metadata conflict on second submission"
    )
    if flagged:
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
        logger.info("disc_disputed fingerprint=%s", existing.fingerprint)
        return JSONResponse(
            status_code=200,
            content={
                "request_id": request_id,
                "status": "disputed",
                "message": "Disc flagged as disputed due to metadata conflict",
            },
        )

    # A2 (VERIFY-02 crit #4): flag_dispute refused — existing is already
    # verified. It stays verified; record an audit DiscEdit and return 200
    # with an explicit message. Never report the disputed status.
    db.add(
        DiscEdit(
            disc_id=existing.id,
            user_id=current_user.id,
            edit_type="dispute_attempted",
            edit_note=(
                "metadata conflict on second submission against a verified "
                "disc — disc remains verified"
            ),
            new_value=json.dumps(body.release.model_dump()),
        )
    )
    db.commit()
    logger.info("disc_dispute_attempt_on_verified fingerprint=%s", existing.fingerprint)
    return JSONResponse(
        status_code=200,
        content={
            "request_id": request_id,
            "status": "verified",
            "message": (
                "Disc is already verified; conflicting metadata recorded "
                "but the disc remains verified"
            ),
        },
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

    # fingerprint_aliases (IDENT-01): primary first (is_primary=True), then
    # the identity_aliases relationship's own order (deterministic
    # (created_at, id) order_by on the relationship — D-06; do not
    # re-sort here, per PATTERNS).
    fingerprint_aliases_resp = [
        FingerprintAliasResponse(
            fingerprint=disc.fingerprint,
            method=_method_of(disc.fingerprint),
            is_primary=True,
        )
    ] + [
        FingerprintAliasResponse(
            fingerprint=alias.fingerprint,
            method=_method_of(alias.fingerprint),
            is_primary=False,
        )
        for alias in disc.identity_aliases
    ]

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
        fingerprint_aliases=fingerprint_aliases_resp,
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
            selectinload(Disc.identity_aliases),
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
            selectinload(Disc.identity_aliases),
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
async def resolve_dispute_endpoint(
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
    resolution = resolve_disc_identity(db, fingerprint)
    if resolution is None:
        return _error_response(request_id, "not_found", "Disc not found", 404)
    disc = resolution.disc
    try:
        resolve_dispute(db, disc, current_user, body.action)
    except VerificationTransitionError as exc:
        return _error_response(request_id, "invalid_state", str(exc), 409)
    if body.action == "verify":
        edit_note = f"Dispute resolved: marked verified by {current_user.username}"
    else:  # reject
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

    resolution = resolve_disc_identity(
        db,
        fingerprint,
        options=(
            joinedload(Disc.titles).joinedload(DiscTitle.tracks),
            selectinload(Disc.releases),
            selectinload(Disc.identity_aliases),
        ),
    )

    if resolution is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )

    return _disc_to_response(resolution.disc, request_id)


def _handle_existing_registered_disc(
    db: Session,
    existing: Disc,
    body: DiscRegisterRequest,
    request_id: str,
) -> JSONResponse:
    """Handle a ``/disc/register`` submission that resolves to an existing disc.

    Attaches any new Lookup Aliases and returns the idempotent 409
    "already registered" response. Reused by both the up-front duplicate
    check and the disc-row losing-race recovery path (IDENT-02).
    """
    try:
        attach_lookup_aliases(
            db,
            existing,
            existing.fingerprint,
            [body.fingerprint, *body.fingerprint_aliases],
        )
    except DiscIdentityConflict as exc:
        return _identity_conflict_response(request_id, exc.fingerprint)
    db.commit()
    return JSONResponse(
        status_code=409,
        content={
            "request_id": request_id,
            "fingerprint": existing.fingerprint,
            "status": existing.status,
            "message": "Disc already registered",
        },
    )


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

    try:
        existing_resolution = resolve_existing_disc_for_identities(
            db,
            body.fingerprint,
            body.fingerprint_aliases,
        )
    except DiscIdentityConflict as exc:
        return _identity_conflict_response(request_id, exc.fingerprint)

    if existing_resolution is not None:
        return _handle_existing_registered_disc(
            db, existing_resolution.disc, body, request_id
        )

    try:
        # SAVEPOINT-scoped disc-row insert (IDENT-02): a losing insert here
        # rolls back only this savepoint, never the outer transaction, so
        # we can cleanly recover and re-resolve to the true winner.
        with db.begin_nested():
            disc = Disc(
                fingerprint=body.fingerprint,
                format=body.format,
                disc_label=body.disc_label,
                status="pending_identification",
                submitted_by=current_user.id,
                seq_num=next_seq(db),
            )
            db.add(disc)
            db.flush()
    except IntegrityError:
        # Another worker won the race for this fingerprint between our
        # duplicate-check and this insert. Discard the stale identity map
        # (Pitfall 2), re-resolve, and fall through to the same duplicate
        # handling used by the up-front check — never split into two rows.
        db.expire_all()
        try:
            winner_resolution = resolve_existing_disc_for_identities(
                db, body.fingerprint, body.fingerprint_aliases
            )
        except DiscIdentityConflict as exc:
            return _identity_conflict_response(request_id, exc.fingerprint)
        if winner_resolution is None:
            # Genuinely unexpected — the UNIQUE violation implies a row
            # exists, but re-resolve found nothing. Do not swallow.
            raise
        return _handle_existing_registered_disc(
            db, winner_resolution.disc, body, request_id
        )

    try:
        attach_lookup_aliases(db, disc, body.fingerprint, body.fingerprint_aliases)
    except DiscIdentityConflict as exc:
        db.rollback()
        return _identity_conflict_response(request_id, exc.fingerprint)
    db.commit()
    logger.info("disc_registered fingerprint=%s by=%s", body.fingerprint, current_user.id)

    return JSONResponse(
        status_code=201,
        content={
            "request_id": request_id,
            "fingerprint": disc.fingerprint,
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
    try:
        existing_resolution = resolve_existing_disc_for_identities(
            db,
            body.fingerprint,
            body.fingerprint_aliases,
        )
    except DiscIdentityConflict as exc:
        return _identity_conflict_response(request_id, exc.fingerprint)

    if existing_resolution is not None:
        return _handle_existing_disc(
            db, existing_resolution.disc, body, current_user, request_id, request
        )

    try:
        # SAVEPOINT-scoped release+disc-row insert (IDENT-02): a losing
        # insert here rolls back only this savepoint — never the outer
        # transaction — so a losing race can be cleanly recovered and
        # re-resolved instead of leaking an orphaned Release row or
        # splitting into two disc rows.
        #
        # CR-01: this try/except is scoped to ONLY the savepoint. Anything
        # after it (aliases, titles/tracks, commit) has its own try/except
        # below so a post-savepoint IntegrityError (e.g. a duplicate
        # title_index) is never misclassified as a fingerprint race.
        with db.begin_nested():
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
    except IntegrityError:
        # Another submitter/worker won the race for this fingerprint
        # between our duplicate-check and this insert. Discard the stale
        # identity map (Pitfall 2), re-resolve to find the true winner, and
        # fall through to the same duplicate-submission handling used by
        # the up-front check — never split into two disc rows (IDENT-02).
        db.expire_all()
        try:
            winner_resolution = resolve_existing_disc_for_identities(
                db, body.fingerprint, body.fingerprint_aliases
            )
        except DiscIdentityConflict as exc:
            return _identity_conflict_response(request_id, exc.fingerprint)
        if winner_resolution is None:
            # Genuinely unexpected — the UNIQUE violation implies a row
            # exists, but re-resolve found nothing. Do not swallow.
            raise
        return _handle_existing_disc(
            db, winner_resolution.disc, body, current_user, request_id, request
        )

    try:
        attach_lookup_aliases(db, disc, body.fingerprint, body.fingerprint_aliases)

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

        # Assign sync sequence numbers so mirrors can track this change
        seq = next_seq(db)
        disc.seq_num = seq
        release.seq_num = seq

        # Audit trail: record the creation event. Capture the submitter's
        # salted /24 subnet hash (D-06) so a future confirmer's IP-diversity
        # can be compared against it (fail-open to NULL when IP/salt absent).
        db.add(
            DiscEdit(
                disc_id=disc.id,
                user_id=current_user.id,
                edit_type="create",
                ip_hash=client_ip_hash(request),
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

    except DiscIdentityConflict as exc:
        db.rollback()
        return _identity_conflict_response(request_id, exc.fingerprint)
    except IntegrityError:
        # A constraint violation AFTER the fingerprint/disc-row savepoint
        # (e.g. a duplicate title_index violating uq_disc_titles_index) is
        # a CLIENT error, not a fingerprint race — the disc row already
        # won its savepoint, so this is invalid submitted structure.
        db.rollback()
        return _error_response(
            request_id,
            "invalid_submission",
            "Duplicate title_index or invalid disc structure in submission",
            400,
        )
    except Exception:
        db.rollback()
        logger.exception("disc_submit_failed fingerprint=%s", body.fingerprint)
        return _error_response(
            request_id, "internal_error", "Failed to submit disc", 500
        )


# ---------------------------------------------------------------------------
# POST /v1/disc/{fingerprint}/verify — RETIRED (D-02)
# ---------------------------------------------------------------------------
# The bodyless verify route was deleted: it flipped status on a bare bearer
# token with no proof of physical possession — a pure Sybil bypass with no
# legitimate caller (the web UI cannot read discs). Confirmation is now ONLY
# structural re-submission via POST /v1/disc, gated by the anti-Sybil
# pre-check and structural_match in _handle_existing_disc above (D-01/D-03).


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

    resolution = resolve_disc_identity(db, fingerprint)
    if resolution is None:
        return _error_response(
            request_id, "not_found", f"No disc with fingerprint '{fingerprint}'", 404
        )
    disc = resolution.disc

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
        fingerprint=disc.fingerprint,
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
