"""Battle voting: eligibility, duplicate prevention, flagging, tallying and finalisation."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.models.challenge import BattleEvent, BattleResult, Challenge, ChallengeEntry, ChallengeParticipant, Vote
from app.models.enums import ChallengeStatus, EntryStatus, ParticipantRole
from app.models.user import User

logger = logging.getLogger("vibespace.voting")

ALLOWED_TRANSITIONS: dict[ChallengeStatus, set[ChallengeStatus]] = {
    ChallengeStatus.draft: {ChallengeStatus.scheduled, ChallengeStatus.open, ChallengeStatus.cancelled},
    ChallengeStatus.scheduled: {ChallengeStatus.open, ChallengeStatus.cancelled},
    ChallengeStatus.open: {ChallengeStatus.active, ChallengeStatus.voting, ChallengeStatus.cancelled},
    ChallengeStatus.active: {ChallengeStatus.voting, ChallengeStatus.cancelled},
    ChallengeStatus.voting: {ChallengeStatus.completed},
    ChallengeStatus.completed: set(),
    ChallengeStatus.cancelled: set(),
}

VOTING_STATES = {ChallengeStatus.voting, ChallengeStatus.active}


def allowed_next_states(challenge: Challenge) -> list[ChallengeStatus]:
    return sorted(ALLOWED_TRANSITIONS.get(challenge.status, set()), key=lambda state: state.value)


def validate_transition(challenge: Challenge, new_status: ChallengeStatus) -> None:
    if new_status == challenge.status:
        return
    if new_status not in ALLOWED_TRANSITIONS.get(challenge.status, set()):
        raise AppError(
            f"A battle in '{challenge.status.value}' cannot move to '{new_status.value}'.",
            details={"allowed": [state.value for state in allowed_next_states(challenge)]},
        )
    if challenge.status == ChallengeStatus.completed:
        raise AppError("Completed battles are frozen: results can no longer change.")


def accepts_entries(challenge: Challenge, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if challenge.status not in {ChallengeStatus.open, ChallengeStatus.active}:
        return False
    if challenge.deadline_at and _aware(challenge.deadline_at) <= now:
        return False
    if challenge.starts_at and _aware(challenge.starts_at) > now:
        return False
    return True


def accepts_votes(challenge: Challenge, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if not challenge.is_voting_enabled:
        return False
    if challenge.status not in VOTING_STATES and challenge.status != ChallengeStatus.open:
        return False
    if challenge.voting_ends_at and _aware(challenge.voting_ends_at) <= now:
        return False
    return True


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def cast_vote(
    db: Session,
    challenge: Challenge,
    voter: User,
    *,
    entry_id: uuid.UUID | None,
    weight: int = 1,
    voter_ip_hash: str | None = None,
) -> Vote:
    now = datetime.now(timezone.utc)

    if challenge.status == ChallengeStatus.completed:
        raise AppError("Voting has closed and the results are final.")
    if not accepts_votes(challenge, now):
        raise AppError("Voting is not open for this battle right now.")
    if challenge.creator_id == voter.id:
        raise ConflictError("The battle organiser cannot vote in their own battle.")

    participant = db.execute(
        select(ChallengeParticipant).where(
            ChallengeParticipant.challenge_id == challenge.id, ChallengeParticipant.user_id == voter.id
        )
    ).scalar_one_or_none()

    if participant is None:
        # Open ballots are allowed, but joining keeps the participation count honest.
        db.add(
            ChallengeParticipant(
                challenge_id=challenge.id,
                user_id=voter.id,
                role=ParticipantRole.joined,
                accepted_at=now,
            )
        )
        challenge.participant_count = (challenge.participant_count or 0) + 1

    entry: ChallengeEntry | None = None
    if entry_id is not None:
        entry = db.get(ChallengeEntry, entry_id)
        if entry is None or entry.challenge_id != challenge.id:
            raise NotFoundError("That entry is not part of this battle.")
        if entry.status == EntryStatus.disqualified:
            raise ConflictError("Disqualified entries cannot receive votes.")
        if entry.user_id == voter.id:
            raise ConflictError("You cannot vote for your own entry.")

    existing = db.execute(
        select(Vote).where(
            Vote.challenge_id == challenge.id,
            Vote.voter_id == voter.id,
            Vote.entry_id == entry_id if entry_id is not None else Vote.entry_id.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("You have already voted here.")

    if challenge.votes_per_voter == 1:
        cast_count = db.execute(
            select(func.count()).select_from(Vote).where(Vote.challenge_id == challenge.id, Vote.voter_id == voter.id)
        ).scalar_one()
        if entry_id is not None and challenge.format.value == "head_to_head" and cast_count >= 1:
            raise ConflictError("This is a single-vote battle: you have already chosen a side.")

    vote = Vote(
        challenge_id=challenge.id,
        entry_id=entry_id,
        voter_id=voter.id,
        weight=weight,
        voter_ip_hash=voter_ip_hash,
    )
    db.add(vote)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("This vote was already recorded.") from exc

    challenge.vote_count = (challenge.vote_count or 0) + 1
    if entry is not None:
        entry.vote_count = (entry.vote_count or 0) + weight

    db.add(
        BattleEvent(
            challenge_id=challenge.id,
            actor_id=voter.id,
            event_type="vote_cast",
            payload={"entry_id": str(entry_id) if entry_id else None, "weight": weight},
        )
    )
    db.commit()
    db.refresh(vote)

    _maybe_flag_vote_burst(db, challenge, voter)
    return vote


def _maybe_flag_vote_burst(db: Session, challenge: Challenge, voter: User, window_minutes: int = 10) -> None:
    """Cheap anomaly signal: one voter hammering many battles in a short window."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    recent = db.execute(
        select(func.count()).select_from(Vote).where(Vote.voter_id == voter.id, Vote.created_at >= since)
    ).scalar_one()
    if recent >= 25:
        db.execute(
            update(Vote)
            .where(Vote.voter_id == voter.id, Vote.created_at >= since)
            .values(is_flagged=True, flag_reason=f"{recent} votes in {window_minutes} minutes")
        )
        db.commit()
        logger.warning("flagged burst voting: voter=%s count=%s", voter.id, recent)


