---
phase: 07-web-ui-production-readiness
plan: 04
subsystem: ui
tags: [nextjs, react, tailwind-v4, testing-library, vitest, accessibility, focus-visible]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness (07-01-SUMMARY.md)
    provides: "@theme token layer (--color-accent, --radius-control, etc.) and Button/Input/Field primitives with baked-in focus-visible ring"
  - phase: 07-web-ui-production-readiness (07-03-SUMMARY.md)
    provides: "status-gated sibling redaction (unverified siblings withhold main_title/duration_secs/track_count) that the disc-detail page's rendering must tolerate"
provides:
  - "disc/[fingerprint]/page.tsx renders a data-testid=\"fingerprint-aliases\" section iterating disc.fingerprint_aliases verbatim (primary badge, method label, never hidden/renumbered)"
  - "Unverified-withheld message (\"Structure withheld until a second contributor verifies this disc.\") replacing the generic empty-titles state"
  - "SiblingDiscs.tsx and ChapterList.tsx at D-02 token / D-03 focus-visible parity (no 12px tier, keyboard-visible focus rings)"
  - "disc-detail.test.tsx DiscDetailPage RSC test harness (vi.mock @/lib/api, makeDisc/renderDiscDetail helpers) reusable by later Phase 7 plans"
affects: [07-05, 07-06, 07-07, 07-08, web-ui-production-readiness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Testing an async Next.js Server Component directly: await DiscDetailPage({ params: Promise.resolve({...}) }) then render() the returned element, with @/lib/api mocked via vi.mock + vi.importActual (keeps ApiError real, only getDisc/getDiscEdits mocked)"
    - "within(screen.getByTestId(...)) scoping to disambiguate duplicate text across sibling regions (the primary alias fingerprint also appears in the top-level Fingerprint: block)"

key-files:
  created: []
  modified:
    - "web/app/disc/[fingerprint]/page.tsx"
    - "web/components/SiblingDiscs.tsx"
    - "web/components/ChapterList.tsx"
    - "web/src/__tests__/disc-detail.test.tsx"

key-decisions:
  - "Executed Task 1 and Task 3 as a single TDD RED→GREEN unit (Task 3's full test set written first as the RED commit, then Task 1's page.tsx implementation as the GREEN commit), matching the plan's own framing of Task 3 as \"the RED partner for Task 1\" and the precedent 07-01-SUMMARY.md set for overlapping TDD tasks. No separate Task 3 commit exists; its scope is fully covered by the 5bb767b test commit."
  - "Marked WEBUI-02 complete: the requirement's other half (full normalized structure — titles, main-feature marker, chapters, audio/subtitle tracks) was already rendered pre-plan via DiscStructure.tsx/ChapterList.tsx; this plan closed the one remaining gap (fingerprint aliases) that the plan's own objective called \"the single biggest requirement gap in the phase.\" Both halves are now proven by disc-detail.test.tsx."
  - "fingerprint-aliases <section data-testid> always renders (never conditionally omitted) with the empty-state copy INSIDE it, per the plan's <behavior> wording, rather than PATTERNS.md's illustrative snippet which placed the fallback <p> outside the section — the plan's explicit acceptance criteria (data-testid region present regardless of alias count) took precedence."
  - "Chose to add the focus-visible ring directly to ChapterList's toggle <button> rather than swapping it for the shared Button primitive — Button's box/border styling would change the inline chapter-count toggle's visual shape, which is out of this task's styling-parity-only scope."

patterns-established:
  - "RSC page tests live in the same *.test.tsx as their child-component tests (disc-detail.test.tsx covers SiblingDiscs, ChapterList, AND DiscDetailPage) rather than a separate page-level test file — extends the existing file rather than fragmenting coverage."

requirements-completed: [WEBUI-02]

coverage:
  - id: D1
    description: "Disc detail page renders a fingerprint-aliases section showing every fingerprint_aliases entry verbatim (dvd1-*, dvdread1-*, BD tiers), with the primary alias badged — none hidden or renumbered"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — fingerprint aliases (WEBUI-02) > renders the fingerprint-aliases section with all identity strings and the primary badge"
        status: pass
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — alias completeness + withheld edge cases (WEBUI-02 gap closure) > renders every provided alias without hiding or renumbering, including dvd1- and dvdread1- identity strings"
        status: pass
    human_judgment: false
  - id: D2
    description: "No-aliases empty state shows the exact UI-SPEC copy \"No additional fingerprint aliases recorded.\" for 0, 1 (boundary), and undefined fingerprint_aliases"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — fingerprint aliases (WEBUI-02) > shows the no-aliases empty copy when there are no additional aliases"
        status: pass
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — alias completeness + withheld edge cases (WEBUI-02 gap closure) > shows the no-aliases empty copy for a single-alias disc (boundary: length === 1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Unverified discs (titles: []) show \"Structure withheld until a second contributor verifies this disc.\" instead of the generic empty-titles message; no titles table renders; aliases and release info still render"
    requirement: "WEBUI-02"
    verification:
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — fingerprint aliases (WEBUI-02) > shows the unverified-withheld message instead of a titles table when status is unverified"
        status: pass
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx#DiscDetailPage — alias completeness + withheld edge cases (WEBUI-02 gap closure) > renders aliases and release info even when the disc is unverified"
        status: pass
    human_judgment: false
  - id: D4
    description: "SiblingDiscs and ChapterList meet the D-02 token / D-03 accessibility floor: no text-xs (12px tier), no sub-4px spacing, focus-visible ring on interactive elements, all prior data-testid values intact"
    verification:
      - kind: unit
        ref: "web/src/__tests__/disc-detail.test.tsx (SiblingDiscs + ChapterList describe blocks, 17 pre-existing tests, all still pass)"
        status: pass
      - kind: other
        ref: "grep -c 'text-xs' web/components/SiblingDiscs.tsx web/components/ChapterList.tsx (both return 0); grep -nE 'py-0\\.5|mt-0\\.5|px-0\\.5' (0 matches)"
        status: pass
    human_judgment: false

# Metrics
duration: 3min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 4: Fingerprint Aliases + Unverified-Withheld Message Summary

**Disc detail page now renders every `fingerprint_aliases[]` identity string (primary badged, never hidden/renumbered) and shows an explicit "Structure withheld" message for unverified discs instead of a generic empty state — closing the phase's single biggest requirement gap (WEBUI-02).**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-07T14:09:42-04:00
- **Completed:** 2026-07-07T14:11:58-04:00
- **Tasks:** 3 (Task 1 + Task 3 executed as one TDD RED→GREEN unit, then Task 2)
- **Files modified:** 4

## Accomplishments
- Added the `data-testid="fingerprint-aliases"` section to `disc/[fingerprint]/page.tsx`, iterating `disc.fingerprint_aliases` verbatim (Geist Mono `<code>`, method label, "primary" badge on `is_primary`) — the previously-never-iterated `fingerprint_aliases[]` field is now fully surfaced (WEBUI-02).
- Replaced the generic "No title structure available." path with an explicit "Structure withheld until a second contributor verifies this disc." message when `disc.status === "unverified"` (Pitfall 4), while aliases and release metadata continue to render.
- Folded every `text-xs` occurrence in `page.tsx`, `SiblingDiscs.tsx`, and `ChapterList.tsx` up to `text-sm` (UI-SPEC: no 12px tier) and added the canonical D-03 `focus-visible:` ring to the sibling-card link and the chapter expand/collapse toggle.
- Extended `disc-detail.test.tsx` with a full `DiscDetailPage` RSC test harness (8 new tests: alias rendering + primary badge, no-alias empty copy at 0/1/undefined boundaries, unverified-withheld copy, and alias/release visibility during withheld state) — 25/25 tests in the file pass, 76/76 across the whole `web` suite.

## Task Commits

Each task was committed atomically. Task 1 and Task 3 were executed as a single TDD RED→GREEN cycle (Task 3's full test set written and confirmed failing first, then Task 1's implementation turned it green), per the plan's own framing of Task 3 as "the RED partner for Task 1."

1. **Task 3 (RED): Extend disc-detail tests — alias rendering + withheld message** - `5bb767b` (test) — 8 new tests added to `disc-detail.test.tsx`; confirmed failing (8/8 fail) against the unmodified page.
2. **Task 1 (GREEN): Render fingerprint aliases + unverified-withheld message** - `07a5c14` (feat) — `disc/[fingerprint]/page.tsx` implementation turns the RED suite green (25/25 pass).
3. **Task 2: Migrate SiblingDiscs + ChapterList to D-02/D-03 floor** - `a90f141` (refactor) — token/focus parity, no behavior or data-testid changes.

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `web/app/disc/[fingerprint]/page.tsx` - New fingerprint-aliases `<section>` (WEBUI-02), unverified-withheld branch replacing `DiscStructure`, fingerprint block + status badge folded from `text-xs` to `text-sm`.
- `web/components/SiblingDiscs.tsx` - All `text-xs` folded to `text-sm`; sibling-card `<Link>` gets the D-03 `focus-visible:` ring (`outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950`).
- `web/components/ChapterList.tsx` - Chapter-table `text-xs` folded to `text-sm`; expand/collapse toggle `<button>` gets the same `focus-visible:` ring.
- `web/src/__tests__/disc-detail.test.tsx` - Extended with a `DiscDetailPage` RSC test harness (`vi.mock("@/lib/api")` via `vi.importActual` passthrough, `makeDisc`/`renderDiscDetail` helpers) and 8 new tests.

## Decisions Made
- Task 1/Task 3 executed as one TDD RED→GREEN unit (see Task Commits) — matches 07-01's precedent for plans with an explicit "RED partner" task relationship.
- Marked `WEBUI-02` complete in REQUIREMENTS.md: the "full normalized structure" half of the requirement was already delivered pre-plan (`DiscStructure.tsx`/`ChapterList.tsx` already render titles, main-feature marker, chapters, audio/subtitle tracks); this plan closed the remaining "shows fingerprint aliases" gap. Both halves are now proven by `disc-detail.test.tsx`.
- The `fingerprint-aliases` section always renders (testid present regardless of alias count), with the empty-state copy nested inside it, following the plan's `<behavior>` block over PATTERNS.md's illustrative snippet (which had placed the fallback outside the section).
- Added the focus-visible ring directly to `ChapterList`'s toggle button rather than swapping it for the shared `Button` primitive, to avoid changing the toggle's compact inline visual shape (out of this task's styling-parity-only scope).

## Deviations from Plan

None - plan executed exactly as written (Task 1/Task 3 execution ORDER was TDD-sequenced per the plan's own "RED partner" framing; no scope, files, or behavior changed from what was specified).

## Issues Encountered
- The first alias-rendering test collided with the existing top-level "Fingerprint:" block, because the primary alias's fingerprint value equals `disc.fingerprint` (both render "dvd1-primary123" on the page) — `getByText` threw a multiple-elements error. Fixed by scoping that one assertion to `within(screen.getByTestId("fingerprint-aliases"))`; not a plan defect, just a test-fixture overlap peculiar to real disc data where the primary alias IS the canonical fingerprint.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- WEBUI-02 is now genuinely complete: fingerprint aliases render alongside the pre-existing full structure rendering, both proven by automated tests.
- `SiblingDiscs`/`ChapterList` are at full D-02/D-03 parity, ready for any further disc-detail polish in 07-05 through 07-08.
- The `DiscDetailPage` RSC test harness (`makeDisc`/`renderDiscDetail`) in `disc-detail.test.tsx` is reusable by later plans that touch this page.
- Full `web` suite remains green (76/76) and `tsc --noEmit` is clean — no regressions introduced.
- No blockers for 07-05 onward.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 3 task commits (`5bb767b`, `07a5c14`, `a90f141`) confirmed in `git log`.
