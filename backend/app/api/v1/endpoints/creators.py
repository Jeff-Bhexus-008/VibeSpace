"""CreatorSpace: real metrics for a creator's own content, computed in SQL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import cast, func, or_, select
from sqlalchemy.types import Date

from app.api.deps import CurrentUser, DbSession, PageWindow
from app.api.v1.serializers import media_url
from app.models.analytics import CreatorAnalyticsEvent
from app.models.challenge import ChallengeEntry
from app.models.enums import ReportTarget, VideoStatus
from app.models.moderation import ModerationAction
from app.models.user import UserProfile
from app.models.video import Video
from app.schemas.common import Page
from app.schemas.creator import AnalyticsPoint, AnalyticsSeries, CreatorSummary, CreatorVideoRow, ModerationNotice

router = APIRouter(prefix="/creator", tags=["creator"])


def _row(video: Video) -> CreatorVideoRow:
    asset = video.media
    return CreatorVideoRow(
        id=video.id,
        title=video.title,
        status=video.status.value,
        visibility=video.visibility.value,
        thumbnail_url=media_url(asset.thumbnail_key) if asset else None,
        view_count=video.view_count,
        unique_view_count=video.unique_view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        save_count=video.save_count,
        share_count=video.share_count,
        duration_seconds=asset.duration_seconds if asset else None,
        published_at=video.published_at,
        created_at=video.created_at,
    )


@router.get("/summary", response_model=CreatorSummary)
def creator_summary(user: CurrentUser, db: DbSession) -> CreatorSummary:
    totals = db.execute(
        select(
            func.coalesce(func.sum(Video.view_count), 0),
            func.coalesce(func.sum(Video.unique_view_count), 0),
            func.coalesce(func.sum(Video.like_count), 0),
            func.coalesce(func.sum(Video.comment_count), 0),
            func.coalesce(func.sum(Video.save_count), 0),
            func.coalesce(func.sum(Video.share_count), 0),
            func.count(Video.id),
        ).where(Video.owner_id == user.id, Video.is_removed.is_(False))
    ).one()

    status_counts = dict(
        db.execute(
            select(Video.status, func.count()).where(Video.owner_id == user.id).group_by(Video.status)
        ).all()
    )
    profile = user.profile or UserProfile(user_id=user.id, follower_count=0, following_count=0, video_count=0)

    views, unique_views, likes, comments, saves, shares, video_count = (int(value or 0) for value in totals)
    interactions = likes + comments + saves
    engagement = round((interactions / unique_views) * 100, 2) if unique_views else 0.0

    return CreatorSummary(
        video_count=video_count,
        published_count=int(status_counts.get(VideoStatus.ready, 0)),
        draft_count=int(status_counts.get(VideoStatus.draft, 0)),
        processing_count=int(status_counts.get(VideoStatus.processing, 0)),
        total_views=views,
        unique_views=unique_views,
        total_likes=likes,
        total_comments=comments,
        total_saves=saves,
        total_shares=shares,
        follower_count=profile.follower_count,
        following_count=profile.following_count,
        engagement_rate=engagement,
        has_data=video_count > 0 and views > 0,
    )


@router.get("/videos", response_model=Page[CreatorVideoRow])
def creator_videos(
    user: CurrentUser,
    db: DbSession,
    window: PageWindow,
    sort: str = Query(default="recent", pattern="^(recent|views|likes|comments)$"),
) -> Page[CreatorVideoRow]:
    orderings = {
        "recent": (Video.created_at.desc(), Video.id.desc()),
        "views": (Video.view_count.desc(), Video.created_at.desc()),
        "likes": (Video.like_count.desc(), Video.created_at.desc()),
        "comments": (Video.comment_count.desc(), Video.created_at.desc()),
    }
    stmt = (
        select(Video)
        .where(Video.owner_id == user.id, Video.is_removed.is_(False))
        .order_by(*orderings[sort])
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars().unique())
    return Page(items=[_row(video) for video in rows], has_more=len(rows) == window["limit"])


@router.get("/drafts", response_model=Page[CreatorVideoRow])
def creator_drafts(user: CurrentUser, db: DbSession, window: PageWindow) -> Page[CreatorVideoRow]:
    stmt = (
        select(Video)
        .where(Video.owner_id == user.id, Video.published_at.is_(None), Video.is_removed.is_(False))
        .order_by(Video.updated_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars().unique())
    return Page(items=[_row(video) for video in rows], has_more=len(rows) == window["limit"])


@router.get("/analytics", response_model=AnalyticsSeries)
def creator_analytics(
    user: CurrentUser,
    db: DbSession,
    range_days: int = Query(default=30, ge=1, le=365),
) -> AnalyticsSeries:
    since = datetime.now(timezone.utc) - timedelta(days=range_days)
    bucket = cast(CreatorAnalyticsEvent.occurred_at, Date)
    rows = db.execute(
        select(bucket.label("day"), CreatorAnalyticsEvent.event_type, func.count())
        .where(CreatorAnalyticsEvent.creator_id == user.id, CreatorAnalyticsEvent.occurred_at >= since)
        .group_by(bucket, CreatorAnalyticsEvent.event_type)
        .order_by(bucket.asc())
    ).all()

    by_day: dict = {}
    totals: dict[str, int] = {}
    for day, event_type, total in rows:
        entry = by_day.setdefault(day, AnalyticsPoint(day=day))
        if hasattr(entry, event_type):
            setattr(entry, event_type, int(total))
        totals[event_type] = totals.get(event_type, 0) + int(total)

    points = [by_day[day] for day in sorted(by_day)]
    return AnalyticsSeries(
        range_days=range_days,
        points=points,
        totals=totals,
        has_data=bool(points),
    )


@router.get("/moderation-notices", response_model=Page[ModerationNotice])
def moderation_notices(user: CurrentUser, db: DbSession, window: PageWindow) -> Page[ModerationNotice]:
    """Moderation actions that touched this creator's content."""
    own_video_ids = select(Video.id).where(Video.owner_id == user.id)
    own_entry_ids = select(ChallengeEntry.id).where(ChallengeEntry.user_id == user.id)

    stmt = (
        select(ModerationAction)
        .where(
            or_(
                (ModerationAction.target_type == ReportTarget.video)
                & ModerationAction.target_id.in_(own_video_ids),
                (ModerationAction.target_type == ReportTarget.entry)
                & ModerationAction.target_id.in_(own_entry_ids),
                (ModerationAction.target_type == ReportTarget.user) & (ModerationAction.target_id == user.id),
            )
        )
        .order_by(ModerationAction.created_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars())

    titles: dict = {}
    video_rows = db.execute(
        select(Video.id, Video.title).where(
            Video.id.in_([row.target_id for row in rows if row.target_type == ReportTarget.video] or [None])
        )
    ).all()
    titles.update({video_id: title for video_id, title in video_rows})
    entry_rows = db.execute(
        select(ChallengeEntry.id, ChallengeEntry.title).where(
            ChallengeEntry.id.in_([row.target_id for row in rows if row.target_type == ReportTarget.entry] or [None])
        )
    ).all()
    titles.update({entry_id: title for entry_id, title in entry_rows})

    return Page(
        items=[
            ModerationNotice(
                id=row.id,
                action_type=row.action_type.value,
                target_type=row.target_type.value,
                target_id=row.target_id,
                reason=row.reason,
                notes=row.notes,
                created_at=row.created_at,
                target_title=titles.get(row.target_id),
            )
            for row in rows
        ],
        has_more=len(rows) == window["limit"],
    )