"""Creator analytics events — the source of truth for the creator dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class CreatorAnalyticsEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "creator_analytics_events"

    creator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("videos.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(96))
    properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_creator_analytics_creator_event_time", "creator_id", "event_type", "occurred_at"),
        Index(
            "uq_creator_analytics_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )