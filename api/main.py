"""OVID API Server — minimal bootstrap."""

from fastapi import FastAPI

app = FastAPI(title="OVID API", description="Open Video Disc Identification Database")


@app.get("/health")
async def health() -> dict:
    """Liveness probe for Docker healthcheck and uptime monitors."""
    return {"status": "ok"}
