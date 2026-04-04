"""Redis-backed server-side session middleware.

Stores session data in Redis with signed cookie references.  Falls back
to empty (no-op) sessions when Redis is unavailable — the API never
crashes due to session storage failure.

Cookie flags: HttpOnly=True, SameSite=Lax, Secure based on environment.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from typing import Any, Optional

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

try:
    from redis import Redis
except ImportError:  # pragma: no cover
    Redis = None  # type: ignore[assignment,misc]


class RedisSessionMiddleware:
    """ASGI middleware that stores sessions server-side in Redis.

    Session ID is stored in a signed cookie.  Session data is stored as
    JSON in Redis with a configurable TTL.

    When Redis is unavailable, the session dict is empty and read-only.
    OAuth state flows that depend on sessions will fail gracefully with
    a clear error rather than crashing the entire request pipeline.
    """

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        redis_client: Optional[Any] = None,
        redis_getter: Optional[Any] = None,
        cookie_name: str = "ovid_session",
        max_age: int = 86400,
    ) -> None:
        self.app = app
        self._signer = URLSafeTimedSerializer(secret_key)
        self._redis: Optional[Any] = redis_client
        self._redis_getter = redis_getter
        self._cookie_name = cookie_name
        self._max_age = max_age
        self._secure = os.environ.get("COOKIE_SECURE", "").lower() not in (
            "",
            "0",
            "false",
        )
        self._domain = os.environ.get("COOKIE_DOMAIN") or None

    @property
    def _active_redis(self) -> Optional[Any]:
        """Return the Redis client, resolving lazily if a getter was provided."""
        if self._redis is not None:
            return self._redis
        if self._redis_getter is not None:
            return self._redis_getter()
        return None

    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        session_id, session_data = self._load_session(connection)

        # Attach session to scope so downstream code can use request.state.session
        scope["session"] = session_data
        initial_data = dict(session_data)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Only write session if data changed
                if scope.get("session") != initial_data:
                    self._save_session(message, scope, session_id)
            await send(message)

        await self.app(scope, receive, send_wrapper)

    # ------------------------------------------------------------------

    def _load_session(
        self, connection: HTTPConnection
    ) -> tuple[str, dict[str, Any]]:
        """Load session from Redis (or cookie fallback) using signed cookie.

        Returns (session_id, session_data).  On any failure returns a
        new session ID with empty data.
        """
        cookie_value = connection.cookies.get(self._cookie_name)
        if not cookie_value:
            return secrets.token_urlsafe(32), {}

        try:
            payload = self._signer.loads(cookie_value, max_age=self._max_age)
        except BadSignature:
            logger.warning("session_invalid_signature cookie=%s", self._cookie_name)
            return secrets.token_urlsafe(32), {}

        redis = self._active_redis

        # When Redis is available, payload is a session_id string
        # When Redis is unavailable, payload is the session dict itself (cookie-mode)
        if redis is not None:
            session_id = payload if isinstance(payload, str) else secrets.token_urlsafe(32)
            try:
                raw = redis.get(f"session:{session_id}")
                if raw is None:
                    return session_id, {}
                return session_id, json.loads(raw)
            except Exception:
                logger.warning("session_redis_read_failed session_id=%s", session_id)
                return session_id, {}
        else:
            # Cookie-mode fallback: payload is the session data dict
            if isinstance(payload, dict):
                return secrets.token_urlsafe(32), payload
            # Legacy: payload was a session_id but Redis is gone
            return payload if isinstance(payload, str) else secrets.token_urlsafe(32), {}

    def _save_session(
        self, message: Message, scope: Scope, session_id: str
    ) -> None:
        """Persist session data to Redis or cookie and set the signed cookie."""
        session_data = scope.get("session", {})
        redis = self._active_redis

        if redis is not None:
            # Redis mode: store data server-side, cookie holds session_id
            try:
                redis.setex(
                    f"session:{session_id}",
                    self._max_age,
                    json.dumps(session_data),
                )
            except Exception:
                logger.warning(
                    "session_redis_write_failed session_id=%s", session_id
                )
                return
            signed = self._signer.dumps(session_id)
        else:
            # Cookie-mode fallback: embed session data in the signed cookie
            signed = self._signer.dumps(session_data)

        headers = MutableHeaders(scope=message)
        cookie_parts = [
            f"{self._cookie_name}={signed}",
            "path=/",
            f"Max-Age={self._max_age}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if self._secure:
            cookie_parts.append("Secure")
        if self._domain:
            cookie_parts.append(f"Domain={self._domain}")

        headers.append("set-cookie", "; ".join(cookie_parts))
