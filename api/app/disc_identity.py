"""Server-side Disc Identity resolution and Lookup Alias persistence."""

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Disc, DiscIdentityAlias


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
    """Persist new Lookup Aliases for a disc, rejecting cross-disc conflicts."""
    for alias in normalize_lookup_aliases(primary_fingerprint, aliases):
        resolution = resolve_disc_identity(db, alias)
        if resolution is None:
            db.add(DiscIdentityAlias(disc_id=disc.id, fingerprint=alias))
            continue
        if resolution.disc.id != disc.id:
            raise DiscIdentityConflict(alias, resolution.disc)
