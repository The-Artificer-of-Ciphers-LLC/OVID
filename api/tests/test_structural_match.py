"""Boundary tests for the D-03 tolerant structural-equality verify gate.

`structural_match(existing_disc, body, db)` is the proof-of-possession gate: a
second contributor's submitted `DiscSubmitRequest` is compared against the STORED
`DiscTitle`/`DiscTrack` rows of an existing disc. The tolerance envelope must
accept benign independent-rip jitter (reordered tracks, relabeled codec, ±1-2s
duration) yet still reject real structural differences (wrong title/chapter
count, missing track, different language) — which route to the dispute path.

Each test varies ONE axis at a time against the Matrix seed
(1 title, chapter_count=39, duration_secs=8160, 1 audio ac3/en/6ch,
1 subtitle vobsub/en). No test asserts positional track_index equality:
tracks compare as sorted multisets keyed on (language_code, codec, channels).
"""

from sqlalchemy.orm import Session

from app.models import Disc, DiscTitle, DiscTrack
from app.schemas import DiscSubmitRequest, ReleaseCreate, TitleCreate, TrackCreate
from app.structural_match import structural_match
from tests.conftest import seed_test_disc


# ---------------------------------------------------------------------------
# Payload builders — mirror the Matrix seed, override one axis per test
# ---------------------------------------------------------------------------
def _matrix_title(**overrides) -> TitleCreate:
    defaults = dict(
        title_index=1,
        chapter_count=39,
        is_main_feature=True,
        duration_secs=8160,
        audio_tracks=[
            TrackCreate(track_index=0, language_code="en", codec="ac3", channels=6)
        ],
        subtitle_tracks=[
            TrackCreate(
                track_index=0, language_code="en", codec="vobsub", channels=None
            )
        ],
    )
    defaults.update(overrides)
    return TitleCreate(**defaults)


def _body(titles=None) -> DiscSubmitRequest:
    return DiscSubmitRequest(
        fingerprint="dvd-ABC123-main",
        format="DVD",
        release=ReleaseCreate(title="The Matrix", content_type="movie"),
        titles=titles if titles is not None else [_matrix_title()],
    )


def _stored_disc(db: Session) -> tuple[Disc, dict]:
    seed = seed_test_disc(db, status="unverified")
    disc = db.get(Disc, seed["disc_id"])
    return disc, seed


def _add_second_audio(db: Session, seed: dict) -> None:
    """Give the stored title a 2nd audio track (fr/dts/2ch) for multiset tests."""
    db.add(
        DiscTrack(
            disc_title_id=seed["title_id"],
            track_type="audio",
            track_index=1,
            language_code="fr",
            codec="dts",
            channels=2,
            is_default=False,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Match (returns True) — benign independent-rip jitter
# ---------------------------------------------------------------------------
def test_exact_match(db_session: Session):
    disc, _ = _stored_disc(db_session)
    assert structural_match(disc, _body(), db_session) is True


def test_reordered_audio_tracks_match(db_session: Session):
    disc, seed = _stored_disc(db_session)
    _add_second_audio(db_session, seed)
    db_session.refresh(disc)
    # Submit the two audio tracks in the OPPOSITE order to stored.
    title = _matrix_title(
        audio_tracks=[
            TrackCreate(track_index=0, language_code="fr", codec="dts", channels=2),
            TrackCreate(track_index=1, language_code="en", codec="ac3", channels=6),
        ]
    )
    assert structural_match(disc, _body([title]), db_session) is True


def test_relabeled_codec_matches(db_session: Session):
    disc, _ = _stored_disc(db_session)
    # Stored "ac3" vs submitted "AC-3" — normalize before compare.
    title = _matrix_title(
        audio_tracks=[
            TrackCreate(track_index=0, language_code="en", codec="AC-3", channels=6)
        ]
    )
    assert structural_match(disc, _body([title]), db_session) is True


def test_duration_within_tolerance_matches(db_session: Session):
    disc, _ = _stored_disc(db_session)
    title = _matrix_title(duration_secs=8161)  # +1s, within DURATION_TOLERANCE_SECS
    assert structural_match(disc, _body([title]), db_session) is True


# ---------------------------------------------------------------------------
# Not-a-match (returns False) — real structural difference
# ---------------------------------------------------------------------------
def test_extra_title_no_match(db_session: Session):
    disc, _ = _stored_disc(db_session)
    second = _matrix_title(title_index=2, chapter_count=12, is_main_feature=False)
    assert structural_match(disc, _body([_matrix_title(), second]), db_session) is False


def test_different_chapter_count_no_match(db_session: Session):
    disc, _ = _stored_disc(db_session)
    title = _matrix_title(chapter_count=40)
    assert structural_match(disc, _body([title]), db_session) is False


def test_missing_audio_track_no_match(db_session: Session):
    disc, seed = _stored_disc(db_session)
    _add_second_audio(db_session, seed)  # stored now has 2 audio tracks
    db_session.refresh(disc)
    # Submit only 1 audio track — a missing track must NOT verify.
    assert structural_match(disc, _body(), db_session) is False


def test_different_language_no_match(db_session: Session):
    disc, _ = _stored_disc(db_session)
    title = _matrix_title(
        audio_tracks=[
            TrackCreate(track_index=0, language_code="fr", codec="ac3", channels=6)
        ]
    )
    assert structural_match(disc, _body([title]), db_session) is False


def test_duration_outside_tolerance_no_match(db_session: Session):
    disc, _ = _stored_disc(db_session)
    title = _matrix_title(duration_secs=8200)  # +40s, well outside tolerance
    assert structural_match(disc, _body([title]), db_session) is False
