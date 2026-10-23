"""Password hashing, token issuing and auth cookie helpers.

Nothing in this module depends on a third-party identity provider: credentials
are stored locally with Argon2id and sessions are our own signed JWTs plus
server-side refresh token records.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

ACCESS_COOKIE = "vs_access"
REFRESH_COOKIE = "vs_refresh"
CSRF_COOKIE = "vs_csrf"

_password_hasher = PasswordHasher()


# --- passwords ---------------------------------------------------------------
def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


# --- tokens ------------------------------------------------------------------
def hash_token(raw_token: str) -> str:
    """Refresh/reset tokens are stored hashed — a database leak must not leak sessions."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def new_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256"), expires_at


def decode_token(raw_token: str, expected_type: Literal["access", "ws"] = "access") -> dict[str, Any]:
    payload = jwt.decode(raw_token, settings.secret_key, algorithms=["HS256"])
    if expected_type == "access" and payload.get("type") != "access":
        raise jwt.InvalidTokenError("unexpected token type")
    return payload


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# --- cookies -----------------------------------------------------------------
def _cookie_secure() -> bool:
    return settings.is_production


def set_auth_cookies(response, access_token: str, refresh_token: str, csrf_token: str) -> None:
    """HttpOnly session cookies; CSRF token readable by JS (double-submit pattern)."""
    common = {
        "httponly": True,
        "secure": _cookie_secure(),
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=settings.access_token_ttl_minutes * 60, **common)
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, max_age=settings.refresh_token_ttl_days * 86400, **common
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=False,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")