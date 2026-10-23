"""Battle entries, fair voting, official results and disputes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, ModeratorUser, OptionalUser, PageWindow, client_ip
from app.api.v1.battles_common import (
    load_challenge,
    require_verified,
    serialize_challenges,
    serialize_entries,
)
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.ratelimit import rate_limit
from app.models.challenge import BattleEvent, BattleResult, Challenge, ChallengeEntry, ChallengeParticipant, Vote
from app.models.enums import (
    EntryStatus,
    ModerationActionType,
    NotificationType,
    ParticipantRole,
    ReportTarget,
)
from app.models.moderation import ModerationAction, Report
from app.models.user import User
from app.repositories.challenges import entries_for, load_users
from app.schemas.challenge import (
    DisputeRequest,
    EntryCreate,
    EntryOut,
    ResultRow,
    StandingsResponse,
    VoteCreate,
    VoteOut,
)
from app.schemas.common import AckResponse, Page
from app.services import voting
from app.services.audit import record_audit, record_battle_event
from app.services.notifications import create_notification
from app.services.uploads import require_owned_asset

router = APIRouter(prefix="/challenges", tags=["battles"])

vote_limit = rate_limit("vote", 120, 60)


# --- entries ------------------------------------------------------------------
@router.post("/{challenge_id}/entries", response_model=EntryOut, status_code=status.HTTP_201_CREATED)
def submit_entry(
    challenge_id: uuid.UUID, payload: EntryCreate, user: CurrentUser, db: DbSession
) -> EntryOut:
    require_verified(user)
    challenge = load_challenge(db, challenge_id)
    if not voting.accepts_entries(challenge):
        raise ConflictError("Entries are closed for this battle.")

    asset = require_owned_asset(db, user, payload.media_asset_id, "video")
    if asset.status.value != "ready":
        raise AppError("That video is still processing. Try again shortly.")

    submitted = db.execute(
        select(func.count())
        .select_from(ChallengeEntry)
        .where(
            ChallengeEntry.challenge_id == challenge.id,
            ChallengeEntry.user_id == user.id,
            ChallengeEntry.status != EntryStatus.withdrawn,
        )
    ).scalar_one()
    if submitted >= challenge.entries_per_user:
        raise ConflictError(f"You can submit {challenge.entries_per_user} entry(ies) to this battle.")
    if challenge.max_entries and challenge.entry_count >= challenge.max_entries:
        raise ConflictError("This battle has reached its entry limit.")

    entry = ChallengeEntry(
        challenge_id=challenge.id,
        user_id=user.id,
        media_asset_id=asset.id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        status=EntryStatus.submitted,
    )
    db.add(entry)
    challenge.entry_count += 1

    participant = db.execute(
        select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge.id,
            ChallengeParticipant.user_id == user.id,
        )
    ).scalar_one_or_none()
    if participant is None:
        db.add(
            ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=user.id,
                role=ParticipantRole.joined,
                accepted_at=datetime.now(timezone.utc),
            )
        )
        challenge.participant_count += 1
    elif participant.accepted_at is None:
        participant.accepted_at = datetime.now(timezone.utc)
        participant.role = ParticipantRole.joined

    # The first entry moves an open battle into its active phase.
    if challenge.status.value == "open":
        challenge.status = voting.ChallengeStatus.active

    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="entry_submitted",
        payload={"title": entry.title},
    )
    db.commit()
    db.refresh(entry)

    if challenge.creator_id != user.id:
        create_notification(
            db,
            user_id=challenge.creator_id,
            type=NotificationType.battle_entry,
            actor_id=user.id,
            entity_type="challenge",
            entity_id=challenge.id,
            payload={"title": challenge.title, "entry_title": entry.title},
        )
    return serialize_entries(db, [entry], user)[0]


@router.get("/{challenge_id}/entries", response_model=Page[EntryOut])
def list_entries(
    challenge_id: uuid.UUID, db: DbSession, viewer: OptionalUser, window: PageWindow
) -> Page[EntryOut]:
    challenge = load_challenge(db, challenge_id)
    if not challenge.is_public and (viewer is None or viewer.id != challenge.creator_id):
        if not _viewer_joined(db, challenge, viewer):
            raise PermissionDeniedError("This battle is private.")

    entries = entries_for(db, challenge.id, limit=window["limit"])
    return Page(items=serialize_entries(db, entries, viewer), has_more=len(entries) == window["limit"])


def _viewer_joined(db: Session, challenge: Challenge, viewer: User | None) -> bool:
    if viewer is None:
        return False
    return (
        db.execute(
            select(ChallengeParticipant.id).where(
                ChallengeParticipant.challenge_id == challenge.id,
                ChallengeParticipant.user_id == viewer.id,
            )
        ).scalar_one_or_none()
        is not None
    )


@router.delete("/{challenge_id}/entries/{entry_id}", response_model=AckResponse)
def withdraw_entry(
    challenge_id: uuid.UUID, entry_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> AckResponse:
    challenge = load_challenge(db, challenge_id)
    entry = db.get(ChallengeEntry, entry_id)
    if entry is None or entry.challenge_id != challenge.id:
        raise NotFoundError("That entry is not part of this battle.")

    is_staff = user.role.value in {"moderator", "admin"}
    if entry.user_id != user.id and challenge.creator_id != user.id and not is_staff:
        raise PermissionDeniedError("Only the entrant or a moderator can remove this entry.")
    if challenge.status.value == "completed":
        raise ConflictError("Completed battles are frozen.")

    entry.status = EntryStatus.withdrawn
    challenge.entry_count = max(challenge.entry_count - 1, 0)
    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="entry_withdrawn",
        payload={"entry_id": str(entry.id)},
    )
    db.commit()
    return AckResponse(message="Entry withdrawn.")


@router.post("/{challenge_id}/entries/{entry_id}/disqualify", response_model=EntryOut)
def disqualify_entry(
    challenge_id: uuid.UUID, entry_id: uuid.UUID, reason: str, user: ModeratorUser, db: DbSession
) -> EntryOut:
    """Moderators remove unfair entries; the action is audited and the entrant is told why."""
    challenge = load_challenge(db, challenge_id)
    entry = db.get(ChallengeEntry, entry_id)
    if entry is None or entry.challenge_id != challenge.id:
        raise NotFoundError("That entry is not part of this battle.")

    entry.status = EntryStatus.disqualified
    entry.disqualification_reason = reason[:500]
    db.add(
        ModerationAction(
            moderator_id=user.id,
            action_type=ModerationActionType.entry_disqualified,
            target_type=ReportTarget.entry,
            target_id=entry.id,
            reason=reason[:500],
        )
    )
    record_audit(
        db,
        actor_id=user.id,
        action="entry_disqualified",
        entity_type="entry",
        entity_id=entry.id,
        metadata={"challenge_id": str(challenge.id), "reason": reason[:200]},
        commit=False,
    )
    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="entry_disqualified",
        payload={"entry_id": str(entry.id)},
    )
    db.commit()
    db.refresh(entry)

    create_notification(
        db,
        user_id=entry.user_id,
        type=NotificationType.moderation,
        actor_id=user.id,
        entity_type="entry",
        entity_id=entry.id,
        payload={"reason": reason[:200], "challenge_id": str(challenge.id)},
    )
    return serialize_entries(db, [entry], user)[0]


# --- voting -------------------------------------------------------------------
def _record_vote(
    db: Session,
    challenge: Challenge,
    user: User,
    *,
    entry_id: uuid.UUID | None,
    weight: int,
    request: Request,
) -> Vote:
    vote = voting.cast_vote(
        db,
        challenge,
        user,
        entry_id=entry_id,
        weight=weight,
        voter_ip_hash=voting.voter_ip_hash(client_ip(request)),
    )
    db.refresh(challenge)
    if challenge.vote_count in {10, 50, 100, 500} and challenge.creator_id != user.id:
        create_notification(
            db,
            user_id=challenge.creator_id,
            type=NotificationType.battle_vote_milestone,
            actor_id=None,
            entity_type="challenge",
            entity_id=challenge.id,
            payload={"title": challenge.title, "vote_count": challenge.vote_count},
        )
    return vote


@router.post("/{challenge_id}/vote", response_model=VoteOut, dependencies=[Depends(vote_limit)])
def cast_battle_vote(
    challenge_id: uuid.UUID,
    payload: VoteCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> VoteOut:
    """Head-to-head ballots omit entry_id (one vote per challenge); entry votes include it."""
    challenge = load_challenge(db, challenge_id)
    vote = _record_vote(
        db, challenge, user, entry_id=payload.entry_id, weight=payload.weight, request=request
    )
    return VoteOut.model_validate(vote)


@router.post(
    "/{challenge_id}/entries/{entry_id}/vote", response_model=VoteOut, dependencies=[Depends(vote_limit)]
)
def vote_for_entry(
    challenge_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    weight: int = Query(default=1, ge=1, le=5),
) -> VoteOut:
    challenge = load_challenge(db, challenge_id)
    vote = _record_vote(db, challenge, user, entry_id=entry_id, weight=weight, request=request)
    return VoteOut.model_validate(vote)


@router.get("/{challenge_id}/votes", response_model=Page[VoteOut])
def my_votes(challenge_id: uuid.UUID, db: DbSession, user: CurrentUser, window: PageWindow) -> Page[VoteOut]:
    challenge = load_challenge(db, challenge_id)
    rows = list(
        db.execute(
            select(Vote)
            .where(Vote.challenge_id == challenge.id, Vote.voter_id == user.id)
            .order_by(Vote.created_at.desc())
            .limit(window["limit"])
        ).scalars()
    )
    return Page(items=[VoteOut.model_validate(row) for row in rows], has_more=len(rows) == window["limit"])


# --- results ------------------------------------------------------------------
@router.get("/{challenge_id}/standings", response_model=StandingsResponse)
def standings(challenge_id: uuid.UUID, db: DbSession, viewer: OptionalUser) -> StandingsResponse:
    challenge = load_challenge(db, challenge_id)

    final_rows = list(
        db.execute(
            select(BattleResult, ChallengeEntry, User)
            .join(ChallengeEntry, ChallengeEntry.id == BattleResult.entry_id)
            .join(User, User.id == ChallengeEntry.user_id)
            .where(BattleResult.challenge_id == challenge.id, BattleResult.is_final.is_(True))
            .order_by(BattleResult.rank.asc())
        ).all()
    )
    if final_rows:
        return StandingsResponse(
            challenge_id=challenge.id,
            is_final=True,
            computed_at=final_rows[0][0].computed_at,
            rows=[
                ResultRow(
                    entry_id=result.entry_id,
                    title=entry.title,
                    rank=result.rank,
                    vote_count=result.vote_count,
                    final_score=result.final_score,
                    is_final=True,
                    username=member.username,
                )
                for result, entry, member in final_rows
            ],
            note="Official result — voting is closed.",
        )

    entries = entries_for(db, challenge.id, include_disqualified=False)
    rows = [
        ResultRow(
            entry_id=entry.id,
            title=entry.title,
            rank=index + 1,
            vote_count=entry.vote_count,
            final_score=round(entry.vote_count + entry.like_count * 0.25, 4),
            is_final=False,
        )
        for index, entry in enumerate(entries)
    ]
    note = (
        "Provisional standings based on votes cast so far."
        if rows
        else "No entries yet, so there is nothing to rank."
    )
    return StandingsResponse(challenge_id=challenge.id, is_final=False, rows=rows, note=note)


@router.post("/{challenge_id}/finalize", response_model=StandingsResponse)
def finalize_challenge(challenge_id: uuid.UUID, user: ModeratorUser, db: DbSession) -> StandingsResponse:
    """Publishes official results from the votes table — client totals are never trusted."""
    challenge = load_challenge(db, challenge_id)
    results = voting.finalize_battle(db, challenge, user)
    db.refresh(challenge)

    entries = {
        entry.id: entry
        for entry in db.execute(select(ChallengeEntry).where(ChallengeEntry.challenge_id == challenge.id))
        .scalars()
        .unique()
    }
    for entry in entries.values():
        if entry.user_id == user.id:
            continue
        create_notification(
            db,
            user_id=entry.user_id,
            type=NotificationType.battle_result,
            actor_id=None,
            entity_type="challenge",
            entity_id=challenge.id,
            payload={
                "title": challenge.title,
                "rank": next((result.rank for result in results if result.entry_id == entry.id), None),
                "won": challenge.winner_entry_id == entry.id,
            },
        )
    record_audit(
        db,
        actor_id=user.id,
        action="battle_results_finalised",
        entity_type="challenge",
        entity_id=challenge.id,
        metadata={"entries": len(results)},
    )

    return StandingsResponse(
        challenge_id=challenge.id,
        is_final=True,
        computed_at=datetime.now(timezone.utc),
        rows=[
            ResultRow(
                entry_id=result.entry_id,
                title=entries[result.entry_id].title if result.entry_id in entries else "Entry",
                rank=result.rank,
                vote_count=result.vote_count,
                final_score=result.final_score,
                is_final=True,
            )
            for result in results
        ],
        note="Official result — voting is closed.",
    )


@router.get("/{challenge_id}/events")
def battle_history(challenge_id: uuid.UUID, db: DbSession, user: CurrentUser, window: PageWindow) -> dict:
    """Battle history, visible to the organiser, moderators and admins."""
    challenge = load_challenge(db, challenge_id)
    voting.ensure_can_manage(challenge, user, role_at_least_moderator=True)
    rows = list(
        db.execute(
            select(BattleEvent)
            .where(BattleEvent.challenge_id == challenge.id)
            .order_by(BattleEvent.created_at.desc())
            .limit(window["limit"])
        ).scalars()
    )
    return {
        "items": [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "payload": event.payload,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in rows
        ]
    }


@router.post("/{challenge_id}/disputes", response_model=AckResponse, status_code=status.HTTP_201_CREATED)
def dispute_battle(
    challenge_id: uuid.UUID, payload: DisputeRequest, user: CurrentUser, db: DbSession
) -> AckResponse:
    challenge = load_challenge(db, challenge_id)
    existing = db.execute(
        select(Report.id).where(
            Report.reporter_id == user.id,
            Report.target_type == ReportTarget.challenge,
            Report.target_id == challenge.id,
        )
    ).scalar_one_or_none()
    if existing:
        return AckResponse(message="Your dispute is already with the moderation team.")

    db.add(
        Report(
            reporter_id=user.id,
            target_type=ReportTarget.challenge,
            target_id=challenge.id,
            reason="battle_dispute",
            details=f"{payload.reason}: {payload.details}"[:1000],
        )
    )
    record_battle_event(
        db,
        challenge_id=challenge.id,
        actor_id=user.id,
        event_type="dispute_opened",
        payload={"reason": payload.reason},
    )
    db.commit()
    return AckResponse(message="Dispute submitted. A moderator will review this battle.")


__all__ = ["router", "serialize_challenges", "load_users"]