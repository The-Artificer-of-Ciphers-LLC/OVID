"""Auth routes — GitHub OAuth, Apple Sign-In, IndieAuth, and /v1/auth/me."""

import logging
import os
import secrets
import time

import httpx
import jwt as pyjwt
from authlib.integrations.starlette_client import OAuth, OAuthError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.indieauth import DiscoveryError, discover_endpoints, generate_pkce_pair, validate_url
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

# Apple Sign-In config (all four required for Apple to be active)
_APPLE_CLIENT_ID = os.environ.get("APPLE_CLIENT_ID", "")
_APPLE_TEAM_ID = os.environ.get("APPLE_TEAM_ID", "")
_APPLE_KEY_ID = os.environ.get("APPLE_KEY_ID", "")
_APPLE_PRIVATE_KEY = os.environ.get("APPLE_PRIVATE_KEY", "")  # PEM or base64-encoded PEM

_APPLE_CONFIGURED = bool(_APPLE_CLIENT_ID and _APPLE_TEAM_ID and _APPLE_KEY_ID and _APPLE_PRIVATE_KEY)

_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

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

if _GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=_GOOGLE_CLIENT_ID,
        client_secret=_GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
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


# ---------------------------------------------------------------------------
# Apple Sign-In helpers
# ---------------------------------------------------------------------------

def _load_apple_private_key():
    """Load Apple ES256 private key from env (PEM text or base64-encoded PEM)."""
    import base64

    raw = _APPLE_PRIVATE_KEY
    if not raw:
        return None

    # If it doesn't look like PEM, try base64 decode
    if "BEGIN" not in raw:
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            return None

    try:
        return serialization.load_pem_private_key(raw.encode("utf-8"), password=None)
    except Exception:
        return None


def generate_apple_client_secret() -> str:
    """Generate the JWT client_secret Apple requires for token exchange.

    Apple's client_secret is itself a JWT signed with ES256 using the team's
    private key, with specific claims.  Valid for up to 6 months.
    """
    private_key = _load_apple_private_key()
    if not private_key:
        raise RuntimeError("Apple private key not loaded")

    now = int(time.time())
    payload = {
        "iss": _APPLE_TEAM_ID,
        "iat": now,
        "exp": now + (86400 * 180),  # 6 months
        "aud": "https://appleid.apple.com",
        "sub": _APPLE_CLIENT_ID,
    }
    headers = {
        "kid": _APPLE_KEY_ID,
        "alg": "ES256",
    }
    return pyjwt.encode(payload, private_key, algorithm="ES256", headers=headers)


# ---------------------------------------------------------------------------
# Apple Sign-In
# ---------------------------------------------------------------------------

_APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"
_APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"


