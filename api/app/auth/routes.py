"""Auth routes — GitHub OAuth login/callback and /v1/auth/me."""

import logging
import os

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token
from app.auth.users import user_upsert
from app.deps import get_db
from app.models import User

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/v1/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# OAuth client setup (authlib Starlette integration)
# ---------------------------------------------------------------------------
oauth = OAuth()

_GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
_OVID_API_URL = os.environ.get("OVID_API_URL", "http://localhost:8000")

if _GITHUB_CLIENT_ID:
    oauth.register(
        name="github",
        client_id=_GITHUB_CLIENT_ID,
        client_secret=_GITHUB_CLIENT_SECRET,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email read:user"},
    )


# ---------------------------------------------------------------------------
# GitHub OAuth
# ---------------------------------------------------------------------------
@auth_router.get("/github/login")
async def github_login(request: Request):
    """Redirect to GitHub authorization page."""
    if not _GITHUB_CLIENT_ID:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    redirect_uri = f"{_OVID_API_URL}/v1/auth/github/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


@auth_router.get("/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    """Exchange GitHub auth code for token, upsert user, return JWT."""
    if not _GITHUB_CLIENT_ID:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    # Exchange code for access token
    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("auth_failed provider=github reason=oauth_error detail=%s", str(e))
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": str(e)})
    except Exception as e:
        logger.warning("auth_failed provider=github reason=token_exchange detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "gateway_timeout", "reason": "Token exchange failed"})

    if not token or "access_token" not in token:
        logger.warning("auth_failed provider=github reason=no_access_token")
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No access token received"})

    # Fetch user profile from GitHub API
    try:
        resp = await oauth.github.get("user", token=token)
        if resp.status_code != 200:
            logger.warning("auth_failed provider=github reason=api_error status=%d", resp.status_code)
            raise HTTPException(
                status_code=401 if resp.status_code == 401 else 502,
                detail={"error": "provider_error", "reason": f"GitHub API returned {resp.status_code}"},
            )
        github_user = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("auth_failed provider=github reason=api_fetch detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "provider_error", "reason": "Failed to fetch user profile"})

    github_id = github_user.get("id")
    if not github_id:
        logger.warning("auth_failed provider=github reason=malformed_response")
        raise HTTPException(status_code=401, detail={"error": "provider_error", "reason": "Malformed GitHub response"})

    # Upsert user
    user = user_upsert(
        db,
        provider="github",
        provider_id=str(github_id),
        email=github_user.get("email"),  # may be None if no public email
        display_name=github_user.get("name") or github_user.get("login"),
    )

    jwt_token = create_access_token(user.id)

    return {
        "token": jwt_token,
        "user": {
            "id": str(user.id),
            "username": user.username,
            "display_name": user.display_name,
        },
    }


# ---------------------------------------------------------------------------
# /v1/auth/me — current user info
# ---------------------------------------------------------------------------
@auth_router.get("/me")
def auth_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "email_verified": current_user.email_verified,
    }
