"""Rate limiting configuration — slowapi with auth-aware key function.

Backend selection is env-driven (INFRA-01). When ``REDIS_URL`` is set the
limiter uses a shared ``RedisStorage`` so counters are correct across gunicorn
workers; when it is unset the limiter keeps the historical single-worker
``memory://`` default. During a Redis outage the limiter degrades to a
self-healing in-memory fallback with a bounded per-key rate (``FALLBACK_LIMIT``
per worker — the bound is on the allowed rate per key, not on how many keys
are tracked) instead of failing closed on the read-heavy ARM lookup path
(INFRA-02, D-01/D-02/D-03).
"""

import logging
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.auth.jwt import decode_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit thresholds (R025)
# ---------------------------------------------------------------------------
# Env-configurable with identical defaults (CR-01) so the load-test harness can
# raise the read tiers via OVID_UNAUTH_LIMIT/OVID_AUTH_LIMIT and measure real
# handler p95 instead of limiter 429s — zero behavior change when unset.
UNAUTH_LIMIT = os.environ.get("OVID_UNAUTH_LIMIT", "100/minute")
AUTH_LIMIT = os.environ.get("OVID_AUTH_LIMIT", "500/minute")

# Tunable launch-safe defaults (never magic numbers) --------------------------
# Auth write-path throttle consumed by Plan 02 (D-08). Kept here so the write
# limit lives beside the read tiers and shares the same env-driven backend.
# Outage note (WR-01, D-04): during a Redis outage slowapi's in-memory
# fallback replaces ALL per-route limits — including this one — with
# FALLBACK_LIMIT below, so the effective write ceiling relaxes from
# 20/minute per account to FALLBACK_LIMIT (60/minute) PER WORKER for the
# outage's duration. This is a deliberate fail-open-on-writes choice,
# consistent with the read-path outage behavior; a fail-closed, per-route-
# type split that keeps writes tighter even during an outage is deferred
# (D-04).
AUTH_WRITE_LIMIT = "20/minute;300/hour"
# Single GLOBAL per-worker cap applied to EVERY route while Redis is unreachable
# (slowapi replaces all per-route limits with the fallback during an outage), so
# it is deliberately conservative enough to still protect the read path (D-01).
FALLBACK_LIMIT = "60/minute"


def _auth_aware_key(request: Request) -> str:
    """Extract a rate-limit key that distinguishes authenticated users from IPs.

    Authenticated requests (valid JWT in Authorization header) are keyed
    as ``user:{user_id}``, giving each user an independent counter.
    Unauthenticated requests fall back to the client IP address.
    """
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            # Invalid/expired token — fall through to IP-based limiting
            pass

    # Fallback: client IP
    return request.client.host if request.client else "unknown"


def _dynamic_limit(key: str) -> str:
    """Return the rate limit string based on the caller's key.

    Authenticated keys start with ``user:``, getting 500/min.
    IP-based keys (unauthenticated) get 100/min.

    This is passed to ``@limiter.limit()`` as a callable — slowapi
    invokes it with the result of the key function for each request.
    """
    if key.startswith("user:"):
        return AUTH_LIMIT
    return UNAUTH_LIMIT


# ---------------------------------------------------------------------------
# Backend selection (INFRA-01) — read REDIS_URL once at import time
# ---------------------------------------------------------------------------
# REDIS_URL set   → shared RedisStorage (cross-worker-correct counters) with a
#                   bounded in-memory fallback during an outage.
# REDIS_URL unset → historical single-worker `memory://` default preserved; the
#                   outage-fallback flags stay off so behavior is unchanged.
REDIS_URL = os.environ.get("REDIS_URL")

# ---------------------------------------------------------------------------
# Fail-fast multi-worker guard (D-06)
# ---------------------------------------------------------------------------
# On `memory://` each gunicorn worker keeps an independent counter, so running
# more than one worker silently inflates every rate limit up to Nx. Refuse to
# boot in that configuration — mirror auth/config._require_env's import-time
# fail-fast. Read an explicit worker-count env var (OVID_WORKERS, falling back
# to gunicorn's own WEB_CONCURRENCY); never scrape gunicorn argv.
_raw_workers = os.environ.get("OVID_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "1"
try:
    _worker_count = int(_raw_workers)
except ValueError:
    raise RuntimeError(
        f"OVID_WORKERS/WEB_CONCURRENCY must be an integer, got {_raw_workers!r}."
    )
if _worker_count > 1 and not REDIS_URL:
    raise RuntimeError(
        f"Rate limiting is misconfigured: OVID_WORKERS={_worker_count} (>1) but "
        f"REDIS_URL is not set. On memory:// storage each worker keeps its own "
        f"counter, so the effective rate limit inflates up to {_worker_count}x the "
        f"nominal value. Set REDIS_URL to a shared Redis instance, or run a single "
        f"worker (OVID_WORKERS=1)."
    )

# Default limit is 100/min per-key.  Routes that need auth-aware
# tiering apply @limiter.limit(_dynamic_limit) explicitly.
limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri=REDIS_URL or "memory://",
    swallow_errors=bool(REDIS_URL),
    in_memory_fallback_enabled=bool(REDIS_URL),
    in_memory_fallback=[FALLBACK_LIMIT] if REDIS_URL else [],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return a JSON 429 response with structured error body.

    The Retry-After header is set by slowapi automatically; we also
    include it in the response body for programmatic consumers.
    """
    # exc.detail contains the limit string, e.g. "100 per 1 minute"
    retry_after = exc.headers.get("Retry-After", "60") if exc.headers else "60"

    logger.warning(
        "rate_limit_exceeded key=%s limit=%s path=%s",
        _auth_aware_key(request),
        exc.detail,
        request.url.path,
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limited",
            "message": f"Rate limit exceeded: {exc.detail}",
            "retry_after": int(retry_after),
        },
        headers={"Retry-After": str(retry_after)},
    )
