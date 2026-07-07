---
phase: 07-web-ui-production-readiness
plan: 01
subsystem: ui
tags: [tailwind-v4, theme-tokens, react, nextjs, accessibility, focus-visible, vitest, testing-library]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness (07-UI-SPEC.md)
    provides: token names/values (accent/destructive/radius), typography scale, focus-visible ring spec
provides:
  - "web/app/globals.css @theme token layer (--color-accent, --color-accent-ring, --color-accent-hover, --color-destructive, --radius-control, --radius-card)"
  - "web/components/Button.tsx shared primitive (variant=primary|ghost, focus-visible ring, data-testid passthrough)"
  - "web/components/Input.tsx shared primitive (focus-visible ring, data-testid passthrough)"
  - "web/components/Field.tsx shared primitive (label/id association, aria-live error region)"
affects: [07-02, 07-03, 07-04, 07-05, 07-06, 07-07, 07-08, web-ui-production-readiness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tailwind v4 @theme block extended (CSS-first, no tailwind.config.*) for design tokens"
    - "focus-visible: (not mouse-noisy focus:) baked into shared primitives so every consumer inherits keyboard-visible focus"
    - "Field takes an explicit id prop and expects the child control to share the same id — no cloneElement magic"

key-files:
  created:
    - web/components/Button.tsx
    - web/components/Input.tsx
    - web/components/Field.tsx
    - web/src/__tests__/primitives.test.tsx
  modified:
    - web/app/globals.css

key-decisions:
  - "Executed Task 2 (primitives) and Task 3 (tests) as a single RED->GREEN TDD cycle: wrote primitives.test.tsx first (confirmed failing — Failed to resolve import), then implemented Button/Input/Field to green, per tdd_mode instructions."
  - "Kept the existing @media (prefers-color-scheme: dark) strategy; did NOT add @custom-variant dark per plan_assumption (RESEARCH A1) despite UI-SPEC prose mentioning it — avoids breaking OS-following dark mode with no toggle in scope."
  - "data-testid explicitly typed as an optional string field on ButtonProps/InputProps (not inferred from HTMLAttributes) because TS's JSX data-*/aria-* exemption only applies to intrinsic elements, not custom components."

patterns-established:
  - "Shared primitive components live in web/components/ as PascalCase.tsx, extend the matching React *HTMLAttributes type, and explicitly declare data-testid passthrough."
  - "focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-neutral-950 is the canonical D-03 focus string for every interactive primitive."

requirements-completed: [WEBUI-01, WEBUI-02, WEBUI-03, WEBUI-04]

coverage:
  - id: D1
    description: "globals.css @theme token layer (accent/accent-ring/accent-hover/destructive/radius-control/radius-card) usable as Tailwind utilities; starter Arial/Helvetica body override removed so Geist font-sans is the single sans source; @media (prefers-color-scheme: dark) strategy preserved"
    requirement: "WEBUI-01"
    verification:
      - kind: other
        ref: "grep -c 'color-accent' web/app/globals.css (returns 3) && grep -Ec 'Helvetica|custom-variant' web/app/globals.css (returns 0)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Button/Input/Field primitives with baked-in focus-visible ring, variant support (primary accent-fill / ghost neutral-bordered), data-testid passthrough, and Field label/id + aria-live error association"
    requirement: "WEBUI-01"
    verification:
      - kind: unit
        ref: "web/src/__tests__/primitives.test.tsx (10 tests: focus-visible class, Tab/Enter/Space keyboard, disabled no-op, ghost-no-accent, label/id association, aria-live error region)"
        status: pass
    human_judgment: false
  - id: D3
    description: "No regressions to the existing web test suite or strict-TS typecheck after introducing the primitives and token layer"
    verification:
      - kind: unit
        ref: "cd web && npm test (68/68 tests pass, 58 pre-existing + 10 new)"
        status: pass
      - kind: other
        ref: "cd web && npx tsc --noEmit (no errors)"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 1: Design Token Layer + Shared Primitives Summary

**Tailwind v4 `@theme` accent/destructive/radius tokens plus hand-authored Button/Input/Field primitives with a baked-in `focus-visible:` ring, laying the D-02/D-03 foundation every downstream Phase 7 UI plan will consume.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-07T17:30:09Z
- **Completed:** 2026-07-07T17:36:51Z
- **Tasks:** 3 (executed as Task 1 standalone + Task 2/3 as one TDD RED→GREEN cycle)
- **Files modified:** 5 (1 modified, 4 created)

## Accomplishments
- Extended `web/app/globals.css`'s existing `@theme` block with the UI-SPEC color/radius tokens (`--color-accent`, `--color-accent-ring`, `--color-accent-hover`, `--color-destructive`, `--radius-control`, `--radius-card`) and removed the Next.js-starter `font-family: Arial, Helvetica, sans-serif` override so Geist `font-sans` (from `layout.tsx`) is the single sans source.
- Authored three strict-TS, hand-built primitives in `web/components/`: `Button` (primary/ghost variants, accent reserved for primary), `Input`, and `Field` (label/id association + `aria-live="polite"` error region) — each carrying the D-03 focus-visible ring and `data-testid` passthrough.
- Wrote `web/src/__tests__/primitives.test.tsx` (10 tests) proving focus-visible class presence, Tab/Enter/Space keyboard operability, disabled no-op, ghost-variant has no accent fill, label/id association, and the aria-live error region — following true RED→GREEN TDD (test file committed first while failing, then primitives committed to turn it green).

## Task Commits

Each task was committed atomically. Tasks 2 and 3 were executed as a single TDD RED→GREEN cycle (test file first, confirmed failing, then implementation), per `tdd_mode` instructions and the plan's own note that Task 3 is "the RED→GREEN partner to Task 2."

1. **Task 3 (RED): Primitive a11y tests** - `1c1d3ba` (test) — `web/src/__tests__/primitives.test.tsx` created; confirmed failing (`Failed to resolve import "@/components/Button"`) before any implementation existed.
2. **Task 2 (GREEN): Button/Input/Field primitives** - `0dcc4ac` (feat) — implementation turns the RED suite green (10/10 pass).
3. **Task 1: `@theme` token layer + starter font drift removal** - `dd7a695` (feat) — `web/app/globals.css`.

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `web/app/globals.css` - Adds accent/accent-ring/accent-hover/destructive/radius-control/radius-card `@theme` tokens; removes the starter Arial/Helvetica body font override; keeps the `@media (prefers-color-scheme: dark)` block untouched.
- `web/components/Button.tsx` - New primitive; `variant?: "primary" | "ghost"` (default primary), focus-visible ring, `data-testid` passthrough.
- `web/components/Input.tsx` - New primitive; focus-visible ring replacing SearchForm's mouse-noisy `focus:`, `data-testid` passthrough.
- `web/components/Field.tsx` - New primitive; `{ id, label, error?, children }`, `<label htmlFor={id}>` + `aria-live="polite"` error slot.
- `web/src/__tests__/primitives.test.tsx` - New Vitest + Testing Library + `user-event` suite (10 tests) proving the D-03 accessibility floor.

## Decisions Made
- Executed Task 2 and Task 3 as one TDD RED→GREEN unit (test-first, confirmed-failing, then implementation-to-green) rather than in the plan's listed file order, because the plan explicitly frames Task 3 as "the RED→GREEN partner to Task 2" and `tdd_mode` requires a genuine failing-test-first cycle.
- Preserved the `@media (prefers-color-scheme: dark)` strategy and did not add a `@custom-variant dark (...)` class/data-attribute toggle, per the plan's own `<plan_assumption>` (RESEARCH A1) — the UI-SPEC prose mentions `@custom-variant dark` but the plan and PATTERNS.md both resolve that a manual toggle would break the existing OS-following dark mode and is out of scope.
- Typed `data-testid` explicitly as an optional prop on `ButtonProps`/`InputProps` rather than relying on TypeScript's JSX data-*/aria-* exemption, because that exemption only applies to intrinsic (lowercase) JSX elements, not custom React components — an implicit-`any`-avoidance / strict-TS correctness fix, not a deviation from the plan's intent.

## Deviations from Plan

None - plan executed exactly as written (Task 2/Task 3 execution ORDER was TDD-sequenced per the plan's own instructions; no scope, files, or behavior changed from what was specified).

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The `@theme` token layer and `Button`/`Input`/`Field` primitives are ready for every downstream Wave-2 UI plan (disc detail, search, submit, settings) to migrate bespoke controls onto.
- Full `web` test suite remains green (68/68) and `tsc --noEmit` is clean — no regressions introduced.
- No blockers for 07-02 onward.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

All 5 created/modified files confirmed present on disk; all 3 task commits (`1c1d3ba`, `0dcc4ac`, `dd7a695`) confirmed in `git log`.
