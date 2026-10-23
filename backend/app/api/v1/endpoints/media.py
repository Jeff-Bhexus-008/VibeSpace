"""Media upload routes: authorise, complete, poll status, discard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, PageWindow
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.ratelimit import rate_limit
from app.models.media import MediaAsset
from app.schemas.common import AckResponse, Page
from app.schemas.media import (
    CompleteUploadRequest,
    MediaAssetOut,
    UploadStatusResponse,
    UploadTicket,
    UploadTicketRequest,
)
from app.services import storage, uploads

router = APIRouter(prefix="/uploads", tags=["uploads"])

upload_limit = Depends(rate_limit("upload", settings.rate_limit_upload_per_hour, 3600))


@router.post("/ticket", response_model=UploadTicket, status_code=201, dependencies=[upload_limit])
def create_upload_ticket(payload: UploadTicketRequest, user: CurrentUser, db: DbSession) -> UploadTicket:
    """Returns a short-lived presigned PUT URL — storage credentials stay on the server."""
    return uploads.create_upload_ticket(db, user, payload)


@router.post("/complete", response_model=UploadStatusResponse)
def complete_upload(payload: CompleteUploadRequest, user: CurrentUser, db: DbSession) -> UploadStatusResponse:
    asset = uploads.complete_upload(db, user, payload.asset_id)
    return UploadStatusResponse(asset=uploads.asset_to_out(asset), ready=asset.status.value == "ready")


@router.get("", response_model=Page[MediaAssetOut])
def recent_uploads(user: CurrentUser, db: DbSession, window: PageWindow) -> Page[MediaAssetOut]:
    stmt = (
        select(MediaAsset)
        .where(MediaAsset.owner_id == user.id)
        .order_by(MediaAsset.created_at.desc())
        .limit(window["limit"])
    )
    rows = list(db.execute(stmt).scalars())
    return Page(items=[uploads.asset_to_out(asset) for asset in rows], has_more=len(rows) == window["limit"])


@router.get("/config/status", response_model=dict)
def storage_status() -> dict:
    """Setup check for the Create screen: explains an unconfigured storage backend clearly."""
    from app.services.media_processing import ffmpeg_available

    return {
        "storage_configured": settings.storage_configured,
        "bucket": settings.s3_bucket if settings.storage_configured else None,
        "max_bytes": settings.upload_max_bytes,
        "video_processing_enabled": settings.video_processing_enabled,
        "ffmpeg_available": ffmpeg_available(),
        "renditions": settings.rendition_list,
    }


@router.get("/{asset_id}", response_model=UploadStatusResponse)
def upload_status(asset_id: uuid.UUID, user: CurrentUser, db: DbSession) -> UploadStatusResponse:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.owner_id != user.id:
        raise NotFoundError("That upload does not exist.")
    return UploadStatusResponse(
        asset=uploads.asset_to_out(asset, private=asset.status.value != "ready"),
        ready=asset.status.value == "ready",
    )


@router.delete("/{asset_id}", response_model=AckResponse)
def discard_upload(asset_id: uuid.UUID, user: CurrentUser, db: DbSession) -> AckResponse:
    asset = uploads.require_owned_asset(db, user, asset_id)
    key, thumbnail = asset.storage_key, asset.thumbnail_key
    db.delete(asset)
    db.commit()
    for object_key in filter(None, [key, thumbnail]):
        storage.delete_object(object_key)
    return AckResponse(message="Upload discarded.")