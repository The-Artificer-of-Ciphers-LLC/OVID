"""Redis / Valkey connection pool with graceful fallback.

Provides a centralized Redis client for rate limiting, sessions, and
token blacklisting.  When REDIS_URL is unset or the server is unreachable,
all consumers fall back to in-memory or no-op behavior — the API never
crashes due to Redis unavailability.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from redis import ConnectionPool, Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None


def init_redis() -> Optional[Redis]:
    """Initialize the Redis connection pool from REDIS_URL.

    Returns the Redis client on success, or None if REDIS_URL is unset
    or the server is unreachable.  Safe to call multiple times — subsequent
    calls re-initialize (useful for testing).
    """
    global _pool, _client

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.warning(
            "redis_not_configured REDIS_URL not set, using in-memory fallback"
        )
        _pool = None
        _client = None
        return None

    # Log only the host portion — never log passwords (T-1-02)
    safe_url = redis_url.split("@")[-1]
    logger.info("redis_connecting host=%s", safe_url)

    try:
        _pool = ConnectionPool.from_url(redis_url, max_connections=10)
        _client = Redis(connection_pool=_pool)
        _client.ping()
        logger.info("redis_connected host=%s", safe_url)
        return _client
    except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
        logger.error(
            "redis_connect_failed host=%s error=%s", safe_url, exc
        )
        _pool = None
        _client = None
        return None


def get_redis() -> Optional[Redis]:
    """Return the current Redis client, or None if not initialized."""
    return _client


def redis_available() -> bool:
    """Return True if a Redis client is connected and responding."""
    return _client is not None
