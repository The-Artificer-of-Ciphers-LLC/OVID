"""Tests for MirrorModeMiddleware.

Uses a standalone FastAPI app with the middleware applied directly,
avoiding import-time env var pollution from the main app module.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import MirrorModeMiddleware


def _make_mirror_app() -> FastAPI:
    """Create a minimal FastAPI app with MirrorModeMiddleware active."""
    app = FastAPI()
    app.add_middleware(MirrorModeMiddleware)

    @app.api_route("/test", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
    async def _test_route():
        return {"ok": True}

    return app


_mirror_app = _make_mirror_app()
_client = TestClient(_mirror_app)


# --------------------------------------------------------------------- tests


def test_post_returns_405():
    """POST to any route is blocked with 405."""
    resp = _client.post("/test")
    assert resp.status_code == 405


def test_put_returns_405():
    """PUT to any route is blocked with 405."""
    resp = _client.put("/test")
    assert resp.status_code == 405


def test_delete_returns_405():
    """DELETE to any route is blocked with 405."""
    resp = _client.delete("/test")
    assert resp.status_code == 405


def test_patch_returns_405():
    """PATCH to any route is blocked with 405."""
    resp = _client.patch("/test")
    assert resp.status_code == 405


def test_get_passes_through():
    """GET passes through the middleware and returns 200."""
    resp = _client.get("/test")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_405_body_has_mirror_mode_error_key():
    """The 405 JSON body contains error='mirror_mode'."""
    resp = _client.post("/test")
    body = resp.json()
    assert body["error"] == "mirror_mode"
    assert "mirror mode" in body["message"].lower()


def test_head_passes_through():
    """HEAD (read-only) passes through."""
    resp = _client.head("/test")
    # FastAPI returns 200 for HEAD on the same route as GET
    assert resp.status_code == 200


def test_options_passes_through():
    """OPTIONS (read-only) passes through."""
    resp = _client.options("/test")
    # FastAPI auto-generates 405 for OPTIONS if not explicitly handled,
    # but the middleware should NOT block it — only write methods are blocked.
    assert resp.status_code != 405 or "mirror_mode" not in resp.text
