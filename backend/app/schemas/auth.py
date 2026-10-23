"""Authentication, session and account-security schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if value.lower() in {"password12", "12345678910", "qwertyuiop1"}:
            raise ValueError("Password is too common.")
        if not any(char.isdigit() for char in value) or not any(char.isalpha() for char in value):
            raise ValueError("Password must contain both letters and numbers.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=10, max_length=128)


class VerifyEmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailConfirm(BaseModel):
    token: str = Field(min_length=10)


class SessionUser(ORMModel):
    """The authenticated caller, as returned by /auth/me."""

    id: uuid.UUID
    username: str
    email: str
    role: str
    is_email_verified: bool
    display_name: str | None = None
    avatar_url: str | None = None
    cover_url: str | None = None
    bio: str | None = None
    follower_count: int = 0
    following_count: int = 0
    video_count: int = 0
    created_at: datetime | None = None


class SessionResponse(BaseModel):
    user: SessionUser
    access_token_expires_at: datetime
    csrf_token: str


class RefreshResponse(BaseModel):
    access_token_expires_at: datetime
    csrf_token: str


class RegisterResponse(SessionResponse):
    """Registration signs the new account in and reports the verification email."""

    verification_email_sent: bool = False
    dev_verify_link: str | None = None