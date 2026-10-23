"""Moderation: reports queue, content actions, suspensions, anomaly review."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.api.deps import DbSession, ModeratorUser, PageWindow
from app.api.v1.serializers import public_user
from app.core.errors import AppError, NotFoundError
from app.models.auth_tokens import RefreshToken
from app.models.challenge import Challenge, ChallengeEntry
from app.models.enums import (
    EntryStatus,
    ModerationActionType,
    NotificationType,
    ReportStatus,
    ReportTarget,
)
from app.models.moderation import AuditLog, ModerationAction, Report
from app.models.social import Comment
from app.models.user import User
from app.models.video import Video
from app.schemas.common import AckResponse, Page
from app.schemas.moderation import (
    ContentActionRequest,
    ModerationActionOut,
    ReportOut,
    ResolveReportRequest,
    SuspiciousVotingResponse,
    SuspendUserRequest,
)
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.voting import detect_suspicious_votes

router = APIRouter(prefix="/moderation", tags=["moderation"])


def _target_preview(db: DbSession, report: Report) -> dict | None:
    if report.target_type == ReportTarget.video:
        video = db.get(Video, report.target_id)
        if video:
            return {"kind": "video", "id": str(video.id), "title": video.title, "owner_id": str(video.owner_id)}
    elif report.target_type == ReportTarget.comment:
        comment = db.get(Comment, report.target_id)
        if comment:
            return {"kind": "comment", "id": str(comment.id), "body": comment.body[:280]}
    elif report.target_type == ReportTarget.user:
        user = db.get(User, report.target_id)
        if user:
            return {"kind": "user", "id": str(user.id), "username": user.username}
    elif report.target_type == ReportTarget.challenge:
        challenge = db.get(Challenge, report.target_id)
        if challenge:
            return {"kind": "challenge", "id": str(challenge.id), "title": challenge.title}
    elif report.target_type == ReportTarget.entry:
        entry = db.get(ChallengeEntry, report.target_id)
        if entry:
            return {"kind": "entry", "id": str(entry.id), "title": entry.title, "challenge_id": str(entry.challenge_id)}
    return None


def _report_out(db: DbSession, report: Report, reporter: User | None) -> ReportOut:
    return ReportOut(
        id=report.id,
        target_type=report.target_type.value,
        target_id=report.target_id,
        reason=report.reason,
        details=report.details,
        status=report.status.value,
        resolution_note=report.resolution_note,
        resolved_at=report.resolved_at,
        created_at=report.created_at,
        reporter=public_user(reporter) if reporter else None,
        target_preview=_target_preview(db, report),
    )


@router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    db: DbSession,
    moderator: ModeratorUser,
    window: PageWindow,
    status_filter: ReportStatus | None = Query(default=None, alias="status"),
    target_type: ReportTarget | None = Query(default=None),
) -> Page[ReportOut]:
    stmt = select(Report, User).join(User, User.id == Report.reporter_id)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)
    if target_type:
        stmt = stmt.where(Report.target_type == target_type)
    stmt = stmt.order_by(Report.created_at.desc()).limit(window["limit"])
    rows = db.execute(stmt).all()
    return Page(
        items=[_report_out(db, report, reporter) for report, reporter in rows],
        has_more=len(rows) == window["limit"],
    )


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: DbSession, moderator: ModeratorUser) -> ReportOut:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("That report does not exist.")
    return _report_out(db, report, db.get(User, report.reporter_id))


@router.get("/summary")
def moderation_summary(db: DbSession, moderator: ModeratorUser) -> dict:
    open_reports = db.execute(
        select(func.count()).select_from(Report).where(Report.status.in_([ReportStatus.open, ReportStatus.reviewing]))
    ).scalar_one()
    suspensions = db.execute(
        select(func.count()).select_from(User).where(User.is_suspended.is_(True))
    ).scalar_one()
    removed_content = db.execute(
        select(func.count()).select_from(Video).where(Video.is_removed.is_(True))
    ).scalar_one()
    recent_actions = db.execute(
        select(func.count()).select_from(ModerationAction)
    ).scalar_one()
    return {
        "open_reports": int(open_reports),
        "suspended_accounts": int(suspensions),
        "removed_videos": int(removed_content),
        "total_moderation_actions": int(recent_actions),
    }


@router.post("/reports/{report_id}/resolve", response_model=ReportOut)
def resolve_report(
    report_id: uuid.UUID, payload: ResolveReportRequest, db: DbSession, moderator: ModeratorUser
) -> ReportOut:
    report = db.get(Report, report_id)
    if report is None:
        raise NotFoundError("That report does not exist.")
    if report.status == ReportStatus.resolved and payload.status == "resolved":
        raise AppError("This report is already resolved.")

    report.status = ReportStatus(payload.status)
    report.resolution_note = payload.note
    report.resolved_by = moderator.id
    report.resolved_at = datetime.now(timezone.utc)

    if payload.action != "none":
        action_type = ModerationActionType(payload.action)
        db.add(
            ModerationAction(
                moderator_id=moderator.id,
                action_type=action_type,
                target_type=report.target_type,
                target_id=report.target_id,
                report_id=report.id,
                reason=report.reason,
                notes=payload.note,
            )
        )
        if action_type == ModerationActionType.content_removed:
            _remove_content(db, report.target_type, report.target_id, payload.note or "Policy violation")
        elif action_type == ModerationActionType.content_restored:
            _restore_content(db, report.target_type, report.target_id)
        elif action_type == ModerationActionType.user_suspended:
            _suspend(db, report.target_type, report.target_id, payload.note or "Policy violation", moderator)

    record_audit(
        db,
        actor_id=moderator.id,
        action="report_resolved",
        entity_type=report.target_type.value,
        entity_id=report.target_id,
        metadata={"status": payload.status, "action": payload.action},
        commit=False,
    )
    db.commit()
    db.refresh(report)

    if report.reporter_id != moderator.id:
        create_notification(
            db,
            user_id=report.reporter_id,
            type=NotificationType.moderation,
            entity_type="report",
            entity_id=report.id,
            payload={"status": report.status.value, "note": payload.note},
        )
    return _report_out(db, report, db.get(User, report.reporter_id))


def _remove_content(db: DbSession, target_type: ReportTarget, target_id: uuid.UUID, reason: str) -> None:
    if target_type == ReportTarget.video:
        video = db.get(Video, target_id)
        if video is None:
            raise NotFoundError("That video no longer exists.")
        video.is_removed = True
        video.removed_reason = reason[:500]
    elif target_type == ReportTarget.comment:
        comment = db.get(Comment, target_id)
        if comment is None:
            raise NotFoundError("That comment no longer exists.")
        comment.is_removed = True
        comment.removed_reason = reason[:500]
    elif target_type == ReportTarget.entry:
        entry = db.get(ChallengeEntry, target_id)
        if entry is None:
            raise NotFoundError("That entry no longer exists.")
        entry.status = EntryStatus.disqualified
        entry.disqualification_reason = reason[:500]


def _restore_content(db: DbSession, target_type: ReportTarget, target_id: uuid.UUID) -> None:
    if target_type == ReportTarget.video:
        video = db.get(Video, target_id)
        if video:
            video.is_removed = False
            video.removed_reason = None
    elif target_type == ReportTarget.comment:
        comment = db.get(Comment, target_id)
        if comment:
            comment.is_removed = False
            comment.removed_reason = None
    elif target_type == ReportTarget.entry:
        entry = db.get(ChallengeEntry, target_id)
        if entry:
            entry.status = EntryStatus.submitted
            entry.disqualification_reason = None


def _suspend(db: DbSession, target_type: ReportTarget, target_id: uuid.UUID, reason: str, moderator: User) -> None:
    user_id = target_id
    if target_type == ReportTarget.video:
        video = db.get(Video, target_id)
        if video is None:
            raise NotFoundError("That video no longer exists.")
        user_id = video.owner_id
    elif target_type == ReportTarget.comment:
        comment = db.get(Comment, target_id)
        if comment is None:
            raise NotFoundError("That comment no longer exists.")
        user_id = comment.author_id
    elif target_type == ReportTarget.entry:
        entry = db.get(ChallengeEntry, target_id)
        if entry is None:
            raise NotFoundError("That entry no longer exists.")
        user_id = entry.user_id

    target_user = db.get(User, user_id)
    if target_user is None:
        raise NotFoundError("That account no longer exists.")
    if target_user.role.value in {"moderator", "admin"} and moderator.role.value != "admin":
        raise AppError("Only an administrator can suspend a moderator or administrator.")

    target_user.is_suspended = True
    target_user.suspended_reason = reason[:500]
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == target_user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


@router.post("/content-action", response_model=ModerationActionOut)
def content_action(payload: ContentActionRequest, db: DbSession, moderator: ModeratorUser) -> ModerationActionOut:
    target_type = ReportTarget(payload.target_type)
    if payload.restore:
        _restore_content(db, target_type, payload.target_id)
        action_type = ModerationActionType.content_restored
    else:
        _remove_content(db, target_type, payload.target_id, payload.reason)
        action_type = ModerationActionType.content_removed

    action = ModerationAction(
        moderator_id=moderator.id,
        action_type=action_type,
        target_type=target_type,
        target_id=payload.target_id,
        reason=payload.reason,
    )
    db.add(action)
    record_audit(
        db,
        actor_id=moderator.id,
        action=action_type.value,
        entity_type=payload.target_type,
        entity_id=payload.target_id,
        metadata={"reason": payload.reason[:200]},
        commit=False,
    )
    db.commit()
    db.refresh(action)
    return ModerationActionOut(
        id=action.id,
        action_type=action.action_type.value,
        target_type=action.target_type.value,
        target_id=action.target_id,
        reason=action.reason,
        notes=action.notes,
        created_at=action.created_at,
        moderator=public_user(moderator),
    )


@router.post("/users/{user_id}/suspend", response_model=AckResponse)
def suspend_user(user_id: uuid.UUID, payload: SuspendUserRequest, db: DbSession, moderator: ModeratorUser) -> AckResponse:
    if user_id != payload.user_id:
        raise AppError("The account id in the body must match the path.")
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("That account does not exist.")
    if target.id == moderator.id:
        raise AppError("You cannot suspend your own account.")

    _suspend(db, ReportTarget.user, user_id, payload.reason, moderator)
    db.add(
        ModerationAction(
            moderator_id=moderator.id,
            action_type=ModerationActionType.user_suspended,
            target_type=ReportTarget.user,
            target_id=user_id,
            reason=payload.reason,
        )
    )
    record_audit(
        db,
        actor_id=moderator.id,
        action="user_suspended",
        entity_type="user",
        entity_id=user_id,
        metadata={"reason": payload.reason[:200]},
        commit=False,
    )
    db.commit()
    return AckResponse(message=f"{target.username} was suspended and signed out everywhere.")


@router.post("/users/{user_id}/reinstate", response_model=AckResponse)
def reinstate_user(user_id: uuid.UUID, db: DbSession, moderator: ModeratorUser) -> AckResponse:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("That account does not exist.")

    target.is_suspended = False
    target.suspended_reason = None
    db.add(
        ModerationAction(
            moderator_id=moderator.id,
            action_type=ModerationActionType.user_reinstated,
            target_type=ReportTarget.user,
            target_id=user_id,
        )
    )
    record_audit(
        db,
        actor_id=moderator.id,
        action="user_reinstated",
        entity_type="user",
        entity_id=user_id,
        commit=False,
    )
    db.commit()
    create_notification(
        db,
        user_id=target.id,
        type=NotificationType.moderation,
        entity_type="user",
        entity_id=target.id,
        payload={"reinstated": True},
    )
    return AckResponse(message=f"{target.username} was reinstated.")


@router.get("/actions", response_model=Page[ModerationActionOut])
def list_actions(db: DbSession, moderator: ModeratorUser, window: PageWindow) -> Page[ModerationActionOut]:
    stmt = select(ModerationAction).order_by(ModerationAction.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars())
    moderators = {}
    ids = {row.moderator_id for row in rows if row.moderator_id}
    if ids:
        moderators = {
            user.id: user for user in db.execute(select(User).where(User.id.in_(ids))).scalars().unique()
        }
    return Page(
        items=[
            ModerationActionOut(
                id=row.id,
                action_type=row.action_type.value,
                target_type=row.target_type.value,
                target_id=row.target_id,
                reason=row.reason,
                notes=row.notes,
                report_id=row.report_id,
                created_at=row.created_at,
                moderator=public_user(moderators[row.moderator_id]) if row.moderator_id in moderators else None,
            )
            for row in rows
        ],
        has_more=len(rows) == window["limit"],
    )


@router.get("/votes/suspicious", response_model=SuspiciousVotingResponse)
def suspicious_votes(
    db: DbSession,
    moderator: ModeratorUser,
    challenge_id: uuid.UUID | None = Query(default=None),
    window_minutes: int = Query(default=15, ge=1, le=1440),
) -> SuspiciousVotingResponse:
    anomalies = detect_suspicious_votes(db, challenge_id=challenge_id, window_minutes=window_minutes)
    return SuspiciousVotingResponse(challenge_id=challenge_id, anomalies=anomalies)


@router.get("/users")
def search_accounts(
    db: DbSession,
    moderator: ModeratorUser,
    window: PageWindow,
    q: str | None = Query(default=None, max_length=80),
    suspended: bool | None = Query(default=None),
) -> dict:
    stmt = select(User)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.username).like(pattern) | func.lower(User.email).like(pattern))
    if suspended is not None:
        stmt = stmt.where(User.is_suspended.is_(suspended))
    stmt = stmt.order_by(User.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars().unique())
    return {
        "items": [
            {
                **public_user(user).model_dump(),
                "email": user.email,
                "is_suspended": user.is_suspended,
                "suspended_reason": user.suspended_reason,
            }
            for user in rows
        ]
    }


@router.get("/audit-logs", response_model=Page[dict])
def audit_logs(db: DbSession, moderator: ModeratorUser, window: PageWindow) -> Page[dict]:
    rows = list(
        db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(window["limit"])).scalars()
    )
    return Page(
        items=[
            {
                "id": str(row.id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "metadata": row.metadata_json,
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        has_more=len(rows) == window["limit"],
    )