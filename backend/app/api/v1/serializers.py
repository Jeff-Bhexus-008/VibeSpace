"""Serialisation helpers.

Media URLs are resolved here so every response returns playable links without
exposing bucket names or credentials. A missing storage configuration degrades
to `null` URLs instead of failing the whole request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ServiceUnavailableError
from app.models.challenge import ChallengeEntry
from app.models.media import MediaAsset
from app.models.social import Comment
from app.models.user import User, UserProfile
from app.models.video import Video
from app.repositories.videos import followed_creator_ids, load_authors, viewer_like_map, viewer_save_map
from app.schemas.challenge import ChallengeCreator, ChallengeOut, EntryOut
from app.schemas.media import MediaAssetOut
from app.schemas.social import CommentAuthor, CommentOut
from app.schemas.user import PublicUser
from app.schemas.video import AuthorSummary, VideoOut
from app.services import storage
from app.services.voting import accepts_entries, accepts_votes


def media_url(key: str | None, *, private: bool = False) -> str | None:
    if not key:
        return None
    try:
        return storage.media_url(key, private=private)
    except ServiceUnavailableError:
        return None


def author_summary(user: User | None, profile: UserProfile | None = None) -> AuthorSummary | None:
    if user is None:
        return None
    profile = profile or user.profile
    return AuthorSummary(
        id=user.id,
        username=user.username,
        display_name=(profile.display_name if profile else None) or user.username,
        avatar_url=media_url(profile.avatar_key if profile else None),
        follower_count=profile.follower_count if profile else 0,
    )


def public_user(
    user: User,
    *,
    viewer: User | None = None,
    is_following: bool | None = None,
    is_followed_by: bool | None = None,
    is_blocked: bool | None = None,
) -> PublicUser:
    profile = user.profile
    return PublicUser(
        id=user.id,
        username=user.username,
        display_name=(profile.display_name if profile else None) or user.username,
        bio=profile.bio if profile else None,
        avatar_url=media_url(profile.avatar_key if profile else None),
        cover_url=media_url(profile.cover_key if profile else None),
        location=profile.location if profile else None,
        links=list(profile.links or []) if profile else [],
        role=user.role.value,
        follower_count=profile.follower_count if profile else 0,
        following_count=profile.following_count if profile else 0,
        video_count=profile.video_count if profile else 0,
        total_likes=profile.total_likes if profile else 0,
        is_private=bool(profile.is_private) if profile else False,
        is_following=is_following,
        is_followed_by=is_followed_by,
        is_blocked=is_blocked,
        is_self=(viewer is not None and viewer.id == user.id),
        created_at=user.created_at,
    )


def video_out(
    video: Video,
    *,
    author: User | None = None,
    is_liked: bool | None = None,
    is_saved: bool | None = None,
    viewer: User | None = None,
) -> VideoOut:
    author = author or getattr(video, "owner", None)
    asset: MediaAsset | None = video.media
    return VideoOut(
        id=video.id,
        title=video.title,
        description=video.description,
        category=video.category,
        tags=list(video.tags or []),
        visibility=video.visibility.value,
        status=video.status.value,
        is_learn_content=video.is_learn_content,
        learn_category=video.learn_category.value if video.learn_category else None,
        allow_comments=video.allow_comments,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
        save_count=video.save_count,
        share_count=video.share_count,
        duration_seconds=asset.duration_seconds if asset else None,
        thumbnail_url=media_url(asset.thumbnail_key) if asset else None,
        playback_url=media_url(asset.storage_key),
        published_at=video.published_at,
        created_at=video.created_at,
        author=author_summary(author),
        is_liked=is_liked,
        is_saved=is_saved,
        is_owner=(viewer is not None and viewer.id == video.owner_id),
    )


def video_items(db: Session, videos: list[Video], viewer: User | None) -> list[VideoOut]:
    """Serialise a page of videos with one author lookup and one like/save lookup."""
    if not videos:
        return []
    ids = [video.id for video in videos]
    authors = load_authors(db, [video.owner_id for video in videos])
    liked = viewer_like_map(db, viewer, ids)
    saved = viewer_save_map(db, viewer, ids)
    return [
        video_out(
            video,
            author=authors.get(video.owner_id),
            is_liked=video.id in liked,
            is_saved=video.id in saved,
            viewer=viewer,
        )
        for video in videos
    ]


def comment_out(comment: Comment, *, author: User | None = None, viewer: User | None = None) -> CommentOut:
    return CommentOut(
        id=comment.id,
        video_id=comment.video_id,
        parent_id=comment.parent_id,
        body=comment.body,
        like_count=comment.like_count,
        reply_count=comment.reply_count,
        is_removed=comment.is_removed,
        created_at=comment.created_at,
        author=CommentAuthor(
            id=author.id,
            username=author.username,
            display_name=(author.profile.display_name if author.profile else None) or author.username,
            avatar_url=media_url(author.profile.avatar_key if author.profile else None),
        )
        if author
        else None,
        is_owner=(viewer is not None and viewer.id == comment.author_id),
    )


def media_out(asset: MediaAsset, *, private: bool = False) -> MediaAssetOut:
    playback = None
    if asset.status.value == "ready":
        playback = media_url(asset.storage_key, private=private)
    return MediaAssetOut(
        id=asset.id,
        kind=asset.kind.value,
        status=asset.status.value,
        storage_key=asset.storage_key,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds,
        width=asset.width,
        height=asset.height,
        detected_content_type=asset.detected_content_type,
        thumbnail_url=media_url(asset.thumbnail_key),
        playback_url=playback,
        renditions=asset.renditions or [],
        processing_error=asset.processing_error,
        created_at=asset.created_at,
    )


def seconds_remaining(target: datetime | None) -> int | None:
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return max(0, int((target - datetime.now(timezone.utc)).total_seconds()))


def challenge_out(
    challenge: Challenge,
    *,
    creator: User | None = None,
    opponent: User | None = None,
    viewer: User | None = None,
    has_joined: bool | None = None,
    has_voted: bool | None = None,
    reference_key: str | None = None,
) -> ChallengeOut:
    reference = media_url(reference_key)
    return ChallengeOut(
        id=challenge.id,
        title=challenge.title,
        description=challenge.description,
        category=challenge.category.value,
        format=challenge.format.value,
        status=challenge.status.value,
        rules=challenge.rules,
        entry_requirements=challenge.entry_requirements,
        is_public=challenge.is_public,
        is_voting_enabled=challenge.is_voting_enabled,
        votes_per_voter=challenge.votes_per_voter,
        max_entries=challenge.max_entries,
        entries_per_user=challenge.entries_per_user,
        starts_at=challenge.starts_at,
        deadline_at=challenge.deadline_at,
        voting_ends_at=challenge.voting_ends_at,
        completed_at=challenge.completed_at,
        entry_count=challenge.entry_count,
        vote_count=challenge.vote_count,
        participant_count=challenge.participant_count,
        reference_media_url=reference,
        creator=challenge_creator(creator or getattr(challenge, "creator", None)),
        opponent=challenge_creator(opponent),
        winner_entry_id=challenge.winner_entry_id,
        is_owner=(viewer is not None and viewer.id == challenge.creator_id),
        has_joined=has_joined,
        has_voted=has_voted,
        accepts_entries=accepts_entries(challenge),
        accepts_votes=accepts_votes(challenge),
        seconds_remaining=seconds_remaining(challenge.deadline_at),
        created_at=challenge.created_at,
    )


def challenge_creator(user: User | None) -> ChallengeCreator | None:
    if user is None:
        return None
    profile = user.profile
    return ChallengeCreator(
        id=user.id,
        username=user.username,
        display_name=(profile.display_name if profile else None) or user.username,
        avatar_url=media_url(profile.avatar_key if profile else None),
    )


def entry_out(
    entry: ChallengeEntry, *, user: User | None = None, viewer: User | None = None, has_voted: bool | None = None
) -> EntryOut:
    asset: MediaAsset | None = entry.media
    return EntryOut(
        id=entry.id,
        challenge_id=entry.challenge_id,
        title=entry.title,
        description=entry.description,
        status=entry.status,
        vote_count=entry.vote_count,
        like_count=entry.like_count,
        comment_count=entry.comment_count,
        score=entry.score,
        submitted_at=entry.submitted_at,
        thumbnail_url=media_url(asset.thumbnail_key) if asset else None,
        playback_url=media_url(asset.storage_key) if asset else None,
        disqualification_reason=entry.disqualification_reason,
        user=challenge_creator(user or getattr(entry, "submitter", None)),
        is_owner=(viewer is not None and viewer.id == entry.user_id),
        has_voted=has_voted,
    )


def reference_keys(db: Session, assets: dict[uuid.UUID, str]) -> dict[uuid.UUID, str]:
    """Resolve reference-media keys for a page of battles in one query."""
    if not assets:
        return {}
    rows = db.execute(
        select(MediaAsset.id, MediaAsset.storage_key).where(MediaAsset.id.in_(list(assets.keys())))
    ).all()
    return {media_id: key for media_id, key in rows}