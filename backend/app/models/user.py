"""Accounts and public profiles."""

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
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import UserRole


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.user, index=True
    )
    is_email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["UserProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("char_length(username) >= 3", name="username_min_length"),
        Index("ix_users_role_created_at", "role", "created_at"),
    )


class UserProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(80))
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_key: Mapped[str | None] = mapped_column(String(512))
    cover_key: Mapped[str | None] = mapped_column(String(512))
    location: Mapped[str | None] = mapped_column(String(120))
    links: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_messages_from: Mapped[str] = mapped_column(String(16), nullable=False, default="everyone")
    topic_preferences: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # Denormalised counters kept authoritative by services (never by the client).
    follower_count: Mapped[int] = mapped_column(nullable=False, default=0)
    following_count: Mapped[int] = mapped_column(nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(nullable=False, default=0)
    total_likes: Mapped[int] = mapped_column(nullable=False, default=0)

    user: Mapped["User"] = relationship(back_populates="profile")

    __table_args__ = (
        CheckConstraint(
            "allow_messages_from IN ('everyone', 'followers', 'nobody')", name="messages_scope_valid"
        ),
        Index("ix_user_profiles_follower_count", "follower_count"),
    )