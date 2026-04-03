"""OVID API Server — minimal bootstrap."""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth.config import SECRET_KEY
from app.auth.routes import auth_router
from app.middleware import RequestIdMiddleware
from app.routes.disc import router as disc_router

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
app.include_router(disc_router)
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict:
    """Liveness probe for Docker healthcheck and uptime monitors."""
    return {"status": "ok"}
