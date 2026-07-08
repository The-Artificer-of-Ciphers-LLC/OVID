"""Server-side Disc Identity resolution and Lookup Alias persistence."""

import uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Disc, DiscIdentityAlias, FingerprintRegistry
from app.schemas import SiblingDiscSummary


@dataclass(frozen=True)
class IdentityResolution:
    """A resolved Disc Identity string and the primary disc it names."""

    disc: Disc
    matched_fingerprint: str
    matched_via_alias: bool


class DiscIdentityConflict(Exception):
    """Raised when one submitted identity string points at another disc."""

    def __init__(self, fingerprint: str, existing_disc: Disc) -> None:
        self.fingerprint = fingerprint
        self.existing_disc = existing_disc
        super().__init__(
            f"Disc Identity '{fingerprint}' already resolves to another disc"
        )


def normalize_lookup_aliases(
    primary_fingerprint: str,
    aliases: Iterable[str] | None,
) -> list[str]:
    """Return unique non-primary Lookup Alias strings in submission order."""
    if aliases is None:
        return []

    normalized: list[str] = []
    seen = {primary_fingerprint}
    for alias in aliases:
        if alias in seen:
            continue
        seen.add(alias)
        normalized.append(alias)
    return normalized


def resolve_disc_identity(
    db: Session,
    fingerprint: str,
    *,
    options: Iterable[object] = (),
) -> IdentityResolution | None:
    """Resolve a Primary Fingerprint or Lookup Alias to its Disc."""
    query = db.query(Disc)
    for option in options:
        query = query.options(option)

    disc = query.filter(Disc.fingerprint == fingerprint).first()
    if disc is not None:
        return IdentityResolution(
            disc=disc,
            matched_fingerprint=fingerprint,
            matched_via_alias=False,
        )

    alias = (
        db.query(DiscIdentityAlias)
        .filter(DiscIdentityAlias.fingerprint == fingerprint)
        .first()
    )
    if alias is None:
        return None

    query = db.query(Disc)
    for option in options:
        query = query.options(option)
    alias_disc = query.filter(Disc.id == alias.disc_id).first()
    if alias_disc is None:
        return None

    return IdentityResolution(
        disc=alias_disc,
        matched_fingerprint=fingerprint,
        matched_via_alias=True,
    )


def resolve_existing_disc_for_identities(
    db: Session,
    primary_fingerprint: str,
    aliases: Iterable[str] | None,
) -> IdentityResolution | None:
    """Resolve submitted identities, rejecting identities split across discs."""
    first_resolution: IdentityResolution | None = None
    fingerprints = [
        primary_fingerprint,
        *normalize_lookup_aliases(primary_fingerprint, aliases),
    ]

    for fingerprint in fingerprints:
        resolution = resolve_disc_identity(db, fingerprint)
        if resolution is None:
            continue
        if first_resolution is None:
            first_resolution = resolution
            continue
        if resolution.disc.id != first_resolution.disc.id:
            raise DiscIdentityConflict(fingerprint, resolution.disc)

    return first_resolution


def attach_lookup_aliases(
    db: Session,
    disc: Disc,
    primary_fingerprint: str,
    aliases: Iterable[str] | None,
) -> None:
    """Persist new Lookup Aliases for a disc, rejecting cross-disc conflicts.

    Concurrent gunicorn workers may attempt to attach the same alias
    fingerprint at the same time (IDENT-02). Reading-then-adding (TOCTOU)
    cannot prevent that race — only the `disc_identity_aliases.fingerprint`
    UNIQUE constraint can arbitrate atomically. So each insert is attempted
    first, inside its own SAVEPOINT (`db.begin_nested()`), so a losing insert
    rolls back only its own savepoint — not sibling aliases already
    committed in this same call, nor the outer submission transaction. A
    caught `IntegrityError` means another worker won the race; we discard
    the now-stale identity map (`db.expire_all()`) and re-resolve to find
    out who actually holds the fingerprint now, converging to a single
    winning disc row instead of a split/duplicate pressing.
    """
    for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
        # Concurrent-worker UNIQUE convergence (IDENT-02): a SAVEPOINT scopes
        # this single insert so a losing race only unwinds this alias, never
        # sibling aliases already committed in this call nor the caller's
        # outer transaction. flush() forces the INSERT (and any violation)
        # to surface here, inside the savepoint, rather than at the outer
        # commit where it could no longer be isolated to just this alias.
        try:
            with db.begin_nested():
                db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))
                register_fingerprint(db, alias, disc.id)
                db.flush()
        except IntegrityError:
            # Another worker won the race. Discard the stale identity map
            # left behind by the rolled-back savepoint before re-resolving
            # (Pitfall 2), then converge to whoever actually holds it now.
            db.expire_all()
            winner = resolve_disc_identity(db, alias)
            if winner is None:
                # Genuinely unexpected — the UNIQUE violation implies a row
                # exists, but re-resolve found nothing. Do not swallow.
                raise
            if winner.disc.id != disc.id:
                raise DiscIdentityConflict(alias, winner.disc)
            # else: our own disc already owns this alias — idempotent no-op.


def redact_sibling_summary(disc: Disc) -> SiblingDiscSummary:
    """Build a SiblingDiscSummary from a Disc ORM object, applying R-1 anti-echo
    redaction (WR-03).

    Withholds the derived structural fields (``main_title``/``duration_secs``/
    ``track_count``) when ``disc`` is ``unverified``, mirroring the same
    predicate ``_disc_to_response`` (``app/routes/disc.py``) uses to redact a
    direct disc lookup (D-09). A disc in any other status (verified/disputed/
    pending_identification) keeps its full structural summary — the gate is
    per-disc status, never a blanket redaction.

    This is the SINGLE shared implementation of the security-relevant R-1 rule.
    It is called from both the nested disc-detail set view
    (``app/routes/disc.py::_build_disc_set_nested``) and the set-search/detail
    view (``app/routes/set.py``) so the redaction rule cannot silently drift
    between the two call sites.
    """
    if disc.status == "unverified":
        return SiblingDiscSummary(
            fingerprint=disc.fingerprint,
            disc_number=disc.disc_number,
            format=disc.format,
            main_title=None,
            duration_secs=None,
            track_count=None,
        )

    main_title_name = None
    main_duration = None
    track_count = 0
    for t in disc.titles:
        track_count += len(t.tracks) if hasattr(t, "tracks") else 0
        if t.is_main_feature:
            main_title_name = t.display_name
            main_duration = t.duration_secs
    return SiblingDiscSummary(
        fingerprint=disc.fingerprint,
        disc_number=disc.disc_number,
        format=disc.format,
        main_title=main_title_name,
        duration_secs=main_duration,
        track_count=track_count,
    )


def register_fingerprint(db: Session, fingerprint: str, disc_id: uuid.UUID) -> None:
    """Register a fingerprint into the cross-table arbitration registry (WR-02).

    The registry's global ``UNIQUE(fingerprint)`` column is what actually
    arbitrates a cross-table race between a new-disc insert and an
    alias-attach for the same fingerprint string on a different disc — the
    caller is REQUIRED to invoke this inside the same ``db.begin_nested()``
    savepoint as the accompanying ``Disc``/``DiscIdentityAlias`` insert, so
    a UNIQUE violation here surfaces through that savepoint's existing
    ``except IntegrityError:`` re-resolve/converge handling. This function
    performs no flush or commit of its own.
    """
    db.add(FingerprintRegistry(fingerprint=fingerprint, disc_id=disc_id))
