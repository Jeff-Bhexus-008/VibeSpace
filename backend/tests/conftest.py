"""Shared pytest fixtures.

These tests need PostgreSQL (and Redis for the rate-limit paths). Point
TEST_DATABASE_URL at a throwaway database — never at production:

    createdb vibespace_test
    export TEST_DATABASE_URL=postgresql+psycopg://vibespace:vibespace@localhost:5432/vibespace_test
    cd backend && pytest

Without TEST_DATABASE_URL the suite skips instead of failing, so CI without a
database still reports clearly.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MINUTE", "1000")
os.environ.setdefault("RATE_LIMIT_UPLOAD_PER_HOUR", "1000")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.integration

if not TEST_DATABASE_URL:
    pytest.skip(
        "TEST_DATABASE_URL is not set — start PostgreSQL and set it to run the backend suite.",
        allow_module_level=True,
    )

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402
from app.models.enums import MediaKind, MediaStatus, UserRole, VideoStatus  # noqa: E402
from app.models.media import MediaAsset  # noqa: E402
from app.models.user import User, UserProfile  # noqa: E402
from app.models.video import Video  # noqa: E402

engine = create_engine(TEST_DATABASE_URL, future=True)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


def _unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def make_user(
    db: Session,
    *,
    role: UserRole = UserRole.user,
    verified: bool = True,
    password: str = "StrongPass123",
    username: str | None = None,
) -> tuple[User, str]:
    from app.core.security import hash_password

    name = username or _unique("user")
    user = User(
        email=f"{name}@example.com",
        username=name,
        password_hash=hash_password(password),
        role=role,
        is_email_verified=verified,
    )
    db.add(user)
    db.flush()
    db.add(UserProfile(user_id=user.id, display_name=name))
    db.commit()
    db.refresh(user)
    return user, password


def login(client: TestClient, user: User, password: str = "StrongPass123") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def make_media(db: Session, owner: User, *, ready: bool = True, kind: MediaKind = MediaKind.video) -> MediaAsset:
    asset = MediaAsset(
        owner_id=owner.id,
        kind=kind,
        status=MediaStatus.ready if ready else MediaStatus.processing,
        storage_key=f"video/{owner.id}/{uuid.uuid4().hex}.mp4",
        bucket="vibespace-test",
        size_bytes=1_048_576,
        duration_seconds=12.5,
        width=1280,
        height=720,
        has_audio=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def make_video(
    db: Session,
    owner: User,
    *,
    title: str = "First vibe",
    asset: MediaAsset | None = None,
    published_hours_ago: int = 1,
) -> Video:
    media = asset or make_media(db, owner)
    video = Video(
        owner_id=owner.id,
        media_asset_id=media.id,
        title=title,
        status=VideoStatus.ready,
        published_at=datetime.now(timezone.utc) - timedelta(hours=published_hours_ago),
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


@pytest.fixture
def api(client: TestClient, db: Session) -> dict:
    """A ready-made cast: regular user, another user, creator, moderator and admin."""
    creator, creator_password = make_user(db, username=_unique("creator"))
    viewer, viewer_password = make_user(db, username=_unique("viewer"))
    moderator, moderator_password = make_user(db, role=UserRole.moderator, username=_unique("mod"))
    admin, admin_password = make_user(db, role=UserRole.admin, username=_unique("admin"))
    return {
        "client": client,
        "db": db,
        "creator": creator,
        "viewer": viewer,
        "moderator": moderator,
        "admin": admin,
        "passwords": {
            "creator": creator_password,
            "viewer": viewer_password,
            "moderator": moderator_password,
            "admin": admin_password,
        },
        "settings": settings,
    }