# OVID-DVD-1 Fingerprint Algorithm Specification

**Version:** 1.0
**Status:** Final (v0.1.0)
**Last updated:** 2026-06-20

---

## Overview

OVID-DVD-1 is a deterministic algorithm for generating a unique fingerprint from the structural layout of a DVD disc. The fingerprint is derived entirely from the logical structure stored in IFO files — title sets, program counts, durations, chapter counts, and audio/subtitle stream metadata. No filesystem timestamps, file sizes, or file dates are used.

The resulting fingerprint is a 45-character string in the format `dvd1-{40 hex chars}`.

OVID is also introducing the libdvdread Disc ID method as the distinct
`dvdread1-*` Fingerprint Version. During the staged migration, OVID-DVD-1
remains the public DVD fingerprint returned by `ovid fingerprint`; libdvdread
identities can be stored by the server as Lookup Aliases.

## Design Goals

- **Deterministic:** The same disc always produces the same fingerprint.
- **Stable:** Unaffected by which drive, OS, or ripping library reads the disc. Unaffected by whether the source is a physical disc, a mounted ISO, or an extracted VIDEO_TS folder.
- **Unique:** Different disc pressings/editions produce different fingerprints.
- **Collision-resistant:** SHA-256 hash space makes accidental collisions negligible.

## Prior Art

The Windows dvdid algorithm (US Patent 6,871,012 B1, now expired) incorporates filesystem timestamps in its CRC inputs. Timestamps change when disc files are copied, ripped to ISO, or transferred between systems — making it unsuitable for a lookup database. OVID-DVD-1 uses only structural data that is byte-identical across every physical copy of the same pressing.

## Input Data

The algorithm reads IFO files from the `VIDEO_TS/` directory:

```
VIDEO_TS/
  VIDEO_TS.IFO      ← root info file (VMG — Video Manager)
  VTS_01_0.IFO      ← title set 1 info
  VTS_02_0.IFO      ← title set 2 info
  ...               ← up to 99 title sets
```

Sources may be:
- An extracted VIDEO_TS folder on disk
- An ISO 9660 image (read via pycdlib or similar)
- A mounted optical drive

## Algorithm

### Step 1: Parse VMG (VIDEO_TS.IFO)

Extract from the Video Manager information file:
- `VTS_count` — number of video title sets (byte offset 0x3E, 2 bytes big-endian)
- `title_count` — number of titles in the title table (TT_SRPT)

### Step 2: Parse Each VTS (VTS_XX_0.IFO)

For each title set from `VTS_01_0.IFO` through `VTS_{VTS_count}_0.IFO`, in order:

1. **PGC (Program Chain) data:**
   - Number of programs (PGCs) in this title set
   - For each PGC in order:
     - Total duration decoded from BCD-encoded playback time field (4 bytes: hours, minutes, seconds, frame-rate flag) → converted to **whole seconds**
     - Number of chapters (programs within the PGC, from `nr_of_programs` field)

2. **Audio streams:**
   - Number of audio streams (from VTS attributes)
   - For each stream: language code (ISO 639-2, e.g. `en`, `fr`, `es`)
   - Codec is parsed and stored for metadata but **excluded** from the canonical string

3. **Subtitle streams:**
   - Number of subtitle streams
   - For each stream: language code (ISO 639-2)

### Step 3: Build Canonical String

Construct a UTF-8 string in this exact format (pipe-delimited, no spaces):

```
OVID-DVD-1|{VTS_count}|{title_count}|{vts1_data}|{vts2_data}|...
```

Each VTS data section:
```
{pgc_count}:{pgc1_dur}:{pgc1_chaps}:{pgc1_audio}:{pgc1_subs},{pgc2_dur}:{pgc2_chaps}:{pgc2_audio}:{pgc2_subs},...
```

Where:
- `{pgc_dur}` — duration in whole seconds (integer)
- `{pgc_chaps}` — chapter count (integer)
- `{pgc_audio}` — comma-joined language codes (e.g. `en,fr,es`), empty string if no audio streams
- `{pgc_subs}` — comma-joined language codes, empty string if no subtitle streams

**Example** (simplified two-VTS disc):
```
OVID-DVD-1|2|4|1:7287:28:en,fr,es:en,fr,es|3:104:3:en:en,88:2:en:,71:1:en:
```

### Step 4: Hash

1. Compute SHA-256 of the canonical string (UTF-8 encoded bytes)
2. Encode the hash as lowercase hexadecimal
3. Take the first 40 characters

### Step 5: Format

Prefix with `dvd1-`:

```
dvd1-{40 hex characters}
```

**Example output:**
```
dvd1-59863dd2519845852f991036aabe2a725fc5d751
```

## BCD Time Decoding

IFO files store playback times in Binary-Coded Decimal format:

