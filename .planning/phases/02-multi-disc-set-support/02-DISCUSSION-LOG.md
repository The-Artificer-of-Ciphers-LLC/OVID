# Phase 2: Multi-Disc Set Support - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 02-multi-disc-set-support
**Areas discussed:** Set creation flow, Sibling disc display, Set ownership & editing, Submit form UX, API response shape, Set search & discovery, Orphan set cleanup, CLI set workflow, Edition name semantics, Set + release relationship, Backward compatibility

---

## Set Creation Flow

| Option | Description | Selected |
|--------|-------------|----------|
| Implicit on first submit | Auto-create set when disc_number > 1 or total_discs > 1 | ✓ |
| Explicit creation first | POST /v1/set required before disc submission | |
| Both — smart fallback | POST /v1/set for explicit + auto-create on submit | |

**User's choice:** Implicit on first submit
**Notes:** Follow-up confirmed POST /v1/set should also exist for programmatic clients (ARM, CLI).

## Set API Endpoint

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — both paths | POST /v1/set for explicit + implicit on disc submit | ✓ |
| No — implicit only | Sets only created as side effect of disc submission | |

**User's choice:** Yes — both paths

## Sibling Disc Display

| Option | Description | Selected |
|--------|-------------|----------|
| Inline card row | Horizontal row below main disc info | ✓ |
| Expandable section | Collapsed by default, click to expand | |
| Sidebar panel | Right sidebar with siblings | |

**User's choice:** Inline card row

## Sibling Card Info

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal — disc number + format | Compact, clean | |
| Medium — add main title | More informative | |
| Rich — full preview | Disc number, format, main title, duration, track count | ✓ |

**User's choice:** Rich — full preview

## Set Ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Anyone authenticated | Community-driven, open contribution | ✓ |
| Creator only | Only set creator can add discs | |
| Anyone + verification | Proposals go through verification | |

**User's choice:** Anyone authenticated

## Disc Number Conflicts

| Option | Description | Selected |
|--------|-------------|----------|
| Reject with 409 | First come, first served | ✓ |
| Allow duplicates | Multiple discs same number | |
| Auto-increment | Assign next available | |

**User's choice:** Reject with 409

## Submit Form UX

| Option | Description | Selected |
|--------|-------------|----------|
| Toggle + search existing sets | Search-as-you-type for existing sets | ✓ |
| Toggle + always new set | Always creates new set | |
| No toggle — always show fields | Fields always visible | |

**User's choice:** Toggle + search existing sets

## API Response Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Nested set object | disc_set object with siblings array in response | ✓ |
| Flat fields + separate endpoint | disc_set_id in response, GET /v1/set for siblings | |
| Flat fields + Link header | REST-pure with link following | |

**User's choice:** Nested set object

## Set Search & Discovery

| Option | Description | Selected |
|--------|-------------|----------|
| Disc-only discovery | Sets found only through disc lookups | |
| GET /v1/set with search | Search by release name/edition | ✓ |
| GET /v1/set basic list only | Paginated list, no search | |

**User's choice:** GET /v1/set endpoint with search

## Orphan Set Cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Keep forever | Orphan sets persist | ✓ |
| Soft-delete after 30 days | Flag empty sets | |
| Auto-delete immediately | Delete when last disc unlinked | |

**User's choice:** Keep forever

## CLI Set Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Prompt when disc_number detected | Smart prompting based on metadata | ✓ |
| Always prompt for set info | Every submit asks about sets | |
| Flag-based only | No interactive prompting | |

**User's choice:** Prompt when disc_number detected

## Edition Name Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Free text | Unrestricted string | |
| Suggested + free text | Autocomplete with common values, free text allowed | ✓ |
| Constrained enum | Predefined list | |

**User's choice:** Suggested + free text

## Set + Release Relationship

| Option | Description | Selected |
|--------|-------------|----------|
| Keep 1:1 with release | Existing FK, matches MusicBrainz model | ✓ |
| Remove release_id, make independent | Sets exist without release | |
| Optional release_id | Nullable FK | |

**User's choice:** Keep 1:1 with release

## Backward Compatibility

| Option | Description | Selected |
|--------|-------------|----------|
| Additive only — all new fields optional | Existing clients unchanged | ✓ |
| Validate disc_number always | Enforce on all discs | |
| Version the API | New fields in /v2 only | |

**User's choice:** Additive only — all new fields optional

## Claude's Discretion

- Autocomplete implementation for edition name suggestions
- Set search pagination and sort order
- Sibling card responsive breakpoints
- Alembic migration approach
- Test fixture design
- Error message wording for 409 conflicts

## Deferred Ideas

- TV series episode-to-title mapping — v0.4.0
- Browse/explore sets page — Phase 6
- Set merge/split tool — future moderation
- Set cover art — not in v0.3.0
