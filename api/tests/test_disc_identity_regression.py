"""Permanent regression guard for `dvd1-*` (OVID-DVD-1) identity resolution.

# guardrail: IDENT-05

This is an UNMARKED, unconditional pytest — it is collected by the plain
``pytest tests/`` invocation CI runs on every push/PR (see
``.github/workflows/ci.yml``), with no hardware fixture and no skip marker.
It seeds a golden `dvd1-`-prefixed pressing as a real ORM record (mirroring
``conftest.seed_test_disc``'s structure, NOT a synthetic/JSON-snapshot
fixture) and asserts that looking it up via ``GET /v1/disc/{fingerprint}``
still resolves the correct disc and returns the exact structure that was
seeded.

Per the phase-1 assumption-delta decisions:

- D-14: the expected structure below is a HARDCODED dict written directly
  in this test body, independent of the seeder's local variables, so the
  assertion catches silent data drift rather than being tautological.
- D-16: the test asserts stable disc *identity* (the persisted disc/release
  row) and *structure* resolved by looking up the fixed `dvd1-*` string --
  it does NOT assert ``response["fingerprint"] == "dvd1-...``. After the
  Phase 5 libdvdread promotion, `dvd1-*` may become a Lookup Alias to a
  `dvdread1-*` primary (see ``app/disc_identity.py:resolve_disc_identity``
  and the alias-lookup tolerance in
  ``test_disc_identity_aliases.py::test_register_duplicate_persists_new_alias``),
  so pinning the literal top-level ``fingerprint`` value would make this
  guardrail fail for the *correct*, intended future behavior.

If this test ever goes red, it means resolution of a pre-migration
`dvd1-*` Disc Identity string has silently regressed -- exactly the
fragmentation ADR 0001 forbids.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import Disc, DiscRelease, DiscTitle, DiscTrack, Release


# The golden Primary Fingerprint under test. Deliberately a `dvd1-*`
# (OVID-DVD-1) string per docs/fingerprint-spec.md, representing a real
# pre-libdvdread-migration identity -- distinct from `seed_test_disc`'s
# `dvd-ABC123-main` (conftest.py does not itself produce a `dvd1-*` value,
# per RESEARCH Pattern 3).
DVD1_GOLDEN_FINGERPRINT = "dvd1-golden-9f3c7a1b"


def seed_dvd1_golden_disc(db: Session) -> dict[str, uuid.UUID]:
    """Seed a golden `dvd1-*` pressing with a fully-specified structure.

    Mirrors ``conftest.seed_test_disc``'s insertion order (release -> Disc
    -> flush -> DiscRelease link -> DiscTitle -> DiscTrack) but uses a
    dedicated `dvd1-`-prefixed fingerprint and its own fixed values, kept
    local to this file so it never drifts alongside the shared fixture.
    """
    release = Release(
        title="Golden Test Film",
        year=2005,
        content_type="movie",
        tmdb_id=99001,
        imdb_id="tt9990001",
        original_language="en",
    )
    db.add(release)
    db.flush()

    disc = Disc(
        fingerprint=DVD1_GOLDEN_FINGERPRINT,
        format="DVD",
        region_code="1",
        upc="000111222333",
        disc_label="GOLDEN_D1",
        disc_number=1,
        total_discs=1,
        edition_name="Golden Edition",
        status="verified",
    )
    db.add(disc)
    db.flush()

    db.execute(
        DiscRelease.__table__.insert().values(disc_id=disc.id, release_id=release.id)
    )

    title = DiscTitle(
        disc_id=disc.id,
        title_index=1,
        title_type="main_feature",
        duration_secs=7200,
        chapter_count=24,
        is_main_feature=True,
        display_name="Golden Test Film",
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


class TestDvd1GoldenRegression:
    """# guardrail: IDENT-05 -- frozen dvd1-* resolution and structure."""

    def test_dvd1_golden_pressing_resolves_with_frozen_structure(
        self, client, db_session: Session
    ) -> None:
        seed_ids = seed_dvd1_golden_disc(db_session)

        # --- (a) resolves 200 by the fixed dvd1-* string ---------------
        resp = client.get(f"/v1/disc/{DVD1_GOLDEN_FINGERPRINT}")
        assert resp.status_code == 200
        body = resp.json()

        # --- (b) persisted disc identity / release is the seeded one ---
        # Resolved via the DB directly (not the response body) so this
        # assertion is independent of any future response-shape change.
        db_session.expire_all()
        resolved_disc = (
            db_session.query(Disc)
            .filter(Disc.fingerprint == DVD1_GOLDEN_FINGERPRINT)
            .one()
        )
        assert resolved_disc.id == seed_ids["disc_id"]
        resolved_release_link = (
            db_session.query(DiscRelease)
            .filter(DiscRelease.disc_id == resolved_disc.id)
            .one()
        )
        assert resolved_release_link.release_id == seed_ids["release_id"]

        # --- (c) normalized structure matches a HARDCODED expected dict
        # (D-14) -- independent of the seeder's local variables above, so
        # this catches silent data drift, not just a 200. Deliberately
        # excludes the top-level `fingerprint` field (D-16): after the
        # Phase 5 libdvdread promotion `dvd1-*` may resolve as a Lookup
        # Alias to a different `dvdread1-*` primary, and this guardrail
        # must keep passing when that happens.
        expected_structure = {
            "format": "DVD",
            "status": "verified",
            "region_code": "1",
            "upc": "000111222333",
            "edition_name": "Golden Edition",
            "disc_number": 1,
            "total_discs": 1,
            "release": {
                "title": "Golden Test Film",
                "year": 2005,
                "content_type": "movie",
                "tmdb_id": 99001,
                "imdb_id": "tt9990001",
            },
            "titles": [
                {
                    "title_index": 1,
                    "is_main_feature": True,
                    "title_type": "main_feature",
                    "display_name": "Golden Test Film",
                    "duration_secs": 7200,
                    "chapter_count": 24,
                    "audio_tracks": [
                        {
                            "index": 0,
                            "language": "en",
                            "codec": "ac3",
                            "channels": 6,
                            "is_default": True,
                        }
                    ],
                    "subtitle_tracks": [
                        {
                            "index": 0,
                            "language": "en",
                            "codec": "vobsub",
                            "channels": None,
                            "is_default": False,
                        }
                    ],
                    "chapters": [],
                }
            ],
        }

        actual_structure = {key: body[key] for key in expected_structure}
        assert actual_structure == expected_structure
