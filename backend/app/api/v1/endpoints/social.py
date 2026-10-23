"""Likes, comments, saves, shares and reports."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, OptionalUser, PageWindow
from app.api.v1.serializers import comment_out, video_out
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.models.enums import NotificationType, ReportTarget
from app.models.social import Block, Comment, Like, Report, SavedVideo
from app.models.user import User
from app.models.video import Video
from app.schemas.common import AckResponse, Page
from app.schemas.social import (
    CommentCreate,
    CommentOut,
    CommentUpdate,
    LikeState,
    ReportCreate,
    SaveRequest,
    SaveState,
)
from app.services.audit import record_audit, record_creator_event
from app.services.notifications import create_notification

router = APIRouter(tags=["social"])


def _video(db, video_id: uuid.UUID) -> Video:
    video = db.get(Video, video_id)
    if video is None or video.is_removed:
        raise NotFoundError("That video is not available.")
    return video


def _comment(db, comment_id: uuid.UUID) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("That comment does not exist.")
    return comment


def _blocked_pair(db, first_id, second_id) -> bool:
    return (
        db.execute(
            select(Block.id).where(
                ((Block.blocker_id == first_id) & (Block.blocked_id == second_id))
                | ((Block.blocker_id == second_id) & (Block.blocked_id == first_id))
            )
        ).scalar_one_or_none()
        is not None
    )


# --- likes --------------------------------------------------------------------
@router.post("/videos/{video_id}/like", response_model=LikeState)
def like_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> LikeState:
    video = _video(db, video_id)
    exists = db.execute(
        select(Like.id).where(Like.user_id == user.id, Like.video_id == video.id)
    ).scalar_one_or_none()
    if exists is None:
        db.add(Like(user_id=user.id, video_id=video.id))
        try:
            db.execute(update(Video).where(Video.id == video.id).values(like_count=Video.like_count + 1))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("You already liked this video.") from exc
        record_creator_event(db, creator_id=video.owner_id, event_type="like", video_id=video.id)
        db.commit()
        if video.owner_id != user.id:
            create_notification(
                db,
                user_id=video.owner_id,
                type=NotificationType.like,
                actor_id=user.id,
                entity_type="video",
                entity_id=video.id,
                payload={"title": video.title},
            )
    db.refresh(video)
    return LikeState(liked=True, like_count=video.like_count)


@router.delete("/videos/{video_id}/like", response_model=LikeState)
def unlike_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> LikeState:
    video = _video(db, video_id)
    result = db.execute(delete(Like).where(Like.user_id == user.id, Like.video_id == video.id))
    if result.rowcount:
        db.execute(
            update(Video)
            .where(Video.id == video.id, Video.like_count > 0)
            .values(like_count=Video.like_count - 1)
        )
    db.commit()
    db.refresh(video)
    return LikeState(liked=False, like_count=video.like_count)


# --- comments -----------------------------------------------------------------
@router.get("/videos/{video_id}/comments", response_model=Page[CommentOut])
def list_comments(
    video_id: uuid.UUID,
    db: DbSession,
    viewer: OptionalUser,
    window: PageWindow,
    include_replies: bool = False,
) -> Page[CommentOut]:
    video = _video(db, video_id)
    stmt = select(Comment, User).join(User, User.id == Comment.author_id).where(Comment.video_id == video.id)
    if not include_replies:
        stmt = stmt.where(Comment.parent_id.is_(None))
    stmt = stmt.order_by(Comment.created_at.desc()).limit(window["limit"])
    rows = db.execute(stmt).all()
    return Page(
        items=[comment_out(comment, author=author, viewer=viewer) for comment, author in rows],
        has_more=len(rows) == window["limit"],
    )


@router.post("/videos/{video_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(video_id: uuid.UUID, payload: CommentCreate, user: CurrentUser, db: DbSession) -> CommentOut:
    video = _video(db, video_id)
    if not video.allow_comments:
        raise AppError("Comments are turned off for this video.")

    parent = None
    if payload.parent_id is not None:
        parent = _comment(db, payload.parent_id)
        if parent.video_id != video.id:
            raise AppError("That comment belongs to a different video.")
        if parent.is_removed:
            raise AppError("You cannot reply to a removed comment.")
        if _blocked_pair(db, user.id, parent.author_id):
            raise PermissionDeniedError("You cannot reply to this account.")

    comment = Comment(
        video_id=video.id,
        author_id=user.id,
        parent_id=parent.id if parent else None,
        body=payload.body.strip(),
    )
    db.add(comment)
    db.execute(update(Video).where(Video.id == video.id).values(comment_count=Video.comment_count + 1))
    if parent is not None:
        db.execute(
            update(Comment).where(Comment.id == parent.id).values(reply_count=Comment.reply_count + 1)
        )
    db.commit()
    db.refresh(comment)

    record_creator_event(db, creator_id=video.owner_id, event_type="comment", video_id=video.id)
    db.commit()

    notify_user = parent.author_id if parent is not None else video.owner_id
    if notify_user != user.id:
        create_notification(
            db,
            user_id=notify_user,
            type=NotificationType.reply if parent else NotificationType.comment,
            actor_id=user.id,
            entity_type="video",
            entity_id=video.id,
            payload={"title": video.title, "excerpt": comment.body[:140], "comment_id": str(comment.id)},
        )
    return comment_out(comment, author=user, viewer=user)


@router.get("/comments/{comment_id}/replies", response_model=Page[CommentOut])
def list_replies(
    comment_id: uuid.UUID, db: DbSession, viewer: OptionalUser, window: PageWindow
) -> Page[CommentOut]:
    parent = _comment(db, comment_id)
    stmt = (
        select(Comment, User)
        .join(User, User.id == Comment.author_id)
        .where(Comment.parent_id == parent.id)
        .order_by(Comment.created_at.asc())
        .limit(window["limit"])
    )
    rows = db.execute(stmt).all()
    return Page(
        items=[comment_out(comment, author=author, viewer=viewer) for comment, author in rows],
        has_more=len(rows) == window["limit"],
    )


@router.patch("/comments/{comment_id}", response_model=CommentOut)
def update_comment(comment_id: uuid.UUID, payload: CommentUpdate, user: CurrentUser, db: DbSession) -> CommentOut:
    comment = _comment(db, comment_id)
    if comment.author_id != user.id:
        raise PermissionDeniedError("You can only edit your own comments.")
    comment.body = payload.body.strip()
    db.commit()
    db.refresh(comment)
    return comment_out(comment, author=user, viewer=user)


@router.delete("/comments/{comment_id}", response_model=AckResponse)
def delete_comment(comment_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AckResponse:
    comment = _comment(db, comment_id)
    is_staff = user.role.value in {"moderator", "admin"}
    if comment.author_id != user.id and not is_staff:
        raise PermissionDeniedError("You can only delete your own comments.")

    replies = db.execute(
        select(func.count()).select_from(Comment).where(Comment.parent_id == comment.id)
    ).scalar_one()
    db.execute(delete(Comment).where(Comment.parent_id == comment.id))
    db.execute(delete(Comment).where(Comment.id == comment.id))
    db.execute(
        update(Video)
        .where(Video.id == comment.video_id)
        .values(comment_count=func.greatest(Video.comment_count - 1 - replies, 0))
    )
    if comment.parent_id:
        db.execute(
            update(Comment)
            .where(Comment.id == comment.parent_id, Comment.reply_count > 0)
            .values(reply_count=Comment.reply_count - 1)
        )
    if is_staff and comment.author_id != user.id:
        record_audit(
            db,
            actor_id=user.id,
            action="comment_removed",
            entity_type="comment",
            entity_id=comment.id,
            metadata={"reason": "moderator action"},
            commit=False,
        )
    db.commit()
    return AckResponse(message="Comment deleted.")


# --- saves --------------------------------------------------------------------
@router.post("/videos/{video_id}/save", response_model=SaveState)
def save_video(video_id: uuid.UUID, payload: SaveRequest, user: CurrentUser, db: DbSession) -> SaveState:
    video = _video(db, video_id)
    existing = db.execute(
        select(SavedVideo).where(SavedVideo.user_id == user.id, SavedVideo.video_id == video.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(SavedVideo(user_id=user.id, video_id=video.id, collection=payload.collection.strip() or "Watch later"))
        try:
            db.execute(update(Video).where(Video.id == video.id).values(save_count=Video.save_count + 1))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("This video is already saved.") from exc
        record_creator_event(db, creator_id=video.owner_id, event_type="save", video_id=video.id)
        db.commit()
    db.refresh(video)
    return SaveState(saved=True, save_count=video.save_count, collection=payload.collection)


@router.delete("/videos/{video_id}/save", response_model=SaveState)
def unsave_video(video_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SaveState:
    video = _video(db, video_id)
    result = db.execute(delete(SavedVideo).where(SavedVideo.user_id == user.id, SavedVideo.video_id == video.id))
    if result.rowcount:
        db.execute(
            update(Video)
            .where(Video.id == video.id, Video.save_count > 0)
            .values(save_count=Video.save_count - 1)
        )
    db.commit()
    db.refresh(video)
    return SaveState(saved=False, save_count=video.save_count)


# --- reports ------------------------------------------------------------------
@router.post("/reports", response_model=AckResponse, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, user: CurrentUser, db: DbSession) -> AckResponse:
    target_id = payload.target_id
    if payload.target_type != "user" and db.get(
        {"video": Video, "comment": Comment, "message": None}.get(payload.target_type, Video), target_id
    ) is None and payload.target_type in {"video", "comment"}:
        raise NotFoundError("That content no longer exists.")

    existing = db.execute(
        select(Report.id).where(
            Report.reporter_id == user.id,
            Report.target_type == ReportTarget(payload.target_type),
            Report.target_id == target_id,
        )
    ).scalar_one_or_none()
    if existing:
        return AckResponse(message="We already have your report for this content.")

    db.add(
        Report(
            reporter_id=user.id,
            target_type=ReportTarget(payload.target_type),
            target_id=target_id,
            reason=payload.reason,
            details=payload.details,
        )
    )
    record_audit(
        db,
        actor_id=user.id,
        action="report_created",
        entity_type=payload.target_type,
        entity_id=target_id,
        metadata={"reason": payload.reason},
        commit=False,
    )
    db.commit()
    return AckResponse(message="Thanks — our moderators will review this report.")