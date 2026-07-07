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

# Auth config reads OVID_SECRET_KEY at import time — set a test value.
os.environ.setdefault("OVID_SECRET_KEY", "test-secret-key-for-unit-tests-32b")

# Auth config also requires OVID_ENV at import time (no default). This line is
# load-bearing: without it every api test fails to import once OVID_ENV became
# required. setdefault keeps any explicitly-exported value intact.
os.environ.setdefault("OVID_ENV", "development")

import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, GlobalSeq, Release, User  # noqa: E402
from app.auth.jwt import create_access_token  # noqa: E402


# ---------------------------------------------------------------------------
# SQLite WAL mode for test concurrency
# ---------------------------------------------------------------------------
# NOTE (IN-02): this hook does NOT do anything UUID-related — it only sets
# ``PRAGMA journal_mode=WAL`` for slightly better concurrency during tests.
# UUID round-tripping (uuid.UUID <-> str) needs no compat shim here: the
# ORM models use `sqlalchemy.dialects.postgresql.UUID(as_uuid=True)`, and
# that type's bind/result processors are dialect-independent pure-Python
# conversions — they transparently convert uuid.UUID <-> str against
# SQLite exactly as they would against PostgreSQL, with no extra event
# hook required. Confirmed by direct round-trip check against this same
# in-memory SQLite engine: values come back as `uuid.UUID` instances, not
# strings, both immediately after commit and after a fresh requery.

def _enable_sqlite_wal(engine):
    """Set PRAGMA journal_mode=WAL on every new connection (test concurrency only)."""
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):
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

_enable_sqlite_wal(_engine)

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
    # Seed the global_seq singleton row so next_seq() works in tests
    with _TestSession() as seed_db:
        seed_db.add(GlobalSeq(id=1, current_seq=0))
        seed_db.commit()
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear slowapi's in-memory storage between tests.

    Without this, rate limit counters accumulate across tests and cause
    spurious 429s.  We reset *before* each test so the limiter state is
    fresh regardless of prior test ordering or failure.
    """
    from app.rate_limit import limiter  # noqa: E402

    limiter.reset()
    yield


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
def seed_test_disc(
    db: Session,
    submitted_by_id: uuid.UUID | None = None,
    status: str = "verified",
) -> dict[str, uuid.UUID]:
    """Seed a disc + release + titles + tracks matching the Matrix pattern.

    ``status`` defaults to ``"verified"`` (existing behavior). Pass
    ``status="unverified"`` to seed a disc for the legitimate
    unverified->disputed path (VERIFY-02 / Phase 1 Plan 03).

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
        status=status,
        submitted_by=submitted_by_id,
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


def matrix_matching_submit_payload() -> dict:
    """A POST /v1/disc payload whose STRUCTURE reproduces ``seed_test_disc``'s
    Matrix disc and whose RELEASE matches it.

    Kept in lockstep with ``seed_test_disc`` (title_index 1, 39 chapters,
    main-feature marker, en/ac3/6ch audio, en/vobsub subtitle; The Matrix /
    1999 / tmdb 603) so a second-contributor re-submission of this payload
    satisfies ``structural_match`` AND ``_releases_match`` and auto-verifies
    (D-01/D-03). Callers mutate a deep copy to drive the mismatch/jitter
    boundary cases.
    """
    return {
        "fingerprint": "dvd-ABC123-main",
        "format": "DVD",
        "region_code": "1",
        "release": {
            "title": "The Matrix",
            "year": 1999,
            "content_type": "movie",
            "tmdb_id": 603,
            "imdb_id": "tt0133093",
            "original_language": "en",
        },
        "titles": [
            {
                "title_index": 1,
                "title_type": "main_feature",
                "duration_secs": 8160,
                "chapter_count": 39,
                "is_main_feature": True,
                "display_name": "The Matrix",
                "audio_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "ac3",
                        "channels": 6,
                        "is_default": True,
                    }
                ],
                "subtitle_tracks": [
                    {
                        "track_index": 0,
                        "language_code": "en",
                        "codec": "vobsub",
                        "is_default": False,
                    }
                ],
            }
        ],
    }


@pytest.fixture()
def seeded_disc(db_session: Session) -> dict[str, uuid.UUID]:
    """Fixture wrapper around seed_test_disc for easy injection."""
    return seed_test_disc(db_session)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def seed_test_user(db: Session) -> User:
    """Create a test user and return the ORM object."""
    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        display_name="Test User",
        role="contributor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def test_user(db_session: Session) -> User:
    """Fixture that creates and returns a test user."""
    return seed_test_user(db_session)


@pytest.fixture()
def auth_header(test_user: User) -> dict[str, str]:
    """Return an Authorization header dict with a valid JWT for the test user."""
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def seeded_disc_with_owner(db_session: Session, test_user: User) -> dict[str, uuid.UUID]:
    """Seed a disc with submitted_by set to the test user."""
    return seed_test_disc(db_session, submitted_by_id=test_user.id)


# ---------------------------------------------------------------------------
# Second user helpers (for two-contributor verification tests)
# ---------------------------------------------------------------------------
def seed_second_user(db: Session) -> User:
    """Create a second test user and return the ORM object."""
    user = User(
        id=uuid.uuid4(),
        username="testuser2",
        email="test2@example.com",
        display_name="Test User 2",
        role="contributor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def second_user(db_session: Session) -> User:
    """Fixture that creates and returns a second test user."""
    return seed_second_user(db_session)


@pytest.fixture()
def second_auth_header(second_user: User) -> dict[str, str]:
    """Return an Authorization header dict with a valid JWT for the second user."""
    token = create_access_token(second_user.id)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Trusted user helpers (for dispute resolution tests)
# ---------------------------------------------------------------------------
def seed_trusted_user(db: Session) -> User:
    """Create a trusted test user and return the ORM object."""
    user = User(
        id=uuid.uuid4(),
        username="trusted_user",
        email="trusted@test.local",
        display_name="Trusted User",
        role="trusted",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def trusted_user(db_session: Session) -> User:
    """Fixture that creates and returns a trusted test user."""
    return seed_trusted_user(db_session)


# ---------------------------------------------------------------------------
# Account-age override helper (VERIFY-04 anti-Sybil soft-signal tests)
# ---------------------------------------------------------------------------
def make_user_with_age(
    db: Session,
    *,
    hours_old: float,
    username: str,
    email: str,
) -> User:
    """Create a User whose ``created_at`` is ``hours_old`` hours in the past.

    Lets the account-age branch of the anti-Sybil weighted trust score be
    exercised deterministically (fresh vs. established confirmer) without
    altering the fixed-age ``test_user``/``second_user`` fixtures.
    """
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=email,
        display_name=username,
        role="contributor",
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def trusted_auth_header(trusted_user: User) -> dict[str, str]:
    """Return an Authorization header dict with a valid JWT for the trusted user."""
    token = create_access_token(trusted_user.id)
    return {"Authorization": f"Bearer {token}"}



# ---------------------------------------------------------------------------
# Disc set helpers (Phase 2)
# ---------------------------------------------------------------------------
def seed_test_disc_set(
    db: Session,
    release_id: uuid.UUID,
    edition_name: str = "Extended Edition",
    total_discs: int = 4,
) -> uuid.UUID:
    """Create a disc set and return its UUID."""
    from app.models import DiscSet
    disc_set = DiscSet(
        release_id=release_id,
        edition_name=edition_name,
        total_discs=total_discs,
    )
    db.add(disc_set)
    db.commit()
    db.refresh(disc_set)
    return disc_set.id
