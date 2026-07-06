"""Redis-outage fallback test for the rate limiter (INFRA-02, D-01/D-03).

Pins the tested outage decision: when the shared Redis store is unreachable,
the limiter degrades to a **bounded, self-healing in-memory fallback** rather
than failing closed on the read-heavy ARM lookup path. Requests keep returning
200 while under ``FALLBACK_LIMIT`` (a per-worker cap) and return 429 once that
cap is exceeded.

The outage is injected deterministically per the repo's cross-platform
IO-failure convention (CLAUDE.md): save the original ``RedisStorage.incr``,
override it to raise ``redis.exceptions.ConnectionError``, assert, then restore
in ``finally`` — never a live-Redis dependency or a permission trick. No live
Redis is required: ``redis.from_url`` does not connect eagerly, and every
counter operation is intercepted before it reaches the socket.
"""

import limits.storage
import redis.exceptions
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.rate_limit import FALLBACK_LIMIT, rate_limit_exceeded_handler


def _fixed_key(request: Request) -> str:
    """A constant key so every request shares one counter.

    NOTE: the parameter MUST be named ``request`` — slowapi inspects the key
    function's signature and only passes the Request when the parameter is
    literally called ``request`` (mirrors ``_auth_aware_key`` in the app).
    """
    return "outage-test-key"


def _fallback_cap() -> int:
    """The integer hit count encoded in FALLBACK_LIMIT's first window."""
    return int(FALLBACK_LIMIT.split("/")[0])


def test_redis_outage_falls_back_to_bounded_cap() -> None:
    """Injected ConnectionError → 200 within FALLBACK_LIMIT, then 429."""
    limiter = Limiter(
        key_func=_fixed_key,
        default_limits=["100000/minute"],  # deliberately huge; outage cap must bind
        storage_uri="redis://localhost:6379",
        swallow_errors=True,
        in_memory_fallback_enabled=True,
        in_memory_fallback=[FALLBACK_LIMIT],
    )

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.get("/ping")
    @limiter.limit("100000/minute")
    async def ping(request: Request):  # noqa: ANN202
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)

    original_incr = limits.storage.RedisStorage.incr

    def _boom(self, *args, **kwargs):
        raise redis.exceptions.ConnectionError("injected redis outage")

    limits.storage.RedisStorage.incr = _boom
    try:
        cap = _fallback_cap()

        # Within the per-worker fallback cap: reads keep flowing (fail-open, D-02).
        for i in range(cap):
            resp = client.get("/ping")
            assert resp.status_code == 200, (
                f"request {i + 1}/{cap} during outage expected 200, "
                f"got {resp.status_code}: {resp.text}"
            )

        # Once the bounded cap is exceeded: 429 with the structured envelope.
        resp = client.get("/ping")
        assert resp.status_code == 429, (
            f"request {cap + 1} should exceed FALLBACK_LIMIT and 429, "
            f"got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["error"] == "rate_limited", body
        assert "retry_after" in body, body
    finally:
        limits.storage.RedisStorage.incr = original_incr
