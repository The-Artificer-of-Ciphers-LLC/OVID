#!/usr/bin/env python3
"""CC0 database dump — export all discs as gzipped NDJSON.

Produces a full snapshot of the OVID database in SyncDiffRecord shape,
suitable for bulk import by mirrors or third-party consumers.  After
writing the dump file, updates ``sync_state`` with snapshot metadata
so the ``/v1/sync/snapshot`` endpoint can advertise the latest dump.

Usage:
    python scripts/dump_cc0.py --output /tmp/ovid-dump.ndjson.gz

Environment:
    DATABASE_URL  SQLAlchemy database URL (required)

The dump is licensed CC0 — see the project LICENSE for details.
"""

import argparse
import gzip
import hashlib
import json
import logging
import os
import sys

# ---------------------------------------------------------------------------
# sys.path bootstrap — make `app.*` importable when run from project root
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_api_root = os.path.join(_project_root, "api")
if _api_root not in sys.path:
    sys.path.insert(0, _api_root)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker, subqueryload  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import Disc, DiscTitle, GlobalSeq, SyncState  # noqa: E402
from app.sync import build_sync_disc  # noqa: E402

logger = logging.getLogger("ovid.dump_cc0")


def make_engine(database_url: str | None = None):
    """Create a standalone engine from DATABASE_URL."""
    url = database_url or os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def dump_discs(database_url: str | None, output_path: str) -> None:
    """Export all discs to gzipped NDJSON and update snapshot metadata."""
    engine = make_engine(database_url)
    SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Use REPEATABLE READ for a consistent snapshot on PostgreSQL.
    # SQLite silently ignores this — catch and proceed.
    try:
        session = SessionFactory()
        session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    except Exception:
        logger.info("REPEATABLE READ not supported (likely SQLite); using default isolation")
        session = SessionFactory()

    try:
        # Read current global seq before dumping
        seq_row = session.query(GlobalSeq).filter_by(id=1).first()
        current_seq = seq_row.current_seq if seq_row else 0

        # Query all discs with eager-loaded relationships
        discs = (
            session.query(Disc)
            .options(
                subqueryload(Disc.titles).subqueryload(DiscTitle.tracks),
                subqueryload(Disc.releases),
            )
            .order_by(Disc.seq_num.asc().nullslast())
            .all()
        )

        # Write gzipped NDJSON
        sha256 = hashlib.sha256()
        record_count = 0

        with gzip.open(output_path, "wt", encoding="utf-8") as gz:
            for disc in discs:
                record = build_sync_disc(disc)
                line = record.model_dump_json() + "\n"
                gz.write(line)
                sha256.update(line.encode("utf-8"))
                record_count += 1

        file_size = os.path.getsize(output_path)
        digest = sha256.hexdigest()

        # Write snapshot metadata to sync_state (upsert pattern)
        metadata = {
            "snapshot_url": f"file://{os.path.abspath(output_path)}",
            "snapshot_seq": str(current_seq),
            "snapshot_size_bytes": str(file_size),
            "snapshot_record_count": str(record_count),
            "snapshot_sha256": digest,
        }

        for key, value in metadata.items():
            existing = session.query(SyncState).filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                session.add(SyncState(key=key, value=value))

        session.commit()

        logger.info(
            "dump_complete records=%d size_bytes=%d sha256=%s seq=%d path=%s",
            record_count,
            file_size,
            digest,
            current_seq,
            output_path,
        )
        print(f"Dump complete: {record_count} records, {file_size} bytes, sha256={digest}")

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Export OVID disc database as CC0-licensed gzipped NDJSON"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (e.g. /tmp/ovid-dump.ndjson.gz)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dump_discs(database_url=None, output_path=args.output)


if __name__ == "__main__":
    main()
