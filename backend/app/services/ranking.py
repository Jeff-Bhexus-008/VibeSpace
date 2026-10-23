"""Feed ranking — deliberately modular so a smarter recommender can replace it.

Score = engagement + recency + creator affinity + discoverability, all from
columns we already index. Nothing here depends on a third-party service.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.models.video import Video

HALF_LIFE_HOURS = 36.0
FOLLOW_BOOST = 0.4
LEARN_BOOST = 0.1


def _age_hours(published_at: datetime | None) -> float:
    if published_at is None:
        return 72.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - published_at).total_seconds() / 3600.0)


def engagement_score(video: Video) -> float:
    likes = video.like_count or 0
    comments = video.comment_count or 0
    saves = video.save_count or 0
    shares = video.share_count or 0
    views = max(video.unique_view_count or video.view_count or 0, 1)
    interactions = likes * 1.0 + comments * 2.0 + saves * 2.5 + shares * 3.0
    # Interaction *rate* matters more than raw totals, with a logarithmic volume bonus.
    return (interactions / views) * math.log10(views + 10)


def score_video(video: Video, *, followed_creator_ids: Iterable = (), now: datetime | None = None) -> float:
    age = _age_hours(video.published_at)
    recency = 0.5 ** (age / HALF_LIFE_HOURS)
    affinity = FOLLOW_BOOST if video.owner_id in set(followed_creator_ids) else 0.0
    learn = LEARN_BOOST if video.is_learn_content else 0.0
    return round(engagement_score(video) + recency + affinity + learn, 6)


def rank_videos(
    videos: list[Video], *, followed_creator_ids: Iterable = (), limit: int | None = None
) -> list[Video]:
    """In-memory ranking of one already-paginated page (never the whole table)."""
    followed = set(followed_creator_ids)
    ranked = sorted(videos, key=lambda video: score_video(video, followed_creator_ids=followed), reverse=True)
    return ranked[:limit] if limit else ranked


def trending_since(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def ranking_explanation() -> dict:
    return {
        "strategy": "engagement_recency_affinity",
        "half_life_hours": HALF_LIFE_HOURS,
        "signals": ["like_count", "comment_count", "save_count", "share_count", "unique_view_count", "published_at", "followed_creators"],
        "extensible": True,
    }