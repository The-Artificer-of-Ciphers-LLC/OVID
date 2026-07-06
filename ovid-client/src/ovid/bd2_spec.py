"""Frozen OVID-BD-2 Tier-2 anti-obfuscation ruleset (FPRINT-06).

These constants define the exact filter/dedup/tie-break pipeline used by
`build_bd_canonical_string()` to select which BDMV playlists contribute to
the Tier-2 structure fingerprint. They are frozen and version-tagged: any
edit to a value here without also bumping `OVID_BD2_VERSION` silently mints
a *different* fingerprint for the *same physical disc* on the next run — the
exact studio-obfuscation failure mode (renumbered/loop-padded `.mpls`
decoys, e.g. Lionsgate "ScreenPass"-style schemes) that FPRINT-06 exists to
close. Do not tune these as loose values; changing them is a fingerprint
version migration, not a bug fix.
"""

from __future__ import annotations

# OVID-BD-2 canonical-string version prefix. D-08: this freezes the v1
# pre-release ruleset as-is — no version bump this phase. CR-01 correction
# (still pre-release/unreleased as `bd2-`/`uhd2-` have not shipped): the
# per-playlist block's audio/subtitle fields were corrected to include
# explicit stream-count fields (see `build_bd_canonical_string()`'s "Format"
# docstring) so that "0 streams" can never collide with "1 stream whose
# joined value happens to be empty". Because this ruleset has not been
# released, the encoding fix is applied in place without a version bump —
# any *future* change to a released `OVID_BD2_VERSION` would require one.
OVID_BD2_VERSION = "OVID-BD-2"

# Minimum total playlist duration (seconds) to include in the structure
# hash. Playlists shorter than this are typically menus, previews, or
# short obfuscation padding that differs between otherwise-identical
# disc pressings.
MIN_DURATION_SECONDS = 60.0

# Maximum number of times a single clip_id may repeat across a playlist's
# play items before that playlist is treated as a loop-padded decoy and
# excluded from the canonical string.
MAX_CLIP_REPEATS = 2
