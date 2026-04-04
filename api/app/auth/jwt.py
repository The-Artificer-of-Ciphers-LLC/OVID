"""JWT token creation and validation for OVID auth.

Access tokens: 1-hour expiry, type=access.
Refresh tokens: 30-day expiry, type=refresh, blacklistable via Redis.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.auth.config import SECRET_KEY
from app.redis import get_redis

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_ISSUER = "ovid"

# Refresh token blacklist TTL matches refresh token lifetime (30 days).
_REFRESH_TTL_DAYS = 30
_REFRESH_BLACKLIST_TTL = _REFRESH_TTL_DAYS * 86400


# ---------------------------------------------------------------------------
# Access tokens (1-hour)
# ---------------------------------------------------------------------------

def create_access_token(user_id: uuid.UUID) -> str:
    """Create a signed JWT access token for the given user.

    Payload includes sub, exp (1 hour), iss, iat, jti, and type=access.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(hours=1),
        "iss": _ISSUER,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Raises:
        jwt.ExpiredSignatureError: token has expired
        jwt.InvalidTokenError: token is malformed, wrong signature, etc.
    """
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
    )


# ---------------------------------------------------------------------------
# Refresh tokens (30-day)
# ---------------------------------------------------------------------------

def create_refresh_token(user_id: uuid.UUID) -> str:
    """Create a signed JWT refresh token for the given user.

    Payload includes sub, exp (30 days), iss, iat, jti, and type=refresh.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(days=_REFRESH_TTL_DAYS),
        "iss": _ISSUER,
        "iat": now,
        "jti": str(uuid.uuid4()),
        "type": "refresh",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=_ALGORITHM)


def decode_refresh_token(token: str) -> dict:
    """Decode and validate a JWT refresh token.

    Raises:
        jwt.InvalidTokenError: if token is invalid or type is not 'refresh'.
    """
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
    )
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Token type is not 'refresh'")
    return payload


# ---------------------------------------------------------------------------
# Refresh token blacklist (Redis-backed)
# ---------------------------------------------------------------------------

def blacklist_refresh_token(token: str) -> bool:
    """Blacklist a refresh token by its jti claim.

    Uses Redis SETNX with TTL matching refresh token lifetime.
    Returns True if blacklisted successfully.  If Redis is unavailable,
    logs a warning and returns False (graceful degradation per D-17).
    """
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[_ALGORITHM], issuer=_ISSUER,
        )
    except jwt.InvalidTokenError:
        return False

    jti = payload.get("jti")
    if not jti:
        return False

    redis = get_redis()
    if not redis:
        logger.warning("refresh_blacklist_unavailable jti=%s reason=redis_down", jti)
        return False

    key = f"refresh_blacklist:{jti}"
    result = redis.setnx(key, "1")
    if result:
        redis.expire(key, _REFRESH_BLACKLIST_TTL)
    return bool(result)


def is_refresh_token_blacklisted(jti: str) -> bool:
    """Check if a refresh token jti is blacklisted.

    Returns False if Redis is unavailable (permit -- per D-17 graceful degradation).
    """
    redis = get_redis()
    if not redis:
        return False
    return bool(redis.get(f"refresh_blacklist:{jti}"))
