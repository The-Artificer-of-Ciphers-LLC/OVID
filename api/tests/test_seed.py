"""Tests for the bulk seed helper (api/scripts/seed.py).

Imports the seed module via sys.path (scripts/ is not a proper package),
mirroring test_sync_daemon.py. Drives ``bulk_seed`` against the SQLite
conftest ``db_session`` fixture (with its UUID round-trip support) so the
INFRA-03 load-test dataset builder gets an automated per-commit signal even
though the p95 load run itself is out-of-band.
"""

import sys
from pathlib import Path

# Make scripts/ importable (scripts/ is not a Python package).
_scripts_dir = str(Path(__file__).parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

import seed as seed_script  # noqa: E402

from app.models import Disc, Release  # noqa: E402


def test_bulk_seed_inserts_n_unique_discs(db_session):
    """bulk_seed(db, N) inserts exactly N discs, each with a unique fingerprint."""
    n = seed_script.bulk_seed(db_session, 25)

    assert n == 25
    assert db_session.query(Disc).count() == 25

    fingerprints = {d.fingerprint for d in db_session.query(Disc).all()}
    assert len(fingerprints) == 25  # every row is a genuine new disc


def test_bulk_seed_disc_is_lookup_and_search_resolvable(db_session):
    """A seeded disc is resolvable by its generated fingerprint and its
    title is matched by the shared search token."""
    seed_script.bulk_seed(db_session, 10)

    # Resolvable by a deterministic generated fingerprint (dvd1-seed-{i}).
    disc = (
        db_session.query(Disc)
        .filter(Disc.fingerprint == "dvd1-seed-3")
        .one_or_none()
    )
    assert disc is not None
    assert disc.status == "verified"  # lookups return full nested structure

    # Searchable by the shared title token the locustfile queries.
    hits = db_session.query(Release).filter(Release.title.ilike("%Seed%")).all()
    assert len(hits) == 10


def test_bulk_seed_zero_is_a_noop(db_session):
    """bulk_seed(db, 0) inserts no discs (boundary)."""
    n = seed_script.bulk_seed(db_session, 0)
    assert n == 0
    assert db_session.query(Disc).count() == 0
