"""S3-compatible object storage (Cloudflare R2, AWS S3, MinIO, Backblaze B2…).

Secrets stay on the server: the browser only ever receives short-lived
presigned URLs scoped to a single object key we generated.
"""

from __future__ import annotations

import logging
import mimetypes
import uuid
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.errors import ServiceUnavailableError

logger = logging.getLogger("vibespace.storage")

_client = None


def require_configured() -> None:
    if not settings.storage_configured:
        raise ServiceUnavailableError(
            "Media storage is not configured yet. Set S3_BUCKET, S3_ACCESS_KEY_ID and "
            "S3_SECRET_ACCESS_KEY (see .env.example) before uploading.",
            details={"missing": ["S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"]},
        )


def get_client():
    global _client
    require_configured()
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if settings.s3_use_path_style else "auto"},
            ),
        )
    return _client


def build_storage_key(owner_id: uuid.UUID, kind: str, filename: str, purpose: str) -> str:
    """Unique, non-guessable key. A user can never overwrite someone else's object."""
    extension = Path(filename).suffix.lower()[:10] or ".bin"
    return f"{purpose}/{kind}/{owner_id}/{uuid.uuid4().hex}{extension}"


def guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(filename)[0] or fallback


def create_presigned_put(key: str, content_type: str, ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds or settings.upload_url_ttl_seconds
    try:
        return get_client().generate_presigned_url(
            "put_object",
            Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl,
        )
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - infrastructure dependent
        logger.error("failed to presign upload: %s", exc)
        raise ServiceUnavailableError("Upload service is temporarily unavailable.") from exc


def create_presigned_get(key: str, ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds or settings.media_url_ttl_seconds
    try:
        return get_client().generate_presigned_url(
            "get_object", Params={"Bucket": settings.s3_bucket, "Key": key}, ExpiresIn=ttl
        )
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover
        logger.error("failed to presign media url: %s", exc)
        raise ServiceUnavailableError("Media is temporarily unavailable.") from exc


def public_url(key: str | None) -> str | None:
    """Public/CDN URL for published media (no signing round-trip on every feed render)."""
    if not key:
        return None
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    return create_presigned_get(key)


def media_url(key: str | None, *, private: bool = False) -> str | None:
    if not key:
        return None
    if private or not settings.s3_public_base_url:
        return create_presigned_get(key)
    return public_url(key)


def get_object_headers(key: str) -> dict | None:
    try:
        return get_client().head_object(Bucket=settings.s3_bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    except BotoCoreError as exc:  # pragma: no cover
        logger.error("head_object failed: %s", exc)
        raise ServiceUnavailableError("Storage is temporarily unavailable.") from exc


def download_to_path(key: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        get_client().download_file(settings.s3_bucket, key, str(destination))
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover
        logger.error("download failed for %s: %s", key, exc)
        raise ServiceUnavailableError("Could not read the uploaded file from storage.") from exc
    return destination


def upload_path(key: str, source: Path, content_type: str | None = None) -> None:
    try:
        get_client().upload_file(
            str(source),
            settings.s3_bucket,
            key,
            ExtraArgs={"ContentType": content_type or guess_content_type(source.name)},
        )
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover
        logger.error("upload failed for %s: %s", key, exc)
        raise ServiceUnavailableError("Could not write the processed media to storage.") from exc


def delete_object(key: str) -> None:
    try:
        get_client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover
        logger.warning("delete failed for %s: %s", key, exc)