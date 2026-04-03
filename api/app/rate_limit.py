"""Rate limiting configuration — slowapi with auth-aware key function.

Uses in-memory storage (per-process). With gunicorn -w N, each worker
has independent counters — effective rate limit is up to Nx the nominal
value. Upgrade path: switch storage_uri to a Redis URL for shared state.
"""

import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.auth.jwt import decode_access_token

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit thresholds (R025)
# ---------------------------------------------------------------------------
UNAUTH_LIMIT = "100/minute"
AUTH_LIMIT = "500/minute"


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


# Default limit is 100/min per-key.  Routes that need auth-aware
# tiering apply @limiter.limit(_dynamic_limit) explicitly.
limiter = Limiter(
    key_func=_auth_aware_key,
    default_limits=[UNAUTH_LIMIT],
    storage_uri="memory://",
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
