"""Real-time endpoints: notifications and per-conversation chat.

WebSockets are the fast path; every event is also reachable through the REST
endpoints above, which the reference client falls back to automatically.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update

from app.core.security import ACCESS_COOKIE, decode_token
from app.db.session import SessionLocal
from app.models.messaging import ConversationParticipant, Message
from app.models.user import User
from app.services.realtime import hub

logger = logging.getLogger("vibespace.ws")

router = APIRouter()


def _authenticate(token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        return None
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if user is None or user.is_suspended:
            return None
        session.expunge(user)
        return user


def _token_from(websocket: WebSocket) -> str | None:
    cookie = websocket.cookies.get(ACCESS_COOKIE)
    if cookie:
        return cookie
    return websocket.query_params.get("token")


async def _safe_reject(websocket: WebSocket, code: int = 4401) -> None:
    await websocket.close(code=code)


@router.websocket("/ws/notifications")
async def notifications_socket(websocket: WebSocket) -> None:
    user = _authenticate(_token_from(websocket))
    if user is None:
        await websocket.accept()
        await _safe_reject(websocket)
        return

    await websocket.accept()
    user_key = str(user.id)
    await hub.register(user_key, websocket)
    await websocket.send_json({"event": "ready", "channel": "notifications", "user_id": user_key})
    try:
        while True:
            raw = await websocket.receive_text()
            # The server pushes here; client frames are only keep-alives.
            if raw.strip().lower() in {"ping", '"ping"'}:
                await websocket.send_json({"event": "pong", "at": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unregister(user_key, websocket)


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_socket(
    websocket: WebSocket, conversation_id: uuid.UUID, token: str | None = Query(default=None)
) -> None:
    user = _authenticate(token or _token_from(websocket))
    if user is None:
        await websocket.accept()
        await _safe_reject(websocket)
        return

    with SessionLocal() as session:
        membership = session.execute(
            select(ConversationParticipant.id).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user.id,
            )
        ).scalar_one_or_none()
    if membership is None:
        await websocket.accept()
        await _safe_reject(websocket, code=4403)
        return

    await websocket.accept()
    user_key = str(user.id)
    await hub.register(user_key, websocket)
    await websocket.send_json({"event": "ready", "channel": "conversation", "conversation_id": str(conversation_id)})

    try:
        while True:
            payload = await websocket.receive_json()
            if payload.get("event") == "ping":
                await websocket.send_json({"event": "pong"})
                continue
            if payload.get("event") != "message":
                continue

            body = (payload.get("body") or "").strip()
            attachment_key = payload.get("attachment_key")
            if not body and not attachment_key:
                await websocket.send_json({"event": "error", "message": "Empty message."})
                continue

            with SessionLocal() as session:
                message = Message(
                    conversation_id=conversation_id,
                    sender_id=user.id,
                    body=body or None,
                    attachment_key=attachment_key,
                    attachment_kind=payload.get("attachment_kind"),
                    shared_video_id=payload.get("shared_video_id"),
                )
                session.add(message)
                session.execute(
                    update(ConversationParticipant)
                    .where(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id != user.id,
                    )
                    .values(unread_count=ConversationParticipant.unread_count + 1)
                )
                session.commit()
                session.refresh(message)
                message_payload = {
                    "event": "message",
                    "conversation_id": str(conversation_id),
                    "id": str(message.id),
                    "sender_id": str(user.id),
                    "body": message.body,
                    "attachment_key": message.attachment_key,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
                recipients = session.execute(
                    select(ConversationParticipant.user_id).where(
                        ConversationParticipant.conversation_id == conversation_id,
                        ConversationParticipant.user_id != user.id,
                    )
                ).scalars().all()

            from app.services.realtime import publish_user_event

            for recipient_id in recipients:
                publish_user_event(recipient_id, message_payload)
            await websocket.send_json({**message_payload, "event": "message_sent"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # pragma: no cover - client dependent
        logger.warning("conversation socket failed: %s", exc)
    finally:
        await hub.unregister(user_key, websocket)