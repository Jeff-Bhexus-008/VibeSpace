"""Health and readiness endpoints (used by Render and by uptime monitoring)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.media_processing import ffmpeg_available

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness: the process is up. Never touches dependencies."""
    return {"status": "ok", "version": __version__, "environment": settings.environment}


@router.get("/health/ready")
def readiness() -> JSONResponse:
    """Readiness: reports which dependencies are actually usable, so setup gaps are visible."""
    checks: dict[str, dict] = {}

    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:  # pragma: no cover - environment dependent
        checks["database"] = {"ok": False, "error": str(exc)[:200]}

    try:
        from app.core.ratelimit import get_redis

        get_redis().ping()
        checks["redis"] = {"ok": True}
    except Exception as exc:  # pragma: no cover
        checks["redis"] = {"ok": False, "error": str(exc)[:200]}

    checks["object_storage"] = {
        "ok": settings.storage_configured,
        "detail": None if settings.storage_configured else "Set S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY",
    }
    checks["video_processing"] = {
        "ok": ffmpeg_available() if settings.video_processing_enabled else True,
        "detail": None if ffmpeg_available() else f"Install FFmpeg ({settings.ffmpeg_binary}) on the worker host",
        "enabled": settings.video_processing_enabled,
    }
    checks["email"] = {
        "ok": settings.email_delivery_configured,
        "detail": None if settings.email_delivery_configured else "Set SMTP_* to deliver verification and reset mail",
    }

    ready = checks["database"]["ok"] and checks["redis"]["ok"]
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "degraded", "checks": checks},
    )