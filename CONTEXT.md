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
