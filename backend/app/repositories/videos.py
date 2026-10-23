"""Query helpers for videos, feeds and search (keeps routers thin and avoids N+1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, Text, exists, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.pagination import encode_cursor
from app.models.enums import LearnCategory, VideoStatus, VideoVisibility
from app.models.social import Follow, Like, SavedVideo
from app.models.user import User, UserProfile
from app.models.video import Video


def private_profile_filter(viewer: User | None):
    private_profile = exists(
        select(UserProfile.user_id).where(
            UserProfile.user_id == Video.owner_id,
            UserProfile.is_private.is_(True),
        )
    )
    if viewer is None:
        return ~private_profile
    if viewer.role.value in {"moderator", "admin"}:
        return True
    following = exists(
        select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followee_id == Video.owner_id)
    )
    return or_(~private_profile, Video.owner_id == viewer.id, following)


def can_view_profile_content(db: Session, owner_id: uuid.UUID, viewer: User | None) -> bool:
    if viewer is not None and (viewer.id == owner_id or viewer.role.value in {"moderator", "admin"}):
        return True
    is_private = db.execute(
        select(UserProfile.is_private).where(UserProfile.user_id == owner_id)
    ).scalar_one_or_none()
    if not is_private:
        return True
    if viewer is None:
        return False
    return (
        db.execute(
            select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followee_id == owner_id)
        ).scalar_one_or_none()
        is not None
    )


def public_filter(viewer: User | None = None) -> list:
    return [
        Video.status == VideoStatus.ready,
        Video.visibility == VideoVisibility.public,
        Video.is_removed.is_(False),
        private_profile_filter(viewer),
    ]


def owned_or_visible(viewer: User | None) -> list:
    if viewer is None:
        return public_filter()
    return [
        Video.status != VideoStatus.processing,
        or_(Video.is_removed.is_(False), Video.owner_id == viewer.id),
        or_(
            Video.visibility == VideoVisibility.public,
            Video.owner_id == viewer.id,
            Video.visibility == VideoVisibility.unlisted,
        ),
        # Only the owner may see private videos.
        or_(Video.visibility != VideoVisibility.private, Video.owner_id == viewer.id),
        private_profile_filter(viewer),
    ]


def _keyset(stmt: Select, model, cursor: tuple[datetime, uuid.UUID] | None, limit: int) -> Select:
    if cursor:
        stmt = stmt.where(tuple_(model.created_at, model.id) < tuple_(cursor[0], cursor[1]))
    return stmt.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)


def page_videos(
    db: Session,
    *,
    filters: list,
    cursor: tuple[datetime, uuid.UUID] | None,
    limit: int,
    order_by_published: bool = False,
) -> tuple[list[Video], str | None, bool]:
    model = Video
    stmt = select(model).where(*filters)
    if order_by_published:
        stmt = stmt.order_by(Video.published_at.desc().nullslast(), Video.created_at.desc())
        if cursor:
            stmt = stmt.where(
                tuple_(func.coalesce(Video.published_at, Video.created_at), Video.id)
                < tuple_(cursor[0], cursor[1])
            )
        stmt = stmt.limit(limit + 1)
    else:
        stmt = _keyset(stmt, model, cursor, limit)

    rows = list(db.execute(stmt).scalars().unique())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(items[-1].published_at or items[-1].created_at, items[-1].id)
        if has_more and items
        else None
    )
    return items, next_cursor, has_more


def videos_by_ids(db: Session, video_ids: list[uuid.UUID]) -> list[Video]:
    if not video_ids:
        return []
    rows = db.execute(select(Video).where(Video.id.in_(video_ids))).scalars().unique().all()
    by_id = {video.id: video for video in rows}
    return [by_id[video_id] for video_id in video_ids if video_id in by_id]


def viewer_like_map(db: Session, viewer: User | None, video_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if viewer is None or not video_ids:
        return set()
    rows = db.execute(
        select(Like.video_id).where(Like.user_id == viewer.id, Like.video_id.in_(video_ids))
    ).scalars()
    return set(rows)


def viewer_save_map(db: Session, viewer: User | None, video_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if viewer is None or not video_ids:
        return set()
    rows = db.execute(
        select(SavedVideo.video_id).where(SavedVideo.user_id == viewer.id, SavedVideo.video_id.in_(video_ids))
    ).scalars()
    return set(rows)


def followed_creator_ids(db: Session, viewer: User | None, limit: int = 500) -> list[uuid.UUID]:
    if viewer is None:
        return []
    from app.models.social import Follow

    rows = db.execute(
        select(Follow.followee_id).where(Follow.follower_id == viewer.id).limit(limit)
    ).scalars()
    return list(rows)


def load_authors(db: Session, owner_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not owner_ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(set(owner_ids)))).scalars().unique().all()
    return {user.id: user for user in rows}


def search_videos(
    db: Session,
    *,
    viewer: User | None,
    query: str,
    learn_only: bool,
    learn_category: LearnCategory | None,
    cursor,
    limit: int,
) -> tuple[list[Video], str | None, bool]:
    pattern = f"%{query.lower()}%"
    filters = public_filter(viewer) + [
        or_(
            func.lower(Video.title).like(pattern),
            func.lower(func.coalesce(Video.description, "")).like(pattern),
            func.lower(func.cast(Video.tags, Text)).like(pattern),
        )
    ]
    if learn_only:
        filters.append(Video.is_learn_content.is_(True))
    if learn_category:
        filters.append(Video.learn_category == learn_category)
    return page_videos(db, filters=filters, cursor=cursor, limit=limit, order_by_published=True)


def search_users(
    db: Session, *, query: str, viewer: User | None, cursor, limit: int
) -> tuple[list[User], str | None, bool]:
    pattern = f"%{query.lower()}%"
    profile_visible = UserProfile.is_private.is_not(True)
    if viewer is not None:
        profile_visible = or_(
            profile_visible,
            User.id == viewer.id,
            exists(
                select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followee_id == User.id)
            ),
        )
    stmt = (
        select(User)
        .join(UserProfile, UserProfile.user_id == User.id, isouter=True)
        .where(
            User.is_suspended.is_(False),
            profile_visible,
            or_(
                func.lower(User.username).like(pattern),
                func.lower(func.coalesce(UserProfile.display_name, "")).like(pattern),
                func.lower(func.coalesce(UserProfile.bio, "")).like(pattern),
            ),
        )
    )
    if cursor:
        stmt = stmt.where(tuple_(User.created_at, User.id) < tuple_(cursor[0], cursor[1]))
    stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
    rows = list(db.execute(stmt).scalars().unique())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return items, next_cursor, has_more