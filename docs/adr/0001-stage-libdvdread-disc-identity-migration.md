# 0001: Stage libdvdread Disc Identity Migration

## Status

Accepted

## Context

OVID currently identifies DVDs with the OVID-DVD-1 structural hash, exposed as `dvd1-*`.

GitHub issue #1 proposes using the libdvdread Disc ID method instead. That method is common in existing DVD tooling, but it produces a different Disc Identity string from OVID-DVD-1. Replacing the public fingerprint immediately would fragment lookups, submissions, tests, documentation, and existing database records.

## Decision

Introduce libdvdread Disc ID as a new Fingerprint Version, `dvdread1-*`, behind a Disc Identity module.

The migration is staged:

1. Phase 1 computes Disc Identity through the new module, tries libdvdread when available, silently falls back to OVID-DVD-1, and keeps `dvd1-*` as the primary public fingerprint.
2. Phase 2 models Lookup Aliases in the API and database so multiple Disc Identity strings can resolve to the same physical disc pressing.
3. Phase 3 can make `dvdread1-*` the primary DVD fingerprint when alias lookup and submission support exist.

`dvd1-*` remains the OVID-DVD-1 structural hash. `dvdread1-*` identifies the libdvdread Disc ID method. The client should submit all known Disc Identity strings once the API can store aliases.

Disc Identity and Disc Structure remain separate concepts. The Disc Identity module answers which exact disc pressing is present. Normalized Disc Structure describes playable titles, chapters, audio tracks, subtitle tracks, durations, and source metadata.

## Consequences

Existing callers can keep using `Disc.from_path(...).fingerprint` during Phase 1.

The native libdvdread adapter can fail silently into OVID-DVD-1 while still recording diagnostic metadata internally for tests and debugging.

The API must eventually store Lookup Aliases instead of treating fingerprint uniqueness as the only identity relationship.

The OVID-DVD-1 parser remains useful for fallback identity and for Normalized Disc Structure even after libdvdread becomes the preferred Disc Identity Method.
