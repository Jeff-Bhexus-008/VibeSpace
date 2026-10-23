"""Helpers shared by the two battle routers (lifecycle and entries/voting)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.serializers import challenge_out, entry_out
from app.core.errors import AppError, NotFoundError
from app.models.challenge import Challenge, ChallengeEntry, ChallengeParticipant
from app.models.user import User
from app.repositories.challenges import (
    joined_challenge_ids,
    load_users,
    reference_media_keys,
    viewer_challenge_votes,
    viewer_entry_votes,
)
from app.schemas.challenge import ChallengeOut, EntryOut


def load_challenge(db: Session, challenge_id: uuid.UUID) -> Challenge:
    challenge = db.get(Challenge, challenge_id)
    if challenge is None:
        raise NotFoundError("That battle does not exist.")
    return challenge


def require_verified(user: User) -> None:
    if not user.is_email_verified:
        raise AppError("Confirm your email address before taking part in battles.")


def is_member(db: Session, challenge: Challenge, viewer: User | None) -> bool:
    if viewer is None:
        return False
    if viewer.id == challenge.creator_id:
        return True
    return (
        db.execute(
            select(ChallengeParticipant.id).where(
                ChallengeParticipant.challenge_id == challenge.id,
                ChallengeParticipant.user_id == viewer.id,
            )
        ).scalar_one_or_none()
        is not None
    )


def serialize_challenges(
    db: Session, challenges: list[Challenge], viewer: User | None
) -> list[ChallengeOut]:
    if not challenges:
        return []
    authors = load_users(
        db, [item.creator_id for item in challenges] + [item.opponent_id for item in challenges]
    )
    keys = reference_media_keys(db, challenges)
    ids = [item.id for item in challenges]
    joined = joined_challenge_ids(db, viewer.id, ids) if viewer else set()
    voted = viewer_challenge_votes(db, viewer.id, ids) if viewer else set()
    return [
        challenge_out(
            challenge,
            creator=authors.get(challenge.creator_id),
            opponent=authors.get(challenge.opponent_id) if challenge.opponent_id else None,
            viewer=viewer,
            has_joined=challenge.id in joined,
            has_voted=challenge.id in voted,
            reference_key=keys.get(challenge.reference_media_id),
        )
        for challenge in challenges
    ]


def serialize_entries(
    db: Session, entries: list[ChallengeEntry], viewer: User | None
) -> list[EntryOut]:
    if not entries:
        return []
    submitters = load_users(db, [entry.user_id for entry in entries])
    voted: set[uuid.UUID] = set()
    if viewer is not None:
        voted = viewer_entry_votes(db, entries[0].challenge_id, viewer.id)
    return [
        entry_out(
            entry,
            user=submitters.get(entry.user_id),
            viewer=viewer,
            has_voted=entry.id in voted if viewer else None,
        )
        for entry in entries
    ]