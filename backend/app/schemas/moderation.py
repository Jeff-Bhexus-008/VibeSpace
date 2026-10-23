"""Moderation and administration schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.user import PublicUser


class ReportOut(ORMModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    details: str | None = None
    status: str
    resolution_note: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None
    reporter: PublicUser | None = None
    target_preview: dict | None = None


class ResolveReportRequest(BaseModel):
    status: Literal["reviewing", "resolved", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)
    action: Literal[
        "none",
        "content_removed",
        "content_restored",
        "user_suspended",
        "user_reinstated",
        "entry_disqualified",
        "warning_issued",
    ] = "none"
    suspend_days: int | None = Field(default=None, ge=1, le=3650)


class ContentActionRequest(BaseModel):
    target_type: Literal["video", "comment", "entry"]
    target_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500)
    restore: bool = False


class SuspendUserRequest(BaseModel):
    user_id: uuid.UUID
    reason: str = Field(min_length=3, max_length=500)


class ModerationActionOut(ORMModel):
    id: uuid.UUID
    action_type: str
    target_type: str
    target_id: uuid.UUID
    reason: str | None = None
    notes: str | None = None
    report_id: uuid.UUID | None = None
    created_at: datetime | None = None
    moderator: PublicUser | None = None


class AuditLogOut(ORMModel):
    id: uuid.UUID
    action: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    metadata_json: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    actor: PublicUser | None = None


class CategoryCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=48, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    kind: Literal["video", "learn", "battle"] = "video"
    sort_order: int = 0
    is_active: bool = True


class CategoryOut(ORMModel):
    id: uuid.UUID
    slug: str
    label: str
    description: str | None = None
    kind: str
    is_active: bool = True
    sort_order: int = 0


class VoteAnomalyOut(BaseModel):
    entry_id: uuid.UUID | None = None
    voter_id: uuid.UUID
    votes_in_window: int
    window_minutes: int
    reason: str
    flagged: bool = False


class SuspiciousVotingResponse(BaseModel):
    challenge_id: uuid.UUID | None = None
    anomalies: list[VoteAnomalyOut]