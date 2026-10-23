"""Authentication routes: register, login, refresh rotation, password and email flows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession, client_ip, hash_ip
from app.api.v1.serializers import media_url
from app.core.config import settings
from app.core.errors import AppError, ConflictError
from app.core.ratelimit import rate_limit
from app.core.security import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_csrf_token,
    new_opaque_token,
    set_auth_cookies,
    verify_password,
)
from app.models.auth_tokens import EmailToken, RefreshToken
from app.models.enums import TokenPurpose
from app.models.user import User, UserProfile
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
    SessionUser,
    VerifyEmailConfirm,
    VerifyEmailRequest,
)
from app.schemas.common import AckResponse
from app.services import email as email_service

router = APIRouter(prefix="/auth", tags=["authentication"])

auth_limit = Depends(rate_limit("auth", settings.rate_limit_auth_per_minute, 60))


def session_user(user: User) -> SessionUser:
    profile = user.profile
    return SessionUser(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        is_email_verified=user.is_email_verified,
        display_name=(profile.display_name if profile else None) or user.username,
        avatar_url=media_url(profile.avatar_key if profile else None),
        cover_url=media_url(profile.cover_key if profile else None),
        bio=profile.bio if profile else None,
        follower_count=profile.follower_count if profile else 0,
        following_count=profile.following_count if profile else 0,
        video_count=profile.video_count if profile else 0,
        created_at=user.created_at,
    )


def _issue_session(db, response: Response, user: User, request: Request) -> SessionResponse:
    access_token, expires_at = create_access_token(user.id, user.role.value)
    raw_refresh = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=(request.headers.get("user-agent") or "")[:255],
            ip_hash=hash_ip(client_ip(request)),
        )
    )
    db.commit()

    csrf_token = new_csrf_token()
    set_auth_cookies(response, access_token, raw_refresh, csrf_token)
    return SessionResponse(user=session_user(user), access_token_expires_at=expires_at, csrf_token=csrf_token)


def _store_email_token(db, user: User, purpose: TokenPurpose, *, ttl: timedelta) -> str:
    raw = new_opaque_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw),
            expires_at=datetime.now(timezone.utc) + ttl,
        )
    )
    db.commit()
    return raw


def _dev_link_only(path: str, token: str) -> str | None:
    """In development, and only when mail delivery is not configured, hand the link back."""
    if settings.is_production or settings.email_delivery_configured:
        return None
    return email_service.build_action_link(path, token)


def _by_email(db, email: str) -> User | None:
    return db.execute(select(User).where(func.lower(User.email) == email.lower())).scalar_one_or_none()


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED, dependencies=[auth_limit])
def register(payload: RegisterRequest, request: Request, response: Response, db: DbSession) -> RegisterResponse:
    if _by_email(db, payload.email) is not None:
        raise ConflictError("An account with that email already exists.")
    taken = db.execute(
        select(User.id).where(func.lower(User.username) == payload.username.lower())
    ).scalar_one_or_none()
    if taken:
        raise ConflictError("That username is already taken.")

    user = User(
        email=payload.email.lower(),
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That username or email is already registered.") from exc

    db.add(UserProfile(user_id=user.id, display_name=payload.display_name or payload.username))
    db.commit()
    db.refresh(user)

    token = _store_email_token(db, user, TokenPurpose.verify_email, ttl=timedelta(hours=24))
    subject, html, text = email_service.verification_email(user.username, token)
    sent = email_service.send_email(user.email, subject, html, text)

    session = _issue_session(db, response, user, request)
    return RegisterResponse(
        **session.model_dump(),
        verification_email_sent=sent,
        dev_verify_link=_dev_link_only("/verify-email", token),
    )


@router.post("/login", response_model=SessionResponse, dependencies=[auth_limit])
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> SessionResponse:
    user = _by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("Email or password is incorrect.", status_code=status.HTTP_401_UNAUTHORIZED)
    if user.is_suspended:
        raise AppError(
            "This account is suspended." + (f" Reason: {user.suspended_reason}" if user.suspended_reason else ""),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    return _issue_session(db, response, user, request)


@router.post("/refresh", response_model=RefreshResponse, dependencies=[auth_limit])
def refresh_session(request: Request, response: Response, db: DbSession) -> RefreshResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if not raw_token:
        raise AppError("No active session to refresh.", status_code=status.HTTP_401_UNAUTHORIZED)

    record = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    ).scalar_one_or_none()
    if record is None:
        clear_auth_cookies(response)
        raise AppError("Session not recognised. Please sign in again.", status_code=status.HTTP_401_UNAUTHORIZED)

    if record.revoked_at is not None:
        # A reused rotated token means the cookie copy leaked: kill the whole family.
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        db.commit()
        clear_auth_cookies(response)
        raise AppError("This session was revoked. Please sign in again.", status_code=status.HTTP_401_UNAUTHORIZED)

    if record.expires_at <= datetime.now(timezone.utc):
        clear_auth_cookies(response)
        raise AppError("Session expired. Please sign in again.", status_code=status.HTTP_401_UNAUTHORIZED)

    user = db.get(User, record.user_id)
    if user is None or user.is_suspended:
        clear_auth_cookies(response)
        raise AppError("This account is not available.", status_code=status.HTTP_401_UNAUTHORIZED)

    access_token, expires_at = create_access_token(user.id, user.role.value)
    raw_refresh = new_opaque_token()
    new_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family_id=record.family_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=record.user_agent,
        ip_hash=record.ip_hash,
    )
    record.revoked_at = datetime.now(timezone.utc)
    db.add(new_record)
    db.flush()
    record.replaced_by_id = new_record.id
    db.commit()

    csrf_token = new_csrf_token()
    set_auth_cookies(response, access_token, raw_refresh, csrf_token)
    return RefreshResponse(access_token_expires_at=expires_at, csrf_token=csrf_token)


@router.post("/logout", response_model=AckResponse)
def logout(request: Request, response: Response, db: DbSession) -> AckResponse:
    raw_token = request.cookies.get(REFRESH_COOKIE)
    if raw_token:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        db.commit()
    clear_auth_cookies(response)
    return AckResponse(message="Signed out.")


@router.post("/logout-all", response_model=AckResponse)
def logout_everywhere(request: Request, response: Response, user: CurrentUser, db: DbSession) -> AckResponse:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    clear_auth_cookies(response)
    return AckResponse(message="Signed out of all devices.")


@router.get("/me", response_model=SessionUser)
def me(user: CurrentUser) -> SessionUser:
    return session_user(user)


@router.post("/password/change", response_model=AckResponse, dependencies=[auth_limit])
def change_password(
    payload: ChangePasswordRequest, request: Request, response: Response, user: CurrentUser, db: DbSession
) -> AckResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise AppError("Your current password is incorrect.", status_code=status.HTTP_400_BAD_REQUEST)

    user.password_hash = hash_password(payload.new_password)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    db.refresh(user)
    _issue_session(db, response, user, request)
    return AckResponse(message="Password updated. Other devices were signed out.")


@router.post("/password/reset-request", response_model=AckResponse, dependencies=[auth_limit])
def request_password_reset(payload: PasswordResetRequest, db: DbSession) -> AckResponse:
    user = _by_email(db, payload.email)
    dev_link = None
    if user is not None:
        token = _store_email_token(db, user, TokenPurpose.reset_password, ttl=timedelta(hours=1))
        subject, html, text = email_service.password_reset_email(user.username, token)
        email_service.send_email(user.email, subject, html, text)
        dev_link = _dev_link_only("/reset-password", token)
    # Always the same answer: whether an email exists stays private.
    return AckResponse(
        message="If that address has an account, a reset link is on its way.",
        dev_reset_link=dev_link,
    )


@router.post("/password/reset-confirm", response_model=AckResponse, dependencies=[auth_limit])
def confirm_password_reset(payload: PasswordResetConfirm, db: DbSession) -> AckResponse:
    record = db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(payload.token),
            EmailToken.purpose == TokenPurpose.reset_password,
            EmailToken.used_at.is_(None),
        )
    ).scalar_one_or_none()
    if record is None or record.expires_at <= datetime.now(timezone.utc):
        raise AppError("This reset link is invalid or has expired.")

    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("This reset link is invalid or has expired.")

    user.password_hash = hash_password(payload.new_password)
    record.used_at = datetime.now(timezone.utc)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    db.commit()
    return AckResponse(message="Password updated. You can sign in now.")


@router.post("/email/verify-request", response_model=AckResponse, dependencies=[auth_limit])
def request_email_verification(user: CurrentUser, db: DbSession) -> AckResponse:
    if user.is_email_verified:
        return AckResponse(message="This email address is already confirmed.")
    token = _store_email_token(db, user, TokenPurpose.verify_email, ttl=timedelta(hours=24))
    subject, html, text = email_service.verification_email(user.username, token)
    sent = email_service.send_email(user.email, subject, html, text)
    return AckResponse(
        message="Confirmation email sent." if sent else "Mail delivery is not configured on this server.",
        dev_verify_link=_dev_link_only("/verify-email", token),
    )


@router.post("/email/verify-confirm", response_model=AckResponse, dependencies=[auth_limit])
def confirm_email(payload: VerifyEmailConfirm, db: DbSession) -> AckResponse:
    record = db.execute(
        select(EmailToken).where(
            EmailToken.token_hash == hash_token(payload.token),
            EmailToken.purpose == TokenPurpose.verify_email,
            EmailToken.used_at.is_(None),
        )
    ).scalar_one_or_none()
    if record is None or record.expires_at <= datetime.now(timezone.utc):
        raise AppError("This confirmation link is invalid or has expired.")

    user = db.get(User, record.user_id)
    if user is None:
        raise AppError("This confirmation link is invalid or has expired.")

    user.is_email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    record.used_at = datetime.now(timezone.utc)
    db.commit()
    return AckResponse(message="Email confirmed.")