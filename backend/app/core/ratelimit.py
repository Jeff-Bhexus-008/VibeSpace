"""Redis-backed fixed-window rate limiting.

Sensitive endpoints (login, register, password reset, uploads, votes) declare a
bucket. If Redis is unreachable the limiter fails open and logs a warning so a
cache outage never takes the whole API down.
"""

from __future__ import annotations

import logging
from typing import Callable

import redis
from fastapi import Request

from app.core.config import settings
from app.core.errors import RateLimitedError

logger = logging.getLogger("vibespace.ratelimit")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1.5)
    return _client


def client_identifier(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is not None:
        return f"user:{user.id}"
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"ip:{ip}"


def enforce(bucket: str, limit: int, window_seconds: int, request: Request) -> None:
    if limit <= 0:
        return
    key = f"rl:{bucket}:{client_identifier(request)}:{window_seconds}"
    try:
        client = get_redis()
        current = client.incr(key)
        if current == 1:
            client.expire(key, window_seconds)
        if current > limit:
            raise RateLimitedError("Too many requests. Please slow down and try again shortly.")
    except RateLimitedError:
        raise
    except redis.RedisError as exc:  # pragma: no cover - depends on infrastructure
        logger.warning("rate limiter unavailable, failing open: %s", exc)


def rate_limit(bucket: str, limit: int, window_seconds: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        enforce(bucket, limit, window_seconds, request)

    return dependency