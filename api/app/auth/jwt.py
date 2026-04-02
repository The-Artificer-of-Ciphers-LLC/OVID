"""JWT token creation and validation for OVID auth."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.auth.config import JWT_EXPIRY_DAYS, SECRET_KEY

_ALGORITHM = "HS256"
_ISSUER = "ovid"


def create_access_token(user_id: uuid.UUID) -> str:
    """Create a signed JWT for the given user.

    Payload: {"sub": "<user-uuid>", "exp": <utc+30d>, "iss": "ovid"}
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(days=JWT_EXPIRY_DAYS),
        "iss": _ISSUER,
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT.

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
