"""SQLAlchemy ORM models for OVID — all 9 core tables.

Tables:
  discs, releases, disc_releases, disc_titles, disc_tracks,
  disc_sets, users, user_oauth_links, disc_edits

Schema follows tech-spec §3 with two additions from S02 research:
  - disc_sets table (R010) with release_id FK
  - user_oauth_links table (R005 OAuth-ready); users drops password_hash,
    adds display_name
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# discs — one row per unique physical disc pressing
# ---------------------------------------------------------------------------
class Disc(Base):
    __tablename__ = "discs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fingerprint: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    region_code: Mapped[str | None] = mapped_column(String(10))
    upc: Mapped[str | None] = mapped_column(String(20))
    disc_label: Mapped[str | None] = mapped_column(String(100))
    disc_number: Mapped[int] = mapped_column(SmallInteger, default=1)
    total_discs: Mapped[int] = mapped_column(SmallInteger, default=1)
    edition_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20), default="unverified"
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    disc_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("disc_sets.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # relationships
    titles: Mapped[list["DiscTitle"]] = relationship(
        back_populates="disc", cascade="all, delete-orphan"
    )
    releases: Mapped[list["Release"]] = relationship(
        secondary="disc_releases", back_populates="discs"
    )
    edits: Mapped[list["DiscEdit"]] = relationship(back_populates="disc")
    disc_set: Mapped["DiscSet | None"] = relationship(back_populates="discs")

    __table_args__ = (
        Index("idx_discs_fingerprint", "fingerprint"),
        Index("idx_discs_upc", "upc", postgresql_where="upc IS NOT NULL"),
        Index(
            "idx_discs_label",
            "disc_label",
            postgresql_where="disc_label IS NOT NULL",
        ),
        Index("idx_discs_status", "status"),
    )


# ---------------------------------------------------------------------------
# releases — canonical movie / TV release
# ---------------------------------------------------------------------------
class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    imdb_id: Mapped[str | None] = mapped_column(String(20))
    original_language: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    discs: Mapped[list["Disc"]] = relationship(
        secondary="disc_releases", back_populates="releases"
    )
    disc_sets: Mapped[list["DiscSet"]] = relationship(back_populates="release")

    __table_args__ = (
        Index(
            "idx_releases_tmdb",
            "tmdb_id",
            postgresql_where="tmdb_id IS NOT NULL",
        ),
        Index(
            "idx_releases_imdb",
            "imdb_id",
            postgresql_where="imdb_id IS NOT NULL",
        ),
    )


# ---------------------------------------------------------------------------
# disc_releases — join table: disc ↔ release (many-to-many)
# ---------------------------------------------------------------------------
class DiscRelease(Base):
    __tablename__ = "disc_releases"

    disc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("releases.id"),
        primary_key=True,
    )


# ---------------------------------------------------------------------------
# disc_titles — playback title / program on a disc
# ---------------------------------------------------------------------------
class DiscTitle(Base):
    __tablename__ = "disc_titles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    disc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discs.id", ondelete="CASCADE"), nullable=False
    )
    title_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title_type: Mapped[str | None] = mapped_column(String(30))
    duration_secs: Mapped[int | None] = mapped_column(Integer)
    chapter_count: Mapped[int | None] = mapped_column(SmallInteger)
    is_main_feature: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int | None] = mapped_column(SmallInteger)

    # relationships
    disc: Mapped["Disc"] = relationship(back_populates="titles")
    tracks: Mapped[list["DiscTrack"]] = relationship(
        back_populates="disc_title", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("disc_id", "title_index", name="uq_disc_titles_index"),
        Index("idx_disc_titles_disc", "disc_id"),
    )


# ---------------------------------------------------------------------------
# disc_tracks — audio / subtitle / video track on a disc title
# ---------------------------------------------------------------------------
class DiscTrack(Base):
    __tablename__ = "disc_tracks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    disc_title_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("disc_titles.id", ondelete="CASCADE"),
        nullable=False,
    )
    track_type: Mapped[str] = mapped_column(String(10), nullable=False)
    track_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(10))
    codec: Mapped[str | None] = mapped_column(String(30))
    channels: Mapped[int | None] = mapped_column(SmallInteger)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(200))

    # relationships
    disc_title: Mapped["DiscTitle"] = relationship(back_populates="tracks")

    __table_args__ = (
        Index("idx_disc_tracks_title", "disc_title_id"),
    )


# ---------------------------------------------------------------------------
# disc_sets — multi-disc grouping per R010
# ---------------------------------------------------------------------------
class DiscSet(Base):
    __tablename__ = "disc_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("releases.id"), nullable=False
    )
    edition_name: Mapped[str | None] = mapped_column(String(200))
    total_discs: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    release: Mapped["Release"] = relationship(back_populates="disc_sets")
    discs: Mapped[list["Disc"]] = relationship(back_populates="disc_set")

    __table_args__ = (
        Index("idx_disc_sets_release", "release_id"),
    )


# ---------------------------------------------------------------------------
# users — OAuth-ready (no password_hash per R005)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str] = mapped_column(String(20), default="contributor")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    submission_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_count: Mapped[int] = mapped_column(Integer, default=0)

    # relationships
    oauth_links: Mapped[list["UserOAuthLink"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# user_oauth_links — OAuth provider links per R005
# ---------------------------------------------------------------------------
class UserOAuthLink(Base):
    __tablename__ = "user_oauth_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    user: Mapped["User"] = relationship(back_populates="oauth_links")

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_oauth_provider_id"),
        Index("idx_user_oauth_links_user", "user_id"),
    )


# ---------------------------------------------------------------------------
# disc_edits — full edit history log
# ---------------------------------------------------------------------------
class DiscEdit(Base):
    __tablename__ = "disc_edits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    disc_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discs.id")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    edit_type: Mapped[str | None] = mapped_column(String(30))
    field_changed: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    edit_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    # relationships
    disc: Mapped["Disc | None"] = relationship(back_populates="edits")


# ---------------------------------------------------------------------------
# mastodon_oauth_clients — cache for dynamic client registration
# ---------------------------------------------------------------------------
class MastodonOAuthClient(Base):
    __tablename__ = "mastodon_oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