@auth_router.get("/apple/login")
async def apple_login(request: Request):
    """Redirect to Apple's OIDC authorization endpoint."""
    if not _APPLE_CONFIGURED:
        raise HTTPException(status_code=501, detail="Apple Sign-In not configured")

    redirect_uri = f"{_OVID_API_URL}/v1/auth/apple/callback"
    state = secrets.token_urlsafe(32)
    request.session["apple_state"] = state

    params = {
        "client_id": _APPLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "name email",
        "response_mode": "query",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    from starlette.responses import RedirectResponse
    return RedirectResponse(url=f"{_APPLE_AUTH_URL}?{qs}")


@auth_router.get("/apple/callback")
async def apple_callback(request: Request, db: Session = Depends(get_db)):
    """Exchange Apple auth code for tokens, decode ID token, upsert user."""
    if not _APPLE_CONFIGURED:
        raise HTTPException(status_code=501, detail="Apple Sign-In not configured")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No authorization code"})

    # Generate the JWT client_secret Apple requires
    try:
        client_secret = generate_apple_client_secret()
    except Exception as e:
        logger.error("apple_client_secret_failed detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "provider_error", "reason": "Failed to generate client secret"})

    redirect_uri = f"{_OVID_API_URL}/v1/auth/apple/callback"

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _APPLE_TOKEN_URL,
                data={
                    "client_id": _APPLE_CLIENT_ID,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                timeout=10.0,
            )
    except httpx.TimeoutException:
        logger.warning("auth_failed provider=apple reason=timeout")
        raise HTTPException(status_code=502, detail={"error": "gateway_timeout", "reason": "Apple token exchange timed out"})
    except Exception as e:
        logger.warning("auth_failed provider=apple reason=token_exchange detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "provider_error", "reason": "Token exchange failed"})

    if resp.status_code != 200:
        logger.warning("auth_failed provider=apple reason=token_error status=%d", resp.status_code)
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "Apple token exchange failed"})

    token_data = resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        logger.warning("auth_failed provider=apple reason=no_id_token")
        raise HTTPException(status_code=401, detail={"error": "provider_error", "reason": "No ID token in response"})

    # Decode the ID token verifying against Apple's JWKS
    try:
        jwks_client = pyjwt.PyJWKClient("https://appleid.apple.com/auth/keys", cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = pyjwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=_APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
            options={"verify_signature": True}
        )
    except pyjwt.PyJWKClientError as e:
        logger.warning("auth_failed provider=apple reason=jwks_error detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "provider_error", "reason": "Failed to fetch Apple JWKS"})
    except pyjwt.InvalidTokenError as e:
        logger.warning("auth_failed provider=apple reason=invalid_id_token detail=%s", str(e))
        raise HTTPException(status_code=401, detail={"error": "invalid_token", "reason": "Invalid Apple ID token"})

    apple_sub = claims.get("sub")
    if not apple_sub:
        logger.warning("auth_failed provider=apple reason=malformed_id_token")
        raise HTTPException(status_code=401, detail={"error": "invalid_token", "reason": "ID token missing sub claim"})

    apple_email = claims.get("email")

    user = user_upsert(
        db,
        provider="apple",
        provider_id=apple_sub,
        email=apple_email,
        display_name=None,  # Apple may send name only on first auth
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
# IndieAuth
# ---------------------------------------------------------------------------

@auth_router.get("/indieauth/login")
async def indieauth_login(request: Request, url: str = ""):
    """Begin IndieAuth flow: discover endpoints, redirect to authorization_endpoint."""
    if not url:
        raise HTTPException(status_code=400, detail={"error": "missing_url", "reason": "url query param required"})

    try:
        validated_url = validate_url(url, allow_localhost=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_url", "reason": str(e)})

    try:
        endpoints = await discover_endpoints(validated_url)
    except DiscoveryError as e:
        raise HTTPException(status_code=400, detail={"error": "discovery_failed", "reason": str(e)})

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()

    # Generate state
    state = secrets.token_urlsafe(32)

    # Store in session for callback
    request.session["indieauth_state"] = state
    request.session["indieauth_code_verifier"] = code_verifier
    request.session["indieauth_me"] = validated_url
    request.session["indieauth_token_endpoint"] = endpoints["token_endpoint"]

    redirect_uri = f"{_OVID_API_URL}/v1/auth/indieauth/callback"
    client_id = _OVID_API_URL

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "me": validated_url,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())

    from starlette.responses import RedirectResponse
    return RedirectResponse(url=f"{endpoints['authorization_endpoint']}?{qs}")


@auth_router.get("/indieauth/callback")
async def indieauth_callback(request: Request, db: Session = Depends(get_db)):
    """Exchange IndieAuth code for token, upsert user."""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code:
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No authorization code"})

    # Verify state
    expected_state = request.session.get("indieauth_state")
    if not expected_state or state != expected_state:
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "State mismatch"})

    code_verifier = request.session.get("indieauth_code_verifier", "")
    token_endpoint = request.session.get("indieauth_token_endpoint", "")

    if not token_endpoint:
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No token endpoint in session"})

    redirect_uri = f"{_OVID_API_URL}/v1/auth/indieauth/callback"
    client_id = _OVID_API_URL

    # Exchange code at token endpoint
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier,
                },
                timeout=10.0,
            )
    except httpx.TimeoutException:
        logger.warning("auth_failed provider=indieauth reason=timeout")
        raise HTTPException(status_code=502, detail={"error": "gateway_timeout", "reason": "Token exchange timed out"})
    except Exception as e:
        logger.warning("auth_failed provider=indieauth reason=token_exchange detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "provider_error", "reason": "Token exchange failed"})

    if resp.status_code != 200:
        logger.warning("auth_failed provider=indieauth reason=token_error status=%d body=%s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "Token exchange failed"})

    token_data = resp.json()
    me_url = token_data.get("me")
    if not me_url:
        logger.warning("auth_failed provider=indieauth reason=no_me_field")
        raise HTTPException(status_code=401, detail={"error": "provider_error", "reason": "Token response missing 'me' field"})

    # Clean up session
    for key in ("indieauth_state", "indieauth_code_verifier", "indieauth_me", "indieauth_token_endpoint"):
        request.session.pop(key, None)

    user = user_upsert(
        db,
        provider="indieauth",
        provider_id=me_url,
        email=None,  # IndieAuth doesn't provide email
        display_name=me_url,
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
# Google OAuth
# ---------------------------------------------------------------------------
@auth_router.get("/google/login")
async def google_login(request: Request):
    """Redirect to Google authorization page."""
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    redirect_uri = f"{_OVID_API_URL}/v1/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@auth_router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Exchange Google auth code for token, upsert user, return JWT."""
    if not _GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    # Exchange code for access token
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        logger.warning("auth_failed provider=google reason=oauth_error detail=%s", str(e))
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": str(e)})
    except Exception as e:
        logger.warning("auth_failed provider=google reason=token_exchange detail=%s", str(e))
        raise HTTPException(status_code=502, detail={"error": "gateway_timeout", "reason": "Token exchange failed"})

    if not token:
        logger.warning("auth_failed provider=google reason=no_token")
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No token received"})

    # Since we use OpenID Connect, userinfo is parsed automatically by authlib
    # if we have server_metadata_url.
    userinfo = token.get("userinfo")
    if not userinfo:
        logger.warning("auth_failed provider=google reason=no_userinfo")
        raise HTTPException(status_code=401, detail={"error": "auth_failed", "reason": "No userinfo received"})

    google_sub = userinfo.get("sub")
    if not google_sub:
        logger.warning("auth_failed provider=google reason=malformed_response")
        raise HTTPException(status_code=401, detail={"error": "provider_error", "reason": "Malformed Google response"})

    # Upsert user
    user = user_upsert(
        db,
        provider="google",
        provider_id=google_sub,
        email=userinfo.get("email"),
        display_name=userinfo.get("name"),
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