def compute_standings(
    db: Session, challenge: Challenge, *, final: bool = False, decided_by: uuid.UUID | None = None
) -> list[BattleResult]:
    """Official tally — always recomputed from the votes table, never from client input."""
    rows = db.execute(
        select(
            ChallengeEntry.id,
            ChallengeEntry.vote_count,
            ChallengeEntry.like_count,
            ChallengeEntry.comment_count,
            ChallengeEntry.status,
        ).where(ChallengeEntry.challenge_id == challenge.id)
    ).all()

    scored: list[tuple[uuid.UUID, int, float, EntryStatus]] = []
    for entry_id, vote_count, like_count, comment_count, status in rows:
        if status == EntryStatus.disqualified:
            continue
        votes = int(vote_count or 0)
        score = round(float(votes) * 1.0 + float(like_count or 0) * 0.25 + float(comment_count or 0) * 0.35, 4)
        scored.append((entry_id, votes, score, status))

    scored.sort(key=lambda row: (row[2], row[1]), reverse=True)

    db.execute(
        BattleResult.__table__.delete().where(
            BattleResult.challenge_id == challenge.id, BattleResult.is_final == final
        )
    )
    results: list[BattleResult] = []
    for rank, (entry_id, votes, score, _status) in enumerate(scored, start=1):
        result = BattleResult(
            challenge_id=challenge.id,
            entry_id=entry_id,
            rank=rank,
            vote_count=votes,
            final_score=score,
            is_final=final,
            decided_by=decided_by if final else None,
        )
        db.add(result)
        results.append(result)

    if final:
        challenge.winner_entry_id = scored[0][0] if scored else None
        challenge.status = ChallengeStatus.completed
        challenge.completed_at = datetime.now(timezone.utc)
        db.add(
            BattleEvent(
                challenge_id=challenge.id,
                actor_id=decided_by,
                event_type="results_finalised",
                payload={"entries": len(scored)},
            )
        )
    db.commit()
    return results


def finalize_battle(db: Session, challenge: Challenge, moderator: User) -> list[BattleResult]:
    if challenge.status == ChallengeStatus.completed and challenge.winner_entry_id:
        raise ConflictError("Results for this battle are already final.")
    if challenge.status not in {ChallengeStatus.voting, ChallengeStatus.active}:
        raise AppError("Only battles in voting can be finalised.")
    return compute_standings(db, challenge, final=True, decided_by=moderator.id)


def detect_suspicious_votes(db: Session, *, challenge_id: uuid.UUID | None = None, window_minutes: int = 15):
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    stmt = select(Vote.voter_id, func.count().label("total")).where(Vote.created_at >= since)
    if challenge_id:
        stmt = stmt.where(Vote.challenge_id == challenge_id)
    stmt = stmt.group_by(Vote.voter_id).having(func.count() >= 10).order_by(func.count().desc()).limit(50)

    anomalies = []
    for voter_id, total in db.execute(stmt).all():
        entries = db.execute(
            select(func.count(func.distinct(Vote.entry_id))).where(
                Vote.voter_id == voter_id, Vote.created_at >= since
            )
        ).scalar_one()
        anomalies.append(
            {
                "voter_id": voter_id,
                "entry_id": None,
                "votes_in_window": int(total),
                "window_minutes": window_minutes,
                "reason": f"{total} votes across {entries} entries in {window_minutes} minutes",
                "flagged": True,
            }
        )
    return anomalies


def voter_ip_hash(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"{ip}:{settings.secret_key}".encode()).hexdigest()[:64]


def eligibility_summary(db: Session, challenge: Challenge, user: User | None) -> dict:
    now = datetime.now(timezone.utc)
    summary = {
        "accepts_entries": accepts_entries(challenge, now),
        "accepts_votes": accepts_votes(challenge, now),
        "has_joined": False,
        "has_voted": False,
    }
    if user is None:
        return summary
    summary["has_joined"] = (
        db.execute(
            select(ChallengeParticipant.id).where(
                ChallengeParticipant.challenge_id == challenge.id, ChallengeParticipant.user_id == user.id
            )
        ).scalar_one_or_none()
        is not None
    )
    summary["has_voted"] = (
        db.execute(
            select(Vote.id).where(Vote.challenge_id == challenge.id, Vote.voter_id == user.id).limit(1)
        ).scalar_one_or_none()
        is not None
    )
    return summary


def ensure_can_manage(challenge: Challenge, user: User, *, role_at_least_moderator: bool = False) -> None:
    if challenge.creator_id == user.id or user.role.value == "admin" or (role_at_least_moderator and user.role.value == "moderator"):
        return
    raise PermissionDeniedError("Only the battle organiser can do that.")