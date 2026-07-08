---
status: complete
quick_id: 260707-u7v
date: 2026-07-08
---

# Quick Task Summary: staging-deploy-doc-sync

Documentation-only sync of `docs/deployment.md`'s Staging section to match the live, already-verified
D-06 staging deploy. No infrastructure was touched — this task only corrected the doc to reality.

## Changes made

1. **API host rename** — `api.staging.oviddb.org` → `staging-api.oviddb.org` everywhere in the
   Staging section (header, host/port table, prerequisites, env-wiring, compose recipe). Added the
   rationale: Cloudflare's free Universal SSL edge cert covers `oviddb.org` + `*.oviddb.org`, and a
   wildcard matches only one label, so the two-level `api.staging.oviddb.org` would not be covered,
   while the single-level `staging-api.oviddb.org` is.
2. **Ports/slot corrected** — staging reuses the retired `test` (x200) slot on holodeck, not a new
   x300 bracket. Web `holodeck:3200` → container `:3000`; API `holodeck:8200` → container `:8000`.
3. **TLS/cert instructions corrected** — no SAN cert or new origin cert needed; the origin reuses
   the existing `oviddb.org` Let's Encrypt cert under Cloudflare **Full** (not strict) mode. Added
   an explicit requirement callout for Full mode, updated the nginx vhost description to the new
   `server_name`/port targets, and added a note that `ssl_stapling`/`ssl_stapling_verify` were
   removed from redshirt's nginx config (Let's Encrypt stopped publishing OCSP responder URLs in
   2025, making stapling a silent no-op that warned on every reload).
4. **DNS corrected** — proxied CNAME records (`staging.oviddb.org`, `staging-api.oviddb.org` →
   `oviddb.org`, both Cloudflare-proxied) replace the prior "add A records to `64.98.89.233`"
   instruction; noted the CNAME-to-proxied-apex approach is equivalent because Cloudflare flattens
   a proxied CNAME to the same proxied edge.
5. **Compose recipe updated** — `docker-compose.staging.yml` example and build/run commands: ports
   `3300`→`3200`, `8300`→`8200`; web build arg `NEXT_PUBLIC_API_URL` → `https://staging-api.oviddb.org`.
   Added a note that the overlay reuses the retired test (x200) slot.
6. **ssl_stapling note** — folded into the TLS/routing bullet above (item 3).

## Commit

- `bdd705d` — `docs(deployment): sync staging section with live D-06 deploy — staging-api host, x200 slot, CF-proxy TLS`

## Verification

Grepped the Staging section (`## Staging (...)` through the "Human sign-off" subsection) after
editing: zero operative references to `3300` or `8300` remain, and zero operative references to
`api.staging.oviddb.org` remain — the only two remaining occurrences of that string are clearly-
labeled rationale prose explaining why the two-level host was rejected in favor of the single-level
`staging-api.oviddb.org`. All new references (`staging-api.oviddb.org`, `3200`, `8200`) are present
in the header, host/port table, prerequisites, env-wiring, and compose recipe as required.

## Scope note

Only `docs/deployment.md`'s Staging section was touched, per the task's explicit scope. The
top-level "Environments" overview table (lines 7-20) and the separate "Test Stack" section still
reference the old test/staging port assignments and are out of scope for this quick task — they
were not part of the "Staging section" this task was scoped to, and were left untouched.
