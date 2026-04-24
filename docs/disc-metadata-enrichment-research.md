# OVID — Disc Metadata Enrichment Research
**Purpose:** Survey of techniques for extracting richer metadata from discs beyond what OVID already reads
**Date:** 2026-04-04

---

## What OVID Currently Reads

As a baseline, OVID's `ovid-client` today reads:
- **DVD:** IFO structure — title sets, PGC counts, durations, chapter counts, audio/subtitle stream language codes
- **Blu-ray:** AACS certificate (Tier 1) + MPLS playlist structure — playlist files, clip durations, stream counts
- **Both:** The result is a fingerprint plus structural counts. No human-readable names are collected.

Everything below is *additional* data that could be harvested from the disc itself or from companion tools — relevant to chapter names, title names, disc title, and metadata enrichment.

---

## Category 1 — Data That Lives On the Disc Already

These don't require any external network call or rendering. The data is sitting on the disc waiting to be read.

### 1A. Blu-ray `bdmt_*.xml` — Title and Chapter Names

**Location:** `BDMV/META/DL/bdmt_eng.xml` (and language variants like `bdmt_jpn.xml`)

**What it contains:**
- The disc's display title (what shows on a PS3 or Sony player)
- In theory: per-title names and per-chapter names
- A thumbnail image

**Reality check:** The spec allows chapter names, but almost no disc studios actually include them. Disc titles (the overall movie name) are more commonly present. TV show box sets are the most likely source of per-title episode names.

**How to read it:** It's a plain XML file. Parse it with Python's standard `xml.etree.ElementTree` — no new dependencies. `libbluray`'s `bd_get_meta()` function also exposes this data if you're using the C library.

