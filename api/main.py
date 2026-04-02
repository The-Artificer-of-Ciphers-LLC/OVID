"""OVID API Server — minimal bootstrap."""

from fastapi import FastAPI

from app.middleware import RequestIdMiddleware
from app.routes.disc import router as disc_router

app = FastAPI(title="OVID API", description="Open Video Disc Identification Database")

app.add_middleware(RequestIdMiddleware)
app.include_router(disc_router)


@app.get("/health")
async def health() -> dict:
    """Liveness probe for Docker healthcheck and uptime monitors."""
    return {"status": "ok"}
