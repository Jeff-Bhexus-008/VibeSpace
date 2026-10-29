"""Upload pipeline: authorise, verify and queue media.

Flow: ticket → browser PUTs directly to object storage → complete → worker probes
and generates thumbnails/renditions. Large bytes never pass through the API.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, NotFoundError, PermissionDeniedError
from app.db.session import SessionLocal
from app.models.enums import MediaKind, MediaStatus
from app.models.media import MediaAsset
from app.models.user import User
from app.schemas.media import MediaAssetOut, UploadTicket, UploadTicketRequest
from app.services import filetypes, storage

logger = logging.getLogger("vibespace.uploads")

PURPOSE_KINDS = {
    "video": {"video"},
    "entry": {"video"},
    "reference": {"video", "image"},
    "avatar": {"image"},
    "cover": {"image"},
    "message": {"video", "image", "audio"},
    "message_image": {"image"},
}


def create_upload_ticket(db: Session, user: User, payload: UploadTicketRequest) -> UploadTicket:
    storage.require_configured()
    _cleanup_abandoned_uploads(db, user)

    allowed_kinds = PURPOSE_KINDS.get(payload.purpose, {payload.kind})
    if payload.kind not in allowed_kinds:
        raise AppError(f"A {payload.kind} file cannot be uploaded for {payload.purpose}.")

    if not filetypes.is_allowed_extension(payload.kind, payload.filename):
        raise AppError(
            "That file type is not supported.",
            details={"filename": payload.filename, "kind": payload.kind},
        )

    if payload.size_bytes > settings.upload_max_bytes:
        raise AppError(
            "That file is larger than the upload limit.",
            details={"max_bytes": settings.upload_max_bytes, "max_mb": round(settings.upload_max_bytes / 1_048_576)},
        )

    key = storage.build_storage_key(user.id, payload.kind, payload.filename, payload.purpose)
    asset = MediaAsset(
        owner_id=user.id,
        kind=MediaKind(payload.kind),
        status=MediaStatus.pending,
        storage_key=key,
        bucket=settings.s3_bucket,
        original_filename=payload.filename,
        declared_content_type=payload.declared_content_type,
        size_bytes=payload.size_bytes,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    upload_url = storage.create_presigned_put(key, payload.declared_content_type)
    return UploadTicket(
        asset_id=asset.id,
        storage_key=key,
        upload_url=upload_url,
        headers={"Content-Type": payload.declared_content_type},
        expires_in=settings.upload_url_ttl_seconds,
        max_bytes=settings.upload_max_bytes,
    )


def require_owned_asset(db: Session, user: User, asset_id: uuid.UUID, expected_kind: str | None = None) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise NotFoundError("That media file does not exist.")
    if asset.owner_id != user.id:
        raise PermissionDeniedError("That media file belongs to another account.")
    if expected_kind and asset.kind != MediaKind(expected_kind):
        raise AppError(f"A {expected_kind} file is required here.")
    return asset


def verify_uploaded_object(asset: MediaAsset) -> tuple[bool, str | None]:
    """Confirm the object exists and that its real bytes match the declared kind."""
    headers = storage.get_object_headers(asset.storage_key)
    if headers is None:
        return False, "The upload did not arrive in storage. Please try again."

    actual_size = int(headers.get("ContentLength") or 0)
    if actual_size <= 0:
        return False, "The uploaded file is empty."
    if actual_size > settings.upload_max_bytes:
        storage.delete_object(asset.storage_key)
        return False, "The uploaded file is larger than the limit."

    declared = headers.get("ContentType") or asset.declared_content_type
    detected = None
    try:
        prefix = _read_prefix(asset.storage_key)
        detected = filetypes.detect_content_type(prefix)
    except Exception as exc:  # pragma: no cover - storage dependent
        logger.warning("content sniff failed for %s: %s", asset.storage_key, exc)

    if not filetypes.is_type_valid_for_kind(asset.kind.value, detected, declared):
        storage.delete_object(asset.storage_key)
        return False, "That file does not look like a valid {kind} file.".format(kind=asset.kind.value)

    asset.size_bytes = actual_size
    asset.detected_content_type = detected or declared
    asset.status = MediaStatus.uploaded
    return True, None


def _read_prefix(key: str, length: int = 32) -> bytes:
    from app.core.config import settings as app_settings
    from app.services.storage import get_client

    response = get_client().get_object(
        Bucket=app_settings.s3_bucket, Key=key, Range=f"bytes=0-{length - 1}"
    )
    return response["Body"].read()


def complete_upload(db: Session, user: User, asset_id: uuid.UUID) -> MediaAsset:
    asset = require_owned_asset(db, user, asset_id)
    if asset.status == MediaStatus.ready:
        return asset

    ok, error = verify_uploaded_object(asset)
    if not ok:
        asset.status = MediaStatus.failed
        asset.processing_error = error
        db.commit()
        raise AppError(error or "Upload verification failed.")

    asset.status = MediaStatus.processing
    asset.processing_error = None
    db.commit()

    if settings.video_processing_enabled and asset.kind == MediaKind.video:
        _enqueue_processing(asset.id)
    else:
        # Images and audio need no transcoding pass.
        asset.status = MediaStatus.ready
        db.commit()

    db.refresh(asset)
    return asset


def _enqueue_processing(asset_id: uuid.UUID) -> None:
    try:
        from app.workers.tasks import process_media_asset

        process_media_asset.delay(str(asset_id))
    except Exception as exc:  # pragma: no cover - broker dependent
        logger.error("could not enqueue processing for %s: %s", asset_id, exc)
        with SessionLocal() as session:
            asset = session.get(MediaAsset, asset_id)
            if asset:
                asset.status = MediaStatus.failed
                asset.processing_error = "Background worker is unavailable. Start Redis and the Celery worker."
                session.commit()
        raise AppError(
            "Video processing is unavailable right now. The background worker is not running.",
            details={"hint": "Start Redis and the Celery worker (see README)."},
        ) from exc


def asset_to_out(asset: MediaAsset, *, private: bool = False) -> MediaAssetOut:
    playback = None
    if asset.status == MediaStatus.ready:
        playback = storage.stable_media_url(asset.id, asset.storage_key, private=private)
    return MediaAssetOut(
        id=asset.id,
        kind=asset.kind.value,
        status=asset.status.value,
        storage_key=asset.storage_key,
        size_bytes=asset.size_bytes,
        duration_seconds=asset.duration_seconds,
        width=asset.width,
        height=asset.height,
        detected_content_type=asset.detected_content_type,
        thumbnail_url=storage.stable_media_url(asset.id, asset.thumbnail_key, thumbnail=True, private=private),
        playback_url=playback,
        renditions=asset.renditions or [],
        processing_error=asset.processing_error,
        created_at=asset.created_at,
    )


def list_pending_assets(db: Session, user: User) -> list[MediaAsset]:
    stmt = (
        select(MediaAsset)
        .where(MediaAsset.owner_id == user.id)
        .order_by(MediaAsset.created_at.desc())
        .limit(50)
    )
    return list(db.execute(stmt).scalars())

ABANDONED_AFTER_HOURS = 24


def _cleanup_abandoned_uploads(db: Session, user: User) -> None:
    """Best-effort sweep of tickets the browser never finished.

    A ticket is created before the browser starts PUTting bytes. If the user closes
    the tab, the row would linger forever and (for buckets using incomplete multipart
    uploads) so could partial objects. Failures here must never block a new upload.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ABANDONED_AFTER_HOURS)
    try:
        stale = list(
            db.execute(
                select(MediaAsset).where(
                    MediaAsset.owner_id == user.id,
                    MediaAsset.status.in_([MediaStatus.pending, MediaStatus.uploading, MediaStatus.failed]),
                    MediaAsset.created_at < cutoff,
                )
            ).scalars()
        )
        for asset in stale:
            key, thumbnail = asset.storage_key, asset.thumbnail_key
            db.delete(asset)
            db.commit()
            for object_key in filter(None, [key, thumbnail]):
                try:
                    storage.delete_object(object_key)
                except Exception:  # pragma: no cover - storage outage
                    logger.warning("could not remove abandoned object %s", object_key)
    except Exception:  # pragma: no cover - cleanup must never fail a ticket
        db.rollback()
        logger.exception("abandoned-upload cleanup failed")
