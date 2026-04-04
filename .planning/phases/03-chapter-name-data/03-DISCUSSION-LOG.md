# Phase 3: Chapter Name Data - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 03-chapter-name-data
**Areas discussed:** Chapter data model, Blu-ray extraction scope, Web UI chapter display, DVD chapter handling

---

## Chapter data model

| Option | Description | Selected |
|--------|-------------|----------|
| Optional names | Chapters can have just index + start_time_secs. Name nullable. | ✓ |
| Required names | Every chapter must have a name. | |
| Name OR timestamp required | At least one of name or start_time must be present. | |

**User's choice:** Optional names
**Notes:** Allows Blu-rays without bdmt to still store timestamp-only chapters from MPLS marks.

| Option | Description | Selected |
|--------|-------------|----------|
| English only | Parse bdmt_eng.xml. Simple, matches ARM. | |
| All languages stored | Parse all bdmt_*.xml variants. Language column. | |
| Primary language only | Parse first bdmt_*.xml found. Single name per chapter. | ✓ |

**User's choice:** Primary language only

| Option | Description | Selected |
|--------|-------------|----------|
| Seconds (int) | Convert ticks to seconds. Simpler API contract. | ✓ |
| Seconds (float) | Decimal seconds for sub-second precision. | |
| Raw ticks + seconds | Store both raw 45kHz ticks and computed seconds. | |

**User's choice:** Seconds (int)

| Option | Description | Selected |
|--------|-------------|----------|
| Nested in title | TitleCreate gets optional chapters list. | ✓ |
| Separate array | Top-level chapters array with title_index references. | |

**User's choice:** Nested in title

| Option | Description | Selected |
|--------|-------------|----------|
| Max 200 chars, 1-based | Name capped at 200 chars. Chapter index starts at 1. | ✓ |
| Max 200 chars, 0-based | Name capped at 200 chars. Index starts at 0. | |
| Unlimited name, 1-based | No length cap. 1-based index. | |

**User's choice:** Max 200 chars, 1-based

| Option | Description | Selected |
|--------|-------------|----------|
| Inherit from disc | Chapters synced as part of parent disc record. | ✓ |
| Own seq_num column | Each chapter row gets its own seq_num. | |

**User's choice:** Inherit from disc

---

## Blu-ray extraction scope

| Option | Description | Selected |
|--------|-------------|----------|
| During fingerprint | Auto-extracted alongside fingerprint. | ✓ |
| Separate step | New `ovid chapters` CLI command. | |
| Both | Auto-extract + standalone command. | |

**User's choice:** During fingerprint

| Option | Description | Selected |
|--------|-------------|----------|
| Silent skip | No bdmt → proceed with MPLS timestamps only. No warning. | ✓ |
| Log a note | INFO-level message that bdmt was not found. | |
| Warn the user | Display visible warning. | |

**User's choice:** Silent skip

| Option | Description | Selected |
|--------|-------------|----------|
| Prefer English, fall back | bdmt_eng.xml first, then first found. | |
| Match disc region | Try to match disc region code to language. | ✓ |
| Let user choose | Present multiple bdmt files in CLI wizard. | |

**User's choice:** Match disc region

---

## Web UI chapter display

| Option | Description | Selected |
|--------|-------------|----------|
| Expandable list | Collapsed by default. Click to expand. | ✓ |
| Always visible table | Compact table always shown. | |
| Summary + modal | Count badge, click for modal. | |

**User's choice:** Expandable list

| Option | Description | Selected |
|--------|-------------|----------|
| Expandable per-title section | Under each title, 'Add chapters' expander with rows. | ✓ |
| Bulk paste | Textarea for pasting chapter data. | |
| Both | Row editor + paste toggle. | |

**User's choice:** Expandable per-title section

---

## DVD chapter handling

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, timestamps only | Extract from IFO PGC. Name-less chapters. | ✓ |
| No, Blu-ray only | Chapter extraction only for Blu-ray. | |
| DVD timestamps + manual names | Extract + prompt for names. | |

**User's choice:** Yes, timestamps only

**Notes:** IFO parser currently has PGCInfo.chapter_count but no per-chapter timestamp extraction. Claude's discretion on implementation approach for cell-time parsing.

---

## Claude's Discretion

- IFO parser cell-time extraction implementation approach
- Chapter list expand/collapse animation and styling
- Start time display format
- Chapter row editor interaction details

## Deferred Ideas

- Multi-language chapter names
- Chapter name editing (post-submission)
- Bulk chapter paste in submit form
- Chapter search/filtering
