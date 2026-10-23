"""Likes, comments, saves, shares and reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: uuid.UUID | None = None


class CommentUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CommentOut(ORMModel):
    id: uuid.UUID
    video_id: uuid.UUID
    parent_id: uuid.UUID | None = None
    body: str
    like_count: int = 0
    reply_count: int = 0
    is_removed: bool = False
    created_at: datetime | None = None
    author: "CommentAuthor | None" = None
    is_owner: bool | None = None


class CommentAuthor(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


CommentOut.model_rebuild()


class LikeState(BaseModel):
    liked: bool
    like_count: int


class SaveRequest(BaseModel):
    collection: str = Field(default="Watch later", max_length=60)


class SaveState(BaseModel):
    saved: bool
    save_count: int
    collection: str | None = None


class ShareRequest(BaseModel):
    channel: Literal["link", "message", "external", "embed"] = "link"
    target_conversation_id: uuid.UUID | None = None


class ReportCreate(BaseModel):
    target_type: Literal["user", "video", "comment", "challenge", "entry", "message"]
    target_id: uuid.UUID
    reason: Literal[
        "spam",
        "harassment",
        "hate_speech",
        "violence",
        "nudity",
        "misinformation",
        "cheating",
        "copyright",
        "other",
    ]
    details: str | None = Field(default=None, max_length=1000)


class FollowSuggestion(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    follower_count: int = 0
    total_likes: int = 0