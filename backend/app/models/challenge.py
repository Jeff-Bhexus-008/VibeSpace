"""Vibe Battles: challenges, participants, entries, votes, results and battle audit trail."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ChallengeCategory,
    ChallengeFormat,
    ChallengeStatus,
    EntryStatus,
    ParticipantRole,
)


class Challenge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Vibe Battle. State changes are validated server-side and journalled in battle_events."""

    __tablename__ = "challenges"

    creator_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[ChallengeCategory] = mapped_column(
        Enum(ChallengeCategory, name="challenge_category"), nullable=False, index=True
    )
    format: Mapped[ChallengeFormat] = mapped_column(
        Enum(ChallengeFormat, name="challenge_format"), nullable=False
    )
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus, name="challenge_status"), nullable=False, default=ChallengeStatus.draft, index=True
    )
    rules: Mapped[str | None] = mapped_column(Text)
    entry_requirements: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(nullable=False, default=True, index=True)
    is_voting_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    votes_per_voter: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_entries: Mapped[int | None] = mapped_column(Integer)
    entries_per_user: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reference_media_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    opponent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    voting_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_entry_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("challenge_entries.id", ondelete="SET NULL"))

    creator = relationship("User", lazy="joined", foreign_keys=[creator_id])

    __table_args__ = (
        CheckConstraint("votes_per_voter >= 1", name="votes_per_voter_min"),
        CheckConstraint("entries_per_user >= 1", name="entries_per_user_min"),
        CheckConstraint(
            "deadline_at IS NULL OR starts_at IS NULL OR deadline_at > starts_at", name="deadline_after_start"
        ),
        Index("ix_challenges_status_created", "status", "created_at"),
        Index("ix_challenges_category_status", "category", "status"),
        Index("ix_challenges_public_deadline", "is_public", "deadline_at"),
    )


class ChallengeParticipant(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "challenge_participants"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ParticipantRole] = mapped_column(
        Enum(ParticipantRole, name="participant_role"), nullable=False, default=ParticipantRole.joined
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("challenge_id", "user_id", name="challenge_user"),
        Index("ix_challenge_participants_user_created", "user_id", "created_at"),
    )


class ChallengeEntry(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "challenge_entries"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    video_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("videos.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[EntryStatus] = mapped_column(
        Enum(EntryStatus, name="entry_status"), nullable=False, default=EntryStatus.submitted, index=True
    )
    disqualification_reason: Mapped[str | None] = mapped_column(Text)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    like_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    submitter = relationship("User", lazy="joined", foreign_keys=[user_id])
    media = relationship("MediaAsset", lazy="joined")

    __table_args__ = (
        CheckConstraint("vote_count >= 0 AND like_count >= 0", name="challenges_counters_non_negative"),
        Index("ix_challenge_entries_challenge_votes", "challenge_id", "vote_count"),
        Index("ix_challenge_entries_user_created", "user_id", "created_at"),
    )


class Vote(UUIDPrimaryKeyMixin, Base):
    """One row per vote. Two partial unique indexes enforce the fairness rules in the database."""

    __tablename__ = "votes"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("challenge_entries.id", ondelete="CASCADE"), index=True
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    is_flagged: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    flag_reason: Mapped[str | None] = mapped_column(Text)
    voter_ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint("weight BETWEEN 1 AND 5", name="weight_range"),
        Index("uq_votes_entry_voter", "entry_id", "voter_id", unique=True, postgresql_where=text("entry_id IS NOT NULL")),
        Index(
            "uq_votes_challenge_voter",
            "challenge_id",
            "voter_id",
            unique=True,
            postgresql_where=text("entry_id IS NULL"),
        ),
        Index("ix_votes_challenge_created", "challenge_id", "created_at"),
        Index("ix_votes_voter_created", "voter_id", "created_at"),
    )


class BattleResult(UUIDPrimaryKeyMixin, Base):
    """Final or provisional standings, always computed by the backend."""

    __tablename__ = "battle_results"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenge_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    is_final: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("challenge_id", "entry_id", "is_final", name="challenge_entry_finality"),
        Index("ix_battle_results_challenge_rank", "challenge_id", "rank"),
    )


class BattleEvent(UUIDPrimaryKeyMixin, Base):
    """Immutable journal of battle-relevant actions, used for audits and disputes."""

    __tablename__ = "battle_events"

    challenge_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_battle_events_challenge_created", "challenge_id", "created_at"),)