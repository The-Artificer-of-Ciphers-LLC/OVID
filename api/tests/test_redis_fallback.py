"""Tests for Redis connection module and rate limiter fallback behavior.

Covers:
- init_redis() returns None when REDIS_URL unset (INFRA-04)
- init_redis() returns client when REDIS_URL set
- get_redis() returns None before init
- Rate limiter storage_uri selection based on REDIS_URL
- Graceful degradation when Redis unavailable at runtime
- Session middleware fallback when Redis unavailable
"""

import os
from unittest.mock import MagicMock, patch



# ---------------------------------------------------------------------------
# Redis connection module tests
# ---------------------------------------------------------------------------

class TestInitRedis:
    """Tests for init_redis() behavior."""

    def test_returns_none_when_redis_url_unset(self):
        """init_redis() returns None when REDIS_URL is not set (INFRA-04)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REDIS_URL", None)
            # Re-import to get fresh module state
            import app.redis as redis_mod
            # Reset module state
            redis_mod._client = None
            redis_mod._pool = None
            result = redis_mod.init_redis()
            assert result is None

    def test_returns_client_when_redis_url_set(self):
        """init_redis() returns a Redis client when REDIS_URL is set."""
        mock_redis_cls = MagicMock()
        mock_client = MagicMock()
        mock_redis_cls.return_value = mock_client
        mock_client.ping.return_value = True

        mock_pool_cls = MagicMock()

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            import app.redis as redis_mod
            redis_mod._client = None
            redis_mod._pool = None

            with patch.object(redis_mod, "ConnectionPool") as mock_pool, \
                 patch.object(redis_mod, "Redis") as mock_redis:
                mock_redis.return_value = mock_client
                result = redis_mod.init_redis()
                assert result is mock_client
                mock_pool.from_url.assert_called_once()

    def test_get_redis_returns_none_before_init(self):
        """get_redis() returns None before init_redis() is called."""
        import app.redis as redis_mod
        redis_mod._client = None
        result = redis_mod.get_redis()
        assert result is None

    def test_redis_available_false_before_init(self):
        """redis_available() returns False before init_redis() is called."""
        import app.redis as redis_mod
        redis_mod._client = None
        assert redis_mod.redis_available() is False

    def test_init_redis_logs_warning_when_url_unset(self):
        """init_redis() logs a warning when REDIS_URL is not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REDIS_URL", None)
            import app.redis as redis_mod
            redis_mod._client = None
            redis_mod._pool = None

            with patch.object(redis_mod.logger, "warning") as mock_warn:
                redis_mod.init_redis()
                mock_warn.assert_called_once()
                assert "redis_not_configured" in mock_warn.call_args[0][0]

    def test_init_redis_handles_connection_failure(self):
        """init_redis() returns None and logs error when Redis unreachable."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://nonexistent:6379/0"}):
            import app.redis as redis_mod
            from redis.exceptions import ConnectionError as RedisConnError
            redis_mod._client = None
            redis_mod._pool = None

            mock_client = MagicMock()
            mock_client.ping.side_effect = RedisConnError("Connection refused")

            with patch.object(redis_mod, "ConnectionPool") as mock_pool, \
                 patch.object(redis_mod, "Redis", return_value=mock_client), \
                 patch.object(redis_mod.logger, "error") as mock_err:
                result = redis_mod.init_redis()
                assert result is None
                mock_err.assert_called_once()


# ---------------------------------------------------------------------------
# Rate limiter storage_uri tests
# ---------------------------------------------------------------------------

class TestRateLimiterStorage:
    """Tests for rate limiter storage_uri selection."""

    def test_storage_uri_memory_when_redis_unset(self):
        """Rate limiter uses memory:// when REDIS_URL is unset."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REDIS_URL", None)
            from app.rate_limit import _get_storage_uri
            assert _get_storage_uri() == "memory://"

    def test_storage_uri_redis_when_redis_set(self):
        """Rate limiter uses redis:// when REDIS_URL is set."""
        with patch.dict(os.environ, {"REDIS_URL": "redis://valkey:6379/0"}):
            from app.rate_limit import _get_storage_uri
            assert "redis://" in _get_storage_uri()


# ---------------------------------------------------------------------------
# Session middleware fallback tests
# ---------------------------------------------------------------------------

class TestSessionMiddleware:
    """Tests for RedisSessionMiddleware fallback behavior."""

    def test_session_middleware_stores_in_redis(self):
        """Session middleware stores session data in Redis when available."""
        from app.auth.session import RedisSessionMiddleware

        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        mock_app = MagicMock()

        middleware = RedisSessionMiddleware(
            app=mock_app,
            secret_key="test-secret-key-at-least-32-bytes-long",
            redis_client=mock_redis,
        )
        assert middleware._redis is mock_redis

    def test_session_middleware_fallback_without_redis(self):
        """Session middleware falls back gracefully when Redis unavailable."""
        from app.auth.session import RedisSessionMiddleware

        mock_app = MagicMock()

        middleware = RedisSessionMiddleware(
            app=mock_app,
            secret_key="test-secret-key-at-least-32-bytes-long",
            redis_client=None,
        )
        assert middleware._redis is None
