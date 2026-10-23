"""Media assets: upload + processing state for everything stored in object storage."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MediaKind, MediaStatus


class MediaAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded file. Bytes live in S3-compatible storage; only metadata is here."""

    __tablename__ = "media_assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[MediaKind] = mapped_column(Enum(MediaKind, name="media_kind"), nullable=False)
    status: Mapped[MediaStatus] = mapped_column(
        Enum(MediaStatus, name="media_status"), nullable=False, default=MediaStatus.pending, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    declared_content_type: Mapped[str | None] = mapped_column(String(120))
    detected_content_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float | None] = mapped_column()
    frame_rate: Mapped[float | None] = mapped_column()
    has_audio: Mapped[bool | None] = mapped_column()
    thumbnail_key: Mapped[str | None] = mapped_column(String(512))
    renditions: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    processing_error: Mapped[str | None] = mapped_column(Text)
    processing_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_non_negative"),
        Index("ix_media_assets_owner_status", "owner_id", "status"),
        Index("ix_media_assets_status_created_at", "status", "created_at"),
    )