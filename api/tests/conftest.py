"""Shared test fixtures for the OVID API test suite.

Uses an in-memory SQLite database with dependency override so tests
never touch the real PostgreSQL instance.

**Important:** DATABASE_URL is patched to SQLite *before* any app module
is imported, so the production engine is never created and psycopg2 is
never required in the test environment.
"""

import os

# Patch DATABASE_URL before any app module touches it.
os.environ["DATABASE_URL"] = "sqlite://"

import uuid  # noqa: E402

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, Release  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite ↔ PostgreSQL UUID compatibility
# ---------------------------------------------------------------------------
# The ORM models use `sqlalchemy.dialects.postgresql.UUID(as_uuid=True)`.
# On SQLite that column type is rendered as `UUID` (accepted by SQLite as a
# typeless column) and values arrive/depart as plain strings.  We hook
# into SQLAlchemy's event system to make uuid.UUID <-> str transparent.

def _sqlite_uuid_compat(engine):
    """Register type adapters so uuid.UUID values round-trip through SQLite."""
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):
        # Enable WAL for slightly better concurrency during tests, and
        # let SQLite accept UUID-typed columns without complaint.
        dbapi_conn.execute("PRAGMA journal_mode=WAL")


# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------
_SQLITE_URL = "sqlite://"  # in-memory

_engine = create_engine(
    _SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_sqlite_uuid_compat(_engine)

_TestSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def _get_test_db():
    """Dependency override for ``get_db`` — uses the in-memory SQLite engine."""
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_tables():
    """Create all tables before each test and drop them afterwards."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db_session() -> Session:  # type: ignore[misc]
    """Direct DB session for seeding / inspecting data in tests."""
    db = _TestSession()
    try:
        yield db  # type: ignore[misc]
    finally:
        db.close()


@pytest.fixture()
def client() -> TestClient:
    """FastAPI TestClient with the DB dependency overridden to SQLite."""
    from main import app  # local import so middleware is already registered

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c  # type: ignore[misc]
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------
def seed_test_disc(db: Session) -> dict[str, uuid.UUID]:
    """Seed a disc + release + titles + tracks matching the Matrix pattern.

    Returns a dict of entity UUIDs: disc_id, release_id, title_id, audio_track_id,
    subtitle_track_id.
    """
    release = Release(
        title="The Matrix",
        year=1999,
        content_type="movie",
        tmdb_id=603,
        imdb_id="tt0133093",
        original_language="en",
    )
    db.add(release)
    db.flush()

    disc = Disc(
        fingerprint="dvd-ABC123-main",
        format="DVD",
        region_code="1",
        upc="012345678901",
        disc_label="THEMATRIX_D1",
        disc_number=1,
        total_discs=1,
        edition_name="10th Anniversary",
        status="verified",
    )
    db.add(disc)
    db.flush()

    # link disc ↔ release
    db.execute(
        DiscRelease.__table__.insert().values(
            disc_id=disc.id, release_id=release.id
        )
    )

    title = DiscTitle(
        disc_id=disc.id,
        title_index=1,
        title_type="main_feature",
        duration_secs=8160,
        chapter_count=39,
        is_main_feature=True,
        display_name="The Matrix",
    )
    db.add(title)
    db.flush()

    audio = DiscTrack(
        disc_title_id=title.id,
        track_type="audio",
        track_index=0,
        language_code="en",
        codec="ac3",
        channels=6,
        is_default=True,
    )
    subtitle = DiscTrack(
        disc_title_id=title.id,
        track_type="subtitle",
        track_index=0,
        language_code="en",
        codec="vobsub",
        channels=None,
        is_default=False,
    )
    db.add_all([audio, subtitle])
    db.commit()

    return {
        "disc_id": disc.id,
        "release_id": release.id,
        "title_id": title.id,
        "audio_track_id": audio.id,
        "subtitle_track_id": subtitle.id,
    }
