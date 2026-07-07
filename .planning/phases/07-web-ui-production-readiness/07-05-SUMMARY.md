---
phase: 07-web-ui-production-readiness
plan: 05
subsystem: ui
tags: [nextjs, react, tailwind-v4, testing-library, vitest, accessibility, focus-visible]

# Dependency graph
requires:
  - phase: 07-web-ui-production-readiness (07-01-SUMMARY.md)
    provides: "@theme token layer (--color-accent, --radius-control, etc.) and Button/Input/Field primitives with baked-in focus-visible ring"
provides:
  - "web/components/SearchForm.tsx migrated to the Button/Input/Field primitives (inherits the D-03 focus-visible ring); submit CTA reads \"Search discs\""
  - "web/app/page.tsx search input rendered as a centered, full-width focal anchor (mx-auto max-w-2xl form, w-full Input)"
  - "no-query empty-state hint at AA-safe contrast (text-neutral-500, not text-neutral-400)"
  - "zero-results empty state extended with the UI-SPEC follow-up line (\"Check the spelling or try a broader title.\")"
  - "web/src/__tests__/pages.test.tsx HomePage describe block (RSC test pattern: await HomePage({searchParams}) then render()) covering CTA label/focus-visible, empty-state copy/contrast, results/zero-results/pagination"
