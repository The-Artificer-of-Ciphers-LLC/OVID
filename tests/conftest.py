"""Repo-root E2E test conftest — bridges ovid-client and API test infrastructure.

Sets DATABASE_URL and OVID_SECRET_KEY *before* any api module is imported
(per K008: api/app/database.py creates an engine at module scope).

Provides:
  - Synthetic disc fixture builders (from ovid-client/tests/conftest.py)
  - FastAPI TestClient wired to an in-memory SQLite database
  - Auth helpers (test user + JWT header)
  - A ``write_fixture_folder`` helper for materialising IFO bytes on disk
"""

from __future__ import annotations

import os

# ── Env vars MUST be set before any app.* import (K008) ──────────────
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("OVID_SECRET_KEY", "test-secret-key-for-e2e-tests-32byte")

import uuid  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# API internals — safe to import now that DATABASE_URL is patched
from app.database import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.models import User  # noqa: E402
from app.auth.jwt import create_access_token  # noqa: E402

# ovid-client is on PYTHONPATH but we don't import anything here;
# the test module imports ovid.disc and ovid.cli directly.


# ---------------------------------------------------------------------------
# SQLite engine (mirrors api/tests/conftest.py, standalone for isolation)
# ---------------------------------------------------------------------------

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(_engine, "connect")
def _on_connect(dbapi_conn, _connection_record):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")


_TestSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def _get_test_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_tables():
    """Create all tables before each test, drop afterwards."""
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture()
def db_session() -> Session:  # type: ignore[misc]
    db = _TestSession()
    try:
        yield db  # type: ignore[misc]
    finally:
        db.close()


@pytest.fixture()
def client() -> TestClient:
    """FastAPI TestClient with SQLite DB override."""
    from main import app  # noqa: E402  — deferred so middleware is registered

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c  # type: ignore[misc]
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        username="e2e_user",
        email="e2e@example.com",
        display_name="E2E User",
        role="contributor",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_header(test_user: User) -> dict[str, str]:
    token = create_access_token(test_user.id)
    return {"Authorization": f"Bearer {token}"}
