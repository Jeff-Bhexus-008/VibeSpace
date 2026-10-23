"""Profiles, follows, blocks and account deletion."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, OptionalUser, PageWindow
from app.api.v1.serializers import media_url, public_user, video_items
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.pagination import InvalidCursorError
from app.core.security import clear_auth_cookies, verify_password
from app.core.ratelimit import rate_limit
from app.models.enums import NotificationType, VideoStatus
from app.models.media import MediaAsset
from app.models.social import Block, Follow
from app.models.user import User, UserProfile
from app.models.video import Video
from app.repositories.videos import page_videos, owned_or_visible
from app.schemas.common import AckResponse, Page
from app.schemas.social import FollowSuggestion
from app.schemas.user import (
    BlockCreate,
    DeleteAccountRequest,
    FollowState,
    ProfileImageUpdate,
    ProfileUpdate,
    PublicUser,
)
from app.schemas.video import VideoOut
from app.services import storage
from app.services.audit import record_audit
from app.services.notifications import create_notification

logger = logging.getLogger("vibespace.users")

router = APIRouter(tags=["users"])


def _by_username(db, username: str) -> User:
    user = db.execute(
        select(User).where(func.lower(User.username) == username.lower(), User.is_suspended.is_(False))
    ).scalar_one_or_none()
    if user is None:
        raise NotFoundError("No account with that username.")
    return user


def _blocked_between(db, first_id, second_id) -> bool:
    row = db.execute(
        select(Block.id).where(
            or_(
                (Block.blocker_id == first_id) & (Block.blocked_id == second_id),
                (Block.blocker_id == second_id) & (Block.blocked_id == first_id),
            )
        )
    ).scalar_one_or_none()
    return row is not None


def _follow_state(db, viewer: User | None, target: User) -> dict:
    if viewer is None or viewer.id == target.id:
        return {"is_following": None, "is_followed_by": None, "is_blocked": None}
    following = db.execute(
        select(Follow.id).where(Follow.follower_id == viewer.id, Follow.followee_id == target.id)
    ).scalar_one_or_none()
    followed_by = db.execute(
        select(Follow.id).where(Follow.follower_id == target.id, Follow.followee_id == viewer.id)
    ).scalar_one_or_none()
    return {
        "is_following": following is not None,
        "is_followed_by": followed_by is not None,
        "is_blocked": _blocked_between(db, viewer.id, target.id),
    }


# --- static routes first: /users/me must not be swallowed by /users/{username} ---
@router.get("/users/me/suggestions", response_model=Page[FollowSuggestion])
def follow_suggestions(viewer: CurrentUser, db: DbSession, window: PageWindow) -> Page[FollowSuggestion]:
    following = select(Follow.followee_id).where(Follow.follower_id == viewer.id)
    stmt = (
        select(User)
        .join(UserProfile, UserProfile.user_id == User.id)
        .where(
            User.id != viewer.id,
            User.is_suspended.is_(False),
            User.id.notin_(following),
            ~User.id.in_(select(Block.blocked_id).where(Block.blocker_id == viewer.id)),
        )
        .order_by(UserProfile.follower_count.desc(), UserProfile.total_likes.desc(), User.created_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars().unique())
    return Page(
        items=[
            FollowSuggestion(
                id=user.id,
                username=user.username,
                display_name=(user.profile.display_name if user.profile else None) or user.username,
                avatar_url=media_url(user.profile.avatar_key if user.profile else None),
                follower_count=user.profile.follower_count if user.profile else 0,
                total_likes=user.profile.total_likes if user.profile else 0,
            )
            for user in rows
        ],
        has_more=len(rows) == window["limit"],
    )


@router.patch("/users/me/profile", response_model=PublicUser)
def update_profile(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> PublicUser:
    profile = user.profile or UserProfile(user_id=user.id)
    db.add(profile)

    if payload.display_name is not None:
        profile.display_name = payload.display_name.strip() or user.username
    if payload.bio is not None:
        profile.bio = payload.bio.strip() or None
    if payload.location is not None:
        profile.location = payload.location.strip() or None
    if payload.links is not None:
        cleaned = []
        for link in payload.links:
            candidate = link.strip()
            if not candidate:
                continue
            if not candidate.startswith(("http://", "https://")):
                raise AppError(f"Links must start with http:// or https:// ({candidate}).")
            cleaned.append(candidate[:300])
        profile.links = cleaned
    if payload.is_private is not None:
        profile.is_private = payload.is_private
    if payload.allow_messages_from is not None:
        profile.allow_messages_from = payload.allow_messages_from
    if payload.topic_preferences is not None:
        profile.topic_preferences = [item.strip()[:40] for item in payload.topic_preferences if item.strip()]

    db.commit()
    db.refresh(profile)
    return public_user(user, viewer=user)


@router.post("/users/me/images/{kind}", response_model=PublicUser)
def set_profile_image(kind: str, payload: ProfileImageUpdate, user: CurrentUser, db: DbSession) -> PublicUser:
    if kind not in {"avatar", "cover"}:
        raise AppError("Only avatar and cover images can be set here.")

    asset = db.execute(
        select(MediaAsset).where(MediaAsset.storage_key == payload.storage_key, MediaAsset.owner_id == user.id)
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("That uploaded image belongs to another account or no longer exists.")
    if asset.kind.value != "image":
        raise AppError("That file is not an image.")
    if asset.status.value not in {"ready", "uploaded"}:
        raise AppError("That image has not finished uploading yet.")

    profile = user.profile or UserProfile(user_id=user.id)
    db.add(profile)
    if kind == "avatar":
        profile.avatar_key = asset.storage_key
    else:
        profile.cover_key = asset.storage_key
    db.commit()
    db.refresh(profile)
    return public_user(user, viewer=user)


@router.post("/users/me/delete-account", response_model=AckResponse)
def delete_account(
    payload: DeleteAccountRequest, response: Response, user: CurrentUser, db: DbSession
) -> AckResponse:
    if not payload.confirm:
        raise AppError("Confirm the deletion before continuing.")
    if not verify_password(payload.password, user.password_hash):
        raise AppError("Your password is incorrect.", status_code=status.HTTP_400_BAD_REQUEST)

    keys = [
        key
        for (key,) in db.execute(select(MediaAsset.storage_key).where(MediaAsset.owner_id == user.id)).all()
    ]
    thumbs = [
        key
        for (key,) in db.execute(
            select(MediaAsset.thumbnail_key).where(MediaAsset.owner_id == user.id, MediaAsset.thumbnail_key.is_not(None))
        ).all()
    ]
    record_audit(db, actor_id=user.id, action="account_deleted", entity_type="user", entity_id=user.id)
    user_id = user.id
    db.delete(user)
    db.commit()

    for key in keys + thumbs:
        try:
            storage.delete_object(key)
        except Exception as exc:  # pragma: no cover - storage dependent
            logger.warning("orphaned object %s after account deletion: %s", key, exc)

    clear_auth_cookies(response)
    return AckResponse(message=f"Account {user_id} and its data were deleted.")


# --- profiles -----------------------------------------------------------------
@router.get("/users/{username}", response_model=PublicUser)
def get_profile(username: str, db: DbSession, viewer: OptionalUser) -> PublicUser:
    target = _by_username(db, username)
    return public_user(target, viewer=viewer, **_follow_state(db, viewer, target))


@router.get("/users/{username}/videos", response_model=Page[VideoOut])
def user_videos(username: str, db: DbSession, viewer: OptionalUser, window: PageWindow) -> Page[VideoOut]:
    target = _by_username(db, username)
    is_self = viewer is not None and viewer.id == target.id
    filters = owned_or_visible(viewer) + [Video.owner_id == target.id]
    if not is_self:
        filters.append(Video.status == VideoStatus.ready)
    try:
        videos, next_cursor, has_more = page_videos(
            db, filters=filters, cursor=window["cursor"], limit=window["limit"], order_by_published=True
        )
    except InvalidCursorError as exc:
        raise AppError(str(exc)) from exc
    return Page(items=video_items(db, videos, viewer), next_cursor=next_cursor, has_more=has_more)


@router.get("/users/{username}/followers", response_model=Page[PublicUser])
def followers(username: str, db: DbSession, viewer: OptionalUser, window: PageWindow) -> Page[PublicUser]:
    target = _by_username(db, username)
    stmt = (
        select(User)
        .join(Follow, Follow.follower_id == User.id)
        .where(Follow.followee_id == target.id)
        .order_by(Follow.created_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars().unique())
    return Page(items=[public_user(item, viewer=viewer) for item in rows], has_more=len(rows) == window["limit"])


@router.get("/users/{username}/following", response_model=Page[PublicUser])
def following(username: str, db: DbSession, viewer: OptionalUser, window: PageWindow) -> Page[PublicUser]:
    target = _by_username(db, username)
    stmt = (
        select(User)
        .join(Follow, Follow.followee_id == User.id)
        .where(Follow.follower_id == target.id)
        .order_by(Follow.created_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars().unique())
    return Page(items=[public_user(item, viewer=viewer) for item in rows], has_more=len(rows) == window["limit"])


# --- follows ------------------------------------------------------------------
@router.post("/users/{username}/follow", response_model=FollowState)
def follow_user(username: str, user: CurrentUser, db: DbSession) -> FollowState:
    target = _by_username(db, username)
    if target.id == user.id:
        raise AppError("You cannot follow yourself.")
    if _blocked_between(db, user.id, target.id):
        raise ConflictError("This account is not available to follow.")

    existing = db.execute(
        select(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(Follow(follower_id=user.id, followee_id=target.id))
        try:
            db.execute(
                update(UserProfile)
                .where(UserProfile.user_id == target.id)
                .values(follower_count=UserProfile.follower_count + 1)
            )
            db.execute(
                update(UserProfile)
                .where(UserProfile.user_id == user.id)
                .values(following_count=UserProfile.following_count + 1)
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("You already follow this account.") from exc
        create_notification(
            db,
            user_id=target.id,
            type=NotificationType.follow,
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
        )

    db.refresh(target)
    return FollowState(following=True, follower_count=target.profile.follower_count if target.profile else 0)


@router.delete("/users/{username}/follow", response_model=FollowState)
def unfollow_user(username: str, user: CurrentUser, db: DbSession) -> FollowState:
    target = _by_username(db, username)
    result = db.execute(
        delete(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id)
    )
    if result.rowcount:
        db.execute(
            update(UserProfile)
            .where(UserProfile.user_id == target.id, UserProfile.follower_count > 0)
            .values(follower_count=UserProfile.follower_count - 1)
        )
        db.execute(
            update(UserProfile)
            .where(UserProfile.user_id == user.id, UserProfile.following_count > 0)
            .values(following_count=UserProfile.following_count - 1)
        )
    db.commit()
    db.refresh(target)
    return FollowState(following=False, follower_count=target.profile.follower_count if target.profile else 0)


# --- blocks -------------------------------------------------------------------
@router.post("/users/{username}/block", response_model=AckResponse)
def block_user(username: str, payload: BlockCreate, user: CurrentUser, db: DbSession) -> AckResponse:
    target = _by_username(db, username)
    if target.id == user.id:
        raise AppError("You cannot block yourself.")

    record_audit(
        db,
        actor_id=user.id,
        action="user_blocked",
        entity_type="user",
        entity_id=target.id,
        metadata={"reason": payload.reason or ""},
        commit=False,
    )
    existing = db.execute(
        select(Block).where(Block.blocker_id == user.id, Block.blocked_id == target.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(Block(blocker_id=user.id, blocked_id=target.id, reason=payload.reason))
        # Blocking removes any follow relationship in both directions.
        db.execute(
            delete(Follow).where(
                or_(
                    (Follow.follower_id == user.id) & (Follow.followee_id == target.id),
                    (Follow.follower_id == target.id) & (Follow.followee_id == user.id),
                )
            )
        )
    db.commit()
    return AckResponse(message="Account blocked.")


@router.delete("/users/{username}/block", response_model=AckResponse)
def unblock_user(username: str, user: CurrentUser, db: DbSession) -> AckResponse:
    target = _by_username(db, username)
    db.execute(delete(Block).where(Block.blocker_id == user.id, Block.blocked_id == target.id))
    db.commit()
    return AckResponse(message="Account unblocked.")