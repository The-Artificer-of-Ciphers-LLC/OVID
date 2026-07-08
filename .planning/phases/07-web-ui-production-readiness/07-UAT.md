---
status: testing
phase: 07-web-ui-production-readiness
source: [07-VERIFICATION.md]
started: 2026-07-07T23:54:11Z
updated: 2026-07-08T15:26:10Z
---

## Current Test

number: 5
name: Settings: confirm 'Link a provider' initiates the add flow; unlink a provider (min-one stays disabled with correct copy); trigger an email-conflict and confirm the merge banner is styled (not raw JSON), names only current-account providers, offers a re-auth link, and leaks no email/account id.
expected: The full OAuth round-trip (cross-origin session cookie + top-level navigation) succeeds on staging, and the D-04/D-05 merge banner renders and is enumeration-safe in a live browser.
awaiting: user response

## Tests

### 1. Prerequisite staging infra: DNS (staging.oviddb.org + api.staging.oviddb.org), redshirt TLS routing, staging API with CORS_ORIGINS=https://staging.oviddb.org, staging web image built with --build-arg NEXT_PUBLIC_API_URL=https://api.staging.oviddb.org (see docs/deployment.md 'Staging' section).
expected: The staging web app is reachable over HTTPS at https://staging.oviddb.org and calls the staging API successfully (no CORS/redirect failures).
result: pass
verified_by: Prerequisite staging infra verified live end-to-end 2026-07-08 — https://staging.oviddb.org/ HTTP 200 (renders OVID app), https://staging-api.oviddb.org/health HTTP 200, /v1/search HTTP 200, CORS preflight from https://staging.oviddb.org returns access-control-allow-origin + allow-credentials (no CORS/redirect failures). Full D-06 path: Cloudflare Full -> redshirt nginx -> holodeck:3200/8200.

### 2. Search: enter a title on the live staging URL; confirm the input is the centered focal anchor, results/count/pagination render, and the empty-state hint is legible (AA contrast) in BOTH light and dark themes.
expected: Search behaves as coded (verified in code/tests) and reads correctly in a real browser/OS theme, including actual rendered contrast.
result: pass
verified_by: Human-verified in live browser at https://staging.oviddb.org 2026-07-08 — search input anchored/centered, results+count+pagination render, empty-state legible at AA contrast, confirmed in BOTH light and dark themes.

### 3. Disc detail: open a disc; confirm the Fingerprint aliases section lists ALL identity strings with the primary badged (data-testid="fingerprint-aliases"); open an unverified disc and confirm the withheld-structure message renders.
expected: Matches the code/test-verified behavior in a live environment against real disc data.
result: pass
verified_by: Human-verified in live browser 2026-07-08 against seeded sample disc https://staging.oviddb.org/disc/dvdread1-seedmatrix1999 — fingerprint-aliases section lists both identity strings (dvdread1-seedmatrix1999 badged primary, dvd1-seedmatrix1999 alias); unverified-withheld structure message renders.

### 4. Submit: sign in, upload an `ovid fingerprint --json` output, confirm preview + submit success; confirm the set-toggle and fields are keyboard-operable (Tab/Space/Enter) with visible focus rings.
expected: End-to-end submit flow works against the live staging API; keyboard operability is visually confirmed.
result: pass
verified_by: Human-verified in live browser 2026-07-08 — GitHub OAuth sign-in now populates logged-in state with NO manual refresh (auth-state gap G-07-1, fixed); uploaded fingerprint JSON at /submit, preview rendered, submit succeeded (disc dvd1-uatsubmit0001 "Bolt", 2 titles stored, status unverified); set-toggle + fields keyboard-operable (Tab/Space/Enter) with visible focus rings.

### 5. Settings: confirm 'Link a provider' initiates the add flow; unlink a provider (min-one stays disabled with correct copy); trigger an email-conflict and confirm the merge banner is styled (not raw JSON), names only current-account providers, offers a re-auth link, and leaks no email/account id.
expected: The full OAuth round-trip (cross-origin session cookie + top-level navigation) succeeds on staging, and the D-04/D-05 merge banner renders and is enumeration-safe in a live browser.
result: [pending]

### 6. Accessibility (D-03, blocking): tab through every interactive element on all four surfaces; each shows a visible :focus-visible ring; Escape dismisses any open dropdown/dialog; verify WCAG AA contrast (4.5:1 text, 3:1 UI) in BOTH light and dark themes.
expected: Full keyboard operability and AA contrast hold in a real rendered/measured environment.
result: [pending]

## Summary

total: 6
passed: 4
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

### G-07-1 — OAuth callback left auth/nav state stale until manual refresh
status: resolved
severity: major
found_in: Test 4 (sign-in)
reason: web/app/auth/callback/page.tsx stored the token then did a client-side router.replace("/"); useAuth in web/lib/auth.ts reads the token in a mount-only useEffect([]), so the already-mounted NavBar never re-read it — logged-in state only appeared after a hard refresh.
fix: changed the callback success path to a full navigation (window.location.assign("/")) so the app remounts and useAuth re-reads the stored token. Commit 1da1647.
regression_test: web/src/__tests__/auth-callback.test.tsx (commit 4834c93) — asserts setToken + window.location.assign("/") on success, router.replace on error.
verified: 2026-07-08 in live browser on staging (clean sign-in populates without refresh).
resolved_by: 1da1647

### G-07-2 — DVD fingerprints dropped by the web /submit form (title/track/chapter structure lost)
status: open
severity: major
found_in: Test 4 prep (real-disc submit path); web-upload only
reason: `ovid fingerprint --json` emits `structure.{vts_count,title_count,vts}` for DVD (a deliberate, back-compat-frozen client shape), but web/components/SubmitForm.tsx only reads `structure.titles`/`structure.playlists` — never `structure.vts`. So a real DVD fingerprint uploaded at /submit parses to zero titles, renders no chapter editors, and POSTs `titles: []`. Blu-ray/UHD web-upload is unaffected (CLI emits `structure.playlists`, which the form reads). `ovid submit` (CLI) is unaffected (it builds the payload from NormalizedDiscStructure.titles directly, not the JSON). Shipped because the web suite's "DVD" fixture (fingerprintWithTitles in web/src/__tests__/submit.test.tsx) is mislabeled — it uses a `titles` shape the DVD CLI never produces, so no test fed a real vts-shaped DVD JSON through SubmitForm.
chosen_fix: Additively emit the normalized `titles` (already computed by normalize_dvd_disc) in `to_fingerprint_json` (ovid-client/src/ovid/disc_structure.py) alongside the existing `vts`/`playlists` legacy_structure — keeps the frozen shape back-compatible while giving the web form's existing `structure.titles` path real data for DVD. Single source of truth (Python normalization); no TS duplication. Update the client "preserves current shape" tests additively (assert titles now also present, do NOT remove vts/playlists assertions), and add a real DVD-shaped web submit test. Deferred to a follow-up at user direction (not blocking the UAT; Blu-ray + CLI paths work).
verified_bug: confirmed by investigation 2026-07-08 (CLI submit + BD web work; only DVD web-upload affected).
