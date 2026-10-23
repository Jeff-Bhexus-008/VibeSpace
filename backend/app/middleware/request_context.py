"""Request id + timing + one structured log line per request.

Bodies are never logged, so passwords, reset tokens and message contents stay
out of the log stream.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("vibespace.request")

SKIP_PATHS = {"/health", "/health/ready", "/openapi.json", "/docs", "/redoc"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        user = getattr(request.state, "user", None)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)

        if request.url.path not in SKIP_PATHS:
            logger.info(
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "user_id": str(user.id) if user else None,
                    "query_keys": sorted(request.query_params.keys()),
                },
            )
        return response