affects: [07-06, 07-07, 07-08, web-ui-production-readiness]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RSC page test pattern reused from disc-detail.test.tsx: vi.mock(\"@/lib/api\") via vi.importActual passthrough + await Page({ searchParams: Promise.resolve(params) }) then render(element)"
    - "next/navigation mocked with both useRouter and useSearchParams (SearchForm is a client component nested inside the server-rendered HomePage tree under test)"

key-files:
  created: []
  modified:
    - "web/app/page.tsx"
    - "web/components/SearchForm.tsx"
    - "web/src/__tests__/pages.test.tsx"
    - "web/package-lock.json"

key-decisions:
  - "Executed Task 2 (tests) before Task 1 (implementation) as a TDD RED->GREEN cycle, per tdd_mode and the plan's own framing of Task 2 as \"RED partner to Task 1\" — matching 07-01/07-04 precedent. 3 of the 5 new HomePage tests failed against the unmodified page.tsx/SearchForm.tsx (CTA label, empty-state contrast, zero-results follow-up hint); the other 2 (results grid, pagination) already passed since that behavior was unchanged, confirming preserved-behavior scope."
  - "Did not touch web/components/Button.tsx's color values: the primary variant already uses bg-blue-600/hover:bg-blue-700, which are the exact hex values UI-SPEC assigns to --color-accent (#2563eb) and --color-accent-hover (#1d4ed8) — Button's primary variant already IS the accent CTA, no change needed."
  - "Rule 1 (auto-fix bug): bumped @tailwindcss/node and @tailwindcss/postcss 4.2.2 -> 4.3.2 (within the existing package.json \"^4\" range) after root-causing a DEP0205 deprecation warning surfaced by the full `npm test` run via `NODE_OPTIONS=--trace-deprecation`. The warning traced to @tailwindcss/node@4.2.2 calling the deprecated module.register() unconditionally on every vitest worker boot instead of checking module.registerHooks() first (Node 26.4.0 supports registerHooks). Verified the fix by unpacking the 4.3.2 tarball and diffing the guard logic before updating. Lockfile diff is scoped entirely to the tailwindcss/@tailwindcss/* package family."
  - "Left WEBUI-01 UNCHECKED in REQUIREMENTS.md. The requirement text is \"Search by movie title returns known disc releases (live at oviddb.org)\" — this plan closes the UI polish/a11y half (anchor, primitives, contrast) but the \"(live at oviddb.org)\" deployment condition is explicitly out of this plan's scope (07-08 covers deploy per this plan's own objective). Marking complete here would be premature; left for 07-08 / the verifier per the task instructions."

patterns-established:
  - "Search surface's centered/widest-control focal anchor achieved via mx-auto max-w-2xl on the form + the Input primitive's baked-in w-full, nested inside the page's existing max-w-5xl container — no changes to the primitives themselves needed."

requirements-completed: []

coverage:
  - id: D1
    description: "SearchForm's title/year inputs and submit control migrated to the 07-01 Button/Input/Field primitives; submit CTA reads \"Search discs\" and inherits the focus-visible ring; useSearchParams stays inside its Suspense boundary; ?q=/year push logic and searchReleases() contract unchanged"
    requirement: "WEBUI-01"
    verification:
      - kind: unit
        ref: "web/src/__tests__/pages.test.tsx#HomePage > renders the submit CTA with the 'Search discs' label and a focus-visible ring"
        status: pass
    human_judgment: false
  - id: D2
    description: "The search input renders as the centered, widest focal control per UI-SPEC (mx-auto max-w-2xl form, full-width Input primitive)"
    requirement: "WEBUI-01"
    verification:
      - kind: manual_procedural
        ref: "Visual layout change (CSS class structure) — no automated pixel/layout assertion in this plan; confirmed via markup structure review (form className=\"mx-auto flex w-full max-w-2xl flex-col gap-4\", Input primitive w-full)"
        status: pass
    human_judgment: true
    rationale: "Visual hierarchy/centering is a layout property Vitest+jsdom cannot meaningfully assert (no real layout engine); needs a human or screenshot-based check to confirm the anchor reads correctly in a browser."
  - id: D3
    description: "No-query empty-state hint renders the UI-SPEC copy at AA-safe contrast (text-neutral-500, not text-neutral-400); grep -c 'text-neutral-400' web/app/page.tsx returns 0"
    requirement: "WEBUI-01"
    verification:
      - kind: unit
        ref: "web/src/__tests__/pages.test.tsx#HomePage > shows the no-query empty state at AA-safe contrast (not neutral-400)"
        status: pass
      - kind: other
        ref: "grep -c 'text-neutral-400' web/app/page.tsx == 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "Zero-results empty state still renders 'No releases found.' plus the UI-SPEC follow-up hint 'Check the spelling or try a broader title.'; results grid, count, and pagination render exactly as before"
    requirement: "WEBUI-01"
    verification:
      - kind: unit
        ref: "web/src/__tests__/pages.test.tsx#HomePage > renders zero-results copy with a follow-up hint; #HomePage > renders the results grid and count when search returns results; #HomePage > renders pagination controls when there are multiple result pages"
        status: pass
    human_judgment: false
  - id: D5
    description: "No sub-4px spacing / no 12px (text-xs) tier introduced in page.tsx or SearchForm.tsx"
    verification:
      - kind: other
        ref: "grep -c 'text-xs' web/app/page.tsx web/components/SearchForm.tsx == 0 for both"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-07
status: complete
---

# Phase 7 Plan 5: Search Surface Anchor + Primitives + AA-Contrast Empty State Summary

**Search input anchored as the centered, primitive-backed focal control (Button/Input/Field, accent "Search discs" CTA) with the borderline empty-state contrast darkened to neutral-500, and a fixed upstream `@tailwindcss/node` deprecation warning root-caused via `--trace-deprecation`.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-07T18:14:47Z
- **Completed:** 2026-07-07T18:26:24Z
- **Tasks:** 2 (executed as one TDD RED->GREEN cycle: Task 2's tests first, confirmed 3/5 failing, then Task 1's implementation)
- **Files modified:** 4 (3 app files + package-lock.json)

## Accomplishments
- Migrated `SearchForm.tsx`'s raw `<input>`/`<button>` to the 07-01 `Input`/`Field`/`Button` primitives, inheriting the `focus-visible:` ring; the submit CTA now reads "Search discs" and uses the primary (accent) `Button` variant. `useSearchParams` remains inside its existing `<Suspense>` boundary; the `?q=`/`year` push logic is byte-identical.
- Restructured the search form's layout (`mx-auto max-w-2xl flex-col`, full-width `Input`) so the title input reads as the centered, widest focal control per UI-SPEC, with the year field and submit CTA as secondary controls below it.
- Darkened the no-query empty-state hint from `text-neutral-400` to `text-neutral-500` (clears the D-03 AA contrast gate) and added the UI-SPEC zero-results follow-up line ("Check the spelling or try a broader title.").
- Added a `HomePage` RSC test suite to `pages.test.tsx` (5 new tests, following the `disc-detail.test.tsx` `await Page({searchParams}) → render()` pattern) proving the CTA label/focus-visible ring, empty-state contrast, and preserved results/zero-results/pagination behavior.
- Root-caused and fixed a `DEP0205` deprecation warning (`module.register()` is deprecated) surfaced by the full `npm test` run: traced via `NODE_OPTIONS=--trace-deprecation` to `@tailwindcss/node@4.2.2` calling the deprecated Node API unconditionally instead of checking `module.registerHooks()` first; bumped to `4.3.2` (within the existing `^4` range) after confirming the fix by diffing the packed tarball.

## Task Commits

Each task was committed atomically. Task 2 and Task 1 were executed as a single TDD RED→GREEN cycle (Task 2's full test set written and confirmed failing first, then Task 1's implementation turned it green), per the plan's own framing of Task 2 as "RED partner to Task 1."

1. **Task 2 (RED): Extend pages tests — focus-visible + empty-state copy/contrast + preserved search behavior** - `ef5db4f` (test) — 5 new tests added to `pages.test.tsx`; confirmed 3/5 failing against the unmodified page.
2. **Task 1 (GREEN): Anchor the search input + migrate SearchForm to primitives + fix empty-state contrast** - `a13aa0b` (feat) — `page.tsx`/`SearchForm.tsx` implementation turns the RED suite green (20/20 pass in the file, 81/81 across the whole `web` suite); folded in the Rule 1 `@tailwindcss/node`/`@tailwindcss/postcss` dependency bump discovered during verification.

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `web/app/page.tsx` - Darkened `text-neutral-400` → `text-neutral-500` empty-state hint; added zero-results follow-up copy ("Check the spelling or try a broader title.").
- `web/components/SearchForm.tsx` - Migrated to `Button`/`Input`/`Field` primitives; centered `mx-auto max-w-2xl` layout with the title `Input` as the widest control; CTA copy "Search discs".
- `web/src/__tests__/pages.test.tsx` - New `HomePage` describe block (5 tests): CTA label + focus-visible ring, no-query empty-state contrast, zero-results follow-up hint, results grid/count, pagination.
- `web/package-lock.json` - `@tailwindcss/node`/`@tailwindcss/postcss` (and transitive `@tailwindcss/oxide-*` platform binaries) `4.2.2` → `4.3.2`.

## Decisions Made
- Task 2/Task 1 executed as one TDD RED→GREEN unit (see Task Commits) — matches 07-01/07-04 precedent for plans with an explicit "RED partner" task relationship.
- No change needed to `Button.tsx`'s color values — its `primary` variant (`bg-blue-600`/`hover:bg-blue-700`) already matches UI-SPEC's `--color-accent`/`--color-accent-hover` hex values exactly; it already *is* the accent CTA.
- Rule 1 auto-fix: upgraded `@tailwindcss/node`/`@tailwindcss/postcss` to `4.3.2` to eliminate a genuine upstream `DEP0205` deprecation warning surfaced during this plan's `npm test` verification run, per the no-waving-off-warnings requirement. Root-caused with `NODE_OPTIONS=--trace-deprecation` (pointed at `@tailwindcss/node/dist/index.js:18`, not Vite/Vitest's own — already-guarded — `module.registerHooks()` call sites) and confirmed the fix exists in `4.3.2` by unpacking and diffing the tarball before updating. Within the already-declared `"^4"` semver range — not a new/unvetted package (Rule 3's package-install exclusion does not apply).
- Left `WEBUI-01` unchecked in `REQUIREMENTS.md` — the requirement text includes "(live at oviddb.org)", a deployment condition this plan does not touch (07-08 owns deploy per this plan's own objective). Documented in coverage `D2` (visual anchor, human-judgment) and this note rather than marking the requirement complete.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Upgraded `@tailwindcss/node`/`@tailwindcss/postcss` 4.2.2 → 4.3.2 to fix an upstream `DEP0205` deprecation warning**
- **Found during:** Task 1 verification (`npm test` full suite run)
- **Issue:** Every full `vitest run` (multi-file) printed `(node:PID) [DEP0205] DeprecationWarning: \`module.register()\` is deprecated. Use \`module.registerHooks()\` instead.` — root-caused via `NODE_OPTIONS=--trace-deprecation` to `@tailwindcss/node@4.2.2` (transitive dep of `@tailwindcss/postcss`) calling `module.register()` unconditionally on every worker boot instead of checking `module.registerHooks()` first (both Vite's and Vitest's own call sites were already properly guarded).
- **Fix:** `npm update tailwindcss @tailwindcss/postcss` → `4.3.2`, within the existing `package.json` `"^4"` range. Verified the fix exists in `4.3.2` by unpacking the tarball and diffing the module-registration guard before applying.
- **Files modified:** `web/package-lock.json` (scoped entirely to the `tailwindcss`/`@tailwindcss/*` family — confirmed via `git diff --stat`)
- **Verification:** `npm test` (81/81 pass, warning gone), `npx tsc --noEmit` (clean), `npm run build` (clean production build, no new warnings)
- **Committed in:** `a13aa0b` (Task 1/GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug — upstream deprecation warning)
**Impact on plan:** Fix is a lockfile-only dependency bump within the already-declared semver range; no application code, API, or test behavior changed. No scope creep.

**Out-of-scope discoveries (not fixed, logged per SCOPE BOUNDARY):** `npm run lint` (run as an extra verification step beyond the plan's own `<verification>` block) surfaced 2 pre-existing errors + 3 pre-existing warnings in files this plan does not touch (`web/components/SetSearchInput.tsx`, `web/components/SiblingDiscs.tsx`, `web/lib/auth.ts`, `web/src/__tests__/auth.test.ts`). Logged to [`deferred-items.md`](./deferred-items.md); confirmed pre-existing (outside this plan's `git diff`).

## Issues Encountered
None beyond the deprecation-warning root-cause investigation documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- The search surface (WEBUI-01's UI/a11y half) is anchored, primitive-backed, and AA-contrast compliant; all prior search behavior (query push, result grid, count, pagination, zero-results, no-query empty state) is proven unchanged by `pages.test.tsx`.
- `WEBUI-01` remains open in `REQUIREMENTS.md` pending 07-08's deploy/staging-sign-off half ("live at oviddb.org").
- `web/components/SetSearchInput.tsx`, `web/components/SiblingDiscs.tsx`, `web/lib/auth.ts`, and `web/src/__tests__/auth.test.ts` have pre-existing lint issues (`react-hooks/set-state-in-effect`, `jsx-a11y/role-has-required-aria-props`, unused vars) tracked in `deferred-items.md` — out of this plan's scope but worth a future cleanup pass.
- Full `web` suite remains green (81/81) and `tsc --noEmit`/`next build` are clean — no regressions introduced.
- No blockers for 07-06 onward.

---
*Phase: 07-web-ui-production-readiness*
*Completed: 2026-07-07*

## Self-Check: PASSED

All 4 created/modified files (`web/app/page.tsx`, `web/components/SearchForm.tsx`,
`web/src/__tests__/pages.test.tsx`, `web/package-lock.json`) plus this SUMMARY.md and
`deferred-items.md` confirmed present on disk; both task commits (`ef5db4f`, `a13aa0b`)
confirmed in `git log`.
