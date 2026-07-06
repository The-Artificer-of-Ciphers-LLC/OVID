"""Seed script — populate OVID database with realistic test data.

Two modes:

* No arguments (default) — idempotent single-disc seed of the canonical
  Matrix disc, keyed on ``FINGERPRINT``; safe to re-run.
* ``--count N`` — bulk-seed N synthetic *verified* discs with unique
  deterministic fingerprints (``dvd1-seed-{i}``) and searchable titles
  (``Seed Movie {i}``) for the INFRA-03 load test (D-13). Each row is a
  genuine new disc with a minimal-but-representative structure (one
  main-feature title + audio/subtitle track) so ``GET /v1/disc/{fp}``
  exercises the real nested-read cost and ``GET /v1/search?q=Seed`` matches.

Run inside the api container:
    docker compose exec api python scripts/seed.py
    docker compose exec api python scripts/seed.py --count 3000
"""

import argparse
import sys
import uuid
from pathlib import Path

# Ensure /app is on sys.path when run from /app/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import (
    Disc,
    DiscEdit,
    DiscRelease,
    DiscSet,
    DiscTitle,
    DiscTrack,
    Release,
    User,
    UserOAuthLink,
)

FINGERPRINT = "dvd1-matrix-1999-r1-us"

# --- Bulk-seed (load-test dataset, D-13) ---------------------------------
# The locustfile reproduces these two constants: it builds lookup URLs from
# BULK_FINGERPRINT_PREFIX + index and queries BULK_TITLE_TOKEN via search.
BULK_FINGERPRINT_PREFIX = "dvd1-seed-"
BULK_TITLE_TOKEN = "Seed"


def bulk_seed(db, count: int) -> int:
    """Insert ``count`` synthetic verified discs for the load-test dataset.

    Each disc gets a UNIQUE deterministic fingerprint (``dvd1-seed-{i}``),
    a Release whose title shares a common searchable token
    (``Seed Movie {i}`` → matched by ``GET /v1/search?q=Seed``), ``verified``
    status (so lookups return the full nested structure and represent the
    real read cost), and a minimal-but-representative title/track set (one
    main-feature title plus an audio + subtitle track). Rows are kept light
    so seeding low-thousands is fast.

    The session is caller-owned: this function commits the batch on success
    but does NOT close the session (the CLI runner / test fixture manages
    lifecycle). Returns the number of discs inserted.
    """
    if count < 0:
        raise ValueError("count must be >= 0")

    if count == 0:
        return 0

    # One shared contributor owns every seeded disc. A random suffix keeps
    # the username/email unique across repeated bulk runs against the same DB.
    suffix = uuid.uuid4().hex[:8]
    submitter = User(
        id=uuid.uuid4(),
        username=f"seedbot-{suffix}",
        email=f"seedbot-{suffix}@seed.local",
        display_name="Load-test Seed Bot",
        email_verified=True,
        role="contributor",
    )
    db.add(submitter)
    db.flush()

    for i in range(count):
        release = Release(
            id=uuid.uuid4(),
            title=f"{BULK_TITLE_TOKEN} Movie {i}",
            year=2000 + (i % 25),
            content_type="movie",
            original_language="en",
        )
        db.add(release)
        db.flush()

        disc = Disc(
            id=uuid.uuid4(),
            fingerprint=f"{BULK_FINGERPRINT_PREFIX}{i}",
            format="DVD",
            region_code="1",
            disc_label=f"SEED_{i}",
            disc_number=1,
            total_discs=1,
            status="verified",
            submitted_by=submitter.id,
        )
        db.add(disc)
        db.flush()

        db.add(DiscRelease(disc_id=disc.id, release_id=release.id))

        title = DiscTitle(
            id=uuid.uuid4(),
            disc_id=disc.id,
            title_index=1,
            title_type="main_feature",
            duration_secs=6000 + i,
            chapter_count=12,
            is_main_feature=True,
            display_name=f"{BULK_TITLE_TOKEN} Movie {i}",
            sort_order=1,
        )
        db.add(title)
        db.flush()

        db.add_all(
            [
                DiscTrack(
                    disc_title_id=title.id,
                    track_type="audio",
                    track_index=1,
                    language_code="en",
                    codec="ac3",
                    channels=6,
                    is_default=True,
                    description="English 5.1 Surround",
                ),
                DiscTrack(
                    disc_title_id=title.id,
                    track_type="subtitle",
                    track_index=1,
                    language_code="en",
                    codec="vobsub",
                    is_default=True,
                    description="English",
                ),
            ]
        )

        # Bound in-flight state on large batches without committing partials.
        if i % 500 == 499:
            db.flush()

    db.commit()
    return count


