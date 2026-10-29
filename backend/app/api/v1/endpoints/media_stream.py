"""Durable media delivery for uploads stored in object storage (Cloudflare R2).

Two delivery modes, chosen by configuration:

* ``S3_PUBLIC_BASE_URL`` / ``R2_PUBLIC_BASE_URL`` set → media is served directly from
  the bucket's public domain, so these routes are not used for playback.
* Bucket is private (default) → ``/api/v1/media/{asset_id}/stream`` authorises the
  viewer and redirects to a freshly signed GET URL. The redirect re-signs on every
  request, so playback keeps working after the user leaves and returns (a presigned
  URL stored in the database would expire within the hour).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DbSession, OptionalUser
from app.core.config import settings
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.enums import MediaStatus, VideoStatus, VideoVisibility
from app.models.media import MediaAsset
from app.models.video import Video
from app.services import storage

router = APIRouter(prefix="/media", tags=["media"])


def _is_publicly_published(db: DbSession, asset: MediaAsset) -> bool:
    """True when the asset backs a video any visitor may watch."""
    row = db.execute(
        select(Video.id).where(
            Video.media_asset_id == asset.id,
            Video.status == VideoStatus.ready,
            Video.published_at.is_not(None),
            Video.visibility.in_([VideoVisibility.public, VideoVisibility.unlisted]),
        )
    ).first()
    return row is not None


def _authorise(db: DbSession, asset: MediaAsset, viewer) -> None:
    if viewer is not None and viewer.id == asset.owner_id:
        return
    if _is_publicly_published(db, asset):
        return
    if viewer is None:
        raise PermissionDeniedError("Sign in to view this media.")
    raise NotFoundError("That media file is not available.")


def _redirect(key: str) -> RedirectResponse:
    if settings.s3_public_base_url:
        target = storage.public_url(key)
    else:
        target = storage.create_presigned_get(key)
    # 307 keeps the method (and any Range header) intact through the redirect.
    return RedirectResponse(target, status_code=307, headers={"Cache-Control": "private, max-age=60"})


@router.get("/{asset_id}/stream")
def stream_asset(asset_id: uuid.UUID, request: Request, db: DbSession, viewer: OptionalUser) -> RedirectResponse:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.status != MediaStatus.ready:
        raise NotFoundError("That media file is not available.")
    _authorise(db, asset, viewer)
    return _redirect(asset.storage_key)


@router.get("/{asset_id}/thumbnail")
def stream_thumbnail(asset_id: uuid.UUID, db: DbSession, viewer: OptionalUser) -> RedirectResponse:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or not asset.thumbnail_key:
        raise NotFoundError("That thumbnail is not available.")
    _authorise(db, asset, viewer)
    return _redirect(asset.thumbnail_key)
