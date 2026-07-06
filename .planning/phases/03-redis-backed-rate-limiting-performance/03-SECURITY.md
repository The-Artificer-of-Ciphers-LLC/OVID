---
phase: 03
slug: redis-backed-rate-limiting-performance
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on (high) severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-06
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Retroactive verification of the four-plan STRIDE registers against the delivered
> Redis-backed rate-limiting implementation. `block_on: high` — only OPEN high/critical
> threats gate ship.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| gunicorn worker → rate-limit store | Each worker's limit check crosses into shared (Redis) or per-worker (memory) counter state; correctness of the abuse-prevention control depends on which | Rate-limit counter reads/writes (ephemeral, non-secret) |
| deploy config (env) → API bootstrap | `REDIS_URL` / `OVID_WORKERS` are operator-supplied; a misconfiguration silently weakens or disables the control | Operator env vars |
| pip index → API/loadtest image | New `redis` / `locust` wheels enter the build | Third-party packages |
| authenticated client → write routes | `user:{id}`-keyed POST traffic crosses into disc-identity mutation; abusable by volume even when each request is individually valid | Authenticated disc submissions |
| write route decorator → business handler | The volumetric ceiling must reject before the handler runs; the confirmation cooldown gates deeper inside | Request-rate counters vs. verify-edit counts |
| container network → redis | The rate-limit store holds ephemeral counters; if reachable from outside the compose network it becomes tamper/DoS surface | Counter state |
| CI runner → ephemeral postgres/redis services | Load-test services must be reachable by the job but never by untrusted networks; carry no real secrets or production data | Synthetic test data, ephemeral JWT |
| load harness → API auth | The submit task needs an authenticated token; leaking a real/long-lived credential into the harness or logs would be a disclosure | Runtime-minted CI JWT |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | Tampering / DoS bypass | multi-worker `memory://` counters (the pre-existing defect) | high | mitigate | Shared `RedisStorage` when `REDIS_URL` set + D-06 fail-fast import guard | closed |
| T-03-02 | Denial of Service | Redis as new availability single-point during an outage | medium | mitigate | Bounded per-worker `FALLBACK_LIMIT` with native slowapi in-memory fallback; fail-open on read path | closed |
| T-03-SC | Tampering (supply chain) | pip install of `redis` client | high | mitigate | Package Legitimacy Audit (RESEARCH: verdict OK, first-party) + pinned `redis>=5,<8` | closed |
| T-03-03 | Denial of Service / spam | write routes flooded with novel (non-confirmation) fingerprints escaping the Phase-2 cooldown | high | mitigate | Stacked `AUTH_WRITE_LIMIT` volumetric ceiling keyed `user:{id}` on all three write routes | closed |
| T-03-04 | Tampering (control weakening) | double-counting / accidental migration of the Phase-2 cooldown onto the general limiter | medium | mitigate | D-10 seam kept explicit; `anti_sybil` stays Postgres-backed; per-limit storage namespace | closed |
| T-03-05 | Information Disclosure / Tampering | redis service exposed on an untrusted network | medium | mitigate | Internal-only service, NO published host port; ephemeral (no persistence) | closed |
| T-03-06 | Denial of Service (config bypass) | multi-worker deploy shipped without `REDIS_URL` | high | mitigate | Compose ships `OVID_WORKERS=4` + `REDIS_URL` together from one source; D-06 boot guard | closed |
| T-03-07 | Information Disclosure | secrets committed via `.env.example` | low | accept | `.env.example` carries placeholders only; real `.env` git-ignored | closed |
| T-03-08 | Information Disclosure | load-test/seed tooling shipping secrets or opening DB/Redis to untrusted networks in CI | medium | mitigate | GH Actions `services` runner-bound; JWT minted at runtime for a seeded test user; synthetic seed rows | closed |
| T-03-09 | Tampering (supply chain) | pip install of `locust` in the load-test job | medium | mitigate | Package Legitimacy Audit (RESEARCH: verdict OK) + pinned `locust>=2.44,<3.0` in isolated file | closed |
| T-03-10 | Denial of Service (self-inflicted) | submit task tripping the Plan-02 write cap and reporting false failures | low | accept | Harness marks write-cap 429 as a non-failure (`catch_response`); benign measurement artifact | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above `high` count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Verification Evidence (ASVS L1 — mitigation present at cited location)

