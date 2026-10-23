"""Vibe Battle lifecycle: create, browse, update, state transitions, participants."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, status
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession, OptionalUser, PageWindow
from app.api.v1.battles_common import (
    is_member,
    load_challenge,
    require_verified,
    serialize_challenges,
)
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.pagination import InvalidCursorError
from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant
from app.models.enums import (
    ChallengeCategory,
    ChallengeFormat,
    ChallengeStatus,
    NotificationType,
    ParticipantRole,
)
from app.models.user import User
from app.repositories.challenges import page_challenges, participants_with_users
from app.schemas.challenge import (
    BattleStateChange,
    ChallengeCreate,
    ChallengeOut,
    ChallengeUpdate,
    ParticipantOut,
    StateChangeResponse,
)
from app.schemas.common import AckResponse, Page
from app.services import voting
from app.services.audit import record_battle_event
from app.services.notifications import create_notification
from app.services.uploads import require_owned_asset

router = APIRouter(prefix="/challenges", tags=["battles"])


@router.post("", response_model=ChallengeOut, status_code=status.HTTP_201_CREATED)
def create_challenge(payload: ChallengeCreate, user: CurrentUser, db: DbSession) -> ChallengeOut:
    require_verified(user)

    opponent: User | None = None
    if payload.opponent_username:
        opponent = db.execute(
            select(User).where(func.lower(User.username) == payload.opponent_username.lower())
        ).scalar_one_or_none()
        if opponent is None:
            raise NotFoundError("No account with that username to challenge.")
        if opponent.id == user.id:
            raise AppError("You cannot challenge yourself.")
        if payload.format != ChallengeFormat.head_to_head:
            raise AppError("An opponent can only be set for a head-to-head battle.")

    if payload.reference_media_id:
        require_owned_asset(db, user, payload.reference_media_id)

    now = datetime.now(timezone.utc)
    challenge = Challenge(
        creator_id=user.id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category,
        format=payload.format,
        status=ChallengeStatus.draft,
        rules=payload.rules,
        entry_requirements=payload.entry_requirements,
        is_public=payload.is_public,
        is_voting_enabled=payload.is_voting_enabled,
        votes_per_voter=payload.votes_per_voter,
        max_entries=payload.max_entries,
        entries_per_user=payload.entries_per_user,
        reference_media_id=payload.reference_media_id,
        opponent_id=opponent.id if opponent else None,
        starts_at=payload.starts_at,
        deadline_at=payload.deadline_at,
        voting_ends_at=payload.voting_ends_at,
    )
    db.add(challenge)
    db.flush()

    db.add(
        ChallengeParticipant(
            challenge_id=challenge.id, user_id=user.id, role=ParticipantRole.host, accepted_at=now
        )
    )
    challenge.participant_count = 1

    if opponent is not None:
        db.add(
            ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=opponent.id,
                role=ParticipantRole.invited,
                invited_by=user.id,
            )
        )
        challenge.participant_count += 1

    if payload.publish:
        target = (
            ChallengeStatus.scheduled
            if payload.starts_at and payload.starts_at > now
            else ChallengeStatus.open
        )
        voting.validate_transition(challenge, target)
        challenge.status = target

    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="challenge_created",
        payload={"format": payload.format.value, "published": payload.publish},
    )
    db.commit()
    db.refresh(challenge)

    if opponent is not None:
        create_notification(
            db,
            user_id=opponent.id,
            type=NotificationType.battle_invite,
            actor_id=user.id,
            entity_type="challenge",
            entity_id=challenge.id,
            payload={"title": challenge.title, "category": challenge.category.value},
        )
    return serialize_challenges(db, [challenge], user)[0]


@router.get("", response_model=Page[ChallengeOut])
def list_challenges(
    db: DbSession,
    viewer: OptionalUser,
    window: PageWindow,
    status_filter: ChallengeStatus | None = Query(default=None, alias="status"),
    category: ChallengeCategory | None = Query(default=None),
    format_filter: ChallengeFormat | None = Query(default=None, alias="format"),
    mine: bool = False,
    participating: bool = False,
    include_private: bool = False,
) -> Page[ChallengeOut]:
    filters: list = []
    if mine:
        if viewer is None:
            raise AppError("Sign in to see your battles.")
        filters.append(Challenge.creator_id == viewer.id)
    elif participating:
        if viewer is None:
            raise AppError("Sign in to see the battles you joined.")
        filters.append(
            Challenge.id.in_(
                select(ChallengeParticipant.challenge_id).where(
                    ChallengeParticipant.user_id == viewer.id
                )
            )
        )
    elif not include_private:
        filters.append(Challenge.is_public.is_(True))

    if status_filter:
        filters.append(Challenge.status == status_filter)
    if category:
        filters.append(Challenge.category == category)
    if format_filter:
        filters.append(Challenge.format == format_filter)

    try:
        rows, next_cursor, has_more = page_challenges(
            db, filters=filters, cursor=window["cursor"], limit=window["limit"]
        )
    except InvalidCursorError as exc:
        raise AppError(str(exc)) from exc
    return Page(items=serialize_challenges(db, rows, viewer), next_cursor=next_cursor, has_more=has_more)


@router.get("/mine/invitations", response_model=Page[ChallengeOut])
def my_invitations(db: DbSession, user: CurrentUser, window: PageWindow) -> Page[ChallengeOut]:
    filters = [
        Challenge.status.notin_([ChallengeStatus.draft, ChallengeStatus.cancelled]),
        Challenge.id.in_(
            select(ChallengeParticipant.challenge_id).where(
                ChallengeParticipant.user_id == user.id,
                ParticipantRole.invited == ChallengeParticipant.role,
            )
        ),
    ]
    rows, next_cursor, has_more = page_challenges(
        db, filters=filters, cursor=window["cursor"], limit=window["limit"]
    )
    return Page(items=serialize_challenges(db, rows, user), next_cursor=next_cursor, has_more=has_more)


@router.get("/{challenge_id}", response_model=ChallengeOut)
def get_challenge(challenge_id: uuid.UUID, db: DbSession, viewer: OptionalUser) -> ChallengeOut:
    challenge = load_challenge(db, challenge_id)
    if not challenge.is_public and not is_member(db, challenge, viewer):
        raise PermissionDeniedError("This battle is private.")
    return serialize_challenges(db, [challenge], viewer)[0]


@router.patch("/{challenge_id}", response_model=ChallengeOut)
def update_challenge(
    challenge_id: uuid.UUID, payload: ChallengeUpdate, user: CurrentUser, db: DbSession
) -> ChallengeOut:
    challenge = load_challenge(db, challenge_id)
    voting.ensure_can_manage(challenge, user)
    if challenge.status in {ChallengeStatus.completed, ChallengeStatus.cancelled}:
        raise ConflictError("Finished battles can no longer be edited.")
    if challenge.status == ChallengeStatus.voting and payload.deadline_at is not None:
        raise ConflictError("The deadline cannot change once voting has started.")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(challenge, field, value)
    if challenge.deadline_at and challenge.starts_at and challenge.deadline_at <= challenge.starts_at:
        raise AppError("The deadline must be after the start time.")

    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="challenge_updated",
        payload={"fields": sorted(data.keys())},
    )
    db.commit()
    db.refresh(challenge)
    return serialize_challenges(db, [challenge], user)[0]


@router.post("/{challenge_id}/state", response_model=StateChangeResponse)
def change_state(
    challenge_id: uuid.UUID, payload: BattleStateChange, user: CurrentUser, db: DbSession
) -> StateChangeResponse:
    challenge = load_challenge(db, challenge_id)
    voting.ensure_can_manage(challenge, user, role_at_least_moderator=True)

    try:
        target = ChallengeStatus(payload.status)
    except ValueError as exc:
        raise AppError("Unknown battle state.") from exc

    if target == ChallengeStatus.completed:
        raise AppError("Close a battle through the finalise step so official results are published.")
    if target == ChallengeStatus.scheduled and challenge.starts_at is None:
        raise AppError("Set a start time before scheduling this battle.")

    voting.validate_transition(challenge, target)
    previous = challenge.status
    challenge.status = target
    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="state_changed",
        payload={"from": previous.value, "to": target.value, "note": payload.note or ""},
    )
    db.commit()
    db.refresh(challenge)
    return StateChangeResponse(
        challenge=serialize_challenges(db, [challenge], user)[0],
        allowed_next=voting.allowed_next_states(challenge),
    )


@router.post("/{challenge_id}/invite", response_model=AckResponse)
def invite_participant(
    challenge_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    username: str = Query(min_length=3, max_length=32),
) -> AckResponse:
    challenge = load_challenge(db, challenge_id)
    voting.ensure_can_manage(challenge, user)
    if challenge.status in {ChallengeStatus.completed, ChallengeStatus.cancelled}:
        raise ConflictError("This battle is finished.")

    invitee = db.execute(
        select(User).where(func.lower(User.username) == username.lower(), User.is_suspended.is_(False))
    ).scalar_one_or_none()
    if invitee is None:
        raise NotFoundError("No account with that username.")
    if invitee.id == user.id:
        raise AppError("You are already the organiser of this battle.")

    existing = db.execute(
        select(ChallengeParticipant.id).where(
            ChallengeParticipant.challenge_id == challenge.id,
            ChallengeParticipant.user_id == invitee.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("That account has already been invited or joined.")

    db.add(
        ChallengeParticipant(
            challenge_id=challenge.id,
            user_id=invitee.id,
            role=ParticipantRole.invited,
            invited_by=user.id,
        )
    )
    challenge.participant_count += 1
    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="participant_invited",
        payload={"user_id": str(invitee.id)},
    )
    db.commit()

    create_notification(
        db,
        user_id=invitee.id,
        type=NotificationType.battle_invite,
        actor_id=user.id,
        entity_type="challenge",
        entity_id=challenge.id,
        payload={"title": challenge.title, "category": challenge.category.value},
    )
    return AckResponse(message=f"Invitation sent to {invitee.username}.")


@router.post("/{challenge_id}/join", response_model=AckResponse)
def join_challenge(challenge_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AckResponse:
    require_verified(user)
    challenge = load_challenge(db, challenge_id)
    if challenge.status in {ChallengeStatus.draft, ChallengeStatus.completed, ChallengeStatus.cancelled}:
        raise ConflictError("This battle is not open for participants.")
    if challenge.format == ChallengeFormat.head_to_head and challenge.opponent_id not in {None, user.id}:
        raise ConflictError("This head-to-head battle is between two invited creators.")

    existing = db.execute(
        select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge.id,
            ChallengeParticipant.user_id == user.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.accepted_at is None:
            existing.accepted_at = datetime.now(timezone.utc)
            existing.role = ParticipantRole.joined
            record_battle_event(
                db, challenge_id=challenge.id, actor_id=user.id, event_type="invitation_accepted", payload={}
            )
            db.commit()
            return AckResponse(message="Invitation accepted.")
        return AckResponse(message="You are already taking part in this battle.")

    db.add(
        ChallengeParticipant(
            challenge_id=challenge.id,
            user_id=user.id,
            role=ParticipantRole.joined,
            accepted_at=datetime.now(timezone.utc),
        )
    )
    challenge.participant_count += 1
    record_battle_event(
        db, challenge_id=challenge.id, actor_id=user.id, event_type="participant_joined", payload={}
    )
    db.commit()

    if challenge.creator_id != user.id:
        create_notification(
            db,
            user_id=challenge.creator_id,
            type=NotificationType.battle_entry,
            actor_id=user.id,
            entity_type="challenge",
            entity_id=challenge.id,
            payload={"title": challenge.title, "joined": True},
        )
    return AckResponse(message="You joined this battle.")


@router.delete("/{challenge_id}/join", response_model=AckResponse)
def leave_challenge(challenge_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AckResponse:
    challenge = load_challenge(db, challenge_id)
    if challenge.creator_id == user.id:
        raise AppError("The organiser cannot leave their own battle. Cancel it instead.")

    entries = db.execute(
        select(func.count())
        .select_from(ChallengeEntry)
        .where(ChallengeEntry.challenge_id == challenge.id, ChallengeEntry.user_id == user.id)
    ).scalar_one()
    if entries:
        raise ConflictError("Withdraw your entries before leaving this battle.")

    result = db.execute(
        delete(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge.id,
            ChallengeParticipant.user_id == user.id,
        )
    )
    if result.rowcount:
        challenge.participant_count = max(challenge.participant_count - 1, 0)
        record_battle_event(
            db, challenge_id=challenge.id, actor_id=user.id, event_type="participant_left", payload={}
        )
    db.commit()
    return AckResponse(message="You left this battle.")


@router.get("/{challenge_id}/participants", response_model=Page[ParticipantOut])
def list_participants(
    challenge_id: uuid.UUID, db: DbSession, viewer: OptionalUser, window: PageWindow
) -> Page[ParticipantOut]:
    challenge = load_challenge(db, challenge_id)
    if not challenge.is_public and not is_member(db, challenge, viewer):
        raise PermissionDeniedError("This battle is private.")

    rows = participants_with_users(db, challenge.id, limit=window["limit"])
    return Page(
        items=[
            ParticipantOut(
                id=participant.id,
                user_id=participant.user_id,
                role=participant.role,
                accepted_at=participant.accepted_at,
                created_at=participant.created_at,
                user={
                    "id": member.id,
                    "username": member.username,
                    "display_name": (member.profile.display_name if member.profile else None)
                    or member.username,
                    "avatar_url": None,
                },
            )
            for participant, member in rows
        ],
        has_more=len(rows) == window["limit"],
    )