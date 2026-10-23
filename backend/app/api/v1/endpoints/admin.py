"""Administration: platform statistics, user roles, audit log and category catalogue."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession, PageWindow
from app.api.v1.serializers import public_user
from app.core.errors import AppError, ConflictError, NotFoundError
from app.models.challenge import Challenge, ChallengeEntry, Vote
from app.models.enums import UserRole
from app.models.media import MediaAsset
from app.models.messaging import Message
from app.models.moderation import AuditLog, ModerationAction, PlatformCategory, Report
from app.models.social import Comment, Like
from app.models.user import User
from app.models.video import Video
from app.schemas.common import AckResponse, Page
from app.schemas.moderation import AuditLogOut, CategoryCreate, CategoryOut
from app.services.audit import record_audit

router = APIRouter(prefix="/admin", tags=["administration"])

ASSIGNABLE_ROLES = [role.value for role in UserRole]


@router.get("/stats")
def platform_stats(db: DbSession, admin: AdminUser) -> dict:
    def count(model, *criteria) -> int:
        return int(db.execute(select(func.count()).select_from(model).where(*criteria)).scalar_one() or 0)

    views = db.execute(select(func.coalesce(func.sum(Video.view_count), 0))).scalar_one()
    storage_bytes = db.execute(select(func.coalesce(func.sum(MediaAsset.size_bytes), 0))).scalar_one()
    return {
        "users": {
            "total": count(User),
            "suspended": count(User, User.is_suspended.is_(True)),
            "creators": count(User, User.role == UserRole.creator),
            "moderators": count(User, User.role == UserRole.moderator),
            "admins": count(User, User.role == UserRole.admin),
        },
        "content": {
            "videos": count(Video),
            "removed_videos": count(Video, Video.is_removed.is_(True)),
            "learn_videos": count(Video, Video.is_learn_content.is_(True)),
            "comments": count(Comment),
            "likes": count(Like),
            "media_assets": count(MediaAsset),
            "storage_bytes": int(storage_bytes or 0),
        },
        "engagement": {
            "total_views": int(views or 0),
            "messages": count(Message),
        },
        "battles": {
            "challenges": count(Challenge),
            "entries": count(ChallengeEntry),
            "votes": count(Vote),
        },
        "moderation": {
            "open_reports": count(Report, Report.status.in_(["open", "reviewing"])),
            "total_reports": count(Report),
            "actions": count(ModerationAction),
        },
    }


@router.get("/users")
def list_users(
    db: DbSession,
    admin: AdminUser,
    window: PageWindow,
    q: str | None = Query(default=None, max_length=80),
    role: UserRole | None = Query(default=None),
) -> dict:
    stmt = select(User)
    if q:
        pattern = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(User.username).like(pattern) | func.lower(User.email).like(pattern))
    if role:
        stmt = stmt.where(User.role == role)
    stmt = stmt.order_by(User.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars().unique())
    return {
        "items": [
            {
                **public_user(user).model_dump(),
                "email": user.email,
                "is_suspended": user.is_suspended,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            }
            for user in rows
        ],
        "assignable_roles": ASSIGNABLE_ROLES,
    }


@router.patch("/users/{user_id}/role", response_model=AckResponse)
def change_role(user_id: uuid.UUID, role: UserRole, db: DbSession, admin: AdminUser) -> AckResponse:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("That account does not exist.")
    if target.id == admin.id:
        raise AppError("You cannot change your own role.")
    if target.role == role:
        return AckResponse(message="This account already has that role.")

    previous = target.role
    target.role = role
    record_audit(
        db,
        actor_id=admin.id,
        action="role_changed",
        entity_type="user",
        entity_id=target.id,
        metadata={"from": previous.value, "to": role.value},
        commit=False,
    )
    db.commit()
    return AckResponse(message=f"{target.username} is now {role.value}.")


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def audit_log(db: DbSession, admin: AdminUser, window: PageWindow, action: str | None = None) -> Page[AuditLogOut]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(window["limit"])
    rows = list(db.execute(stmt).scalars())

    actors = {}
    ids = {row.actor_id for row in rows if row.actor_id}
    if ids:
        actors = {user.id: user for user in db.execute(select(User).where(User.id.in_(ids))).scalars().unique()}

    return Page(
        items=[
            AuditLogOut(
                id=row.id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                metadata_json=row.metadata_json,
                created_at=row.created_at,
                actor=public_user(actors[row.actor_id]) if row.actor_id in actors else None,
            )
            for row in rows
        ],
        has_more=len(rows) == window["limit"],
    )


# --- category catalogue -------------------------------------------------------
@router.get("/categories", response_model=Page[CategoryOut])
def list_categories(db: DbSession, admin: AdminUser, window: PageWindow) -> Page[CategoryOut]:
    rows = list(
        db.execute(
            select(PlatformCategory)
            .order_by(PlatformCategory.sort_order.asc(), PlatformCategory.label.asc())
            .limit(window["limit"])
        ).scalars()
    )
    return Page(items=[CategoryOut.model_validate(row) for row in rows], has_more=len(rows) == window["limit"])


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: DbSession, admin: AdminUser) -> CategoryOut:
    existing = db.execute(
        select(PlatformCategory.id).where(PlatformCategory.slug == payload.slug)
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("A category with that slug already exists.")

    category = PlatformCategory(**payload.model_dump())
    db.add(category)
    record_audit(
        db,
        actor_id=admin.id,
        action="category_created",
        entity_type="platform_category",
        metadata={"slug": payload.slug},
        commit=False,
    )
    db.commit()
    db.refresh(category)
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID, payload: CategoryCreate, db: DbSession, admin: AdminUser
) -> CategoryOut:
    category = db.get(PlatformCategory, category_id)
    if category is None:
        raise NotFoundError("That category does not exist.")
    for field, value in payload.model_dump().items():
        setattr(category, field, value)
    record_audit(
        db,
        actor_id=admin.id,
        action="category_updated",
        entity_type="platform_category",
        entity_id=category.id,
        metadata={"slug": category.slug},
        commit=False,
    )
    db.commit()
    db.refresh(category)
    return CategoryOut.model_validate(category)


@router.delete("/categories/{category_id}", response_model=AckResponse)
def retire_category(category_id: uuid.UUID, db: DbSession, admin: AdminUser) -> AckResponse:
    """Categories are retired rather than deleted so existing content keeps its label."""
    category = db.get(PlatformCategory, category_id)
    if category is None:
        raise NotFoundError("That category does not exist.")
    category.is_active = False
    record_audit(
        db,
        actor_id=admin.id,
        action="category_retired",
        entity_type="platform_category",
        entity_id=category.id,
        commit=False,
    )
    db.commit()
    return AckResponse(message=f"{category.label} was retired.")