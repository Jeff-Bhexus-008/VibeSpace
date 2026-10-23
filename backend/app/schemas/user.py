"""Profile, follow and block schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.common import ORMModel

MESSAGE_SCOPES = ("everyone", "followers", "nobody")


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=120)
    links: list[str] | None = Field(default=None, max_length=5)
    is_private: bool | None = None
    allow_messages_from: Literal["everyone", "followers", "nobody"] | None = None
    topic_preferences: list[str] | None = Field(default=None, max_length=12)


class ProfileImageUpdate(BaseModel):
    """Key returned by the upload ticket flow (avatar/cover are images, stored in the same bucket)."""

    storage_key: str = Field(min_length=4, max_length=512)


class PublicUser(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    location: str | None = None
    links: list[str] = []
    role: str = "user"
    follower_count: int = 0
    following_count: int = 0
    video_count: int = 0
    total_likes: int = 0
    is_private: bool = False
    is_following: bool | None = None
    is_followed_by: bool | None = None
    is_blocked: bool | None = None
    is_self: bool | None = None
    created_at: datetime | None = None


class FollowState(BaseModel):
    following: bool
    follower_count: int


class BlockCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm: bool = False