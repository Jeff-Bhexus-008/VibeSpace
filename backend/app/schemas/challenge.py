"""Vibe Battles schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import ChallengeCategory, ChallengeFormat, ChallengeStatus, EntryStatus, ParticipantRole
from app.schemas.common import ORMModel


class ChallengeCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: ChallengeCategory
    format: ChallengeFormat = ChallengeFormat.open_challenge
    rules: str | None = Field(default=None, max_length=4000)
    entry_requirements: str | None = Field(default=None, max_length=1000)
    is_public: bool = True
    is_voting_enabled: bool = True
    votes_per_voter: int = Field(default=1, ge=1, le=5)
    max_entries: int | None = Field(default=None, ge=2, le=5000)
    entries_per_user: int = Field(default=1, ge=1, le=10)
    reference_media_id: uuid.UUID | None = None
    opponent_username: str | None = Field(default=None, max_length=32)
    starts_at: datetime | None = None
    deadline_at: datetime | None = None
    voting_ends_at: datetime | None = None
    publish: bool = False

    @model_validator(mode="after")
    def validate_schedule(self) -> "ChallengeCreate":
        if self.starts_at and self.deadline_at and self.deadline_at <= self.starts_at:
            raise ValueError("deadline_at must be after starts_at")
        if self.voting_ends_at and self.deadline_at and self.voting_ends_at < self.deadline_at:
            raise ValueError("voting_ends_at cannot be before deadline_at")
        if self.format == ChallengeFormat.head_to_head and not self.opponent_username:
            raise ValueError("A head-to-head battle needs an opponent.")
        return self


class ChallengeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: ChallengeCategory | None = None
    rules: str | None = Field(default=None, max_length=4000)
    entry_requirements: str | None = Field(default=None, max_length=1000)
    is_public: bool | None = None
    is_voting_enabled: bool | None = None
    starts_at: datetime | None = None
    deadline_at: datetime | None = None
    voting_ends_at: datetime | None = None


class ChallengeCreator(ORMModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    avatar_url: str | None = None


class ChallengeOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    category: str
    format: str
    status: str
    rules: str | None = None
    entry_requirements: str | None = None
    is_public: bool = True
    is_voting_enabled: bool = True
    votes_per_voter: int = 1
    max_entries: int | None = None
    entries_per_user: int = 1
    starts_at: datetime | None = None
    deadline_at: datetime | None = None
    voting_ends_at: datetime | None = None
    completed_at: datetime | None = None
    entry_count: int = 0
    vote_count: int = 0
    participant_count: int = 0
    reference_media_url: str | None = None
    creator: ChallengeCreator | None = None
    opponent: ChallengeCreator | None = None
    winner_entry_id: uuid.UUID | None = None
    is_owner: bool | None = None
    has_joined: bool | None = None
    has_voted: bool | None = None
    accepts_entries: bool | None = None
    accepts_votes: bool | None = None
    seconds_remaining: int | None = None
    created_at: datetime | None = None


class ParticipantOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: ParticipantRole
    accepted_at: datetime | None = None
    created_at: datetime | None = None
    user: ChallengeCreator | None = None


class EntryCreate(BaseModel):
    media_asset_id: uuid.UUID
    title: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class EntryOut(ORMModel):
    id: uuid.UUID
    challenge_id: uuid.UUID
    title: str
    description: str | None = None
    status: EntryStatus
    vote_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    score: float = 0
    submitted_at: datetime | None = None
    thumbnail_url: str | None = None
    playback_url: str | None = None
    disqualification_reason: str | None = None
    user: ChallengeCreator | None = None
    is_owner: bool | None = None
    has_voted: bool | None = None


class VoteCreate(BaseModel):
    entry_id: uuid.UUID | None = None
    weight: int = Field(default=1, ge=1, le=5)


class VoteOut(ORMModel):
    id: uuid.UUID
    challenge_id: uuid.UUID
    entry_id: uuid.UUID | None = None
    voter_id: uuid.UUID
    weight: int = 1
    is_flagged: bool = False
    created_at: datetime | None = None


class ResultRow(BaseModel):
    entry_id: uuid.UUID
    title: str
    rank: int
    vote_count: int
    final_score: float
    is_final: bool
    username: str | None = None
    thumbnail_url: str | None = None


class StandingsResponse(BaseModel):
    challenge_id: uuid.UUID
    is_final: bool
    computed_at: datetime | None = None
    rows: list[ResultRow]
    note: str | None = None


class BattleStateChange(BaseModel):
    status: Literal[
        "draft",
        "scheduled",
        "open",
        "active",
        "voting",
        "completed",
        "cancelled",
    ]
    note: str | None = Field(default=None, max_length=500)


class StateChangeResponse(BaseModel):
    challenge: ChallengeOut
    allowed_next: list[ChallengeStatus]


class DisputeRequest(BaseModel):
    reason: Literal["suspicious_votes", "unfair_entry", "rule_break", "deadline_dispute", "other"]
    details: str = Field(min_length=10, max_length=1000)