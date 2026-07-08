---
status: testing
phase: 07-web-ui-production-readiness
source: [07-VERIFICATION.md]
started: 2026-07-07T23:54:11Z
updated: 2026-07-08T01:57:29Z
---

## Current Test

number: 2
name: Search: enter a title on the live staging URL; confirm the input is the centered focal anchor, results/count/pagination render, and the empty-state hint is legible (AA contrast) in BOTH light and dark themes.
expected: Search behaves as coded (verified in code/tests) and reads correctly in a real browser/OS theme, including actual rendered contrast.
awaiting: user response

## Tests

### 1. Prerequisite staging infra: DNS (staging.oviddb.org + api.staging.oviddb.org), redshirt TLS routing, staging API with CORS_ORIGINS=https://staging.oviddb.org, staging web image built with --build-arg NEXT_PUBLIC_API_URL=https://api.staging.oviddb.org (see docs/deployment.md 'Staging' section).
expected: The staging web app is reachable over HTTPS at https://staging.oviddb.org and calls the staging API successfully (no CORS/redirect failures).
result: pass
verified_by: Prerequisite staging infra verified live end-to-end 2026-07-08 — https://staging.oviddb.org/ HTTP 200 (renders OVID app), https://staging-api.oviddb.org/health HTTP 200, /v1/search HTTP 200, CORS preflight from https://staging.oviddb.org returns access-control-allow-origin + allow-credentials (no CORS/redirect failures). Full D-06 path: Cloudflare Full -> redshirt nginx -> holodeck:3200/8200.

### 2. Search: enter a title on the live staging URL; confirm the input is the centered focal anchor, results/count/pagination render, and the empty-state hint is legible (AA contrast) in BOTH light and dark themes.
expected: Search behaves as coded (verified in code/tests) and reads correctly in a real browser/OS theme, including actual rendered contrast.
result: [pending]

### 3. Disc detail: open a disc; confirm the Fingerprint aliases section lists ALL identity strings with the primary badged (data-testid="fingerprint-aliases"); open an unverified disc and confirm the withheld-structure message renders.
expected: Matches the code/test-verified behavior in a live environment against real disc data.
result: [pending]

### 4. Submit: sign in, upload an `ovid fingerprint --json` output, confirm preview + submit success; confirm the set-toggle and fields are keyboard-operable (Tab/Space/Enter) with visible focus rings.
expected: End-to-end submit flow works against the live staging API; keyboard operability is visually confirmed.
result: [pending]

### 5. Settings: confirm 'Link a provider' initiates the add flow; unlink a provider (min-one stays disabled with correct copy); trigger an email-conflict and confirm the merge banner is styled (not raw JSON), names only current-account providers, offers a re-auth link, and leaks no email/account id.
expected: The full OAuth round-trip (cross-origin session cookie + top-level navigation) succeeds on staging, and the D-04/D-05 merge banner renders and is enumeration-safe in a live browser.
result: [pending]

### 6. Accessibility (D-03, blocking): tab through every interactive element on all four surfaces; each shows a visible :focus-visible ring; Escape dismisses any open dropdown/dialog; verify WCAG AA contrast (4.5:1 text, 3:1 UI) in BOTH light and dark themes.
expected: Full keyboard operability and AA contrast hold in a real rendered/measured environment.
result: [pending]

## Summary

total: 6
passed: 1
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
