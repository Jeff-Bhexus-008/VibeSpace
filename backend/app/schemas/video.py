"""Video publishing schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import LearnCategory
from app.schemas.common import ORMModel


class VideoCreate(BaseModel):
    media_asset_id: uuid.UUID
    title: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    tags: list[str] = Field(default_factory=list, max_length=12)
    visibility: Literal["public", "unlisted", "private"] = "public"
    allow_comments: bool = True
    is_learn_content: bool = False
    learn_category: LearnCategory | None = None
    publish: bool = True

    def normalised_tags(self) -> list[str]:
        seen: list[str] = []
        for tag in self.tags:
            cleaned = tag.strip().lower().lstrip("#")[:32]
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen[:12]


class VideoUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = Field(default=None, max_length=12)
    visibility: Literal["public", "unlisted", "private"] | None = None
    allow_comments: bool | None = None
    is_learn_content: bool | None = None
    learn_category: LearnCategory | None = None


class AuthorSummary(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    follower_count: int = 0


class VideoOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] = []
    visibility: str
    status: str
    is_learn_content: bool = False
    learn_category: str | None = None
    allow_comments: bool = True
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    save_count: int = 0
    share_count: int = 0
    duration_seconds: float | None = None
    thumbnail_url: str | None = None
    playback_url: str | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None
    author: AuthorSummary | None = None
    is_liked: bool | None = None
    is_saved: bool | None = None
    is_owner: bool | None = None


class ViewReport(BaseModel):
    watched_seconds: float | None = Field(default=None, ge=0, le=36_000)
    counted: bool
    view_count: int