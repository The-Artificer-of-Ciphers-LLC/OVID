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

# CORS — must be added before SessionMiddleware so preflight OPTIONS
# requests get proper headers without hitting the session layer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# SessionMiddleware is required for OAuth state (CSRF protection).
# Must be added before route handlers that use request.session.
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
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
