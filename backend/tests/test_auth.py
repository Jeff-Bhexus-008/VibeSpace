"""Registration, login, session refresh and password reset."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_token, new_opaque_token

from app.models.auth_tokens import EmailToken, RefreshToken
from app.models.enums import TokenPurpose
from tests.conftest import _unique, login, make_user


def test_registration_creates_account_and_session(client, db):
    username = _unique("newbie")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["username"] == username
    assert body["user"]["is_email_verified"] is False
    assert "vs_access" in response.cookies and "vs_refresh" in response.cookies

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == username


def test_registration_rejects_duplicate_email_and_weak_password(client, db):
    user, _ = make_user(db)
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"username": _unique("dup"), "email": user.email, "password": "StrongPass123"},
    )
    assert duplicate.status_code == 409

    weak = client.post(
        "/api/v1/auth/register",
        json={"username": _unique("weak"), "email": f"{uuid.uuid4().hex[:8]}@example.com", "password": "short"},
    )
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "validation_error"


def test_login_rejects_wrong_password(client, db):
    user, _ = make_user(db)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "WrongPass123"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_login_sets_cookies_and_csrf_is_required_for_writes(client, db):
    user, password = make_user(db)
    headers = login(client, user, password)

    # Without the CSRF header a cookie-authenticated write is refused.
    blocked = client.patch("/api/v1/users/me/profile", json={"bio": "hello"})
    assert blocked.status_code == 403

    allowed = client.patch("/api/v1/users/me/profile", json={"bio": "hello"}, headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["bio"] == "hello"


def test_refresh_rotates_and_reuse_is_revoked(client, db):
    user, password = make_user(db)
    login(client, user, password)
    first_cookie = client.cookies.get("vs_refresh")

    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    assert client.cookies.get("vs_refresh") != first_cookie

    # Replaying the old cookie must fail and revoke the family.
    replay = client.post("/api/v1/auth/refresh", cookies={"vs_refresh": first_cookie})
    assert replay.status_code == 401

    active = db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).scalars().all()
    assert active == []


def test_password_reset_flow_is_generic_then_works(client, db):
    user, _ = make_user(db)
    unknown = client.post("/api/v1/auth/password/reset-request", json={"email": "nobody@example.com"})
    known = client.post("/api/v1/auth/password/reset-request", json={"email": user.email})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]

    token_row = db.execute(
        select(EmailToken).where(
            EmailToken.user_id == user.id, EmailToken.purpose == TokenPurpose.reset_password
        )
    ).scalar_one()
    assert token_row.used_at is None

    # The raw token is only known to the mail recipient; mint one here.
    raw = new_opaque_token()
    token_row.token_hash = hash_token(raw)
    db.commit()

    confirmed = client.post(
        "/api/v1/auth/password/reset-confirm", json={"token": raw, "new_password": "BrandNew123"}
    )
    assert confirmed.status_code == 200, confirmed.text
    relogin = client.post("/api/v1/auth/login", json={"email": user.email, "password": "BrandNew123"})
    assert relogin.status_code == 200


def test_email_verification_confirm(client, db):
    user, password = make_user(db, verified=False)
    headers = login(client, user, password)

    request = client.post("/api/v1/auth/email/verify-request", headers=headers)
    assert request.status_code == 200
    assert request.json()["dev_verify_link"] or request.json()["message"]

    raw = new_opaque_token()
    row = EmailToken(
        user_id=user.id,
        purpose=TokenPurpose.verify_email,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(row)
    db.commit()

    confirmed = client.post("/api/v1/auth/email/verify-confirm", json={"token": raw}, headers=headers)
    assert confirmed.status_code == 200
    db.refresh(user)
    assert user.is_email_verified is True


def test_suspended_account_cannot_sign_in(client, db):
    user, password = make_user(db)
    user.is_suspended = True
    user.suspended_reason = "repeated policy violations"
    db.commit()

    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 403