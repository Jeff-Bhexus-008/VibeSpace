"""Cloudflare R2 storage: configuration mapping, presigning, durable playback URLs.

These tests run without any real bucket: presigned URL generation happens locally in
boto3, and object-storage calls are monkeypatched. They prove the wiring is correct;
a real upload must still be exercised against the live bucket (see docs/R2_SETUP.md).
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings, settings as live_settings
from app.models.enums import VideoVisibility
from app.models.video import Video
from app.services import storage
from tests.conftest import make_media, make_video


def _r2_settings() -> Settings:
    return Settings(
        r2_account_id="testaccount",
        r2_access_key_id="AKIATESTKEY",
        r2_secret_access_key="super-secret-r2-key",
        r2_bucket_name="vibespace-media",
    )


def test_r2_settings_map_onto_s3_fields():
    cfg = _r2_settings()
    assert cfg.storage_configured is True
    assert cfg.storage_backend == "cloudflare_r2"
    assert cfg.s3_endpoint_url == "https://testaccount.r2.cloudflarestorage.com"
    assert cfg.s3_region == "auto"
    assert cfg.s3_bucket == "vibespace-media"
    assert cfg.s3_access_key_id == "AKIATESTKEY"


def test_r2_public_base_url_is_normalised_and_never_contains_secrets():
    cfg = Settings(
        r2_account_id="testaccount",
        r2_access_key_id="AKIATESTKEY",
        r2_secret_access_key="super-secret-r2-key",
        r2_bucket_name="vibespace-media",
        r2_public_base_url="https://media.vibespace.app/",
    )
    assert cfg.s3_public_base_url == "https://media.vibespace.app"
    assert "super-secret-r2-key" not in str(cfg.s3_public_base_url)


def test_storage_unconfigured_when_no_credentials():
    cfg = Settings(r2_account_id=None, s3_bucket="", s3_access_key_id=None, s3_secret_access_key=None)
    assert cfg.storage_configured is False
    assert cfg.storage_backend is None


def test_presigned_put_targets_the_r2_endpoint_without_leaking_the_secret(monkeypatch):
    cfg = _r2_settings()
    monkeypatch.setattr(storage, "settings", cfg)
    monkeypatch.setattr(storage, "_client", None)

    url = storage.create_presigned_put("video/video/owner/abc.mp4", "video/mp4", ttl_seconds=900)

    assert url.startswith("https://testaccount.r2.cloudflarestorage.com/vibespace-media/video/video/owner/abc.mp4")
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=900" in url
    assert "super-secret-r2-key" not in url


def test_stable_media_url_uses_stream_route_for_private_buckets(monkeypatch):
    cfg = _r2_settings()
    monkeypatch.setattr(storage, "settings", cfg)
    asset_id = uuid.uuid4()

    url = storage.stable_media_url(asset_id, "video/video/owner/abc.mp4")
    assert url == f"{cfg.backend_url.rstrip('/')}/api/v1/media/{asset_id}/stream"

    thumb = storage.stable_media_url(asset_id, "video/video/owner/abc.jpg", thumbnail=True)
    assert thumb.endswith(f"/api/v1/media/{asset_id}/thumbnail")


def test_stable_media_url_uses_public_domain_when_configured(monkeypatch):
    cfg = Settings(
        r2_account_id="testaccount",
        r2_access_key_id="AKIATESTKEY",
        r2_secret_access_key="super-secret-r2-key",
        r2_bucket_name="vibespace-media",
        r2_public_base_url="https://media.vibespace.app",
    )
    monkeypatch.setattr(storage, "settings", cfg)
    url = storage.stable_media_url(uuid.uuid4(), "video/video/owner/abc.mp4")
    assert url == "https://media.vibespace.app/video/video/owner/abc.mp4"


def test_stream_route_redirects_for_a_published_public_video(api, monkeypatch):
    client, db = api["client"], api["db"]
    video = make_video(db, api["creator"])

    monkeypatch.setattr(
        "app.api.v1.endpoints.media_stream.storage.create_presigned_get",
        lambda key, ttl_seconds=None: f"https://testaccount.r2.cloudflarestorage.com/signed/{key}",
    )
    response = client.get(f"/api/v1/media/{video.media_asset_id}/stream", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://testaccount.r2.cloudflarestorage.com/signed/")


def test_stream_route_hides_private_video_from_anonymous_visitors(api, monkeypatch):
    client, db = api["client"], api["db"]
    video = make_video(db, api["creator"])
    video.visibility = VideoVisibility.private
    db.commit()

    response = client.get(f"/api/v1/media/{video.media_asset_id}/stream", follow_redirects=False)
    assert response.status_code in {401, 403, 404}


def test_stream_route_allows_the_owner_before_publication(api, monkeypatch):
    client, db = api["client"], api["db"]
    from tests.conftest import login

    asset = make_media(db, api["creator"])
    video = Video(owner_id=api["creator"].id, media_asset_id=asset.id, title="Draft vibe")
    db.add(video)
    db.commit()

    monkeypatch.setattr(
        "app.api.v1.endpoints.media_stream.storage.create_presigned_get",
        lambda key, ttl_seconds=None: f"https://r2.example.com/{key}",
    )
    headers = login(client, api["creator"], api["passwords"]["creator"])
    response = client.get(f"/api/v1/media/{asset.id}/stream", headers=headers, follow_redirects=False)
    assert response.status_code == 307


def test_stream_route_404s_for_unknown_or_unready_assets(api):
    client, db = api["client"], api["db"]
    assert client.get(f"/api/v1/media/{uuid.uuid4()}/stream", follow_redirects=False).status_code == 404

    pending = make_media(db, api["creator"], ready=False)
    assert client.get(f"/api/v1/media/{pending.id}/stream", follow_redirects=False).status_code == 404


def test_complete_upload_marks_video_ready_when_processing_is_disabled(api, monkeypatch):
    from app.models.enums import MediaStatus
    from app.services import uploads as uploads_service
    from tests.conftest import login

    client, db = api["client"], api["db"]
    asset = make_media(db, api["creator"], ready=False)
    asset.status = MediaStatus.uploaded
    db.commit()

    monkeypatch.setattr(uploads_service, "verify_uploaded_object", lambda a: (True, None))
    monkeypatch.setattr(uploads_service.settings, "video_processing_enabled", False)

    headers = login(client, api["creator"], api["passwords"]["creator"])
    response = client.post("/api/v1/uploads/complete", json={"asset_id": str(asset.id)}, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["ready"] is True
    assert response.json()["asset"]["status"] == "ready"


def test_complete_upload_never_publishes_a_missing_object(api, monkeypatch):
    from app.models.enums import MediaStatus
    from app.services import uploads as uploads_service
    from tests.conftest import login

    client, db = api["client"], api["db"]
    asset = make_media(db, api["creator"], ready=False)
    asset.status = MediaStatus.uploaded
    db.commit()

    monkeypatch.setattr(
        uploads_service,
        "verify_uploaded_object",
        lambda a: (False, "The upload did not arrive in storage. Please try again."),
    )
    headers = login(client, api["creator"], api["passwords"]["creator"])
    response = client.post("/api/v1/uploads/complete", json={"asset_id": str(asset.id)}, headers=headers)

    assert response.status_code >= 400
    db.refresh(asset)
    assert asset.status == MediaStatus.failed
