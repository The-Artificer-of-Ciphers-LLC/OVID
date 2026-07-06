"""Tolerant structural-equality gate for two-contributor verification (D-03)."""

from collections import Counter

from sqlalchemy.orm import Session

from app.models import Disc, DiscTitle
from app.schemas import DiscSubmitRequest, TitleCreate

# Duration jitter accepted between two independent rips of the same disc (D-08:
# tunable launch-safe default, not a magic number). ±N seconds per title.
DURATION_TOLERANCE_SECS: int = 2


def _normalize_codec(codec: str | None) -> str | None:
    """Collapse codec labels so "AC-3", "ac3", "AC3" all compare equal.

    Lower-cases and strips every non-alphanumeric character. Returns None for
    None so an absent codec on both sides still matches.
    """
    if codec is None:
        return None
    return "".join(ch for ch in codec.lower() if ch.isalnum())


def _track_multiset(tracks) -> Counter:
    """Order-independent multiset keyed on (language, normalized codec, channels).

    Deliberately ignores positional ``track_index`` — two genuine rips may emit
    the same tracks in a different order (D-03 benign jitter).
    """
    return Counter(
        (t.language_code, _normalize_codec(t.codec), t.channels) for t in tracks
    )


def _title_matches(stored: DiscTitle, submitted: TitleCreate) -> bool:
    """Compare one stored title against its submitted counterpart (D-03 envelope)."""
    if stored.chapter_count != submitted.chapter_count:
        return False
    if stored.is_main_feature != submitted.is_main_feature:
        return False

    # Duration: only enforce when BOTH sides know it (fail-open on unknown, D-07).
    if stored.duration_secs is not None and submitted.duration_secs is not None:
        if abs(stored.duration_secs - submitted.duration_secs) > DURATION_TOLERANCE_SECS:
            return False

    stored_audio = [t for t in stored.tracks if t.track_type == "audio"]
    stored_subs = [t for t in stored.tracks if t.track_type == "subtitle"]
    if _track_multiset(stored_audio) != _track_multiset(submitted.audio_tracks):
        return False
    if _track_multiset(stored_subs) != _track_multiset(submitted.subtitle_tracks):
        return False

    return True


def structural_match(
    existing_disc: Disc, body: DiscSubmitRequest, db: Session
) -> bool:
    """Return True if the submitted structure reproduces the STORED disc structure.

    Proof-of-possession gate (D-01/D-03): compares the submitted
    ``DiscSubmitRequest`` against the withheld stored ``DiscTitle``/``DiscTrack``
    rows using a tolerant, canonical envelope — exact title count and per-title
    chapter counts, main-feature marker, track multisets (order-independent,
    codec-normalized), and duration within ``DURATION_TOLERANCE_SECS``. Reads no
    release-level (public) field, so a match proves the confirmer read a physical
    disc rather than echoing searchable metadata. Comparison-only: never mutates
    the disc, never writes status (VERIFY-02 boundary).
    """
    stored_titles = (
        db.query(DiscTitle).filter(DiscTitle.disc_id == existing_disc.id).all()
    )

    # CR-02: an empty structure is not proof of possession. Without this
    # check, two zero-title submissions "match" vacuously (the per-title
    # loop below runs zero times) — a title-less disc would auto-verify off
    # public release metadata alone, the exact echo attack this function
    # exists to prevent. A real disc pressing always has >=1 title, so a
    # title-less disc correctly stays unverifiable via this gate (fail-safe).
    if not stored_titles or not body.titles:
        return False

    if len(stored_titles) != len(body.titles):
        return False

    stored_by_index = {t.title_index: t for t in stored_titles}
    submitted_by_index = {t.title_index: t for t in body.titles}
    if set(stored_by_index) != set(submitted_by_index):
        return False

    for title_index, stored in stored_by_index.items():
        if not _title_matches(stored, submitted_by_index[title_index]):
            return False

    return True
