"""Shared enumerations — mirrors the PostgreSQL enum types created by migration 0001."""

from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    user = "user"
    creator = "creator"
    moderator = "moderator"
    admin = "admin"


class MediaKind(str, enum.Enum):
    video = "video"
    image = "image"
    audio = "audio"


class MediaStatus(str, enum.Enum):
    pending = "pending"
    uploading = "uploading"
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class VideoVisibility(str, enum.Enum):
    public = "public"
    unlisted = "unlisted"
    private = "private"


class VideoStatus(str, enum.Enum):
    draft = "draft"
    processing = "processing"
    ready = "ready"
    removed = "removed"


class ChallengeCategory(str, enum.Enum):
    dance = "dance"
    comedy = "comedy"
    music = "music"
    sports = "sports"
    gaming = "gaming"
    coding = "coding"
    education = "education"
    art = "art"
    fitness = "fitness"
    creativity = "creativity"


class ChallengeFormat(str, enum.Enum):
    head_to_head = "head_to_head"
    open_challenge = "open_challenge"
    community_challenge = "community_challenge"
    skill_challenge = "skill_challenge"


class ChallengeStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    open = "open"
    active = "active"
    voting = "voting"
    completed = "completed"
    cancelled = "cancelled"


class ParticipantRole(str, enum.Enum):
    host = "host"
    challenger = "challenger"
    invited = "invited"
    joined = "joined"


class EntryStatus(str, enum.Enum):
    submitted = "submitted"
    approved = "approved"
    disqualified = "disqualified"
    withdrawn = "withdrawn"


class NotificationType(str, enum.Enum):
    follow = "follow"
    like = "like"
    comment = "comment"
    reply = "reply"
    battle_invite = "battle_invite"
    battle_entry = "battle_entry"
    battle_vote_milestone = "battle_vote_milestone"
    battle_result = "battle_result"
    message = "message"
    moderation = "moderation"
    system = "system"


class ReportTarget(str, enum.Enum):
    user = "user"
    video = "video"
    comment = "comment"
    challenge = "challenge"
    entry = "entry"
    message = "message"


class ReportStatus(str, enum.Enum):
    open = "open"
    reviewing = "reviewing"
    resolved = "resolved"
    dismissed = "dismissed"


class ModerationActionType(str, enum.Enum):
    content_removed = "content_removed"
    content_restored = "content_restored"
    user_suspended = "user_suspended"
    user_reinstated = "user_reinstated"
    entry_disqualified = "entry_disqualified"
    result_finalized = "result_finalized"
    report_dismissed = "report_dismissed"
    warning_issued = "warning_issued"


class TokenPurpose(str, enum.Enum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class LearnCategory(str, enum.Enum):
    programming = "programming"
    technology = "technology"
    business = "business"
    academics = "academics"
    creative_arts = "creative_arts"
    personal_development = "personal_development"
    practical_skills = "practical_skills"