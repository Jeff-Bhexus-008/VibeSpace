"""Search, trending, feeds, categories and leaderboards — all backed by real queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, OptionalUser, PageWindow
from app.api.v1.serializers import public_user, video_items
from app.core.errors import AppError
from app.core.pagination import InvalidCursorError
from app.models.challenge import Challenge, ChallengeEntry
from app.models.enums import ChallengeCategory, ChallengeStatus, LearnCategory
from app.models.moderation import PlatformCategory
from app.models.user import User, UserProfile
from app.models.video import Video
from app.repositories.challenges import page_challenges
from app.repositories.videos import (
    followed_creator_ids,
    page_videos,
    public_filter as video_public_filter,
    search_users,
    search_videos,
)
from app.schemas.common import Page
from app.schemas.video import VideoOut
from app.services.ranking import rank_videos, ranking_explanation

router = APIRouter(tags=["discovery"])

FEED_MODES = {"for_you", "following", "new", "trending", "learn", "saved_creators"}


@router.get("/feed", response_model=Page[VideoOut])
def feed(
    db: DbSession,
    viewer: OptionalUser,
    window: PageWindow,
    mode: str = Query(default="for_you"),
    surface: str = Query(default="vibe", pattern="^(vibe|learn)$"),
    category: str | None = Query(default=None, max_length=40),
    learn_category: LearnCategory | None = Query(default=None),
    creator: str | None = Query(default=None, max_length=32),
) -> Page[VideoOut]:
    """Cursor-paginated page of videos; ranking reorders only the fetched page."""
    if mode not in FEED_MODES:
        raise AppError(f"Unknown feed mode. Choose one of: {', '.join(sorted(FEED_MODES))}.")

    filters = video_public_filter()
    if surface == "learn" or mode == "learn":
        filters.append(Video.is_learn_content.is_(True))
    if learn_category:
        filters.append(Video.learn_category == learn_category)
    if category:
        filters.append(Video.category == category)

    if mode == "following":
        if viewer is None:
            raise AppError("Sign in to see the creators you follow.")
        ids = followed_creator_ids(db, viewer)
        filters.append(Video.owner_id.in_(ids or [None]))

    if creator:
        author = db.execute(
            select(User).where(func.lower(User.username) == creator.lower())
        ).scalar_one_or_none()
        if author is None:
            raise AppError("No creator with that username.")
        filters.append(Video.owner_id == author.id)

    if mode == "trending":
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        filters.append(func.coalesce(Video.published_at, Video.created_at) >= cutoff)
        stmt = (
            select(Video)
            .where(*filters)
            .order_by(
                (
                    func.coalesce(Video.like_count, 0)
                    + func.coalesce(Video.comment_count, 0) * 2
                    + func.coalesce(Video.save_count, 0) * 2
                ).desc(),
                Video.published_at.desc().nullslast(),
            )
            .limit(window["limit"])
        )
        rows = list(db.execute(stmt).scalars().unique())
        return Page(items=video_items(db, rows, viewer), has_more=len(rows) == window["limit"])

    try:
        videos, next_cursor, has_more = page_videos(
            db,
            filters=filters,
            cursor=window["cursor"],
            limit=window["limit"],
            order_by_published=True,
        )
    except InvalidCursorError as exc:
        raise AppError(str(exc)) from exc

    ranked = rank_videos(
        videos,
        followed_creator_ids=followed_creator_ids(db, viewer),
    )
    return Page(items=video_items(db, ranked, viewer), next_cursor=next_cursor, has_more=has_more)


@router.get("/feed/ranking")
def feed_ranking() -> dict:
    """Documents the current ranking strategy so clients (and future services) can adapt."""
    return ranking_explanation()


@router.get("/discovery/trending")
def trending(db: DbSession, viewer: OptionalUser) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
    videos = list(
        db.execute(
            select(Video)
            .where(*video_public_filter(), func.coalesce(Video.published_at, Video.created_at) >= cutoff)
            .order_by((func.coalesce(Video.like_count, 0) + func.coalesce(Video.comment_count, 0)).desc())
            .limit(12)
        )
        .scalars()
        .unique()
    )
    creators = list(
        db.execute(
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(User.is_suspended.is_(False))
            .order_by(UserProfile.follower_count.desc(), UserProfile.total_likes.desc())
            .limit(8)
        )
        .scalars()
        .unique()
    )
    battles = list(
        db.execute(
            select(Challenge)
            .where(
                Challenge.is_public.is_(True),
                Challenge.status.in_([ChallengeStatus.open, ChallengeStatus.active, ChallengeStatus.voting]),
            )
            .order_by(Challenge.vote_count.desc(), Challenge.created_at.desc())
            .limit(6)
        ).scalars()
    )
    learn = list(
        db.execute(
            select(Video)
            .where(*video_public_filter(), Video.is_learn_content.is_(True))
            .order_by(Video.published_at.desc().nullslast())
            .limit(6)
        )
        .scalars()
        .unique()
    )
    return {
        "videos": [item.model_dump() for item in video_items(db, videos, viewer)],
        "creators": [public_user(user, viewer=viewer).model_dump() for user in creators],
        "battles": [
            {
                "id": str(battle.id),
                "title": battle.title,
                "category": battle.category.value,
                "format": battle.format.value,
                "status": battle.status.value,
                "entry_count": battle.entry_count,
                "vote_count": battle.vote_count,
                "deadline_at": battle.deadline_at.isoformat() if battle.deadline_at else None,
            }
            for battle in battles
        ],
        "learn": [item.model_dump() for item in video_items(db, learn, viewer)],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/search")
def search(
    db: DbSession,
    viewer: OptionalUser,
    window: PageWindow,
    q: str = Query(min_length=1, max_length=80),
    type: str = Query(default="all", pattern="^(all|users|videos|learn|challenges)$"),
    learn_category: LearnCategory | None = Query(default=None),
) -> dict:
    """PostgreSQL-backed search. Swap in a dedicated engine later without touching clients."""
    results: dict = {"query": q, "type": type}

    if type in {"all", "users"}:
        users, users_cursor, users_more = search_users(db, query=q, cursor=window["cursor"], limit=window["limit"])
        results["users"] = Page(
            items=[public_user(user, viewer=viewer) for user in users],
            next_cursor=users_cursor,
            has_more=users_more,
        ).model_dump()

    if type in {"all", "videos", "learn"}:
        learn_only = type == "learn"
        videos, next_cursor, has_more = search_videos(
            db,
            query=q,
            learn_only=learn_only,
            learn_category=learn_category,
            cursor=window["cursor"],
            limit=window["limit"],
        )
        results["videos"] = Page(
            items=video_items(db, videos, viewer), next_cursor=next_cursor, has_more=has_more
        ).model_dump()

    if type in {"all", "challenges"}:
        try:
            category = ChallengeCategory(q.lower())
        except ValueError:
            category = None
        filters = [Challenge.is_public.is_(True)]
        filters.append(
            or_(
                func.lower(Challenge.title).like(f"%{q.lower()}%"),
                func.lower(func.coalesce(Challenge.description, "")).like(f"%{q.lower()}%"),
                Challenge.category == category if category else Challenge.title.like(f"%{q}%"),
            )
        )
        battles, next_cursor, has_more = page_challenges(
            db, filters=filters, cursor=window["cursor"], limit=window["limit"]
        )
        results["challenges"] = {
            "items": [
                {
                    "id": str(battle.id),
                    "title": battle.title,
                    "category": battle.category.value,
                    "format": battle.format.value,
                    "status": battle.status.value,
                    "entry_count": battle.entry_count,
                    "vote_count": battle.vote_count,
                    "deadline_at": battle.deadline_at.isoformat() if battle.deadline_at else None,
                }
                for battle in battles
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    return results


@router.get("/categories")
def categories(db: DbSession, kind: str | None = Query(default=None, max_length=24)) -> dict:
    stmt = select(PlatformCategory).where(PlatformCategory.is_active.is_(True))
    if kind:
        stmt = stmt.where(PlatformCategory.kind == kind)
    rows = list(db.execute(stmt.order_by(PlatformCategory.sort_order.asc(), PlatformCategory.label.asc())).scalars())
    if rows:
        return {"items": [{"slug": row.slug, "label": row.label, "kind": row.kind} for row in rows]}

    # Nothing configured yet: expose the built-in catalogues so the UI is never empty.
    return {
        "items": [{"slug": name, "label": name.replace("_", " ").title(), "kind": "battle"} for name in ChallengeCategory.__members__]
        + [{"slug": name, "label": name.replace("_", " ").title(), "kind": "learn"} for name in LearnCategory.__members__],
        "note": "Built-in catalogue. Seed platform_categories to customise labels.",
    }


@router.get("/leaderboards/{scope}")
def leaderboard(
    scope: str,
    db: DbSession,
    viewer: OptionalUser,
    window: PageWindow,
) -> dict:
    """Official standings. Provisional rows are labelled as such."""
    limit = min(window["limit"], 50)

    if scope == "creators":
        rows = db.execute(
            select(User)
            .join(UserProfile, UserProfile.user_id == User.id)
            .where(User.is_suspended.is_(False))
            .order_by(UserProfile.follower_count.desc(), UserProfile.total_likes.desc())
            .limit(limit)
        ).scalars().unique()
        return {
            "scope": scope,
            "is_final": True,
            "note": "Ranked by followers, then total likes.",
            "items": [
                {
                    "rank": index + 1,
                    "creator": public_user(user, viewer=viewer).model_dump(),
                    "score": user.profile.follower_count if user.profile else 0,
                }
                for index, user in enumerate(rows)
            ],
        }

    if scope == "videos":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        rows = db.execute(
            select(Video, User)
            .join(User, User.id == Video.owner_id)
            .where(*video_public_filter(), func.coalesce(Video.published_at, Video.created_at) >= cutoff)
            .order_by(Video.like_count.desc(), Video.view_count.desc())
            .limit(limit)
        ).all()
        return {
            "scope": scope,
            "is_final": True,
            "note": "Most liked videos published in the last 7 days.",
            "items": [
                {"rank": index + 1, "video_id": str(video.id), "title": video.title, "like_count": video.like_count}
                for index, (video, _user) in enumerate(rows)
            ],
        }

    if scope == "battles":
        rows = db.execute(
            select(Challenge)
            .where(Challenge.is_public.is_(True))
            .order_by(Challenge.vote_count.desc(), Challenge.entry_count.desc())
            .limit(limit)
        ).scalars()
        return {
            "scope": scope,
            "is_final": False,
            "note": "Provisional: ranked by votes collected so far, including battles still open.",
            "items": [
                {
                    "rank": index + 1,
                    "challenge_id": str(battle.id),
                    "title": battle.title,
                    "status": battle.status.value,
                    "vote_count": battle.vote_count,
                    "entry_count": battle.entry_count,
                }
                for index, battle in enumerate(rows)
            ],
        }

    if scope == "winners":
        rows = db.execute(
            select(Challenge, ChallengeEntry)
            .join(ChallengeEntry, ChallengeEntry.id == Challenge.winner_entry_id)
            .where(Challenge.status == ChallengeStatus.completed)
            .order_by(Challenge.completed_at.desc())
            .limit(limit)
        ).all()
        return {
            "scope": scope,
            "is_final": True,
            "note": "Officially completed battles and their winning entry.",
            "items": [
                {
                    "rank": index + 1,
                    "challenge_id": str(battle.id),
                    "title": battle.title,
                    "winning_entry_id": str(entry.id),
                    "winning_entry_title": entry.title,
                    "votes": entry.vote_count,
                    "completed_at": battle.completed_at.isoformat() if battle.completed_at else None,
                }
                for index, (battle, entry) in enumerate(rows)
            ],
        }

    if scope == "participation":
        rows = db.execute(
            select(User, func.count(ChallengeEntry.id).label("entries"))
            .join(ChallengeEntry, ChallengeEntry.user_id == User.id)
            .where(User.is_suspended.is_(False))
            .group_by(User.id)
            .order_by(func.count(ChallengeEntry.id).desc())
            .limit(limit)
        ).all()
        return {
            "scope": scope,
            "is_final": True,
            "note": "Creators with the most battle entries.",
            "items": [
                {"rank": index + 1, "creator": public_user(user, viewer=viewer).model_dump(), "entries": int(entries)}
                for index, (user, entries) in enumerate(rows)
            ],
        }

    raise AppError("Unknown leaderboard. Try creators, videos, battles, winners or participation.")