| Threat ID | Severity | Disposition | Evidence (file:line) |
|-----------|----------|-------------|----------------------|
| T-03-01 | high | mitigate | `api/app/rate_limit.py:96` (`REDIS_URL` read once at import), `:124-131` (`storage_uri=REDIS_URL or "memory://"` → shared RedisStorage when set), `:106-120` (D-06 multi-worker fail-fast `RuntimeError`) |
| T-03-02 | medium | mitigate | `api/app/rate_limit.py:49` (`FALLBACK_LIMIT="60/minute"`), `:128-130` (`swallow_errors`/`in_memory_fallback_enabled`/`in_memory_fallback` gated on `bool(REDIS_URL)`); fallback proven by `tests/test_rate_limit_fallback.py` (injected `ConnectionError`) |
| T-03-SC | high | mitigate | `api/requirements.txt:12` (`redis>=5,<8`, upper bound required by `limits`); legitimacy verdict OK in `03-RESEARCH.md` |
| T-03-03 | high | mitigate | `api/app/routes/disc.py:811` (`submit_disc`), `:720` (`register_disc`) `@limiter.limit(AUTH_WRITE_LIMIT, methods=["POST"])`; `:610` (`resolve_dispute_endpoint`) `@limiter.shared_limit(AUTH_WRITE_LIMIT, scope="disc_write:resolve")` — all three stacked above `_dynamic_limit`; import at `:30` |
| T-03-04 | medium | mitigate | `api/app/routes/disc.py:327` (D-10 seam doc note); `api/app/anti_sybil.py` untouched in Phase 03 (last commit `d22e77b`, a Phase-02 fix) — cooldown stays Postgres-backed |
| T-03-05 | medium | mitigate | `docker-compose.prod.yml:30-40` (redis service, no `ports:` key → internal-only, `--save "" --appendonly no`); `docker-compose.test.yml:28-38` likewise |
| T-03-06 | high | mitigate | `docker-compose.prod.yml:54,64-65` and `docker-compose.test.yml:52,61-62` (`OVID_WORKERS` drives both `-w` and the env var; `REDIS_URL` set alongside); base `docker-compose.yml:35` single uvicorn worker, no redis; guard at `rate_limit.py:113-120` |
| T-03-07 | low | accept | `.env.example:38` (`REDIS_URL=redis://redis:6379/0` commented placeholder, internal non-secret); `.gitignore:12-14` (`.env` + `.env.*` ignored, `!.env.example` tracked); real secrets carry `change_me...` placeholders — logged in Accepted Risks below |
| T-03-08 | medium | mitigate | `.github/workflows/loadtest.yml:50-72` (postgres+redis `services`, runner-bound), `:95-128` (JWT minted at runtime for seeded `loadtester`, written to `GITHUB_ENV`, never committed), `:35` (synthetic CI-only `OVID_SECRET_KEY`); `api/scripts/seed.py:49` (`bulk_seed` inserts synthetic `dvd1-seed-{i}` rows) |
| T-03-09 | medium | mitigate | `loadtest/requirements.txt:8` (`locust>=2.44,<3.0`, isolated from `api/requirements.txt`); legitimacy verdict OK in `03-RESEARCH.md` |
| T-03-10 | low | accept | `loadtest/locustfile.py:158-161` (`catch_response=True`; 429 marked success, excluded from `fail_ratio`); p95/error gate at `:171-203` — logged in Accepted Risks below |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-07 | `.env.example` carries placeholders only — `REDIS_URL=redis://redis:6379/0` is a non-secret internal compose address; real-secret keys hold `change_me...` sentinels. Real `.env` is git-ignored (`.gitignore:12-14`, `!.env.example` re-includes the template). Low severity; standard repo convention. | gsd-security-auditor (planner disposition, Plan 03) | 2026-07-06 |
| AR-03-02 | T-03-10 | Under sustained load a single shared submit token can trip the Plan-02 20/min write cap; those 429s are an expected throttle, not a service failure. The harness marks write-path 429 as success via `catch_response` and uses novel unique fingerprints, so throttles never inflate `fail_ratio`. A benign measurement artifact confined to the out-of-band load test, not a production risk. | gsd-security-auditor (planner disposition, Plan 04) | 2026-07-06 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags (new attack surface without a threat mapping)

None. The only SUMMARY threat-surface note is in `03-04-SUMMARY.md` ("## Threat Surface"), which explicitly maps the CI-only synthetic `OVID_SECRET_KEY`, the `locust` install, and write-cap 429 handling to existing threats T-03-08 / T-03-09 / T-03-10 respectively. No net-new, unmapped surface was declared.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-06 | 11 | 11 | 0 | gsd-security-auditor |

Notes:
- ASVS L1 verification: each declared mitigation confirmed PRESENT at its cited file:line. Implementation files were not modified.
- All 4 high-severity threats (T-03-01, T-03-SC, T-03-03, T-03-06) are CLOSED → `threats_open: 0` under `block_on: high`.
- Corroborating context (not the basis of closure): phase passed deep code review `03-REVIEW.md` (CR-01/WR-01..WR-04 resolved) and an INFRA-03 load test (p95 270ms, 0 failures on the honest Redis-backed `gunicorn -w 4` stack).

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-06
