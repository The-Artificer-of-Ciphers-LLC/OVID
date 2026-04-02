# OVID-DVD-1 Fingerprint Algorithm Specification

**Version:** 1.0
**Status:** Final (v0.1.0)
**Last updated:** 2026-04-01

---

## Overview

OVID-DVD-1 is a deterministic algorithm for generating a unique fingerprint from the structural layout of a DVD disc. The fingerprint is derived entirely from the logical structure stored in IFO files — title sets, program counts, durations, chapter counts, and audio/subtitle stream metadata. No filesystem timestamps, file sizes, or file dates are used.

The resulting fingerprint is a 45-character string in the format `dvd1-{40 hex chars}`.

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
| `dvd1-` | DVD | OVID-DVD-1 (this spec) |
| `bd1-aacs-` | Blu-ray | AACS Disc ID (planned, v0.2.0) |
| `bd2-` | Blu-ray | BDMV structure hash (planned, v0.2.0) |
| `uhd1-aacs-` | 4K UHD | AACS Disc ID (planned, v0.2.0) |
| `uhd2-` | 4K UHD | BDMV structure hash (planned, v0.2.0) |

## Reference Implementation

The reference implementation is in `ovid-client` (Python):

- `ovid/ifo_parser.py` — IFO binary parsing (parse_vmg, parse_vts, decode_bcd_time)
- `ovid/fingerprint.py` — Canonical string builder and SHA-256 hashing
- `ovid/disc.py` — High-level `Disc.from_path()` entry point
- `ovid/readers/` — Source abstraction (FolderReader, ISOReader, DriveReader)

## Versioning

The algorithm version is embedded in the canonical string prefix (`OVID-DVD-1`). If the algorithm changes in a way that produces different fingerprints for the same disc, a new version (`OVID-DVD-2`) will be defined. Both versions can coexist in the database — lookup tries the current version first.

## License

This specification is released under CC0 1.0 Universal (Public Domain). Anyone may implement a compatible fingerprint generator.
