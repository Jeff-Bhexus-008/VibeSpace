"""Immutable audit trails: admin actions, battle events and creator analytics."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.analytics import CreatorAnalyticsEvent
from app.models.challenge import BattleEvent
from app.models.moderation import AuditLog


def record_audit(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    ip_hash: str | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=metadata or {},
        ip_hash=ip_hash,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry


def record_battle_event(
    db: Session,
    *,
    challenge_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    commit: bool = False,
) -> BattleEvent:
    event = BattleEvent(
        challenge_id=challenge_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload or {},
    )
    db.add(event)
    if commit:
        db.commit()
    return event


def record_creator_event(
    db: Session,
    *,
    creator_id: uuid.UUID | None,
    event_type: str,
    video_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Analytics rows are best-effort: a failure must never break the user action."""
    if creator_id is None:
        return
    try:
        db.add(
            CreatorAnalyticsEvent(
                creator_id=creator_id,
                video_id=video_id,
                event_type=event_type,
                dedupe_key=dedupe_key,
                properties=properties or {},
            )
        )
    except Exception:  # pragma: no cover - defensive
        db.rollback()