"""Upload tickets and media asset schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

ALLOWED_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
ALLOWED_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class UploadTicketRequest(BaseModel):
    """Client asks for permission to upload; the server decides the key and the limits."""

    kind: Literal["video", "image", "audio"] = "video"
    filename: str = Field(min_length=3, max_length=255)
    declared_content_type: str = Field(min_length=3, max_length=120)
    size_bytes: int = Field(gt=0)
    purpose: Literal["video", "entry", "avatar", "cover", "reference", "message", "message_image"] = "video"


class UploadTicket(ORMModel):
    asset_id: uuid.UUID
    storage_key: str
    upload_url: str
    method: str = "PUT"
    headers: dict[str, str] = {}
    expires_in: int
    max_bytes: int


class CompleteUploadRequest(BaseModel):
    asset_id: uuid.UUID


class MediaAssetOut(ORMModel):
    id: uuid.UUID
    kind: str
    status: str
    storage_key: str
    size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    detected_content_type: str | None = None
    thumbnail_url: str | None = None
    playback_url: str | None = None
    renditions: list[dict] = []
    processing_error: str | None = None
    created_at: datetime | None = None


class UploadStatusResponse(BaseModel):
    asset: MediaAssetOut
    ready: bool