# OVID Context

## Glossary

### Normalized Disc Structure

A format-neutral description of a physical video disc's structure, including its fingerprint, format, titles, chapters, audio tracks, subtitle tracks, and source metadata. It preserves disc identity while hiding DVD-specific IFO details and Blu-ray-specific MPLS/AACS details from callers.

### Main Feature

The title or playlist on a physical video disc that represents the primary movie or episode content. OVID derives this marker from disc structure when possible so callers do not need to know DVD-specific or Blu-ray-specific selection rules.

### Normalized Title

A format-neutral title entry within a Normalized Disc Structure. It represents one playable title or playlist with duration, chapter count, Main Feature status, and associated tracks without exposing DVD PGC or Blu-ray playlist implementation details.

### Normalized Track

A format-neutral audio or subtitle track entry within a Normalized Title. It carries language, codec, channel, and default-track facts that are relevant to disc identity and submission.

### Normalized Chapter

A format-neutral chapter entry within a Normalized Title. It carries chapter order and optional timing or naming data without exposing DVD cell or Blu-ray mark implementation details.

### Disc Identity

A stable identifier for a physical video disc pressing. It answers which exact disc is present without describing the disc's playable titles, chapters, audio tracks, or subtitle tracks.

### Disc Identity Method

The method used to derive a Disc Identity. Different methods can identify the same physical disc pressing while producing different fingerprint strings.

### Fingerprint Version

The versioned format of a Disc Identity string. A Fingerprint Version tells callers which Disc Identity Method produced the string and lets multiple identifiers for the same physical disc pressing coexist during compatibility windows.

`dvd1-*` identifies the OVID-DVD-1 structural hash method. `dvdread1-*` identifies the libdvdread Disc ID method.

### Primary Fingerprint

The Disc Identity string that OVID publishes as the canonical identifier for a physical video disc pressing. Lookup by a secondary Disc Identity can resolve to a disc while responses still expose the disc's Primary Fingerprint.

### Lookup Alias

A secondary Disc Identity string that resolves to the same physical video disc pressing as the Primary Fingerprint. A Lookup Alias identifies one physical video disc pressing globally; if the same Disc Identity string appears for a different pressing, OVID treats that as an identity conflict. Lookup Aliases preserve access to records created with older Fingerprint Versions or alternate Disc Identity Methods.

### Disc Structure

The playable layout of a physical video disc, including titles, chapters, audio tracks, subtitle tracks, durations, and source metadata. It describes what can be played on the disc without deciding which identifier should represent the disc pressing.
