"""Messaging and notification schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import PublicUser


class ConversationCreate(BaseModel):
    participant_usernames: list[str] = Field(min_length=1, max_length=20)
    title: str | None = Field(default=None, max_length=120)
    first_message: str | None = Field(default=None, max_length=2000)


class ConversationOut(ORMModel):
    id: uuid.UUID
    is_group: bool = False
    title: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    participants: list[PublicUser] = []
    last_message_preview: str | None = None


class MessageCreate(BaseModel):
    body: str | None = Field(default=None, max_length=4000)
    attachment_key: str | None = Field(default=None, max_length=512)
    attachment_kind: str | None = Field(default=None, max_length=16)
    shared_video_id: uuid.UUID | None = None


class MessageOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID | None = None
    body: str | None = None
    attachment_url: str | None = None
    attachment_kind: str | None = None
    shared_video_id: uuid.UUID | None = None
    edited_at: datetime | None = None
    created_at: datetime | None = None
    sender: PublicUser | None = None


class NotificationOut(ORMModel):
    id: uuid.UUID
    type: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    payload: dict = {}
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime | None = None
    actor: PublicUser | None = None


class UnreadSummary(BaseModel):
    notifications: int
    messages: int
    conversations: int


class MarkReadRequest(BaseModel):
    ids: list[uuid.UUID] | None = None
    all: bool = False


class ReadReceiptRequest(BaseModel):
    last_message_id: uuid.UUID | None = None