def _run_bulk(count: int) -> None:
    """CLI wrapper around ``bulk_seed`` that owns the real-DB session."""
    db = SessionLocal()
    try:
        n = bulk_seed(db, count)
        print(f"[seed] Bulk-seeded {n} discs (fingerprints {BULK_FINGERPRINT_PREFIX}0..{n - 1}).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed() -> None:
    db = SessionLocal()
    try:
        # Idempotency check — if the fingerprint exists, skip seeding
        existing = db.query(Disc).filter(Disc.fingerprint == FINGERPRINT).first()
        if existing:
            print(f"[seed] Disc '{FINGERPRINT}' already exists — skipping.")
            return

        # --- User ---
        user = User(
            id=uuid.uuid4(),
            username="testcontributor",
            email="test@example.com",
            display_name="Test Contributor",
            email_verified=True,
            role="contributor",
        )
        db.add(user)
        db.flush()

        # --- OAuth link ---
        oauth_link = UserOAuthLink(
            user_id=user.id,
            provider="github",
            provider_id="gh-123456",
        )
        db.add(oauth_link)

        # --- Release ---
        release = Release(
            id=uuid.uuid4(),
            title="The Matrix",
            year=1999,
            content_type="movie",
            tmdb_id=603,
            imdb_id="tt0133093",
            original_language="en",
        )
        db.add(release)
        db.flush()

        # --- Disc set ---
        disc_set = DiscSet(
            id=uuid.uuid4(),
            release_id=release.id,
            edition_name="Original US Release",
            total_discs=1,
        )
        db.add(disc_set)
        db.flush()

        # --- Disc ---
        disc = Disc(
            id=uuid.uuid4(),
            fingerprint=FINGERPRINT,
            format="DVD",
            region_code="1",
            upc="085391200024",
            disc_label="THE_MATRIX",
            disc_number=1,
            total_discs=1,
            edition_name="Original US Release",
            status="unverified",
            submitted_by=user.id,
            disc_set_id=disc_set.id,
        )
        db.add(disc)
        db.flush()

        # --- disc_releases join ---
        disc_release = DiscRelease(disc_id=disc.id, release_id=release.id)
        db.add(disc_release)

        # --- Disc titles ---
        # 1. Main feature
        main_title = DiscTitle(
            id=uuid.uuid4(),
            disc_id=disc.id,
            title_index=1,
            title_type="main_feature",
            duration_secs=8100,
            chapter_count=32,
            is_main_feature=True,
            display_name="The Matrix",
            sort_order=1,
        )
        # 2. Bonus: Making Of
        bonus1 = DiscTitle(
            id=uuid.uuid4(),
            disc_id=disc.id,
            title_index=2,
            title_type="bonus",
            duration_secs=600,
            chapter_count=1,
            is_main_feature=False,
            display_name="Making Of The Matrix",
            sort_order=2,
        )
        # 3. Bonus: Behind the scenes
        bonus2 = DiscTitle(
            id=uuid.uuid4(),
            disc_id=disc.id,
            title_index=3,
            title_type="bonus",
            duration_secs=600,
            chapter_count=1,
            is_main_feature=False,
            display_name="Behind the Scenes",
            sort_order=3,
        )
        # 4. Trailer
        trailer = DiscTitle(
            id=uuid.uuid4(),
            disc_id=disc.id,
            title_index=4,
            title_type="trailer",
            duration_secs=120,
            chapter_count=1,
            is_main_feature=False,
            display_name="Theatrical Trailer",
            sort_order=4,
        )
        db.add_all([main_title, bonus1, bonus2, trailer])
        db.flush()

        # --- Audio tracks on main feature ---
        audio_en = DiscTrack(
            disc_title_id=main_title.id,
            track_type="audio",
            track_index=1,
            language_code="en",
            codec="ac3",
            channels=6,
            is_default=True,
            description="English 5.1 Surround",
        )
        audio_fr = DiscTrack(
            disc_title_id=main_title.id,
            track_type="audio",
            track_index=2,
            language_code="fr",
            codec="ac3",
            channels=2,
            is_default=False,
            description="French 2.0 Stereo",
        )
        # --- Subtitle tracks on main feature ---
        sub_en = DiscTrack(
            disc_title_id=main_title.id,
            track_type="subtitle",
            track_index=1,
            language_code="en",
            codec="vobsub",
            is_default=True,
            description="English",
        )
        sub_es = DiscTrack(
            disc_title_id=main_title.id,
            track_type="subtitle",
            track_index=2,
            language_code="es",
            codec="vobsub",
            is_default=False,
            description="Spanish",
        )
        db.add_all([audio_en, audio_fr, sub_en, sub_es])

        # --- Disc edit (audit trail) ---
        edit = DiscEdit(
            disc_id=disc.id,
            user_id=user.id,
            edit_type="create",
            edit_note="Initial submission via seed script",
        )
        db.add(edit)

        db.commit()
        print(f"[seed] Seeded disc '{FINGERPRINT}' with 4 titles, 4 tracks, 1 edit.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the OVID database.")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=(
            "Bulk-seed N synthetic verified discs (dvd1-seed-{i}) for load "
            "testing. Omit for the idempotent single-Matrix seed."
        ),
    )
    args = parser.parse_args()

    if args.count is not None:
        _run_bulk(args.count)
    else:
        seed()
