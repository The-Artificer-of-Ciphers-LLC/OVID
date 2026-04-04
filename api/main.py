"""OVID API Server — minimal bootstrap."""

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from slowapi.errors import RateLimitExceeded

from app.auth.config import SECRET_KEY
from app.auth.device_flow import device_router
from app.auth.routes import auth_router
from app.auth.session import RedisSessionMiddleware
from app.middleware import MirrorModeMiddleware, RequestIdMiddleware
from app.rate_limit import UNAUTH_LIMIT, limiter, rate_limit_exceeded_handler
from app.redis import get_redis, init_redis
from app.routes.disc import router as disc_router
from app.routes.set import router as set_router
from app.routes.sync import router as sync_router


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize shared resources at startup."""
    init_redis()
    yield


app = FastAPI(
    title="OVID API",
    description="Open Video Disc Identification Database",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — parse ALLOWED_ORIGINS (preferred) falling back to CORS_ORIGINS
# ---------------------------------------------------------------------------
_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    os.environ.get("CORS_ORIGINS", "http://localhost:3000"),
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Session middleware — Redis-backed, separate secret key (D-06)
# ---------------------------------------------------------------------------
_session_secret = os.environ.get("SESSION_SECRET_KEY") or SECRET_KEY
app.add_middleware(
    RedisSessionMiddleware,
    secret_key=_session_secret,
    redis_getter=get_redis,
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
app.include_router(device_router)


@app.get("/health")
@limiter.limit(UNAUTH_LIMIT)
async def health(request: Request) -> dict:
    """Liveness probe for Docker healthcheck and uptime monitors."""
    return {"status": "ok"}
