"""OVID API Server — minimal bootstrap."""

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from slowapi.errors import RateLimitExceeded

from app.auth.config import SECRET_KEY
from app.auth.routes import auth_router, indieauth_router
from app.middleware import MirrorModeMiddleware, RequestIdMiddleware
from app.rate_limit import UNAUTH_LIMIT, limiter, rate_limit_exceeded_handler
from app.routes.disc import router as disc_router
from app.routes.set import router as set_router
from app.routes.sync import router as sync_router

app = FastAPI(
    title="OVID API",
    description="Open Video Disc Identification Database",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS. NOTE on middleware ordering (WR-02): Starlette's add_middleware()
# prepends to the internal user_middleware list, and build_middleware_stack()
# wraps the app by walking that list in REVERSE — so the LAST middleware
# added below becomes the OUTERMOST layer (first to see every request, last
# to see every response), not the first-added one. Given the actual
# add_middleware() call order in this file (CORSMiddleware -> SessionMiddleware
# -> RequestIdMiddleware -> conditionally MirrorModeMiddleware), the real
# runtime stack, outermost to innermost, is:
#   MirrorModeMiddleware -> RequestIdMiddleware -> SessionMiddleware ->
#   CORSMiddleware -> routes
# i.e. CORSMiddleware is actually the INNERMOST layer here: every request,
# including a CORS preflight OPTIONS, passes through RequestIdMiddleware and
# SessionMiddleware BEFORE reaching CORSMiddleware, not after. This does not
# currently break preflight handling — MirrorModeMiddleware explicitly passes
# OPTIONS through untouched (app/middleware.py) and neither RequestIdMiddleware
# nor SessionMiddleware raises on OPTIONS — but a future maintainer adding
# middleware that short-circuits (e.g. raises before calling call_next) should
# know CORS headers will NOT yet have been applied at that point.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# SessionMiddleware is required for OAuth state (CSRF protection) and (per the
# Phase 7 option-b provider-link flow) carries link_to_user_id — so in any HTTPS
# deployment it must be marked Secure (HTTPS-only). Defaults to False so local
# http://localhost dev and the TestClient test suite are unaffected; set
# SESSION_COOKIE_SECURE=true in staging/production.
_session_cookie_secure = os.environ.get("SESSION_COOKIE_SECURE", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)
# Must be added before route handlers that use request.session.
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=_session_cookie_secure,  # Secure flag: set SESSION_COOKIE_SECURE=true in HTTPS (staging/prod)
    same_site="lax",  # load-bearing: the Phase-7 provider-link flow relies on the session cookie surviving a top-level cross-subdomain navigation
)
app.add_middleware(RequestIdMiddleware)

# Mirror-mode guard — when OVID_MODE=mirror, reject all write methods.
# Added last so it wraps outermost (checked first on every request).
if os.environ.get("OVID_MODE") == "mirror":
    app.add_middleware(MirrorModeMiddleware)

# Rate limiting — exception handler turns RateLimitExceeded into JSON 429.
# No SlowAPIMiddleware — limit enforcement happens in the @limiter.limit()
# decorator wrappers (auto_check=True).  This avoids the middleware's
# default_limits applying on top of per-route dynamic limits.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.include_router(disc_router)
app.include_router(set_router)
app.include_router(sync_router)
app.include_router(auth_router)

# IndieAuth is opt-in (D-08): it is not one of the four headline providers, so its
# routes register only when an operator explicitly enables OVID_ENABLE_INDIEAUTH.
# Disabled by default → the IndieAuth endpoints 404. This gate is INDEPENDENT of
# the OVID_ENV production-safety guard (config import above): disabling IndieAuth
# never disables that guard, and enabling IndieAuth never re-enables the localhost
# bypass in production (Pitfall 6).
if os.environ.get("OVID_ENABLE_INDIEAUTH", "").lower() in ("1", "true", "yes"):
    app.include_router(indieauth_router)


@app.get("/health")
@limiter.limit(UNAUTH_LIMIT)
async def health(request: Request) -> dict:
    """Liveness probe for Docker healthcheck and uptime monitors."""
    return {"status": "ok"}
