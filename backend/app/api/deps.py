"""Authentication/authorisation dependencies shared by every protected route."""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated, Callable

import jwt
from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, PermissionDeniedError
from app.core.pagination import InvalidCursorError, clamp_limit, decode_cursor
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, decode_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ROLE_RANK = {UserRole.user: 0, UserRole.creator: 1, UserRole.moderator: 2, UserRole.admin: 3}

DbSession = Annotated[Session, Depends(get_db)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(f"{ip}:{settings.secret_key}".encode()).hexdigest()[:64]


def _extract_token(request: Request) -> tuple[str | None, bool]:
    cookie_token = request.cookies.get(ACCESS_COOKIE)
    if cookie_token:
        return cookie_token, True
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip(), False
    return None, False


def _enforce_csrf(request: Request) -> None:
    """Double-submit check for state-changing requests that ride on cookies."""
    if request.method in SAFE_METHODS:
        return
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise AppError(
            "Missing or invalid CSRF token.",
            status_code=403,
            details={"hint": "Send the vs_csrf cookie value back in the X-CSRF-Token header."},
        )


def _load_user(db: Session, token: str) -> User:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise AppError("Your session has expired. Please sign in again.", status_code=401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("Invalid session token.", status_code=401) from exc

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise AppError("Invalid session token.", status_code=401) from exc

    user = db.get(User, user_id)
    if user is None:
        raise AppError("This account no longer exists.", status_code=401)
    if user.is_suspended:
        raise PermissionDeniedError(
            "This account is suspended." + (f" Reason: {user.suspended_reason}" if user.suspended_reason else "")
        )
    return user


def get_current_user(request: Request, db: DbSession) -> User:
    token, from_cookie = _extract_token(request)
    if not token:
        raise AppError("Sign in to continue.", status_code=401)
    if from_cookie:
        _enforce_csrf(request)
    user = _load_user(db, token)
    request.state.user = user
    return user


def get_optional_user(request: Request, db: DbSession) -> User | None:
    token, from_cookie = _extract_token(request)
    if not token:
        return None
    if from_cookie:
        try:
            _enforce_csrf(request)
        except AppError:
            # A public read with a stale CSRF cookie should still work.
            if request.method not in SAFE_METHODS:
                raise
    try:
        user = _load_user(db, token)
    except AppError:
        return None
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(minimum: UserRole) -> Callable[[User], User]:
    def dependency(user: CurrentUser) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise PermissionDeniedError(f"This action requires the {minimum.value} role.")
        return user

    return dependency


ModeratorUser = Annotated[User, Depends(require_role(UserRole.moderator))]
AdminUser = Annotated[User, Depends(require_role(UserRole.admin))]


def pagination(
    limit: int = Query(default=20, ge=1, le=100, description="Rows per page"),
    cursor: str | None = Query(default=None, description="Opaque cursor from the previous page"),
) -> dict:
    try:
        decoded = decode_cursor(cursor)
    except InvalidCursorError as exc:
        raise AppError(str(exc), details={"cursor": cursor}) from exc
    return {"limit": clamp_limit(limit), "cursor": decoded}


PageWindow = Annotated[dict, Depends(pagination)]