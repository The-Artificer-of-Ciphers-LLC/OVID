"""OAuth 2.0 Device Authorization Grant (RFC 8628) endpoints.

Provides device authorization flow for CLI clients and ARM integration
where browser-based OAuth redirect is not available.
"""

import json
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token, create_refresh_token
from app.rate_limit import limiter
from app.redis import get_redis

device_router = APIRouter(prefix="/v1/auth/device", tags=["device-auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_user_code(length: int = 8) -> str:
    """Generate easy-to-type alphanumeric code (no ambiguous chars)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    return "".join(secrets.choice(alphabet) for _ in range(length))


# ---------------------------------------------------------------------------
# POST /v1/auth/device/authorize
# ---------------------------------------------------------------------------

@device_router.post("/authorize")
@limiter.limit("10/minute")
async def device_authorize(request: Request):
    """Start a device authorization flow.

    Returns device_code (for polling), user_code (for user to enter),
    verification_uri, expires_in, and interval.
    """
    redis = get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

    device_code = secrets.token_urlsafe(32)
    user_code = _generate_user_code()

    redis.setex(f"device:{device_code}", 900, json.dumps({
        "user_code": user_code,
        "status": "pending",
        "last_poll": 0,
    }))
    redis.setex(f"usercode:{user_code}", 900, device_code)

    web_url = os.environ.get("OVID_WEB_URL", "http://localhost:3000")
    return {
        "device_code": device_code,
        "user_code": user_code,
        "verification_uri": f"{web_url}/device",
        "expires_in": 900,
        "interval": 5,
    }


# ---------------------------------------------------------------------------
# POST /v1/auth/device/token
# ---------------------------------------------------------------------------

@device_router.post("/token")
@limiter.limit("12/minute")
async def device_token(request: Request, device_code: str = Body(..., embed=True)):
    """Poll for device authorization result.

    Returns:
        200 with access_token/refresh_token when approved.
        428 authorization_pending while waiting.
        429 slow_down if polled too frequently.
        401 expired_token if device code has expired.
    """
    redis = get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

    key = f"device:{device_code}"
    raw = redis.get(key)
    if not raw:
        raise HTTPException(status_code=401, detail={"error": "expired_token"})

    data = json.loads(raw)

    # Enforce polling interval (per Pitfall 5)
    now = time.time()
    if now - data.get("last_poll", 0) < 4.5:  # slight tolerance under 5s
        raise HTTPException(status_code=429, detail={"error": "slow_down", "interval": 5})

    data["last_poll"] = now
    ttl = redis.ttl(key) or 900
    redis.setex(key, ttl, json.dumps(data))

    if data["status"] == "pending":
        raise HTTPException(status_code=428, detail={"error": "authorization_pending"})

    if data["status"] == "denied":
        redis.delete(key)
        raise HTTPException(status_code=401, detail={"error": "access_denied"})

    # status == "approved"
    user_id = uuid.UUID(data["user_id"])
    redis.delete(key)
    return {
        "access_token": create_access_token(user_id),
        "refresh_token": create_refresh_token(user_id),
        "token_type": "Bearer",
        "expires_in": 3600,
    }


# ---------------------------------------------------------------------------
# POST /v1/auth/device/approve
# ---------------------------------------------------------------------------

@device_router.post("/approve")
@limiter.limit("10/minute")
async def device_approve(
    request: Request,
    user_code: str = Body(..., embed=True),
    user=Depends(get_current_user),
):
    """Approve a device authorization request by entering the user_code.

    Requires an authenticated user (cookie or Bearer token).
    """
    redis = get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

    uc_key = f"usercode:{user_code.upper().strip()}"
    device_code_raw = redis.get(uc_key)
    if not device_code_raw:
        raise HTTPException(status_code=404, detail={"error": "invalid_user_code"})

    device_code = device_code_raw.decode()
    dc_key = f"device:{device_code}"
    raw = redis.get(dc_key)
    if not raw:
        raise HTTPException(status_code=404, detail={"error": "expired_device_code"})

    data = json.loads(raw)
    data["status"] = "approved"
    data["user_id"] = str(user.id)
    ttl = redis.ttl(dc_key) or 900
    redis.setex(dc_key, ttl, json.dumps(data))
    redis.delete(uc_key)
    return {"approved": True}
