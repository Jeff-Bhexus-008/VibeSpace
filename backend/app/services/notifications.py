"""Notifications: persisted in PostgreSQL, pushed over Redis/WebSocket when possible."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.enums import NotificationType
from app.models.messaging import ConversationParticipant, Notification
from app.services.realtime import publish_user_event


def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    commit: bool = True,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        actor_id=actor_id,
        type=type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    db.add(notification)
    if commit:
        db.commit()
        db.refresh(notification)

    publish_user_event(
        user_id,
        {
            "event": "notification",
            "id": str(notification.id),
            "type": notification.type.value,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "payload": notification.payload,
        },
    )
    return notification


def notify_many(db: Session, user_ids: list[uuid.UUID], **kwargs) -> int:
    sent = 0
    for user_id in set(user_ids):
        create_notification(db, user_id=user_id, commit=False, **kwargs)
        sent += 1
    db.commit()
    for user_id in set(user_ids):
        publish_user_event(user_id, {"event": "notification", "type": kwargs.get("type", "system")})
    return sent


def mark_notifications_read(db: Session, user_id: uuid.UUID, ids: list[uuid.UUID] | None, mark_all: bool) -> int:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    if not mark_all:
        if not ids:
            return 0
        stmt = stmt.where(Notification.id.in_(ids))
    stmt = stmt.values(is_read=True, read_at=func.now())
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


def unread_summary(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    notifications = db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
    ).scalar_one()
    message_rows = db.execute(
        select(func.coalesce(func.sum(ConversationParticipant.unread_count), 0), func.count()).where(
            ConversationParticipant.user_id == user_id, ConversationParticipant.unread_count > 0
        )
    ).one()
    return {
        "notifications": int(notifications or 0),
        "messages": int(message_rows[0] or 0),
        "conversations": int(message_rows[1] or 0),
    }


def increment_conversation_unread(db: Session, conversation_id: uuid.UUID, sender_id: uuid.UUID) -> None:
    db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != sender_id,
        )
        .values(unread_count=ConversationParticipant.unread_count + 1)
    )