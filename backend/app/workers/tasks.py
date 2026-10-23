"""Media processing tasks: probe, thumbnail, rendition transcode.

Each task owns its own database session and temporary directory. Failures are
retried with backoff and always leave the media asset in an explainable state.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import MediaStatus, VideoStatus
from app.models.media import MediaAsset
from app.models.video import Video
from app.services import media_processing, storage
from app.workers.celery_app import celery_app

logger = logging.getLogger("vibespace.worker")


@celery_app.task(bind=True, name="media.process_asset", max_retries=3, default_retry_delay=60)
def process_media_asset(self, asset_id: str) -> dict:
    """Download the original, extract metadata, build thumbnail + renditions, mark it ready."""
    asset_uuid = uuid.UUID(asset_id)
    workdir = Path(tempfile.mkdtemp(prefix=f"vibespace-{asset_id[:8]}-"))

    try:
        with SessionLocal() as session:
            asset = session.get(MediaAsset, asset_uuid)
            if asset is None:
                return {"asset_id": asset_id, "status": "missing"}

            asset.status = MediaStatus.processing
            asset.processing_attempts = (asset.processing_attempts or 0) + 1
            session.commit()

            storage_key = asset.storage_key
            kind = asset.kind.value
            owner_id = asset.owner_id

        source = workdir / f"original{Path(storage_key).suffix or '.mp4'}"
        storage.download_to_path(storage_key, source)

        if kind != "video":
            _finish_without_transcode(asset_uuid)
            return {"asset_id": asset_id, "status": "ready", "skipped": "not a video"}

        media_processing.require_ffmpeg()
        metadata = media_processing.probe(source)

        thumbnail_path = media_processing.generate_thumbnail(source, workdir / "thumbnail.jpg")
        thumbnail_key = f"thumbnails/{asset_uuid}.jpg"
        storage.upload_path(thumbnail_key, thumbnail_path, "image/jpeg")

        renditions: list[dict] = []
        for label in media_processing.renditions_to_build(metadata.height):
            target = workdir / f"{label}.mp4"
            try:
                media_processing.transcode_rendition(source, target, label)
            except Exception as exc:  # one bad rendition must not fail the whole upload
                logger.warning("rendition %s failed for %s: %s", label, asset_id, exc)
                continue
            key = f"renditions/{asset_uuid}/{label}.mp4"
            storage.upload_path(key, target, "video/mp4")
            renditions.append(
                {
                    "label": label,
                    "key": key,
                    "height": media_processing.RENDITION_HEIGHTS[label],
                    "bitrate": media_processing.RENDITION_BITRATES.get(label),
                }
            )

        _mark_ready(asset_uuid, metadata, thumbnail_key, renditions, owner_id)
        return {
            "asset_id": asset_id,
            "status": "ready",
            "duration_seconds": metadata.duration_seconds,
            "renditions": [item["label"] for item in renditions],
        }

    except SoftTimeLimitExceeded as exc:  # pragma: no cover - long media
        _mark_failed(asset_uuid, "Processing took too long and was stopped.")
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.exception("media processing failed for %s", asset_id)
        _mark_failed(asset_uuid, str(exc)[:500])
        raise self.retry(exc=exc)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _mark_ready(
    asset_id: uuid.UUID,
    metadata: media_processing.VideoMetadata,
    thumbnail_key: str,
    renditions: list[dict],
    owner_id: uuid.UUID,
) -> None:
    with SessionLocal() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            return
        asset.status = MediaStatus.ready
        asset.width = metadata.width
        asset.height = metadata.height
        asset.duration_seconds = metadata.duration_seconds
        asset.frame_rate = metadata.frame_rate
        asset.has_audio = metadata.has_audio
        asset.thumbnail_key = thumbnail_key
        asset.renditions = renditions
        asset.processing_error = None
        asset.processed_at = datetime.now(timezone.utc)

        # Publishing is possible as soon as processing finishes.
        for video in session.query(Video).filter(Video.media_asset_id == asset_id).all():
            if video.status == VideoStatus.processing:
                video.status = VideoStatus.ready

        session.commit()

    if settings.email_delivery_configured:
        _notify(owner_id, asset_id, ready=True)


def _finish_without_transcode(asset_id: uuid.UUID) -> None:
    with SessionLocal() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is not None:
            asset.status = MediaStatus.ready
            asset.processed_at = datetime.now(timezone.utc)
            session.commit()


def _mark_failed(asset_id: uuid.UUID, reason: str) -> None:
    with SessionLocal() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            return
        asset.status = MediaStatus.failed
        asset.processing_error = reason
        for video in session.query(Video).filter(Video.media_asset_id == asset_id).all():
            video.status = VideoStatus.draft
        session.commit()


def _notify(owner_id: uuid.UUID, asset_id: uuid.UUID, *, ready: bool) -> None:
    """In-app notification when processing finishes (best effort, never fatal)."""
    try:
        from app.models.enums import NotificationType
        from app.services.notifications import create_notification

        with SessionLocal() as session:
            create_notification(
                session,
                user_id=owner_id,
                type=NotificationType.system,
                entity_type="media_asset",
                entity_id=asset_id,
                payload={"status": "ready" if ready else "failed"},
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("could not notify owner %s: %s", owner_id, exc)