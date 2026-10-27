"""Published videos, their counters and audited view events."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import LearnCategory, VideoStatus, VideoVisibility


class Video(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "videos"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40), index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    visibility: Mapped[VideoVisibility] = mapped_column(
        Enum(VideoVisibility, name="video_visibility"), nullable=False, default=VideoVisibility.public, index=True
    )
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"), nullable=False, default=VideoStatus.draft, index=True
    )
    is_learn_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    learn_category: Mapped[LearnCategory | None] = mapped_column(Enum(LearnCategory, name="learn_category"))
    allow_comments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    removed_reason: Mapped[str | None] = mapped_column(Text)

    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    save_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    media = relationship("MediaAsset", lazy="joined")

    __table_args__ = (
        CheckConstraint("view_count >= 0 AND like_count >= 0 AND comment_count >= 0", name="videos_counters_non_negative"),
        Index("ix_videos_feed", "status", "visibility", "published_at"),
        Index("ix_videos_owner_published", "owner_id", "published_at"),
        Index("ix_videos_learn", "is_learn_content", "learn_category", "published_at"),
    )


class VideoViewEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only view log. Counters are derived from deduplicated events."""

    __tablename__ = "video_view_events"

    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    viewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    session_key: Mapped[str | None] = mapped_column(String(64))
    watched_seconds: Mapped[float | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="feed")
    counted_as_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("ix_video_view_events_video_created", "video_id", "created_at"),)