"""Query helpers for battles, entries, votes and their related media."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.core.pagination import encode_cursor
from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant, Vote
from app.models.enums import ChallengeStatus, EntryStatus
from app.models.media import MediaAsset
from app.models.user import User


def page_challenges(
    db: Session,
    *,
    filters: list,
    cursor: tuple[datetime, uuid.UUID] | None,
    limit: int,
    newest_first: bool = True,
) -> tuple[list[Challenge], str | None, bool]:
    stmt: Select = select(Challenge).where(*filters)
    if cursor:
        comparator = (
            tuple_(Challenge.created_at, Challenge.id) < tuple_(cursor[0], cursor[1])
            if newest_first
            else tuple_(Challenge.created_at, Challenge.id) > tuple_(cursor[0], cursor[1])
        )
        stmt = stmt.where(comparator)
    order = (
        (Challenge.created_at.desc(), Challenge.id.desc())
        if newest_first
        else (Challenge.created_at.asc(), Challenge.id.asc())
    )
    stmt = stmt.order_by(*order).limit(limit + 1)
    rows = list(db.execute(stmt).scalars().unique())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more and items else None
    return items, next_cursor, has_more


def public_filter() -> list:
    terminal = (ChallengeStatus.completed, ChallengeStatus.cancelled)
    return [
        Challenge.is_public.is_(True),
        Challenge.status.notin_(terminal),
    ]


def load_users(db: Session, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    ids = {user_id for user_id in user_ids if user_id}
    if not ids:
        return {}
    rows = db.execute(select(User).where(User.id.in_(ids))).scalars().unique().all()
    return {user.id: user for user in rows}


def reference_media_keys(db: Session, challenges: list[Challenge]) -> dict[uuid.UUID, str]:
    asset_ids = {challenge.reference_media_id for challenge in challenges if challenge.reference_media_id}
    if not asset_ids:
        return {}
    rows = db.execute(
        select(MediaAsset.id, MediaAsset.storage_key).where(MediaAsset.id.in_(asset_ids))
    ).all()
    return {media_id: key for media_id, key in rows}


def entries_for(
    db: Session,
    challenge_id: uuid.UUID,
    *,
    include_disqualified: bool = True,
    limit: int = 200,
) -> list[ChallengeEntry]:
    stmt = select(ChallengeEntry).where(ChallengeEntry.challenge_id == challenge_id)
    if not include_disqualified:
        stmt = stmt.where(ChallengeEntry.status != EntryStatus.disqualified)
    stmt = stmt.order_by(ChallengeEntry.vote_count.desc(), ChallengeEntry.submitted_at.asc()).limit(limit)
    return list(db.execute(stmt).scalars().unique())


def viewer_entry_votes(db: Session, challenge_id: uuid.UUID, voter_id: uuid.UUID) -> set[uuid.UUID]:
    rows = db.execute(
        select(Vote.entry_id).where(
            Vote.challenge_id == challenge_id, Vote.voter_id == voter_id, Vote.entry_id.is_not(None)
        )
    ).scalars()
    return {entry_id for entry_id in rows if entry_id}


def viewer_challenge_votes(db: Session, voter_id: uuid.UUID, challenge_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not challenge_ids:
        return set()
    rows = db.execute(
        select(Vote.challenge_id).where(Vote.voter_id == voter_id, Vote.challenge_id.in_(challenge_ids))
    ).scalars()
    return set(rows)


def joined_challenge_ids(db: Session, user_id: uuid.UUID, challenge_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not challenge_ids:
        return set()
    rows = db.execute(
        select(ChallengeParticipant.challenge_id).where(
            ChallengeParticipant.user_id == user_id, ChallengeParticipant.challenge_id.in_(challenge_ids)
        )
    ).scalars()
    return set(rows)


def participants_with_users(
    db: Session, challenge_id: uuid.UUID, limit: int = 100
) -> list[tuple[ChallengeParticipant, User]]:
    stmt = (
        select(ChallengeParticipant, User)
        .join(User, User.id == ChallengeParticipant.user_id)
        .where(ChallengeParticipant.challenge_id == challenge_id)
        .order_by(ChallengeParticipant.created_at.asc())
        .limit(limit)
    )
    return [(participant, user) for participant, user in db.execute(stmt).all()]


def entry_counts(db: Session, challenge_id: uuid.UUID) -> dict[str, int]:
    rows = db.execute(
        select(ChallengeEntry.status, func.count())
        .where(ChallengeEntry.challenge_id == challenge_id)
        .group_by(ChallengeEntry.status)
    ).all()
    return {status.value: int(total) for status, total in rows}