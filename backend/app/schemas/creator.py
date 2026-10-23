"""CreatorSpace schemas — real metrics only, empty states when there is no data."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class CreatorSummary(BaseModel):
    video_count: int = 0
    published_count: int = 0
    draft_count: int = 0
    processing_count: int = 0
    total_views: int = 0
    unique_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    total_saves: int = 0
    total_shares: int = 0
    follower_count: int = 0
    following_count: int = 0
    engagement_rate: float = 0.0
    has_data: bool = False


class CreatorVideoRow(ORMModel):
    id: uuid.UUID
    title: str
    status: str
    visibility: str
    thumbnail_url: str | None = None
    view_count: int = 0
    unique_view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    save_count: int = 0
    share_count: int = 0
    duration_seconds: float | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None


class AnalyticsPoint(BaseModel):
    day: date
    views: int = 0
    likes: int = 0
    comments: int = 0
    follows: int = 0
    uploads: int = 0


class AnalyticsSeries(BaseModel):
    range_days: int
    points: list[AnalyticsPoint]
    totals: dict[str, int] = {}
    has_data: bool = False


class ModerationNotice(BaseModel):
    id: uuid.UUID
    action_type: str
    target_type: str
    target_id: uuid.UUID
    reason: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    target_title: str | None = None