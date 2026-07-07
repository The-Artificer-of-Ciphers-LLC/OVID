# Phase 07 — Deferred Items

Out-of-scope discoveries surfaced during plan execution but not fixed (SCOPE BOUNDARY:
only auto-fix issues directly caused by the current task's changes).

## From 07-05 (search surface polish)

`npm run lint` was run as an extra verification step beyond the plan's `<verification>`
block (which only specifies `vitest run` + grep checks). It surfaced 2 pre-existing
errors + 3 pre-existing warnings in files 07-05 does not touch:

- `web/components/SetSearchInput.tsx:38` — `react-hooks/set-state-in-effect` error
  (`setResults([])`/`setShowDropdown(false)`/`setLoading(false)` called synchronously
  in a `useEffect` body).
- `web/components/SetSearchInput.tsx:137` — `jsx-a11y/role-has-required-aria-props`
  warning (`role="combobox"` missing `aria-controls`/`aria-expanded`).
- `web/components/SiblingDiscs.tsx:47` — `@typescript-eslint/no-unused-vars` warning
  (`currentFingerprint` defined but unused).
- `web/lib/auth.ts:46` — `react-hooks/set-state-in-effect` error (`setLoading(false)`
  called synchronously in a `useEffect` body).
- `web/src/__tests__/auth.test.ts:23` — `@typescript-eslint/no-unused-vars` warning
  (`_i` defined but unused).

None of these files appear in 07-05's `files_modified` list (`web/app/page.tsx`,
`web/components/SearchForm.tsx`, `web/src/__tests__/pages.test.tsx`), and 07-05's
git diff does not touch them. Confirmed pre-existing (present before this plan's
changes) — not introduced by this plan.
