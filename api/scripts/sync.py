"""Sync daemon — polls canonical server's head/diff endpoints and upserts locally.

Runs as a standalone process (sidecar in Docker Compose mirror profile).
All functions are importable for testing; the daemon loop is guarded
behind ``if __name__ == '__main__'``.

Usage:
    python scripts/sync.py --once          # single sync pass then exit
    python scripts/sync.py --daemon        # continuous polling (default)

Environment:
    DATABASE_URL           SQLAlchemy database URL (required)
    SYNC_SOURCE_URL        Canonical API base URL (default: https://api.oviddb.org)
    SYNC_INTERVAL_MINUTES  Minutes between polls (default: 60)
"""

import argparse
import logging
import os
import signal
import sys
import time

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure the api/ package root is on sys.path so `app.*` imports work
# when the script is invoked as `python scripts/sync.py` from the api/ dir.
_script_dir = os.path.dirname(os.path.abspath(__file__))
_api_root = os.path.dirname(_script_dir)
if _api_root not in sys.path:
    sys.path.insert(0, _api_root)

from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    Disc,
    DiscRelease,
    DiscTitle,
    DiscTrack,
    Release,
    SyncState,
)

logger = logging.getLogger("ovid.sync")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def make_engine(database_url: str | None = None):
    """Create a standalone engine from DATABASE_URL (no FastAPI side-effects)."""
    url = database_url or os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine):
    """Create a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ---------------------------------------------------------------------------
# sync_state helpers
# ---------------------------------------------------------------------------

def get_last_seq(db: Session) -> int:
    """Return the last synced sequence number, or 0 if never synced."""
    row = db.query(SyncState).filter_by(key="last_seq").first()
    return int(row.value) if row else 0


def set_last_seq(db: Session, seq: int) -> None:
    """Upsert the last_seq value into sync_state."""
    row = db.query(SyncState).filter_by(key="last_seq").first()
    if row:
        row.value = str(seq)
    else:
        db.add(SyncState(key="last_seq", value=str(seq)))
    db.flush()


# ---------------------------------------------------------------------------
# Diff application
# ---------------------------------------------------------------------------

def _find_or_create_release(db: Session, release_data: dict) -> Release:
    """Find an existing release by tmdb_id or (title+year+content_type), or create one."""
    release = None

    # Prefer tmdb_id match
    tmdb_id = release_data.get("tmdb_id")
    if tmdb_id is not None:
        release = db.query(Release).filter_by(tmdb_id=tmdb_id).first()

    # Fallback: match on title + year + content_type
    if release is None:
        release = (
            db.query(Release)
            .filter_by(
                title=release_data["title"],
                year=release_data.get("year"),
                content_type=release_data["content_type"],
            )
            .first()
        )

    if release is None:
        release = Release(
            title=release_data["title"],
            year=release_data.get("year"),
            content_type=release_data["content_type"],
            tmdb_id=tmdb_id,
            imdb_id=release_data.get("imdb_id"),
            original_language=release_data.get("original_language"),
        )
        db.add(release)
        db.flush()

    return release


def _upsert_disc(db: Session, record: dict) -> Disc:
    """Find-or-create a Disc by fingerprint, updating scalar fields."""
    disc = db.query(Disc).filter_by(fingerprint=record["fingerprint"]).first()

    scalar_fields = [
        "format", "status", "region_code", "upc", "disc_label",
        "edition_name", "disc_number", "total_discs", "seq_num",
    ]

    if disc is None:
        disc = Disc(fingerprint=record["fingerprint"])
        for field in scalar_fields:
            if field in record:
                setattr(disc, field, record[field])
        db.add(disc)
        db.flush()
    else:
        for field in scalar_fields:
            if field in record:
                setattr(disc, field, record[field])
        db.flush()

    return disc


def _replace_titles(db: Session, disc: Disc, titles_data: list[dict]) -> None:
    """Delete existing titles+tracks for a disc and insert fresh ones."""
    # Delete existing tracks first (cascade), then titles
    existing_titles = db.query(DiscTitle).filter_by(disc_id=disc.id).all()
    for t in existing_titles:
        db.query(DiscTrack).filter_by(disc_title_id=t.id).delete()
    db.query(DiscTitle).filter_by(disc_id=disc.id).delete()
    db.flush()

    for title_data in titles_data:
        title = DiscTitle(
            disc_id=disc.id,
            title_index=title_data["title_index"],
            title_type=title_data.get("title_type"),
            duration_secs=title_data.get("duration_secs"),
            chapter_count=title_data.get("chapter_count"),
            is_main_feature=title_data.get("is_main_feature", False),
            display_name=title_data.get("display_name"),
        )
        db.add(title)
        db.flush()

        for track_data in title_data.get("tracks", []):
            track = DiscTrack(
                disc_title_id=title.id,
                track_type=track_data.get("track_type", "audio"),
                track_index=track_data.get("index", 0),
                language_code=track_data.get("language"),
                codec=track_data.get("codec"),
                channels=track_data.get("channels"),
                is_default=track_data.get("is_default", False),
            )
            db.add(track)

    db.flush()


def apply_diff(db: Session, records: list[dict]) -> int:
    """Apply a list of diff records to the local database. Returns count applied."""
    count = 0
    for record in records:
        # 1. Find-or-create release
        release = None
        release_data = record.get("release")
        if release_data:
            release = _find_or_create_release(db, release_data)

        # 2. Upsert disc
        disc = _upsert_disc(db, record)

        # 3. Link disc ↔ release if not already linked
        if release is not None:
            existing_link = (
                db.query(DiscRelease)
                .filter_by(disc_id=disc.id, release_id=release.id)
                .first()
            )
            if existing_link is None:
                db.add(DiscRelease(disc_id=disc.id, release_id=release.id))
                db.flush()

        # 4. Replace titles + tracks
        _replace_titles(db, disc, record.get("titles", []))

        count += 1

    return count


# ---------------------------------------------------------------------------
# Sync orchestration
# ---------------------------------------------------------------------------

def sync_once(source_url: str, db: Session, client: httpx.Client | None = None) -> int:
    """Run a single sync pass. Returns total records applied.

    If *client* is None a new httpx.Client is created (and closed) for
    this call.  Tests pass a mock client.
    """
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=httpx.Timeout(30.0, read=60.0))

    try:
        # Check head
        logger.info("sync_check_head url=%s", source_url)
        head_resp = client.get(f"{source_url}/v1/sync/head")
        head_resp.raise_for_status()
        head_data = head_resp.json()
        head_seq = head_data["seq"]

        last_seq = get_last_seq(db)

        if head_seq <= last_seq:
            logger.info("sync_up_to_date seq=%d", last_seq)
            return 0

        # Paged diff loop
        total = 0
        since = last_seq

        while True:
            logger.info("sync_page since=%d", since)
            diff_resp = client.get(
                f"{source_url}/v1/sync/diff",
                params={"since": since, "limit": 500},
            )
            diff_resp.raise_for_status()
            diff_data = diff_resp.json()

            records = diff_data["records"]
            applied = apply_diff(db, records)
            total += applied

            next_since = diff_data["next_since"]
            has_more = diff_data["has_more"]

            set_last_seq(db, next_since)
            db.commit()

            logger.info(
                "sync_page records=%d next_since=%d has_more=%s",
                applied, next_since, has_more,
            )

            if not has_more:
                break

            since = next_since

        logger.info("sync_complete total=%d", total)
        return total

    finally:
        if own_client:
            client.close()


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_signal(signum, _frame):
    """Signal handler for graceful shutdown."""
    global _shutdown_requested
    logger.info("sync_shutdown signal=%d", signum)
    _shutdown_requested = True


def run_daemon(source_url: str, interval_minutes: int, database_url: str | None = None):
    """Run the sync daemon in a continuous loop with exponential backoff on errors."""
    global _shutdown_requested
    _shutdown_requested = False

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    engine = make_engine(database_url)
    SessionLocal = make_session_factory(engine)

    backoff = 1  # minutes
    max_backoff = 30  # minutes

    logger.info(
        "sync_daemon_start source=%s interval=%dm",
        source_url, interval_minutes,
    )

    while not _shutdown_requested:
        db = SessionLocal()
        try:
            sync_once(source_url, db)
            backoff = 1  # reset on success
            sleep_secs = interval_minutes * 60
        except httpx.HTTPError as exc:
            logger.error(
                "sync_error error=%s backoff_secs=%d",
                str(exc), backoff * 60,
            )
            sleep_secs = backoff * 60
            backoff = min(backoff * 2, max_backoff)
        except Exception:
            logger.exception("sync_unexpected_error")
            sleep_secs = backoff * 60
            backoff = min(backoff * 2, max_backoff)
        finally:
            db.close()

        # Sleep in small increments so we can respond to signals
        for _ in range(sleep_secs):
            if _shutdown_requested:
                break
            time.sleep(1)

    logger.info("sync_daemon_stopped")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OVID sync daemon")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--once", action="store_true",
        help="Run a single sync pass and exit",
    )
    group.add_argument(
        "--daemon", action="store_true", default=True,
        help="Run continuously (default)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    source_url = os.environ.get("SYNC_SOURCE_URL", "https://api.oviddb.org")
    interval = int(os.environ.get("SYNC_INTERVAL_MINUTES", "60"))

    if args.once:
        engine = make_engine()
        SessionLocal = make_session_factory(engine)
        db = SessionLocal()
        try:
            total = sync_once(source_url, db)
            logger.info("sync_once_complete total=%d", total)
        finally:
            db.close()
    else:
        run_daemon(source_url, interval)


if __name__ == "__main__":
    main()
