# Phase 1: Security Hardening & Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-04
**Phase:** 01-Security Hardening & Infrastructure
**Areas discussed:** Auth token delivery, Mastodon security depth, Redis integration approach, Startup validation strictness

---

## Auth Token Delivery

### OAuth callback token delivery
| Option | Description | Selected |
|--------|-------------|----------|
| Auth code exchange | Callback sets short-lived auth code in session, redirects to web. Web exchanges code for JWT via POST. Matches OAuth2 best practice. | ✓ |
| HttpOnly cookie | API sets JWT as httpOnly secure cookie on callback. Simplest, but breaks CLI/mobile. | |
| Fragment-based redirect | Token in URL fragment (#token=JWT). Not sent to server logs, but still in browser history. | |

**User's choice:** Auth code exchange
**Notes:** None

### Token storage
| Option | Description | Selected |
|--------|-------------|----------|
| localStorage (current) | Persists across tabs and page refreshes. Vulnerable to XSS but acceptable with CSP. | |
| HttpOnly cookie + localStorage hybrid | API sets httpOnly cookie for SSR; JS reads companion flag cookie for client-side auth state. | ✓ |
| You decide | Keep localStorage since it's already working. | |

**User's choice:** HttpOnly cookie + localStorage hybrid

### Auth code TTL
| Option | Description | Selected |
|--------|-------------|----------|
| Single-use, 60-second TTL | Standard OAuth2 behavior. Code deleted after first exchange. | ✓ |
| Single-use, 5-minute TTL | More forgiving for slow redirects. Still single-use. | |
| You decide | | |

**User's choice:** Single-use, 60-second TTL

### CLI/ARM auth
| Option | Description | Selected |
|--------|-------------|----------|
| Device authorization flow | CLI shows URL + code, user visits in browser, approves, CLI polls for token. RFC 8628. | ✓ |
| API key / personal access token | User generates long-lived API key from account settings. Simpler. | |
| You decide | | |

**User's choice:** Device authorization flow

### Token lifetime
| Option | Description | Selected |
|--------|-------------|----------|
| Keep current (1h access, 30d refresh) | Already defined in project constraints. | ✓ |
| Shorten to 15min access, 7d refresh | Tighter security. More frequent refresh. | |
| You decide | | |

**User's choice:** Keep current

### Session middleware
| Option | Description | Selected |
|--------|-------------|----------|
| Separate session secret from JWT secret | Dedicated SESSION_SECRET_KEY env var. Cleaner separation. | ✓ |
| Keep shared secret | One key for both. Simpler config. | |
| You decide | | |

**User's choice:** Separate session secret from JWT secret

### Token revocation
| Option | Description | Selected |
|--------|-------------|----------|
| Refresh token rotation + blacklist | Old refresh token blacklisted on use. Redis-backed. | ✓ |
| Full token blacklist | Check every access token against blacklist. Higher overhead. | |
| Rely on short TTL only | No revocation mechanism. Simplest. | |

**User's choice:** Refresh token rotation + blacklist

### Auth endpoint rate limits
| Option | Description | Selected |
|--------|-------------|----------|
| 5 login + 10 callback per IP/min | Tight enough for brute force protection. | ✓ |
| 10 login + 20 callback per IP/min | More lenient for shared IPs. | |
| You decide | | |

**User's choice:** 5 login + 10 callback per IP/min

### CORS configuration
| Option | Description | Selected |
|--------|-------------|----------|
| Environment-driven CORS origins | ALLOWED_ORIGINS env var. Cookie domain from COOKIE_DOMAIN. | ✓ |
| Wildcard in dev, strict in prod | Dev allows all origins. Prod locks to oviddb.org. | |
| You decide | | |

**User's choice:** Environment-driven CORS origins

---

## Mastodon Security Depth

### Domain validation thoroughness
| Option | Description | Selected |
|--------|-------------|----------|
| Harden existing check + blocklist | Pin resolved IP, add blocklist, rate limit new domain registration (3/hour per IP). | ✓ |
| Full SSRF prevention | DNS rebinding, HTTPS-only, certificate pinning, DNS-over-HTTPS. Maximum security. | |
| Minimal + rate limit only | Keep existing check, add rate limit. Fix known bugs only. | |

**User's choice:** Harden existing check + blocklist

### OAuth client cache expiry
| Option | Description | Selected |
|--------|-------------|----------|
| TTL + lazy cleanup | expires_at column (30 days). Re-register on expired lookup. No scheduler. | ✓ |
| TTL + scheduled cleanup | Same expiry + APScheduler hourly cleanup. | |
| You decide | | |

**User's choice:** TTL + lazy cleanup

---

## Redis Integration Approach

### Redis requirement level
| Option | Description | Selected |
|--------|-------------|----------|
| Required in prod, optional in dev | REDIS_URL env var. Fallback to in-memory in dev with warning. Docker always includes it. | ✓ |
| Required everywhere | All environments must have Redis. Simpler code. Higher dev friction. | |
| Always optional | In-memory fallback everywhere. Redis only improves accuracy. | |

**User's choice:** Required in prod, optional in dev

### Redis failure behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Permit all requests | Rate limiting degrades to no-limit. Token blacklist skipped. Log warning. | ✓ |
| Reject write requests only | Reads work. Writes return 503. | |
| You decide | | |

**User's choice:** Permit all requests

### Redis distribution
| Option | Description | Selected |
|--------|-------------|----------|
| Redis 7 Alpine | Standard. Smallest image. Widely supported. | |
| Valkey 8 Alpine | Open-source Redis fork by Linux Foundation. API-compatible. Future-proofed. | ✓ |

**User's choice:** Valkey 8 Alpine

### Connection pooling
| Option | Description | Selected |
|--------|-------------|----------|
| redis-py connection pool (max 10) | Built-in ConnectionPool. Standard approach. | ✓ |
| Single connection per request | Simpler but higher latency. | |
| You decide | | |

**User's choice:** redis-py connection pool

### Redis scope
| Option | Description | Selected |
|--------|-------------|----------|
| Rate limiting + token blacklist only | Minimal scope for Phase 1. | |
| Also move session storage to Redis | Replace cookie-based sessions with Redis-backed. Enables server-side invalidation. | ✓ |

**User's choice:** Also move session storage to Redis

---

## Startup Validation Strictness

### Validation strictness
| Option | Description | Selected |
|--------|-------------|----------|
| Fail fast on all critical config | App refuses to start on weak JWT secret, invalid Apple key, missing DB. | ✓ |
| Fail on core, warn on optional | Fail if JWT/DB invalid. Warn and disable if Apple key missing. | |
| Warn only, never crash | Log warnings, always start. Broken features return 501. | |

**User's choice:** Fail fast on all critical config

### What counts as critical
| Option | Description | Selected |
|--------|-------------|----------|
| Core only: JWT + DB + Redis (prod) | Only essential services. Missing providers don't appear in login UI. | |
| Core + all configured providers | If APPLE_PRIVATE_KEY is set but invalid, fail. If unset, skip. | |
| Everything configured in .env | Validate every set env var. Strictest. Catches typos. | ✓ |

**User's choice:** Everything configured in .env

---

## Claude's Discretion

- DNS rebinding prevention implementation details
- Mastodon instance blocklist contents
- Redis connection retry backoff strategy
- Alembic migration ordering
- Test fixture design for OAuth mocking

## Deferred Ideas

- Full access token blacklist — add if 1-hour TTL proves insufficient
- Audit trail for auth events — future phase
- Circuit breaker for Mastodon instance health — nice-to-have, not P0
