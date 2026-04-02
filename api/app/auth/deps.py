"""FastAPI dependency for extracting the current authenticated user."""

import logging
import uuid

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.deps import get_db
from app.models import User

logger = logging.getLogger(__name__)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Extract Bearer token, decode JWT, and return the User.

    Raises HTTPException(401) with a JSON body containing:
        {"detail": {"error": "missing_token" | "invalid_token" | "expired_token"}}
    """
    if not authorization:
        raise HTTPException(status_code=401, detail={"error": "missing_token"})

    # Expect "Bearer <token>"
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail={"error": "missing_token"})

    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail={"error": "missing_token"})

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail={"error": "expired_token"})
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    try:
        user_id = uuid.UUID(sub)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        logger.warning("auth_user_not_found sub=%s", sub)
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})

    return user
