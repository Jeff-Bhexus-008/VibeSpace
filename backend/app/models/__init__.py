"""Import every model so SQLAlchemy metadata (and Alembic) sees all tables."""

from app.models.analytics import CreatorAnalyticsEvent
from app.models.auth_tokens import EmailToken, RefreshToken
from app.models.challenge import (
    BattleEvent,
    BattleResult,
    Challenge,
    ChallengeEntry,
    ChallengeParticipant,
    Vote,
)
from app.models.media import MediaAsset
from app.models.messaging import (
    Conversation,
    ConversationParticipant,
    Message,
    Notification,
)
from app.models.moderation import AuditLog, ModerationAction, PlatformCategory, Report
from app.models.social import Block, Comment, Follow, Like, SavedVideo, ShareEvent
from app.models.user import User, UserProfile
from app.models.video import Video, VideoViewEvent

__all__ = [
    "AuditLog",
    "BattleEvent",
    "BattleResult",
    "Block",
    "Challenge",
    "ChallengeEntry",
    "ChallengeParticipant",
    "Comment",
    "Conversation",
    "ConversationParticipant",
    "CreatorAnalyticsEvent",
    "EmailToken",
    "Follow",
    "Like",
    "MediaAsset",
    "Message",
    "ModerationAction",
    "Notification",
    "PlatformCategory",
    "RefreshToken",
    "Report",
    "SavedVideo",
    "ShareEvent",
    "User",
    "UserProfile",
    "Video",
    "VideoViewEvent",
    "Vote",
]