**Python tools:**
- [PyBluRead](https://github.com/cmlburnett/PyBluRead) — Python wrapper around libbluray; provides `bd_get_meta()` output including disc title
- [bluinfo](https://github.com/SavSanta/bluinfo) — standalone Blu-ray metadata extractor for Linux/Mac, reads BDMV structure

**Integration fit for OVID:** Parse `bdmt_eng.xml` during fingerprint generation in `ovid-client`. If a disc title or title names are present, include them in the fingerprint JSON output so the submission wizard can pre-populate fields. This is low effort and purely additive.

**Caveat:** Not present on every disc — must be treated as optional. Most Hollywood releases do not include it.

---

### 1B. DVD Text (DVD-Text / DVD_TEXT.SR)

**What it is:** DVDs can optionally carry text metadata in a special data area — title names, chapter names, performer info. This was more commonly used on concert music DVDs and some Japanese releases.

**Reality check:** Very rare on mainstream movie DVDs. MakeMKV's own documentation notes: "Some DVDs do have chapter names in text format... These DVDs are rare, usually concert music DVDs."

**How to read it:** `libdvdread` exposes DVD text data. The `dvdxchap` command-line tool on Linux can extract chapter info and any embedded text from DVD IFO files.

**Tools:**
- `dvdxchap` (part of `ogmtools`) — [man page](https://linux.die.net/man/1/dvdxchap)
- `libdvdread`/`libdvdnav` 7.0 (just released in 2025) — new version with improved metadata APIs

**Integration fit for OVID:** Worth checking during DVD fingerprint generation. Add an optional pass to look for DVD text and include it in the enrichment JSON if present. Expected hit rate: <5% of movie DVDs, but 100% useful when present.

---

### 1C. Blu-ray MPLS Chapter Timestamps (No Names, but Timestamps)

**What it is:** Every Blu-ray playlist (`.mpls` file in `BDMV/PLAYLIST/`) contains precise chapter entry timestamps — where each chapter starts. These are always present and reliable. Chapter names are NOT stored here.

**Why it matters for OVID:** Chapter timestamps let you calculate chapter durations. Combined with chapter count, you get richer structural data. Also useful for cross-checking that two submitted entries for the same fingerprint agree on chapter structure.

**Python tools:**
- [pympls](https://github.com/rlaphoenix/pympls) — Python library for parsing Blu-ray `.mpls` files (chapter timestamps, clip references)
- [pymplschapters](https://github.com/rlaphoenix/pymplschapters) — extracts chapter timestamps from `.mpls` to Matroska XML

**Integration fit for OVID:** OVID's Blu-ray fingerprinting already reads MPLS files for the structural hash. The chapter timestamps could be extracted in the same pass and included in the fingerprint JSON output as start-time data. This enriches what a contributor can submit with minimal extra work.

---

### 1D. HandBrake `--scan --json` Output

**What it is:** HandBrake's CLI can scan a disc without encoding and output a JSON summary. This includes: title durations, chapter counts, audio track details, subtitle track details, disc name, and — importantly — whether chapters have names.

**Command:**
```bash
HandBrakeCLI --input /dev/sr0 --scan --json 2>/dev/null
```

**What you get back:** A JSON blob per title listing all detected metadata. Chapter names, when present, are included as `"Name": "Chapter 1"` entries (HandBrake generates placeholder names if the disc has none).

**Caveat:** HandBrake auto-generates `"Chapter 1"`, `"Chapter 2"` etc. when no names are present — so you can't blindly import these as real chapter names. The field has real content only when the disc itself provides names (rare; see 1A and 1B above).

**Integration fit for OVID:** A `--scan --json` pass could serve as an alternate data source for the `ovid submit` wizard, pre-populating title structure without requiring the user to hand-enter it. More relevant as an ARM integration: ARM already runs HandBrake, so that scan output is already available for free.

---

## Category 2 — Menu Screen Capture and OCR

This is the "can we read text off the disc's menu screen?" question. Short answer: it's technically possible but practically difficult. Here's the full picture.

### 2A. Why Disc Menus Have Text That Isn't in the File System

DVD and Blu-ray menus are bitmap graphics, not text files. When a menu says "Play Movie" or "Chapter 3: The Fellowship Sets Out," that text is burned into a graphic overlay image (called PGS on Blu-ray, VOBSUB on DVD). There is no separate text file containing those strings.

This is why chapter names are so hard to extract programmatically — they may exist only as pixels in a menu image, not as any machine-readable metadata.

### 2B. DVD Menu Capture — The Approach That Works

**Tool chain:** `libdvdnav` → render menu frames → capture image → OCR

libdvdnav (just updated to version 7 in 2025) can navigate a DVD programmatically — including stepping through menus — without a screen. VLC and MPlayer both use it. The approach:

1. Use libdvdnav to load the disc and navigate to the chapter menu
2. Capture the rendered menu frame as an image (VLC can do this with `--snapshot` options)
3. Run OCR (Tesseract or an AI vision model) on the image to extract text
4. Parse the text to find chapter name patterns

**Reality check:** This is a research-grade pipeline, not a polished tool. It requires:
- libdvdnav navigation working for a specific disc's menu structure (varies by disc)
- A working display/framebuffer or virtual framebuffer (Xvfb) for rendering
- OCR accuracy sufficient to handle stylized menu fonts
- A parser that can match OCR output to chapter structure

**Practical use case for OVID:** This is worth pursuing as a community tool for power contributors — not something to build into the default `ovid submit` flow. Someone with 500 DVDs to submit could run a batch menu-capture pipeline to harvest chapter names that no other method can get.

### 2C. Blu-ray Menu Capture — Much Harder

Blu-ray menus come in two types:

**HDMV (static/simple menus):** These use IGS (Interactive Graphic Stream) overlays — bitmap images with interactive regions. BDedit can open and view these. Capturing and OCR-ing them is similar to the DVD approach but requires a BD-capable player stack.

**BD-J (Java-based menus):** These run a Java application on a JVM bundled with the player. Common on premium Hollywood releases. You cannot render these without a full BD-J runtime. VLC requires Java installed for BD-J menus. This path is effectively closed for automated processing.

**Practical use case for OVID:** Narrow. Most discs with elaborate menus have BD-J menus you can't render headlessly. Simpler HDMV discs are more tractable.

**Tool references:**
- [BDedit](https://forum.videohelp.com/threads/394139) — can open HDMV IGS menu graphics on Windows
- [VLC + MakeMKV](https://www.omgubuntu.co.uk/2022/08/watch-bluray-discs-in-vlc-on-ubuntu-with-makemkv) — full BD playback with menus (requires Java for BD-J)

### 2D. VobSub / PGS Subtitle OCR — The Better Path for Chapter Names

Here's the thing: on many DVDs, chapter names appear in the subtitle stream, not just the menu. If a disc has a subtitle track that shows chapter markers (some Japanese releases, concert DVDs, etc.), those can be extracted as image files and OCR-ed with much better reliability than live menu capture.

**Modern AI-based OCR tools (2024–2025):**
- [subtitles-ai-ocr](https://github.com/hekmon/subtitles-ai-ocr) — sends PGS/VobSub bitmap frames to any OpenAI-compatible vision API (Ollama with qwen3-vl, OpenAI GPT-4V, etc.); tested at 1,057 subtitles successfully
- [SubExtractor](https://github.com/bitblaster/SubExtractor) — converts DVD VOBSUB and Blu-ray PGS to SRT using traditional OCR
- [pgs-to-srt](https://github.com/wydengyre/pgs-to-srt) — Tesseract-based PGS → SRT conversion

**Integration fit for OVID:** A power-contributor tool, not a default flow. ARM users often have access to the extracted VOBSUB/PGS streams already (they're ripped as part of the MKV). If OVID provided a utility that accepts a VOBSUB file and outputs chapter name candidates via AI OCR, that's a low-friction way to harvest names from discs that have them baked into subtitle streams.

---

## Category 3 — External Data Sources

These require a network call but don't require rendering anything.

### 3A. OpenSubtitles Hash Lookup

OpenSubtitles uses a hash of the actual video file content (not the disc fingerprint) to identify a specific video file. This can resolve edition-level differences: the theatrical cut and director's cut will have different hashes.

**Relevance to OVID:** Low for chapter names specifically. Useful as a secondary cross-reference when a rip is already complete. Not useful during the disc fingerprinting phase before ripping.

### 3B. ChapterDB (chapterdb.org)

**What it was:** A community database of DVD/Blu-ray chapter names, searchable by movie and edition. Used by tools like Handbrake and the ChapterGrabber utility.

**Current status:** ChapterDB has been unreliable and largely offline for years. The community data it held is considered lost.

**Relevance to OVID:** This is exactly the gap OVID could fill for chapter names. The fact that ChapterDB is dead and was never tied to disc fingerprints makes OVID's approach (fingerprint-first, then community metadata) better by design.

### 3C. MusicBrainz Model (Analogous Reference)

MusicBrainz stores track titles for CDs as community-submitted data — not read from the disc itself. The disc TOC is the fingerprint; track names come from community contribution.

OVID should follow the same model for chapter names: the chapter count comes from the disc structure (already collected), the chapter names are community-submitted optional metadata.

---

## Summary: What OVID Should Actually Do

Here's the pragmatic ranking of approaches, from easiest to hardest:

### ✅ Recommended to Build Into `ovid-client` (v0.3 or sooner)

| Technique | Effort | Expected Hit Rate | What It Gives |
|---|---|---|---|
| Parse `BDMV/META/DL/bdmt_*.xml` | Low — just XML parsing | ~20–40% of Blu-rays | Disc title, sometimes title names |
| Check for DVD text in IFO | Low — `libdvdread` already used | <5% of movie DVDs, ~50% concert DVDs | Chapter names where present |
| Export MPLS chapter timestamps | Low — MPLS already read for fingerprint | 100% of Blu-rays | Chapter start times (not names) |
| HandBrake `--scan --json` integration | Medium — subprocess call; parsing | 100% (but auto-generated names) | Pre-populated title structure for submission |

### ⚠️ Recommended as a Separate Community Tool (not in core client)

| Technique | Effort | Expected Hit Rate | What It Gives |
|---|---|---|---|
| PGS/VobSub AI OCR for chapter names | Medium — runs against extracted subtitle files | Varies; best on concert/anime DVDs | Chapter names from bitmap subtitle streams |
| DVD menu capture via libdvdnav | High — needs framebuffer/VLC headless | ~30% of DVDs with chapter menus | Chapter names from menu graphics |

### ❌ Not Worth Pursuing for OVID

| Technique | Reason |
|---|---|
| Blu-ray BD-J menu capture | Requires Java runtime; not automatable |
| ChapterDB lookup | Database is offline/dead |
| TMDB/IMDB chapter data | These services don't have chapter names at disc level |

---

## Recommended Next Actions for OVID

1. **Immediate (within existing `ovid-client` fingerprint pass):** Add a `bdmt_*.xml` parser. If the file is present, extract disc title and any title names. Include in the JSON output for the submission wizard to pre-populate. Single Python file, no new dependencies.

2. **Near-term (for chapter name beta feature):** Collect chapter timestamps from MPLS during Blu-ray fingerprinting. Store `start_time_secs` in the `disc_chapters` table alongside any community-submitted names. This gives partial data (timestamps without names) that's still useful.

3. **Community tooling (power users):** Publish a standalone `ovid-enrich` utility that accepts an already-ripped disc folder or a PGS/VobSub file and runs the AI OCR pipeline to suggest chapter names. Submits suggestions back via the API. Keeps the core client clean while enabling power contributors.

4. **ARM integration opportunity:** ARM already runs HandBrake. The HandBrake `--scan --json` output could be passed directly to `ovid submit` to pre-populate all structural metadata without any additional disc reading. This is a zero-cost enrichment for ARM users.

---

*Research compiled 2026-04-04*

---

## Sources

- [PyBluRead — Python libbluray wrapper](https://github.com/cmlburnett/PyBluRead)
- [bluinfo — Blu-Ray Metadata Extractor](https://github.com/SavSanta/bluinfo)
- [pympls — Python MPLS parser](https://github.com/rlaphoenix/pympls)
- [pymplschapters — MPLS to Matroska XML chapter extractor](https://github.com/rlaphoenix/pymplschapters)
- [MKVToolNix issue: Parsing Blu-ray title names for MKV chapters](https://gitlab.com/mbunkus/mkvtoolnix/-/issues/2486)
- [subtitles-ai-ocr — PGS/VobSub OCR via Vision Language Models](https://github.com/hekmon/subtitles-ai-ocr)
- [SubExtractor — VOBSUB and PGS to SRT via OCR](https://github.com/bitblaster/SubExtractor)
- [pgs-to-srt — Tesseract-based PGS → SRT](https://github.com/wydengyre/pgs-to-srt)
- [dvdxchap man page — DVD chapter extraction](https://linux.die.net/man/1/dvdxchap)
- [libdvdnav 7.0 / libdvdread 7.0 release notes (2025)](https://jbkempf.com/blog/2025/DVD_audio_edition/)
- [libbluray 1.4.0 release (2025)](https://jbkempf.com/blog/2025/libbluray-1.4.0/)
- [libbluray API reference](https://videolan.videolan.me/libbluray/bluray_8h.html)
- [libdvdnav tutorial](https://codedocs.xyz/xbmc/libdvdnav/tutorial.html)
- [Parsing Blu-ray MPLS Playlist Files](https://thomasguymer.co.uk/blog/2018/2018-02-21/)
- [Blu-ray menu screenshot discussion — VideoHelp](https://forum.videohelp.com/threads/394139-Blu-ray-Menu-Screenshots-Is-there-any-hope)
- [HandBrake CLI documentation](https://handbrake.fr/docs/en/latest/cli/command-line-reference.html)
- [ARM crash when bdmt_eng.xml missing — GitHub issue](https://github.com/automatic-ripping-machine/automatic-ripping-machine/issues/213)