| Byte | Content |
|------|---------|
| 0 | Hours (BCD: high nibble = tens, low nibble = ones) |
| 1 | Minutes (BCD) |
| 2 | Seconds (BCD) |
| 3 | Frame count + frame rate flag (bits 7-6 = rate, bits 5-0 = frames) |

Conversion: `total_seconds = hours * 3600 + minutes * 60 + seconds`

The frame rate flag and frame count are **not** included in the duration — only whole seconds are used. This ensures stability across different drive read speeds.

**Invalid BCD nibbles** (≥10) are clamped to 0 rather than raising an error. Some real-world discs have garbled metadata in unused PGC slots.

## Edge Cases

| Case | Handling |
|------|----------|
| Malformed or truncated IFO files | Raise an error — the fingerprint cannot be computed |
| Zero PGCs in a title set | Include in canonical string as `0:` (empty PGC section) |
| No audio or subtitle streams | Empty string in the corresponding canonical field position |
| Region coding | Does NOT affect IFO structure — fingerprint is region-agnostic. Region is stored separately in the OVID database record. |
| Dual-layer discs | IFO structure is identical regardless of physical layer count |

## Fingerprint Format Summary

| Prefix | Format | Algorithm |
|--------|--------|-----------|
| `dvd1-` | DVD | OVID-DVD-1 structural hash (this spec) |
| `dvdread1-` | DVD | libdvdread Disc ID |
| `bd1-aacs-` | Blu-ray | AACS Disc ID (see OVID-BD-2 section below) |
| `bd2-` | Blu-ray | BDMV structure hash (see OVID-BD-2 section below) |
| `uhd1-aacs-` | 4K UHD | AACS Disc ID (see OVID-BD-2 section below) |
| `uhd2-` | 4K UHD | BDMV structure hash (see OVID-BD-2 section below) |

## Reference Implementation

The reference implementation is in `ovid-client` (Python):

- `ovid/ifo_parser.py` — IFO binary parsing (parse_vmg, parse_vts, decode_bcd_time)
- `ovid/fingerprint.py` — Canonical string builder and SHA-256 hashing
- `ovid/disc.py` — High-level `Disc.from_path()` entry point
- `ovid/readers/` — Source abstraction (FolderReader, ISOReader, DriveReader)

## Versioning

The algorithm version is embedded in the canonical string prefix (`OVID-DVD-1`). If the algorithm changes in a way that produces different fingerprints for the same disc, a new Fingerprint Version is defined.

`dvdread1-*` is the Fingerprint Version for libdvdread Disc ID values. It is not a replacement meaning for `dvd1-*`; the prefixes identify different Disc Identity Methods. Both versions can coexist through Lookup Aliases.

## OVID-BD-2 Fingerprint Algorithm Specification

**Version:** 1.0 (OVID-BD-2 v1)
**Status:** Final (v0.2.0)
**Last updated:** 2026-07-06

### Overview

OVID uses a two-tier fingerprinting scheme for Blu-ray and 4K UHD discs:

- **Tier 1** (`bd1-aacs-` / `uhd1-aacs-`) — the AACS Disc ID, a plaintext-file hash read from the disc's AACS directory.
- **Tier 2** (`bd2-` / `uhd2-`) — the BDMV structure hash, derived from the disc's playlist (`.mpls`) structure. Tier 2 is always the primary identity of the pair whenever it can be computed.

### Alias-Pair Behavior

Both tiers are computed whenever possible and returned together as one `DiscIdentitySet`: Tier 2 is fixed as primary, with Tier 1 attached as an alias when the disc's AACS directory is present and readable. This mirrors the `dvd1-*`/`dvdread1-*` alias-pair precedent established for DVD in ADR 0001 — one canonical primary identity plus zero or more Lookup Aliases from other identity methods, not a single hard-coded fingerprint per disc.

There is one degenerate exception: if Tier 2 cannot be computed at all (no playlist survives the Tier 2 filter pipeline below), Tier 1 becomes primary instead — a documented fallback, not a silent one, since a diagnostic (`tier2_unavailable_using_tier1_primary`) is always recorded alongside it. If neither tier is available, disc identification fails outright rather than returning a hollow identity.

### Tier 1 — AACS Disc ID

**"AACS Disc ID" ≡ `SHA-1(AACS/Unit_Key_RO.inf)`.**

This is a one-way SHA-1 digest of the plaintext `Unit_Key_RO.inf` file found in a disc's `AACS/` directory — the same value the FOSS Blu-ray tooling ecosystem (libaacs, MakeMKV `keydb.cfg`) refers to as the "AACS Disc ID." Computing it is a plaintext filesystem read plus a one-way hash: it involves **no descrambling, no drive-level handshake, and no AACS device keys**. It is explicitly **not a decryption key** — the wrapped CPS/Title-Key material inside `Unit_Key_RO.inf` is unusable without the Media Key Block and AACS-LA-licensed device keys, neither of which OVID ever holds or stores, and a one-way SHA-1 digest cannot be inverted to recover key material.

