"""VibeSpace initial schema

Creates every table for accounts, media, videos, social graph, battles, voting,
messaging, moderation and analytics, including the constraints that make the
fairness rules true at the database level.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

ENUMS: dict[str, list[str]] = {
    "user_role": ["user", "creator", "moderator", "admin"],
    "media_kind": ["video", "image", "audio"],
    "media_status": ["pending", "uploading", "uploaded", "processing", "ready", "failed"],
    "video_visibility": ["public", "unlisted", "private"],
    "video_status": ["draft", "processing", "ready", "removed"],
    "learn_category": [
        "programming",
        "technology",
        "business",
        "academics",
        "creative_arts",
        "personal_development",
        "practical_skills",
    ],
    "challenge_category": [
        "dance",
        "comedy",
        "music",
        "sports",
        "gaming",
        "coding",
        "education",
        "art",
        "fitness",
        "creativity",
    ],
    "challenge_format": ["head_to_head", "open_challenge", "community_challenge", "skill_challenge"],
    "challenge_status": ["draft", "scheduled", "open", "active", "voting", "completed", "cancelled"],
    "participant_role": ["host", "challenger", "invited", "joined"],
    "entry_status": ["submitted", "approved", "disqualified", "withdrawn"],
    "notification_type": [
        "follow",
        "like",
        "comment",
        "reply",
        "battle_invite",
        "battle_entry",
        "battle_vote_milestone",
        "battle_result",
        "message",
        "moderation",
        "system",
    ],
    "report_target": ["user", "video", "comment", "challenge", "entry", "message"],
    "report_status": ["open", "reviewing", "resolved", "dismissed"],
    "moderation_action_type": [
        "content_removed",
        "content_restored",
        "user_suspended",
        "user_reinstated",
        "entry_disqualified",
        "result_finalized",
        "report_dismissed",
        "warning_issued",
    ],
    "moderation_target_type": ["user", "video", "comment", "challenge", "entry", "message"],
    "token_purpose": ["verify_email", "reset_password"],
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an enum type that upgrade() has already created explicitly."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # --- accounts -------------------------------------------------------------
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", _enum("user_role"), server_default="user", nullable=False),
        sa.Column("is_email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("is_suspended", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suspended_reason", sa.Text()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("char_length(username) >= 3", name="username_min_length"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])
    op.create_index("ix_users_role_created_at", "users", ["role", "created_at"])

    op.create_table(
        "user_profiles",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(80)),
        sa.Column("bio", sa.Text()),
        sa.Column("avatar_key", sa.String(512)),
        sa.Column("cover_key", sa.String(512)),
        sa.Column("location", sa.String(120)),
        sa.Column("links", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("is_private", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("allow_messages_from", sa.String(16), server_default="everyone", nullable=False),
        sa.Column("topic_preferences", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("follower_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("following_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("video_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("total_likes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_ts(),
        sa.CheckConstraint("allow_messages_from IN ('everyone', 'followers', 'nobody')", name="messages_scope_valid"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)
    op.create_index("ix_user_profiles_follower_count", "user_profiles", ["follower_count"])

    op.create_table(
        "refresh_tokens",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_id", sa.Uuid(), sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL")),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("ip_hash", sa.String(64)),
        _created_at(),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])
    op.create_index("ix_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked_at", "expires_at"])

    op.create_table(
        "email_tokens",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", _enum("token_purpose"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("request_ip_hash", sa.String(64)),
        _created_at(),
    )
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index("ix_email_tokens_purpose", "email_tokens", ["purpose"])
    op.create_index("ix_email_tokens_user_purpose", "email_tokens", ["user_id", "purpose", "used_at"])

    # --- media + videos -------------------------------------------------------
    op.create_table(
        "media_assets",
        _pk(),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", _enum("media_kind"), nullable=False),
        sa.Column("status", _enum("media_status"), server_default="pending", nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("bucket", sa.String(120), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("declared_content_type", sa.String(120)),
        sa.Column("detected_content_type", sa.String(120)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("frame_rate", sa.Float()),
        sa.Column("has_audio", sa.Boolean()),
        sa.Column("thumbnail_key", sa.String(512)),
        sa.Column("renditions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("processing_error", sa.Text()),
        sa.Column("processing_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_non_negative"),
    )
    op.create_index("ix_media_assets_owner_id", "media_assets", ["owner_id"])
    op.create_index("ix_media_assets_status", "media_assets", ["status"])
    op.create_index("ix_media_assets_owner_status", "media_assets", ["owner_id", "status"])
    op.create_index("ix_media_assets_status_created_at", "media_assets", ["status", "created_at"])

    op.create_table(
        "videos",
        _pk(),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "media_asset_id", sa.Uuid(), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(40)),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("visibility", _enum("video_visibility"), server_default="public", nullable=False),
        sa.Column("status", _enum("video_status"), server_default="draft", nullable=False),
        sa.Column("is_learn_content", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("learn_category", _enum("learn_category")),
        sa.Column("allow_comments", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_removed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("removed_reason", sa.Text()),
        sa.Column("view_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unique_view_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("comment_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("save_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("share_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint(
            "view_count >= 0 AND like_count >= 0 AND comment_count >= 0", name="counters_non_negative"
        ),
    )
    op.create_index("ix_videos_owner_id", "videos", ["owner_id"])
    op.create_index("ix_videos_media_asset_id", "videos", ["media_asset_id"])
    op.create_index("ix_videos_category", "videos", ["category"])
    op.create_index("ix_videos_visibility", "videos", ["visibility"])
    op.create_index("ix_videos_status", "videos", ["status"])
    op.create_index("ix_videos_is_learn_content", "videos", ["is_learn_content"])
    op.create_index("ix_videos_is_removed", "videos", ["is_removed"])
    op.create_index("ix_videos_published_at", "videos", ["published_at"])
    op.create_index("ix_videos_feed", "videos", ["status", "visibility", "published_at"])
    op.create_index("ix_videos_owner_published", "videos", ["owner_id", "published_at"])
    op.create_index("ix_videos_learn", "videos", ["is_learn_content", "learn_category", "published_at"])

    op.create_table(
        "video_view_events",
        _pk(),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("viewer_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("session_key", sa.String(64)),
        sa.Column("watched_seconds", sa.Float()),
        sa.Column("source", sa.String(24), server_default="feed", nullable=False),
        sa.Column("counted_as_unique", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _created_at(),
    )
    op.create_index("ix_video_view_events_video_id", "video_view_events", ["video_id"])
    op.create_index("ix_video_view_events_created_at", "video_view_events", ["created_at"])
    op.create_index("ix_video_view_events_video_created", "video_view_events", ["video_id", "created_at"])

    # --- social graph ---------------------------------------------------------
    op.create_table(
        "follows",
        _pk(),
        sa.Column("follower_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("followee_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        _created_at(),
        sa.UniqueConstraint("follower_id", "followee_id", name="follower_followee"),
        sa.CheckConstraint("follower_id <> followee_id", name="no_self_follow"),
    )
    op.create_index("ix_follows_follower_id", "follows", ["follower_id"])
    op.create_index("ix_follows_followee_id", "follows", ["followee_id"])
    op.create_index("ix_follows_followee_created", "follows", ["followee_id", "created_at"])

    op.create_table(
        "blocks",
        _pk(),
        sa.Column("blocker_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("blocked_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.Text()),
        _created_at(),
        sa.UniqueConstraint("blocker_id", "blocked_id", name="blocker_blocked"),
        sa.CheckConstraint("blocker_id <> blocked_id", name="no_self_block"),
    )
    op.create_index("ix_blocks_blocker_id", "blocks", ["blocker_id"])
    op.create_index("ix_blocks_blocked_id", "blocks", ["blocked_id"])

    op.create_table(
        "likes",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        _created_at(),
        sa.UniqueConstraint("user_id", "video_id", name="user_video"),
    )
    op.create_index("ix_likes_user_id", "likes", ["user_id"])
    op.create_index("ix_likes_video_id", "likes", ["video_id"])
    op.create_index("ix_likes_created_at", "likes", ["created_at"])

    op.create_table(
        "comments",
        _pk(),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Uuid(), sa.ForeignKey("comments.id", ondelete="CASCADE")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reply_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_removed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("removed_reason", sa.Text()),
        *_ts(),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
    )
    op.create_index("ix_comments_video_id", "comments", ["video_id"])
    op.create_index("ix_comments_author_id", "comments", ["author_id"])
    op.create_index("ix_comments_is_removed", "comments", ["is_removed"])
    op.create_index("ix_comments_video_created", "comments", ["video_id", "created_at"])
    op.create_index("ix_comments_parent_created", "comments", ["parent_id", "created_at"])

    op.create_table(
        "saved_videos",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("collection", sa.String(60), server_default="Watch later", nullable=False),
        _created_at(),
        sa.UniqueConstraint("user_id", "video_id", name="user_video"),
    )
    op.create_index("ix_saved_videos_user_id", "saved_videos", ["user_id"])
    op.create_index("ix_saved_videos_video_id", "saved_videos", ["video_id"])
    op.create_index("ix_saved_videos_user_collection", "saved_videos", ["user_id", "collection"])

    op.create_table(
        "share_events",
        _pk(),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(24), server_default="link", nullable=False),
        _created_at(),
    )
    op.create_index("ix_share_events_video_id", "share_events", ["video_id"])

    # --- battles --------------------------------------------------------------
    op.create_table(
        "challenges",
        _pk(),
        sa.Column("creator_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", _enum("challenge_category"), nullable=False),
        sa.Column("format", _enum("challenge_format"), nullable=False),
        sa.Column("status", _enum("challenge_status"), server_default="draft", nullable=False),
        sa.Column("rules", sa.Text()),
        sa.Column("entry_requirements", sa.Text()),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_voting_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("votes_per_voter", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("max_entries", sa.Integer()),
        sa.Column("entries_per_user", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("reference_media_id", sa.Uuid(), sa.ForeignKey("media_assets.id", ondelete="SET NULL")),
        sa.Column("opponent_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("voting_ends_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("entry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("vote_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("participant_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("winner_entry_id", sa.Uuid()),
        *_ts(),
        sa.CheckConstraint("votes_per_voter >= 1", name="votes_per_voter_min"),
        sa.CheckConstraint("entries_per_user >= 1", name="entries_per_user_min"),
        sa.CheckConstraint(
            "deadline_at IS NULL OR starts_at IS NULL OR deadline_at > starts_at", name="deadline_after_start"
        ),
    )
    op.create_index("ix_challenges_creator_id", "challenges", ["creator_id"])
    op.create_index("ix_challenges_category", "challenges", ["category"])
    op.create_index("ix_challenges_status", "challenges", ["status"])
    op.create_index("ix_challenges_is_public", "challenges", ["is_public"])
    op.create_index("ix_challenges_starts_at", "challenges", ["starts_at"])
    op.create_index("ix_challenges_deadline_at", "challenges", ["deadline_at"])
    op.create_index("ix_challenges_status_created", "challenges", ["status", "created_at"])
    op.create_index("ix_challenges_category_status", "challenges", ["category", "status"])
    op.create_index("ix_challenges_public_deadline", "challenges", ["is_public", "deadline_at"])

    op.create_table(
        "challenge_participants",
        _pk(),
        sa.Column("challenge_id", sa.Uuid(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", _enum("participant_role"), server_default="joined", nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.UniqueConstraint("challenge_id", "user_id", name="challenge_user"),
    )
    op.create_index("ix_challenge_participants_challenge_id", "challenge_participants", ["challenge_id"])
    op.create_index("ix_challenge_participants_user_id", "challenge_participants", ["user_id"])
    op.create_index("ix_challenge_participants_user_created", "challenge_participants", ["user_id", "created_at"])

    op.create_table(
        "challenge_entries",
        _pk(),
        sa.Column("challenge_id", sa.Uuid(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "media_asset_id", sa.Uuid(), sa.ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", _enum("entry_status"), server_default="submitted", nullable=False),
        sa.Column("disqualification_reason", sa.Text()),
        sa.Column("vote_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("like_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("comment_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *_ts(),
        sa.CheckConstraint("vote_count >= 0 AND like_count >= 0", name="counters_non_negative"),
    )
    op.create_index("ix_challenge_entries_challenge_id", "challenge_entries", ["challenge_id"])
    op.create_index("ix_challenge_entries_user_id", "challenge_entries", ["user_id"])
    op.create_index("ix_challenge_entries_status", "challenge_entries", ["status"])
    op.create_index("ix_challenge_entries_submitted_at", "challenge_entries", ["submitted_at"])
    op.create_index("ix_challenge_entries_challenge_votes", "challenge_entries", ["challenge_id", "vote_count"])
    op.create_index("ix_challenge_entries_user_created", "challenge_entries", ["user_id", "created_at"])

    op.create_foreign_key(
        "fk_challenges_winner_entry_id_challenge_entries",
        "challenges",
        "challenge_entries",
        ["winner_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "votes",
        _pk(),
        sa.Column("challenge_id", sa.Uuid(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("challenge_entries.id", ondelete="CASCADE")),
        sa.Column("voter_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("flag_reason", sa.Text()),
        sa.Column("voter_ip_hash", sa.String(64)),
        _created_at(),
        sa.CheckConstraint("weight BETWEEN 1 AND 5", name="weight_range"),
    )
    op.create_index("ix_votes_challenge_id", "votes", ["challenge_id"])
    op.create_index("ix_votes_entry_id", "votes", ["entry_id"])
    op.create_index("ix_votes_voter_id", "votes", ["voter_id"])
    op.create_index("ix_votes_created_at", "votes", ["created_at"])
    op.create_index("ix_votes_is_flagged", "votes", ["is_flagged"])
    # Fairness enforced by the database: one vote per voter per entry, and one vote
    # per voter per head-to-head battle (ballots without an entry id).
    op.create_index(
        "uq_votes_entry_voter",
        "votes",
        ["entry_id", "voter_id"],
        unique=True,
        postgresql_where=sa.text("entry_id IS NOT NULL"),
    )
    op.create_index(
        "uq_votes_challenge_voter",
        "votes",
        ["challenge_id", "voter_id"],
        unique=True,
        postgresql_where=sa.text("entry_id IS NULL"),
    )
    op.create_index("ix_votes_challenge_created", "votes", ["challenge_id", "created_at"])
    op.create_index("ix_votes_voter_created", "votes", ["voter_id", "created_at"])

    op.create_table(
        "battle_results",
        _pk(),
        sa.Column("challenge_id", sa.Uuid(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_id", sa.Uuid(), sa.ForeignKey("challenge_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("vote_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("final_score", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_final", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("challenge_id", "entry_id", "is_final", name="challenge_entry_finality"),
    )
    op.create_index("ix_battle_results_challenge_id", "battle_results", ["challenge_id"])
    op.create_index("ix_battle_results_entry_id", "battle_results", ["entry_id"])
    op.create_index("ix_battle_results_is_final", "battle_results", ["is_final"])
    op.create_index("ix_battle_results_challenge_rank", "battle_results", ["challenge_id", "rank"])

    op.create_table(
        "battle_events",
        _pk(),
        sa.Column("challenge_id", sa.Uuid(), sa.ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _created_at(),
    )
    op.create_index("ix_battle_events_challenge_id", "battle_events", ["challenge_id"])
    op.create_index("ix_battle_events_event_type", "battle_events", ["event_type"])
    op.create_index("ix_battle_events_challenge_created", "battle_events", ["challenge_id", "created_at"])

    # --- messaging + notifications -------------------------------------------
    op.create_table(
        "conversations",
        _pk(),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("is_group", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("title", sa.String(120)),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        *_ts(),
    )
    op.create_index("ix_conversations_last_message", "conversations", ["last_message_at"])

    op.create_table(
        "conversation_participants",
        _pk(),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unread_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True)),
        sa.Column("is_muted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("conversation_id", "user_id", name="conversation_user"),
        sa.CheckConstraint("unread_count >= 0", name="unread_non_negative"),
    )
    op.create_index("ix_conversation_participants_conversation_id", "conversation_participants", ["conversation_id"])
    op.create_index("ix_conversation_participants_user_id", "conversation_participants", ["user_id"])
    op.create_index(
        "ix_conversation_participants_user", "conversation_participants", ["user_id", "conversation_id"]
    )

    op.create_table(
        "messages",
        _pk(),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("body", sa.Text()),
        sa.Column("attachment_key", sa.String(512)),
        sa.Column("attachment_kind", sa.String(16)),
        sa.Column("shared_video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="SET NULL")),
        sa.Column("edited_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.CheckConstraint(
            "body IS NOT NULL OR attachment_key IS NOT NULL OR shared_video_id IS NOT NULL", name="has_content"
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])

    op.create_table(
        "notifications",
        _pk(),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("type", _enum("notification_type"), nullable=False),
        sa.Column("entity_type", sa.String(32)),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        _created_at(),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "is_read", "created_at"])

    # --- moderation -----------------------------------------------------------
    op.create_table(
        "reports",
        _pk(),
        sa.Column("reporter_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", _enum("report_target"), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("details", sa.Text()),
        sa.Column("status", _enum("report_status"), server_default="open", nullable=False),
        sa.Column("resolved_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_ts(),
        sa.UniqueConstraint("reporter_id", "target_type", "target_id", name="reporter_target"),
    )
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_target_type", "reports", ["target_type"])
    op.create_index("ix_reports_target_id", "reports", ["target_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_status_created", "reports", ["status", "created_at"])
    op.create_index("ix_reports_target", "reports", ["target_type", "target_id"])

    op.create_table(
        "moderation_actions",
        _pk(),
        sa.Column("moderator_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action_type", _enum("moderation_action_type"), nullable=False),
        sa.Column("target_type", _enum("moderation_target_type"), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), sa.ForeignKey("reports.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text()),
        sa.Column("notes", sa.Text()),
        _created_at(),
    )
    op.create_index("ix_moderation_actions_moderator_id", "moderation_actions", ["moderator_id"])
    op.create_index("ix_moderation_actions_action_type", "moderation_actions", ["action_type"])
    op.create_index("ix_moderation_actions_target_id", "moderation_actions", ["target_id"])
    op.create_index("ix_moderation_actions_created_at", "moderation_actions", ["created_at"])
    op.create_index("ix_moderation_actions_target", "moderation_actions", ["target_type", "target_id"])

    op.create_table(
        "audit_logs",
        _pk(),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32)),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("ip_hash", sa.String(64)),
        _created_at(),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_action_created", "audit_logs", ["action", "created_at"])

    op.create_table(
        "platform_categories",
        _pk(),
        sa.Column("slug", sa.String(48), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("kind", sa.String(24), server_default="video", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_ts(),
    )
    op.create_index("ix_platform_categories_is_active", "platform_categories", ["is_active"])

    op.create_table(
        "creator_analytics_events",
        _pk(),
        sa.Column("creator_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("dedupe_key", sa.String(96)),
        sa.Column("properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_creator_analytics_events_creator_id", "creator_analytics_events", ["creator_id"])
    op.create_index("ix_creator_analytics_events_event_type", "creator_analytics_events", ["event_type"])
    op.create_index("ix_creator_analytics_events_occurred_at", "creator_analytics_events", ["occurred_at"])
    op.create_index(
        "ix_creator_analytics_creator_event_time",
        "creator_analytics_events",
        ["creator_id", "event_type", "occurred_at"],
    )
    op.create_index(
        "uq_creator_analytics_dedupe",
        "creator_analytics_events",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )


def downgrade() -> None:
    for table in (
        "creator_analytics_events",
        "platform_categories",
        "audit_logs",
        "moderation_actions",
        "reports",
        "notifications",
        "messages",
        "conversation_participants",
        "conversations",
        "battle_events",
        "battle_results",
        "votes",
    ):
        op.drop_table(table)

    op.drop_constraint("fk_challenges_winner_entry_id_challenge_entries", "challenges", type_="foreignkey")
    op.drop_table("challenge_entries")

    for table in (
        "challenge_participants",
        "challenges",
        "share_events",
        "saved_videos",
        "comments",
        "likes",
        "blocks",
        "follows",
        "video_view_events",
        "videos",
        "media_assets",
        "email_tokens",
        "refresh_tokens",
        "user_profiles",
        "users",
    ):
        op.drop_table(table)

    for name in ENUMS:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)