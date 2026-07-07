---
status: testing
phase: 06-oauth-account-linking
source: [06-VERIFICATION.md]
started: 2026-07-07T04:36:17Z
updated: 2026-07-07T04:36:17Z
---

## Current Test

number: 1
name: Live OAuth round-trip for all four providers (GitHub, Google, Apple, Mastodon)
expected: |
  Complete a real browser sign-in round-trip for GitHub, Google, Apple, and Mastodon against
  live provider apps (real client credentials + registered callback URLs). Each provider
  redirects to its authorize endpoint, returns to the OVID callback, and mints a session/JWT
  for the resolved user; the Apple exchange succeeds with the per-exchange ES256 client
  secret; Mastodon dynamically registers on a real instance.
awaiting: user response

## Tests

### 1. Live OAuth round-trip for all four providers (GitHub, Google, Apple, Mastodon)
expected: Complete a real browser sign-in round-trip for GitHub, Google, Apple, and Mastodon against live provider apps (real client credentials + registered callback URLs). Each provider redirects to its authorize endpoint, returns to the OVID callback, and mints a session/JWT for the resolved user; the Apple exchange succeeds with the per-exchange ES256 client secret; Mastodon dynamically registers on a real instance.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

None recorded yet — pending manual execution of the live-provider round-trip.
