"""Request-ID middleware — generates a UUID4 per request.
MirrorModeMiddleware — rejects write methods when OVID_MODE=mirror.
"""

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request/response cycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class MirrorModeMiddleware(BaseHTTPMiddleware):
    """Return 405 on all mutating HTTP methods when active.

    This middleware is added only when ``OVID_MODE=mirror``.  Read-only
    methods (GET, HEAD, OPTIONS) pass through unchanged.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in _WRITE_METHODS:
            logger.warning(
                "mirror_mode_blocked method=%s path=%s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=405,
                content={
                    "error": "mirror_mode",
                    "message": (
                        "This OVID instance is in mirror mode. "
                        "Write operations are disabled."
                    ),
                },
            )
        return await call_next(request)
