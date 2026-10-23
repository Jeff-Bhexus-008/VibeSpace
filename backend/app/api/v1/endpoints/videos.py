"""Video publishing: create, read, update, delete and legitimate view tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, OptionalUser, PageWindow, client_ip, hash_ip
from app.api.v1.serializers import video_items, video_out
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.core.pagination import InvalidCursorError
from app.core.ratelimit import get_redis
from app.models.enums import MediaStatus, VideoStatus, VideoVisibility
from app.models.social import Comment, Like, SavedVideo, ShareEvent
from app.models.user import User, UserProfile
from app.models.video import Video, VideoViewEvent
from app.repositories.videos import owned_or_visible, page_videos
from app.schemas.common import AckResponse, Page
from app.schemas.video import VideoCreate, VideoOut, VideoUpdate, ViewReport
from app.services import storage
from app.services.audit import record_creator_event
from app.services.uploads import require_owned_asset

router = APIRouter(prefix="/videos", tags=["videos"])

VIEW_DEDUPE_SECONDS = 1800


def _load_video(db: Session, video_id: uuid.UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise NotFoundError("That video does not exist.")
    return video


def _assert_can_view(video: Video, viewer: User | None) -> None:
    owner = viewer is not None and viewer.id == video.owner_id
    if video.is_removed and not owner and (viewer is None or viewer.role.value not in {"moderator", "admin"}):
        raise NotFoundError("That video is no longer available.")
    if video.status != VideoStatus.ready and not owner:
        raise NotFoundError("That video is still processing.")
    if video.visibility == VideoVisibility.private and not owner:
        raise PermissionDeniedError("That video is private.")
    if video.visibility == VideoVisibility.unlisted and viewer is None:
        # Unlisted videos are reachable by link but never listed; viewing is allowed.
        return


def _require_verified(user: User) -> None:
    if not user.is_email_verified:
        raise AppError(
            "Confirm your email address before publishing.",
            details={"hint": "Resend the confirmation email from Settings."},
        )


# --- static routes before /{video_id} ----------------------------------------
@router.get("/mine", response_model=Page[VideoOut])
def my_videos(
    user: CurrentUser,
    db: DbSession,
    window: PageWindow,
    status_filter: str | None = None,
    learn_only: bool = False,
) -> Page[VideoOut]:
    filters = [Video.owner_id == user.id]
    if status_filter:
        try:
            filters.append(Video.status == VideoStatus(status_filter))
        except ValueError as exc:
            raise AppError("Unknown status filter.") from exc
    if learn_only:
        filters.append(Video.is_learn_content.is_(True))
    try:
        videos, next_cursor, has_more = page_videos(
            db, filters=filters, cursor=window["cursor"], limit=window["limit"]
        )
    except InvalidCursorError as exc:
        raise AppError(str(exc)) from exc
    return Page(items=video_items(db, videos, user), next_cursor=next_cursor, has_more=has_more)


@router.get("/saved", response_model=Page[VideoOut])
def saved_videos(user: CurrentUser, db: DbSession, window: PageWindow) -> Page[VideoOut]:
    video_ids = list(
        db.execute(
            select(SavedVideo.video_id)
            .where(SavedVideo.user_id == user.id)
            .order_by(SavedVideo.created_at.desc())
            .limit(window["limit"])
        ).scalars()
    )
    filters = [Video.id.in_(video_ids)] if video_ids else [Video.id.is_(None)]
    videos, _, _ = page_videos(db, filters=filters, cursor=None, limit=window["limit"])
    return Page(items=video_items(db, videos, user), has_more=False)


# --- collection ---------------------------------------------------------------
@router.post("", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
def create_video(payload: VideoCreate, user: CurrentUser, db: DbSession) -> VideoOut:
    _require_verified(user)
    asset = require_owned_asset(db, user, payload.media_asset_id, "video")
    if asset.status != MediaStatus.ready:
        raise AppError(
            "That video has not finished processing yet.",
            details={"media_status": asset.status.value, "asset_id": str(asset.id)},
        )

    if payload.is_learn_content and payload.learn_category is None:
        raise AppError("Choose a LearnSpace category for educational content.")

    publish_now = payload.publish and payload.visibility in {VideoVisibility.public, VideoVisibility.unlisted}
    video = Video(
        owner_id=user.id,
        media_asset_id=asset.id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category,
        tags=payload.normalised_tags(),
        visibility=VideoVisibility(payload.visibility),
        status=VideoStatus.ready,
        allow_comments=payload.allow_comments,
        is_learn_content=payload.is_learn_content,
        learn_category=payload.learn_category,
        published_at=datetime.now(timezone.utc) if publish_now else None,
    )
    db.add(video)
    db.flush()

    profile = user.profile or UserProfile(user_id=user.id)
    db.add(profile)
    profile.video_count = (profile.video_count or 0) + 1

    record_creator_event(
        db,
        creator_id=user.id,
        event_type="upload",
        video_id=video.id,
        dedupe_key=None,
        properties={"learn": payload.is_learn_content},
    )
    db.commit()
    db.refresh(video)
    return video_out(video, author=user, viewer=user)


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: uuid.UUID, db: DbSession, viewer: OptionalUser) -> VideoOut:
    video = _load_video(db, video_id)
    _assert_can_view(video, viewer)

    liked = saved = None
    if viewer is not None:
        liked = (
            db.execute(
                select(Like.id).where(Like.user_id == viewer.id, Like.video_id == video.id)
            ).scalar_one_or_none()
            is not None
        )
        saved = (
            db.execute(
                select(SavedVideo.id).where(SavedVideo.user_id == viewer.id, SavedVideo.video_id == video.id)
            ).scalar_one_or_none()
            is not None
        )
    author = db.get(User, video.owner_id)
    return video_out(video, author=author, is_liked=liked, is_saved=saved, viewer=viewer)


@router.patch("/{video_id}", response_model=VideoOut)
def update_video(video_id: uuid.UUID, payload: VideoUpdate, user: CurrentUser, db: DbSession) -> VideoOut:
    video = _load_video(db, video_id)
    if video.owner_id != user.id:
        raise PermissionDeniedError("Only the creator can edit this video.")

    data = payload.model_dump(exclude_unset=True)
    if "tags" in data and data["tags"] is not None:
        seen: list[str] = []
        for tag in data.pop("tags"):
            cleaned = tag.strip().lower().lstrip("#")[:32]
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        video.tags = seen[:12]
    for field, value in data.items():
        if field == "visibility" and value is not None:
            video.visibility = VideoVisibility(value)
            if value == "public" and video.published_at is None:
                video.published_at = datetime.now(timezone.utc)
        elif field == "learn_category" and value is not None:
            video.learn_category = value
        elif value is not None:
            setattr(video, field, value)

    if video.is_learn_content and video.learn_category is None:
        raise AppError("LearnSpace videos need a category.")

    db.commit()
    db.refresh(video)
    author = db.get(User, video.owner_id)
    return video_out(video, author=author, viewer=user)


@router.delete("/{video_id}", response_model=AckResponse)
def delete_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AckResponse:
    video = _load_video(db, video_id)
    if video.owner_id != user.id and user.role.value not in {"moderator", "admin"}:
        raise PermissionDeniedError("Only the creator can delete this video.")

    asset_keys = [video.media.storage_key, video.media.thumbnail_key] if video.media else []
    db.execute(delete(Like).where(Like.video_id == video.id))
    db.execute(delete(SavedVideo).where(SavedVideo.video_id == video.id))
    db.execute(delete(Comment).where(Comment.video_id == video.id))
    if user.profile and user.id == video.owner_id:
        db.execute(
            update(UserProfile)
            .where(UserProfile.user_id == user.id, UserProfile.video_count > 0)
            .values(video_count=UserProfile.video_count - 1)
        )
    db.delete(video)
    db.commit()

    for key in filter(None, asset_keys):
        storage.delete_object(key)
    return AckResponse(message="Video deleted.")


@router.post("/{video_id}/view", response_model=ViewReport)
def record_view(
    video_id: uuid.UUID,
    request: Request,
    db: DbSession,
    viewer: OptionalUser,
    session_key: str | None = Query(default=None, max_length=64),
    watched_seconds: float | None = Query(default=None, ge=0, le=36000),
    source: str = Query(default="feed", max_length=24),
) -> ViewReport:
    """One counted view per viewer per 30 minutes — refreshing the page adds nothing."""
    video = _load_video(db, video_id)
    _assert_can_view(video, viewer)

    identity = (
        f"user:{viewer.id}"
        if viewer is not None
        else f"session:{session_key}"
        if session_key
        else f"anon:{hash_ip(client_ip(request))}"
    )
    counted = False
    try:
        redis_client = get_redis()
        counted = bool(
            redis_client.set(f"view:{video.id}:{identity}", "1", ex=VIEW_DEDUPE_SECONDS, nx=True)
        )
    except Exception:
        # Without Redis we still record the event but never inflate the unique counter.
        counted = False

    db.add(
        VideoViewEvent(
            video_id=video.id,
            viewer_id=viewer.id if viewer else None,
            session_key=session_key[:64] if session_key else None,
            watched_seconds=watched_seconds,
            source=source[:24],
            counted_as_unique=counted,
        )
    )
    db.execute(update(Video).where(Video.id == video.id).values(view_count=Video.view_count + 1))
    if counted:
        db.execute(
            update(Video).where(Video.id == video.id).values(unique_view_count=Video.unique_view_count + 1)
        )
        record_creator_event(
            db,
            creator_id=video.owner_id,
            event_type="view",
            video_id=video.id,
            dedupe_key=f"view:{video.id}:{identity}:{datetime.now(timezone.utc):%Y%m%d%H}",
        )
    db.commit()
    db.refresh(video)
    return ViewReport(watched_seconds=watched_seconds, counted=counted, view_count=video.view_count)


@router.post("/{video_id}/share", response_model=dict)
def record_share(
    video_id: uuid.UUID, db: DbSession, viewer: OptionalUser, channel: str = "link"
) -> dict:
    video = _load_video(db, video_id)
    _assert_can_view(video, viewer)
    db.add(ShareEvent(video_id=video.id, user_id=viewer.id if viewer else None, channel=channel[:24]))
    db.execute(update(Video).where(Video.id == video.id).values(share_count=Video.share_count + 1))
    record_creator_event(db, creator_id=video.owner_id, event_type="share", video_id=video.id)
    db.commit()
    db.refresh(video)
    return {"share_count": video.share_count}