The raw `Unit_Key_RO.inf` file itself is never published or stored by OVID — only the derived fingerprint string (`bd1-aacs-{40 hex chars}` or `uhd1-aacs-{40 hex chars}`) is public.

### Tier 2 — BDMV Structure Hash Algorithm

Tier 2 selects a canonical, deterministic subset of a disc's `.mpls` playlists and hashes their structural content. The filter/dedup/sort pipeline is frozen in `ovid-client/src/ovid/bd2_spec.py` and enforced by `select_canonical_playlists()`:

1. **Minimum-duration filter** — playlists with total duration under `MIN_DURATION_SECONDS` (60.0 seconds) are excluded. These are typically menus, previews, or short obfuscation padding that differs between otherwise-identical disc pressings.
2. **Loop-pad decoy filter** — playlists where any single `clip_id` repeats more than `MAX_CLIP_REPEATS` (2) times across the playlist's play-items are excluded. This defends against loop-padded duration decoys — the same clip referenced many times to inflate apparent duration.
3. **Content-based dedup** — surviving playlists are deduped by their full ordered `(clip_id, in_time, out_time)` sequence, keeping one canonical block per equivalence class. This defends against renumbered or duplicated decoy copies of the same underlying content.
4. **Deterministic sort** — remaining playlists are sorted by `(-total_duration_seconds, clip_sequence_tuple)`, i.e. longest duration first, then by content-based clip sequence as a tie-break. Sorting is **never** by filename, since studios renumber `.mpls` files across pressings.

The surviving, deduped, sorted playlists are encoded into a pipe-delimited canonical string:

```
OVID-BD-2|{playlist_count}|{pl1_block}|{pl2_block}|...
```

Each playlist block:

```
{play_item_count}:{total_duration}:{chapter_count}:{audio_count}:{audio_info}:{subtitle_count}:{subtitle_info}
```

Where:
- `play_item_count` — number of PlayItems in the playlist
- `total_duration` — total seconds as an integer
- `chapter_count` — number of chapter marks
- `audio_count` — number of audio streams (`len(audio_streams)`)
- `audio_info` — comma-joined `codec+language+channels` per audio stream, empty string if none
- `subtitle_count` — number of subtitle streams (`len(subtitle_streams)`)
- `subtitle_info` — comma-joined language codes per subtitle stream, empty string if none

The explicit `audio_count`/`subtitle_count` fields exist so that "zero streams" can never be confused with "one stream whose joined value happens to be empty" (e.g. an unparsed/null-language subtitle track) — both previously collapsed to the same empty `subtitle_info` field, a real fingerprint collision between structurally different discs. Because `OVID-BD-2` is pre-release/unreleased, this encoding was corrected in place rather than via a version bump.

The canonical string is SHA-256 hashed (UTF-8 encoded bytes), and the first 40 hex characters of the digest are taken, matching OVID-DVD-1's own hashing step. The result is prefixed with `bd2-` (standard Blu-ray) or `uhd2-` (4K UHD):

```
bd2-{40 hex characters}
uhd2-{40 hex characters}
```

### Format Detection (UHD)

UHD (4K) discs are distinguished from standard Blu-ray discs by inspecting the MPLS playlist header version: `"0300"` indicates UHD, `"0200"` indicates standard Blu-ray. This follows the same convention used by libbluray's reverse-engineered UHD support.

This detection rule is a **community-corroborated convention, not a licensed BDA specification guarantee** — there is no publicly licensed Blu-ray Disc Association document OVID can cite for it. A misdetection under this heuristic would only affect the disc's `format` field (`"bluray"` vs `"uhd"`); it has no effect on the disc's identity or fingerprint value, since Tier 1 and Tier 2 fingerprints are computed identically regardless of the detected format (only the prefix, `bd*`/`uhd*`, changes).

### Versioning

The algorithm version is embedded in the canonical string prefix (`OVID-BD-2`). Any change to the filter/max-repeat/tie-break constants in `bd2_spec.py` (`MIN_DURATION_SECONDS`, `MAX_CLIP_REPEATS`, or the sort/dedup rules) must bump the `OVID_BD2_VERSION` literal, minting a new Fingerprint Version (e.g. `bd2v2-`/`uhd2v2-`) that coexists with `bd2-`/`uhd2-` through Lookup Aliases — the constants are never mutated in place. This mirrors OVID-DVD-1's own Versioning rule: a change that produces different fingerprints for the same disc always defines a new Fingerprint Version rather than silently redefining an existing one.

## License

This specification is released under CC0 1.0 Universal (Public Domain). Anyone may implement a compatible fingerprint generator.
