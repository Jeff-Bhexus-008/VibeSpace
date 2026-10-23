"""Upload authorisation, setup errors and media metadata."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.enums import MediaStatus
from tests.conftest import login, make_user


def test_unconfigured_storage_returns_a_clear_setup_error(api, monkeypatch):
    client = api["client"]
    headers = login(client, api["creator"])
    monkeypatch.setattr(settings, "s3_access_key_id", None)
    monkeypatch.setattr(settings, "s3_secret_access_key", None)

    response = client.post(
        "/api/v1/uploads/ticket",
        json={
            "kind": "video",
            "filename": "clip.mp4",
            "declared_content_type": "video/mp4",
            "size_bytes": 2048,
            "purpose": "video",
        },
        headers=headers,
    )
    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "service_unavailable"
    assert "S3_BUCKET" in body["error"]["details"]["missing"]


def test_upload_ticket_rejects_wrong_extension_and_oversized_files(api, monkeypatch):
    client = api["client"]
    headers = login(client, api["creator"])
    monkeypatch.setattr(settings, "s3_access_key_id", "test-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret")

    wrong_extension = client.post(
        "/api/v1/uploads/ticket",
        json={
            "kind": "video",
            "filename": "payload.exe",
            "declared_content_type": "video/mp4",
            "size_bytes": 1024,
            "purpose": "video",
        },
        headers=headers,
    )
    assert wrong_extension.status_code == 400

    too_big = client.post(
        "/api/v1/uploads/ticket",
        json={
            "kind": "video",
            "filename": "huge.mp4",
            "declared_content_type": "video/mp4",
            "size_bytes": settings.upload_max_bytes + 1,
            "purpose": "video",
        },
        headers=headers,
    )
    assert too_big.status_code == 400
    assert too_big.json()["error"]["details"]["max_bytes"] == settings.upload_max_bytes


def test_upload_ticket_creates_pending_asset_with_unique_key(api, monkeypatch):
    client, db = api["client"], api["db"]
    headers = login(client, api["creator"])
    monkeypatch.setattr(settings, "s3_access_key_id", "test-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret")

    payload = {
        "kind": "video",
        "filename": "clip.mp4",
        "declared_content_type": "video/mp4",
        "size_bytes": 4096,
        "purpose": "video",
    }
    first = client.post("/api/v1/uploads/ticket", json=payload, headers=headers)
    second = client.post("/api/v1/uploads/ticket", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201
    assert first.json()["storage_key"] != second.json()["storage_key"]
    assert first.json()["upload_url"].startswith("http")

    from app.models.media import MediaAsset

    asset = db.get(MediaAsset, first.json()["asset_id"])
    assert asset.status == MediaStatus.pending
    assert str(api["creator"].id) in asset.storage_key

    # Another account cannot poll or discard this upload.
    other, password = make_user(db)
    other_headers = login(client, other, password)
    assert client.get(f"/api/v1/uploads/{asset.id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/uploads/{asset.id}", headers=other_headers).status_code == 403


def test_video_requires_ready_media(api):
    client, db = api["client"], api["db"]
    from tests.conftest import make_media

    headers = login(client, api["creator"])
    processing = make_media(db, api["creator"], ready=False)
    response = client.post(
        "/api/v1/videos",
        json={"media_asset_id": str(processing.id), "title": "Still cooking"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"]["media_status"] == "processing"


def test_video_metadata_is_stored_and_returned(api):
    client, db = api["client"], api["db"]
    from tests.conftest import make_media

    headers = login(client, api["creator"])
    asset = make_media(db, api["creator"])
    created = client.post(
        "/api/v1/videos",
        json={
            "media_asset_id": str(asset.id),
            "title": "Vibe check",
            "description": "First upload",
            "tags": ["Dance", "#vibe", "dance"],
            "category": "dance",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["tags"] == ["dance", "vibe"]
    assert body["duration_seconds"] == 12.5
    assert body["status"] == "ready"

    listed = client.get("/api/v1/videos/mine", headers=headers)
    assert listed.json()["items"][0]["id"] == body["id"]


def test_storage_status_reports_setup_gaps(api):
    client = api["client"]
    response = client.get("/api/v1/uploads/config/status")
    assert response.status_code == 200
    body = response.json()
    assert "storage_configured" in body
    assert "ffmpeg_available" in body


@pytest.mark.parametrize("kind,purpose", [("image", "avatar"), ("audio", "message")])
def test_non_video_purposes_accept_their_own_kinds(api, monkeypatch, kind, purpose):
    client = api["client"]
    headers = login(client, api["creator"])
    monkeypatch.setattr(settings, "s3_access_key_id", "test-key")
    monkeypatch.setattr(settings, "s3_secret_access_key", "test-secret")

    extension = {"image": "png", "audio": "mp3"}[kind]
    response = client.post(
        "/api/v1/uploads/ticket",
        json={
            "kind": kind,
            "filename": f"asset.{extension}",
            "declared_content_type": f"{kind}/{extension}",
            "size_bytes": 1024,
            "purpose": purpose,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text