"""Direct messaging and notifications (with a polling-friendly REST surface)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, or_, select, update

from app.api.deps import CurrentUser, DbSession, PageWindow
from app.api.v1.serializers import public_user
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.models.messaging import Conversation, ConversationParticipant, Message, Notification
from app.models.social import Block, Follow
from app.models.user import User
from app.schemas.common import AckResponse, Page
from app.schemas.messaging import (
    ConversationCreate,
    ConversationOut,
    MarkReadRequest,
    MessageCreate,
    MessageOut,
    NotificationOut,
    ReadReceiptRequest,
    UnreadSummary,
)
from app.services import storage
from app.services.notifications import mark_notifications_read, unread_summary
from app.services.realtime import publish_user_event

router = APIRouter(tags=["messaging"])


# --- helpers ------------------------------------------------------------------
def _conversation_for(db: DbSession, conversation_id: uuid.UUID, user: User) -> ConversationParticipant:
    participant = db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user.id,
        )
    ).scalar_one_or_none()
    if participant is None:
        raise PermissionDeniedError("You are not part of this conversation.")
    return participant


def _blocked(db: DbSession, first_id: uuid.UUID, second_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(Block.id).where(
                or_(
                    (Block.blocker_id == first_id) & (Block.blocked_id == second_id),
                    (Block.blocker_id == second_id) & (Block.blocked_id == first_id),
                )
            )
        ).scalar_one_or_none()
        is not None
    )


def _can_message(db: DbSession, sender: User, recipient: User) -> None:
    if _blocked(db, sender.id, recipient.id):
        raise ConflictError("Messaging is not available with this account.")
    profile = recipient.profile
    if profile is None:
        return
    if profile.allow_messages_from == "nobody":
        raise ConflictError("This account does not accept messages.")
    if profile.allow_messages_from == "followers":
        follows = db.execute(
            select(Follow.id).where(Follow.follower_id == sender.id, Follow.followee_id == recipient.id)
        ).scalar_one_or_none()
        if follows is None:
            raise ConflictError("Only followers can message this account.")


def _message_out(db: DbSession, message: Message, senders: dict | None = None) -> MessageOut:
    sender = (senders or {}).get(message.sender_id) if message.sender_id else None
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        body=message.body if message.deleted_at is None else None,
        attachment_url=storage.media_url(message.attachment_key) if message.attachment_key else None,
        attachment_kind=message.attachment_kind,
        shared_video_id=message.shared_video_id,
        edited_at=message.edited_at,
        created_at=message.created_at,
        sender=public_user(sender) if sender else None,
    )


# --- conversations ------------------------------------------------------------
@router.get("/conversations", response_model=Page[ConversationOut])
def list_conversations(db: DbSession, user: CurrentUser, window: PageWindow) -> Page[ConversationOut]:
    stmt = (
        select(ConversationParticipant, Conversation)
        .join(Conversation, Conversation.id == ConversationParticipant.conversation_id)
        .where(ConversationParticipant.user_id == user.id)
        .order_by(Conversation.last_message_at.desc().nullslast(), Conversation.created_at.desc())
        .limit(window["limit"])
    )
    rows = db.execute(stmt).all()
    conversation_ids = [conversation.id for _participant, conversation in rows]

    members: dict[uuid.UUID, list[User]] = {conversation_id: [] for conversation_id in conversation_ids}
    if conversation_ids:
        member_rows = db.execute(
            select(ConversationParticipant.conversation_id, User)
            .join(User, User.id == ConversationParticipant.user_id)
            .where(ConversationParticipant.conversation_id.in_(conversation_ids))
        ).all()
        for conversation_id, member in member_rows:
            members.setdefault(conversation_id, []).append(member)

    previews: dict[uuid.UUID, str] = {}
    if conversation_ids:
        latest = db.execute(
            select(Message.conversation_id, Message.body)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.conversation_id, Message.created_at.desc())
        ).all()
        for conversation_id, body in latest:
            previews.setdefault(conversation_id, (body or "Attachment")[:120])

    return Page(
        items=[
            ConversationOut(
                id=conversation.id,
                is_group=conversation.is_group,
                title=conversation.title,
                last_message_at=conversation.last_message_at,
                unread_count=participant.unread_count,
                participants=[public_user(member) for member in members.get(conversation.id, [])],
                last_message_preview=previews.get(conversation.id),
            )
            for participant, conversation in rows
        ],
        has_more=len(rows) == window["limit"],
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(payload: ConversationCreate, db: DbSession, user: CurrentUser) -> ConversationOut:
    recipients = []
    for username in payload.participant_usernames:
        recipient = db.execute(
            select(User).where(func.lower(User.username) == username.lower(), User.is_suspended.is_(False))
        ).scalar_one_or_none()
        if recipient is None:
            raise NotFoundError(f"No account named {username}.")
        if recipient.id == user.id:
            continue
        _can_message(db, user, recipient)
        recipients.append(recipient)

    if not recipients:
        raise AppError("Choose at least one other account to message.")

    if len(recipients) == 1:
        existing = db.execute(
            select(Conversation)
            .join(ConversationParticipant, ConversationParticipant.conversation_id == Conversation.id)
            .where(
                Conversation.is_group.is_(False),
                ConversationParticipant.user_id.in_([user.id, recipients[0].id]),
            )
            .group_by(Conversation.id)
            .having(func.count(ConversationParticipant.id) == 2)
        ).scalar_one_or_none()
        if existing is not None:
            conversation = existing
        else:
            conversation = Conversation(created_by=user.id, is_group=False)
            db.add(conversation)
            db.flush()
            db.add_all(
                [
                    ConversationParticipant(conversation_id=conversation.id, user_id=user.id),
                    ConversationParticipant(conversation_id=conversation.id, user_id=recipients[0].id),
                ]
            )
    else:
        conversation = Conversation(
            created_by=user.id,
            is_group=True,
            title=payload.title or ", ".join(recipient.username for recipient in recipients)[:120],
        )
        db.add(conversation)
        db.flush()
        db.add(ConversationParticipant(conversation_id=conversation.id, user_id=user.id))
        db.add_all(
            [
                ConversationParticipant(conversation_id=conversation.id, user_id=recipient.id)
                for recipient in recipients
            ]
        )

    if payload.first_message:
        message = Message(conversation_id=conversation.id, sender_id=user.id, body=payload.first_message.strip())
        db.add(message)
        conversation.last_message_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(conversation)

    if payload.first_message:
        _fan_out(db, conversation, user.id, payload.first_message[:120])

    return ConversationOut(
        id=conversation.id,
        is_group=conversation.is_group,
        title=conversation.title,
        last_message_at=conversation.last_message_at,
        unread_count=0,
        participants=[public_user(member) for member in [user, *recipients]],
    )


def _fan_out(db: DbSession, conversation: Conversation, sender_id: uuid.UUID, preview: str) -> None:
    recipients = db.execute(
        select(ConversationParticipant.user_id).where(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.user_id != sender_id,
        )
    ).scalars()
    for recipient_id in recipients:
        publish_user_event(
            recipient_id,
            {
                "event": "message",
                "conversation_id": str(conversation.id),
                "preview": preview,
            },
        )


@router.get("/conversations/{conversation_id}/messages", response_model=Page[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    window: PageWindow,
    since: datetime | None = Query(default=None, description="Polling fallback: only newer messages"),
    before_id: uuid.UUID | None = Query(default=None),
) -> Page[MessageOut]:
    """Polling fallback for clients without WebSocket support."""
    _conversation_for(db, conversation_id, user)
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if since is not None:
        stmt = stmt.where(Message.created_at > since)
    if before_id is not None:
        anchor = db.get(Message, before_id)
        if anchor is not None:
            stmt = stmt.where(Message.created_at < anchor.created_at)
    stmt = stmt.order_by(Message.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars())

    senders = {}
    sender_ids = {row.sender_id for row in rows if row.sender_id}
    if sender_ids:
        senders = {
            member.id: member
            for member in db.execute(select(User).where(User.id.in_(sender_ids))).scalars().unique()
        }
    items = [_message_out(db, message, senders) for message in reversed(rows)]
    return Page(items=items, has_more=len(rows) == window["limit"])


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201)
def send_message(
    conversation_id: uuid.UUID, payload: MessageCreate, db: DbSession, user: CurrentUser
) -> MessageOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError("That conversation does not exist.")
    _conversation_for(db, conversation_id, user)

    if not payload.body and not payload.attachment_key and not payload.shared_video_id:
        raise AppError("Write a message or attach media.")

    others = db.execute(
        select(ConversationParticipant, User)
        .join(User, User.id == ConversationParticipant.user_id)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != user.id,
        )
    ).all()
    for _participant, member in others:
        _can_message(db, user, member)

    message = Message(
        conversation_id=conversation_id,
        sender_id=user.id,
        body=(payload.body or "").strip() or None,
        attachment_key=payload.attachment_key,
        attachment_kind=payload.attachment_kind,
        shared_video_id=payload.shared_video_id,
    )
    db.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    db.execute(
        update(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id != user.id,
        )
        .values(unread_count=ConversationParticipant.unread_count + 1)
    )
    db.commit()
    db.refresh(message)

    _fan_out(db, conversation, user.id, (message.body or "Attachment")[:120])
    return _message_out(db, message, {user.id: user})


@router.patch("/messages/{message_id}", response_model=MessageOut)
def edit_message(message_id: uuid.UUID, payload: MessageCreate, db: DbSession, user: CurrentUser) -> MessageOut:
    message = db.get(Message, message_id)
    if message is None or message.deleted_at is not None:
        raise NotFoundError("That message does not exist.")
    if message.sender_id != user.id:
        raise PermissionDeniedError("You can only edit your own messages.")
    if not payload.body:
        raise AppError("A message needs text.")

    message.body = payload.body.strip()
    message.edited_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return _message_out(db, message, {user.id: user})


@router.delete("/messages/{message_id}", response_model=AckResponse)
def delete_message(message_id: uuid.UUID, db: DbSession, user: CurrentUser) -> AckResponse:
    message = db.get(Message, message_id)
    if message is None:
        raise NotFoundError("That message does not exist.")
    is_staff = user.role.value in {"moderator", "admin"}
    if message.sender_id != user.id and not is_staff:
        raise PermissionDeniedError("You can only delete your own messages.")

    message.deleted_at = datetime.now(timezone.utc)
    message.body = None
    message.attachment_key = None
    db.commit()
    return AckResponse(message="Message deleted.")


@router.post("/conversations/{conversation_id}/read", response_model=AckResponse)
def mark_conversation_read(
    conversation_id: uuid.UUID, payload: ReadReceiptRequest, db: DbSession, user: CurrentUser
) -> AckResponse:
    participant = _conversation_for(db, conversation_id, user)
    participant.unread_count = 0
    participant.last_read_at = datetime.now(timezone.utc)
    db.commit()
    publish_user_event(
        user.id, {"event": "conversation_read", "conversation_id": str(conversation_id), "last_message_id": str(payload.last_message_id) if payload.last_message_id else None}
    )
    return AckResponse(message="Marked as read.")


# --- notifications ------------------------------------------------------------
@router.get("/notifications", response_model=Page[NotificationOut])
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    window: PageWindow,
    unread_only: bool = False,
) -> Page[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars())

    actor_ids = {row.actor_id for row in rows if row.actor_id}
    actors = {}
    if actor_ids:
        actors = {
            member.id: member
            for member in db.execute(select(User).where(User.id.in_(actor_ids))).scalars().unique()
        }
    return Page(
        items=[
            NotificationOut(
                id=row.id,
                type=row.type.value,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                payload=row.payload,
                is_read=row.is_read,
                read_at=row.read_at,
                created_at=row.created_at,
                actor=public_user(actors[row.actor_id]) if row.actor_id in actors else None,
            )
            for row in rows
        ],
        has_more=len(rows) == window["limit"],
    )


@router.post("/notifications/read", response_model=AckResponse)
def mark_read(payload: MarkReadRequest, db: DbSession, user: CurrentUser) -> AckResponse:
    if not payload.all and not payload.ids:
        raise AppError("Provide notification ids, or set all=true.")
    updated = mark_notifications_read(db, user.id, payload.ids, payload.all)
    return AckResponse(message=f"{updated} notification(s) marked as read.")


@router.get("/notifications/unread", response_model=UnreadSummary)
def unread(user: CurrentUser, db: DbSession) -> UnreadSummary:
    return UnreadSummary(**unread_summary(db, user.id))


@router.delete("/notifications", response_model=AckResponse)
def clear_notifications(db: DbSession, user: CurrentUser) -> AckResponse:
    result = db.execute(delete(Notification).where(Notification.user_id == user.id))
    db.commit()
    return AckResponse(message=f"{result.rowcount or 0} notification(s) cleared.")