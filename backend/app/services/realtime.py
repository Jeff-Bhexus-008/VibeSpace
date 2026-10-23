"""Real-time fan-out.

Local WebSocket connections live in-process; events are also published to Redis
so every instance delivers to its own clients. Clients can always fall back to
polling the REST endpoints when WebSockets are unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket
from redis import asyncio as aioredis

from app.core.config import settings
from app.core.ratelimit import get_redis

logger = logging.getLogger("vibespace.realtime")

USER_CHANNEL = "vibespace:user:{user_id}"
SUBSCRIBE_PATTERN = "vibespace:user:*"


def publish_user_event(user_id: uuid.UUID | str, event: dict[str, Any]) -> None:
    """Sync publish — safe to call from request handlers."""
    try:
        get_redis().publish(USER_CHANNEL.format(user_id=user_id), json.dumps(event, default=str))
    except Exception as exc:  # pragma: no cover - cache outage
        logger.warning("realtime publish failed: %s", exc)


class RealtimeHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._task: asyncio.Task | None = None
        self._redis: aioredis.Redis | None = None

    async def register(self, user_id: str, websocket: WebSocket) -> None:
        self._connections.setdefault(user_id, set()).add(websocket)

    async def unregister(self, user_id: str, websocket: WebSocket) -> None:
        sockets = self._connections.get(user_id)
        if sockets:
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)

    async def deliver_local(self, user_id: str, payload: dict[str, Any]) -> None:
        for socket in list(self._connections.get(user_id, set())):
            try:
                await socket.send_json(payload)
            except Exception:
                await self.unregister(user_id, socket)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def _listen(self) -> None:
        try:
            pubsub = self._redis.pubsub()
            await pubsub.psubscribe(SUBSCRIBE_PATTERN)
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                channel = str(message.get("channel", ""))
                user_id = channel.rsplit(":", 1)[-1]
                try:
                    payload = json.loads(message.get("data") or "{}")
                except json.JSONDecodeError:
                    continue
                await self.deliver_local(user_id, payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - infrastructure
            logger.warning("realtime subscriber stopped: %s", exc)


hub = RealtimeHub()