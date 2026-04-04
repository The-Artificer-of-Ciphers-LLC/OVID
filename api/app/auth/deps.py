"""FastAPI dependency for extracting the current authenticated user."""

import logging
import uuid

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.jwt import decode_access_token
from app.deps import get_db
from app.models import User

logger = logging.getLogger(__name__)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Extract token from cookie or Authorization header, decode JWT, return User.

    Cookie auth (ovid_token) is checked first for web clients.
    Falls back to Authorization: Bearer header for CLI/API clients.

    Raises HTTPException(401) with a JSON body containing:
        {"detail": {"error": "missing_token" | "invalid_token" | "expired_token"}}
    """
    # Check ovid_token cookie first (web auth via HttpOnly cookie)
    token = request.cookies.get("ovid_token")

    # Fall back to Authorization: Bearer header (CLI / API auth)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

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
