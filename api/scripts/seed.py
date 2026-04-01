"""Seed script — populate OVID database with realistic test data.

Idempotent: checks for existing disc by fingerprint before inserting.
Run inside the api container:
    docker compose exec api python scripts/seed.py
"""

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
    seed()
