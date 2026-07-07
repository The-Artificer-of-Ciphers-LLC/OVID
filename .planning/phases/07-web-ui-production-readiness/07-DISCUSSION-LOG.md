# Phase 7: Web UI Production Readiness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-07
**Phase:** 07-web-ui-production-readiness
**Areas discussed:** Re-integrated re-review depth, Design system vs bespoke, Account-settings merge UX, Deployment scope (P7 vs P8)
**Mode:** advisor (standard calibration tier; 4 parallel research agents)

---

## Re-integrated Feature Re-review Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Risk-based targeted | Fit-check auth/alias/anti-echo seams, migration 008/009 ordering+idempotency, dead-code sweep, UX parity; escalate only if it surfaces something | ✓ |
| Full audit + rework | Line-by-line review of both features, re-derive design intent | |
| Accept as-is | Trust green suites, no extra review | |

**User's choice:** Risk-based targeted review
**Notes:** Proportionate to a 2-feature scope; tests passing proves original behavior, not architectural fit on the new baseline. Escalate to fuller audit only on a real security/migration finding.

---

## Design System vs Bespoke Tailwind

| Option | Description | Selected |
|--------|-------------|----------|
| Tailwind @theme tokens + primitives | CSS-variable tokens + shared Button/Input/Field, keep bespoke components, zero new deps | ✓ |
| Adopt shadcn/ui (Radix) | Vendored Radix components with tested ARIA/focus; new deps to maintain | |
| Polish bespoke in place | Shared cn() convention + a11y pass, no shared token/primitive layer | |

**User's choice:** Tailwind v4 `@theme` tokens + shared primitives
**Notes:** Honors "no gratuitous dependencies" / "don't re-platform." Production a11y floor (focus-visible, WCAG AA in both themes, keyboard operability, aria/label + aria-live) applies regardless (captured as D-03).

---

## Account-Settings Merge UX (WEBUI-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Middle: explanatory 409 + backend redirect fix | Backend redirects merge-offer 409 to the app; enumeration-safe banner + direct re-auth link | ✓ |
| Full guided pending-merge flow | Frontend orchestrates the whole re-auth round-trip (TTL/mismatch/multi-provider) | |
| Minimal add/remove only | Providers only; still needs the backend fix or users dead-end on JSON | |

**User's choice:** Middle depth
**Notes:** Research surfaced that `finalize_auth` today returns a raw 409 JSONResponse with no redirect — a genuine dead-end. The small backend redirect fix is required (D-04); full automation deferred to v1.0.

---

## Deployment Scope (Phase 7 vs Phase 8)

| Option | Description | Selected |
|--------|-------------|----------|
| Staging in P7, promote in P8 | Deploy to staging for real TLS/DNS/env verification; P8 promotes to public apex + seeding | ✓ |
| Production-ready only (cutover in P8) | Build/runbook in P7, cutover entirely in P8 | |
| Full live cutover in P7 | Stand up oviddb.org now (exposes near-empty DB) | |

**User's choice:** Staging deploy in P7, promote in P8
**Notes:** `docker-compose.prod.yml` already declares the `web` service at oviddb.org:3100 via redshirt, so infra cost is low. Avoids a near-empty catalog going public before Phase 8 seeds it. Roadmap success-criterion 1 wording should be updated (staging vs apex).

---

## Claude's Discretion

- Exact staging URL/subdomain, primitive component API shapes, and design-token naming — left to research/planning within the locked decisions.

## Deferred Ideas

- Full automated pending-merge re-auth flow → post-launch / v1.0.
- shadcn/ui adoption → only if complex interactive widgets emerge.
- Public oviddb.org apex cutover, domain redirects, DB seeding → Phase 8 (Launch Readiness).
