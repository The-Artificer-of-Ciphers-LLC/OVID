"""Pydantic request/response schemas for OVID API — tech spec §4."""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Confidence mapping: disc.status → human-readable confidence level
# ---------------------------------------------------------------------------
STATUS_CONFIDENCE: dict[str, str] = {
    "verified": "high",
    "unverified": "medium",
    "disputed": "medium",
}


# ---------------------------------------------------------------------------
# Response schemas (read)
# ---------------------------------------------------------------------------
class TrackResponse(BaseModel):
    index: int
    language: str | None = None
    codec: str | None = None
    channels: int | None = None
    is_default: bool = False


class TitleResponse(BaseModel):
    title_index: int
    is_main_feature: bool = False
    title_type: str | None = None
    display_name: str | None = None
    duration_secs: int | None = None
    chapter_count: int | None = None
    audio_tracks: list[TrackResponse] = Field(default_factory=list)
    subtitle_tracks: list[TrackResponse] = Field(default_factory=list)


class ReleaseResponse(BaseModel):
    title: str
    year: int | None = None
    content_type: str
    tmdb_id: int | None = None
    imdb_id: str | None = None


class DiscLookupResponse(BaseModel):
    request_id: str
    fingerprint: str
    format: str
    status: str
    confidence: str
    region_code: str | None = None
    upc: str | None = None
    edition_name: str | None = None
    disc_number: int = 1
    total_discs: int = 1
    submitted_by: str | None = None
    verified_by: str | None = None
    release: ReleaseResponse | None = None
    titles: list[TitleResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request schemas (write)
# ---------------------------------------------------------------------------
class TrackCreate(BaseModel):
    track_index: int = Field(ge=0)
    language_code: str | None = None
    codec: str | None = None
    channels: int | None = Field(default=None, ge=0)
    is_default: bool = False


class TitleCreate(BaseModel):
    title_index: int = Field(ge=0)
    title_type: str | None = None
    duration_secs: int | None = Field(default=None, ge=0)
    chapter_count: int | None = Field(default=None, ge=0)
    is_main_feature: bool = False
    display_name: str | None = None
    audio_tracks: list[TrackCreate] = Field(default_factory=list)
    subtitle_tracks: list[TrackCreate] = Field(default_factory=list)


class ReleaseCreate(BaseModel):
    title: str = Field(min_length=1)
    year: int | None = None
    content_type: str = Field(min_length=1)
    tmdb_id: int | None = None
    imdb_id: str | None = None
    original_language: str | None = None


class UpcLookupResponse(BaseModel):
    request_id: str
    results: list[DiscLookupResponse] = Field(default_factory=list)


class DisputeResolveRequest(BaseModel):
    action: Literal["verify", "reject"]


class DisputedDiscsResponse(BaseModel):
    request_id: str
    total: int
    limit: int
    offset: int
    results: list[DiscLookupResponse] = Field(default_factory=list)


class DiscSubmitRequest(BaseModel):
    fingerprint: str = Field(min_length=1)
    format: str = Field(min_length=1)
    region_code: str | None = None
    upc: str | None = None
    disc_label: str | None = None
    edition_name: str | None = None
    disc_number: int = Field(default=1, ge=1)
    total_discs: int = Field(default=1, ge=1)
    release: ReleaseCreate
    titles: list[TitleCreate] = Field(default_factory=list)


class DiscSubmitResponse(BaseModel):
    request_id: str
    fingerprint: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# Edit history schemas (R015)
# ---------------------------------------------------------------------------
class DiscEditResponse(BaseModel):
    edit_type: str | None = None
    field_changed: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    edit_note: str | None = None
    created_at: str
    user_id: str | None = None


class DiscEditsListResponse(BaseModel):
    request_id: str
    fingerprint: str
    edits: list[DiscEditResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Search schemas
# ---------------------------------------------------------------------------
class SearchResultRelease(BaseModel):
    id: str
    title: str
    year: int | None = None
    content_type: str
    tmdb_id: int | None = None
    disc_count: int = 0


class SearchResponse(BaseModel):
    request_id: str
    results: list[SearchResultRelease] = Field(default_factory=list)
    page: int = 1
    total_pages: int = 0
    total_results: int = 0


# ---------------------------------------------------------------------------
# Sync feed schemas (R018)
# ---------------------------------------------------------------------------
class SyncTrackRecord(BaseModel):
    """Track data for sync diff records — mirrors TrackResponse."""

    index: int
    track_type: str
    language: str | None = None
    codec: str | None = None
    channels: int | None = None
    is_default: bool = False


class SyncTitleRecord(BaseModel):
    """Title data for sync diff records — includes all tracks unsplit."""

    title_index: int
    is_main_feature: bool = False
    title_type: str | None = None
    display_name: str | None = None
    duration_secs: int | None = None
    chapter_count: int | None = None
    tracks: list[SyncTrackRecord] = Field(default_factory=list)


class SyncReleaseRecord(BaseModel):
    """Release data for sync diff records."""

    title: str
    year: int | None = None
    content_type: str
    tmdb_id: int | None = None
    imdb_id: str | None = None
    original_language: str | None = None


class SyncDiffRecord(BaseModel):
    """A single disc record in a sync diff response.

    Includes enough data for a mirror to reconstruct the disc locally.
    The ``type`` discriminator enables future extension to non-disc records.
    """

    type: str = "disc"
    seq_num: int
    fingerprint: str
    format: str
    status: str
    region_code: str | None = None
    upc: str | None = None
    disc_label: str | None = None
    edition_name: str | None = None
    disc_number: int = 1
    total_discs: int = 1
    titles: list[SyncTitleRecord] = Field(default_factory=list)
    release: SyncReleaseRecord | None = None


class SyncDiffResponse(BaseModel):
    """Response for GET /v1/sync/diff — paginated change feed."""

    records: list[SyncDiffRecord] = Field(default_factory=list)
    next_since: int
    has_more: bool


class SyncHeadResponse(BaseModel):
    """Response for GET /v1/sync/head — current sequence position."""

    seq: int
    timestamp: str


# ---------------------------------------------------------------------------
# Error schema
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    request_id: str
    error: str
    message: str
