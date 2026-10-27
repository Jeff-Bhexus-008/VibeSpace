"""Follows, blocks, likes, comments, saves and shares."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Follow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "follows"

    follower_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    followee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="follower_followee"),
        CheckConstraint("follower_id <> followee_id", name="no_self_follow"),
        Index("ix_follows_followee_created", "followee_id", "created_at"),
    )


class Block(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "blocks"

    blocker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="blocker_blocked"),
        CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
    )


class Like(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "likes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_likes_user_video"),)


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("comments.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    removed_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
        Index("ix_comments_video_created", "video_id", "created_at"),
        Index("ix_comments_parent_created", "parent_id", "created_at"),
    )


class SavedVideo(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "saved_videos"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection: Mapped[str] = mapped_column(String(60), nullable=False, default="Watch later")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "video_id", name="uq_saved_videos_user_video"),
        Index("ix_saved_videos_user_collection", "user_id", "collection"),
    )


class ShareEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "share_events"

    video_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="link")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )